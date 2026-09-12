"""Offline bridge probe; writes only under this probe's result directory."""
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
SOURCE = REPO / ".work/parallel/source-semantics-v1/integration-r1/source"
SCRIPT_DIR = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes"
OUT = SCRIPT_DIR / "result"
sys.path[:0] = [str(SOURCE / "src"), str(SOURCE), str(SOURCE / "vendor/claude-obsidian")]

from tests.research.test_source_admission import apply_publication  # noqa: E402
from tests.support import make_checkout  # noqa: E402
from tests.upstream.test_markdown_source import _admit, _captured_fixture  # noqa: E402
from video_paper_wiki.assessment_history_v2 import derive_assessment_heads  # noqa: E402
from video_paper_wiki.canonical_compiler_v2 import compile_pages  # noqa: E402
from video_paper_wiki.contracts import validate_document  # noqa: E402
from video_paper_wiki.identity import assessment_event_id, claim_id, paper_page_slug  # noqa: E402
from video_paper_wiki.jcs import canonicalize  # noqa: E402
from video_paper_wiki.markdown_locator import (  # noqa: E402
    encode_evidence, evidence_fingerprint_versioned, evidence_profile,
)
from video_paper_wiki.receipt_audit import audit_integrity  # noqa: E402
from video_paper_wiki.source_semantics_contracts import (  # noqa: E402
    COMPILE, PAPER, association_reference, extraction_descriptor, sha,
)
from video_paper_wiki.source_versions import (  # noqa: E402
    associate_source, derive_display_heads, validate_source_inventory,
)
from claude_obsidian.ledgers import validate_source_ledger  # noqa: E402

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
    """Normalize disposable absolute paths before hashing run authorities."""
    if isinstance(value, str):
        return value.replace(temporary_root, "<disposable-root>")
    if isinstance(value, list):
        return [stable(item, temporary_root) for item in value]
    if isinstance(value, dict):
        return {key: stable(item, temporary_root) for key, item in value.items()}
    return value


def main() -> None:
    if not SOURCE.is_dir():
        raise RuntimeError(f"missing accepted source tree: {SOURCE}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="vpwiki-bridge-", dir="/private/tmp") as tmp:
        checkout = Path(tmp) / "c"
        checkout.mkdir()
        make_checkout(checkout)
        os.chdir(checkout)

        # Actual pinned capture + legacy admission.  These helpers bootstrap a
        # real genesis, run the pinned adapter, apply capture, bind its result,
        # run admission, and apply the legacy source-registration transaction.
        vault, _prepared, capture, capture_bound = _captured_fixture(checkout)
        admission = _admit(vault, capture, capture_bound, batch_id="probe-admit",
                           operation_id="probe-admit", ingested_at=STAMP)
        admission_authority = admission["publication_authority"]
        applied = apply_publication(checkout, vault, admission_authority)
        audit = audit_integrity(vault)
        assert audit["classification"] == "receipt_backed"

        observation = copy.deepcopy(capture["request"]["plan"]["observation"])
        raw_path = capture["stored_path"]
        raw = (vault / raw_path).read_bytes()
        head_path = "wiki/meta/registries/operation-head.json"
        head = (vault / head_path).read_bytes()
        receipts = {
            p.relative_to(vault).as_posix(): p.read_bytes()
            for p in sorted((vault / "wiki/meta/operations").glob("*.json"))
        }
        ledger_path = "wiki/meta/ledgers/source-ledger.json"
        ledger = (vault / ledger_path).read_bytes()
        ledger_doc = json.loads(ledger)

        # Registration proof is derived from actual receipt/head/current-ledger
        # bytes.  No receipt or historical proof is manufactured here.
        association = associate_source(
            observation, raw_bytes=raw, head_bytes=head, receipt_bytes=receipts,
            ledger_bytes=ledger, existing=[]
        )["association"]
        assoc_ref = association_reference(association)
        extraction = extraction_descriptor(observation)
        extraction_raw = canonicalize(observation)
        snapshot_path = association["registration"]["source_ledger_path"]
        paper_id = observation["paper_id"]
        paper_page = f"wiki/papers/{paper_page_slug(paper_id)}.md"
        source_id = association["source_id"]

        proposed_ledger = copy.deepcopy(ledger_doc)
        proposed_ledger["sources"][source_id]["pages"] = [paper_page]
        assert validate_source_ledger(proposed_ledger) == []

        page = observation["pages"][0]
        text = raw.decode("utf-8")
        start, end = page["text_start"], page["text_end"]
        locator = {
            "kind": "markdown", "source_id": source_id, "association": assoc_ref,
            "path": association["raw"]["path"], "sha256": association["raw"]["sha256"],
            "charspan": [start, end], "page_anchor": page["anchor"],
            "excerpt_sha256": h(text[start:end].encode("utf-8")),
        }
        evidence = {**locator, "relation": "supports"}
        wire = encode_evidence(evidence)
        claim_text = "The captured Markdown source contains an exact observed statement."
        subject = f"paper:{paper_id}"
        claim = {
            "claim_id": claim_id(subject, claim_text),
            "stable_subject_id": subject,
            "canonical_claim_text": claim_text,
            "evidence": [evidence], "assessment": "provisional", "reviewed_at": None,
        }
        event = {
            "schema": "video-paper-wiki.assessment-event.v2", "event_id": "ase-" + "0" * 20,
            "claim_id": claim["claim_id"], "previous_event_id": None,
            "actor_kind": "system", "transition_kind": "genesis", "from_assessment": None,
            "to_assessment": "provisional", "claim_text_sha256": h(claim_text.encode()),
            "evidence_fingerprint": evidence_fingerprint_versioned([evidence]),
            "decided_by": "offline-source-publication-probe", "decided_at": STAMP,
            "reason": "Offline proposed v2 genesis event; no human decision.",
            "evidence_profile": evidence_profile([evidence]),
        }
        event["event_id"] = assessment_event_id(event)
        event_sha = h(canonicalize(event))
        assessment_heads = derive_assessment_heads(claims=[claim], events=[event])
        assessment_heads_v2 = {
            "schema": "video-paper-wiki.assessment-heads.v2",
            "heads": {claim["claim_id"]: {"event_id": event["event_id"],
                                             "event_sha256": event_sha,
                                             "evidence_profile": "mixed-v2"}},
        }
        display_heads = derive_display_heads([association], [])

        record = json.loads((SOURCE / "tests/fixtures/contracts/valid/"
                             "video-paper-wiki.paper-record.v2.json").read_bytes())
        record.update({
            "paper_id": paper_id, "title": observation["title"],
            "title_zh": observation["title"], "authors": ["Offline probe"],
            "published_at": "2026-09-09", "aliases": [], "source_ids": [source_id],
            "taxonomy": [], "active_extraction_path": None,
            "active_extraction_sha256": None,
            "section_claim_refs": [{"section": "one_sentence_conclusion",
                                    "claim_id": claim["claim_id"], "core": True,
                                    "lifecycle": "active"}],
            "created_at": STAMP, "updated_at": STAMP,
            "source_associations": [assoc_ref], "display_head": None,
        })
        validate_document(record, PAPER)
        material = {
            "schema": COMPILE, "operation_id": "offline-source-publication-probe",
            "papers": [{"record": record, "claims": [claim], "events": [event],
                         "associations": [association], "display_decisions": [],
                         "assessment_heads": assessment_heads}],
            "code": [], "concepts": [],
        }
        compile_kwargs = {
            "raw_sources": {association["raw"]["path"]: raw},
            "extraction_artifacts": {extraction["path"]: extraction_raw},
            "head_bytes": head, "receipt_bytes": receipts,
            "registration_ledgers": {snapshot_path: ledger},
        }
        pages = compile_pages(material, **compile_kwargs)
        validate_source_inventory([association], **compile_kwargs)

        payloads = [put(association["raw"]["path"], raw),
                    put(extraction["path"], extraction_raw), put(snapshot_path, ledger),
                    put_json(ledger_path, proposed_ledger)]
        association_path = f"wiki/meta/records/source-versions/{association['association_id']}.json"
        event_path = f"wiki/meta/reviews/{claim['claim_id']}/{event['event_id']}.json"
        record_path = f"wiki/meta/records/papers/{paper_page_slug(paper_id)}.json"
        payloads += [put_json(association_path, association), put_json(event_path, event),
                     put_json(record_path, record), put_json("wiki/meta/records/assessment-heads.json",
                                                             assessment_heads_v2)]
        compiled = [put(path, value) for path, value in pages.items()]

        actual = {
            "capture": {"disposition": capture.get("disposition"),
                         "stored_path": capture["stored_path"], "source_id": capture["source_id"],
                         "request_batch_id": capture["request"]["plan"]["batch_id"],
                         "requested_operation_id": capture["requested_operation_id"]},
            "legacy_admission": {"state": admission["state"], "operation_id": admission["operation_id"],
                                  "source_id": admission["source_id"],
                                  "request_batch_id": admission_authority["request"]["batch_id"]},
            "receipt_backed": {"classification": audit["classification"], "head_path": head_path,
                               "head_sha256": h(head), "receipt_count": len(receipts),
                               "receipt_paths": sorted(receipts), "ledger_sha256": h(ledger),
                               "raw_path": raw_path, "raw_sha256": h(raw)},
        }
        result = {
            "schema": "video-paper-wiki.source-publication-bridge-probe-result.v1",
            "status": "validated_proposed_bytes_only",
            "source_tree": str(SOURCE), "source_tree_contract": "SOURCE-SEMANTICS-v1/integration-r1",
            "actual": actual,
            "proposed": {"paper_id": paper_id, "paper_page": paper_page, "source_id": source_id,
                         "association": association, "association_path": association_path,
                         "observation": observation, "wire_evidence": wire, "claim": claim,
                         "event": event, "assessment_heads": assessment_heads,
                         "assessment_heads_v2": assessment_heads_v2, "display_heads": display_heads,
                         "source_ledger_pages": [paper_page], "proposed_source_ledger": proposed_ledger,
                         "compile_material": material, "compiled_page_paths": sorted(pages)},
            "payloads": payloads, "compiled_payloads": compiled,
            "checks": {"pinned_source_ledger": True, "actual_receipt_registration_proof": True,
                       "association_inventory": True, "assessment_heads": True, "compiler_v2": True,
                       "display_decision": False, "human_decision": False, "proposed_bytes_applied": False},
        }
        for rel, value in (("actual/capture-authority.json", capture),
                           ("actual/capture-bound-result.json", capture_bound),
                           ("actual/admission-authority.json", admission_authority),
                           ("actual/admission-applied-result.json", applied),
                           ("actual/audit.json", audit)):
            put_json(rel, value)
        result_raw = canonicalize(result)
        result_path = OUT / "source-publication-bridge-probe-result.json"
        result_path.write_bytes(result_raw)
        print(json.dumps({"result": str(result_path), "result_sha256": h(result_raw),
                          "result_size_bytes": len(result_raw), "association_id": association["association_id"],
                          "source_id": source_id, "claim_id": claim["claim_id"],
                          "event_id": event["event_id"], "compiled_pages": sorted(pages)},
                         separators=(",", ":")))


if __name__ == "__main__":
    main()
