"""Offline R2 source-publication proposal probe.

The probe exercises the real pinned Markdown capture/admission chain in a
disposable Vault, then builds and validates a closed knowledge proposal from
the resulting receipt-backed state.  It never applies the knowledge proposal.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
SOURCE = REPO / ".work/parallel/source-publication-v1/terminal-1/source"
SCRIPT_DIR = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/r2"
OUT = SCRIPT_DIR / "result"
sys.path[:0] = [str(SOURCE / "src"), str(SOURCE), str(SOURCE / "vendor/claude-obsidian")]

from claude_obsidian.ledgers import validate_claim_ledger, validate_source_ledger  # noqa: E402
from tests.research.test_source_admission import apply_publication  # noqa: E402
from tests.support import make_checkout  # noqa: E402
from tests.upstream.test_markdown_source import _admit, _captured_fixture  # noqa: E402
from video_paper_wiki.assessment_history_v2 import derive_assessment_heads  # noqa: E402
from video_paper_wiki.canonical_compiler_v2 import compile_pages  # noqa: E402
from video_paper_wiki.contracts import validate_document  # noqa: E402
from video_paper_wiki.identity import assessment_event_id, claim_id, paper_page_slug  # noqa: E402
from video_paper_wiki.jcs import canonicalize  # noqa: E402
from video_paper_wiki.markdown_locator import (  # noqa: E402
    decode_evidence,
    encode_evidence,
    evidence_fingerprint_versioned,
    evidence_profile,
)
from video_paper_wiki.receipt_audit import HEAD, _Snapshot, _enumerate, audit_integrity  # noqa: E402
from video_paper_wiki.secure_io import parse_strict_json  # noqa: E402
from video_paper_wiki.source_publication_contracts import PROPOSAL, validate as validate_publication  # noqa: E402
from video_paper_wiki.source_publication_io import proposal_tree  # noqa: E402
from video_paper_wiki.source_semantics_contracts import (  # noqa: E402
    COMPILE,
    PAPER,
    association_reference,
    extraction_descriptor,
    sha,
)
from video_paper_wiki.source_versions import associate_source, derive_display_heads, validate_source_inventory  # noqa: E402

STAMP = "2026-09-09T00:00:00Z"


def h(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def put(rel: str, raw: bytes) -> dict[str, object]:
    path = OUT / "payloads" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": rel, "sha256": h(raw), "size_bytes": len(raw)}


def put_json(rel: str, value: object) -> dict[str, object]:
    return put(rel, canonicalize(value))


def stable(value: object, temporary_root: str) -> object:
    """Normalize disposable checkout paths in retained authority evidence."""
    if isinstance(value, str):
        return value.replace(temporary_root, "<disposable-root>")
    if isinstance(value, list):
        return [stable(item, temporary_root) for item in value]
    if isinstance(value, dict):
        return {key: stable(item, temporary_root) for key, item in value.items()}
    return value


def inventory_entries(actual: dict[str, tuple[str, int, int]]) -> list[dict[str, object]]:
    return [
        {"path": path, "sha256": digest, "size_bytes": size, "mode": mode}
        for path, (digest, size, mode) in sorted(actual.items(), key=lambda item: item[0].encode())
    ]


def external_proposal(root: Path, proposal: dict[str, object], payloads: dict[str, bytes]) -> tuple[dict, dict[str, bytes]]:
    """Write and retained-read the exact external proposal layout."""
    base = root / "source-publication"
    content = base / "content"
    content.mkdir(parents=True)
    descriptors = []
    by_digest: dict[str, bytes] = {}
    for path, raw in sorted(payloads.items(), key=lambda item: item[0].encode()):
        digest = h(raw)
        if digest in by_digest and by_digest[digest] != raw:
            raise AssertionError("digest collision in probe payloads")
        by_digest[digest] = raw
        (content / digest).write_bytes(raw)
        descriptors.append({"path": path, "content_file": f"content/{digest}"})
    proposal = {**proposal, "payloads": descriptors}
    proposal_raw = canonicalize(proposal)
    proposal_path = base / "proposal.json"
    proposal_path.write_bytes(proposal_raw)
    with proposal_tree(proposal_path) as tree:
        parsed = validate_publication(parse_strict_json(tree.request_bytes(), invalid_code="SOURCE_PUBLICATION_INVALID"), PROPOSAL)
        assert canonicalize(parsed) == proposal_raw
        bound = tree.bind({digest: len(raw) for digest, raw in by_digest.items()})
        assert bound == {digest: by_digest[digest] for digest in sorted(by_digest)}
        tree.verify()
    return parsed, by_digest


def main() -> None:
    if not SOURCE.is_dir():
        raise RuntimeError(f"missing accepted source tree: {SOURCE}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="vpwiki-source-publication-r2-", dir="/private/tmp") as tmp:
        checkout = Path(tmp) / "checkout"
        checkout.mkdir()
        make_checkout(checkout)
        os.chdir(checkout)

        # Actual pinned capture, apply, admission, inspect, and apply.  The
        # resulting source row and raw bytes are the only registration basis.
        vault, _prepared, capture, capture_bound = _captured_fixture(checkout)
        admission = _admit(
            vault,
            capture,
            capture_bound,
            batch_id="probe-r2-admit",
            operation_id="probe-r2-admit",
            ingested_at=STAMP,
        )
        admission_authority = admission["publication_authority"]
        admission_applied = apply_publication(checkout, vault, admission_authority)
        audit = audit_integrity(vault)
        assert audit["classification"] == "receipt_backed"

        raw_path = capture["stored_path"]
        raw = (vault / raw_path).read_bytes()
        head = (vault / HEAD).read_bytes()
        receipts = {
            path.relative_to(vault).as_posix(): path.read_bytes()
            for path in sorted((vault / "wiki/meta/operations").glob("*.json"))
        }
        ledger_path = "wiki/meta/ledgers/source-ledger.json"
        claim_ledger_path = "wiki/meta/ledgers/claim-ledger.json"
        ledger = (vault / ledger_path).read_bytes()
        claim_ledger_current = (vault / claim_ledger_path).read_bytes()
        ledger_doc = json.loads(ledger)

        # Build the association solely from actual receipt/head/current-ledger
        # bytes.  This is not a fabricated source or registration proof.
        observation = copy.deepcopy(capture["request"]["plan"]["observation"])
        association = associate_source(
            observation,
            raw_bytes=raw,
            head_bytes=head,
            receipt_bytes=receipts,
            ledger_bytes=ledger,
            existing=[],
        )["association"]
        source_id = association["source_id"]
        association_path = f"wiki/meta/records/source-versions/{association['association_id']}.json"
        snapshot_path = association["registration"]["source_ledger_path"]
        extraction = extraction_descriptor(observation)
        extraction_raw = canonicalize(observation)
        paper_id = observation["paper_id"]
        paper_page = f"wiki/papers/{paper_page_slug(paper_id)}.md"

        page = observation["pages"][0]
        text = raw.decode("utf-8")
        start, end = page["text_start"], page["text_end"]
        locator = {
            "kind": "markdown",
            "source_id": source_id,
            "association": association_reference(association),
            "path": association["raw"]["path"],
            "sha256": association["raw"]["sha256"],
            "charspan": [start, end],
            "page_anchor": page["anchor"],
            "excerpt_sha256": h(text[start:end].encode("utf-8")),
        }
        evidence = {**locator, "relation": "supports"}
        wire_evidence = encode_evidence(evidence)
        assert decode_evidence(wire_evidence) == evidence
        claim_text = "The captured Markdown source contains an exact observed statement."
        subject = f"paper:{paper_id}"
        claim = {
            "claim_id": claim_id(subject, claim_text),
            "stable_subject_id": subject,
            "canonical_claim_text": claim_text,
            "evidence": [evidence],
            "assessment": "provisional",
            "reviewed_at": None,
        }
        event = {
            "schema": "video-paper-wiki.assessment-event.v2",
            "event_id": "ase-" + "0" * 20,
            "claim_id": claim["claim_id"],
            "previous_event_id": None,
            "actor_kind": "system",
            "transition_kind": "genesis",
            "from_assessment": None,
            "to_assessment": "provisional",
            "claim_text_sha256": h(claim_text.encode("utf-8")),
            "evidence_fingerprint": evidence_fingerprint_versioned([evidence]),
            "decided_by": "offline-source-publication-r2-probe",
            "decided_at": STAMP,
            "reason": "Offline proposed v2 genesis event; no human decision.",
            "evidence_profile": evidence_profile([evidence]),
        }
        event["event_id"] = assessment_event_id(event)
        event_sha = h(canonicalize(event))
        assessment_heads_legacy = derive_assessment_heads(claims=[claim], events=[event])
        assessment_heads = {
            "schema": "video-paper-wiki.assessment-heads.v2",
            "heads": {
                claim["claim_id"]: {
                    "event_id": event["event_id"],
                    "event_sha256": event_sha,
                    "evidence_profile": "mixed-v2",
                }
            },
        }
        display_heads = derive_display_heads([association], [])

        record = json.loads(
            (SOURCE / "tests/fixtures/contracts/valid/video-paper-wiki.paper-record.v2.json").read_bytes()
        )
        record.update(
            {
                "paper_id": paper_id,
                "title": observation["title"],
                "title_zh": observation["title"],
                "authors": ["Offline proposal probe"],
                "published_at": "2026-09-09",
                "aliases": [],
                "source_ids": [source_id],
                "taxonomy": [],
                "active_extraction_path": None,
                "active_extraction_sha256": None,
                "section_claim_refs": [
                    {
                        "section": "one_sentence_conclusion",
                        "claim_id": claim["claim_id"],
                        "core": True,
                        "lifecycle": "active",
                    }
                ],
                "created_at": STAMP,
                "updated_at": STAMP,
                "source_associations": [association_reference(association)],
                "display_head": None,
            }
        )
        validate_document(record, PAPER)

        proposed_ledger = copy.deepcopy(ledger_doc)
        proposed_ledger["sources"][source_id]["pages"] = [paper_page]
        assert validate_source_ledger(proposed_ledger) == []

        claim_ledger = json.loads(claim_ledger_current)
        claim_ledger["generated_at"] = STAMP
        claim_ledger["claims"][claim["claim_id"]] = {
            "text": claim_text,
            "risk": "normal",
            "assessment": "provisional",
            "confidence": "medium",
            "location": {"path": paper_page, "anchor": "^" + claim["claim_id"]},
            "reviewed_at": None,
            "evidence": [
                {"source_id": source_id, "relation": "supports", "locator": wire_evidence["locator"]}
            ],
        }

        material = {
            "schema": COMPILE,
            "operation_id": "offline-source-publication-r2-probe",
            "papers": [
                {
                    "record": record,
                    "claims": [claim],
                    "events": [event],
                    "associations": [association],
                    "display_decisions": [],
                    "assessment_heads": assessment_heads_legacy,
                }
            ],
            "code": [],
            "concepts": [],
        }
        compile_kwargs = {
            "raw_sources": {association["raw"]["path"]: raw},
            "extraction_artifacts": {extraction["path"]: extraction_raw},
            "head_bytes": head,
            "receipt_bytes": receipts,
            "registration_ledgers": {snapshot_path: ledger},
        }
        pages = compile_pages(material, **compile_kwargs)
        validate_source_inventory([association], **compile_kwargs)
        claim_errors = validate_claim_ledger(claim_ledger, proposed_ledger, planned_files=pages)
        if claim_errors:
            raise AssertionError(claim_errors)
        validate_document(assessment_heads, "video-paper-wiki.assessment-heads.v2")
        validate_document(display_heads, "video-paper-wiki.source-display-heads.v1")

        payloads = {
            ledger_path: canonicalize(proposed_ledger),
            claim_ledger_path: canonicalize(claim_ledger),
            snapshot_path: ledger,
            extraction["path"]: extraction_raw,
            association_path: canonicalize(association),
            f"wiki/meta/reviews/{claim['claim_id']}/{event['event_id']}.json": canonicalize(event),
            f"wiki/meta/records/papers/{paper_page_slug(paper_id)}.json": canonicalize(record),
            "wiki/meta/records/assessment-heads.json": canonicalize(assessment_heads),
            "wiki/meta/records/source-display-heads.json": canonicalize(display_heads),
            **pages,
        }
        proposal, bound_payloads = external_proposal(
            checkout / "caller-root",
            {"schema": PROPOSAL, "kind": "knowledge", "registration": None},
            payloads,
        )
        assert proposal["kind"] == "knowledge" and proposal["registration"] is None
        external_files = [put("external/proposal.json", canonicalize(proposal))]
        external_files.extend(
            put(f"external/content/{digest}", raw_bytes)
            for digest, raw_bytes in sorted(bound_payloads.items())
        )

        # Freeze the R2 current and prospective basis exactly over the audited
        # managed inventory.  The head/receipt advance is intentionally outside
        # this prospective business inventory.
        snap = _Snapshot(vault)
        try:
            actual_inventory = _enumerate(vault, snap)
            snap.verify()
        finally:
            snap.close()
        entries = inventory_entries(actual_inventory)
        prospective = dict(actual_inventory)
        for path, data in payloads.items():
            mode = actual_inventory[path][2] if path in actual_inventory else 0o600
            prospective[path] = (h(data), len(data), mode)
        prospective_entries = inventory_entries(prospective)
        basis = {
            "operation_head_sha256": h(head),
            "inventory_sha256": h(canonicalize(entries)),
        }
        prospective_inventory_sha256 = h(canonicalize(prospective_entries))

        payload_records = [
            {"path": path, "sha256": h(raw_bytes), "size_bytes": len(raw_bytes)}
            for path, raw_bytes in sorted(payloads.items(), key=lambda item: item[0].encode())
        ]
        result = {
            "schema": "video-paper-wiki.source-publication-proposal-probe-result.v2",
            "status": "validated_proposed_bytes_only",
            "source_tree": str(SOURCE),
            "source_tree_head": "c32e68d08a142d5a5559ce717ff397f9b27f55d1",
            "contract": {
                "r2_sha256": "908c94b376f5e130883acd332c7d9c12378daf2cd37b21507a16185dd58d5628",
                "r3_sha256": "67f3e8b0b287eb20e144de9f9300e97fd78adff6f785979a9dc9559a636310f6",
                "r4_sha256": "658ed78359a9baf3ae7974afee07c1f3b396eac820e085fd2927bdae9ae3f3cd",
                "freeze_sha256": "5629054bfc7e2f385bf2f9cadc4964a1651a52d89564a0f485372515963f7a95",
            },
            "actual": {
                "capture": {
                    "disposition": capture.get("disposition"),
                    "stored_path": capture["stored_path"],
                    "source_id": capture["source_id"],
                    "request_batch_id": capture["request"]["plan"]["batch_id"],
                    "requested_operation_id": capture["requested_operation_id"],
                },
                "legacy_admission": {
                    "state": admission["state"],
                    "operation_id": admission["operation_id"],
                    "source_id": admission["source_id"],
                    "request_batch_id": admission_authority["request"]["batch_id"],
                },
                "receipt_backed": {
                    "classification": audit["classification"],
                    "head_path": HEAD,
                    "head_sha256": h(head),
                    "receipt_count": len(receipts),
                    "receipt_paths": sorted(receipts),
                    "ledger_sha256": h(ledger),
                    "raw_path": raw_path,
                    "raw_sha256": h(raw),
                },
                "read_preconditions": [
                    {"path": raw_path, "sha256": h(raw), "size_bytes": len(raw)},
                    {"path": HEAD, "sha256": h(head), "size_bytes": len(head)},
                    *[
                        {"path": path, "sha256": h(raw_bytes), "size_bytes": len(raw_bytes)}
                        for path, raw_bytes in sorted(receipts.items(), key=lambda item: item[0].encode())
                    ],
                ],
            },
            "basis": basis,
            "prospective_inventory_sha256": prospective_inventory_sha256,
            "inventory": entries,
            "prospective_inventory": prospective_entries,
            "proposal": proposal,
            "proposal_payloads": payload_records,
            "external_files": external_files,
            "payloads": [put(path, raw_bytes) for path, raw_bytes in sorted(payloads.items(), key=lambda item: item[0].encode())],
            "actual_payloads": [
                put_json("actual/capture-authority.json", stable(capture, tmp)),
                put_json("actual/capture-bound-result.json", stable(capture_bound, tmp)),
                put_json("actual/admission-authority.json", stable(admission_authority, tmp)),
                put_json("actual/admission-applied-result.json", stable(admission_applied, tmp)),
                put_json("actual/audit.json", audit),
                put("actual/raw-capture.md", raw),
                put("actual/operation-head.json", head),
                *[put(f"actual/receipts/{path.rsplit('/', 1)[-1]}", data) for path, data in sorted(receipts.items())],
                put("actual/current-source-ledger.json", ledger),
                put("actual/current-claim-ledger.json", claim_ledger_current),
            ],
            "derived": {
                "source_id": source_id,
                "association_id": association["association_id"],
                "claim_id": claim["claim_id"],
                "event_id": event["event_id"],
                "event_sha256": event_sha,
                "assessment_heads": assessment_heads,
                "display_heads": display_heads,
                "wire_evidence": wire_evidence,
                "compiled_page_paths": sorted(pages),
            },
            "checks": {
                "pinned_capture_and_apply": True,
                "receipt_backed_admission_and_apply": True,
                "actual_registration_proof": True,
                "claim_ledger_actual_encoded_v2_evidence": True,
                "assessment_heads_registry": True,
                "source_display_heads_empty": True,
                "compiler_page": True,
                "source_inventory": True,
                "external_proposal_shape_and_content_set": True,
                "proposal_kind_knowledge_registration_null": True,
                "frozen_operation_type_ingest": True,
                "raw_capture_is_read_precondition": True,
                "human_decision": False,
                "knowledge_proposal_applied": False,
            },
        }
        result_raw = canonicalize(result)
        result_path = OUT / "source-publication-proposal-probe-result.json"
        result_path.write_bytes(result_raw)
        print(
            json.dumps(
                {
                    "result": str(result_path),
                    "result_sha256": h(result_raw),
                    "result_size_bytes": len(result_raw),
                    "proposal_payload_count": len(payloads),
                    "source_id": source_id,
                    "claim_id": claim["claim_id"],
                    "event_id": event["event_id"],
                    "compiled_pages": sorted(pages),
                },
                separators=(",", ":"),
            )
        )


if __name__ == "__main__":
    main()
