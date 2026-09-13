"""Independent history goldens and closed-profile adversarial checks."""
import builtins
import copy
import hashlib
import json
import socket
import subprocess
import time
import unicodedata
from pathlib import Path

import pytest

from video_paper_wiki import assessment_history as history
from video_paper_wiki import identity, projection_runtime
from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document

FIXTURE = json.loads((Path(__file__).parent / "fixtures/assessment-history/complete-vectors.json").read_text())
SHAPE = "SCHEMA_INVALID"
CHAIN = "ASSESSMENT_CHAIN_INVALID"
FP = "EVIDENCE_FINGERPRINT_MISMATCH"
CROSS = "CROSS_OBJECT_IDENTITY_MISMATCH"
LIMIT = "PROJECTION_LIMIT_EXCEEDED"
STATES = ("provisional", "accepted", "contested", "unsupported", "deprecated")


def canonical(value):
    # Independent reference for these ASCII-key, integer/string-only objects.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def seal(event):
    event["event_id"] = "ase-" + sha(canonical({k: v for k, v in event.items() if k != "event_id"}))[:20]
    return event


def one(text="A stable claim.", evidence=None):
    subject = "paper:arxiv:2311.15127"
    material = "video-paper-wiki.claim.v1\0" + subject + "\0" + " ".join(unicodedata.normalize("NFKC", text).split())
    claim_id = "clm-" + sha(material)[:20]
    claim = {"claim_id": claim_id, "stable_subject_id": subject, "canonical_claim_text": text,
             "evidence": [] if evidence is None else evidence, "assessment": "provisional", "reviewed_at": None}
    event = seal({"schema": "video-paper-wiki.assessment-event.v1", "claim_id": claim_id,
                  "previous_event_id": None, "actor_kind": "system", "transition_kind": "genesis",
                  "from_assessment": None, "to_assessment": "provisional", "claim_text_sha256": sha(text),
                  "evidence_fingerprint": FIXTURE["fingerprints"]["empty"]["sha256"],
                  "decided_by": "fixture", "decided_at": "2026-09-01T00:00:00Z", "reason": "Synthetic only."})
    return [claim], [event]


def append(claims, events, target, *, kind="human_assessment", fingerprint=None, at="2026-09-01T00:00:00Z"):
    parent = events[-1]
    event = seal({**parent, "previous_event_id": parent["event_id"], "actor_kind": "human" if kind == "human_assessment" else "system",
                  "transition_kind": kind, "from_assessment": parent["to_assessment"], "to_assessment": target,
                  "evidence_fingerprint": parent["evidence_fingerprint"] if fingerprint is None else fingerprint,
                  "decided_at": at})
    events.append(event)
    claims[0]["assessment"] = target
    claims[0]["reviewed_at"] = at[:10] if kind == "human_assessment" else None
    return event


def derive(claims, events):
    return history.derive_assessment_heads(claims=claims, events=events)


def refused(code, claims, events, *, pointer=None, exit_code=2):
    with pytest.raises(ContractError) as caught:
        derive(claims, events)
    error = caught.value
    assert error.code == code and error.exit_code == exit_code
    assert set(error.details) == {"instance_pointer"}
    assert type(error.details["instance_pointer"]) is str
    json.dumps(error.details, ensure_ascii=False).encode()
    if pointer is not None:
        assert error.details["instance_pointer"] == pointer
    return error


def test_independent_fixed_complete_history_and_identity_vectors():
    original = copy.deepcopy(FIXTURE)
    result = derive(FIXTURE["claims"], FIXTURE["events"])
    assert result == FIXTURE["heads"]
    assert list(result) == sorted(result)
    assert result is not FIXTURE["heads"]
    assert FIXTURE == original
    for vector, event in zip(FIXTURE["event_vectors"], FIXTURE["events"]):
        assert identity.assessment_event_id(event) == vector["event_id"]
        assert sha(vector["canonical_utf8"]) == vector["sha256"]
        assert canonical({k: v for k, v in event.items() if k != "event_id"}) == vector["canonical_utf8"]
    for claim, vector in zip(FIXTURE["claims"], FIXTURE["claim_vectors"]):
        assert identity.claim_id(claim["stable_subject_id"], claim["canonical_claim_text"]) == vector["claim_id"]
        assert identity.sha256_hex(claim["canonical_claim_text"]) == vector["text_sha256"]
        assert sha(vector["material_utf8"])[:20] == vector["claim_id"][4:]
    evidence = FIXTURE["evidence"]
    for name, items in (("empty", []), ("pdf", [evidence["pdf"]]), ("code", [evidence["code"]]),
                        ("pdf_duplicate", [evidence["pdf"], evidence["pdf"]]), ("both", list(evidence.values()))):
        assert identity.evidence_fingerprint(items) == FIXTURE["fingerprints"][name]["sha256"]


def test_order_independent_result_and_no_mutable_aliases():
    claims, events = copy.deepcopy((FIXTURE["claims"], FIXTURE["events"]))
    result = derive(claims[::-1], events[::-1])
    assert result == FIXTURE["heads"] and list(result) == sorted(result)
    claims.clear()
    events.clear()
    assert result == FIXTURE["heads"]
    result.clear()
    assert derive(FIXTURE["claims"], FIXTURE["events"]) == FIXTURE["heads"]
    assert derive([], []) == {}


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("target", STATES[1:])
def test_every_human_state_edge(state, target):
    claims, events = one()
    if state != "provisional":
        append(claims, events, state)
    append(claims, events, target)
    if state == target:
        refused(CHAIN, claims, events, pointer=f"/events/{len(events)-1}/to_assessment")
    else:
        assert derive(claims, events) == {claims[0]["claim_id"]: events[-1]["event_id"]}


@pytest.mark.parametrize("state", STATES)
def test_every_invalidation_edge_and_system_date_reset(state):
    claims, events = one()
    if state != "provisional":
        append(claims, events, state)
    claims[0]["evidence"] = [copy.deepcopy(FIXTURE["evidence"]["pdf"])]
    append(claims, events, "provisional", kind="evidence_invalidation", fingerprint=FIXTURE["fingerprints"]["pdf"]["sha256"])
    assert claims[0]["reviewed_at"] is None
    assert derive(claims, events)[claims[0]["claim_id"]] == events[-1]["event_id"]


@pytest.mark.parametrize("at", ["0001-01-01T00:00:00Z", "9999-12-31T23:59:59Z", "2024-02-29T23:59:59.1Z",
                                "2024-02-29T23:59:59.123456789Z", "2024-02-29T23:59:59.100Z"])
def test_valid_utc_dates_keep_original_precision(at):
    claims, events = one()
    append(claims, events, "accepted", at=at)
    assert derive(claims, events)[claims[0]["claim_id"]] == events[-1]["event_id"]
    assert events[-1]["decided_at"] == at


@pytest.mark.parametrize("at", ["0000-01-01T00:00:00Z", "2023-02-29T00:00:00Z", "2026-13-01T00:00:00Z",
                                "2026-09-01T24:00:00Z", "2026-09-01T00:60:00Z", "2026-09-01T00:00:60Z",
                                "2026-09-01T00:00:00.1234567890Z", "2026-09-01T00:00:00.Z",
                                "2026-09-01T00:00:00z", "2026-09-01T00:00:00+00:00", "2026-09-01T00:00:00Z\n",
                                "2026-09-01t00:00:00Z", 1, False, None])
def test_invalid_utc_dates(at):
    claims, events = one()
    events[0]["decided_at"] = at
    seal(events[0])
    refused(SHAPE, claims, events, pointer="/events/0/decided_at")


@pytest.mark.parametrize("value", ["", False, 1, "0000-01-01", "2023-02-29", "2026-1-01", "2026-09-01\n"])
def test_invalid_reviewed_date(value):
    claims, events = one()
    claims[0]["reviewed_at"] = value
    refused(SHAPE, claims, events, pointer="/claims/0/reviewed_at")


def test_raw_text_hash_and_unchanged_claim_identity():
    claims, events = one("A stable claim.")
    claims[0]["canonical_claim_text"] = "  A\u2003stable claim.\n"
    assert identity.claim_id(claims[0]["stable_subject_id"], claims[0]["canonical_claim_text"]) == claims[0]["claim_id"]
    refused(CROSS, claims, events, pointer="/events/0/claim_text_sha256")
    events[0]["claim_text_sha256"] = sha(claims[0]["canonical_claim_text"])
    seal(events[0])
    assert derive(claims, events)


@pytest.mark.parametrize("change", ["equal", "different", "normalized_equal"])
def test_duplicate_binding_precedes_individual_id_mismatch(change):
    claims, events = one()
    claims[0]["claim_id"] = "clm-" + "0" * 20
    other = copy.deepcopy(claims[0])
    if change == "different":
        other["canonical_claim_text"] = "Another claim."
    elif change == "normalized_equal":
        other["canonical_claim_text"] = "  A   stable claim. "
    claims.append(other)
    refused("CLAIM_ID_COLLISION" if change == "different" else "PRIMARY_OWNER_INVALID", claims, events,
            pointer="/claims/1/claim_id", exit_code=75 if change == "different" else 2)


def test_all_claim_shapes_precede_collision():
    claims, events = one()
    claims.append(copy.deepcopy(claims[0]))
    claims.append({**claims[0], "reviewed_at": False})
    refused(SHAPE, claims, events, pointer="/claims/2/reviewed_at")


@pytest.mark.parametrize("case", ["claim", "event", "text", "fingerprint", "assessment", "reviewed_at"])
def test_bound_hash_and_materialization_mismatches(case):
    claims, events = one()
    if case == "claim":
        claims[0]["claim_id"] = "clm-" + "0" * 20
        refused("CLAIM_ID_MISMATCH", claims, events, pointer="/claims/0/claim_id")
    elif case == "event":
        events[0]["event_id"] = "ase-" + "0" * 20
        refused("EVENT_ID_MISMATCH", claims, events, pointer="/events/0/event_id")
    elif case in {"text", "fingerprint"}:
        key = "claim_text_sha256" if case == "text" else "evidence_fingerprint"
        events[0][key] = "0" * 64
        seal(events[0])
        refused(CROSS if case == "text" else FP, claims, events, pointer="/events/0/" + key)
    else:
        claims[0][case] = "accepted" if case == "assessment" else "2026-09-01"
        refused(CROSS, claims, events, pointer="/claims/0/" + case)


@pytest.mark.parametrize("kind", ["human_assessment", "evidence_invalidation"])
def test_fingerprint_edge_policy(kind):
    claims, events = one()
    append(claims, events, "accepted" if kind == "human_assessment" else "provisional", kind=kind,
           fingerprint="a" * 64 if kind == "human_assessment" else None)
    refused(FP, claims, events, pointer="/events/1/evidence_fingerprint")


@pytest.mark.parametrize("case", ["missing", "unknown", "duplicate", "two_geneses", "dangling", "fork", "state", "cross_claim"])
def test_graph_refusals_with_recomputed_event_ids(case):
    claims, events = one()
    if case == "missing":
        events.clear()
    elif case == "unknown":
        claims.clear()
    elif case == "duplicate":
        events.append(copy.deepcopy(events[0]))
    elif case == "two_geneses":
        events.append(seal({**events[0], "reason": "Second genesis"}))
    elif case == "dangling":
        append(claims, events, "accepted")
        events[1]["previous_event_id"] = "ase-" + "0" * 20
        seal(events[1])
    elif case == "fork":
        append(claims, events, "accepted")
        events.append(seal({**events[-1], "to_assessment": "contested"}))
    elif case == "state":
        append(claims, events, "accepted")
        events[-1]["from_assessment"] = "contested"
        seal(events[-1])
    else:
        other_claims, other_events = one("A distinct claim.")
        claims.extend(other_claims)
        events.extend(other_events)
        event = {**events[0], "previous_event_id": events[1]["event_id"], "from_assessment": "provisional",
                 "actor_kind": "human", "transition_kind": "human_assessment", "to_assessment": "accepted"}
        events.append(seal(event))
    refused(CHAIN, claims, events)


def test_synthetic_disconnected_cycle_graph_control_without_real_id_claim():
    # Deliberately synthetic IDs, exercising the real graph routine independently
    # of content hash fixed points. The production public entry still hashes IDs.
    _claims, events = one()
    genesis = events[0]
    a = {**genesis, "event_id": "synthetic-a", "previous_event_id": "synthetic-b", "from_assessment": "provisional",
         "transition_kind": "evidence_invalidation", "evidence_fingerprint": "a" * 64}
    b = {**a, "event_id": "synthetic-b", "previous_event_id": "synthetic-a", "evidence_fingerprint": "b" * 64}
    chain = list(enumerate([genesis, a, b]))
    with pytest.raises(ContractError) as caught:
        history._chain_head(chain, {event["event_id"]: (index, event) for index, event in chain})
    assert caught.value.code == CHAIN
    assert caught.value.details["instance_pointer"] == "/events/1/previous_event_id"


def test_long_chain_is_iterative():
    claims, events = one()
    for index in range(1200):
        append(claims, events, "accepted" if index % 2 == 0 else "contested")
    assert derive(claims, events)[claims[0]["claim_id"]] == events[-1]["event_id"]


@pytest.mark.parametrize("value", [None, False, {}, (), "[]", b"[]"])
@pytest.mark.parametrize("side", ["claims", "events"])
def test_root_exact_list_requirement(side, value):
    claims, events = one()
    refused(SHAPE, value if side == "claims" else claims, value if side == "events" else events, pointer="/" + side)


@pytest.mark.parametrize("side,field,value", [
    ("claims", "evidence", None), ("claims", "evidence", False), ("claims", "canonical_claim_text", ""),
    ("claims", "canonical_claim_text", 1), ("claims", "assessment", False),
    ("claims", "stable_subject_id", "concept:v1:example"), ("claims", "stable_subject_id", "repo:github:Owner/repo"),
    ("claims", "stable_subject_id", "paper:arxiv:2311.15127\n"), ("claims", "claim_id", "clm-" + "a" * 20 + "\n"),
    ("events", "event_id", "ase-" + "a" * 20 + "\n"), ("events", "previous_event_id", False),
    ("events", "claim_text_sha256", "a" * 64 + "\n"), ("events", "evidence_fingerprint", 1.0),
    ("events", "schema", "video-paper-wiki.gate-decision.v1"), ("events", "reason", ""),
    ("events", "decided_by", []), ("events", "actor_kind", "human"), ("events", "from_assessment", "provisional"),
    ("events", "to_assessment", "accepted"), ("events", "transition_kind", "invented"),
])
def test_bad_field_shapes(side, field, value):
    claims, events = one()
    (claims if side == "claims" else events)[0][field] = value
    refused(SHAPE, claims, events, pointer=f"/{side}/0/{field}")


@pytest.mark.parametrize("side", ["claims", "events"])
def test_missing_keys_unknown_keys_and_safe_pointer_escaping(side):
    claims, events = one()
    item = (claims if side == "claims" else events)[0]
    key = "reviewed_at" if side == "claims" else "reason"
    del item[key]
    refused(SHAPE, claims, events, pointer=f"/{side}/0/{key}")
    item[key] = None if side == "claims" else "Synthetic"
    item["bad~/key"] = 0
    refused(SHAPE, claims, events, pointer=f"/{side}/0/bad~0~1key")


def test_python_tree_preflight_type_cycle_and_surrogate_safety():
    class CustomList(list):
        pass
    class CustomString(str):
        pass
    claims, events = one()
    refused(SHAPE, CustomList(claims), events, pointer="/claims")
    claims[0]["canonical_claim_text"] = CustomString("text")
    refused(SHAPE, claims, events, pointer="/claims/0/canonical_claim_text")
    for key in (1, None, ("tuple",)):
        claims, events = one()
        claims[0][key] = True
        refused(SHAPE, claims, events, pointer="/claims/0")
    claims, events = one()
    events[0]["reason"] = "\ud800"
    refused(SHAPE, claims, events, pointer="/events/0/reason")
    claims, events = one()
    claims[0]["evidence"].append(claims)
    refused(SHAPE, claims, events, pointer="/claims/0/evidence/0")
    claims, events = one()
    events[0]["reason"] = float("nan")
    refused(SHAPE, claims, events, pointer="/events/0/reason")


def test_global_budget_includes_virtual_root_keys_and_alias_occurrences(monkeypatch):
    monkeypatch.setattr(projection_runtime, "MAX_OCCURRENCES", 4)
    refused(LIMIT, [], [], pointer="")
    monkeypatch.setattr(projection_runtime, "MAX_OCCURRENCES", 5)
    assert derive([], []) == {}
    claims, events = one()
    claims[0]["evidence"] = [FIXTURE["evidence"]["pdf"], FIXTURE["evidence"]["pdf"]]
    def occurrences(value):
        if type(value) is dict:
            return 1 + len(value) + sum(occurrences(child) for child in value.values())
        if type(value) is list:
            return 1 + sum(occurrences(child) for child in value)
        return 1
    budget = occurrences({"claims": claims, "events": events})
    monkeypatch.setattr(projection_runtime, "MAX_OCCURRENCES", budget - 1)
    refused(LIMIT, claims, events)
    monkeypatch.setattr(projection_runtime, "MAX_OCCURRENCES", budget)
    refused(FP, claims, events)


@pytest.mark.parametrize("text", ["x" * 65536, "é" * 32768])
def test_exact_text_utf8_cap_and_first_byte_over(text):
    claims, events = one(text)
    assert derive(claims, events)
    claims[0]["canonical_claim_text"] += "x"
    refused(LIMIT, claims, events, pointer="/claims/0/canonical_claim_text")


def test_text_limit_precedes_identity_normalization(monkeypatch):
    claims, events = one()
    claims[0]["canonical_claim_text"] = "x" * 65537
    def unexpected(*args, **kwargs):
        raise AssertionError("identity normalization must not run")
    monkeypatch.setattr(identity, "claim_identity_material", unexpected)
    refused(LIMIT, claims, events, pointer="/claims/0/canonical_claim_text")


def test_wire_cap_exact_and_overflow_prefixed_pointer():
    evidence = copy.deepcopy(FIXTURE["evidence"]["code"])
    locator = {key: value for key, value in evidence.items() if key != "relation"}
    wire = "vpwiki-locator-v1:" + canonical({"schema": "video-paper-wiki.ledger-locator.v1", "locator": locator})
    evidence["symbol"] += "x" * (65536 - len(wire.encode()))
    claims, events = one(evidence=[evidence])
    events[0]["evidence_fingerprint"] = FIXTURE["fingerprints"]["code"]["sha256"]
    seal(events[0])
    assert derive(claims, events)
    evidence["symbol"] += "x"
    refused(LIMIT, claims, events, pointer="/claims/0/evidence/0")


@pytest.mark.parametrize("field,value,code", [("relation", "context", "LEDGER_EVIDENCE_INVALID"),
                                             ("page", True, "LEDGER_LOCATOR_INVALID"),
                                             ("page", 1.0, "LEDGER_LOCATOR_INVALID"),
                                             ("source_id", "src-bad\n", "LEDGER_LOCATOR_INVALID"),
                                             ("bbox", [0, 1, 2], "LEDGER_LOCATOR_INVALID")])
def test_full_evidence_refusal_and_pointer_prefix(field, value, code):
    item = copy.deepcopy(FIXTURE["evidence"]["pdf"])
    item[field] = value
    claims, events = one(evidence=[item])
    refused(code, claims, events, pointer=f"/claims/0/evidence/0/{field}")


def test_display_changes_and_permutation_preserve_fp_but_multiplicity_does_not():
    items = copy.deepcopy(list(FIXTURE["evidence"].values()))
    claims, events = one(evidence=items)
    events[0]["evidence_fingerprint"] = FIXTURE["fingerprints"]["both"]["sha256"]
    seal(events[0])
    items[0]["bbox"] = [0.5, 1, -10.5, 20]
    items[0]["charspan"] = [0, 999]
    items[1]["symbol"] = "changed"
    items.reverse()
    assert derive(claims, events)
    items.append(items[0])
    refused(FP, claims, events)


def test_opaque_reason_and_actor_preserve_schema_semantics_and_safe_errors():
    claims, events = one()
    events[0]["decided_by"] = " "
    events[0]["reason"] = "\t"
    seal(events[0])
    assert derive(claims, events)
    secret = "SECRET_CLAIM_OR_REASON_MUST_NOT_BE_LOGGED"
    events[0]["reason"] = {"value": secret}
    error = refused(SHAPE, claims, events)
    assert secret not in str(error) + json.dumps(error.details)


def test_old_event_schema_still_accepts_human_noop():
    claims, events = one()
    append(claims, events, "accepted")
    append(claims, events, "accepted")
    assert validate_document(events[-1]) is events[-1]
    refused(CHAIN, claims, events)


def test_warmed_pure_api_has_no_caller_io(monkeypatch):
    schema_by_title("video-paper-wiki.common.v1")
    claims, events = copy.deepcopy((FIXTURE["claims"], FIXTURE["events"]))
    def forbidden(*args, **kwargs):
        raise AssertionError("supplied-value validation must not perform I/O")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    assert derive(claims, events)


def test_aggregate_depth_integer_and_scalar_limits(monkeypatch):
    # Minimal envelope has 16 scalar bytes: quoted "claims" and "events" keys.
    monkeypatch.setattr(projection_runtime, "MAX_SCALAR_BYTES", 15)
    refused(LIMIT, [], [])
    monkeypatch.setattr(projection_runtime, "MAX_SCALAR_BYTES", 16)
    assert derive([], []) == {}
    monkeypatch.setattr(projection_runtime, "MAX_SCALAR_BYTES", 64 * 1024 * 1024)
    claims, events = one()
    events[0]["reason"] = 1 << 2048
    refused(LIMIT, claims, events, pointer="/events/0/reason")
    events[0]["reason"] = (1 << 2048) - 1
    refused(SHAPE, claims, events, pointer="/events/0/reason")
    for nested_lists, expected in ((61, SHAPE), (62, LIMIT)):
        value = None
        for _ in range(nested_lists):
            value = [value]
        events[0]["reason"] = value
        refused(expected, claims, events)


@pytest.mark.parametrize("field", ["relation", "source_id", "bbox"])
def test_whole_tree_nonjson_precedes_codec_domain_error(field):
    evidence = copy.deepcopy(FIXTURE["evidence"]["pdf"])
    evidence[field] = object()
    claims, events = one(evidence=[evidence])
    refused(SHAPE, claims, events, pointer=f"/claims/0/evidence/0/{field}")


def test_fingerprint_relation_and_content_changes_require_invalidation():
    evidence = copy.deepcopy(FIXTURE["evidence"]["pdf"])
    claims, events = one(evidence=[evidence])
    events[0]["evidence_fingerprint"] = FIXTURE["fingerprints"]["pdf"]["sha256"]
    seal(events[0])
    assert derive(claims, events)
    evidence["relation"] = "contradicts"
    refused(FP, claims, events)
    evidence["relation"] = "supports"
    evidence["artifact_sha256"] = "e" * 64
    refused(FP, claims, events)


def test_fractional_zeroes_are_event_identity_material():
    claims, events = one()
    append(claims, events, "accepted", at="2026-09-01T00:00:00.1Z")
    first_id = events[-1]["event_id"]
    events[-1]["decided_at"] = "2026-09-01T00:00:00.100Z"
    refused("EVENT_ID_MISMATCH", claims, events, pointer="/events/1/event_id")
    seal(events[-1])
    assert events[-1]["event_id"] != first_id
    assert derive(claims, events)[claims[0]["claim_id"]] == events[-1]["event_id"]
