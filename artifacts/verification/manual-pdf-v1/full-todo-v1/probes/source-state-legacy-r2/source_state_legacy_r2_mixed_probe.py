"""Offline R2 mixed legacy/source-v1 source-state probe.

This replay starts from the accepted R1 receipt-backed legacy fixture, performs
an actual Markdown capture and admission on that same disposable Vault, then
builds a complete mixed publication from the exact R2 modern proposal material.
The modern association/event are resealed against the merged legacy receipt
chain and ledger.  No repository Vault, admin command, production code, tests,
or Git state is changed.
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
import traceback
from pathlib import Path

REPO = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
SOURCE = REPO / ".work/parallel/source-publication-v1/terminal-1/source"
R1_SCRIPT = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/source-state-legacy-r1/source_state_legacy_probe.py"
R2_ROOT = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/r2"
R2_RESULT = R2_ROOT / "result/source-publication-proposal-probe-result.json"
R2_HASHES = R2_ROOT / "source-publication-proposal-probe-hashes.json"
OUT = REPO / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/source-state-legacy-r2"
RESULT_DIR = OUT / "result"
UPSTREAM = SOURCE / "vendor/claude-obsidian"
sys.path[:0] = [str(SOURCE / "src"), str(SOURCE), str(UPSTREAM)]

from tests.markdown_source_fixture import prepared_source  # noqa: E402
from tests.research.conftest import UPSTREAM as TEST_UPSTREAM  # noqa: E402
from tests.research.test_source_admission import _apply_bundle, apply_publication  # noqa: E402
from video_paper_wiki.identity import assessment_event_id  # noqa: E402
from video_paper_wiki.jcs import canonicalize  # noqa: E402
from video_paper_wiki.markdown_locator import (  # noqa: E402
    decode_evidence,
    encode_evidence,
    evidence_fingerprint_versioned,
)
from video_paper_wiki.markdown_source import (  # noqa: E402
    admit_markdown_source,
    bind_markdown_capture_result,
    inspect_markdown_capture,
)
from video_paper_wiki.markdown_source_contracts import sha as markdown_sha  # noqa: E402
from video_paper_wiki.receipt_audit import (  # noqa: E402
    HEAD,
    _Snapshot,
    _walk_inventory,
    audit_integrity,
)
from video_paper_wiki.secure_io import parse_strict_json  # noqa: E402
from video_paper_wiki.source_publication import (  # noqa: E402
    audit_source_state,
    inspect_source_publication,
    prepare_source_publication_source,
)
from video_paper_wiki.source_publication_contracts import (  # noqa: E402
    ASSESSMENT_HEADS,
    CLAIM_LEDGER,
    DISPLAY_HEADS,
    PROPOSAL,
    SOURCE_LEDGER,
    validate as validate_publication,
)
from video_paper_wiki.source_registration import historical_source_ledger  # noqa: E402
from video_paper_wiki.source_semantics_contracts import sha  # noqa: E402
from video_paper_wiki.source_state import collect_source_state  # noqa: E402
from video_paper_wiki.source_versions import associate_source  # noqa: E402
from video_paper_wiki.source_publication_io import proposal_tree  # noqa: E402

STAMP = "2026-09-09T00:00:00Z"
R2_PAYLOAD_COUNT = 10


def h(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def put(rel: str, raw: bytes) -> dict[str, object]:
    path = RESULT_DIR / "payloads" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": rel, "sha256": h(raw), "size_bytes": len(raw)}


def put_json(rel: str, value: object) -> dict[str, object]:
    return put(rel, canonicalize(value))


def stable(value: object, temporary_root: str) -> object:
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


def load_r1_module():
    spec = importlib.util.spec_from_file_location("source_state_legacy_r1", R1_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load immutable R1 fixture builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def inventory_bytes(snapshot: _Snapshot) -> dict[str, bytes]:
    return {path: snapshot.read(path) for path in _walk_inventory(snapshot, read_bytes=True)}


def write_external_proposal(root: Path, payloads: dict[str, bytes]) -> tuple[Path, dict]:
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


def build_modern_overlay(
    *,
    snapshot: _Snapshot,
    audit: dict,
    r2_payloads: dict[str, bytes],
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Rebuild the R2 modern objects against the actual mixed receipt chain."""
    data = inventory_bytes(snapshot)
    current = collect_source_state(snapshot, audit, allow_legacy_structural=True)
    observation_path = next(
        path for path in r2_payloads if path.startswith(".raw/derived/markdown-source/")
    )
    observation = json.loads(r2_payloads[observation_path])
    raw_path = f".raw/captured/{observation['markdown']['sha256']}.md"
    raw = data[raw_path]
    receipts = {path: data[path] for path in audit["receipts"]}
    association = associate_source(
        observation,
        raw_bytes=raw,
        existing=[],
        head_bytes=data[HEAD],
        receipt_bytes=receipts,
        ledger_bytes=data[SOURCE_LEDGER],
    )["association"]
    association_path = f"wiki/meta/records/source-versions/{association['association_id']}.json"

    r2_claim_ledger = json.loads(r2_payloads[CLAIM_LEDGER])
    claim_id, r2_row = next(iter(r2_claim_ledger["claims"].items()))
    claim_row = copy.deepcopy(r2_row)
    locator = decode_evidence(claim_row["evidence"][0])
    locator["source_id"] = association["source_id"]
    locator["association"] = {
        "association_id": association["association_id"],
        "sha256": sha(canonicalize(association)),
    }
    claim_row["evidence"] = [encode_evidence({**locator, "relation": "supports"})]
    claim_ledger = json.loads(data[CLAIM_LEDGER])
    claim_ledger["generated_at"] = STAMP
    claim_ledger["claims"][claim_id] = claim_row

    event = json.loads(
        r2_payloads[
            next(path for path in r2_payloads if path.startswith("wiki/meta/reviews/clm-"))
        ]
    )
    event["evidence_fingerprint"] = evidence_fingerprint_versioned([decode_evidence(claim_row["evidence"][0])])
    event["event_id"] = "ase-" + "0" * 20
    event["event_id"] = assessment_event_id(event)
    event_path = f"wiki/meta/reviews/{claim_id}/{event['event_id']}.json"

    paper = json.loads(
        r2_payloads[
            next(path for path in r2_payloads if path.startswith("wiki/meta/records/papers/"))
        ]
    )
    paper["source_associations"] = [{
        "association_id": association["association_id"],
        "sha256": sha(canonicalize(association)),
    }]
    paper["source_ids"] = [association["source_id"]]
    paper_path = next(path for path in r2_payloads if path.startswith("wiki/meta/records/papers/"))

    heads = copy.deepcopy(current["assessment_heads"])
    heads["heads"][claim_id] = {
        "event_id": event["event_id"],
        "event_sha256": sha(canonicalize(event)),
        "evidence_profile": event["evidence_profile"],
    }
    display_heads = {"schema": "video-paper-wiki.source-display-heads.v1", "heads": []}

    # The existing registered source identity remains immutable. Its page list
    # is the mutable ledger projection required for the newly owned v2 page.
    merged_ledger = json.loads(data[SOURCE_LEDGER])
    merged_ledger["sources"][association["source_id"]]["pages"] = [paper_path.replace("meta/records/papers/", "papers/").replace(".json", ".md")]
    merged_ledger_raw = canonicalize(merged_ledger)

    overlay = {
        observation_path: r2_payloads[observation_path],
        association_path: canonicalize(association),
        event_path: canonicalize(event),
        paper_path: canonicalize(paper),
        CLAIM_LEDGER: canonicalize(claim_ledger),
        SOURCE_LEDGER: merged_ledger_raw,
        ASSESSMENT_HEADS: canonicalize(heads),
        DISPLAY_HEADS: canonicalize(display_heads),
    }
    # First ask the pure source-state collector for the complete mixed compiler
    # result, then supply every generated page as an explicit durable payload.
    prospective = collect_source_state(
        snapshot, audit, overlay=overlay, require_rendered=False, allow_legacy_structural=True
    )
    overlay.update(prospective["pages"])
    verified = collect_source_state(
        snapshot, audit, overlay=overlay, require_rendered=True, allow_legacy_structural=True
    )
    if verified["profile"] != "source-v1" or verified["counts"] != {
        "files": 56,
        "papers": 4,
        "repos": 1,
        "claims": 4,
        "events": 7,
        "associations": 1,
        "display_decisions": 0,
        "ledger_snapshots": 2,
        "compiled_pages": 6,
    }:
        raise AssertionError("mixed prospective state counts differ from the complete v2 overlay")
    return overlay, {
        "association": association,
        "association_path": association_path,
        "event": event,
        "event_path": event_path,
        "paper_path": paper_path,
        "observation_path": observation_path,
        "raw_path": raw_path,
        "prospective": verified,
    }


def error_record(exc: BaseException) -> dict[str, object]:
    return {
        "error_type": type(exc).__name__,
        "code": getattr(exc, "code", None),
        "message": getattr(exc, "message", str(exc)),
        "details": getattr(exc, "details", {}),
    }


def run() -> None:
    if not SOURCE.is_dir():
        raise RuntimeError(f"missing accepted source tree: {SOURCE}")
    if not R1_SCRIPT.is_file() or not R2_RESULT.is_file() or not R2_HASHES.is_file():
        raise RuntimeError("immutable R1 fixture and R2 proposal evidence are required")
    # Keep any explicitly recorded failed attempts as immutable history while
    # regenerating the successful candidate payloads.
    if (RESULT_DIR / "payloads").exists():
        shutil.rmtree(RESULT_DIR / "payloads")
    for stale in (RESULT_DIR / "source-state-legacy-r2-mixed-probe-result.json",
                  RESULT_DIR / "source-state-legacy-r2-mixed-probe-failure.json"):
        if stale.exists():
            stale.unlink()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    r2_payloads, r2_proposal, r2_hashes = load_r2_payloads()
    r1 = load_r1_module()

    with tempfile.TemporaryDirectory(prefix="vpwiki-source-state-r2-", dir="/private/tmp") as tmp_name:
        tmp = Path(tmp_name)
        legacy = r1.build_legacy(tmp)
        checkout, vault = legacy["checkout"], legacy["vault"]
        legacy_audit = audit_integrity(vault, _snapshot=legacy["snap"])
        legacy_state = collect_source_state(legacy["snap"], legacy_audit)
        legacy["snap"].close()
        if legacy_state["profile"] != "legacy-v1" or legacy_state["counts"] != {
            "files": 45,
            "papers": 3,
            "repos": 1,
            "claims": 3,
            "events": 6,
            "associations": 0,
            "display_decisions": 0,
            "ledger_snapshots": 0,
            "compiled_pages": 5,
        }:
            raise AssertionError("R1 legacy baseline changed")

        # Capture and apply the actual Markdown bytes through the pinned
        # capture adapter before source registration.
        planned, prepared_capture, markdown_payload = prepared_source(checkout, batch="mixed-md-capture")
        before_capture_inspect = vault_snapshot(vault)
        capture_authority = inspect_markdown_capture(
            prepared=prepared_capture["request_path"],
            operation_id="mixed-md-capture",
            vault_root=vault,
            upstream_root=TEST_UPSTREAM,
        )["authority"]
        if before_capture_inspect != vault_snapshot(vault):
            raise AssertionError("Markdown capture inspect mutated the Vault")
        capture_bundle = checkout / ".work/mixed-md-capture" / capture_authority["transaction_staging"]["bundle_file"]
        capture_applied = _apply_bundle(
            vault,
            capture_bundle,
            capture_authority["upstream_authority"]["transaction"]["inspection"]["approval_sha256"],
        )
        stored_path = capture_authority["stored_path"]
        capture_bound = bind_markdown_capture_result(
            capture_authority,
            capture_applied,
            before={stored_path: None},
            after={stored_path: {
                "sha256": capture_authority["request"]["plan"]["observation"]["markdown"]["sha256"],
                "mode": stat.S_IMODE((vault / stored_path).stat().st_mode),
            }},
        )
        admission = admit_markdown_source(
            authority=capture_authority,
            capture_result=capture_bound,
            vault_root=vault,
            upstream_root=TEST_UPSTREAM,
            batch_id="mixed-md-admit",
            operation_id="mixed-md-admit",
            ingested_at=STAMP,
            publication_profile="source-v1",
        )
        apply_publication(checkout, vault, admission["publication_authority"])
        source_audit_before = audit_source_state(vault_root=vault)
        if source_audit_before["profile"] != "legacy-v1":
            raise AssertionError("registration must preserve the structural legacy baseline")

        before_prepare = vault_snapshot(vault)
        snapshot = _Snapshot(vault)
        try:
            audit_before = audit_integrity(vault, _snapshot=snapshot)
            all_overlay, derived = build_modern_overlay(
                snapshot=snapshot, audit=audit_before, r2_payloads=r2_payloads
            )
        finally:
            snapshot.close()
        # The complete mixed compiler may reproduce an existing page byte-for-byte.
        # Such a payload remains covered by the full-state check but is omitted
        # from the durable knowledge request as an ineffective duplicate.
        overlay = {
            path: raw for path, raw in all_overlay.items()
            if before_prepare.get(path, (None, None))[0] != raw
        }

        proposal_path, proposal = write_external_proposal(checkout / "caller-root", overlay)
        if proposal["kind"] != "knowledge" or proposal["registration"] is not None:
            raise AssertionError("mixed R2 overlay must be a knowledge proposal")
        prepared = prepare_source_publication_source(
            proposal_path=proposal_path,
            batch_id="mixed-publication",
            operation_id="mixed-publication",
            vault_root=vault,
        )
        after_prepare = vault_snapshot(vault)
        if before_prepare != after_prepare:
            raise AssertionError("prepare mutated the Vault")
        if set(prepared["changed_paths"]) != set(overlay):
            raise AssertionError("prepared changed paths differ from the complete mixed overlay")

        authority = inspect_source_publication(
            prepared=prepared["request_path"],
            operation_id="mixed-publication",
            vault_root=vault,
            upstream_root=TEST_UPSTREAM,
        )
        after_inspect = vault_snapshot(vault)
        if before_prepare != after_inspect:
            raise AssertionError("inspect mutated the Vault")

        tx = authority["transaction"]
        business_paths = [write["path"] for write in tx["writes"] if write["role"] == "business"]
        write_paths = {write["path"] for write in tx["writes"]}
        read_paths = set(tx["read_preconditions"])
        if set(business_paths) != set(overlay):
            raise AssertionError("mixed inspected business writes differ from the complete overlay")
        if tx["claimed_inputs"] != [] or write_paths.intersection(read_paths):
            raise AssertionError("knowledge transaction claimed inputs or overlaps reads and writes")
        if tx["operation_type"] != "ingest" or tx["phase"] != "inspected":
            raise AssertionError("mixed transaction is not an inspected ingest")
        if tx != authority["upstream_authority"]["transaction"]:
            raise AssertionError("upstream and pinned mixed transaction authorities differ")

        applied = apply_publication(checkout, vault, authority)
        integrity_after = audit_integrity(vault)
        source_audit_after = audit_source_state(vault_root=vault)
        after_apply = vault_snapshot(vault)
        if source_audit_after["profile"] != "source-v1" or source_audit_after["counts"] != {
            "files": 57,
            "papers": 4,
            "repos": 1,
            "claims": 4,
            "events": 7,
            "associations": 1,
            "display_decisions": 0,
            "ledger_snapshots": 2,
            "compiled_pages": 6,
        }:
            raise AssertionError("post-apply mixed source-v1 counts differ")
        if not integrity_after["valid"] or integrity_after["classification"] != "receipt_backed":
            raise AssertionError("post-apply mixed receipt audit is not valid")

        # Existing raw bytes and immutable R1 semantic records survive the
        # mixed publication. Every proposed byte is also checked exactly.
        immutable_prefixes = (
            ".raw/captured/",
            ".raw/derived/",
            "wiki/meta/reviews/clm-",
            "wiki/meta/operations/",
        )
        for path, (raw, _mode) in before_prepare.items():
            if path.startswith(immutable_prefixes) and path in after_apply:
                if after_apply[path][0] != raw and path not in overlay:
                    raise AssertionError(f"existing immutable byte changed at {path}")
        for path, raw in overlay.items():
            if path not in after_apply or after_apply[path][0] != raw:
                raise AssertionError(f"applied mixed payload differs at {path}")

        receipt_path = next(write["path"] for write in tx["writes"] if write["role"] == "receipt")
        head_path = next(write["path"] for write in tx["writes"] if write["role"] == "head")
        actual_payloads = [
            put_json("actual/capture-authority.json", stable(capture_authority, tmp_name)),
            put_json("actual/capture-bound-result.json", stable(capture_bound, tmp_name)),
            put_json("actual/capture-applied-result.json", capture_applied),
            put_json("actual/admission-authority.json", stable(admission["publication_authority"], tmp_name)),
            put_json("actual/admission-applied-result.json", {
                "changed_paths": admission["publication_authority"]["transaction"]["writes"],
                "state": admission["state"],
                "published": admission["published"],
                "receipt_backed": admission["receipt_backed"],
            }),
            put_json("actual/integrity-before.json", audit_before),
            put_json("actual/source-audit-before.json", source_audit_before),
            put_json("actual/integrity-after.json", integrity_after),
            put_json("actual/source-audit-after.json", source_audit_after),
            put_json("actual/publication-authority.json", authority),
            put_json("actual/publication-applied-result.json", applied),
        ]
        external_files = [put("external/proposal.json", canonicalize(proposal))]
        external_files.extend(
            put(f"external/content/{h(raw)}", raw)
            for _path, raw in sorted(overlay.items(), key=lambda item: item[0].encode())
        )
        proposed_files = [
            put(f"proposed/{path}", raw)
            for path, raw in sorted(overlay.items(), key=lambda item: item[0].encode())
        ]

        result = {
            "schema": "video-paper-wiki.source-state-legacy-r2-mixed-probe-result.v1",
            "status": "validated_legacy_capture_registration_mixed_prepare_inspect_and_fixture_apply",
            "temporary_fixture_only": True,
            "source_tree": str(SOURCE),
            "source_tree_head": "c32e68d08a142d5a5559ce717ff397f9b27f55d1",
            "r1_baseline": {
                "profile": legacy_state["profile"],
                "counts": legacy_state["counts"],
            },
            "r2_inputs": {
                "result_sha256": r2_hashes["result_sha256"],
                "hashes_sha256": r2_hashes["hashes_sha256"],
                "original_payload_count": len(r2_payloads),
            },
            "capture": {
                "source_id": capture_authority["source_id"],
                "stored_path": capture_authority["stored_path"],
                "disposition": capture_authority["disposition"],
                "operation_id": capture_authority["requested_operation_id"],
                "bound_transaction_operation": capture_bound["transaction"]["operation_id"],
            },
            "modern_resealed": {
                "association_id": derived["association"]["association_id"],
                "association_path": derived["association_path"],
                "event_id": derived["event"]["event_id"],
                "event_path": derived["event_path"],
                "observation_path": derived["observation_path"],
                "raw_path": derived["raw_path"],
                "registration": derived["association"]["registration"],
            },
            "proposal": proposal,
            "prepared": stable(prepared, tmp_name),
            "authority_summary": {
                "request_sha256": authority["request_sha256"],
                "prospective_inventory_sha256": authority["prospective_inventory_sha256"],
                "operation_id": tx["operation_id"],
                "operation_type": tx["operation_type"],
                "phase": tx["phase"],
                "claimed_inputs": tx["claimed_inputs"],
                "business_paths": business_paths,
                "receipt_path": receipt_path,
                "head_path": head_path,
                "read_precondition_count": len(read_paths),
                "read_preconditions_sha256": sha(canonicalize(tx["read_preconditions"])),
            },
            "audit_before": source_audit_before,
            "audit_after": source_audit_after,
            "vault_before": snapshot_hashes(before_prepare),
            "vault_after": snapshot_hashes(after_apply),
            "checks": {
                "r1_legacy_baseline_preserved": legacy_state["profile"] == "legacy-v1" and legacy_state["counts"]["papers"] == 3,
                "actual_markdown_capture_and_bind": capture_authority["disposition"] == "create" and capture_bound["transaction"]["operation_type"] == "capture",
                "registration_preserved_legacy_structure": source_audit_before["profile"] == "legacy-v1",
                "r2_modern_payloads_resealed_against_mixed_chain": True,
                "external_proposal_canonical_and_retained": True,
                "prepare_no_vault_mutation": before_prepare == after_prepare,
                "inspect_no_vault_mutation": before_prepare == after_inspect,
                "complete_mixed_business_write_set": set(business_paths) == set(overlay),
                "knowledge_claimed_inputs_empty": tx["claimed_inputs"] == [],
                "read_write_sets_disjoint": not write_paths.intersection(read_paths),
                "upstream_transaction_identical": tx == authority["upstream_authority"]["transaction"],
                "fixture_only_operator_apply": True,
                "receipt_backed_after_apply": integrity_after["classification"] == "receipt_backed" and integrity_after["valid"],
                "source_v1_typed_audit_after_apply": source_audit_after["profile"] == "source-v1",
                "mixed_counts_complete": source_audit_after["counts"] == {
                    "files": 57, "papers": 4, "repos": 1, "claims": 4, "events": 7,
                    "associations": 1, "display_decisions": 0, "ledger_snapshots": 2, "compiled_pages": 6,
                },
                "raw_and_immutable_history_preserved": True,
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
        result_path = RESULT_DIR / "source-state-legacy-r2-mixed-probe-result.json"
        result_path.write_bytes(result_raw)
        print(json.dumps({
            "result": str(result_path),
            "result_sha256": h(result_raw),
            "result_size_bytes": len(result_raw),
            "payload_count": len(overlay),
            "business_write_count": len(business_paths),
            "post_profile": source_audit_after["profile"],
            "post_counts": source_audit_after["counts"],
        }, separators=(",", ":")))


def main() -> None:
    try:
        run()
    except BaseException as exc:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        failure = {
            "schema": "video-paper-wiki.source-state-legacy-r2-mixed-probe-result.v1",
            "status": "failed",
            **error_record(exc),
            "traceback": traceback.format_exc(),
        }
        (RESULT_DIR / "source-state-legacy-r2-mixed-probe-failure.json").write_bytes(canonicalize(failure))
        raise


if __name__ == "__main__":
    main()
