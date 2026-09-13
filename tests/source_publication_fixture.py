"""Actual pinned transactions over synthetic text; never real operator approval."""
from __future__ import annotations

import copy
import json

from tests.source_semantics_fixture import STAMP, claim_for, event_for, fixture, locator_for
from tests.upstream.test_markdown_source import _admit, _captured_fixture
from tests.research.test_source_admission import apply_publication
from video_paper_wiki.assessment_history_v2 import derive_assessment_heads
from video_paper_wiki.canonical_compiler_v2 import compile_pages, concept_items_for_papers
from video_paper_wiki.identity import paper_page_slug
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import encode_evidence
from video_paper_wiki.receipt_audit import HEAD, audit_integrity
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER, DISPLAY_HEADS, HEADS, SOURCE_LEDGER
from video_paper_wiki.source_semantics_contracts import COMPILE, PAPER, association_reference, sha
from video_paper_wiki.source_versions import associate_source, derive_display_heads


def registered_source(checkout, *, legacy=False):
    vault, prepared, capture, bound = _captured_fixture(checkout)
    admitted = _admit(vault, capture, bound, publication_profile="legacy-v1" if legacy else "source-v1")
    apply_publication(checkout, vault, admitted["publication_authority"])
    return vault, capture, bound, admitted


def knowledge_proposal(vault, capture):
    audit = audit_integrity(vault)
    observed = capture["request"]["plan"]["observation"]
    raw = (vault / capture["stored_path"]).read_bytes()
    ledger_bytes = (vault / SOURCE_LEDGER).read_bytes()
    head_bytes = (vault / HEAD).read_bytes()
    receipts = {p: (vault / p).read_bytes() for p in audit["receipts"]}
    association = associate_source(observed, raw_bytes=raw, head_bytes=head_bytes,
        receipt_bytes=receipts, ledger_bytes=ledger_bytes, existing=[])["association"]
    pid, sid = association["paper_id"], association["source_id"]
    claim = claim_for([{**locator_for(association, raw), "relation": "supports"}],
                      subject="paper:" + pid, text="This synthetic source describes temporal attention.")
    event = event_for(claim)
    record = fixture("video-paper-wiki.paper-record.v2")
    record.pop("arxiv_id", None)
    record.pop("doi", None)
    record.update(paper_id=pid, title=observed["title"], title_zh="合成发布测试",
        published_at="2026-09-09", aliases=[], source_ids=[sid], taxonomy=[],
        source_associations=[association_reference(association)], display_head=None,
        active_extraction_path=None, active_extraction_sha256=None,
        section_claim_refs=[{"claim_id": claim["claim_id"], "section": "one_sentence_conclusion", "core": True, "lifecycle": "active"}],
        created_at=STAMP, updated_at=STAMP)
    material = {"schema": COMPILE, "operation_id": "fixture-compile", "code": [], "concepts": [],
        "papers": [{"record": record, "claims": [claim], "events": [event],
                    "associations": [association], "display_decisions": []}]}
    arguments = {"raw_sources": {association["raw"]["path"]: raw},
        "extraction_artifacts": {association["extraction"]["path"]: canonicalize(observed)},
        "registration_ledgers": {association["registration"]["source_ledger_path"]: ledger_bytes},
        "head_bytes": head_bytes, "receipt_bytes": receipts}
    payloads = render_proposal(material, arguments)
    source = json.loads(ledger_bytes)
    source["sources"][sid]["pages"] = ["wiki/papers/" + paper_page_slug(pid) + ".md"]
    payloads[SOURCE_LEDGER] = canonicalize(source)
    payloads[association["registration"]["source_ledger_path"]] = ledger_bytes
    return payloads, material, arguments


def render_proposal(material, arguments):
    """Explicit proposal bytes; expected pages are independently tested elsewhere."""
    material = copy.deepcopy(material)
    material["concepts"] = concept_items_for_papers([x["record"] for x in material["papers"]])
    payloads = compile_pages(material, **arguments)
    claims, events, associations, decisions = [], [], [], []
    ledger_rows = {}
    for group in material["papers"]:
        record = group["record"]
        page = "wiki/papers/" + paper_page_slug(record["paper_id"]) + ".md"
        payloads["wiki/meta/records/papers/" + paper_page_slug(record["paper_id"]) + ".json"] = canonicalize(record)
        claims.extend(group["claims"])
        events.extend(group["events"])
        associations.extend(group.get("associations", []))
        decisions.extend(group.get("display_decisions", []))
        for claim in group["claims"]:
            ledger_rows[claim["claim_id"]] = {"text": claim["canonical_claim_text"], "risk": "normal",
                "assessment": claim["assessment"], "confidence": "unknown", "reviewed_at": claim["reviewed_at"],
                "location": {"path": page, "anchor": "^" + claim["claim_id"]},
                "evidence": [encode_evidence(x) for x in claim["evidence"]], "notes": None, "supersedes": None}
    payloads[CLAIM_LEDGER] = canonicalize({"schema": "claude-obsidian.claim-ledger.v1", "generated_at": STAMP, "claims": ledger_rows})
    for event in events:
        payloads[f"wiki/meta/reviews/{event['claim_id']}/{event['event_id']}.json"] = canonicalize(event)
    by_id = {event["event_id"]: event for event in events}
    payloads[ASSESSMENT_HEADS] = canonicalize({"schema": HEADS, "heads": {cid: {
        "event_id": eid, "event_sha256": sha(canonicalize(by_id[eid])),
        "evidence_profile": by_id[eid].get("evidence_profile", "legacy-v1")}
        for cid, eid in derive_assessment_heads(claims=claims, events=events).items()}})
    payloads[DISPLAY_HEADS] = canonicalize(derive_display_heads(associations, decisions))
    for association in associations:
        payloads[f"wiki/meta/records/source-versions/{association['association_id']}.json"] = canonicalize(association)
        payloads[association["extraction"]["path"]] = canonicalize(association["observation"])
    for decision in decisions:
        payloads[f"wiki/meta/reviews/source-display/{decision['decision_id']}.json"] = canonicalize(decision)
    return payloads
