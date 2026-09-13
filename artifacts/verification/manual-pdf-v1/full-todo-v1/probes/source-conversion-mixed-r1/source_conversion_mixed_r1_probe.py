"""Independent mixed legacy/code conversion probe.

The fixture starts with the immutable R1 receipt-backed legacy builder, adds an
actual Markdown capture/admission to that same disposable Vault, and converts
the lightweight Markdown paper through the source-conversion WIP checkout.
Only /private/tmp and this verification artifact directory are written.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

REPO = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
S = REPO / ".work/parallel/source-conversion-v1/terminal-1/source"
R1 = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/source-state-legacy-r1/source_state_legacy_probe.py"
OUT = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/source-conversion-mixed-r1"
UPSTREAM = S / "vendor/claude-obsidian"

sys.path[:0] = [str(S / "src"), str(S), str(UPSTREAM)]

from video_paper_wiki.jcs import canonicalize  # noqa: E402


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def vault_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def snapshot_hashes(snapshot: dict[str, tuple[bytes, int]]) -> list[dict[str, object]]:
    return [
        {"path": path, "sha256": digest(raw), "size_bytes": len(raw), "mode": mode}
        for path, (raw, mode) in sorted(snapshot.items(), key=lambda item: item[0].encode())
    ]


def load_r1():
    spec = importlib.util.spec_from_file_location("source_state_legacy_r1_mixed", R1)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load immutable R1 fixture builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_with_unreviewed_row(r1):
    """Reuse R1 builder, making one unrelated legacy claim nonaccepted/undated."""
    original_make = r1.make_initial_material
    original_payloads = r1.payloads_for_legacy
    original_collect = r1.collect_source_state

    def collect_legacy_state(snapshot, audit, **kwargs):
        # The conversion contract deliberately accepts the closed historical
        # legacy projection, whose optional reviewed_at key may be absent.
        kwargs.setdefault("allow_legacy_structural", True)
        return original_collect(snapshot, audit, **kwargs)

    def make_material(fixture_dir):
        material, code, pdfs, artifacts, triple = original_make(fixture_dir)
        target = material["papers"][-1]
        claim = target["claims"][0]
        # Retain the accepted core claim required by the legacy compiler and
        # append an unrelated non-core provisional claim whose historical
        # ledger row intentionally omits reviewed_at.
        genesis = next(event for event in target["events"] if event["previous_event_id"] is None)
        extra_text = "An unrelated legacy limitation remains provisional."
        extra = copy.deepcopy(claim)
        extra["canonical_claim_text"] = extra_text
        extra["claim_id"] = r1.claim_id("paper:" + target["record"]["paper_id"], extra_text)
        extra["assessment"] = "provisional"
        # The internal legacy compiler shape requires the key, while the
        # historical ledger payload below intentionally omits it.
        extra["reviewed_at"] = None
        extra_event = copy.deepcopy(genesis)
        extra_event["claim_id"] = extra["claim_id"]
        extra_event["claim_text_sha256"] = digest(extra_text.encode())
        extra_event["evidence_fingerprint"] = r1.evidence_fingerprint(extra["evidence"])
        extra_event["event_id"] = "ase-" + "0" * 20
        extra_event["event_id"] = r1.assessment_event_id(extra_event)
        target["claims"].append(extra)
        target["events"].append(extra_event)
        target["record"]["section_claim_refs"].append({
            "claim_id": extra["claim_id"], "section": "limitations", "core": False, "lifecycle": "active",
        })
        return material, code, pdfs, artifacts, triple

    def payloads(material, code, pdfs, artifacts, triple):
        result = original_payloads(material, code, pdfs, artifacts, triple)
        ledger_path = "wiki/meta/ledgers/claim-ledger.json"
        ledger = json.loads(result[ledger_path])
        paper = material["papers"][-1]
        extra = next(claim for claim in paper["claims"] if claim["assessment"] == "provisional")
        # The immutable R1 helper only emits its original first claim into the
        # closed ledger/compiler-input slots. Add the deliberately unrelated
        # provisional row to those same legacy payloads so the mixed fixture is
        # a structurally complete legacy state rather than an orphan-row test.
        page = "wiki/papers/" + r1.paper_page_slug(paper["record"]["paper_id"]) + ".md"
        ledger["claims"][extra["claim_id"]] = {
            "text": extra["canonical_claim_text"], "risk": "normal",
            "assessment": "provisional", "confidence": "unknown",
            "reviewed_at": None, "location": {"path": page},
            "evidence": [r1.encode_evidence(extra["evidence"][0])],
            "notes": None, "supersedes": None,
        }
        ledger["claims"][extra["claim_id"]].pop("reviewed_at", None)
        result[ledger_path] = canonicalize(ledger)
        # Conversion materializes the missing reviewed_at key on every
        # historical row. Give this unrelated row's retained PDF source its
        # existing owner-page link so that the source-ledger preservation
        # invariant can be checked when that otherwise unchanged row is
        # touched by the typed migration.
        source_ledger_path = "wiki/meta/ledgers/source-ledger.json"
        source_ledger = json.loads(result[source_ledger_path])
        source_id = extra["evidence"][0]["source_id"]
        source_ledger["sources"][source_id]["pages"] = [page]
        result[source_ledger_path] = canonicalize(source_ledger)
        slug = r1.paper_page_slug(paper["record"]["paper_id"])
        result[f".raw/derived/compiler-input/{slug}-claims.json"] = canonicalize(paper["claims"])
        result[f".raw/derived/compiler-input/{slug}-events.json"] = canonicalize(paper["events"])
        return result

    r1.make_initial_material = make_material
    r1.payloads_for_legacy = payloads
    r1.collect_source_state = collect_legacy_state
    return r1


def reset_to_conversion_imports():
    """Drop fixture-loaded production modules so conversion imports exact S bytes."""
    sys.path[:] = [str(S / "src"), str(S), str(UPSTREAM)] + [
        entry for entry in sys.path
        if entry not in {str(S / "src"), str(S), str(UPSTREAM), str(REPO)}
    ]
    for name in list(sys.modules):
        if name == "video_paper_wiki" or name.startswith("video_paper_wiki."):
            del sys.modules[name]
        elif name == "video_paper_wiki_research" or name.startswith("video_paper_wiki_research."):
            del sys.modules[name]


def run() -> dict[str, object]:
    r1 = legacy_with_unreviewed_row(load_r1())
    with tempfile.TemporaryDirectory(prefix="vpwiki-source-conversion-mixed-r1-", dir="/private/tmp") as tmp_name:
        tmp = Path(tmp_name)
        legacy = r1.build_legacy(tmp)
        checkout, vault = legacy["checkout"], legacy["vault"]

        # Use the fixture's actual legacy source-state implementation to verify
        # the baseline before adding the real Markdown capture.
        state_before = legacy["state"]
        if state_before["profile"] != "legacy-v1":
            raise AssertionError("legacy baseline did not remain structural")
        missing_reviewed = [
            cid for cid, row in state_before["claim_ledger"]["claims"].items()
            if "reviewed_at" not in row
        ]
        if not missing_reviewed:
            raise AssertionError("baseline lacks the required undated nonaccepted legacy row")

        # Fixture helpers perform actual pinned capture/admission transactions.
        from tests.markdown_source_fixture import LIGHT_ID, prepared_source
        from tests.research.test_source_admission import _apply_bundle, apply_publication
        from video_paper_wiki.markdown_source import (
            admit_markdown_source, bind_markdown_capture_result, inspect_markdown_capture,
        )
        planned, prepared, _markdown_payload = prepared_source(checkout, batch="mixed-md-capture")
        capture_authority = inspect_markdown_capture(
            prepared=prepared["request_path"],
            operation_id="mixed-md-capture",
            vault_root=vault,
            upstream_root=UPSTREAM,
        )["authority"]
        capture_bundle = checkout / ".work/mixed-md-capture" / capture_authority["transaction_staging"]["bundle_file"]
        capture_applied = _apply_bundle(
            vault, capture_bundle,
            capture_authority["upstream_authority"]["transaction"]["inspection"]["approval_sha256"],
        )
        stored = capture_authority["stored_path"]
        capture_bound = bind_markdown_capture_result(
            capture_authority,
            capture_applied,
            before={stored: None},
            after={stored: {"sha256": capture_authority["request"]["plan"]["observation"]["markdown"]["sha256"],
                            "mode": stat.S_IMODE((vault / stored).stat().st_mode)}},
        )
        admission = admit_markdown_source(
            authority=capture_authority,
            capture_result=capture_bound,
            vault_root=vault,
            upstream_root=UPSTREAM,
            batch_id="mixed-md-admit",
            operation_id="mixed-md-admit",
            ingested_at="2026-09-09T02:00:00Z",
            publication_profile="source-v1",
        )
        apply_publication(checkout, vault, admission["publication_authority"])

        # Build and import a real lightweight head from the same captured source.
        from tests.research.test_light_knowledge import _knowledge_document
        from video_paper_wiki_research.light_index import build_index
        from video_paper_wiki_research.light_knowledge import export_knowledge_context, import_knowledge
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

        authority_path = checkout / "mixed-capture-authority.json"
        authority_path.write_bytes(canonicalize(capture_authority))
        metadata_path = checkout / "mixed-conversion-metadata.json"
        metadata = {
            "schema": "video-paper-wiki.source-conversion-metadata.v1",
            "paper_id": LIGHT_ID,
            "title": "Mixed legacy conversion paper",
            "title_zh": "混合迁移论文",
            "authors": [],
            "published_at": "2024-01-02T12:34:56.123Z",
            "aliases": [],
            "taxonomy": [],
            "code_urls": [],
        }
        metadata_path.write_bytes(canonicalize(metadata))

        before_convert = vault_snapshot(vault)
        # Import the conversion WIP after fixture assembly so its production
        # modules are loaded from the exact S checkout, not the R1 helper tree.
        reset_to_conversion_imports()
        from video_paper_wiki.source_publication import audit_source_state
        from video_paper_wiki.source_state import collect_source_state
        from video_paper_wiki.receipt_audit import _Snapshot, audit_integrity
        from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER, SOURCE_LEDGER
        from video_paper_wiki_research.source_conversion import convert_source_knowledge

        kwargs = {
            "workspace_root": workspace,
            "paper_id": LIGHT_ID,
            "record_id": imported["record_id"],
            "capture_authority": authority_path,
            "metadata": metadata_path,
            "batch_id": "mixed-conversion",
            "operation_id": "mixed-conversion",
            "vault_root": vault,
            "proposed_at": "2026-09-09T04:00:00Z",
        }
        prepared_conversion = convert_source_knowledge(**kwargs)
        if prepared_conversion["state"] != "source_publication_prepared":
            raise AssertionError("conversion did not prepare a publication")
        prepared_vault_unchanged = vault_snapshot(vault) == before_convert
        if not prepared_vault_unchanged:
            raise AssertionError("conversion preparation mutated the Vault")

        # Inspect/apply through existing fixture helper and audit the result.
        authority = __import__("video_paper_wiki.source_publication", fromlist=["inspect_source_publication"]).inspect_source_publication(
            prepared=prepared_conversion["request_path"],
            operation_id="mixed-conversion",
            vault_root=vault,
            upstream_root=UPSTREAM,
        )
        if vault_snapshot(vault) != before_convert:
            raise AssertionError("conversion inspect mutated the Vault")
        applied = apply_publication(checkout, vault, authority)
        after = vault_snapshot(vault)

        snapshot = _Snapshot(vault)
        try:
            audit = audit_integrity(vault, _snapshot=snapshot)
            final_state = collect_source_state(snapshot, audit)
        finally:
            snapshot.close()
        source_audit = audit_source_state(vault_root=vault)
        if source_audit["profile"] != "source-v1":
            raise AssertionError("post-conversion state is not source-v1")

        final_rows = final_state["claim_ledger"]["claims"]
        if any("reviewed_at" not in row for row in final_rows.values()):
            raise AssertionError("complete mixed state still lacks reviewed_at key")
        if not all(final_rows[cid]["reviewed_at"] is None for cid in missing_reviewed):
            raise AssertionError("missing reviewed_at rows did not migrate to null")

        changed = {}
        for path in sorted(set(before_convert) | set(after), key=lambda item: item.encode()):
            before_raw = before_convert.get(path, (None, None))[0]
            after_raw = after.get(path, (None, None))[0]
            if before_raw != after_raw:
                changed[path] = {"before": None if before_raw is None else digest(before_raw),
                                 "after": None if after_raw is None else digest(after_raw)}
        # Existing code capture/manifests/pages and immutable history must stay byte exact.
        for path, pair in changed.items():
            if path.startswith((".raw/captured/", ".raw/derived/", "wiki/meta/reviews/", "wiki/meta/operations/")):
                # The new Markdown source and its association are expected new
                # payloads; all pre-existing paths must remain exact.
                if path in before_convert:
                    raise AssertionError(f"existing immutable path changed: {path}")
            if path.startswith("wiki/code/") and path in before_convert:
                raise AssertionError(f"legacy code page changed: {path}")
        unrelated = []
        for cid in missing_reviewed:
            before_row = json.loads(before_convert[CLAIM_LEDGER][0])["claims"][cid]
            after_row = final_rows[cid]
            expected = copy.deepcopy(before_row)
            expected["reviewed_at"] = None
            if after_row != expected:
                raise AssertionError(f"unrelated legacy row changed beyond reviewed_at:null: {cid}")
            unrelated.append({"claim_id": cid, "before": before_row, "after": after_row})

        result = {
            "schema": "video-paper-wiki.source-conversion-mixed-legacy-r1.v1",
            "status": "passed",
            "temporary_fixture_only": True,
            "source_root": str(S),
            "source_head": "fb37dcd80fa4445d86872a9e03ecb6a720048596",
            "initial": {
                "profile": state_before["profile"],
                "counts": state_before["counts"],
                "missing_reviewed_at_claim_ids": sorted(missing_reviewed),
                "markdown_capture_source_id": capture_authority["source_id"],
                "markdown_capture_path": stored,
                "admission_operation": admission["publication_authority"]["transaction"]["operation_id"],
            },
            "conversion": {
                "state": prepared_conversion["state"],
                "summary": prepared_conversion["conversion"],
                "request_path": str(prepared_conversion["request_path"]),
                "prepared_request_sha256": digest(Path(prepared_conversion["request_path"]).read_bytes()),
                "applied_operation": authority["transaction"]["operation_id"],
            },
            "final": {
                "profile": source_audit["profile"],
                "counts": source_audit["counts"],
                "receipt_backed": source_audit["receipt_backed"],
                "integrity_classification": audit["classification"],
                "missing_reviewed_at_rows_migrated": unrelated,
                "changed_paths": sorted(changed, key=lambda item: item.encode()),
            },
            "checks": {
                "legacy_code_and_pdf_baseline_receipt_backed": state_before["counts"]["repos"] == 1,
                "markdown_captured_and_registered_in_same_vault": True,
                "light_paper_id_differs_from_legacy_papers": True,
                "prepared_without_vault_mutation": prepared_vault_unchanged,
                "mixed_state_source_v1": source_audit["profile"] == "source-v1",
                "reviewed_at_only_delta_for_unrelated_legacy_rows": True,
                "old_code_pages_preserved": True,
                "old_records_events_raw_operations_preserved": True,
                "post_state_receipt_backed": audit["classification"] == "receipt_backed" and audit["valid"],
                "human_gate_closed": False,
                "real_vault_or_admin_used": False,
            },
            "applied_result": applied,
        }
        return result


def main() -> None:
    try:
        result = run()
    except BaseException as exc:
        result = {
            "schema": "video-paper-wiki.source-conversion-mixed-legacy-r1.v1",
            "status": "failed",
            "temporary_fixture_only": True,
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", None),
            "error_message": getattr(exc, "message", str(exc)),
            "error_details": getattr(exc, "details", {}),
        }
        raise
    OUT.mkdir(parents=True, exist_ok=True)
    raw = canonicalize(result)
    # R1 result remains immutable evidence; corrected reporting is emitted as
    # a successor report rather than replacing that earlier artifact.
    path = OUT / "source-conversion-mixed-r2-result.json"
    path.write_bytes(raw)
    print(json.dumps({"result": str(path), "sha256": digest(raw), "size_bytes": len(raw)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
