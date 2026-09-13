"""Bounded legacy taxonomy-retirement refusal probe.

This keeps one legacy paper's only taxonomy concept in the receipt-backed R1
fixture, then asks source conversion to update that existing paper while
removing the concept.  The probe records the current preparation refusal and
checks that the retained Vault is unchanged.  It never edits production code
or a real Vault.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import stat
import sys
import tempfile
from pathlib import Path

REPO = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
S = REPO / ".work/parallel/source-conversion-v1/terminal-1/source"
UPSTREAM = S / "vendor/claude-obsidian"
R1 = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/source-state-legacy-r1/source_state_legacy_probe.py"
BASE = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/source-conversion-mixed-r1/source_conversion_mixed_r1_probe.py"
OUT = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/source-conversion-mixed-r1"
LIGHT_ID = "sha256:" + "a" * 64

sys.path[:0] = [str(S / "src"), str(S), str(UPSTREAM)]

from video_paper_wiki.jcs import canonicalize  # noqa: E402


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def vault_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def load_base():
    spec = importlib.util.spec_from_file_location("mixed_probe_helpers", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load mixed probe helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_with_single_taxonomy(base, r1):
    original_make = r1.make_initial_material
    original_payloads = r1.payloads_for_legacy
    original_collect = r1.collect_source_state

    def collect_legacy_state(snapshot, audit, **kwargs):
        kwargs.setdefault("allow_legacy_structural", True)
        return original_collect(snapshot, audit, **kwargs)

    def make_material(fixture_dir):
        material, code, pdfs, artifacts, triple = original_make(fixture_dir)
        target = material["papers"][-1]
        old_paper_id = target["record"]["paper_id"]
        target["record"]["paper_id"] = LIGHT_ID
        # Retain the old explicit arXiv identifier as a canonical alias so
        # the v1 identity binding remains valid after changing the primary
        # paper identity to the lightweight SHA identity.
        target["record"]["aliases"] = sorted({*target["record"]["aliases"], old_paper_id})
        target["record"]["taxonomy"] = [{"axis": "backbone", "slug": "dit"}]
        # The other legacy papers retain their records but no longer own the
        # concept, so this target is the actual last stored concept owner.
        for paper in material["papers"][:-1]:
            paper["record"]["taxonomy"] = []
        old_event_ids = {event["event_id"]: event for event in target["events"]}
        claim_ids = {}
        for claim in target["claims"]:
            old_id = claim["claim_id"]
            new_id = r1.claim_id("paper:" + LIGHT_ID, claim["canonical_claim_text"])
            claim_ids[old_id] = new_id
            claim["claim_id"] = new_id
            claim["stable_subject_id"] = "paper:" + LIGHT_ID
        for ref in target["record"]["section_claim_refs"]:
            ref["claim_id"] = claim_ids[ref["claim_id"]]
        # Rebind the small legacy event chain to the replacement paper ID.
        old_to_new_event = {}
        for event in sorted(target["events"], key=lambda item: item["previous_event_id"] is not None):
            old_id = event["event_id"]
            event["claim_id"] = claim_ids[event["claim_id"]]
            previous = event["previous_event_id"]
            event["previous_event_id"] = None if previous is None else old_to_new_event[previous]
            event["event_id"] = "ase-" + "0" * 20
            event["event_id"] = r1.assessment_event_id(event)
            old_to_new_event[old_id] = event["event_id"]
        material["concepts"] = r1.concept_items_for_papers([x["record"] for x in material["papers"]])
        return material, code, pdfs, artifacts, triple

    r1.make_initial_material = make_material
    r1.collect_source_state = collect_legacy_state
    return r1


def main() -> None:
    base = load_base()
    r1 = legacy_with_single_taxonomy(base, base.load_r1())
    result = {
        "schema": "video-paper-wiki.source-conversion-taxonomy-retirement-r1.v1",
        "status": "failed",
        "temporary_fixture_only": True,
        "source_root": str(S),
        "source_head": "fb37dcd80fa4445d86872a9e03ecb6a720048596",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="vpwiki-source-conversion-taxonomy-r1-", dir="/private/tmp") as tmp_name:
            tmp = Path(tmp_name)
            legacy = r1.build_legacy(tmp)
            checkout, vault = legacy["checkout"], legacy["vault"]
            state_before = legacy["state"]
            old_concept = "wiki/concepts/backbone-dit.md"
            if old_concept not in state_before["bytes"]:
                raise AssertionError("single legacy taxonomy concept page was not retained")

            from tests.markdown_source_fixture import LIGHT_ID as FIXTURE_LIGHT_ID, prepared_source
            from tests.research.test_source_admission import _apply_bundle, apply_publication
            from video_paper_wiki.markdown_source import admit_markdown_source, bind_markdown_capture_result, inspect_markdown_capture
            from video_paper_wiki.receipt_audit import _Snapshot, audit_integrity
            from video_paper_wiki_research.light_index import build_index
            from video_paper_wiki_research.light_knowledge import export_knowledge_context, import_knowledge
            from tests.research.test_light_knowledge import _knowledge_document

            if FIXTURE_LIGHT_ID != LIGHT_ID:
                raise AssertionError("fixture light identity drifted")
            planned, prepared, _ = prepared_source(checkout, batch="taxonomy-md-capture")
            capture_authority = inspect_markdown_capture(
                prepared=prepared["request_path"], operation_id="taxonomy-md-capture",
                vault_root=vault, upstream_root=UPSTREAM,
            )["authority"]
            capture_bundle = checkout / ".work/taxonomy-md-capture" / capture_authority["transaction_staging"]["bundle_file"]
            capture_applied = _apply_bundle(
                vault, capture_bundle,
                capture_authority["upstream_authority"]["transaction"]["inspection"]["approval_sha256"],
            )
            stored = capture_authority["stored_path"]
            capture_bound = bind_markdown_capture_result(
                capture_authority, capture_applied, before={stored: None},
                after={stored: {"sha256": capture_authority["request"]["plan"]["observation"]["markdown"]["sha256"],
                                "mode": stat.S_IMODE((vault / stored).stat().st_mode)}},
            )
            admission = admit_markdown_source(
                authority=capture_authority, capture_result=capture_bound,
                vault_root=vault, upstream_root=UPSTREAM, batch_id="taxonomy-md-admit",
                operation_id="taxonomy-md-admit", ingested_at="2026-09-09T02:00:00Z",
                publication_profile="source-v1",
            )
            apply_publication(checkout, vault, admission["publication_authority"])

            workspace = checkout / ".work/light-library"
            if not build_index(workspace)["ok"]:
                raise AssertionError("light index build failed")
            context = export_knowledge_context(workspace, paper_id=LIGHT_ID)
            if not context["ok"]:
                raise AssertionError("light context export failed")
            document = _knowledge_document(LIGHT_ID, context["context"]["evidence"][0]["chunk_id"])
            imported = import_knowledge(workspace, context, document)
            if not imported["ok"]:
                raise AssertionError("light knowledge import failed")

            target_record = legacy["material"]["papers"][-1]["record"]
            metadata = {
                "schema": "video-paper-wiki.source-conversion-metadata.v1", "paper_id": LIGHT_ID,
                "title": target_record["title"], "title_zh": target_record["title_zh"],
                "authors": target_record["authors"], "published_at": target_record["published_at"],
                "aliases": target_record["aliases"], "taxonomy": [], "code_urls": target_record["code_urls"],
            }
            authority_path = checkout / "taxonomy-capture-authority.json"
            authority_path.write_bytes(canonicalize(capture_authority))
            metadata_path = checkout / "taxonomy-retirement-metadata.json"
            metadata_path.write_bytes(canonicalize(metadata))
            before_convert = vault_snapshot(vault)

            base.reset_to_conversion_imports()
            from video_paper_wiki_research.source_conversion import convert_source_knowledge

            try:
                convert_source_knowledge(
                    workspace_root=workspace, paper_id=LIGHT_ID, record_id=imported["record_id"],
                    capture_authority=authority_path, metadata=metadata_path,
                    batch_id="taxonomy-retirement", operation_id="taxonomy-retirement",
                    vault_root=vault, proposed_at="2026-09-09T04:00:00Z",
                )
            except BaseException as exc:
                result.update({
                    # The bounded probe is successful when it reproduces the
                    # known ordering gap: refusal occurs, but the current
                    # implementation reports INVALID instead of the frozen
                    # unsupported-change code.
                    "status": ("passed" if getattr(exc, "code", None) == "SOURCE_PUBLICATION_UNSUPPORTED_CHANGE"
                                else "observed_contract_gap" if getattr(exc, "code", None) == "SOURCE_PUBLICATION_INVALID"
                                else "failed"),
                    "expected_refusal_code": "SOURCE_PUBLICATION_UNSUPPORTED_CHANGE",
                    "error_type": type(exc).__name__, "error_code": getattr(exc, "code", None),
                    "error_message": getattr(exc, "message", str(exc)),
                    "error_details": getattr(exc, "details", {}),
                    "checks": {
                        "legacy_single_concept_page_present": old_concept in state_before["bytes"],
                        "metadata_removes_last_taxonomy_concept": True,
                        "prepare_refused": True,
                        "vault_unchanged_after_refusal": before_convert == vault_snapshot(vault),
                        "real_vault_or_admin_used": False,
                    },
                })
            else:
                raise AssertionError("taxonomy retirement unexpectedly prepared")
    except BaseException as exc:
        result.update({"status": "failed", "error_type": type(exc).__name__,
                       "error_code": getattr(exc, "code", None),
                       "error_message": getattr(exc, "message", str(exc)),
                       "error_details": getattr(exc, "details", {})})
        raise
    OUT.mkdir(parents=True, exist_ok=True)
    raw = canonicalize(result)
    # R1's reproduced ordering-gap result remains immutable evidence; this
    # successor report records the narrowed conversion precheck's result.
    path = OUT / "source-conversion-taxonomy-retirement-r2-result.json"
    path.write_bytes(raw)
    print(json.dumps({"result": str(path), "sha256": digest(raw), "size_bytes": len(raw)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
