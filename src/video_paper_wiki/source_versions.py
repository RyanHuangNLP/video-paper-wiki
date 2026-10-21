"""Immutable source association and display history over supplied pure material."""
from __future__ import annotations

import copy

from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source import validate_payload
from video_paper_wiki.markdown_source_contracts import OBSERVATION
from video_paper_wiki.source_registration import registration_proof
from video_paper_wiki.source_semantics_contracts import (
    ASSOCIATION, DECISION, HEADS, LIMIT, association_id, association_reference,
    byte_map, calendar, decision_id, digest, extraction_descriptor, fail,
    preflight, sha, source_id, validate,
)


def _version_key(association):
    version = association["version"]
    return (association["paper_id"], version["kind"],
            version["label"] if version["kind"] == "declared" else association["raw"]["sha256"])


def association_inventory(values):
    preflight(values)
    if type(values) is not list:
        fail("SOURCE_ASSOCIATION_INVALID", "association inventory must be an array")
    if len(values) > 1024:
        fail(LIMIT, "association inventory exceeds its bound")
    documents = [validate(value, ASSOCIATION) for value in values]
    result, keys, owners = {}, set(), {}
    for index, doc in enumerate(documents):
        aid, key = doc["association_id"], _version_key(doc)
        if aid in result or key in keys:
            fail("SOURCE_ASSOCIATION_INVALID", "association identity or version key is duplicated", f"/{index}")
        keys.add(key)
        for identity in (doc["source_id"], doc["raw"]["sha256"]):
            if identity in owners and owners[identity] != doc["paper_id"]:
                fail("SOURCE_ASSOCIATION_INVALID", "one source has multiple paper owners", f"/{index}")
            owners[identity] = doc["paper_id"]
        result[aid] = doc
    return result


def associate_source(observation, *, raw_bytes, head_bytes, receipt_bytes, ledger_bytes, existing):
    """Propose/reuse a source association; no publication or provenance is minted."""
    preflight({"observation": observation, "existing": existing})
    observed = validate(observation, OBSERVATION)
    prior = association_inventory(existing)
    byte_map(receipt_bytes, "/receipt_bytes", maximum=1024 * 1024)
    for data, at, maximum in ((head_bytes, "/head_bytes", 1024 * 1024),
                              (ledger_bytes, "/ledger_bytes", 16 * 1024 * 1024)):
        if type(data) is not bytes:
            fail("SOURCE_REGISTRATION_INVALID", "registration material requires exact bytes", at)
        if len(data) > maximum:
            fail(LIMIT, "registration material exceeds its byte bound", at)
    if type(raw_bytes) is not bytes:
        fail("SOURCE_INVENTORY_INVALID", "source payload must be exact bytes", "/raw_bytes")
    if len(raw_bytes) > 8388608:
        fail(LIMIT, "source payload exceeds its byte bound", "/raw_bytes")
    validate_payload(raw_bytes, observed)
    raw = {"path": f".raw/captured/{observed['markdown']['sha256']}.md", **observed["markdown"]}
    sid = source_id(raw)
    registration = registration_proof(raw, sid, head_bytes=head_bytes,
                                      receipt_bytes=receipt_bytes, ledger_bytes=ledger_bytes)
    doc = {"schema": ASSOCIATION, "association_id": "sva-" + "0" * 64,
           "paper_id": observed["paper_id"], "source_id": sid, "version": observed["version"],
           "raw": raw, "observation": observed, "registration": registration,
           "extraction": extraction_descriptor(observed)}
    doc["association_id"] = association_id(doc)
    doc = validate(doc, ASSOCIATION)
    key = _version_key(doc)
    for old in prior.values():
        if _version_key(old) != key:
            continue
        if old["raw"] != doc["raw"]:
            fail("SOURCE_VERSION_CONFLICT", "declared version already binds different source bytes",
                 "/version", exit_code=75)
        if old["registration"] != doc["registration"]:
            fail("SOURCE_ASSOCIATION_INVALID", "reuse registration proof differs", "/registration")
        if old["observation"] != doc["observation"]:
            fail("SOURCE_PROVENANCE_VARIANT", "same version has different observation metadata",
                 "/observation", exit_code=75, prior_association=association_reference(old),
                 proposed_observation_sha256=digest(observed))
        if old != doc:
            fail("SOURCE_ASSOCIATION_INVALID", "reuse must preserve the complete prior association")
        return {"state": "reused", "association": copy.deepcopy(old)}
    association_inventory([*prior.values(), doc])
    return {"state": "proposed", "association": doc}


def validate_source_inventory(associations, *, raw_sources, extraction_artifacts,
                              head_bytes, receipt_bytes, registration_ledgers):
    """Verify a complete supplied source set; callers establish its real authority."""
    documents = association_inventory(associations)
    raw_sources = byte_map(raw_sources, "/raw_sources")
    extraction_artifacts = byte_map(extraction_artifacts, "/extraction_artifacts")
    registration_ledgers = byte_map(registration_ledgers, "/registration_ledgers", maximum=16 * 1024 * 1024)
    receipt_bytes = byte_map(receipt_bytes, "/receipt_bytes", maximum=1024 * 1024)
    if head_bytes is not None and type(head_bytes) is not bytes:
        fail("SOURCE_INVENTORY_INVALID", "registration head must be exact bytes or null", "/head_bytes")
    expected = ({x["raw"]["path"] for x in documents.values()},
                {x["extraction"]["path"] for x in documents.values()},
                {x["registration"]["source_ledger_path"] for x in documents.values()})
    for supplied, wanted, at in zip((raw_sources, extraction_artifacts, registration_ledgers),
                                    expected, ("/raw_sources", "/extraction_artifacts", "/registration_ledgers")):
        if set(supplied) != wanted:
            fail("SOURCE_INVENTORY_INVALID", "source material map contains missing or orphan entries", at)
    if not documents:
        if head_bytes is not None or receipt_bytes != {}:
            fail("SOURCE_INVENTORY_INVALID", "empty source inventory requires no registration authority")
        return {}
    proof_cache = {}
    for aid, doc in sorted(documents.items()):
        raw = raw_sources[doc["raw"]["path"]]
        validate_payload(raw, doc["observation"])
        extracted = extraction_artifacts[doc["extraction"]["path"]]
        if extracted != canonicalize(doc["observation"]):
            fail("SOURCE_INVENTORY_INVALID", "extraction bytes differ from exact source observation", "/extraction_artifacts")
        ledger = registration_ledgers[doc["registration"]["source_ledger_path"]]
        key = (doc["raw"]["path"], sha(ledger))
        if key not in proof_cache:
            proof_cache[key] = registration_proof(doc["raw"], doc["source_id"], head_bytes=head_bytes,
                                                receipt_bytes=receipt_bytes, ledger_bytes=ledger)
        if proof_cache[key] != doc["registration"]:
            fail("SOURCE_ASSOCIATION_INVALID", "association registration reference differs", "/registration")
    return documents


def make_display_decision(*, paper_id, sequence, previous_decision_id, association,
                          actor, choice, decided_at, reason):
    """Seal explicitly supplied choice material; cannot authenticate a human."""
    preflight({"paper_id": paper_id, "sequence": sequence, "previous_decision_id": previous_decision_id,
               "association": association, "actor": actor, "choice": choice, "decided_at": decided_at, "reason": reason})
    doc = {"schema": DECISION, "decision_id": "svd-" + "0" * 64, "paper_id": paper_id,
           "sequence": sequence, "previous_decision_id": previous_decision_id, "association": association,
           "actor": actor, "choice": choice, "decided_at": decided_at, "reason": reason}
    from video_paper_wiki.source_semantics_contracts import validate_shape
    validate_shape(doc, DECISION)
    calendar(decided_at, "/decided_at")
    doc["decision_id"] = decision_id(doc)
    return validate(doc, DECISION)


def derive_display_heads(associations, decisions):
    """Derive heads of the complete supplied chains, without selecting any default."""
    preflight({"associations": associations, "decisions": decisions})
    by_association = association_inventory(associations)
    if type(decisions) is not list:
        fail("SOURCE_DISPLAY_INVALID", "display decisions must be an array", "/decisions")
    if len(decisions) > 8192:
        fail(LIMIT, "display decision inventory exceeds its bound", "/decisions")
    docs = [validate(value, DECISION) for value in decisions]
    by_id, groups = {}, {}
    for index, doc in enumerate(docs):
        aid = doc["association"]["association_id"]
        association = by_association.get(aid)
        if (doc["decision_id"] in by_id or association is None
                or doc["association"] != association_reference(association)
                or association["paper_id"] != doc["paper_id"]):
            fail("SOURCE_DISPLAY_INVALID", "display decision ID, owner or association reference differs", f"/decisions/{index}")
        by_id[doc["decision_id"]] = doc
        groups.setdefault(doc["paper_id"], []).append(doc)
    heads = []
    for paper_id, chain in sorted(groups.items()):
        chain.sort(key=lambda x: (x["sequence"], x["decision_id"]))
        previous = None
        for sequence, doc in enumerate(chain, 1):
            if (doc["sequence"] != sequence or doc["previous_decision_id"] !=
                    (None if previous is None else previous["decision_id"])):
                fail("SOURCE_DISPLAY_INVALID", "display history is not one complete consecutive chain", "/decisions")
            if previous is not None and calendar(doc["decided_at"]) < calendar(previous["decided_at"]):
                fail("SOURCE_DISPLAY_INVALID", "display history time moves backwards", "/decisions")
            previous = doc
        last = chain[-1]
        heads.append({"paper_id": paper_id, "decision_id": last["decision_id"],
                      "decision_sha256": digest(last), "association": last["association"], "sequence": last["sequence"]})
    return validate({"schema": HEADS, "heads": heads}, HEADS)
