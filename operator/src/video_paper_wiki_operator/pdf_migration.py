"""Operator PDF migrate-apply, open, and rollback. No Drive upload."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.contracts import validate_document
from video_paper_wiki.pdf_locations import KIND_FORMAL, locations_bytes, sha256_bytes
from video_paper_wiki.pdf_migration import (
    PLAN_SCHEMA,
    PdfMigrationError,
    apply_plan_to_root,
    parse_roots,
    resolve_from_root,
    rollback_journal,
)
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki.staging import stage_bytes, validate_batch_id
from video_paper_wiki.transaction_staging import encode_transaction_inspect_bundle


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
    plan = validate_document(_load_json(plan_path), PLAN_SCHEMA)
    roots = parse_roots(_load_json(roots_path))
    root = next((row for row in roots if row["root_id"] == root_id), None)
    if root is None:
        raise PdfMigrationError("PDF_MIGRATION_INVALID", "root_id is not in roots.json", {"root_id": root_id})
    accepted = bool(confirm({"plan_sha256": plan["plan_sha256"], "root_id": root_id, "kind": root["kind"]}))
    if root["kind"] == KIND_FORMAL:
        if upstream_root is None:
            raise PdfMigrationError(
                "PDF_MIGRATION_INVALID",
                "formal-vault migrate-apply requires --upstream-root",
            )
        _stage_formal_bundle(plan, root, approved_plan_sha256)
    return apply_plan_to_root(
        plan=plan,
        roots=roots,
        root_id=root_id,
        approved_plan_sha256=approved_plan_sha256,
        confirm=accepted,
    )


def _stage_formal_bundle(plan: Mapping[str, Any], root: Mapping[str, Any], approved_plan_sha256: str) -> None:
    """Build a generic inspect bundle for receipt-backed formal vault writes."""

    writes = []
    expected = {}
    batch = validate_batch_id(plan["batch_id"])
    for item in plan["items"]:
        if item["root_id"] != root["root_id"]:
            continue
        loc_bytes = locations_bytes(item["location"])
        digest = sha256_bytes(loc_bytes)
        stage_bytes(batch_id=batch, relative=("pdf-migration", "content", digest), data=loc_bytes)
        mode = "create" if item["before_location_sha256"] is None else "replace"
        writes.append({"path": item["location_path"], "mode": mode, "sha256": digest})
        expected[item["location_path"]] = item["before_location_sha256"]
        if item["page_path"] and item["after_page_sha256"]:
            writes.append(
                {
                    "path": item["page_path"],
                    "mode": "create" if item["before_page_sha256"] is None else "replace",
                    "sha256": item["after_page_sha256"],
                }
            )
            expected[item["page_path"]] = item["before_page_sha256"]
    if not writes:
        return
    material = {
        "operation_id": "pdf-mig-" + plan["plan_sha256"][:12],
        "operation_type": "generic",
        "writes": writes,
        "expected_hashes": expected,
        "read_preconditions": {},
    }
    bundle = encode_transaction_inspect_bundle(material)
    stage_bytes(batch_id=batch, relative=("pdf-migration", "transaction-bundle.json"), data=bundle)
    stage_bytes(
        batch_id=batch,
        relative=("pdf-migration", "approved-plan-sha256.txt"),
        data=(approved_plan_sha256 + "\n").encode("utf-8"),
    )


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


def rollback_pdf(*, journal_path: Path, roots_path: Path, confirm) -> dict[str, Any]:
    accepted = bool(confirm({"journal": str(journal_path)}))
    return rollback_journal(journal_path=journal_path, roots_path=roots_path, confirm=accepted)
