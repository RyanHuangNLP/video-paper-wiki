"""Operator PDF migrate-apply, open, and rollback. No Drive upload."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.pdf_locations import KIND_FORMAL, locations_bytes, sha256_bytes
from video_paper_wiki.pdf_migration import (
    PDF_FORMAL_TRANSACTION_REQUIRED,
    PDF_MIGRATION_INVALID,
    PDF_UPSTREAM_INVALID,
    PLAN_SCHEMA,
    PdfMigrationError,
    apply_plan_to_root,
    derived_location_path,
    derived_page_path,
    parse_roots,
    resolve_from_root,
    rollback_journal,
    verify_approved_plan,
    verify_pinned_upstream_root,
    _atomic_write,
    _current_location_and_page,
    _file_sha,
    _journal_path,
    _next_page_bytes,
    _recheck_input_preconditions,
)
from video_paper_wiki.receipt_audit import HEAD as HEAD_PATH
from video_paper_wiki.receipt_audit import _Snapshot, audit_integrity
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki.staging import WORK_DIRNAME, _open_batch_session, resolve_checkout_root, validate_batch_id
from video_paper_wiki.transaction_contracts import (
    transaction_declaration_hash,
    validate_transaction,
    verify_transaction_bytes,
)
from video_paper_wiki.transaction_staging import (
    MAX_BUNDLE_BYTES,
    _stage_transaction_inspect_transport,
    encode_transaction_inspect_bundle,
)
from video_paper_wiki.upstream_adapter import inspect_pinned_transaction
from video_paper_wiki.transaction_contracts import attach_upstream_inspection


def _load_json(path: Path) -> Any:
    return parse_strict_json(Path(path).read_bytes(), invalid_code="PDF_MIGRATION_INVALID")


def apply_pdf_migration(
    *,
    plan_path: Path,
    roots_path: Path,
    root_id: str,
    approved_plan_sha256: str,
    upstream_root: Path | str | None,
    confirm,
) -> dict[str, Any]:
    plan = verify_approved_plan(_load_json(plan_path), approved_plan_sha256)
    roots = parse_roots(_load_json(roots_path))
    root = next((row for row in roots if row["root_id"] == root_id), None)
    if root is None:
        raise PdfMigrationError("PDF_MIGRATION_INVALID", "root_id is not in roots.json", {"root_id": root_id})
    accepted = bool(confirm({"plan_sha256": plan["plan_sha256"], "root_id": root_id, "kind": root["kind"]}))
    if root["kind"] == KIND_FORMAL:
        pinned = verify_pinned_upstream_root(upstream_root)
        if not accepted:
            raise PdfMigrationError(
                "HUMAN_APPROVAL_REQUIRED",
                "interactive confirmation is required",
                {"next_action": "confirm_interactively"},
            )
        return apply_formal_vault_plan(
            plan=plan,
            roots=roots,
            root=root,
            approved_plan_sha256=approved_plan_sha256,
            upstream_root=pinned,
        )
    if upstream_root not in {None, ""}:
        try:
            verify_pinned_upstream_root(upstream_root)
        except PdfMigrationError as exc:
            if exc.code in {PDF_UPSTREAM_INVALID, "PDF_UPSTREAM_REQUIRED"}:
                raise
    return apply_plan_to_root(
        plan=plan,
        roots=roots,
        root_id=root_id,
        approved_plan_sha256=approved_plan_sha256,
        confirm=accepted,
    )


def _payload_bytes_for_root(plan: Mapping[str, Any], root: Mapping[str, Any]) -> dict[str, bytes]:
    payload: dict[str, bytes] = {}
    for item in plan["items"]:
        if item["root_id"] != root["root_id"]:
            continue
        loc_rel = derived_location_path(root["kind"], item["paper_id"])
        loc_bytes = locations_bytes(item["location"])
        if sha256_bytes(loc_bytes) != item["after_location_sha256"]:
            raise PdfMigrationError(PDF_MIGRATION_INVALID, "planned location bytes do not match after digest")
        payload[loc_rel] = loc_bytes
        if item["page_path"] and item["after_page_sha256"]:
            page_rel, page_bytes = _next_page_bytes(root, item["paper_id"], item["location"])
            if page_rel is None or page_bytes is None or sha256_bytes(page_bytes) != item["after_page_sha256"]:
                raise PdfMigrationError(
                    "PDF_APPLY_CHANGED",
                    "page bytes changed and cannot be rewritten safely",
                    {"item_id": item["item_id"]},
                )
            payload[page_rel] = page_bytes
    return payload


def _assemble_and_inspect(
    *,
    plan: Mapping[str, Any],
    root: Mapping[str, Any],
    payload_bytes: dict[str, bytes],
    upstream_root: Path,
    operation_id: str,
) -> dict[str, Any]:
    vault = Path(root["path"])
    checkout = resolve_checkout_root()
    batch = validate_batch_id(plan["batch_id"])
    snapshot = _Snapshot(vault)
    try:
        head_raw = snapshot.read_optional(HEAD_PATH, max_bytes=1024 * 1024)
        if head_raw is None:
            audit = {"head": None}
        else:
            try:
                audit = audit_integrity(vault, _snapshot=snapshot)
            except ContractError as exc:
                if exc.code != "RECEIPT_BOOTSTRAP_REQUIRED":
                    raise
                audit = {"head": None}
        with _open_batch_session(batch, create=True) as session:
            assembled = _assemble_generic_transaction(
                operation_id=operation_id,
                operation_type="generic",
                batch=batch,
                payload_bytes=payload_bytes,
                claimed_input_paths=[],
                read_bytes={},
                audit=audit,
                snapshot=snapshot,
                session=session,
                upstream_root=upstream_root,
                checkout=checkout,
                vault=vault,
            )
    finally:
        if hasattr(snapshot, "close"):
            snapshot.close()
        elif hasattr(snapshot, "root_fd"):
            try:
                os.close(snapshot.root_fd)
            except OSError:
                pass
    return assembled


def _assemble_generic_transaction(
    *,
    operation_id,
    operation_type,
    batch,
    payload_bytes,
    claimed_input_paths,
    read_bytes,
    audit,
    snapshot,
    session,
    upstream_root,
    checkout,
    vault,
) -> dict[str, Any]:
    sequence = 1 if audit["head"] is None else audit["head"]["sequence"] + 1
    old_head_bytes = None if sequence == 1 else snapshot.read(HEAD_PATH, max_bytes=1024 * 1024)
    old_head_stat = None if sequence == 1 else snapshot.files[HEAD_PATH][0]
    business = []
    original: dict[str, bytes | None] = {}
    expected: dict[str, str | None] = {}
    mutable_payload = dict(payload_bytes)
    for path, data in sorted(mutable_payload.items()):
        try:
            old = snapshot.read_optional(path)
            if old is None:
                raise FileNotFoundError
            old_st = snapshot.files[path][0]
            mode = "replace"
            before = hashlib.sha256(old).hexdigest()
            original[path] = old
            original_mode = stat.S_IMODE(old_st.st_mode)
            original_size = len(old)
        except FileNotFoundError:
            mode = "create"
            before = None
            original[path] = None
            original_mode = None
            original_size = 0
        digest = hashlib.sha256(data).hexdigest()
        expected[path] = before
        business.append(
            {
                "path": path,
                "role": "business",
                "mode": mode,
                "sha256": digest,
                "size_bytes": len(data),
                "original_size_bytes": original_size,
                "original_mode": original_mode,
            }
        )
    claims = [
        {"path": path, "mode": "read", "sha256": hashlib.sha256(read_bytes[path]).hexdigest()}
        for path in claimed_input_paths
    ]
    previous = None if sequence == 1 else {"path": audit["head"]["receipt_path"], "sha256": audit["head"]["receipt_sha256"]}
    receipt = {
        "schema": "video-paper-wiki.operation-receipt.v1",
        "sequence": sequence,
        "previous": previous,
        "operation_id": operation_id,
        "operation_type": operation_type,
        "intent_sha256": "0" * 64,
        "writes": [
            {
                "path": item["path"],
                "mode": item["mode"],
                "before_sha256": expected[item["path"]],
                "after_sha256": item["sha256"],
            }
            for item in business
        ],
        "claimed_inputs": claims,
    }
    receipt["intent_sha256"] = receipt_intent_sha256(receipt)
    receipt_path = f"wiki/meta/operations/{sequence:012d}-{operation_id}.json"
    receipt_raw = canonicalize(receipt)
    head = {
        "schema": "video-paper-wiki.operation-head.v1",
        "sequence": sequence,
        "receipt_path": receipt_path,
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
    }
    head_raw = canonicalize(head)
    for path, data, role in ((receipt_path, receipt_raw, "receipt"), (HEAD_PATH, head_raw, "head")):
        old = None if sequence == 1 or role == "receipt" else old_head_bytes
        business.append(
            {
                "path": path,
                "role": role,
                "mode": "create" if old is None else "replace",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "original_size_bytes": len(old or b""),
                "original_mode": None if old is None else stat.S_IMODE(old_head_stat.st_mode),
            }
        )
        expected[path] = None if old is None else hashlib.sha256(old).hexdigest()
        original[path] = old
        mutable_payload[path] = data
    read_hashes = {path: hashlib.sha256(value).hexdigest() for path, value in read_bytes.items()}
    material = {
        "operation_id": operation_id,
        "operation_type": operation_type,
        "writes": [{key: item[key] for key in ("path", "mode", "sha256")} for item in business],
        "expected_hashes": expected,
        "read_preconditions": read_hashes,
    }
    bundle = encode_transaction_inspect_bundle(material)
    if len(bundle) > MAX_BUNDLE_BYTES:
        raise ContractError("TRANSACTION_LIMIT_EXCEEDED", "bundle exceeds limit")
    proposal = {
        "schema": "video-paper-wiki.transaction-facade.v1",
        "phase": "proposal",
        "operation_id": operation_id,
        "operation_type": operation_type,
        "writes": business,
        "expected_hashes": expected,
        "read_preconditions": read_hashes,
        "claimed_inputs": claims,
        "address_requests": [],
        "source_manifest_updates": {},
        "engine_expanded_paths": [],
        "receipt": receipt,
        "head": head,
        "input_bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "declaration_sha256": "0" * 64,
        "inspection": None,
        "runtime_result": None,
    }
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    proposal = validate_transaction(proposal)
    verify_transaction_bytes(proposal, write_bytes=mutable_payload, original_bytes=original, read_bytes=read_bytes)
    staging = _stage_transaction_inspect_transport(
        proposal,
        write_bytes=mutable_payload,
        original_bytes=original,
        read_bytes=read_bytes,
        batch_id=batch,
        session=session,
    )
    bundle_path = checkout / WORK_DIRNAME / batch / "transaction-inspect" / "bundle.json"
    upstream = inspect_pinned_transaction(
        proposal,
        upstream_root=upstream_root,
        work_root=checkout / WORK_DIRNAME,
        vault_root=vault,
        bundle_path=bundle_path,
    )
    tx = attach_upstream_inspection(proposal, upstream["transaction"]["inspection"])
    return {
        "transaction": tx,
        "transaction_staging": staging,
        "upstream_authority": upstream,
        "bundle_path": bundle_path,
        "receipt": receipt,
        "receipt_path": receipt_path,
        "payload_bytes": mutable_payload,
    }


def _run_upstream_apply(*, upstream_root: Path, bundle_path: Path, vault: Path, approval_sha256: str) -> dict[str, Any]:
    child = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            "utf8",
            str(upstream_root / "scripts" / "claude-obsidian.py"),
            "transaction",
            "apply",
            str(bundle_path),
            "--vault",
            str(vault),
            "--approved-plan-sha256",
            approval_sha256,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if child.returncode != 0:
        detail = child.stderr.decode("utf-8", errors="replace") or child.stdout.decode("utf-8", errors="replace")
        raise PdfMigrationError(
            PDF_FORMAL_TRANSACTION_REQUIRED,
            "pinned upstream transaction apply failed",
            {"returncode": child.returncode, "detail": detail[:1024]},
        )
    try:
        return json.loads(child.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PdfMigrationError(PDF_MIGRATION_INVALID, "upstream apply returned invalid JSON") from exc


def apply_formal_vault_plan(
    *,
    plan: Mapping[str, Any],
    roots: list[Mapping[str, Any]],
    root: Mapping[str, Any],
    approved_plan_sha256: str,
    upstream_root: Path,
) -> dict[str, Any]:
    verify_approved_plan(plan, approved_plan_sha256)
    for item in plan["items"]:
        if item["root_id"] != root["root_id"]:
            continue
        _recheck_input_preconditions(roots=roots, preconditions=item.get("input_preconditions"))
        loc_rel = derived_location_path(root["kind"], item["paper_id"])
        if item["location_path"] != loc_rel:
            raise PdfMigrationError(
                "PDF_LOCATION_INVALID",
                "plan location_path does not match the derived identity path",
                {"planned": item["location_path"], "derived": loc_rel},
            )
        if item["page_path"]:
            expected_page = derived_page_path(root["kind"], item["paper_id"])
            if item["page_path"] != expected_page:
                raise PdfMigrationError(
                    "PDF_LOCATION_INVALID",
                    "plan page_path does not match the derived identity path",
                    {"planned": item["page_path"], "derived": expected_page},
                )
    payload = _payload_bytes_for_root(plan, root)
    if not payload:
        raise PdfMigrationError(PDF_MIGRATION_INVALID, "formal-vault plan has no writes for this root")
    journal_path = _journal_path(Path(root["path"]), plan["plan_sha256"])
    backup_dir = journal_path.parent / "backups"
    intent_entries = []
    for item in plan["items"]:
        if item["root_id"] != root["root_id"]:
            continue
        intent_entries.append(
            {
                "item_id": item["item_id"],
                "location_path": item["location_path"],
                "page_path": item["page_path"],
                "before_location_sha256": item["before_location_sha256"],
                "after_location_sha256": item["after_location_sha256"],
                "before_page_sha256": item["before_page_sha256"],
                "after_page_sha256": item["after_page_sha256"],
            }
        )
        for rel, before in (
            (item["location_path"], item["before_location_sha256"]),
            (item["page_path"], item["before_page_sha256"]),
        ):
            if not rel:
                continue
            live = Path(root["path"]) / rel
            if live.is_file() and not live.is_symlink():
                backup_dir.mkdir(parents=True, exist_ok=True)
                _atomic_write(backup_dir / sha256_json_safe(rel, before), live.read_bytes())
    intent_journal = {
        "schema": "video-paper-wiki.pdf-migration-journal.internal.v1",
        "plan_sha256": plan["plan_sha256"],
        "root_id": root["root_id"],
        "kind": KIND_FORMAL,
        "receipt_path": None,
        "intent": intent_entries,
        "entries": [],
    }
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(journal_path, canonicalize(intent_journal) + b"\n")
    operation_id = "pdf-mig-" + plan["plan_sha256"][:12]
    assembled = _assemble_and_inspect(
        plan=plan,
        root=root,
        payload_bytes=payload,
        upstream_root=upstream_root,
        operation_id=operation_id,
    )
    content_files = assembled["transaction_staging"]["content_files"]
    page_paths = [path for path in payload if path.startswith("wiki/papers/")]
    if page_paths:
        page_digests = {sha256_bytes(payload[path]) for path in page_paths}
        staged_digests = {item["sha256"] for item in content_files}
        if not page_digests <= staged_digests:
            raise PdfMigrationError(PDF_MIGRATION_INVALID, "formal transaction bundle is missing page content files")
    approval = assembled["transaction"]["inspection"]["approval_sha256"]
    applied = _run_upstream_apply(
        upstream_root=upstream_root,
        bundle_path=assembled["bundle_path"],
        vault=Path(root["path"]),
        approval_sha256=approval,
    )
    receipt_path = assembled["receipt_path"]
    if not (Path(root["path"]) / receipt_path).is_file():
        raise PdfMigrationError(PDF_FORMAL_TRANSACTION_REQUIRED, "formal apply did not produce a receipt")
    journal = {
        "schema": "video-paper-wiki.pdf-migration-journal.internal.v1",
        "plan_sha256": plan["plan_sha256"],
        "root_id": root["root_id"],
        "kind": KIND_FORMAL,
        "receipt_path": receipt_path,
        "receipt_sha256": assembled["receipt"]["intent_sha256"],
        "intent": [
            {
                "item_id": item["item_id"],
                "location_path": item["location_path"],
                "page_path": item["page_path"],
                "before_location_sha256": item["before_location_sha256"],
                "after_location_sha256": item["after_location_sha256"],
                "before_page_sha256": item["before_page_sha256"],
                "after_page_sha256": item["after_page_sha256"],
            }
            for item in plan["items"]
            if item["root_id"] == root["root_id"]
        ],
        "entries": [
            {
                "item_id": item["item_id"],
                "path": path,
                "before_sha256": item["before_location_sha256"] if path == item["location_path"] else item["before_page_sha256"],
                "after_sha256": item["after_location_sha256"] if path == item["location_path"] else item["after_page_sha256"],
            }
            for item in plan["items"]
            if item["root_id"] == root["root_id"]
            for path in ((item["location_path"],) + ((item["page_path"],) if item["page_path"] else ()))
        ],
    }
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(journal_path, canonicalize(journal) + b"\n")
    results = []
    for item in plan["items"]:
        if item["root_id"] != root["root_id"]:
            continue
        state = "unverified" if item["verification"] == "unverified" else "linked"
        results.append({"item_id": item["item_id"], "state": state, "code": None})
    return {
        "root_id": root["root_id"],
        "kind": KIND_FORMAL,
        "plan_sha256": plan["plan_sha256"],
        "journal_path": str(journal_path),
        "journal_sha256": sha256_bytes(journal_path.read_bytes()),
        "receipt_path": receipt_path,
        "upstream_apply": applied,
        "results": results,
        "keep_local": True,
    }


def open_pdf(*, roots_path: Path, root_id: str, paper_id: str, prefer: str, offline: bool, pdf_sha256: str | None) -> dict[str, Any]:
    resolved = resolve_from_root(
        roots_path=roots_path,
        root_id=root_id,
        paper_id=paper_id,
        prefer=prefer,
        offline=offline,
        pdf_sha256=pdf_sha256,
    )
    target = resolved["target"]
    if resolved["target_kind"] == "local":
        opened = webbrowser.open(Path(target).resolve().as_uri())
    else:
        opened = webbrowser.open(str(target))
    resolved["open_submitted"] = True
    resolved["browser_accepted"] = bool(opened)
    resolved["message"] = "open request submitted"
    return resolved


def sha256_json_safe(path: str, before: str) -> str:
    from video_paper_wiki.pdf_locations import sha256_json

    return sha256_json({"path": path, "before": before})


def rollback_formal_vault(*, journal: Mapping[str, Any], root: Mapping[str, Any], upstream_root: Path, plan: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = {}
    base = Path(root["path"])
    journal_path = Path(journal.get("path") or "")
    backup_dir = journal_path.parent / "backups" if journal_path else base / ".work" / "pdf-migration" / "backups"
    for entry in journal.get("entries") or []:
        if entry.get("path") in {journal.get("receipt_path"), HEAD_PATH}:
            continue
        if entry.get("path", "").startswith("wiki/meta/operations/"):
            continue
        current = _file_sha(base / entry["path"])
        if current != entry.get("after_sha256"):
            raise PdfMigrationError("PDF_ROLLBACK_CONFLICT", "rollback found later edits", {"path": entry["path"]})
        before = entry.get("before_sha256")
        if before is None:
            raise PdfMigrationError(
                "PDF_ROLLBACK_CONFLICT",
                "formal compensating rollback cannot delete a created file through the generic write modes",
                {"path": entry["path"]},
            )
        backup = backup_dir / sha256_json_safe(entry["path"], before)
        if not backup.is_file():
            raise PdfMigrationError("PDF_ROLLBACK_CONFLICT", "compensating backup is missing", {"path": entry["path"]})
        data = backup.read_bytes()
        if sha256_bytes(data) != before:
            raise PdfMigrationError("PDF_ROLLBACK_CONFLICT", "compensating backup digest differs", {"path": entry["path"]})
        payload[entry["path"]] = data
    if not payload:
        raise PdfMigrationError(PDF_MIGRATION_INVALID, "formal rollback has no replaceable writes")
    batch = validate_batch_id((plan or {}).get("batch_id") or "pdf-rollback")
    operation_id = "pdf-rb-" + (journal.get("plan_sha256") or "x" * 12)[:12]
    fake_plan = {"batch_id": batch, "items": [], "plan_sha256": journal.get("plan_sha256") or "0" * 64}
    assembled = _assemble_and_inspect(
        plan=fake_plan,
        root=root,
        payload_bytes=payload,
        upstream_root=upstream_root,
        operation_id=operation_id,
    )
    approval = assembled["transaction"]["inspection"]["approval_sha256"]
    applied = _run_upstream_apply(
        upstream_root=upstream_root,
        bundle_path=assembled["bundle_path"],
        vault=base,
        approval_sha256=approval,
    )
    return {
        "restored": sorted(payload),
        "keep_local": True,
        "drive_unchanged": True,
        "receipt_path": assembled["receipt_path"],
        "compensating": True,
        "upstream_apply": applied,
    }


def rollback_pdf(*, journal_path: Path, roots_path: Path, confirm, upstream_root: Path | str | None = None) -> dict[str, Any]:
    accepted = bool(confirm({"journal": str(journal_path)}))
    journal = _load_json(journal_path)
    journal["path"] = str(journal_path)
    roots = parse_roots(_load_json(roots_path))
    root = next((row for row in roots if row["root_id"] == journal.get("root_id")), None)
    if root is None:
        raise PdfMigrationError(PDF_MIGRATION_INVALID, "journal root_id is not in roots.json")
    if root["kind"] == KIND_FORMAL or journal.get("kind") == KIND_FORMAL or journal.get("receipt_path"):
        if not accepted:
            raise PdfMigrationError("HUMAN_APPROVAL_REQUIRED", "interactive confirmation is required")
        pinned = verify_pinned_upstream_root(upstream_root)
        return rollback_formal_vault(journal=journal, root=root, upstream_root=pinned, plan=None)
    return rollback_journal(journal_path=journal_path, roots_path=roots_path, confirm=accepted)
