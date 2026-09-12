"""Offline R3 source-publication prepare/inspect probe.

This replays the R2 legacy receipt-backed admission fixture, feeds its exact
ten proposal payloads through the new source-publication external-input and
prepare/inspect entrypoints, and optionally applies the inspected authority
only to the disposable fixture Vault through the existing test helper.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
SOURCE = REPO / ".work/parallel/source-publication-v1/terminal-1/source"
R2_ROOT = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/r2"
R2_RESULT = R2_ROOT / "result/source-publication-proposal-probe-result.json"
R2_HASHES = R2_ROOT / "source-publication-proposal-probe-hashes.json"
SCRIPT_DIR = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/r3"
OUT = SCRIPT_DIR / "result"
sys.path[:0] = [str(SOURCE / "src"), str(SOURCE), str(SOURCE / "vendor/claude-obsidian")]

from tests.research.conftest import UPSTREAM  # noqa: E402
from tests.research.test_source_admission import apply_publication  # noqa: E402
from tests.support import make_checkout  # noqa: E402
from tests.upstream.test_markdown_source import _admit, _captured_fixture  # noqa: E402
from video_paper_wiki.jcs import canonicalize  # noqa: E402
from video_paper_wiki.receipt_audit import HEAD, audit_integrity  # noqa: E402
from video_paper_wiki.secure_io import parse_strict_json  # noqa: E402
from video_paper_wiki.source_publication import (  # noqa: E402
    audit_source_state,
    inspect_source_publication,
    prepare_source_publication_source,
)
from video_paper_wiki.source_publication_contracts import PROPOSAL, validate as validate_publication  # noqa: E402
from video_paper_wiki.source_publication_io import proposal_tree  # noqa: E402
from video_paper_wiki.source_semantics_contracts import sha  # noqa: E402

STAMP = "2026-09-09T00:00:00Z"
R2_PAYLOAD_COUNT = 10


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
    """Make envelopes portable while preserving full raw authority artifacts."""
    if isinstance(value, str):
        return value.replace(temporary_root, "<disposable-root>")
    if isinstance(value, list):
        return [stable(item, temporary_root) for item in value]
    if isinstance(value, dict):
        return {key: stable(item, temporary_root) for key, item in value.items()}
    return value


def vault_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def snapshot_hashes(snapshot: dict[str, tuple[bytes, int]]) -> list[dict[str, object]]:
    return [
        {"path": path, "sha256": h(raw), "size_bytes": len(raw), "mode": mode}
        for path, (raw, mode) in sorted(snapshot.items(), key=lambda item: item[0].encode())
    ]


def write_external_proposal(root: Path, payloads: dict[str, bytes], expected: dict) -> tuple[Path, dict]:
    proposal_root = root / "source-publication"
    content_root = proposal_root / "content"
    content_root.mkdir(parents=True)
    descriptors = []
    contents: dict[str, bytes] = {}
    for path, raw in sorted(payloads.items(), key=lambda item: item[0].encode()):
        digest = h(raw)
        contents[digest] = raw
        (content_root / digest).write_bytes(raw)
        descriptors.append({"path": path, "content_file": f"content/{digest}"})
    proposal = {
        "schema": PROPOSAL,
        "kind": "knowledge",
        "payloads": descriptors,
        "registration": None,
    }
    proposal_raw = canonicalize(proposal)
    expected_raw = canonicalize(expected)
    if proposal_raw != expected_raw:
        raise AssertionError("R2 proposal bytes differ from the external R3 reconstruction")
    proposal_path = proposal_root / "proposal.json"
    proposal_path.write_bytes(proposal_raw)
    with proposal_tree(proposal_path) as tree:
        parsed = validate_publication(
            parse_strict_json(tree.request_bytes(), invalid_code="SOURCE_PUBLICATION_INVALID"),
            PROPOSAL,
        )
        bound = tree.bind({digest: len(raw) for digest, raw in contents.items()})
        if bound != {digest: contents[digest] for digest in sorted(contents)}:
            raise AssertionError("retained external proposal content differs")
        tree.verify()
    return proposal_path, parsed


def load_r2_payloads() -> tuple[dict[str, bytes], dict, dict[str, str]]:
    result_raw = R2_RESULT.read_bytes()
    result = json.loads(result_raw)
    if canonicalize(result) != result_raw:
        raise AssertionError("R2 result is not canonical JSON")
    payloads: dict[str, bytes] = {}
    for item in result["proposal_payloads"]:
        path = item["path"]
        if path.startswith("/") or ".." in Path(path).parts:
            raise AssertionError(f"unsafe R2 payload path: {path}")
        raw = (R2_ROOT / "result/payloads" / path).read_bytes()
        if h(raw) != item["sha256"] or len(raw) != item["size_bytes"]:
            raise AssertionError(f"R2 payload digest mismatch: {path}")
        payloads[path] = raw
    if len(payloads) != R2_PAYLOAD_COUNT:
        raise AssertionError(f"expected {R2_PAYLOAD_COUNT} R2 payloads, got {len(payloads)}")
    return payloads, result["proposal"], {
        "result_sha256": h(result_raw),
        "hashes_sha256": h(R2_HASHES.read_bytes()),
    }


def run() -> None:
    if not SOURCE.is_dir():
        raise RuntimeError(f"missing accepted source tree: {SOURCE}")
    if not R2_RESULT.is_file() or not R2_HASHES.is_file():
        raise RuntimeError("R2 probe result/hash manifest is required")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    payloads, r2_proposal, r2_hashes = load_r2_payloads()
    with tempfile.TemporaryDirectory(prefix="vpwiki-source-publication-r3-", dir="/private/tmp") as tmp:
        checkout = Path(tmp) / "checkout"
        checkout.mkdir()
        make_checkout(checkout)
        os.chdir(checkout)

        # Preserve the R2 migration branch: actual pinned Markdown capture and
        # legacy admission are applied before the new source publisher runs.
        vault, _prepared_capture, capture, capture_bound = _captured_fixture(checkout)
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
        integrity_before = audit_integrity(vault)
        source_audit_before = audit_source_state(vault_root=vault)
        if source_audit_before["profile"] != "legacy-v1":
            raise AssertionError("R2 legacy admission did not leave a legacy-v1 state")

        before_prepare = vault_snapshot(vault)
        proposal_path, proposal = write_external_proposal(checkout / "caller-root", payloads, r2_proposal)
        prepared = prepare_source_publication_source(
            proposal_path=proposal_path,
            batch_id="probe-r3",
            operation_id="probe-r3",
            vault_root=vault,
        )
        after_prepare = vault_snapshot(vault)
        if before_prepare != after_prepare:
            raise AssertionError("prepare mutated the Vault")

        authority = inspect_source_publication(
            prepared=prepared["request_path"],
            operation_id="probe-r3",
            vault_root=vault,
            upstream_root=UPSTREAM,
        )
        after_inspect = vault_snapshot(vault)
        if before_prepare != after_inspect:
            raise AssertionError("inspect mutated the Vault")

        tx = authority["transaction"]
        business_paths = [write["path"] for write in tx["writes"] if write["role"] == "business"]
        write_paths = {write["path"] for write in tx["writes"]}
        read_paths = set(tx["read_preconditions"])
        expected_payload_paths = set(payloads)
        if set(prepared["changed_paths"]) != expected_payload_paths:
            raise AssertionError("legacy migration did not retain all ten R2 payload writes")
        if set(business_paths) != expected_payload_paths:
            raise AssertionError("inspected business write set differs from the ten R2 payloads")
        if tx["claimed_inputs"] != []:
            raise AssertionError("knowledge publication unexpectedly claimed an input")
        if "wiki/meta/ledgers/source-ledger.json" in read_paths:
            raise AssertionError("source-ledger write was also classified as a read")
        if write_paths.intersection(read_paths):
            raise AssertionError("transaction write/read paths overlap")
        if tx["operation_type"] != "ingest" or tx["phase"] != "inspected":
            raise AssertionError("inspected transaction is not ingest/inspected")
        if tx != authority["upstream_authority"]["transaction"]:
            raise AssertionError("upstream and pinned transaction authorities differ")

        applied = apply_publication(checkout, vault, authority)
        integrity_after = audit_integrity(vault)
        source_audit_after = audit_source_state(vault_root=vault)
        after_apply = vault_snapshot(vault)

        receipt_path = f"wiki/meta/operations/000000000003-probe-r3.json"
        expected_apply_paths = set(expected_payload_paths) | {receipt_path, HEAD}
        if set(applied["changed_paths"]) != expected_apply_paths:
            raise AssertionError("fixture apply changed paths differ from inspected authority")
        if source_audit_after["profile"] != "source-v1":
            raise AssertionError("post-apply typed audit did not enter source-v1")
        if source_audit_after["counts"] != {
            "files": 16,
            "papers": 1,
            "repos": 0,
            "claims": 1,
            "events": 1,
            "associations": 1,
            "display_decisions": 0,
            "ledger_snapshots": 1,
            "compiled_pages": 1,
        }:
            raise AssertionError("post-apply typed counts differ from the complete proposal state")
        if source_audit_after["display_heads"]["heads"] != []:
            raise AssertionError("post-apply source display heads are not empty")
        if not integrity_after["valid"] or integrity_after["classification"] != "receipt_backed":
            raise AssertionError("post-apply receipt audit is not receipt-backed and valid")

        # Existing raw input and any pre-existing immutable semantic bytes must
        # remain byte-identical across the publication.  New immutable bytes
        # are checked against the exact proposed payload map.
        immutable_prefixes = (
            ".raw/derived/source-ledgers/",
            ".raw/derived/markdown-source/",
            "wiki/meta/records/source-versions/",
            "wiki/meta/reviews/clm-",
            "wiki/meta/reviews/source-display/",
        )
        preserved = [
            path
            for path in before_prepare
            if path.startswith(immutable_prefixes) or path.startswith(".raw/captured/")
        ]
        if any(after_apply[path][0] != before_prepare[path][0] for path in preserved):
            raise AssertionError("an existing raw or immutable semantic byte changed")
        for path, raw in payloads.items():
            if path not in after_apply or after_apply[path][0] != raw:
                raise AssertionError(f"applied payload bytes differ at {path}")

        actual_payloads = [
            put_json("actual/admission-authority.json", admission_authority),
            put_json("actual/admission-applied-result.json", admission_applied),
            put_json("actual/integrity-before.json", integrity_before),
            put_json("actual/integrity-after.json", integrity_after),
            put_json("actual/source-audit-before.json", source_audit_before),
            put_json("actual/source-audit-after.json", source_audit_after),
            put_json("actual/publication-authority.json", authority),
            put_json("actual/publication-applied-result.json", applied),
        ]
        external_files = [put("external/proposal.json", canonicalize(proposal))]
        external_files.extend(
            put(f"external/content/{h(raw)}", raw)
            for _path, raw in sorted(payloads.items(), key=lambda item: item[0].encode())
        )
        proposed_files = [
            put(f"proposed/{path}", raw)
            for path, raw in sorted(payloads.items(), key=lambda item: item[0].encode())
        ]

        result = {
            "schema": "video-paper-wiki.source-publication-prepare-inspect-probe-result.v3",
            "status": "validated_prepared_inspected_and_fixture_applied",
            "source_tree": str(SOURCE),
            "source_tree_head": "c32e68d08a142d5a5559ce717ff397f9b27f55d1",
            "r2_inputs": {
                "result_sha256": r2_hashes["result_sha256"],
                "hashes_sha256": r2_hashes["hashes_sha256"],
                "proposal_payload_count": len(payloads),
            },
            "proposal": proposal,
            "prepared": stable(prepared, tmp),
            "authority_summary": {
                "request_sha256": authority["request_sha256"],
                "request_basis": authority["request"]["basis"],
                "prospective_inventory_sha256": authority["prospective_inventory_sha256"],
                "operation_id": tx["operation_id"],
                "operation_type": tx["operation_type"],
                "phase": tx["phase"],
                "claimed_inputs": tx["claimed_inputs"],
                "business_paths": business_paths,
                "receipt_path": receipt_path,
                "head_path": HEAD,
                "read_precondition_count": len(read_paths),
                "read_preconditions_sha256": sha(canonicalize(tx["read_preconditions"])),
            },
            "audit_before": source_audit_before,
            "audit_after": source_audit_after,
            "vault_before": snapshot_hashes(before_prepare),
            "vault_after": snapshot_hashes(after_apply),
            "checks": {
                "r2_complete_ten_payloads": len(payloads) == R2_PAYLOAD_COUNT,
                "external_proposal_canonical_and_retained": True,
                "legacy_migration_baseline": source_audit_before["profile"] == "legacy-v1",
                "prepare_no_vault_mutation": before_prepare == after_prepare,
                "inspect_no_vault_mutation": before_prepare == after_inspect,
                "knowledge_registration_null": proposal["kind"] == "knowledge" and proposal["registration"] is None,
                "frozen_operation_type_ingest": tx["operation_type"] == "ingest",
                "complete_business_write_set": set(business_paths) == expected_payload_paths,
                "knowledge_claimed_inputs_empty": tx["claimed_inputs"] == [],
                "source_ledger_write_not_read": "wiki/meta/ledgers/source-ledger.json" not in read_paths,
                "read_write_sets_disjoint": not write_paths.intersection(read_paths),
                "upstream_transaction_identical": tx == authority["upstream_authority"]["transaction"],
                "fixture_only_operator_apply": True,
                "receipt_backed_after_apply": integrity_after["classification"] == "receipt_backed",
                "source_v1_typed_audit_after_apply": source_audit_after["profile"] == "source-v1",
                "immutable_history_and_raw_preserved": True,
                "display_heads_empty": source_audit_after["display_heads"]["heads"] == [],
                "human_decision": False,
                "real_vault_or_admin_used": False,
            },
            "payloads": {
                "actual": actual_payloads,
                "external": external_files,
                "proposed": proposed_files,
            },
        }
        result_raw = canonicalize(result)
        result_path = OUT / "source-publication-prepare-inspect-probe-result.json"
        result_path.write_bytes(result_raw)
        print(
            json.dumps(
                {
                    "result": str(result_path),
                    "result_sha256": h(result_raw),
                    "result_size_bytes": len(result_raw),
                    "proposal_payload_count": len(payloads),
                    "prepared_changed_count": len(prepared["changed_paths"]),
                    "inspected_business_write_count": len(business_paths),
                    "applied_path_count": len(applied["changed_paths"]),
                    "post_profile": source_audit_after["profile"],
                },
                separators=(",", ":"),
            )
        )


def main() -> None:
    try:
        run()
    except BaseException as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        failure = {
            "schema": "video-paper-wiki.source-publication-prepare-inspect-probe-result.v3",
            "status": "failed",
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", None),
            "message": str(exc),
            "details": getattr(exc, "details", {}),
            "traceback": traceback.format_exc(),
        }
        (OUT / "source-publication-prepare-inspect-probe-failure.json").write_bytes(canonicalize(failure))
        raise


if __name__ == "__main__":
    main()
