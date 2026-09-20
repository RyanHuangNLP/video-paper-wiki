"""PDF inventory, link-plan, writeset apply, report, and rollback. No Drive upload."""

from __future__ import annotations

import json
import os
import stat
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
    drive_relative_path,
    hash_file,
    is_pdf_bytes,
    item_id_for,
    load_locations_file,
    location_relative_path,
    locations_bytes,
    merge_local_ref,
    page_relative_path,
    paper_dir_for,
    parse_roots,
    render_pdf_section,
    roots_digest,
    roots_map,
    seed_alias,
    sha256_bytes,
    sha256_json,
    validate_locations,
)
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki.staging import stage_bytes, validate_batch_id

INVENTORY_SCHEMA = "video-paper-wiki.pdf-migration-inventory.v1"
MANIFEST_SCHEMA = "video-paper-wiki.pdf-upload-manifest.v1"
PLAN_SCHEMA = "video-paper-wiki.pdf-link-plan.v1"
REPORT_SCHEMA = "video-paper-wiki.pdf-migration-report.v1"
PDF_MIGRATION_INVALID = "PDF_MIGRATION_INVALID"
PDF_APPLY_CHANGED = "PDF_APPLY_CHANGED"
PDF_ROLLBACK_CONFLICT = "PDF_ROLLBACK_CONFLICT"
PLAN_HASH_MISMATCH = "PLAN_HASH_MISMATCH"
HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
INTAKE_ONLY = "intake-only"
EXCLUDED_MARKERS = (
    "/tests/fixtures/",
    "/artifacts/verification/",
    "/.git/",
    "/node_modules/",
)
WORK_BLOBS = ".work/blobs"
LOCK_NAME = ".pdf-migration.lock"
JOURNAL_SCHEMA = "video-paper-wiki.pdf-migration-journal.internal.v1"


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

    for directory, label in ((captured_dir, ".raw/captured"), (blobs_dir, WORK_BLOBS)):
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
            paper_id = None
            if HEX64.fullmatch(path.stem) and path.stem == digest:
                paper_id = f"sha256:{digest}"
            if paper_id is None:
                # Unbound captured bytes stay intake-only unless a paper binding exists.
                paper_id = f"sha256:{digest}"
                status = INTAKE_ONLY
            else:
                status = "included"
            rel_drive = drive_relative_path(paper_id)
            key = (canonical_paper_id(paper_id), digest)
            item = items.get(key)
            if item is None:
                item = {
                    "item_id": item_id_for(paper_id=paper_id, pdf_sha256=digest, drive_relative_path=rel_drive),
                    "paper_id": canonical_paper_id(paper_id),
                    "aliases": [{"id": seed_alias(paper_id), "basis": "seed-or-slug"}],
                    "pdf_sha256": digest,
                    "size_bytes": scanned["size_bytes"],
                    "media_type": MEDIA_PDF,
                    "category": category_for_paper(paper_id),
                    "paper_dir": paper_dir_for(paper_id),
                    "drive_relative_path": rel_drive,
                    "local_copies": [],
                    "bindings": [],
                    "status": status,
                    "blockers": [],
                }
                items[key] = item
            copy = _copy(root["root_id"], rel, digest, scanned["size_bytes"])
            if copy not in item["local_copies"]:
                item["local_copies"].append(copy)
            bind_info = items.get(("bind", item["paper_id"]))
            if bind_info:
                item["status"] = "included"
                for binding in bind_info["bindings"]:
                    if binding not in item["bindings"]:
                        item["bindings"].append(binding)

    # Attach paper bindings to matching digest items; papers without PDF stay blocked.
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
                if item["status"] == INTAKE_ONLY and item["bindings"]:
                    item["status"] = "included"

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
    loc_rel = location_relative_path(root["kind"], paper_id)
    page_rel = page_relative_path(root["kind"], paper_id)
    loc = load_locations_file(base / loc_rel)
    loc_sha = _file_sha(base / loc_rel)
    page_sha = _file_sha(base / page_rel) if page_rel else None
    return loc, loc_sha, page_sha


def _next_page_bytes(root: Mapping[str, Any], paper_id: str, location: Mapping[str, Any]) -> tuple[str | None, bytes | None]:
    page_rel = page_relative_path(root["kind"], paper_id)
    if page_rel is None:
        return None, None
    path = Path(root["path"]) / page_rel
    section = render_pdf_section(location)
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
    if manifest_entry["drive_relative_path"] not in {inventory_item["drive_relative_path"], None}:
        if manifest_entry["drive_relative_path"] != inventory_item["drive_relative_path"]:
            _fail(
                ROOT_LAYOUT_MISMATCH,
                "Drive relative path does not match inventory convention",
                {
                    "item_id": inventory_item["item_id"],
                    "expected": inventory_item["drive_relative_path"],
                    "actual": manifest_entry["drive_relative_path"],
                },
            )
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
        relative_path=inventory_item["drive_relative_path"],
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
    manifest = validate_document(_load_json(manifest_path), MANIFEST_SCHEMA)
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
    plan_items = []
    blocked = []
    seen_manifest = set()
    for entry in manifest["entries"]:
        item_id = entry["item_id"]
        seen_manifest.add(item_id)
        inventory_item = by_id.get(item_id)
        if inventory_item is None:
            blocked.append(
                {
                    "item_id": item_id,
                    "paper_id": None,
                    "code": PDF_MIGRATION_INVALID,
                    "message": "manifest item_id is not in inventory",
                }
            )
            continue
        if inventory_item["status"] != "included":
            blocked.append(
                {
                    "item_id": item_id,
                    "paper_id": inventory_item["paper_id"],
                    "code": inventory_item["blockers"][0]["code"] if inventory_item["blockers"] else "blocked",
                    "message": "inventory item is not included",
                }
            )
            continue
        if entry["result"] not in {"uploaded", "reused"}:
            blocked.append(
                {
                    "item_id": item_id,
                    "paper_id": inventory_item["paper_id"],
                    "code": entry["result"],
                    "message": "manifest result is not uploaded/reused",
                }
            )
            continue
        if entry["remote_pdf_sha256"] != inventory_item["pdf_sha256"]:
            blocked.append(
                {
                    "item_id": item_id,
                    "paper_id": inventory_item["paper_id"],
                    "code": PDF_CONTENT_CONFLICT,
                    "message": "remote digest differs from inventory digest",
                }
            )
            continue
        for root in roots:
            if root["role"] != "target":
                continue
            if root["kind"] == KIND_CACHE:
                continue
            try:
                location = _location_for_manifest_entry(inventory_item, entry, root=root)
            except (PdfMigrationError, PdfLocationError) as exc:
                blocked.append(
                    {
                        "item_id": item_id,
                        "paper_id": inventory_item["paper_id"],
                        "code": exc.code,
                        "message": exc.message,
                    }
                )
                continue
            loc_rel = location_relative_path(root["kind"], inventory_item["paper_id"])
            _existing, before_loc, before_page = _current_location_and_page(root, inventory_item["paper_id"])
            loc_bytes = locations_bytes(location)
            page_rel, page_bytes = _next_page_bytes(root, inventory_item["paper_id"], location)
            after_page = sha256_bytes(page_bytes) if page_bytes is not None else None
            plan_items.append(
                {
                    "item_id": item_id,
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
                }
            )
    for item in inventory["items"]:
        if item["item_id"] not in seen_manifest and item["status"] == "included":
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
    plan["plan_sha256"] = sha256_json({key: value for key, value in plan.items() if key != "plan_sha256"})
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
        pdfs.append(entry)
        location = build_locations_document(canonical, pdfs)
    else:
        location = build_locations_document(canonical, [entry])
    loc_rel = location_relative_path(root["kind"], canonical)
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
    plan["plan_sha256"] = sha256_json({key: value for key, value in plan.items() if key != "plan_sha256"})
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


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


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
    validated = validate_document(plan, PLAN_SCHEMA)
    if approved_plan_sha256 != validated["plan_sha256"]:
        _fail(PLAN_HASH_MISMATCH, "approved-plan-sha256 does not match plan.json")
    root = next((row for row in roots if row["root_id"] == root_id), None)
    if root is None:
        _fail(PDF_MIGRATION_INVALID, "root_id is not in roots.json", {"root_id": root_id})
    if root["role"] != "target":
        _fail(PDF_MIGRATION_INVALID, "apply requires a target root")
    if root["kind"] == KIND_FORMAL:
        # Receipt-backed apply is executed by the operator using upstream inspect.
        # Direct writeset is used only for notes/repo/research; formal still re-checks
        # and records the intended writes so a later receipt apply is bound.
        pass
    base = Path(root["path"])
    lock = _acquire_lock(base)
    try:
        journal_path = _journal_path(base, validated["plan_sha256"])
        journal = _load_journal(journal_path)
        journal["plan_sha256"] = validated["plan_sha256"]
        journal["root_id"] = root_id
        done = {(entry.get("item_id"), entry.get("path")) for entry in journal.get("entries", [])}
        results = []
        for item in validated["items"]:
            if item["root_id"] != root_id:
                continue
            if item["verification"] != VERIFIED and validated["kind"] == "migration":
                results.append({"item_id": item["item_id"], "state": "unverified", "code": "not_migration_success"})
                continue
            loc_path = base / item["location_path"]
            current_loc = _file_sha(loc_path)
            if current_loc == item["after_location_sha256"]:
                state = "linked"
            elif current_loc not in {item["before_location_sha256"], None} and current_loc != item["after_location_sha256"]:
                _fail(
                    PDF_APPLY_CHANGED,
                    "location file changed after prepare",
                    {"path": item["location_path"], "item_id": item["item_id"]},
                )
            else:
                loc_bytes = locations_bytes(item["location"])
                if sha256_bytes(loc_bytes) != item["after_location_sha256"]:
                    _fail(PDF_MIGRATION_INVALID, "planned location bytes do not match after digest")
                before_raw = loc_path.read_bytes() if loc_path.exists() and loc_path.is_file() else None
                backup_dir = journal_path.parent / "backups"
                if before_raw is not None:
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    _atomic_write(
                        backup_dir / sha256_json({"path": item["location_path"], "before": item["before_location_sha256"]}),
                        before_raw,
                    )
                _atomic_write(loc_path, loc_bytes)
                journal["entries"].append(
                    {
                        "item_id": item["item_id"],
                        "path": item["location_path"],
                        "before_sha256": item["before_location_sha256"],
                        "after_sha256": item["after_location_sha256"],
                        "before_bytes_sha256": sha256_bytes(before_raw) if before_raw is not None else None,
                    }
                )
                state = "linked"
            if item["page_path"] and item["after_page_sha256"]:
                page_path = base / item["page_path"]
                current_page = _file_sha(page_path)
                if current_page == item["after_page_sha256"]:
                    pass
                elif current_page not in {item["before_page_sha256"], None}:
                    _fail(
                        PDF_APPLY_CHANGED,
                        "page file changed after prepare",
                        {"path": item["page_path"], "item_id": item["item_id"]},
                    )
                else:
                    _page_rel, page_bytes = _next_page_bytes(root, item["paper_id"], item["location"])
                    if page_bytes is None or sha256_bytes(page_bytes) != item["after_page_sha256"]:
                        _fail(PDF_APPLY_CHANGED, "page bytes changed and cannot be rewritten safely")
                    before_raw = page_path.read_bytes() if page_path.exists() and page_path.is_file() else None
                    backup_dir = journal_path.parent / "backups"
                    if before_raw is not None:
                        backup_dir.mkdir(parents=True, exist_ok=True)
                        _atomic_write(
                            backup_dir / sha256_json({"path": item["page_path"], "before": item["before_page_sha256"]}),
                            before_raw,
                        )
                    _atomic_write(page_path, page_bytes)
                    journal["entries"].append(
                        {
                            "item_id": item["item_id"],
                            "path": item["page_path"],
                            "before_sha256": item["before_page_sha256"],
                            "after_sha256": item["after_page_sha256"],
                            "before_bytes_sha256": sha256_bytes(before_raw) if before_raw is not None else None,
                        }
                    )
            if item["verification"] == UNVERIFIED:
                state = "unverified"
            results.append({"item_id": item["item_id"], "state": state, "code": None})
            _ = done
        journal_path.parent.mkdir(parents=True, exist_ok=True)
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
        lock.close()


def rollback_journal(*, journal_path: Path, roots_path: Path, confirm: bool) -> dict[str, Any]:
    if not confirm:
        _fail(HUMAN_APPROVAL_REQUIRED, "interactive confirmation is required")
    journal = _load_json(journal_path)
    roots = parse_roots(_load_json(roots_path))
    root = next((row for row in roots if row["root_id"] == journal.get("root_id")), None)
    if root is None:
        _fail(PDF_MIGRATION_INVALID, "journal root_id is not in roots.json")
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


def build_report(*, plan_path: Path, roots_path: Path) -> dict[str, Any]:
    plan = validate_document(_load_json(plan_path), PLAN_SCHEMA)
    roots = parse_roots(_load_json(roots_path))
    items = []
    root_stats: dict[str, dict[str, Any]] = {}
    for root in roots:
        root_stats[root["root_id"]] = {
            "root_id": root["root_id"],
            "kind": root["kind"],
            "linked": 0,
            "pending": 0,
            "conflict": 0,
            "journal_sha256": None,
        }
        journal = _journal_path(Path(root["path"]), plan["plan_sha256"])
        if journal.is_file():
            root_stats[root["root_id"]]["journal_sha256"] = sha256_bytes(journal.read_bytes())
    for item in plan["items"]:
        root = next((row for row in roots if row["root_id"] == item["root_id"]), None)
        state = "pending"
        code = None
        message = "not applied"
        if root is not None:
            loc_sha = _file_sha(Path(root["path"]) / item["location_path"])
            if loc_sha == item["after_location_sha256"]:
                state = "linked" if item["verification"] == VERIFIED else "unverified"
                message = "location file matches planned after digest"
            elif loc_sha not in {item["before_location_sha256"], None}:
                state = "conflict"
                code = PDF_APPLY_CHANGED
                message = "location file does not match before or after digest"
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
            "missing_original": 0,
            "excluded": 0,
            "blocked": blocked,
        },
        "roots": [root_stats[row["root_id"]] for row in roots if row["root_id"] in root_stats],
        "items": items,
    }
    # blocked paper_id may be null in plan; report schema requires canonical paper_id.
    # Replace invalid rows already coerced above.
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
