"""Pure conversion of validated light knowledge into explicit publication bytes."""
from __future__ import annotations

import copy
import re

from video_paper_wiki.contracts import validate_document
from video_paper_wiki.identity import (
    IdentityError, assessment_event_id, claim_id, normalize_arxiv_id,
    normalize_doi, paper_page_slug,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import (
    decode_evidence, encode_evidence, evidence_fingerprint_versioned,
    evidence_profile, resolve_markdown_locator,
)
from video_paper_wiki.receipt_audit import HEAD
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER, SOURCE_LEDGER
from video_paper_wiki.source_semantics_contracts import (
    EVENT, PAPER, association_reference, calendar, fail, sha, validate,
)
from video_paper_wiki.source_versions import associate_source

METADATA = "video-paper-wiki.source-conversion-metadata.v1"
SECTION_MAPPING = {
    "summary": "one_sentence_conclusion", "method": "method",
    "architecture": "representation_architecture", "training_data": "training_data",
    "experiments": "experiments_results", "limitations": "limitations",
    "code_resources": "code_resources", "open_questions": "research_question",
}


def invalid(message, pointer=""):
    fail("SOURCE_CONVERSION_INVALID", message, pointer)


def unsupported(message, pointer=""):
    fail("SOURCE_CONVERSION_UNSUPPORTED_CHANGE", message, pointer, exit_code=75)


def proposal_time(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        invalid("proposed_at requires whole-second UTC precision", "/proposed_at")
    calendar(value, "/proposed_at")
    return value


def _chronology(proposed_at, previous, pointer):
    if calendar(proposed_at) < calendar(previous):
        invalid("proposal timestamp precedes the changed object's timestamp", pointer)


def validate_metadata(value, paper_id):
    metadata = copy.deepcopy(validate_document(value, METADATA))
    if metadata["paper_id"] != paper_id:
        invalid("metadata identity differs from the registered canonical paper", "/metadata/paper_id")
    calendar(metadata["published_at"], "/metadata/published_at", timestamp=len(metadata["published_at"]) != 10)
    for key, normalize in (("doi", normalize_doi), ("arxiv_id", normalize_arxiv_id)):
        if key in metadata:
            try:
                normalized = normalize(metadata[key])
            except IdentityError:
                invalid("metadata identifier cannot be normalized", "/metadata/" + key)
            if normalized not in {paper_id, *metadata["aliases"]}:
                invalid("metadata identifier lacks a canonical identity or alias", "/metadata/" + key)
    return metadata


def source_association(current, observation, raw):
    """Find the earliest actual registration ledger, never a later substitute."""
    raw_path = ".raw/captured/" + observation["markdown"]["sha256"] + ".md"
    ledger_sha = None
    for receipt_path, receipt in current["chain"]:
        if any(item["path"] == raw_path for field in ("claimed_inputs", "writes") for item in receipt[field]):
            matches = [item for item in receipt["writes"] if item["path"] == SOURCE_LEDGER]
            if len(matches) != 1:
                fail("SOURCE_REGISTRATION_INVALID", "first raw receipt has no unique source ledger", receipt_path)
            ledger_sha = matches[0]["after_sha256"]
            break
    if ledger_sha is None:
        fail("SOURCE_REGISTRATION_INVALID", "captured source has no actual registration receipt", "/capture_authority")
    ledger_path = ".raw/derived/source-ledgers/" + ledger_sha + ".json"
    ledger = current["bytes"].get(ledger_path)
    if ledger is None and sha(current["bytes"][SOURCE_LEDGER]) == ledger_sha:
        ledger = current["bytes"][SOURCE_LEDGER]
    if ledger is None:
        fail("SOURCE_REGISTRATION_INVALID", "earliest registration ledger snapshot is unavailable", ledger_path)
    result = associate_source(observation, raw_bytes=raw, head_bytes=current["bytes"][HEAD],
        receipt_bytes={p: current["bytes"][p] for p, _ in current["chain"]}, ledger_bytes=ledger,
        existing=list(current["documents"]["association"].values()))
    return result, ledger


def _evidence(section, chunks, association, raw, pointer):
    result = []
    for index, citation in enumerate(section["citations"]):
        chunk = chunks.get(citation)
        at = pointer + "/citations/" + str(index)
        if chunk is None or chunk["paper_id"] != association["observation"]["light_paper_id"]:
            invalid("citation is not a current chunk of the selected lightweight paper", at)
        locator = {"kind": "markdown", "source_id": association["source_id"],
            "association": association_reference(association), "path": association["raw"]["path"],
            "sha256": association["raw"]["sha256"], "charspan": [chunk["text_start"], chunk["text_end"]],
            "page_anchor": "page-" + str(chunk["page"]), "excerpt_sha256": chunk["text_sha256"]}
        resolve_markdown_locator(locator, association, raw)
        result.append({**locator, "relation": "supports"})
    if not result:
        invalid("provisional section requires current source citations", pointer + "/citations")
    return result


def _event(cid, text, evidence, previous, record_id, association_id, proposed_at):
    if previous is not None:
        _chronology(proposed_at, previous["decided_at"], "/proposed_at")
    reason = ("Created from lightweight record " if previous is None else "Evidence changed by lightweight record ")
    reason += record_id + "; source association " + association_id + "."
    event = {"schema": EVENT, "event_id": "ase-" + "0" * 20, "claim_id": cid,
        "previous_event_id": None if previous is None else previous["event_id"],
        "actor_kind": "system", "transition_kind": "genesis" if previous is None else "evidence_invalidation",
        "from_assessment": None if previous is None else previous["to_assessment"],
        "to_assessment": "provisional", "claim_text_sha256": sha(text.encode("utf-8")),
        "evidence_profile": evidence_profile(evidence), "evidence_fingerprint": evidence_fingerprint_versioned(evidence),
        "decided_by": "source-conversion-v1", "decided_at": proposed_at, "reason": reason}
    event["event_id"] = assessment_event_id(event)
    return validate(event, EVENT)


def assemble_conversion(*, current, observation, raw, document, chunks, record_id,
                        metadata, proposed_at):
    """Return explicit rows/history/record payloads; the shared compiler adds pages."""
    association_result, historical_ledger = source_association(current, observation, raw)
    association = association_result["association"]
    aid, pid = association["association_id"], association["paper_id"]
    page = "wiki/papers/" + paper_page_slug(pid) + ".md"
    record_path = "wiki/meta/records/papers/" + paper_page_slug(pid) + ".json"
    existing = None
    for path, paper in current["documents"]["paper"].items():
        if paper["paper_id"] == pid:
            record_path, existing = path, paper
            break
    if metadata is None and existing is None:
        invalid("a new canonical paper requires explicit bibliographic metadata", "/metadata")
    if metadata is not None:
        metadata = validate_metadata(metadata, pid)
        if existing is not None and metadata["aliases"] != existing["aliases"]:
            invalid("existing aliases must retain their exact spelling and order", "/metadata/aliases")
    record = copy.deepcopy(existing) if existing is not None else {
        "paper_id": pid, "source_ids": [], "section_claim_refs": [],
        "created_at": proposed_at, "updated_at": proposed_at,
    }
    if metadata is not None:
        record.update({k: copy.deepcopy(v) for k, v in metadata.items() if k != "schema"})
    upgrading = existing is not None and existing["schema"] != PAPER
    if existing is None or upgrading:
        record.update(schema=PAPER, display_head=None, active_extraction_path=None, active_extraction_sha256=None)
    associations = {a["association_id"]: a for a in current["documents"]["association"].values() if a["paper_id"] == pid}
    associations[aid] = association
    record["source_associations"] = [association_reference(associations[key]) for key in sorted(associations)]
    ledger = copy.deepcopy(current["claim_ledger"])
    rows = ledger["claims"]
    # A complete mixed publication gives historical nonaccepted rows the explicit
    # null required by the typed transport. No assessment or evidence is changed.
    for row in rows.values():
        row.setdefault("reviewed_at", None)
    refs = {ref["claim_id"]: ref for ref in record["section_claim_refs"]}
    events = {event["event_id"]: event for event in current["documents"]["event"].values()}
    summary = {"light_paper_id": observation["light_paper_id"], "record_id": record_id,
        "canonical_paper_id": pid, "association_id": aid, "association_state": association_result["state"],
        "created_claim_ids": [], "invalidated_claim_ids": [], "unchanged_claim_ids": [],
        "location_migrated_claim_ids": [], "unmapped_concepts": copy.deepcopy(document["concepts"])}
    payloads = {"wiki/meta/records/source-versions/" + aid + ".json": canonicalize(association),
        association["extraction"]["path"]: canonicalize(observation),
        association["registration"]["source_ledger_path"]: historical_ledger}
    selected = {}
    for key, section in document["sections"].items():
        if section["status"] != "provisional":
            continue
        if key not in SECTION_MAPPING:
            invalid("provisional section has no canonical mapping", "/sections/" + key)
        text = section["text"]
        cid = claim_id("paper:" + pid, text)
        ref = {"section": SECTION_MAPPING[key], "claim_id": cid, "core": key == "summary", "lifecycle": "active"}
        if cid in selected:
            invalid("one claim cannot be assigned incompatible section ownership", "/sections/" + key)
        selected[cid] = key
        evidence = _evidence(section, chunks, association, raw, "/sections/" + key)
        previous = None
        if cid in rows:
            row = rows[cid]
            if row["text"] != text:
                fail("CLAIM_ID_COLLISION", "claim identity normalization would replace exact historical text", "/sections/" + key, exit_code=75)
            owner = current["owners"][cid]
            if owner["subject"] != "paper:" + pid or refs.get(cid) != ref:
                invalid("existing claim owner, section/core reference or lifecycle differs", "/sections/" + key)
            old_evidence = [decode_evidence(x) for x in row["evidence"]]
            if ((evidence_profile(old_evidence), evidence_fingerprint_versioned(old_evidence))
                    == (evidence_profile(evidence), evidence_fingerprint_versioned(evidence))):
                summary["unchanged_claim_ids"].append(cid)
                continue
            previous = events[current["assessment_heads"]["heads"][cid]["event_id"]]
            summary["invalidated_claim_ids"].append(cid)
            row.update(assessment="provisional", reviewed_at=None, evidence=[encode_evidence(x) for x in evidence])
        else:
            summary["created_claim_ids"].append(cid)
            rows[cid] = {"text": text, "risk": "normal", "assessment": "provisional", "confidence": "unknown",
                "reviewed_at": None, "location": {"path": page, "anchor": "^" + cid},
                "evidence": [encode_evidence(x) for x in evidence], "notes": None, "supersedes": None}
            record["section_claim_refs"].append(ref)
            refs[cid] = ref
        event = _event(cid, text, evidence, previous, record_id, aid, proposed_at)
        payloads[f"wiki/meta/reviews/{cid}/{event['event_id']}.json"] = canonicalize(event)
    for cid in refs:
        if not rows[cid]["evidence"]:
            unsupported("preserved v2 paper claims must have source evidence", "/claims/" + cid + "/evidence")
        location = {"path": page, "anchor": "^" + cid}
        if upgrading and rows[cid]["location"] != location:
            rows[cid]["location"] = location
            summary["location_migrated_claim_ids"].append(cid)
    source_ids = {a["source_id"] for a in associations.values()}
    source_ids.update(item["source_id"] for cid in refs for item in rows[cid]["evidence"])
    if not set(record["source_ids"]) <= source_ids:
        unsupported("preserved paper source IDs cannot be represented by its associations and evidence", "/paper/source_ids")
    record["source_ids"] = sorted(source_ids)
    if existing is not None and record != existing:
        _chronology(proposed_at, existing["updated_at"], "/proposed_at")
        record["updated_at"] = proposed_at
    validate(record, PAPER)
    if existing is None or record != existing:
        payloads[record_path] = canonicalize(record)
    if rows != current["claim_ledger"]["claims"]:
        _chronology(proposed_at, ledger["generated_at"], "/proposed_at")
        ledger["generated_at"] = proposed_at
        payloads[CLAIM_LEDGER] = canonicalize(ledger)
    sources = copy.deepcopy(current["source_ledger"])
    for sid in source_ids:
        if sid not in sources["sources"]:
            invalid("paper evidence source is not registered", "/paper/source_ids")
        pages = sources["sources"][sid]["pages"]
        if page not in pages:
            sources["sources"][sid]["pages"] = sorted({*pages, page})
    if sources["sources"] != current["source_ledger"]["sources"]:
        _chronology(proposed_at, sources["generated_at"], "/proposed_at")
        sources["generated_at"] = proposed_at
        payloads[SOURCE_LEDGER] = canonicalize(sources)
    for key in ("created_claim_ids", "invalidated_claim_ids", "unchanged_claim_ids", "location_migrated_claim_ids"):
        summary[key] = sorted(set(summary[key]))
    return {p: raw for p, raw in payloads.items() if current["bytes"].get(p) != raw}, summary
