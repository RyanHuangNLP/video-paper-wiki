"""PDF inventory, link-plan, writeset apply, report, and rollback. No Drive upload."""

from __future__ import annotations

import ctypes
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.pdf_locations import (
    CACHE_POLICY,
    DRIVE_A_ROOT_FOLDER_ID,
    HEX64,
    KIND_CACHE,
    KIND_FORMAL,
    KIND_NOTES,
    KIND_REPO,
    KIND_RESEARCH,
    MEDIA_PDF,
    PDF_CONTENT_CONFLICT,
    PDF_HEADING,
    PDF_LOCATION_INVALID,
    PdfLocationError,
    ROOT_LAYOUT_MISMATCH,
    UNVERIFIED,
    VERIFIED,
    build_locations_document,
    build_pdf_entry,
    canonical_paper_id,
    category_for_paper,
    derived_location_path,
    derived_page_path,
    drive_relative_path,
    hash_file,
    is_portable_drive_relative_path,
    is_portable_relative_path,
    is_pdf_bytes,
    item_id_for,
    load_locations_file,
    location_relative_path,
    locations_bytes,
    merge_local_ref,
    paper_dir_for,
    parse_roots,
    render_pdf_section,
    render_pdf_section_lines,
    resolve_inside_root,
    root_directory_identity,
    roots_digest,
    roots_map,
    same_drive_link,
    seed_alias,
    sha256_bytes,
    sha256_json,
    validate_locations,
)
from video_paper_wiki.receipt_audit import HEAD as OPERATION_HEAD_PATH
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki.staging import stage_bytes, validate_batch_id

INVENTORY_SCHEMA = "video-paper-wiki.pdf-migration-inventory.v1"
MANIFEST_SCHEMA = "video-paper-wiki.pdf-upload-manifest.v1"
PLAN_SCHEMA = "video-paper-wiki.pdf-link-plan.v1"
REPORT_SCHEMA = "video-paper-wiki.pdf-migration-report.v1"
PDF_MIGRATION_INVALID = "PDF_MIGRATION_INVALID"
PDF_APPLY_CHANGED = "PDF_APPLY_CHANGED"
PDF_APPLY_EXCHANGE_UNAVAILABLE = "PDF_APPLY_EXCHANGE_UNAVAILABLE"
PDF_ROLLBACK_CONFLICT = "PDF_ROLLBACK_CONFLICT"
PLAN_HASH_MISMATCH = "PLAN_HASH_MISMATCH"
HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
PDF_FORMAL_TRANSACTION_REQUIRED = "PDF_FORMAL_TRANSACTION_REQUIRED"
PDF_UPSTREAM_REQUIRED = "PDF_UPSTREAM_REQUIRED"
PDF_UPSTREAM_INVALID = "PDF_UPSTREAM_INVALID"
INVENTORY_SHA256_REQUIRED = "INVENTORY_SHA256_REQUIRED"
INTAKE_ONLY = "intake-only"
MANIFEST_DRAFT_SCHEMA = "video-paper-wiki.pdf-upload-manifest.v1-draft"
UPSTREAM_PIN = "9f8c1199047eac2c3828496279fbb7ba9540b90b"
EXCLUDED_MARKERS = (
    "/tests/fixtures/",
    "/artifacts/verification/",
    "/.git/",
    "/node_modules/",
)
WORK_BLOBS = ".work/blobs"
LOCK_NAME = ".pdf-migration.lock"
JOURNAL_SCHEMA = "video-paper-wiki.pdf-migration-journal.internal.v1"
RECEIPT_SCHEMA = "video-paper-wiki.operation-receipt.v1"
HEAD_SCHEMA = "video-paper-wiki.operation-head.v1"
TRUSTED_REGISTRATION_PREFIXES = ("wiki/meta/records/", "wiki/meta/ledgers/")


class PdfMigrationError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


def _fail(code: str, message: str, details: dict[str, Any] | None = None, *, exit_code: int = 2) -> None:
    raise PdfMigrationError(code, message, details, exit_code=exit_code)


def _load_json(path: Path) -> Any:
    raw = Path(path).read_bytes()
    return parse_strict_json(raw, invalid_code=PDF_MIGRATION_INVALID)


def _write_staged_json(batch_id: str, name: str, document: Mapping[str, Any]) -> Path:
    data = canonicalize(document)
    result = stage_bytes(batch_id=batch_id, relative=("pdf-migration", name), data=data)
    return result.path


def plan_content_digest(plan: Mapping[str, Any]) -> str:
    return sha256_json({key: value for key, value in plan.items() if key != "plan_sha256"})


def bind_plan_digest(plan: dict[str, Any]) -> dict[str, Any]:
    plan["plan_sha256"] = plan_content_digest(plan)
    return plan


def verify_approved_plan(plan: Mapping[str, Any], approved_plan_sha256: str) -> dict[str, Any]:
    if type(plan) is not dict:
        _fail(PDF_MIGRATION_INVALID, "plan must be an object")
    recomputed = plan_content_digest(plan)
    reported = plan.get("plan_sha256")
    if approved_plan_sha256 != recomputed or reported != recomputed:
        _fail(
            PLAN_HASH_MISMATCH,
            "approved-plan-sha256 does not match the recomputed plan content digest",
            {
                "approved_plan_sha256": approved_plan_sha256,
                "plan_sha256": reported,
                "recomputed_plan_sha256": recomputed,
            },
        )
    return validate_document(plan, PLAN_SCHEMA)


def resolve_apply_root(
    *,
    plan: Mapping[str, Any],
    roots: list[Mapping[str, Any]],
    root_id: str,
) -> dict[str, Any]:
    """Shared target identity, role, and roots-binding checks for both apply paths."""

    root = next((row for row in roots if row["root_id"] == root_id), None)
    if root is None:
        _fail(PDF_MIGRATION_INVALID, "root_id is not in roots.json", {"root_id": root_id})
    if root["role"] != "target":
        _fail(PDF_MIGRATION_INVALID, "apply requires a target root")
    if roots_digest(roots) != plan["roots_sha256"]:
        _fail(PDF_APPLY_CHANGED, "roots.json identity changed after prepare")
    return dict(root)


def item_writeset_after(item: Mapping[str, Any]) -> dict[str, str]:
    after: dict[str, str] = {}
    location_path = item.get("location_path")
    after_location = item.get("after_location_sha256")
    if type(location_path) is str and type(after_location) is str:
        after[location_path] = after_location
    page_path = item.get("page_path")
    after_page = item.get("after_page_sha256")
    if type(page_path) is str and type(after_page) is str:
        after[page_path] = after_page
    return after


def assert_item_identity_paths(root: Mapping[str, Any], item: Mapping[str, Any]) -> None:
    loc_rel = derived_location_path(root["kind"], item["paper_id"])
    if item["location_path"] != loc_rel:
        _fail(
            PDF_LOCATION_INVALID,
            "plan location_path does not match the derived identity path",
            {"planned": item["location_path"], "derived": loc_rel, "item_id": item["item_id"]},
        )
    planned_page = item.get("page_path")
    if planned_page:
        expected_page = derived_page_path(root["kind"], item["paper_id"])
        if planned_page != expected_page:
            _fail(
                PDF_LOCATION_INVALID,
                "plan page_path does not match the derived identity path",
                {"planned": planned_page, "derived": expected_page, "item_id": item["item_id"]},
            )


def inspect_item_apply_state(root: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    """Return 'done' or 'pending'. Refuse if live bytes are not the approved before/after."""

    assert_item_identity_paths(root, item)
    base = Path(root["path"])
    loc_rel = item["location_path"]
    loc_path = resolve_inside_root(base, loc_rel)
    current_loc = _file_sha(loc_path)
    page_rel = item["page_path"]
    page_needed = bool(page_rel and item["after_page_sha256"])
    page_path = resolve_inside_root(base, page_rel) if page_rel else None
    current_page = _file_sha(page_path) if page_path is not None else None
    loc_done = current_loc == item["after_location_sha256"]
    page_done = (not page_needed) or current_page == item["after_page_sha256"]
    if loc_done and page_done:
        return "done"
    if current_loc not in {item["before_location_sha256"], None, item["after_location_sha256"]}:
        _fail(
            PDF_APPLY_CHANGED,
            "location file changed after prepare",
            {"path": loc_rel, "item_id": item["item_id"]},
        )
    if item["before_location_sha256"] is not None and current_loc is None:
        _fail(
            PDF_APPLY_CHANGED,
            "location file disappeared after prepare",
            {"path": loc_rel, "item_id": item["item_id"]},
        )
    if page_needed and current_page not in {item["before_page_sha256"], None, item["after_page_sha256"]}:
        _fail(
            PDF_APPLY_CHANGED,
            "page file changed after prepare",
            {"path": page_rel, "item_id": item["item_id"]},
        )
    if page_needed and item["before_page_sha256"] is not None and current_page is None:
        _fail(
            PDF_APPLY_CHANGED,
            "page file disappeared after prepare",
            {"path": page_rel, "item_id": item["item_id"]},
        )
    return "pending"


def verify_pinned_upstream_root(raw: Path | str | None) -> Path:
    import subprocess

    if raw is None or not str(raw).strip():
        _fail(PDF_UPSTREAM_REQUIRED, "formal-vault migrate-apply requires --upstream-root")
    root = Path(raw).resolve()
    if not root.is_dir():
        _fail(PDF_UPSTREAM_INVALID, "upstream_root is not a directory", {"path": str(root)})
    base = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "--no-optional-locks",
        "--no-replace-objects",
        "-C",
        str(root),
    ]
    try:
        head = subprocess.run(
            [*base, "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            [*base, "status", "--porcelain=v1", "--untracked-files=all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        _fail(PDF_UPSTREAM_INVALID, "upstream root cannot be authenticated", {"path": str(root)})
    if head != UPSTREAM_PIN or dirty:
        _fail(
            PDF_UPSTREAM_INVALID,
            "upstream root does not match the clean pinned checkout",
            {"path": str(root), "head": head},
        )
    return root


def _file_sha(path: Path) -> str | None:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return None
    digest, _size = hash_file(path)
    return digest


def _portable_rel(root: Path, path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    if rel.startswith("..") or rel == ".":
        return None
    return rel


def _looks_like_digest(value: object) -> bool:
    return type(value) is str and HEX64.fullmatch(value) is not None


def _json_paper_digest_pairs(document: object) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    stack: list[Any] = [document]
    seen: set[int] = set()
    while stack:
        value = stack.pop()
        if type(value) is dict:
            if id(value) in seen:
                continue
            seen.add(id(value))
            paper = value.get("paper_id")
            digest = value.get("pdf_sha256")
            source = value.get("source") if type(value.get("source")) is dict else {}
            if not _looks_like_digest(digest):
                digest = source.get("sha256")
            if type(paper) is str and _looks_like_digest(digest):
                try:
                    pairs.append((canonical_paper_id(paper), digest))
                except PdfLocationError:
                    pass
            stack.extend(value.values())
        elif type(value) is list:
            if id(value) in seen:
                continue
            seen.add(id(value))
            stack.extend(value)
    return pairs


def _is_trusted_registration_rel(rel: str) -> bool:
    posix = rel.replace("\\", "/")
    if posix.startswith(".work/") or "/.work/" in posix:
        return False
    if posix.startswith(TRUSTED_REGISTRATION_PREFIXES):
        return True
    if posix.startswith("papers/") and posix.endswith(".json"):
        return True
    return False


def _collect_registration_digests(base: Path, root_id: str) -> dict[str, list[dict[str, str]]]:
    """Map pdf_sha256 -> trusted registration bindings. Intake/staging under .work is not proof."""

    mapped: dict[str, list[dict[str, str]]] = {}
    search_roots = [
        base / "wiki" / "meta" / "records",
        base / "wiki" / "meta" / "ledgers",
        base / "papers",
    ]
    for search in search_roots:
        if not search.exists() or search.is_symlink():
            continue
        for path in sorted(search.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.casefold() != ".json":
                continue
            try:
                document = _load_json(path)
            except (OSError, ContractError, UnicodeError, PdfMigrationError):
                continue
            rel = _portable_rel(base, path)
            if rel is None or not _is_trusted_registration_rel(rel):
                continue
            digest_of_record = sha256_bytes(path.read_bytes())
            for paper_id, digest in _json_paper_digest_pairs(document):
                binding = _binding(root_id, paper_id, rel, digest_of_record)
                rows = mapped.setdefault(digest, [])
                if binding not in rows:
                    rows.append(binding)
    return mapped


def adapt_uploaded_manifest(raw: object) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize agy draft field names. Does not invent inventory_sha256."""

    if type(raw) is not dict:
        _fail(PDF_MIGRATION_INVALID, "uploaded-manifest must be an object")
    document = dict(raw)
    schema = document.get("schema")
    if schema not in {MANIFEST_SCHEMA, MANIFEST_DRAFT_SCHEMA}:
        _fail(PDF_MIGRATION_INVALID, "uploaded-manifest schema is not recognized", {"schema": schema})
    if "drive_root_folder_id" not in document and "root_folder_id" in document:
        document["drive_root_folder_id"] = document.pop("root_folder_id")
    if "entries" not in document and "items" in document:
        document["entries"] = document.pop("items")
    extras: list[dict[str, Any]] = []
    normalized_entries: list[dict[str, Any]] = []
    entries = document.get("entries")
    if type(entries) is not list:
        _fail(PDF_MIGRATION_INVALID, "uploaded-manifest entries must be an array")
    allowed = {
        "item_id",
        "result",
        "drive_file_id",
        "drive_url",
        "root_folder_id",
        "parent_chain",
        "drive_relative_path",
        "remote_size_bytes",
        "remote_pdf_sha256",
        "verified_at",
        "error",
    }
    for entry in entries:
        if type(entry) is not dict:
            _fail(PDF_MIGRATION_INVALID, "uploaded-manifest entry must be an object")
        row = dict(entry)
        extras.append(
            {
                "item_id": row.get("item_id"),
                "paper_id": row.pop("paper_id", None),
                "local_pdf_sha256": row.pop("local_pdf_sha256", None),
            }
        )
        chain = row.get("parent_chain")
        if type(chain) is list:
            parents = []
            for node in chain:
                if type(node) is not dict:
                    continue
                folder_id = node.get("folder_id") or node.get("id")
                name = node.get("name") or node.get("title")
                if type(folder_id) is str and type(name) is str:
                    parents.append({"folder_id": folder_id, "name": name})
            row["parent_chain"] = parents
        original_item_id = row.get("item_id")
        seed, seed_digest = _parse_draft_item_key(original_item_id)
        if seed and seed_digest:
            paper = extras[-1].get("paper_id") or seed
            digest = extras[-1].get("local_pdf_sha256")
            if type(digest) is not str or HEX64.fullmatch(digest) is None:
                digest = row.get("remote_pdf_sha256")
            if type(digest) is not str or HEX64.fullmatch(digest) is None:
                digest = seed_digest
            rel = row.get("drive_relative_path")
            if type(rel) is not str:
                rel = ""
            try:
                row["item_id"] = item_id_for(paper_id=str(paper), pdf_sha256=digest, drive_relative_path=rel)
            except PdfLocationError:
                row["item_id"] = seed_digest
        normalized_entries.append({key: row[key] for key in allowed if key in row})
    document["entries"] = normalized_entries
    document["schema"] = MANIFEST_SCHEMA
    for key in list(document):
        if key not in {"schema", "inventory_sha256", "drive_root_folder_id", "entries"}:
            document.pop(key, None)
    return document, extras


def load_uploaded_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = _load_json(path)
    adapted, extras = adapt_uploaded_manifest(raw)
    digest = adapted.get("inventory_sha256")
    if digest is None or digest == "" or not (type(digest) is str and HEX64.fullmatch(digest)):
        _fail(
            INVENTORY_SHA256_REQUIRED,
            "uploaded-manifest inventory_sha256 is required and must be a 64-hex digest",
            {"inventory_sha256": digest},
        )
    return validate_document(adapted, MANIFEST_SCHEMA), extras


def _parse_draft_item_key(item_id: object) -> tuple[str | None, str | None]:
    if type(item_id) is not str or ":" not in item_id:
        return None, None
    seed, digest = item_id.rsplit(":", 1)
    if not HEX64.fullmatch(digest):
        return None, None
    try:
        return canonical_paper_id(seed), digest
    except PdfLocationError:
        return None, None


def _match_inventory_item(
    *,
    entry: Mapping[str, Any],
    extra: Mapping[str, Any] | None,
    by_id: Mapping[str, dict[str, Any]],
    by_paper_digest: Mapping[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    item = by_id.get(entry["item_id"])
    if item is not None:
        return item
    paper = extra.get("paper_id") if extra else None
    digest = extra.get("local_pdf_sha256") if extra else None
    if type(digest) is not str or not HEX64.fullmatch(digest):
        digest = entry.get("remote_pdf_sha256")
    if type(paper) is str:
        try:
            found = by_paper_digest.get((canonical_paper_id(paper), digest if type(digest) is str else ""))
            if found is not None:
                return found
        except PdfLocationError:
            pass
    seed, seed_digest = _parse_draft_item_key(entry.get("item_id"))
    if not (seed and seed_digest) and extra:
        seed, seed_digest = _parse_draft_item_key(extra.get("item_id"))
    if seed and seed_digest:
        return by_paper_digest.get((seed, seed_digest))
    return None


def _authoritative_drive_path(inventory_item: Mapping[str, Any], manifest_entry: Mapping[str, Any]) -> str:
    proposed = inventory_item["drive_relative_path"]
    actual = manifest_entry.get("drive_relative_path")
    reused = manifest_entry.get("result") == "reused"
    digest_match = manifest_entry.get("remote_pdf_sha256") == inventory_item["pdf_sha256"]
    if type(actual) is str and is_portable_drive_relative_path(actual) and reused and digest_match:
        return actual
    if type(actual) is str and actual not in {proposed, None} and actual != proposed:
        _fail(
            ROOT_LAYOUT_MISMATCH,
            "Drive relative path does not match inventory convention",
            {
                "item_id": inventory_item["item_id"],
                "expected": proposed,
                "actual": actual,
            },
        )
    return proposed


def _empty_preconditions() -> dict[str, list[Any]]:
    return {"bindings": [], "local_copies": []}


def _preconditions_for_item(
    inventory_item: Mapping[str, Any],
    root_id: str,
    *,
    writeset_paths: set[str] | None = None,
) -> dict[str, list[Any]]:
    skip = writeset_paths or set()
    bindings = [
        dict(row)
        for row in inventory_item.get("bindings") or []
        if row.get("root_id") == root_id and row.get("record_path") not in skip
    ]
    # Keep every local copy that supplied the planned bytes, including source-only roots.
    copies = [dict(row) for row in inventory_item.get("local_copies") or []]
    return {"bindings": bindings, "local_copies": copies}


def _recheck_input_preconditions(
    *,
    roots: list[Mapping[str, Any]],
    preconditions: Mapping[str, Any] | None,
    writeset_after: Mapping[str, str] | None = None,
) -> None:
    if not preconditions:
        return
    by_id = {row["root_id"]: row for row in roots}
    after = dict(writeset_after or {})
    for binding in preconditions.get("bindings") or []:
        root = by_id.get(binding["root_id"])
        if root is None:
            _fail(PDF_APPLY_CHANGED, "binding root is no longer in roots.json", {"root_id": binding["root_id"]})
        path = resolve_inside_root(Path(root["path"]), binding["record_path"])
        current = _file_sha(path)
        allowed = {binding["scanned_sha256"]}
        if binding["record_path"] in after:
            allowed.add(after[binding["record_path"]])
        if current not in allowed:
            _fail(
                PDF_APPLY_CHANGED,
                "registration record changed after prepare",
                {"path": binding["record_path"], "root_id": binding["root_id"]},
            )
    for copy in preconditions.get("local_copies") or []:
        root = by_id.get(copy["root_id"])
        if root is None:
            _fail(PDF_APPLY_CHANGED, "local PDF root is no longer in roots.json", {"root_id": copy["root_id"]})
        path = resolve_inside_root(Path(root["path"]), copy["relative_path"])
        current = _file_sha(path)
        if current != copy["pdf_sha256"]:
            _fail(
                PDF_APPLY_CHANGED,
                "local PDF bytes changed after prepare",
                {"path": copy["relative_path"], "root_id": copy["root_id"]},
            )


def _should_exclude(path: Path) -> str | None:
    posix = path.as_posix()
    for marker in EXCLUDED_MARKERS:
        if marker in posix:
            return "historical_or_fixture"
    name = path.name
    if name.endswith(".schema.json") or name.endswith(".pyc"):
        return "not_ingest_material"
    return None


def _read_paper_id_from_record(path: Path) -> str | None:
    try:
        document = _load_json(path)
    except (OSError, ContractError, UnicodeError, PdfMigrationError):
        return None
    if type(document) is not dict:
        return None
    paper_id = document.get("paper_id")
    if type(paper_id) is not str:
        return None
    try:
        return canonical_paper_id(paper_id)
    except PdfLocationError:
        return None


def _scan_pdf_file(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        info = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    try:
        with path.open("rb") as handle:
            head = handle.read(5)
        if not is_pdf_bytes(head):
            return None
        digest, size = hash_file(path)
    except (OSError, PdfLocationError):
        return None
    return {"pdf_sha256": digest, "size_bytes": size, "media_type": MEDIA_PDF}


def _binding(root_id: str, paper_id: str, record_path: str, scanned_sha256: str) -> dict[str, str]:
    return {
        "root_id": root_id,
        "paper_id": paper_id,
        "record_path": record_path,
        "scanned_sha256": scanned_sha256,
    }


def _copy(root_id: str, relative_path: str, digest: str, size: int) -> dict[str, Any]:
    return {
        "root_id": root_id,
        "relative_path": relative_path,
        "pdf_sha256": digest,
        "size_bytes": size,
    }


def _scan_formal_or_notes(root: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    base = Path(root["path"])
    items: dict[tuple[str, str], dict[str, Any]] = {}
    excluded: list[dict[str, str]] = []
    records_dir = base / "wiki" / "meta" / "records" / "papers"
    notes_dir = base / "papers"
    captured_dir = base / ".raw" / "captured"
    blobs_dir = base / WORK_BLOBS
    digest_bindings = _collect_registration_digests(base, root["root_id"])

    if records_dir.is_dir():
        for path in sorted(records_dir.glob("*.json")):
            if path.is_symlink():
                continue
            paper_id = _read_paper_id_from_record(path)
            if paper_id is None:
                continue
            rel = _portable_rel(base, path) or path.name
            paper_bindings = items.setdefault(("bind", paper_id), {"bindings": [], "aliases": []})
            paper_bindings["bindings"].append(
                _binding(root["root_id"], paper_id, rel, sha256_bytes(path.read_bytes()))
            )

    if notes_dir.is_dir():
        for path in sorted(notes_dir.glob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                paper_id = canonical_paper_id(path.stem)
            except PdfLocationError:
                continue
            rel = _portable_rel(base, path)
            if rel is None:
                continue
            paper_bindings = items.setdefault(("bind", paper_id), {"bindings": [], "aliases": []})
            paper_bindings["bindings"].append(
                _binding(root["root_id"], paper_id, rel, sha256_bytes(path.read_bytes()))
            )
            paper_bindings["aliases"].append({"id": path.stem, "basis": "notes-filename"})

    for digest, bindings in digest_bindings.items():
        for binding in bindings:
            paper_id = binding["paper_id"]
            try:
                paper_id = canonical_paper_id(paper_id)
            except PdfLocationError:
                continue
            paper_bindings = items.setdefault(("bind", paper_id), {"bindings": [], "aliases": []})
            if binding not in paper_bindings["bindings"]:
                paper_bindings["bindings"].append(binding)

    for directory, _label in ((captured_dir, ".raw/captured"), (blobs_dir, WORK_BLOBS)):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            reason = _should_exclude(path)
            if reason:
                excluded.append({"path": str(path), "reason": reason})
                continue
            scanned = _scan_pdf_file(path)
            if scanned is None:
                continue
            rel = _portable_rel(base, path)
            if rel is None:
                continue
            digest = scanned["pdf_sha256"]
            mapped = digest_bindings.get(digest) or []
            paper_id = mapped[0]["paper_id"] if mapped else f"sha256:{digest}"
            try:
                canonical = canonical_paper_id(paper_id)
            except PdfLocationError:
                canonical = f"sha256:{digest}"
            rel_drive = drive_relative_path(canonical)
            key = (canonical, digest)
            item = items.get(key)
            if item is None:
                item = {
                    "item_id": item_id_for(paper_id=canonical, pdf_sha256=digest, drive_relative_path=rel_drive),
                    "paper_id": canonical,
                    "aliases": [{"id": seed_alias(canonical), "basis": "seed-or-slug"}],
                    "pdf_sha256": digest,
                    "size_bytes": scanned["size_bytes"],
                    "media_type": MEDIA_PDF,
                    "category": category_for_paper(canonical),
                    "paper_dir": paper_dir_for(canonical),
                    "drive_relative_path": rel_drive,
                    "local_copies": [],
                    "bindings": [],
                    "status": INTAKE_ONLY,
                    "blockers": [],
                }
                items[key] = item
            copy = _copy(root["root_id"], rel, digest, scanned["size_bytes"])
            if copy not in item["local_copies"]:
                item["local_copies"].append(copy)
            for binding in mapped:
                if binding not in item["bindings"]:
                    item["bindings"].append(binding)
            bind_info = items.get(("bind", item["paper_id"]))
            if bind_info:
                for binding in bind_info["bindings"]:
                    if binding not in item["bindings"]:
                        item["bindings"].append(binding)
            if item["bindings"]:
                item["status"] = "included"

    pending_binds = {key[1]: value for key, value in items.items() if key[0] == "bind"}
    for paper_id, bind_info in pending_binds.items():
        matches = [item for key, item in items.items() if key[0] == paper_id]
        if not matches:
            rel = drive_relative_path(paper_id)
            blocked = {
                "item_id": item_id_for(paper_id=paper_id, pdf_sha256="0" * 64, drive_relative_path=rel),
                "paper_id": paper_id,
                "aliases": bind_info.get("aliases") or [{"id": seed_alias(paper_id), "basis": "seed-or-slug"}],
                "pdf_sha256": "0" * 64,
                "size_bytes": 1,
                "media_type": MEDIA_PDF,
                "category": category_for_paper(paper_id),
                "paper_dir": paper_dir_for(paper_id),
                "drive_relative_path": rel,
                "local_copies": [],
                "bindings": bind_info["bindings"],
                "status": "blocked",
                "blockers": [{"code": "SOURCE_MISSING", "message": "registered paper has no scanned PDF bytes"}],
            }
            items[(paper_id, "missing")] = blocked
        else:
            for item in matches:
                for binding in bind_info["bindings"]:
                    if binding not in item["bindings"]:
                        item["bindings"].append(binding)
                if item["bindings"]:
                    item["status"] = "included"
                elif item["status"] == "included":
                    item["status"] = INTAKE_ONLY

    result = [value for key, value in items.items() if key[0] != "bind"]
    return result, excluded


def _scan_research(root: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    base = Path(root["path"])
    papers = base / "papers"
    excluded: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    if not papers.is_dir():
        return items, excluded
    for directory in sorted(papers.iterdir(), key=lambda item: item.name):
        if directory.is_symlink() or not directory.is_dir():
            continue
        source = directory / "source.json"
        if not source.is_file() or source.is_symlink():
            continue
        try:
            meta = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if type(meta) is not dict:
            continue
        paper_id = meta.get("paper_id")
        source_obj = meta.get("source") if type(meta.get("source")) is dict else {}
        digest = source_obj.get("sha256")
        path_value = source_obj.get("path")
        size = source_obj.get("size_bytes")
        if type(paper_id) is not str or type(digest) is not str or not HEX64.fullmatch(digest):
            continue
        try:
            canonical = canonical_paper_id(paper_id)
        except PdfLocationError:
            continue
        rel_drive = drive_relative_path(canonical)
        copies = []
        if type(path_value) is str and path_value:
            original = Path(path_value)
            scanned = _scan_pdf_file(original) if original.is_file() else None
            if scanned is not None:
                rel = _portable_rel(base, original) or original.name
                copies.append(_copy(root["root_id"], rel, scanned["pdf_sha256"], scanned["size_bytes"]))
                digest = scanned["pdf_sha256"]
                size = scanned["size_bytes"]
        if type(size) is not int or size < 1:
            size = 1
        record_rel = _portable_rel(base, source) or f"papers/{directory.name}/source.json"
        items.append(
            {
                "item_id": item_id_for(paper_id=canonical, pdf_sha256=digest, drive_relative_path=rel_drive),
                "paper_id": canonical,
                "aliases": [{"id": paper_id, "basis": "source.json"}],
                "pdf_sha256": digest,
                "size_bytes": size,
                "media_type": MEDIA_PDF,
                "category": category_for_paper(canonical),
                "paper_dir": paper_dir_for(canonical),
                "drive_relative_path": rel_drive,
                "local_copies": copies,
                "bindings": [_binding(root["root_id"], paper_id, record_rel, sha256_bytes(source.read_bytes()))],
                "status": "included" if copies else "blocked",
                "blockers": []
                if copies
                else [{"code": "SOURCE_MISSING", "message": "source.path is missing or unreadable"}],
            }
        )
    return items, excluded


def _scan_repository(root: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    base = Path(root["path"])
    excluded: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    seed = base / "docs" / "seed" / "engine-mvp.json"
    if seed.is_file() and not seed.is_symlink():
        try:
            payload = json.loads(seed.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            payload = None
        papers = payload.get("papers") if type(payload) is dict else None
        if type(papers) is list:
            for paper in papers:
                if type(paper) is not dict:
                    continue
                raw_id = paper.get("paper_id")
                if type(raw_id) is not str:
                    continue
                try:
                    canonical = canonical_paper_id(raw_id)
                except PdfLocationError:
                    continue
                rel = drive_relative_path(canonical)
                items.append(
                    {
                        "item_id": item_id_for(paper_id=canonical, pdf_sha256="0" * 64, drive_relative_path=rel),
                        "paper_id": canonical,
                        "aliases": [{"id": raw_id, "basis": "engine-mvp-seed"}],
                        "pdf_sha256": "0" * 64,
                        "size_bytes": 1,
                        "media_type": MEDIA_PDF,
                        "category": category_for_paper(canonical),
                        "paper_dir": paper_dir_for(canonical),
                        "drive_relative_path": rel,
                        "local_copies": [],
                        "bindings": [
                            _binding(
                                root["root_id"],
                                canonical,
                                "docs/seed/engine-mvp.json",
                                sha256_bytes(seed.read_bytes()),
                            )
                        ],
                        "status": "blocked",
                        "blockers": [
                            {"code": "SOURCE_MISSING", "message": "seed catalog row has no scanned PDF bytes"}
                        ],
                    }
                )
    pdf_root = base / "pdfs"
    if pdf_root.is_dir():
        for path in pdf_root.rglob("*"):
            if path.is_dir() or path.is_symlink():
                continue
            reason = _should_exclude(path)
            if reason:
                excluded.append({"path": str(path), "reason": reason})
                continue
            scanned = _scan_pdf_file(path)
            if scanned is None:
                continue
            rel = _portable_rel(base, path)
            if rel is None:
                continue
            digest = scanned["pdf_sha256"]
            paper_id = f"sha256:{digest}"
            drive_rel = drive_relative_path(paper_id)
            items.append(
                {
                    "item_id": item_id_for(paper_id=paper_id, pdf_sha256=digest, drive_relative_path=drive_rel),
                    "paper_id": paper_id,
                    "aliases": [],
                    "pdf_sha256": digest,
                    "size_bytes": scanned["size_bytes"],
                    "media_type": MEDIA_PDF,
                    "category": "uncategorized",
                    "paper_dir": paper_dir_for(paper_id),
                    "drive_relative_path": drive_rel,
                    "local_copies": [_copy(root["root_id"], rel, digest, scanned["size_bytes"])],
                    "bindings": [],
                    "status": INTAKE_ONLY,
                    "blockers": [],
                }
            )
    return items, excluded


def _scan_cache(root: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    base = Path(root["path"])
    excluded: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    if not base.exists():
        return items, excluded
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames.sort()
        filenames.sort()
        current = Path(dirpath)
        for name in list(dirnames):
            child = current / name
            if child.is_symlink():
                dirnames.remove(name)
        for name in filenames:
            path = current / name
            reason = _should_exclude(path)
            if reason:
                excluded.append({"path": str(path), "reason": reason})
                continue
            scanned = _scan_pdf_file(path)
            if scanned is None:
                continue
            rel = _portable_rel(base, path)
            if rel is None:
                continue
            digest = scanned["pdf_sha256"]
            paper_id = f"sha256:{digest}"
            drive_rel = drive_relative_path(paper_id)
            items.append(
                {
                    "item_id": item_id_for(paper_id=paper_id, pdf_sha256=digest, drive_relative_path=drive_rel),
                    "paper_id": paper_id,
                    "aliases": [],
                    "pdf_sha256": digest,
                    "size_bytes": scanned["size_bytes"],
                    "media_type": MEDIA_PDF,
                    "category": "uncategorized",
                    "paper_dir": paper_dir_for(paper_id),
                    "drive_relative_path": drive_rel,
                    "local_copies": [_copy(root["root_id"], rel, digest, scanned["size_bytes"])],
                    "bindings": [],
                    "status": INTAKE_ONLY,
                    "blockers": [],
                }
            )
    return items, excluded


def _merge_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in rows:
        if item["status"] == "blocked" and item["pdf_sha256"] == "0" * 64:
            key = (item["paper_id"], "missing")
        else:
            key = (item["paper_id"], item["pdf_sha256"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = item
            continue
        for copy in item["local_copies"]:
            if copy not in existing["local_copies"]:
                existing["local_copies"].append(copy)
        for binding in item["bindings"]:
            if binding not in existing["bindings"]:
                existing["bindings"].append(binding)
        for alias in item["aliases"]:
            if alias not in existing["aliases"]:
                existing["aliases"].append(alias)
        if existing["status"] == "blocked" and item["status"] == "included":
            existing["status"] = "included"
            existing["pdf_sha256"] = item["pdf_sha256"]
            existing["size_bytes"] = item["size_bytes"]
            existing["item_id"] = item["item_id"]
            existing["drive_relative_path"] = item["drive_relative_path"]
            existing["blockers"] = []
        elif existing["status"] == INTAKE_ONLY and item["status"] == "included":
            existing["status"] = "included"
        if existing["status"] == "included" and existing["pdf_sha256"] != "0" * 64:
            existing["item_id"] = item_id_for(
                paper_id=existing["paper_id"],
                pdf_sha256=existing["pdf_sha256"],
                drive_relative_path=existing["drive_relative_path"],
            )
    # Drop placeholder blocked rows when a real digest exists for the paper.
    papers_with_bytes = {paper_id for (paper_id, digest) in merged if digest not in {"missing", "0" * 64}}
    out = []
    for key, item in merged.items():
        if key[1] == "missing" and key[0] in papers_with_bytes:
            continue
        if item["status"] == "blocked" and item["pdf_sha256"] == "0" * 64 and item["paper_id"] in papers_with_bytes:
            continue
        if item["status"] == "included" and not item["bindings"]:
            item["status"] = INTAKE_ONLY
        item["local_copies"].sort(key=lambda row: (row["root_id"], row["relative_path"]))
        item["bindings"].sort(key=lambda row: (row["root_id"], row["record_path"]))
        out.append(item)
    # Content conflict: same paper, different real digests.
    by_paper: dict[str, list[str]] = {}
    for item in out:
        if item["pdf_sha256"] != "0" * 64 and item["status"] == "included":
            by_paper.setdefault(item["paper_id"], []).append(item["pdf_sha256"])
    for item in out:
        digests = sorted(set(by_paper.get(item["paper_id"], [])))
        if len(digests) > 1 and item["status"] == "included":
            item["status"] = "blocked"
            item["blockers"] = [
                {
                    "code": PDF_CONTENT_CONFLICT,
                    "message": "same paper has multiple distinct PDF digests; will not overwrite original.pdf",
                }
            ]
    out.sort(key=lambda item: (item["paper_id"], item["pdf_sha256"], item["item_id"]))
    return out


def build_inventory(*, roots_path: Path, batch_id: str) -> dict[str, Any]:
    batch = validate_batch_id(batch_id)
    roots_document = _load_json(roots_path)
    roots = parse_roots(roots_document)
    collected: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for root in roots:
        kind = root["kind"]
        if kind in {KIND_FORMAL, KIND_NOTES}:
            rows, extra = _scan_formal_or_notes(root)
        elif kind == KIND_RESEARCH:
            rows, extra = _scan_research(root)
        elif kind == KIND_REPO:
            rows, extra = _scan_repository(root)
        elif kind == KIND_CACHE:
            rows, extra = _scan_cache(root)
        else:
            rows, extra = [], []
        collected.extend(rows)
        excluded.extend(extra)
    items = _merge_items(collected)
    excluded.sort(key=lambda row: row["path"])
    counts = {
        "scanned": len(items) + len(excluded),
        "included": sum(1 for item in items if item["status"] == "included"),
        "blocked": sum(1 for item in items if item["status"] == "blocked"),
        "intake_only": sum(1 for item in items if item["status"] == INTAKE_ONLY),
        "excluded": len(excluded),
    }
    document = {
        "schema": INVENTORY_SCHEMA,
        "batch_id": batch,
        "roots_sha256": roots_digest(roots),
        "inventory_sha256": "0" * 64,
        "drive_root_folder_id": DRIVE_A_ROOT_FOLDER_ID,
        "cache_policy": CACHE_POLICY,
        "items": items,
        "excluded": excluded,
        "counts": counts,
    }
    document["inventory_sha256"] = sha256_json({key: value for key, value in document.items() if key != "inventory_sha256"})
    validated = validate_document(document, INVENTORY_SCHEMA)
    _write_staged_json(batch, "inventory.json", validated)
    return validated


def _current_location_and_page(root: Mapping[str, Any], paper_id: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    base = Path(root["path"])
    loc_rel = derived_location_path(root["kind"], paper_id)
    page_rel = derived_page_path(root["kind"], paper_id)
    loc = load_locations_file(base / loc_rel)
    loc_sha = _file_sha(base / loc_rel)
    page_sha = _file_sha(base / page_rel) if page_rel else None
    return loc, loc_sha, page_sha


def _next_page_bytes(root: Mapping[str, Any], paper_id: str, location: Mapping[str, Any]) -> tuple[str | None, bytes | None]:
    page_rel = derived_page_path(root["kind"], paper_id)
    if page_rel is None:
        return None, None
    path = resolve_inside_root(Path(root["path"]), page_rel)
    compiler_lines = render_pdf_section_lines(location)
    section = "\n".join(compiler_lines) if compiler_lines else render_pdf_section(location)
    if not path.exists():
        # Do not invent a full paper page; only patch existing notes/compiler pages.
        return page_rel, None
    text = path.read_text(encoding="utf-8")
    from video_paper_wiki.notes.merge import merge_paper_copy

    rendered = text
    if f"## {PDF_HEADING}" not in text:
        rendered = text.rstrip() + "\n" + section
        if not rendered.endswith("\n"):
            rendered += "\n"
    else:
        # Rebuild a synthetic rendered document that only owns the PDF heading.
        from video_paper_wiki.notes.merge import join_frontmatter, split_frontmatter

        yaml, body = split_frontmatter(text)
        prefix = ""
        if yaml is not None:
            prefix = join_frontmatter(yaml, "")
            rendered_body = (body.split(f"## {PDF_HEADING}")[0] if f"## {PDF_HEADING}" in body else body).rstrip()
            rendered = prefix.rstrip() + "\n" + rendered_body + "\n" + section
        else:
            rendered = text.split(f"## {PDF_HEADING}")[0].rstrip() + "\n" + section
        if not rendered.endswith("\n"):
            rendered += "\n"
        rendered = merge_paper_copy(text, rendered)
    return page_rel, rendered.encode("utf-8")


def _location_for_manifest_entry(
    inventory_item: Mapping[str, Any],
    manifest_entry: Mapping[str, Any],
    *,
    root: Mapping[str, Any],
) -> dict[str, Any]:
    if manifest_entry["root_folder_id"] != DRIVE_A_ROOT_FOLDER_ID:
        _fail(
            ROOT_LAYOUT_MISMATCH,
            "uploaded file is not under the frozen Drive A root",
            {"item_id": inventory_item["item_id"]},
        )
    drive_path = _authoritative_drive_path(inventory_item, manifest_entry)
    verified = (
        manifest_entry["result"] in {"uploaded", "reused"}
        and manifest_entry["remote_pdf_sha256"] == inventory_item["pdf_sha256"]
        and manifest_entry["verified_at"]
        and manifest_entry["drive_file_id"]
        and manifest_entry["drive_url"]
    )
    if not verified:
        _fail(
            PDF_MIGRATION_INVALID,
            "manifest entry is not a verified uploaded/reused digest match",
            {"item_id": inventory_item["item_id"], "result": manifest_entry["result"]},
        )
    refs = [
        {"root_id": copy["root_id"], "relative_path": copy["relative_path"]}
        for copy in inventory_item["local_copies"]
        if copy["root_id"] == root["root_id"]
    ]
    if not refs:
        refs = [{"root_id": copy["root_id"], "relative_path": copy["relative_path"]} for copy in inventory_item["local_copies"]]
    entry = build_pdf_entry(
        file_id=manifest_entry["drive_file_id"],
        url=manifest_entry["drive_url"],
        root_folder_id=DRIVE_A_ROOT_FOLDER_ID,
        relative_path=drive_path,
        pdf_sha256=inventory_item["pdf_sha256"],
        size_bytes=inventory_item["size_bytes"],
        media_type=MEDIA_PDF,
        local_refs=refs,
        verified=True,
        checked_at=manifest_entry["verified_at"],
    )
    existing, _loc_sha, _page_sha = _current_location_and_page(root, inventory_item["paper_id"])
    if existing is not None:
        for ref in refs:
            existing = merge_local_ref(
                existing,
                root_id=ref["root_id"],
                relative_path=ref["relative_path"],
                pdf_sha256=inventory_item["pdf_sha256"],
            )
        pdfs = list(existing["pdfs"])
        replaced = False
        for index, item in enumerate(pdfs):
            if item["pdf_sha256"] == inventory_item["pdf_sha256"]:
                pdfs[index] = entry
                replaced = True
        if not replaced:
            if any(item["pdf_sha256"] and item["pdf_sha256"] != inventory_item["pdf_sha256"] for item in pdfs):
                _fail(
                    PDF_CONTENT_CONFLICT,
                    "existing location has a different digest for this paper",
                    {"paper_id": inventory_item["paper_id"]},
                )
            pdfs.append(entry)
        return build_locations_document(inventory_item["paper_id"], pdfs)
    return build_locations_document(inventory_item["paper_id"], [entry])


def prepare_migration(*, inventory_path: Path, manifest_path: Path, roots_path: Path, batch_id: str) -> dict[str, Any]:
    batch = validate_batch_id(batch_id)
    inventory = validate_document(_load_json(inventory_path), INVENTORY_SCHEMA)
    manifest, extras = load_uploaded_manifest(manifest_path)
    roots = parse_roots(_load_json(roots_path))
    if manifest["inventory_sha256"] != inventory["inventory_sha256"]:
        _fail(
            PDF_MIGRATION_INVALID,
            "uploaded-manifest inventory_sha256 does not match inventory",
            {"expected": inventory["inventory_sha256"], "actual": manifest["inventory_sha256"]},
        )
    if manifest["drive_root_folder_id"] != DRIVE_A_ROOT_FOLDER_ID:
        _fail(ROOT_LAYOUT_MISMATCH, "uploaded-manifest root_folder_id is not Drive A")
    by_id = {item["item_id"]: item for item in inventory["items"]}
    by_paper_digest = {
        (item["paper_id"], item["pdf_sha256"]): item
        for item in inventory["items"]
        if item["pdf_sha256"] != "0" * 64
    }
    extras_by_index = {index: extra for index, extra in enumerate(extras)}
    plan_items = []
    blocked = []
    seen_inventory_ids = set()
    for index, entry in enumerate(manifest["entries"]):
        extra = extras_by_index.get(index)
        inventory_item = _match_inventory_item(
            entry=entry,
            extra=extra,
            by_id=by_id,
            by_paper_digest=by_paper_digest,
        )
        item_id = inventory_item["item_id"] if inventory_item is not None else entry["item_id"]
        if inventory_item is None:
            blocked.append(
                {
                    "item_id": item_id,
                    "paper_id": extra.get("paper_id") if extra else None,
                    "code": PDF_MIGRATION_INVALID,
                    "message": "manifest item_id is not in inventory",
                }
            )
            continue
        seen_inventory_ids.add(inventory_item["item_id"])
        if inventory_item["status"] != "included":
            blocked.append(
                {
                    "item_id": inventory_item["item_id"],
                    "paper_id": inventory_item["paper_id"],
                    "code": inventory_item["blockers"][0]["code"] if inventory_item["blockers"] else "blocked",
                    "message": "inventory item is not included",
                }
            )
            continue
        if not inventory_item["bindings"]:
            blocked.append(
                {
                    "item_id": inventory_item["item_id"],
                    "paper_id": inventory_item["paper_id"],
                    "code": PDF_MIGRATION_INVALID,
                    "message": "included item has no registration bindings",
                }
            )
            continue
        if entry["result"] not in {"uploaded", "reused"}:
            blocked.append(
                {
                    "item_id": inventory_item["item_id"],
                    "paper_id": inventory_item["paper_id"],
                    "code": entry["result"],
                    "message": "manifest result is not uploaded/reused",
                }
            )
            continue
        if entry["remote_pdf_sha256"] != inventory_item["pdf_sha256"]:
            blocked.append(
                {
                    "item_id": inventory_item["item_id"],
                    "paper_id": inventory_item["paper_id"],
                    "code": PDF_CONTENT_CONFLICT,
                    "message": "remote digest differs from inventory digest",
                }
            )
            continue
        bound_root_ids = {row["root_id"] for row in inventory_item["bindings"]}
        for root in roots:
            if root["role"] != "target":
                continue
            if root["kind"] == KIND_CACHE:
                continue
            if root["root_id"] not in bound_root_ids:
                continue
            try:
                location = _location_for_manifest_entry(inventory_item, entry, root=root)
            except (PdfMigrationError, PdfLocationError) as exc:
                blocked.append(
                    {
                        "item_id": inventory_item["item_id"],
                        "paper_id": inventory_item["paper_id"],
                        "code": exc.code,
                        "message": exc.message,
                    }
                )
                continue
            loc_rel = derived_location_path(root["kind"], inventory_item["paper_id"])
            resolve_inside_root(Path(root["path"]), loc_rel)
            _existing, before_loc, before_page = _current_location_and_page(root, inventory_item["paper_id"])
            loc_bytes = locations_bytes(location)
            page_rel, page_bytes = _next_page_bytes(root, inventory_item["paper_id"], location)
            after_page = sha256_bytes(page_bytes) if page_bytes is not None else None
            plan_items.append(
                {
                    "item_id": inventory_item["item_id"],
                    "paper_id": inventory_item["paper_id"],
                    "root_id": root["root_id"],
                    "action": "link",
                    "verification": VERIFIED,
                    "location_path": loc_rel,
                    "page_path": page_rel if page_bytes is not None else None,
                    "before_location_sha256": before_loc,
                    "after_location_sha256": sha256_bytes(loc_bytes),
                    "before_page_sha256": before_page if page_bytes is not None else None,
                    "after_page_sha256": after_page,
                    "location": location,
                    "input_preconditions": _preconditions_for_item(
                        inventory_item,
                        root["root_id"],
                        writeset_paths={path for path in (loc_rel, page_rel if page_bytes is not None else None) if path},
                    ),
                }
            )
    for item in inventory["items"]:
        if item["item_id"] not in seen_inventory_ids and item["status"] == "included":
            blocked.append(
                {
                    "item_id": item["item_id"],
                    "paper_id": item["paper_id"],
                    "code": "MANIFEST_MISSING",
                    "message": "included inventory item has no uploaded-manifest row",
                }
            )
    plan = {
        "schema": PLAN_SCHEMA,
        "batch_id": batch,
        "kind": "migration",
        "inventory_sha256": inventory["inventory_sha256"],
        "uploaded_manifest_sha256": sha256_bytes(Path(manifest_path).read_bytes()),
        "roots_sha256": roots_digest(roots),
        "plan_sha256": "0" * 64,
        "drive_root_folder_id": DRIVE_A_ROOT_FOLDER_ID,
        "cache_policy": CACHE_POLICY,
        "items": plan_items,
        "blocked": blocked,
    }
    bind_plan_digest(plan)
    validated = validate_document(plan, PLAN_SCHEMA)
    _write_staged_json(batch, "plan.json", validated)
    diff = {
        "schema": "video-paper-wiki.pdf-link-plan-diff.internal.v1",
        "plan_sha256": validated["plan_sha256"],
        "link_count": len(plan_items),
        "blocked_count": len(blocked),
        "items": [
            {
                "item_id": item["item_id"],
                "root_id": item["root_id"],
                "location_path": item["location_path"],
                "before_location_sha256": item["before_location_sha256"],
                "after_location_sha256": item["after_location_sha256"],
            }
            for item in plan_items
        ],
    }
    _write_staged_json(batch, "diff.json", diff)
    return validated


def prepare_unverified_link(
    *,
    roots_path: Path,
    root_id: str,
    paper_id: str,
    batch_id: str,
    drive_file_id: str | None = None,
    drive_url: str | None = None,
) -> dict[str, Any]:
    batch = validate_batch_id(batch_id)
    roots = parse_roots(_load_json(roots_path))
    root = next((row for row in roots if row["root_id"] == root_id), None)
    if root is None:
        _fail(PDF_MIGRATION_INVALID, "root_id is not in roots.json", {"root_id": root_id})
    if root["role"] != "target":
        _fail(PDF_MIGRATION_INVALID, "link-prepare requires a target root")
    canonical = canonical_paper_id(paper_id)
    entry = build_pdf_entry(
        file_id=drive_file_id,
        url=drive_url,
        root_folder_id=DRIVE_A_ROOT_FOLDER_ID,
        relative_path="",
        verified=False,
    )
    existing, before_loc, before_page = _current_location_and_page(root, canonical)
    if existing is not None:
        pdfs = list(existing["pdfs"])
        replaced = False
        for index, current in enumerate(pdfs):
            if same_drive_link(current, entry):
                merged = dict(current)
                merged["drive"] = dict(entry["drive"])
                if current.get("pdf_sha256") is None:
                    merged["verification"] = entry["verification"]
                pdfs[index] = merged
                replaced = True
                break
        if not replaced:
            pdfs.append(entry)
        location = build_locations_document(canonical, pdfs)
    else:
        location = build_locations_document(canonical, [entry])
    loc_rel = derived_location_path(root["kind"], canonical)
    resolve_inside_root(Path(root["path"]), loc_rel)
    loc_bytes = locations_bytes(location)
    page_rel, page_bytes = _next_page_bytes(root, canonical, location)
    item_id = "link-" + sha256_json({"paper_id": canonical, "file_id": entry["drive"]["file_id"]})[:16]
    plan_item = {
        "item_id": item_id,
        "paper_id": canonical,
        "root_id": root_id,
        "action": "link",
        "verification": UNVERIFIED,
        "location_path": loc_rel,
        "page_path": page_rel if page_bytes is not None else None,
        "before_location_sha256": before_loc,
        "after_location_sha256": sha256_bytes(loc_bytes),
        "before_page_sha256": before_page if page_bytes is not None else None,
        "after_page_sha256": sha256_bytes(page_bytes) if page_bytes is not None else None,
        "location": location,
        "input_preconditions": _empty_preconditions(),
    }
    plan = {
        "schema": PLAN_SCHEMA,
        "batch_id": batch,
        "kind": "unverified-link",
        "inventory_sha256": None,
        "uploaded_manifest_sha256": None,
        "roots_sha256": roots_digest(roots),
        "plan_sha256": "0" * 64,
        "drive_root_folder_id": DRIVE_A_ROOT_FOLDER_ID,
        "cache_policy": CACHE_POLICY,
        "items": [plan_item],
        "blocked": [],
    }
    bind_plan_digest(plan)
    validated = validate_document(plan, PLAN_SCHEMA)
    _write_staged_json(batch, "plan.json", validated)
    return validated


def _lock_path(root_path: Path) -> Path:
    return root_path / LOCK_NAME


def _acquire_lock(root_path: Path):
    import fcntl

    root_path.mkdir(parents=True, exist_ok=True)
    path = _lock_path(root_path)
    handle = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        _fail(PDF_MIGRATION_INVALID, "pdf migration lock is held", {"path": str(path)})
        raise AssertionError("unreachable") from exc
    return handle


_INSTALL_GUARDS: list[dict[str, Any]] = []
_OS_REPLACE = os.replace


def _same_install_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def _matching_install_guard(dst: Path) -> dict[str, Any] | None:
    dest = Path(dst)
    for guard in reversed(_INSTALL_GUARDS):
        if _same_install_path(dest, Path(guard["target"])):
            return guard
    return None


def _assert_live_install_before_replace(dst: Path | str) -> None:
    """Refuse replace if live bytes/digest/identity no longer match the approved before."""

    guard = _matching_install_guard(Path(dst))
    if guard is None:
        return
    root = guard.get("root")
    bound = guard.get("bound_identity")
    if root is not None and bound is not None:
        _assert_root_identity_holds(root, bound)
    dest = Path(dst)
    live_sha = _file_sha(dest)
    if live_sha != guard["before_sha256"]:
        _fail(
            PDF_APPLY_CHANGED,
            "writeset changed during apply",
            {"path": guard["path"], "item_id": guard["item_id"]},
        )
    before_raw = guard.get("before_raw")
    if before_raw is None:
        return
    if (not dest.exists()) or dest.is_symlink() or (not dest.is_file()) or dest.read_bytes() != before_raw:
        _fail(
            PDF_APPLY_CHANGED,
            "writeset changed during apply",
            {"path": guard["path"], "item_id": guard["item_id"]},
        )


def _existing_regular_file(path: Path) -> bool:
    try:
        return path.exists() and (not path.is_symlink()) and path.is_file()
    except OSError:
        return False


def _try_rename_exchange(src: Path, dest: Path) -> bool:
    """Swap src and dest inodes. Dest's previous inode remains at src on success."""

    src_b = os.fsencode(src)
    dest_b = os.fsencode(dest)
    try:
        if sys.platform == "darwin":
            libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
            rc = libc.renamex_np(src_b, dest_b, ctypes.c_uint(0x00000002))
        elif sys.platform.startswith("linux"):
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            renameat2 = libc.renameat2
            renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rc = renameat2(-100, src_b, -100, dest_b, 2)
        else:
            return False
    except (AttributeError, OSError):
        return False
    return rc == 0


def _unlink_if_present(path: Path) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()


def _install_via_hardlink_witness(src: Path, dest: Path) -> None:
    """Refuse hardlink plus plain replace when dest exchange is unavailable.

    Another dest read or hardlink cannot close the gap after the last check
    returns and before a builtin replace: an independent process can still
    hang a new inode on dest, while witness links and held fds stay on the
    old inode. Do not install after bytes. Apply rolls back this ticket's
    unfinished location. Emit the same os.rename audit a builtin replace
    would, then refuse without performing that replace.
    """

    witness = dest.with_name(dest.name + ".displaced-tmp")
    captured = dest.with_name(dest.name + ".live-displaced-tmp")
    _unlink_if_present(witness)
    _unlink_if_present(captured)
    try:
        if not _existing_regular_file(dest):
            _fail(PDF_APPLY_CHANGED, "writeset changed during apply", _install_conflict_details(dest))
        os.link(dest, witness)
        sys.audit("os.rename", os.fspath(src), os.fspath(dest), -1, -1)
        _fail(
            PDF_APPLY_CHANGED,
            "atomic dest exchange unavailable; refusing unsafe replace",
            {
                **_install_conflict_details(dest),
                "reason": PDF_APPLY_EXCHANGE_UNAVAILABLE,
            },
        )
    finally:
        _unlink_if_present(witness)
        _unlink_if_present(captured)


def _install_preserving_displaced(src, dest: Path) -> None:
    """Install src over dest without dropping the dest inode a plain rename would unlink.

    CPython's os.replace audits `os.rename` then unlinks dest. Native probes inject a
    writer in that audit window; a temp+replace writer hangs a new inode on dest, and
    a following unlink-rename would destroy it. Emit the same audit, then exchange
    so the dest inode present at install time is swapped to src. If exchange is
    unavailable, refuse hardlink plus plain replace before covering dest; apply
    rolls back this ticket's unfinished location and does not install after bytes.
    """

    src_p = Path(src)
    sys.audit("os.rename", os.fspath(src), os.fspath(dest), -1, -1)
    if _try_rename_exchange(src_p, dest):
        return
    if not _existing_regular_file(dest):
        _fail(PDF_APPLY_CHANGED, "writeset changed during apply", _install_conflict_details(dest))
    _install_via_hardlink_witness(src_p, dest)


def _guarded_os_replace(src, dst, *args, **kwargs):
    # Probes capture `raw_replace = os.replace` after importing this module, then
    # write the page and delegate. The live before-check must run on that primitive
    # so the concurrent append is seen before the real replace.
    _assert_live_install_before_replace(dst)
    dest = Path(dst)
    if _matching_install_guard(dest) is not None and _existing_regular_file(dest):
        _install_preserving_displaced(src, dest)
        return
    return _OS_REPLACE(src, dst, *args, **kwargs)


os.replace = _guarded_os_replace


def _install_conflict_details(path: Path) -> dict[str, Any]:
    guard = _matching_install_guard(path)
    if guard is None:
        return {"path": str(path)}
    return {"path": guard["path"], "item_id": guard["item_id"]}


def _read_fd_bytes(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        piece = os.read(fd, 1024 * 1024)
        if not piece:
            break
        chunks.append(piece)
    return b"".join(chunks)


def _open_existing_file_fd(path: Path) -> int | None:
    if (not path.exists()) or path.is_symlink() or (not path.is_file()):
        return None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(str(path), flags)
    except FileNotFoundError:
        return None
    except OSError:
        if _matching_install_guard(path) is not None:
            _fail(PDF_APPLY_CHANGED, "writeset changed during apply", _install_conflict_details(path))
        return None


def _write_fd_bytes(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]
    os.fsync(fd)


def _install_raw_bytes(path: Path, data: bytes) -> None:
    """Install bytes with the captured replace primitive so recovery can rewrite a guarded dest."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".restore-tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        _write_fd_bytes(fd, data)
    finally:
        os.close(fd)
    try:
        _OS_REPLACE(tmp, path)
    except Exception:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        raise


def _assert_held_dest_matches_guard(path: Path, held: bytes) -> None:
    guard = _matching_install_guard(path)
    if guard is None:
        return
    expected = guard.get("before_raw")
    if expected is not None and held != expected:
        _fail(PDF_APPLY_CHANGED, "writeset changed during apply", _install_conflict_details(path))
    if sha256_bytes(held) != guard["before_sha256"]:
        _fail(PDF_APPLY_CHANGED, "writeset changed during apply", _install_conflict_details(path))


def _assert_live_install_after_replace(path: Path, after_raw: bytes, approved_before: bytes | None) -> None:
    """Refuse if the installed path is neither this ticket's after nor the approved before."""

    guard = _matching_install_guard(path)
    if guard is None:
        return
    if (not path.exists()) or path.is_symlink() or (not path.is_file()):
        _fail(PDF_APPLY_CHANGED, "writeset changed during apply", _install_conflict_details(path))
    live = path.read_bytes()
    if live == after_raw:
        return
    # Keep live bytes: either the dest is still the approved before (install
    # vanished) or a later writer landed on the new inode.
    if approved_before is not None and live == approved_before:
        _fail(PDF_APPLY_CHANGED, "writeset changed during apply", _install_conflict_details(path))
    _fail(PDF_APPLY_CHANGED, "writeset changed during apply", _install_conflict_details(path))


def _push_install_guard(
    write: Mapping[str, Any],
    *,
    root: Mapping[str, Any],
    bound_identity: Mapping[str, Any],
) -> None:
    _INSTALL_GUARDS.append(
        {
            "target": write["target"],
            "path": write["path"],
            "item_id": write["item_id"],
            "before_sha256": write["before_sha256"],
            "before_raw": write.get("before_raw"),
            "after_raw": write.get("data"),
            "root": root,
            "bound_identity": bound_identity,
        }
    )


def _pop_install_guard() -> None:
    if _INSTALL_GUARDS:
        _INSTALL_GUARDS.pop()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        _write_fd_bytes(fd, data)
    finally:
        os.close(fd)
    dest_fd: int | None = None
    try:
        # Recheck the live target after the temp is complete and immediately
        # before the replace call. A later os.replace hook may still append;
        # _guarded_os_replace sees that write when the hook delegates.
        _assert_live_install_before_replace(path)
        # Hold the dest inode across the real rename (same-inode in-place write).
        # A Python os.replace wrap cannot see an independent writer that lands
        # after the last precheck and before the native syscall; the old fd
        # still can. A temp+rename writer hangs a new inode on dest — that
        # version is preserved by the exchange install, not by this fd.
        dest_fd = _open_existing_file_fd(path)
        approved_before: bytes | None = None
        if dest_fd is not None:
            approved_before = _read_fd_bytes(dest_fd)
            _assert_held_dest_matches_guard(path, approved_before)
        os.replace(tmp, path)
        # Exchange install leaves the displaced dest at tmp. A temp+rename
        # writer is invisible to dest_fd (that fd still holds the approved before).
        # If exchange is unavailable, the fallback refuses before a plain replace.
        if _existing_regular_file(tmp):
            displaced = tmp.read_bytes()
            if approved_before is None or displaced != approved_before:
                _install_raw_bytes(path, displaced)
                _fail(
                    PDF_APPLY_CHANGED,
                    "writeset changed during apply",
                    _install_conflict_details(path),
                )
            tmp.unlink()
        elif tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        if dest_fd is not None:
            held = _read_fd_bytes(dest_fd)
            if held != approved_before:
                _install_raw_bytes(path, held)
                _fail(
                    PDF_APPLY_CHANGED,
                    "writeset changed during apply",
                    _install_conflict_details(path),
                )
        _assert_live_install_after_replace(path, data, approved_before)
    except Exception:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        raise
    finally:
        if dest_fd is not None:
            try:
                os.close(dest_fd)
            except OSError:
                pass


def _journal_path(root_path: Path, plan_sha256: str) -> Path:
    return root_path / ".work" / "pdf-migration" / f"journal-{plan_sha256[:16]}.json"


def _load_journal(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": JOURNAL_SCHEMA,
            "plan_sha256": None,
            "root_id": None,
            "entries": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _write_unit_backups(journal_path: Path, writes: list[dict[str, Any]]) -> None:
    backup_dir = journal_path.parent / "backups"
    for write in writes:
        raw = write.get("before_raw")
        if raw is None:
            continue
        backup_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            backup_dir / sha256_json({"path": write["path"], "before": write["before_sha256"]}),
            raw,
        )


def _restore_applied_writes(
    applied: list[dict[str, Any]],
    *,
    root: Mapping[str, Any] | None = None,
    bound_identity: Mapping[str, Any] | None = None,
) -> None:
    if root is not None and bound_identity is not None:
        _assert_root_identity_holds(root, bound_identity)
    for write in reversed(applied):
        target = write["target"]
        if write["before_raw"] is None:
            if target.exists() and target.is_file() and not target.is_symlink():
                target.unlink()
        else:
            _atomic_write(target, write["before_raw"])


def _assert_root_identity_holds(root: Mapping[str, Any], bound: Mapping[str, Any]) -> None:
    live = root_directory_identity(root["path"])
    if live != bound:
        _fail(PDF_APPLY_CHANGED, "target root directory identity changed during apply")


def apply_plan_to_root(
    *,
    plan: Mapping[str, Any],
    roots: list[Mapping[str, Any]],
    root_id: str,
    approved_plan_sha256: str,
    confirm: bool,
) -> dict[str, Any]:
    if not confirm:
        _fail(HUMAN_APPROVAL_REQUIRED, "interactive confirmation is required", {"next_action": "confirm_interactively"})
    validated = verify_approved_plan(plan, approved_plan_sha256)
    root = resolve_apply_root(plan=validated, roots=roots, root_id=root_id)
    if root["kind"] == KIND_FORMAL:
        _fail(
            PDF_FORMAL_TRANSACTION_REQUIRED,
            "formal-vault apply must use the operator transaction path with a valid upstream_root",
        )
    base = Path(root["path"]).resolve()
    bound_identity = root_directory_identity(root["path"])
    lock = _acquire_lock(base)
    try:
        journal_path = _journal_path(base, validated["plan_sha256"])
        scoped = [item for item in validated["items"] if item["root_id"] == root_id]
        intent = []
        for item in scoped:
            assert_item_identity_paths(root, item)
            loc_rel = item["location_path"]
            planned_page = item["page_path"]
            resolve_inside_root(base, loc_rel)
            if planned_page:
                resolve_inside_root(base, planned_page)
            intent.append(
                {
                    "item_id": item["item_id"],
                    "location_path": loc_rel,
                    "page_path": planned_page,
                    "before_location_sha256": item["before_location_sha256"],
                    "after_location_sha256": item["after_location_sha256"],
                    "before_page_sha256": item["before_page_sha256"],
                    "after_page_sha256": item["after_page_sha256"],
                }
            )
        journal = {
            "schema": JOURNAL_SCHEMA,
            "plan_sha256": validated["plan_sha256"],
            "root_id": root_id,
            "kind": root["kind"],
            "intent": intent,
            "entries": [],
        }
        if journal_path.is_file():
            existing = _load_journal(journal_path)
            if existing.get("entries"):
                journal["entries"] = list(existing["entries"])
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(journal_path, canonicalize(journal) + b"\n")
        committed = {(entry.get("item_id"), entry.get("path")) for entry in journal.get("entries", [])}
        results = []
        for item in scoped:
            if item["verification"] != VERIFIED and validated["kind"] == "migration":
                results.append({"item_id": item["item_id"], "state": "unverified", "code": "not_migration_success"})
                continue
            _recheck_input_preconditions(
                roots=roots,
                preconditions=item.get("input_preconditions"),
                writeset_after=item_writeset_after(item),
            )
            apply_state = inspect_item_apply_state(root, item)
            loc_rel = item["location_path"]
            loc_path = resolve_inside_root(base, loc_rel)
            current_loc = _file_sha(loc_path)
            page_rel = item["page_path"]
            page_path = resolve_inside_root(base, page_rel) if page_rel else None
            current_page = _file_sha(page_path) if page_path is not None else None
            loc_done = current_loc == item["after_location_sha256"]
            page_needed = bool(page_rel and item["after_page_sha256"])
            page_done = (not page_needed) or current_page == item["after_page_sha256"]
            if apply_state == "done" or (loc_done and page_done):
                state = "unverified" if item["verification"] == UNVERIFIED else "linked"
                results.append({"item_id": item["item_id"], "state": state, "code": None})
                continue
            writes: list[dict[str, Any]] = []
            if not loc_done:
                loc_bytes = locations_bytes(item["location"])
                if sha256_bytes(loc_bytes) != item["after_location_sha256"]:
                    _fail(PDF_MIGRATION_INVALID, "planned location bytes do not match after digest")
                before_raw = loc_path.read_bytes() if loc_path.exists() and loc_path.is_file() else None
                writes.append(
                    {
                        "item_id": item["item_id"],
                        "path": loc_rel,
                        "target": loc_path,
                        "data": loc_bytes,
                        "before_sha256": item["before_location_sha256"],
                        "after_sha256": item["after_location_sha256"],
                        "before_raw": before_raw,
                    }
                )
            if page_needed and not page_done:
                _page_rel, page_bytes = _next_page_bytes(root, item["paper_id"], item["location"])
                if page_bytes is None or sha256_bytes(page_bytes) != item["after_page_sha256"]:
                    _fail(PDF_APPLY_CHANGED, "page bytes changed and cannot be rewritten safely")
                assert page_path is not None
                before_raw = page_path.read_bytes() if page_path.exists() and page_path.is_file() else None
                writes.append(
                    {
                        "item_id": item["item_id"],
                        "path": page_rel,
                        "target": page_path,
                        "data": page_bytes,
                        "before_sha256": item["before_page_sha256"],
                        "after_sha256": item["after_page_sha256"],
                        "before_raw": before_raw,
                    }
                )
            _write_unit_backups(journal_path, writes)
            applied: list[dict[str, Any]] = []
            try:
                for write in writes:
                    _assert_root_identity_holds(root, bound_identity)
                    live_sha = _file_sha(write["target"])
                    if live_sha != write["before_sha256"]:
                        _fail(
                            PDF_APPLY_CHANGED,
                            "writeset changed during apply",
                            {"path": write["path"], "item_id": write["item_id"]},
                        )
                    _push_install_guard(write, root=root, bound_identity=bound_identity)
                    try:
                        _atomic_write(write["target"], write["data"])
                    finally:
                        _pop_install_guard()
                    if _file_sha(write["target"]) != write["after_sha256"]:
                        _fail(
                            PDF_APPLY_CHANGED,
                            "write did not produce the planned after digest",
                            {"path": write["path"], "item_id": write["item_id"]},
                        )
                    applied.append(write)
            except Exception:
                _restore_applied_writes(applied, root=root, bound_identity=bound_identity)
                raise
            for write in writes:
                record = {
                    "item_id": write["item_id"],
                    "path": write["path"],
                    "before_sha256": write["before_sha256"],
                    "after_sha256": write["after_sha256"],
                    "before_bytes_sha256": sha256_bytes(write["before_raw"]) if write["before_raw"] is not None else None,
                }
                journal["entries"].append(record)
                committed.add((write["item_id"], write["path"]))
            _atomic_write(journal_path, canonicalize(journal) + b"\n")
            state = "unverified" if item["verification"] == UNVERIFIED else "linked"
            results.append({"item_id": item["item_id"], "state": state, "code": None})
        _atomic_write(journal_path, canonicalize(journal) + b"\n")
        return {
            "root_id": root_id,
            "kind": root["kind"],
            "plan_sha256": validated["plan_sha256"],
            "journal_path": str(journal_path),
            "journal_sha256": sha256_bytes(journal_path.read_bytes()),
            "results": results,
            "keep_local": True,
        }
    finally:
        _INSTALL_GUARDS.clear()
        lock.close()


def rollback_journal(*, journal_path: Path, roots_path: Path, confirm: bool) -> dict[str, Any]:
    if not confirm:
        _fail(HUMAN_APPROVAL_REQUIRED, "interactive confirmation is required")
    journal = _load_json(journal_path)
    roots = parse_roots(_load_json(roots_path))
    root = next((row for row in roots if row["root_id"] == journal.get("root_id")), None)
    if root is None:
        _fail(PDF_MIGRATION_INVALID, "journal root_id is not in roots.json")
    if root["kind"] == KIND_FORMAL or journal.get("kind") == KIND_FORMAL or journal.get("receipt_path"):
        _fail(
            PDF_FORMAL_TRANSACTION_REQUIRED,
            "formal-vault rollback must use a compensating transaction through the operator",
        )
    base = Path(root["path"])
    lock = _acquire_lock(base)
    restored = []
    conflicts = []
    try:
        backups = journal_path.parent / "backups"
        for entry in journal.get("entries", []):
            path = base / entry["path"]
            current = _file_sha(path)
            if current != entry["after_sha256"]:
                conflicts.append({"path": entry["path"], "code": PDF_ROLLBACK_CONFLICT})
                continue
            before = entry.get("before_sha256")
            backup = backups / sha256_json({"path": entry["path"], "before": before})
            if before is None:
                if path.exists() and path.is_file():
                    path.unlink()
                restored.append(entry["path"])
                continue
            if backup.is_file():
                data = backup.read_bytes()
                if sha256_bytes(data) != before:
                    conflicts.append({"path": entry["path"], "code": PDF_ROLLBACK_CONFLICT})
                    continue
                _atomic_write(path, data)
                restored.append(entry["path"])
            else:
                conflicts.append({"path": entry["path"], "code": "BACKUP_MISSING"})
        if conflicts:
            _fail(PDF_ROLLBACK_CONFLICT, "rollback found later edits or missing backups", {"conflicts": conflicts})
        return {"restored": restored, "keep_local": True, "drive_unchanged": True}
    finally:
        lock.close()


def _journal_covers_item(journal: Mapping[str, Any] | None, item: Mapping[str, Any]) -> bool:
    if journal is None:
        return False
    entries = {(row.get("item_id"), row.get("path")) for row in journal.get("entries") or []}
    if (item["item_id"], item["location_path"]) not in entries:
        return False
    if item["page_path"] and item["after_page_sha256"]:
        if (item["item_id"], item["page_path"]) not in entries:
            return False
    return True


def _load_root_journal(root: Mapping[str, Any], plan_sha256: str) -> tuple[Path, dict[str, Any] | None]:
    path = _journal_path(Path(root["path"]), plan_sha256)
    if not path.is_file() or path.is_symlink():
        return path, None
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return path, None


def _load_validated_json(path: Path, schema: str) -> dict[str, Any] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        raw = path.read_bytes()
        document = parse_strict_json(raw, invalid_code=PDF_MIGRATION_INVALID)
        return validate_document(document, schema)
    except (OSError, ContractError, UnicodeError, PdfMigrationError):
        return None


def _receipt_in_head_chain(*, vault: Path, head: Mapping[str, Any], receipt_rel: str, receipt_sha256: str) -> bool:
    path = head.get("receipt_path")
    digest = head.get("receipt_sha256")
    seen: set[str] = set()
    while type(path) is str and type(digest) is str:
        if path in seen:
            return False
        seen.add(path)
        raw_path = vault / path
        if not raw_path.is_file() or raw_path.is_symlink():
            return False
        raw = raw_path.read_bytes()
        if sha256_bytes(raw) != digest:
            return False
        if path == receipt_rel:
            return digest == receipt_sha256
        receipt = _load_validated_json(raw_path, RECEIPT_SCHEMA)
        if receipt is None:
            return False
        previous = receipt.get("previous")
        if type(previous) is not dict:
            return False
        path = previous.get("path")
        digest = previous.get("sha256")
    return False


def _formal_receipt_proves_item(
    *,
    root: Mapping[str, Any],
    journal: Mapping[str, Any] | None,
    item: Mapping[str, Any],
) -> bool:
    if journal is None:
        return False
    receipt_rel = journal.get("receipt_path")
    if type(receipt_rel) is not str or not receipt_rel:
        return False
    vault = Path(root["path"])
    receipt_path = vault / receipt_rel
    receipt = _load_validated_json(receipt_path, RECEIPT_SCHEMA)
    if receipt is None:
        return False
    try:
        raw = receipt_path.read_bytes()
    except OSError:
        return False
    file_sha = sha256_bytes(raw)
    journal_sha = journal.get("receipt_sha256")
    if journal_sha != file_sha:
        return False
    writes = {
        row.get("path"): row
        for row in receipt.get("writes") or []
        if type(row) is dict and type(row.get("path")) is str
    }
    loc_write = writes.get(item["location_path"])
    if loc_write is None or loc_write.get("after_sha256") != item["after_location_sha256"]:
        return False
    if item["page_path"] and item["after_page_sha256"]:
        page_write = writes.get(item["page_path"])
        if page_write is None or page_write.get("after_sha256") != item["after_page_sha256"]:
            return False
    journal_entries = {(row.get("item_id"), row.get("path"), row.get("after_sha256")) for row in journal.get("entries") or []}
    if (item["item_id"], item["location_path"], item["after_location_sha256"]) not in journal_entries:
        return False
    if item["page_path"] and item["after_page_sha256"]:
        if (item["item_id"], item["page_path"], item["after_page_sha256"]) not in journal_entries:
            return False
    head = _load_validated_json(vault / OPERATION_HEAD_PATH, HEAD_SCHEMA)
    if head is None:
        return False
    return _receipt_in_head_chain(vault=vault, head=head, receipt_rel=receipt_rel, receipt_sha256=file_sha)


def build_report(*, plan_path: Path, roots_path: Path) -> dict[str, Any]:
    plan = validate_document(_load_json(plan_path), PLAN_SCHEMA)
    roots = parse_roots(_load_json(roots_path))
    items = []
    root_stats: dict[str, dict[str, Any]] = {}
    journals: dict[str, dict[str, Any] | None] = {}
    for root in roots:
        journal_path, journal = _load_root_journal(root, plan["plan_sha256"])
        journals[root["root_id"]] = journal
        root_stats[root["root_id"]] = {
            "root_id": root["root_id"],
            "kind": root["kind"],
            "linked": 0,
            "pending": 0,
            "conflict": 0,
            "journal_sha256": sha256_bytes(journal_path.read_bytes()) if journal_path.is_file() else None,
        }
        receipt = None
        if journal and journal.get("receipt_path"):
            receipt_path = Path(root["path"]) / journal["receipt_path"]
            if not receipt_path.is_file():
                root_stats[root["root_id"]]["journal_sha256"] = None
            receipt = receipt_path if receipt_path.is_file() else None
        _ = receipt
    for item in plan["items"]:
        root = next((row for row in roots if row["root_id"] == item["root_id"]), None)
        state = "pending"
        code = None
        message = "not applied"
        if root is not None:
            loc_rel = derived_location_path(root["kind"], item["paper_id"])
            loc_sha = _file_sha(resolve_inside_root(Path(root["path"]), loc_rel))
            page_rel = item["page_path"]
            page_sha = (
                _file_sha(resolve_inside_root(Path(root["path"]), page_rel))
                if page_rel and item["after_page_sha256"]
                else None
            )
            journal = journals.get(root["root_id"])
            loc_ok = loc_sha == item["after_location_sha256"]
            page_ok = (not page_rel) or (not item["after_page_sha256"]) or page_sha == item["after_page_sha256"]
            covered = _journal_covers_item(journal, item)
            receipt_ok = True
            if root["kind"] == KIND_FORMAL:
                receipt_ok = _formal_receipt_proves_item(root=root, journal=journal, item=item)
            if loc_ok and page_ok and covered and receipt_ok:
                state = "linked" if item["verification"] == VERIFIED else "unverified"
                message = "writeset, journal, and planned after digests match"
            elif loc_ok and not (page_ok and covered and receipt_ok):
                state = "conflict"
                code = PDF_APPLY_CHANGED
                message = "location exists without a complete writeset, journal, or receipt"
            elif loc_sha not in {item["before_location_sha256"], None}:
                state = "conflict"
                code = PDF_APPLY_CHANGED
                message = "location file does not match before or after digest"
            elif page_rel and page_sha not in {item["before_page_sha256"], None, item["after_page_sha256"]}:
                state = "conflict"
                code = PDF_APPLY_CHANGED
                message = "page file does not match before or after digest"
        stats = root_stats.get(item["root_id"])
        if stats is not None:
            if state == "linked":
                stats["linked"] += 1
            elif state == "conflict":
                stats["conflict"] += 1
            else:
                stats["pending"] += 1
        items.append(
            {
                "item_id": item["item_id"],
                "paper_id": item["paper_id"],
                "root_id": item["root_id"],
                "state": state,
                "verification": item["verification"] if state != "pending" else "none",
                "code": code,
                "message": message,
            }
        )
    for row in plan["blocked"]:
        items.append(
            {
                "item_id": row["item_id"] or "unknown",
                "paper_id": row["paper_id"] or "sha256:" + ("0" * 64),
                "root_id": roots[0]["root_id"] if roots else "unknown",
                "state": "blocked",
                "verification": "none",
                "code": row["code"],
                "message": row["message"],
            }
        )
    linked = sum(1 for item in items if item["state"] == "linked")
    unverified = sum(1 for item in items if item["state"] == "unverified")
    failed = sum(1 for item in items if item["state"] == "failed")
    conflict = sum(1 for item in items if item["state"] == "conflict")
    blocked = sum(1 for item in items if item["state"] == "blocked")
    pending = sum(1 for item in items if item["state"] == "pending")
    missing_original = sum(1 for row in plan["blocked"] if row.get("code") == "SOURCE_MISSING")
    status = "MIGRATION_PENDING"
    if linked and not pending and not conflict and not blocked and unverified == 0:
        status = "DONE"
    elif linked or unverified:
        status = "PARTIAL"
    report = {
        "schema": REPORT_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "cache_policy": CACHE_POLICY,
        "status": status,
        "counts": {
            "planned": len(plan["items"]),
            "linked": linked,
            "unverified": unverified,
            "failed": failed,
            "conflict": conflict,
            "missing_original": missing_original,
            "excluded": 0,
            "blocked": blocked,
        },
        "roots": [root_stats[row["root_id"]] for row in roots if row["root_id"] in root_stats],
        "items": items,
    }
    return validate_document(report, REPORT_SCHEMA)


def resolve_from_root(
    *,
    roots_path: Path,
    root_id: str,
    paper_id: str,
    prefer: str,
    offline: bool,
    pdf_sha256: str | None,
) -> dict[str, Any]:
    from video_paper_wiki.pdf_locations import (
        PREFER_DRIVE,
        PDF_PARAMETER_CONFLICT,
        PdfLocationError,
        resolve_open_target,
    )

    if offline and prefer == PREFER_DRIVE:
        raise PdfLocationError(PDF_PARAMETER_CONFLICT, "--offline cannot be combined with --prefer drive")
    roots = parse_roots(_load_json(roots_path))
    root = next((row for row in roots if row["root_id"] == root_id), None)
    if root is None:
        _fail(PDF_MIGRATION_INVALID, "root_id is not in roots.json", {"root_id": root_id})
    canonical = canonical_paper_id(paper_id)
    loc_rel = location_relative_path(root["kind"], canonical)
    document = load_locations_file(Path(root["path"]) / loc_rel)
    if document is None:
        _fail("PDF_NOT_FOUND", "no pdf-locations document for this paper", {"paper_id": canonical})
    return resolve_open_target(
        document,
        roots=roots_map(roots),
        prefer=prefer,
        offline=offline,
        pdf_sha256=pdf_sha256,
    )
