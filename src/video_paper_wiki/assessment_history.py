"""Derive assessment heads from supplied complete histories, without Vault access.

Consistency of these values does not authenticate ownership, human approval,
publication, or completeness of the caller's event inventory.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from video_paper_wiki import identity
from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document
from video_paper_wiki.ledger_locator import encode_ledger_evidence
from video_paper_wiki.projection_runtime import _preflight

_TITLE = "video-paper-wiki.assessment-event.v1"
_LIMIT = "PROJECTION_LIMIT_EXCEEDED"
_SHAPE = "SCHEMA_INVALID"
_CHAIN = "ASSESSMENT_CHAIN_INVALID"
_FP = "EVIDENCE_FINGERPRINT_MISMATCH"
_CROSS = "CROSS_OBJECT_IDENTITY_MISMATCH"
_STATES = {"provisional", "accepted", "contested", "unsupported", "deprecated"}
_CLAIM_FIELDS = {"claim_id", "stable_subject_id", "canonical_claim_text", "evidence", "assessment", "reviewed_at"}
_CLAIM_ID = re.compile(r"clm-[0-9a-f]{20}")
_EVENT_ID = re.compile(r"ase-[0-9a-f]{20}")
_SHA = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z")
_MAX_TEXT_BYTES = 65536


def _fail(code: str, pointer: str, message: str, *, exit_code: int = 2) -> None:
    raise ContractError(code, message, {"instance_pointer": pointer}, exit_code=exit_code)


def _field(base: str, key: str) -> str:
    return base + "/" + key.replace("~", "~0").replace("/", "~1")


def _closed(value: object, fields: set[str], pointer: str) -> None:
    if type(value) is not dict:
        _fail(_SHAPE, pointer, "value must be an exact object")
    for key in value:
        if key not in fields:
            _fail(_SHAPE, _field(pointer, key), "object contains an undeclared field")
    for key in sorted(fields):
        if key not in value:
            _fail(_SHAPE, _field(pointer, key), "object is missing a required field")


def _pattern(value: object, pattern: re.Pattern, pointer: str) -> None:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(_SHAPE, pointer, "value does not match the complete field grammar")


def _date(value: object, pointer: str, *, timestamp: bool = False) -> None:
    _pattern(value, _UTC if timestamp else _DATE, pointer)
    try:
        if timestamp:
            datetime(int(value[:4]), int(value[5:7]), int(value[8:10]),
                     int(value[11:13]), int(value[14:16]), int(value[17:19]))
        else:
            date.fromisoformat(value)
    except ValueError:
        _fail(_SHAPE, pointer, "value must contain a valid Gregorian date and time")


def _claim_shape(claim: object, pointer: str) -> None:
    _closed(claim, _CLAIM_FIELDS, pointer)
    _pattern(claim["claim_id"], _CLAIM_ID, pointer + "/claim_id")
    subject = claim["stable_subject_id"]
    if (type(subject) is not str or not subject.startswith(("paper:", "repo:"))
            or not identity.is_stable_subject_id(subject)):
        _fail(_SHAPE, pointer + "/stable_subject_id", "subject must be canonical paper or repo identity")
    text = claim["canonical_claim_text"]
    if type(text) is not str or not text:
        _fail(_SHAPE, pointer + "/canonical_claim_text", "claim text must be a nonempty scalar string")
    if len(text) > _MAX_TEXT_BYTES or len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        _fail(_LIMIT, pointer + "/canonical_claim_text", "claim text exceeds the UTF-8 byte budget")
    if type(claim["assessment"]) is not str or claim["assessment"] not in _STATES:
        _fail(_SHAPE, pointer + "/assessment", "invalid ledger assessment")
    if claim["reviewed_at"] is not None:
        _date(claim["reviewed_at"], pointer + "/reviewed_at")
    evidence = claim["evidence"]
    if type(evidence) is not list:
        _fail(_SHAPE, pointer + "/evidence", "evidence must be an exact array")
    for index, item in enumerate(evidence):
        try:
            encode_ledger_evidence(item)
        except ContractError as exc:
            _fail(exc.code, f"{pointer}/evidence/{index}" + exc.details.get("instance_pointer", ""),
                  "evidence violates the frozen locator profile", exit_code=exc.exit_code)


def _event_shape(event: object, pointer: str) -> None:
    _closed(event, set(schema_by_title(_TITLE)["required"]), pointer)
    for key in ("event_id", "claim_id", "claim_text_sha256", "evidence_fingerprint"):
        pattern = _EVENT_ID if key == "event_id" else _CLAIM_ID if key == "claim_id" else _SHA
        _pattern(event[key], pattern, pointer + "/" + key)
    if event["previous_event_id"] is not None:
        _pattern(event["previous_event_id"], _EVENT_ID, pointer + "/previous_event_id")
    _date(event["decided_at"], pointer + "/decided_at", timestamp=True)
    for key in ("reason", "decided_by"):
        if type(event[key]) is not str or not event[key]:
            _fail(_SHAPE, pointer + "/" + key, "event metadata must be a nonempty scalar string")
    choices = {"schema": {_TITLE}, "actor_kind": {"human", "system"},
               "transition_kind": {"genesis", "human_assessment", "evidence_invalidation"},
               "from_assessment": _STATES | {None}, "to_assessment": _STATES}
    for key, allowed in choices.items():
        value = event[key]
        if value is not None and type(value) is not str:
            _fail(_SHAPE, pointer + "/" + key, "event field has an invalid type")
        if value not in allowed:
            _fail(_SHAPE, pointer + "/" + key, "event field is outside its declared choices")
    transition = event["transition_kind"]
    expected_actor = "human" if transition == "human_assessment" else "system"
    if event["actor_kind"] != expected_actor:
        _fail(_SHAPE, pointer + "/actor_kind", "actor does not match the transition kind")
    for key in ("previous_event_id", "from_assessment"):
        if (event[key] is None) != (transition == "genesis"):
            _fail(_SHAPE, pointer + "/" + key, "predecessor and from-state must match the transition kind")
    if (event["to_assessment"] == "provisional") != (transition != "human_assessment"):
        _fail(_SHAPE, pointer + "/to_assessment", "target state does not match the transition kind")
    try:
        validate_document(event, expected_schema=_TITLE)
    except ContractError as exc:
        suffix = "/event_id" if exc.code == "EVENT_ID_MISMATCH" else exc.details.get("instance_pointer", "")
        _fail(exc.code, pointer + suffix, "event violates its schema or content identity", exit_code=exc.exit_code)


def _chain_head(chain: list[tuple[int, dict]], by_id: dict[str, tuple[int, dict]]) -> str:
    """Check all graph edges and coverage; tests may use explicitly synthetic IDs."""
    children: dict[str, str] = {}
    genesis = []
    for index, event in chain:
        previous = event["previous_event_id"]
        pointer = f"/events/{index}"
        if previous is None:
            genesis.append(event["event_id"])
            continue
        parent_pair = by_id.get(previous)
        if parent_pair is None or parent_pair[1]["claim_id"] != event["claim_id"]:
            _fail(_CHAIN, pointer + "/previous_event_id", "predecessor must exist and belong to the same claim")
        if previous in children:
            _fail(_CHAIN, pointer + "/previous_event_id", "assessment history must not fork")
        children[previous] = event["event_id"]
        parent = parent_pair[1]
        if parent["to_assessment"] != event["from_assessment"]:
            _fail(_CHAIN, pointer + "/from_assessment", "child state must continue the parent state")
        if event["transition_kind"] == "human_assessment":
            if event["from_assessment"] == event["to_assessment"]:
                _fail(_CHAIN, pointer + "/to_assessment", "human assessment must change the state")
            if parent["evidence_fingerprint"] != event["evidence_fingerprint"]:
                _fail(_FP, pointer + "/evidence_fingerprint", "human assessment must retain the parent fingerprint")
        elif parent["evidence_fingerprint"] == event["evidence_fingerprint"]:
            _fail(_FP, pointer + "/evidence_fingerprint", "invalidation must change the parent fingerprint")
    if len(genesis) != 1:
        _fail(_CHAIN, f"/events/{chain[0][0]}/previous_event_id", "claim history must have exactly one genesis")
    seen: set[str] = set()
    cursor = genesis[0]
    while True:
        if cursor in seen:
            _fail(_CHAIN, f"/events/{by_id[cursor][0]}/previous_event_id", "assessment history must not cycle")
        seen.add(cursor)
        child = children.get(cursor)
        if child is None:
            break
        cursor = child
    if len(seen) != len(chain):
        unvisited = next(index for index, event in chain if event["event_id"] not in seen)
        _fail(_CHAIN, f"/events/{unvisited}/previous_event_id", "history must be one complete connected chain")
    return cursor


def derive_assessment_heads(*, claims: object, events: object) -> dict[str, str]:
    """Validate all supplied claim histories and return their sorted terminal IDs."""
    try:
        _preflight({"claims": claims, "events": events})
    except ContractError as exc:
        _fail(_LIMIT if exc.code == _LIMIT else _SHAPE, exc.details.get("instance_pointer", ""),
              "history input is not a supported bounded value tree")
    for name, values in (("claims", claims), ("events", events)):
        if type(values) is not list:
            _fail(_SHAPE, "/" + name, "history inputs must be exact arrays")
    for index, claim in enumerate(claims):
        _claim_shape(claim, f"/claims/{index}")
    materials: dict[str, tuple[str, str]] = {}
    for index, claim in enumerate(claims):
        material = identity.claim_identity_material(claim["stable_subject_id"], claim["canonical_claim_text"])
        claim_id = claim["claim_id"]
        if claim_id in materials:
            collision = materials[claim_id] != material
            _fail("CLAIM_ID_COLLISION" if collision else "PRIMARY_OWNER_INVALID", f"/claims/{index}/claim_id",
                  "claim ID has conflicting identity material" if collision else "claim ID has duplicate bindings",
                  exit_code=75 if collision else 2)
        materials[claim_id] = material
    bindings = {}
    for index, claim in enumerate(claims):
        expected = identity.claim_id(claim["stable_subject_id"], claim["canonical_claim_text"])
        if expected != claim["claim_id"]:
            _fail("CLAIM_ID_MISMATCH", f"/claims/{index}/claim_id", "claim ID does not match its identity material")
        bindings[expected] = (index, claim, identity.sha256_hex(claim["canonical_claim_text"]),
                              identity.evidence_fingerprint(claim["evidence"]))
    by_id: dict[str, tuple[int, dict]] = {}
    chains: dict[str, list[tuple[int, dict]]] = {}
    for index, event in enumerate(events):
        pointer = f"/events/{index}"
        _event_shape(event, pointer)
        if event["event_id"] in by_id:
            _fail(_CHAIN, pointer + "/event_id", "event ID occurs more than once")
        binding = bindings.get(event["claim_id"])
        if binding is None:
            _fail(_CHAIN, pointer + "/claim_id", "event belongs to an unknown claim")
        if event["claim_text_sha256"] != binding[2]:
            _fail(_CROSS, pointer + "/claim_text_sha256", "event does not bind the exact ledger text")
        by_id[event["event_id"]] = (index, event)
        chains.setdefault(event["claim_id"], []).append((index, event))
    heads = {}
    for claim_id in sorted(bindings):
        index, claim, _text_hash, fingerprint = bindings[claim_id]
        chain = chains.get(claim_id)
        if chain is None:
            _fail(_CHAIN, f"/claims/{index}/claim_id", "claim has no assessment history")
        head_id = _chain_head(chain, by_id)
        event_index, head = by_id[head_id]
        if head["evidence_fingerprint"] != fingerprint:
            _fail(_FP, f"/events/{event_index}/evidence_fingerprint", "head does not bind current ledger evidence")
        if claim["assessment"] != head["to_assessment"]:
            _fail(_CROSS, f"/claims/{index}/assessment", "ledger assessment differs from its head")
        reviewed_at = head["decided_at"][:10] if head["actor_kind"] == "human" else None
        if claim["reviewed_at"] != reviewed_at:
            _fail(_CROSS, f"/claims/{index}/reviewed_at", "ledger review date differs from its head")
        heads[claim_id] = head_id
    return heads
