"""Paper maintenance: list/edit, reversible archive/restore, replace, and recovery.

Replacement journals may complete with outcome=aborted-before-staging when a
pre-staging attempt is safely abandoned: the old live paper is unchanged, no
replacement is reported, the owned stage is removed only after a complete
native-layout check, and the settled event is not a backup blocker.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki_research.light_index import (
    _index_is_current,
    _load_index,
    _load_paper,
    _paper_dirs,
    classify_index_tree,
)
from video_paper_wiki_research.light_library_state import (
    ARCHIVE_DIRNAME,
    ARCHIVE_EVENT_FIELDS,
    ARCHIVE_EVENT_SCHEMA,
    ARCHIVE_MANIFEST_FIELDS,
    ARCHIVE_SCHEMA,
    FILE_INVENTORY_FIELDS,
    LIBRARY_DIRNAME,
    LOCKS_DIRNAME,
    OPERATIONS_DIRNAME,
    LIBRARY_SCHEMA,
    LIGHT_LIBRARY_CONFLICT,
    LIGHT_LIBRARY_INVALID,
    LIGHT_LIBRARY_NEEDS_RECOVERY,
    LIGHT_WORKSPACE_BUSY,
    OPERATION_SCHEMA,
    OUTCOME_ABORTED_BEFORE_STAGING,
    OUTCOME_ARCHIVED,
    OUTCOME_REPLACED,
    OUTCOME_RESTORED,
    PAPER_DIRNAME,
    SOURCE_INVALID,
    STAGING_DIRNAME,
    STAGING_OWNER_FIELDS,
    STAGING_OWNER_SCHEMA,
    TRANSACTIONS_DIR,
    WORKFLOW_DIRNAME,
    WORKSPACE_LOCK_NAME,
    _Busy,
    archive_dir,
    chain_has_symlink,
    closed,
    ensure_library_dirs,
    exclusive_workspace_lock,
    fail,
    file_is_hardlinked,
    inventory_row,
    is_hex_id,
    is_paper_id,
    is_regular_dir,
    is_regular_file,
    iter_operation_files,
    knowledge_staging_nonempty,
    library_diagnostics,
    limits_ok,
    list_names,
    load_persisted_object,
    new_hex_id,
    normalize_tags,
    normalize_title,
    ok_result,
    operation_path,
    paper_digest,
    pending_operation_ids,
    persisted_bytes,
    posix_rel,
    recognized_operation,
    require_hex_id,
    require_paper_id,
    require_workspace,
    run_library_inject,
    sha256_bytes,
    source_from_file_inventory,
    staging_dir,
    validate_directory_inventory,
    validate_file_inventory,
    validate_stage_file_inventory,
    walk_regular_tree,
    write_bytes_atomic,
    write_bytes_create_only,
    write_persisted_atomic,
)
from video_paper_wiki_research.light_pdf import (
    _try_lock,
    classify_paper_dir,
    classify_transaction_tree,
    extract_pdf,
    lock_is_held,
    lock_path_for,
)
from video_paper_wiki_research.light_workspace import inspect_workspace

PRIOR_NOTES_NAME = "prior-paper-notes.md"
REINDEX_ACTION = "Rebuild the lexical index with build_index before querying or exporting contexts."
RECOVER_ACTION = "Call recover_library to finish or inspect the pending library operation."


def _paper_lock(workspace: Path, digest: str):
    lock = _try_lock(workspace, digest)
    if lock is None:
        return None
    return lock


def _index_state(workspace: Path) -> tuple[str, str | None]:
    loaded: list[dict[str, Any]] = []
    for directory in _paper_dirs(workspace):
        classified = classify_paper_dir(directory, directory.name)
        if classified["kind"] == "complete":
            loaded.append(classified["loaded"])
    stored = _load_index(workspace)
    if stored is None:
        path = workspace / ".light-index" / "index.v1.json"
        if path.exists() or path.is_symlink():
            return "invalid", None
        return "missing", None
    index_id = stored.get("index_id") if type(stored.get("index_id")) is str else None
    if _index_is_current(stored, loaded):
        return "current", index_id
    return "stale", index_id


def _current_tags(meta: Mapping[str, Any]) -> list[str]:
    tags = meta.get("tags")
    if type(tags) is not list:
        return []
    if any(type(item) is not str for item in tags):
        return []
    return list(tags)


def _paper_summary(loaded: Mapping[str, Any]) -> dict[str, Any]:
    meta = loaded["metadata"]
    warnings = meta.get("warnings")
    warning_rows = [item for item in warnings if type(item) is str] if type(warnings) is list else []
    return {
        "paper_id": loaded["paper_id"],
        "title": loaded["title"],
        "tags": _current_tags(meta),
        "page_count": loaded["page_count"],
        "markdown_path": loaded["markdown_path"],
        "markdown_sha256": loaded["markdown_sha256"],
        "source_json_sha256": loaded["source_json_sha256"],
        "metadata_stale": bool(loaded["metadata_stale"]),
        "warnings": warning_rows,
    }


def _scan_paper_tree(paper_dir: Path, *, original_prefix: str) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    directories: list[str] = [original_prefix]
    total = 0
    if paper_dir.is_symlink() or not paper_dir.is_dir():
        return {"ok": False, "status": LIGHT_LIBRARY_INVALID, "message": "paper path is not a regular directory"}
    for dirpath, dirnames, filenames in os.walk(paper_dir, followlinks=False):
        base = Path(dirpath)
        dirnames.sort()
        filenames.sort()
        rel_dir = posix_rel(str(base.relative_to(paper_dir))) if base != paper_dir else ""
        for name in list(dirnames):
            child = base / name
            child_rel = f"{original_prefix}/{rel_dir}/{name}".replace("//", "/") if rel_dir else f"{original_prefix}/{name}"
            if child.is_symlink() or not child.is_dir():
                return {
                    "ok": False,
                    "status": LIGHT_LIBRARY_INVALID,
                    "message": f"refusing unsafe directory extra {child_rel}",
                }
            directories.append(child_rel)
        for name in filenames:
            child = base / name
            child_rel = f"{original_prefix}/{rel_dir}/{name}".replace("//", "/") if rel_dir else f"{original_prefix}/{name}"
            from video_paper_wiki_research.light_library_state import classify_text_file

            classified = classify_text_file(child, label=child_rel)
            if classified["kind"] == "unsupported-size":
                return {
                    "ok": False,
                    "status": LIGHT_LIBRARY_INVALID,
                    "message": classified["reason"],
                    "path": child_rel,
                }
            if classified["kind"] != "ok":
                return {
                    "ok": False,
                    "status": LIGHT_LIBRARY_INVALID,
                    "message": classified.get("reason") or f"refusing unsafe extra {child_rel}",
                    "path": child_rel,
                }
            files.append(
                {
                    "original_relative_path": child_rel,
                    "archive_relative_path": f"paper/{rel_dir}/{name}".replace("//", "/") if rel_dir else f"paper/{name}",
                    "size_bytes": classified["size_bytes"],
                    "sha256": classified["sha256"],
                }
            )
            total += classified["size_bytes"]
    files.sort(key=lambda item: item["original_relative_path"])
    directories = sorted(set(directories))
    limit = limits_ok(len(files), total)
    if limit:
        return {"ok": False, "status": LIGHT_LIBRARY_INVALID, "message": limit}
    return {"ok": True, "files": files, "directories": directories, "total_bytes": total}


def _archive_manifest(*, archive_id: str, paper_id: str, digest: str, scanned: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": ARCHIVE_SCHEMA,
        "archive_id": archive_id,
        "paper_id": paper_id,
        "original_directory": f"{PAPER_DIRNAME}/{digest}",
        "transport_directory": "paper",
        "files": list(scanned["files"]),
        "directories": list(scanned["directories"]),
    }


def _same_file_inventory(left: list[Mapping[str, Any]], right: list[Mapping[str, Any]]) -> bool:
    def _rows(items: list[Mapping[str, Any]]) -> list[tuple[str, str, int, str]] | None:
        rows: list[tuple[str, str, int, str]] = []
        seen: set[str] = set()
        for item in items:
            if type(item) is not dict or set(item) != FILE_INVENTORY_FIELDS:
                return None
            original = item.get("original_relative_path")
            archive_rel = item.get("archive_relative_path")
            size = item.get("size_bytes")
            digest = item.get("sha256")
            if type(original) is not str or type(archive_rel) is not str:
                return None
            if type(size) is not int or type(size) is bool or type(digest) is not str:
                return None
            if original in seen:
                return None
            seen.add(original)
            rows.append((original, archive_rel, size, digest))
        rows.sort()
        return rows

    left_rows = _rows(list(left))
    right_rows = _rows(list(right))
    return left_rows is not None and left_rows == right_rows


def _validate_archive_manifest_shape(manifest: Mapping[str, Any], archive_root: Path) -> dict[str, Any] | None:
    if type(manifest) is not dict or set(manifest) != ARCHIVE_MANIFEST_FIELDS:
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive manifest has unknown or missing top-level fields"}
    if manifest.get("schema") != ARCHIVE_SCHEMA:
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive manifest schema is not recognized"}
    if manifest.get("archive_id") != archive_root.name or not is_hex_id(manifest.get("archive_id")):
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive manifest archive_id does not match the archive directory"}
    paper_id = manifest.get("paper_id")
    if not is_paper_id(paper_id):
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive manifest paper_id is invalid"}
    digest = paper_digest(str(paper_id))
    if manifest.get("original_directory") != f"{PAPER_DIRNAME}/{digest}":
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive original directory does not match paper identity"}
    if manifest.get("transport_directory") != "paper":
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive transport directory must be paper"}
    if not validate_file_inventory(manifest.get("files")):
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive file inventory is invalid"}
    if not validate_directory_inventory(manifest.get("directories")):
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive directory inventory is invalid"}
    if f"{PAPER_DIRNAME}/{digest}" not in manifest["directories"]:
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive directory inventory omits the paper directory"}
    return None


def _actual_original_directories(payload: Path, digest: str) -> list[str] | None:
    actual = [f"{PAPER_DIRNAME}/{digest}"]
    for dirpath, dirnames, _filenames in os.walk(payload, followlinks=False):
        base = Path(dirpath)
        dirnames.sort()
        for name in list(dirnames):
            child = base / name
            if child.is_symlink() or not child.is_dir():
                return None
            rel = posix_rel(str(child.relative_to(payload)))
            actual.append(f"{PAPER_DIRNAME}/{digest}/{rel}")
    return sorted(set(actual))


def _validate_archive_payload(archive_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    shape = _validate_archive_manifest_shape(manifest, archive_root)
    if shape is not None:
        return shape
    paper_id = str(manifest["paper_id"])
    digest = paper_digest(paper_id)
    payload = archive_root / "paper"
    if not is_regular_dir(payload):
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive transport payload is missing"}
    files = manifest["files"]
    directories = list(manifest["directories"])
    expected_files = {item["archive_relative_path"]: item for item in files}
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(payload, followlinks=False):
        base = Path(dirpath)
        dirnames.sort()
        filenames.sort()
        for name in dirnames:
            child = base / name
            if child.is_symlink() or not child.is_dir():
                return {"status": LIGHT_LIBRARY_INVALID, "message": "archive payload contains an unsafe directory"}
        for name in filenames:
            child = base / name
            rel = "paper/" + posix_rel(str(child.relative_to(payload)))
            if child.is_symlink() or not child.is_file() or file_is_hardlinked(child):
                return {"status": LIGHT_LIBRARY_INVALID, "message": f"archive payload file is unsafe: {rel}"}
            expected = expected_files.get(rel)
            if expected is None:
                return {"status": LIGHT_LIBRARY_INVALID, "message": f"archive payload has unexpected file {rel}"}
            data = child.read_bytes()
            if len(data) != expected.get("size_bytes") or sha256_bytes(data) != expected.get("sha256"):
                return {"status": LIGHT_LIBRARY_INVALID, "message": f"archive payload hash mismatch for {rel}"}
            original = expected.get("original_relative_path")
            if original != f"{PAPER_DIRNAME}/{digest}/" + posix_rel(str(child.relative_to(payload))):
                return {"status": LIGHT_LIBRARY_INVALID, "message": f"archive original/transport mapping is invalid for {rel}"}
            seen.add(rel)
    if seen != set(expected_files):
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive payload set does not match the manifest"}
    actual_dirs = _actual_original_directories(payload, digest)
    if actual_dirs is None or actual_dirs != directories:
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive directory inventory does not match the payload"}
    source_json = payload / "source.json"
    source_md = payload / "source.md"
    if not is_regular_file(source_json) or not is_regular_file(source_md):
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archived paper pair is incomplete"}
    try:
        meta = json.loads(source_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": SOURCE_INVALID, "message": "archived source.json is not valid JSON"}
    if type(meta) is not dict:
        return {"status": SOURCE_INVALID, "message": "archived source.json root must be an object"}
    if meta.get("paper_id") != paper_id:
        return {"status": SOURCE_INVALID, "message": "archived source.json identity does not match the original paper"}
    document = meta.get("document")
    if type(document) is not dict or document.get("path") != f"{PAPER_DIRNAME}/{digest}/source.md":
        return {"status": SOURCE_INVALID, "message": "archived source.md path must remain papers/<digest>/source.md"}
    source = meta.get("source") if type(meta.get("source")) is dict else {}
    if source.get("sha256") != digest:
        return {"status": SOURCE_INVALID, "message": "archived source identity does not match the original digest"}
    return None


def _live_matches_file_inventory(paper_dir: Path, digest: str, files: list[Mapping[str, Any]], directories: list[str] | None) -> dict[str, Any] | None:
    scanned = _scan_paper_tree(paper_dir, original_prefix=f"{PAPER_DIRNAME}/{digest}")
    if not scanned.get("ok"):
        return {"status": str(scanned.get("status") or LIGHT_LIBRARY_INVALID), "message": str(scanned.get("message") or "live paper inventory is invalid")}
    if not _same_file_inventory(list(scanned["files"]), list(files)):
        return {"status": LIGHT_LIBRARY_NEEDS_RECOVERY, "message": "live paper bytes do not match the frozen inventory"}
    if directories is not None and list(scanned["directories"]) != list(directories):
        return {"status": LIGHT_LIBRARY_NEEDS_RECOVERY, "message": "live paper directories do not match the frozen inventory"}
    return None


def _archive_matches_operation(archive_root: Path, operation: Mapping[str, Any]) -> dict[str, Any] | None:
    digest = paper_digest(str(operation["paper_id"]))
    manifest = _archive_manifest(
        archive_id=str(operation["archive_id"]),
        paper_id=str(operation["paper_id"]),
        digest=digest,
        scanned={"files": operation["file_inventory"], "directories": operation["directories"]},
    )
    error = _validate_archive_payload(archive_root, manifest)
    if error:
        return error
    persisted = load_persisted_object(archive_root / "manifest.json")
    if persisted is None:
        return {"status": LIGHT_LIBRARY_INVALID, "message": "archive manifest is missing or not persisted canonical JSON"}
    shape = _validate_archive_manifest_shape(persisted, archive_root)
    if shape is not None:
        return shape
    if not _same_file_inventory(list(persisted.get("files") or []), list(operation["file_inventory"])):
        return {"status": LIGHT_LIBRARY_NEEDS_RECOVERY, "message": "archive manifest does not match the frozen journal inventory"}
    if list(persisted.get("directories") or []) != list(operation["directories"]):
        return {"status": LIGHT_LIBRARY_NEEDS_RECOVERY, "message": "archive directory inventory does not match the frozen journal"}
    return None


def _write_archive_event(archive_root: Path, event: Mapping[str, Any]) -> None:
    write_persisted_atomic(archive_root / "event.json", event)


def _load_archive_bundle(archive_root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    manifest = load_persisted_object(archive_root / "manifest.json")
    event = load_persisted_object(archive_root / "event.json")
    return manifest, event


def _iter_archives(workspace: Path) -> list[dict[str, Any]]:
    root = workspace / LIBRARY_DIRNAME / ARCHIVE_DIRNAME
    rows: list[dict[str, Any]] = []
    if not is_regular_dir(root):
        return rows
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        if item.is_symlink() or not item.is_dir() or not is_hex_id(item.name):
            continue
        manifest, event = _load_archive_bundle(item)
        if manifest is None or manifest.get("schema") != ARCHIVE_SCHEMA:
            continue
        payload_present = is_regular_dir(item / "paper")
        state = "archived" if payload_present else "restored"
        if event and event.get("state") in {"archived", "restored"}:
            state = str(event["state"])
        files = manifest.get("files") if type(manifest.get("files")) is list else []
        rows.append(
            {
                "archive_id": item.name,
                "paper_id": manifest.get("paper_id"),
                "state": state,
                "payload_present": payload_present,
                "file_count": len(files),
            }
        )
    return rows


def _matching_archives(workspace: Path, paper_id: str, *, payload_present: bool | None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for row in _iter_archives(workspace):
        if row.get("paper_id") != paper_id:
            continue
        if payload_present is not None and bool(row.get("payload_present")) != payload_present:
            continue
        found.append(row)
    return found


def _write_operation(workspace: Path, operation: Mapping[str, Any]) -> None:
    write_persisted_atomic(operation_path(workspace, str(operation["operation_id"])), operation)


def _live_present(workspace: Path, digest: str) -> bool:
    return os.path.lexists(workspace / PAPER_DIRNAME / digest)


def _complete_live(workspace: Path, digest: str) -> bool:
    classified = classify_paper_dir(workspace / PAPER_DIRNAME / digest, digest)
    return classified["kind"] == "complete"


def _prior_notes_markdown(*, old_paper_id: str, archive_id: str, scanned: Mapping[str, Any]) -> str:
    lines = [
        "# Prior paper notes",
        "",
        f"These notes belong to the replaced paper `{old_paper_id}` archived as `{archive_id}`.",
        "They are not statements about the current PDF.",
        "",
    ]
    for item in scanned.get("files") or []:
        original = item.get("original_relative_path")
        archive_rel = item.get("archive_relative_path")
        if type(original) is not str or type(archive_rel) is not str:
            continue
        name = Path(original).name
        if name in {"source.md", "source.json"}:
            continue
        link = f"../../{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}/{archive_id}/{archive_rel}"
        lines.append(f"- [`{name}`]({link})")
    if len(lines) == 5:
        lines.append("- No additional user note files were present on the replaced paper.")
    lines.append("")
    return "\n".join(lines)


def _retained_note_paths(archive_id: str, scanned: Mapping[str, Any], *, new_paper_id: str | None = None) -> list[str]:
    paths: list[str] = []
    if is_paper_id(new_paper_id):
        paths.append(f"{PAPER_DIRNAME}/{paper_digest(str(new_paper_id))}/{PRIOR_NOTES_NAME}")
    for item in scanned.get("files") or []:
        archive_rel = item.get("archive_relative_path")
        original = item.get("original_relative_path")
        if type(archive_rel) is not str or type(original) is not str:
            continue
        if Path(original).name in {"source.md", "source.json"}:
            continue
        paths.append(f"{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}/{archive_id}/{archive_rel}")
    return paths


def list_papers(workspace_root: Path) -> dict[str, Any]:
    """Read-only library listing. Does not repair state."""
    workspace = require_workspace(workspace_root)
    inspect = inspect_workspace(workspace)
    papers = []
    diagnostics = list(inspect.get("diagnostics") or [])
    for directory in _paper_dirs(workspace):
        classified = classify_paper_dir(directory, directory.name)
        if classified["kind"] == "complete":
            papers.append(_paper_summary(classified["loaded"]))
    papers.sort(key=lambda item: item["paper_id"])
    archives = _iter_archives(workspace)
    pending = pending_operation_ids(workspace)
    index_state, index_id = _index_state(workspace)
    return ok_result(
        f"listed {len(papers)} live papers",
        schema=LIBRARY_SCHEMA,
        workspace_root=str(workspace),
        papers=papers,
        archives=archives,
        pending_operation_ids=pending,
        diagnostics=diagnostics,
        index_state=index_state,
        index_id=index_id,
        inspect_state=inspect.get("state"),
    )


def update_paper_metadata(
    workspace_root: Path,
    paper_id: str,
    *,
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    paper_id = require_paper_id(paper_id)
    if title is not None:
        normalized_title = normalize_title(title)
        if normalized_title is None:
            fail(LIGHT_LIBRARY_INVALID, "title must be 1-500 characters without control characters")
        title = normalized_title
    if tags is not None:
        normalized_tags = normalize_tags(tags)
        if normalized_tags is None:
            fail(LIGHT_LIBRARY_INVALID, "tags must be at most 30 distinct 1-100 character labels")
        tags = normalized_tags
    workspace = require_workspace(workspace_root)
    digest = paper_digest(paper_id)
    try:
        with exclusive_workspace_lock(workspace):
            lock = _paper_lock(workspace, digest)
            if lock is None:
                return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation owns this paper digest", paper_id=paper_id)
            try:
                return _update_metadata_locked(workspace, paper_id, title=title, tags=tags)
            finally:
                lock.release()
    except _Busy:
        return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation currently owns this workspace", paper_id=paper_id)


def _update_metadata_locked(
    workspace: Path,
    paper_id: str,
    *,
    title: str | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    digest = paper_digest(paper_id)
    paper_dir = workspace / PAPER_DIRNAME / digest
    classified = classify_paper_dir(paper_dir, digest)
    if classified["kind"] != "complete":
        return closed(
            LIGHT_LIBRARY_INVALID,
            classified.get("reason") or "selected paper is not a complete live paper",
            paper_id=paper_id,
        )
    loaded = classified["loaded"]
    meta = dict(loaded["metadata"])
    current_title = meta.get("title") if type(meta.get("title")) is str else loaded["title"]
    current_tags = _current_tags(meta)
    next_title = current_title if title is None else title
    next_tags = current_tags if tags is None else tags
    if next_title == current_title and next_tags == current_tags:
        return ok_result(
            "metadata is unchanged",
            paper_id=paper_id,
            title=current_title,
            tags=list(current_tags),
            reused=True,
            metadata_path=str((paper_dir / "source.json").resolve()),
            next_actions=[],
        )
    meta["title"] = next_title
    meta["tags"] = list(next_tags)
    encoded = (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    dest = paper_dir / "source.json"
    write_bytes_atomic(dest, encoded, inject="after_metadata_tmp")
    return ok_result(
        "updated paper metadata; existing index is now stale",
        paper_id=paper_id,
        title=next_title,
        tags=list(next_tags),
        reused=False,
        metadata_path=str(dest.resolve()),
        next_actions=[REINDEX_ACTION],
    )


def archive_paper(workspace_root: Path, paper_id: str) -> dict[str, Any]:
    paper_id = require_paper_id(paper_id)
    workspace = require_workspace(workspace_root)
    digest = paper_digest(paper_id)
    try:
        with exclusive_workspace_lock(workspace):
            lock = _paper_lock(workspace, digest)
            if lock is None:
                return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation owns this paper digest", paper_id=paper_id)
            try:
                return _archive_locked(workspace, paper_id)
            finally:
                lock.release()
    except _Busy:
        return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation currently owns this workspace", paper_id=paper_id)


def _archive_locked(workspace: Path, paper_id: str, *, operation: dict[str, Any] | None = None) -> dict[str, Any]:
    digest = paper_digest(paper_id)
    live = workspace / PAPER_DIRNAME / digest
    matches = _matching_archives(workspace, paper_id, payload_present=True)
    live_exists = os.path.lexists(live)
    if operation is None and not live_exists:
        if len(matches) == 1:
            row = matches[0]
            return ok_result(
                "paper is already archived",
                paper_id=paper_id,
                archive_id=row["archive_id"],
                operation_id=None,
                reused=True,
                next_actions=[REINDEX_ACTION],
            )
        if len(matches) > 1:
            return closed(LIGHT_LIBRARY_CONFLICT, "multiple matching archives exist for this paper", paper_id=paper_id)
        return closed(LIGHT_LIBRARY_INVALID, "selected paper is not present", paper_id=paper_id)
    if matches and live_exists:
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "an archived copy already exists for this paper while a live directory is also present",
            paper_id=paper_id,
        )
    if operation is not None:
        dest_root = archive_dir(workspace, str(operation["archive_id"]))
        payload_present = is_regular_dir(dest_root / "paper")
        if payload_present and live_exists:
            return closed(
                LIGHT_LIBRARY_CONFLICT,
                "archive and live paper both exist unexpectedly",
                paper_id=paper_id,
                archive_id=operation["archive_id"],
                operation_id=operation["operation_id"],
            )
        if payload_present and not live_exists:
            error = _archive_matches_operation(dest_root, operation)
            if error:
                return closed(str(error.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), error["message"], paper_id=paper_id, archive_id=operation["archive_id"], operation_id=operation["operation_id"])
            operation = dict(operation)
            operation["phase"] = "archived"
            _write_operation(workspace, operation)
            return _finish_archive(workspace, operation, {"files": operation["file_inventory"]})
        if not payload_present and not live_exists:
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "neither archive payload nor live paper is present",
                paper_id=paper_id,
                archive_id=operation["archive_id"],
                operation_id=operation["operation_id"],
            )
        mismatch = _live_matches_file_inventory(live, digest, list(operation["file_inventory"]), list(operation["directories"]))
        if mismatch:
            return closed(str(mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), mismatch["message"], paper_id=paper_id, operation_id=operation["operation_id"])
    classified = classify_paper_dir(live, digest)
    if classified["kind"] != "complete":
        return closed(
            LIGHT_LIBRARY_INVALID,
            classified.get("reason") or "live paper is not a complete pair",
            paper_id=paper_id,
        )
    scanned = _scan_paper_tree(live, original_prefix=f"{PAPER_DIRNAME}/{digest}")
    if not scanned.get("ok"):
        return closed(str(scanned.get("status") or LIGHT_LIBRARY_INVALID), str(scanned.get("message") or "paper extras are unsafe"), paper_id=paper_id)
    if operation is not None and (
        not _same_file_inventory(list(scanned["files"]), list(operation["file_inventory"]))
        or list(scanned["directories"]) != list(operation["directories"])
    ):
        return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "live paper no longer matches the frozen archive inventory", paper_id=paper_id, operation_id=operation["operation_id"])
    ensure_library_dirs(workspace)
    if operation is None:
        operation_id = new_hex_id()
        archive_id = new_hex_id()
        operation = {
            "schema": OPERATION_SCHEMA,
            "operation_id": operation_id,
            "kind": "archive",
            "paper_id": paper_id,
            "archive_id": archive_id,
            "phase": "intent",
            "owned_relative_paths": [
                f"{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}/{archive_id}/",
                f"{LIBRARY_DIRNAME}/{OPERATIONS_DIRNAME}/{operation_id}.json",
            ],
            "source_inventory": source_from_file_inventory(scanned["files"]),
            "file_inventory": scanned["files"],
            "directories": scanned["directories"],
        }
        _write_operation(workspace, operation)
        run_library_inject("after_intent")
    archive_id = str(operation["archive_id"])
    operation_id = str(operation["operation_id"])
    dest_root = archive_dir(workspace, archive_id)
    payload = dest_root / "paper"
    if os.path.lexists(payload) and live_exists:
        return closed(LIGHT_LIBRARY_CONFLICT, "archive and live paper both exist unexpectedly", paper_id=paper_id, archive_id=archive_id, operation_id=operation_id)
    if is_regular_dir(payload) and not live_exists:
        error = _archive_matches_operation(dest_root, operation)
        if error:
            return closed(str(error.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), error["message"], paper_id=paper_id, archive_id=archive_id, operation_id=operation_id)
        operation = dict(operation)
        operation["phase"] = "archived"
        _write_operation(workspace, operation)
        return _finish_archive(workspace, operation, {"files": operation["file_inventory"]})
    if os.path.lexists(dest_root) and not is_regular_dir(dest_root):
        return closed(LIGHT_LIBRARY_CONFLICT, "archive destination is unsafe", paper_id=paper_id, archive_id=archive_id)
    dest_root.mkdir(exist_ok=True)
    frozen = {"files": operation["file_inventory"], "directories": operation["directories"]}
    manifest = _archive_manifest(archive_id=archive_id, paper_id=paper_id, digest=digest, scanned=frozen)
    write_persisted_atomic(dest_root / "manifest.json", manifest)
    _write_archive_event(
        dest_root,
        {
            "schema": ARCHIVE_EVENT_SCHEMA,
            "archive_id": archive_id,
            "paper_id": paper_id,
            "operation_id": operation_id,
            "state": "archived",
        },
    )
    again = _live_matches_file_inventory(live, digest, list(operation["file_inventory"]), list(operation["directories"]))
    if again:
        return closed(LIGHT_LIBRARY_CONFLICT, again["message"], paper_id=paper_id, operation_id=operation_id)
    run_library_inject("before_archive_move")
    os.rename(live, payload)
    run_library_inject("after_archive_move")
    error = _archive_matches_operation(dest_root, operation)
    if error:
        return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, error["message"], paper_id=paper_id, archive_id=archive_id, operation_id=operation_id)
    operation = dict(operation)
    operation["phase"] = "archived"
    _write_operation(workspace, operation)
    return _finish_archive(workspace, operation, frozen)


def _finish_archive(workspace: Path, operation: Mapping[str, Any], scanned: Mapping[str, Any]) -> dict[str, Any]:
    dest_root = archive_dir(workspace, str(operation["archive_id"]))
    error = _archive_matches_operation(dest_root, operation)
    if error:
        return closed(str(error.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), error["message"], paper_id=operation["paper_id"], archive_id=operation["archive_id"], operation_id=operation["operation_id"])
    if os.path.lexists(workspace / PAPER_DIRNAME / paper_digest(str(operation["paper_id"]))):
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "archive payload and live paper both exist",
            paper_id=operation["paper_id"],
            archive_id=operation["archive_id"],
            operation_id=operation["operation_id"],
        )
    operation = dict(operation)
    operation["phase"] = "complete"
    operation["outcome"] = OUTCOME_ARCHIVED
    _write_operation(workspace, operation)
    return ok_result(
        "archived paper; original PDF was not copied or deleted",
        paper_id=operation["paper_id"],
        archive_id=operation["archive_id"],
        operation_id=operation["operation_id"],
        reused=False,
        file_count=len(scanned.get("files") or operation.get("file_inventory") or []),
        next_actions=[REINDEX_ACTION],
    )


def restore_paper(workspace_root: Path, archive_id: str) -> dict[str, Any]:
    archive_id = require_hex_id(archive_id, name="archive_id")
    workspace = require_workspace(workspace_root)
    try:
        with exclusive_workspace_lock(workspace):
            return _restore_locked(workspace, archive_id)
    except _Busy:
        return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation currently owns this workspace", archive_id=archive_id)


def _restore_locked(
    workspace: Path,
    archive_id: str,
    *,
    operation: dict[str, Any] | None = None,
    acquire_paper_lock: bool = True,
) -> dict[str, Any]:
    dest_root = archive_dir(workspace, archive_id)
    if not is_regular_dir(dest_root):
        return closed(LIGHT_LIBRARY_INVALID, "archive_id is not present", archive_id=archive_id)
    manifest, event = _load_archive_bundle(dest_root)
    if manifest is None:
        return closed(LIGHT_LIBRARY_INVALID, "archive manifest is missing or not persisted canonical JSON", archive_id=archive_id)
    paper_id = manifest.get("paper_id")
    if not is_paper_id(paper_id):
        return closed(LIGHT_LIBRARY_INVALID, "archive manifest paper_id is invalid", archive_id=archive_id)
    digest = paper_digest(str(paper_id))
    lock = _paper_lock(workspace, digest) if acquire_paper_lock else None
    if acquire_paper_lock and lock is None:
        return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation owns this paper digest", paper_id=paper_id, archive_id=archive_id)
    try:
        live = workspace / PAPER_DIRNAME / digest
        payload = dest_root / "paper"
        payload_present = is_regular_dir(payload)
        live_exists = os.path.lexists(live)
        shape = _validate_archive_manifest_shape(manifest, dest_root)
        if shape is not None:
            return closed(shape["status"], shape["message"], paper_id=paper_id, archive_id=archive_id)
        frozen_files = list(manifest["files"])
        frozen_dirs = list(manifest["directories"])
        if operation is None and not payload_present and live_exists and _complete_live(workspace, digest):
            if event and event.get("state") == "restored":
                mismatch = _live_matches_file_inventory(live, digest, frozen_files, frozen_dirs)
                if mismatch is None:
                    return ok_result(
                        "archive is already restored",
                        paper_id=paper_id,
                        archive_id=archive_id,
                        operation_id=None if operation is None else operation.get("operation_id"),
                        reused=True,
                        next_actions=[REINDEX_ACTION],
                    )
            return closed(LIGHT_LIBRARY_CONFLICT, "live paper slot already exists and is not an exact restore of this archive", paper_id=paper_id, archive_id=archive_id)
        if live_exists and payload_present:
            return closed(LIGHT_LIBRARY_CONFLICT, "archive payload and live paper both exist", paper_id=paper_id, archive_id=archive_id)
        if not payload_present and not live_exists:
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "neither archive payload nor live paper is present", paper_id=paper_id, archive_id=archive_id)
        error = _validate_archive_payload(dest_root, manifest) if payload_present else None
        if error:
            return closed(error["status"], error["message"], paper_id=paper_id, archive_id=archive_id)
        ensure_library_dirs(workspace)
        if operation is None:
            operation = {
                "schema": OPERATION_SCHEMA,
                "operation_id": new_hex_id(),
                "kind": "restore",
                "paper_id": paper_id,
                "archive_id": archive_id,
                "phase": "intent",
                "owned_relative_paths": [
                    f"{PAPER_DIRNAME}/{digest}/",
                    f"{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}/{archive_id}/",
                ],
                "source_inventory": source_from_file_inventory(frozen_files),
                "file_inventory": frozen_files,
                "directories": frozen_dirs,
            }
            _write_operation(workspace, operation)
            run_library_inject("after_intent")
        else:
            if not _same_file_inventory(list(operation["file_inventory"]), frozen_files) or list(operation["directories"]) != frozen_dirs:
                return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "restore journal inventory does not match the archive manifest", paper_id=paper_id, archive_id=archive_id, operation_id=operation["operation_id"])
        papers_root = workspace / PAPER_DIRNAME
        if not is_regular_dir(papers_root):
            papers_root.mkdir(exist_ok=True)
        if not payload_present and live_exists:
            mismatch = _live_matches_file_inventory(live, digest, list(operation["file_inventory"]), list(operation["directories"]))
            if mismatch:
                return closed(str(mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), mismatch["message"], paper_id=paper_id, archive_id=archive_id, operation_id=operation["operation_id"])
            if not _complete_live(workspace, digest):
                return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "restored directory is not a valid live paper", paper_id=paper_id, archive_id=archive_id)
            return _finish_restore(workspace, dest_root, operation, reused=True)
        if os.path.lexists(live):
            return closed(LIGHT_LIBRARY_CONFLICT, "refusing to overwrite an existing live paper", paper_id=paper_id, archive_id=archive_id)
        run_library_inject("before_restore_move")
        os.rename(payload, live)
        run_library_inject("after_restore_move")
        mismatch = _live_matches_file_inventory(live, digest, list(operation["file_inventory"]), list(operation["directories"]))
        if mismatch:
            return closed(str(mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), mismatch["message"], paper_id=paper_id, archive_id=archive_id, operation_id=operation["operation_id"])
        if not _complete_live(workspace, digest):
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "restored directory is not a valid live paper", paper_id=paper_id, archive_id=archive_id)
        return _finish_restore(workspace, dest_root, operation, reused=False)
    finally:
        if lock is not None:
            lock.release()


def _finish_restore(workspace: Path, dest_root: Path, operation: Mapping[str, Any], *, reused: bool) -> dict[str, Any]:
    paper_id = str(operation["paper_id"])
    archive_id = str(operation["archive_id"])
    event = {
        "schema": ARCHIVE_EVENT_SCHEMA,
        "archive_id": archive_id,
        "paper_id": paper_id,
        "operation_id": operation["operation_id"],
        "state": "restored",
    }
    if set(event) != ARCHIVE_EVENT_FIELDS:
        return closed(LIGHT_LIBRARY_INVALID, "archive event shape is invalid", paper_id=paper_id, archive_id=archive_id)
    _write_archive_event(dest_root, event)
    operation = dict(operation)
    operation["phase"] = "complete"
    operation["outcome"] = OUTCOME_RESTORED
    _write_operation(workspace, operation)
    return ok_result(
        "recognized an already completed restore move" if reused else "restored archived paper to its original slot",
        paper_id=paper_id,
        archive_id=archive_id,
        operation_id=operation["operation_id"],
        reused=reused,
        next_actions=[REINDEX_ACTION],
    )


def replace_paper(workspace_root: Path, paper_id: str, pdf_path: Path, *, title: str | None = None) -> dict[str, Any]:
    paper_id = require_paper_id(paper_id)
    if title is not None:
        normalized = normalize_title(title)
        if normalized is None:
            fail(LIGHT_LIBRARY_INVALID, "title must be 1-500 characters without control characters")
        title = normalized
    workspace = require_workspace(workspace_root)
    digest = paper_digest(paper_id)
    try:
        with exclusive_workspace_lock(workspace):
            lock = _paper_lock(workspace, digest)
            if lock is None:
                return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation owns this paper digest", paper_id=paper_id)
            try:
                return _replace_locked(workspace, paper_id, Path(pdf_path), title=title)
            finally:
                lock.release()
    except _Busy:
        return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation currently owns this workspace", paper_id=paper_id)


def _iter_recognized_operations(workspace: Path) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in iter_operation_files(workspace):
        loaded = recognized_operation(load_persisted_object(path), filename=path.name)
        if loaded is not None:
            found.append((path, loaded))
    return found


def _matching_replace_events(
    workspace: Path,
    *,
    paper_id: str,
    new_paper_id: str,
    title: str | None,
    phase: str | None = None,
    outcome: str | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for _path, operation in _iter_recognized_operations(workspace):
        if operation.get("kind") != "replace":
            continue
        if operation.get("paper_id") != paper_id or operation.get("new_paper_id") != new_paper_id:
            continue
        if operation.get("title") != title:
            continue
        if phase is not None and operation.get("phase") != phase:
            continue
        if outcome is not None and operation.get("outcome") != outcome:
            continue
        matches.append(operation)
    return matches


def _reuse_completed_replace(workspace: Path, operation: Mapping[str, Any]) -> dict[str, Any]:
    paper_id = str(operation["paper_id"])
    new_paper_id = str(operation["new_paper_id"])
    archive_id = str(operation["archive_id"])
    old_digest = paper_digest(paper_id)
    new_digest = paper_digest(new_paper_id)
    if _complete_live(workspace, old_digest):
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "the original paper was recreated live after replacement",
            paper_id=paper_id,
            new_paper_id=new_paper_id,
            archive_id=archive_id,
            operation_id=operation["operation_id"],
        )
    archive_root = archive_dir(workspace, archive_id)
    error = _archive_matches_operation(archive_root, operation)
    if error:
        return closed(str(error.get("status") or LIGHT_LIBRARY_CONFLICT), error["message"], paper_id=paper_id, new_paper_id=new_paper_id, archive_id=archive_id)
    new_live = workspace / PAPER_DIRNAME / new_digest
    mismatch = _live_matches_file_inventory(
        new_live,
        new_digest,
        list(operation.get("new_file_inventory") or []),
        list(operation.get("new_directories") or []),
    )
    if mismatch:
        return closed(str(mismatch.get("status") or LIGHT_LIBRARY_CONFLICT), mismatch["message"], paper_id=paper_id, new_paper_id=new_paper_id)
    if not _complete_live(workspace, new_digest):
        return closed(LIGHT_LIBRARY_CONFLICT, "completed replacement live paper is missing or changed", paper_id=paper_id, new_paper_id=new_paper_id)
    return ok_result(
        "reused the exact completed replacement event",
        paper_id=paper_id,
        new_paper_id=new_paper_id,
        archive_id=archive_id,
        operation_id=operation["operation_id"],
        reused=True,
        retained_note_paths=_retained_note_paths(archive_id, {"files": operation.get("file_inventory") or []}, new_paper_id=new_paper_id),
        next_actions=[REINDEX_ACTION],
    )


def _replace_locked(
    workspace: Path,
    paper_id: str,
    pdf_path: Path,
    *,
    title: str | None,
    operation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    digest = paper_digest(paper_id)
    live = workspace / PAPER_DIRNAME / digest
    from video_paper_wiki_research.light_pdf import _read_pdf

    _source, _data, new_digest = _read_pdf(Path(pdf_path))
    new_paper_id = f"sha256:{new_digest}"
    classified = classify_paper_dir(live, digest)
    if new_digest == digest:
        if classified["kind"] != "complete":
            return closed(LIGHT_LIBRARY_INVALID, classified.get("reason") or "selected paper is not a complete live paper", paper_id=paper_id)
        loaded = classified["loaded"]
        if title is not None and _current_title_conflict(loaded, title):
            return closed("LIGHT_PAPER_CONFLICT", "explicit title conflicts with the existing paper title", paper_id=paper_id)
        return ok_result(
            "replacement PDF matches the live paper digest",
            paper_id=paper_id,
            new_paper_id=paper_id,
            archive_id=None,
            operation_id=None,
            reused=True,
            retained_note_paths=[],
            next_actions=[],
        )
    completed = _matching_replace_events(
        workspace,
        paper_id=paper_id,
        new_paper_id=new_paper_id,
        title=title,
        phase="complete",
        outcome=OUTCOME_REPLACED,
    )
    pending = [
        item
        for item in _matching_replace_events(workspace, paper_id=paper_id, new_paper_id=new_paper_id, title=title)
        if item.get("phase") != "complete"
    ]
    if operation is None and len(completed) > 1:
        return closed(LIGHT_LIBRARY_CONFLICT, "multiple matching replacement events exist", paper_id=paper_id, new_paper_id=new_paper_id)
    if operation is None and len(pending) > 1:
        return closed(LIGHT_LIBRARY_CONFLICT, "duplicate pending replacement events exist", paper_id=paper_id, new_paper_id=new_paper_id)
    if operation is None and completed:
        if classified["kind"] == "complete":
            return closed(
                LIGHT_LIBRARY_CONFLICT,
                "the original paper was recreated live after replacement",
                paper_id=paper_id,
                new_paper_id=new_paper_id,
                archive_id=completed[0]["archive_id"],
            )
        if _complete_live(workspace, new_digest) or not os.path.lexists(live):
            return _reuse_completed_replace(workspace, completed[0])
        return closed(LIGHT_LIBRARY_CONFLICT, "completed replacement state is ambiguous", paper_id=paper_id, new_paper_id=new_paper_id)
    if operation is None and pending:
        return _replace_forward(workspace, dict(pending[0]), pdf_path=pdf_path, scanned_old=None)
    if classified["kind"] != "complete" and operation is None:
        return closed(LIGHT_LIBRARY_INVALID, classified.get("reason") or "selected paper is not a complete live paper", paper_id=paper_id)
    scanned_old = _scan_paper_tree(live, original_prefix=f"{PAPER_DIRNAME}/{digest}") if classified.get("kind") == "complete" else None
    if scanned_old is not None and not scanned_old.get("ok"):
        return closed(str(scanned_old.get("status") or LIGHT_LIBRARY_INVALID), str(scanned_old.get("message")), paper_id=paper_id)
    if _complete_live(workspace, new_digest):
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "replacement digest is already an active paper",
            paper_id=paper_id,
            new_paper_id=new_paper_id,
        )
    ensure_library_dirs(workspace)
    if operation is None:
        if scanned_old is None:
            return closed(LIGHT_LIBRARY_INVALID, "selected paper is not a complete live paper", paper_id=paper_id)
        operation_id = new_hex_id()
        archive_id = new_hex_id()
        operation = {
            "schema": OPERATION_SCHEMA,
            "operation_id": operation_id,
            "kind": "replace",
            "paper_id": paper_id,
            "new_paper_id": new_paper_id,
            "archive_id": archive_id,
            "phase": "intent",
            "pdf_sha256": new_digest,
            "title": title,
            "owned_relative_paths": [
                f"{LIBRARY_DIRNAME}/{STAGING_DIRNAME}/{operation_id}/",
                f"{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}/{archive_id}/",
                f"{PAPER_DIRNAME}/{new_digest}/",
            ],
            "source_inventory": source_from_file_inventory(scanned_old["files"]),
            "file_inventory": scanned_old["files"],
            "directories": scanned_old["directories"],
            "stage_file_inventory": [],
            "stage_directories": [],
        }
        intent_files, intent_dirs = _intent_stage_records(operation)
        operation["stage_file_inventory"] = intent_files
        operation["stage_directories"] = intent_dirs
        _write_staging_ownership(workspace, operation)
        _write_operation(workspace, operation)
        run_library_inject("after_intent")
    return _replace_forward(workspace, operation, pdf_path=pdf_path, scanned_old=scanned_old)


def _current_title_conflict(loaded: Mapping[str, Any], title: str) -> bool:
    existing = loaded["metadata"].get("title")
    return type(existing) is str and existing != title


def _ownership_document(operation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": STAGING_OWNER_SCHEMA,
        "version": 1,
        "kind": "replace",
        "operation_id": operation["operation_id"],
        "target_id": operation["paper_id"],
        "intended_relative_target": f"{LIBRARY_DIRNAME}/{STAGING_DIRNAME}/{operation['operation_id']}/workspace",
        "allowed_payload_set": ["workspace/", "ownership.json"],
    }


def _intent_stage_records(operation: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    encoded = persisted_bytes(_ownership_document(operation))
    return (
        [{"path": "ownership.json", "size_bytes": len(encoded), "sha256": sha256_bytes(encoded)}],
        [],
    )


NATIVE_PRODUCER_LOCK_BYTES = b""


def _native_producer_file_paths(new_digest: str, *, prior_notes: bool) -> list[str]:
    files = [
        "ownership.json",
        f"workspace/{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}/{WORKSPACE_LOCK_NAME}",
        f"workspace/{TRANSACTIONS_DIR}/{new_digest}.lock",
        f"workspace/{PAPER_DIRNAME}/{new_digest}/source.json",
        f"workspace/{PAPER_DIRNAME}/{new_digest}/source.md",
    ]
    if prior_notes:
        files.append(f"workspace/{PAPER_DIRNAME}/{new_digest}/{PRIOR_NOTES_NAME}")
    return sorted(files)


def _native_producer_directories(new_digest: str, *, remaining_after_publish: bool = False) -> list[str]:
    directories = [
        "workspace",
        f"workspace/{PAPER_DIRNAME}",
        f"workspace/{TRANSACTIONS_DIR}",
        f"workspace/{WORKFLOW_DIRNAME}",
        f"workspace/{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}",
    ]
    if not remaining_after_publish:
        directories.append(f"workspace/{PAPER_DIRNAME}/{new_digest}")
    return sorted(directories)


def _native_producer_lock_ok(path: Path) -> bool:
    if path.is_symlink() or not is_regular_file(path) or file_is_hardlinked(path):
        return False
    try:
        return path.read_bytes() == NATIVE_PRODUCER_LOCK_BYTES
    except OSError:
        return False


def _producer_paper_identity_ok(paper_dir: Path, new_digest: str, *, prior_notes: bool) -> bool:
    classified = classify_paper_dir(paper_dir, new_digest)
    if classified.get("kind") != "complete":
        return False
    loaded = classified.get("loaded")
    if type(loaded) is not dict or loaded.get("paper_id") != f"sha256:{new_digest}":
        return False
    metadata = loaded.get("metadata")
    if type(metadata) is not dict:
        return False
    source = metadata.get("source")
    document = metadata.get("document")
    if type(source) is not dict or type(document) is not dict:
        return False
    if source.get("sha256") != new_digest:
        return False
    if document.get("path") != f"{PAPER_DIRNAME}/{new_digest}/source.md":
        return False
    markdown = paper_dir / "source.md"
    try:
        markdown_bytes = markdown.read_bytes()
    except OSError:
        return False
    if type(document.get("sha256")) is not str or document.get("sha256") != sha256_bytes(markdown_bytes):
        return False
    extras = classified.get("extras")
    if type(extras) is not list:
        return False
    if prior_notes:
        return extras == [PRIOR_NOTES_NAME]
    return extras == []


def _validate_native_producer_stage(
    staged: Path,
    operation: Mapping[str, Any],
    *,
    new_digest: str,
    prior_notes: bool,
    prior_notes_bytes: bytes | None = None,
) -> dict[str, Any] | None:
    """Refuse unless the stage is the exact native producer layout for this digest.

    A fresh walk/hash observes known files; it never grants ownership of extras.
    """
    paper_id = str(operation["paper_id"])
    operation_id = str(operation["operation_id"])
    if not _owned_marker_intact(staged, operation):
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "replacement staging owner marker is missing or changed; introduced content was preserved",
            paper_id=paper_id,
            operation_id=operation_id,
        )
    scanned = _scan_stage_tree(staged)
    if scanned is None:
        return closed(
            LIGHT_LIBRARY_INVALID,
            "replacement staging is unsafe; introduced content was preserved",
            paper_id=paper_id,
            operation_id=operation_id,
        )
    expected_files = _native_producer_file_paths(new_digest, prior_notes=prior_notes)
    expected_dirs = _native_producer_directories(new_digest)
    actual_files = [item["path"] for item in scanned["files"]]
    if actual_files != expected_files or list(scanned["directories"]) != expected_dirs:
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "replacement staging contains unrecognized producer content; the live paper and extras were preserved",
            paper_id=paper_id,
            operation_id=operation_id,
        )
    workspace_lock = staged / "workspace" / WORKFLOW_DIRNAME / LOCKS_DIRNAME / WORKSPACE_LOCK_NAME
    paper_lock = staged / "workspace" / TRANSACTIONS_DIR / f"{new_digest}.lock"
    if not _native_producer_lock_ok(workspace_lock) or not _native_producer_lock_ok(paper_lock):
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "replacement staging lock is not the native producer lock; the live paper and extras were preserved",
            paper_id=paper_id,
            operation_id=operation_id,
        )
    paper_dir = staged / "workspace" / PAPER_DIRNAME / new_digest
    if not _producer_paper_identity_ok(paper_dir, new_digest, prior_notes=prior_notes):
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "replacement staging paper is not the native producer identity; the live paper and extras were preserved",
            paper_id=paper_id,
            operation_id=operation_id,
        )
    if prior_notes:
        notes = paper_dir / PRIOR_NOTES_NAME
        if notes.is_symlink() or not is_regular_file(notes) or file_is_hardlinked(notes):
            return closed(
                LIGHT_LIBRARY_CONFLICT,
                "prior-paper notes are not a regular owned file; the existing bytes were preserved",
                paper_id=paper_id,
                operation_id=operation_id,
            )
        if prior_notes_bytes is not None:
            try:
                if notes.read_bytes() != prior_notes_bytes:
                    return closed(
                        LIGHT_LIBRARY_CONFLICT,
                        "prior-paper notes are not the attributed owned file; the existing bytes were preserved",
                        paper_id=paper_id,
                        operation_id=operation_id,
                    )
            except OSError:
                return closed(
                    LIGHT_LIBRARY_INVALID,
                    "prior-paper notes could not be read after create-only write",
                    paper_id=paper_id,
                    operation_id=operation_id,
                )
    return None


def _allowlisted_stage_paths(
    operation: Mapping[str, Any],
    *,
    remaining_after_publish: bool,
) -> tuple[list[str], list[str]] | None:
    if operation.get("phase") == "intent":
        return (["ownership.json"], [])
    new_paper_id = operation.get("new_paper_id")
    if not is_paper_id(new_paper_id):
        return None
    digest = paper_digest(str(new_paper_id))
    files = _native_producer_file_paths(digest, prior_notes=True)
    directories = _native_producer_directories(digest, remaining_after_publish=remaining_after_publish)
    if remaining_after_publish:
        prefix = f"workspace/{PAPER_DIRNAME}/{digest}"
        files = [path for path in files if path != prefix and not path.startswith(prefix + "/")]
    return files, directories


def _discard_validated_native_stage(
    workspace: Path,
    operation: Mapping[str, Any],
    new_digest: str,
    *,
    prior_notes: bool,
) -> bool:
    staged = staging_dir(workspace, str(operation["operation_id"]))
    if _validate_native_producer_stage(staged, operation, new_digest=new_digest, prior_notes=prior_notes) is not None:
        return False
    scanned = _scan_stage_tree(staged)
    if scanned is None:
        return False
    for item in scanned["files"]:
        child = staged / str(item["path"])
        if not is_regular_file(child) or file_is_hardlinked(child):
            return False
        try:
            child.unlink()
        except OSError:
            return False
    for rel in sorted(scanned["directories"], key=lambda path: path.count("/"), reverse=True):
        child = staged / rel
        try:
            if list_names(child):
                return False
            child.rmdir()
        except OSError:
            return False
    try:
        if list_names(staged):
            return False
        staged.rmdir()
    except OSError:
        return False
    return not os.path.lexists(staged)


def _write_staging_ownership(workspace: Path, operation: Mapping[str, Any]) -> None:
    staged = staging_dir(workspace, str(operation["operation_id"]))
    staged.mkdir(exist_ok=True)
    write_persisted_atomic(staged / "ownership.json", _ownership_document(operation))


def _replace_forward(
    workspace: Path,
    operation: dict[str, Any],
    *,
    pdf_path: Path | None,
    scanned_old: dict[str, Any] | None,
) -> dict[str, Any]:
    operation_id = str(operation["operation_id"])
    archive_id = str(operation["archive_id"])
    paper_id = str(operation["paper_id"])
    old_digest = paper_digest(paper_id)
    new_paper_id = operation.get("new_paper_id")
    staged_root = staging_dir(workspace, operation_id)
    stage_ws = staged_root / "workspace"
    old_live = workspace / PAPER_DIRNAME / old_digest
    archive_root = archive_dir(workspace, archive_id)
    phase = operation.get("phase")
    if phase == "intent":
        if pdf_path is None:
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "replacement staging is incomplete and the original PDF is no longer available to this recovery",
                paper_id=paper_id,
                operation_id=operation_id,
            )
        if not _stage_is_pre_staging_clean(staged_root, operation):
            return closed(
                LIGHT_LIBRARY_CONFLICT,
                "replacement staging is not the exact intent shape; the live paper and extras were preserved",
                paper_id=paper_id,
                operation_id=operation_id,
            )
        expected_new_id = operation.get("new_paper_id")
        if not is_paper_id(expected_new_id):
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "replacement intent is missing the expected new paper identity",
                paper_id=paper_id,
                operation_id=operation_id,
            )
        expected_digest = paper_digest(str(expected_new_id))
        stage_ws.mkdir(exist_ok=True)
        extracted = extract_pdf(pdf_path, stage_ws, title=operation.get("title"))
        if extracted.get("ok") is not True:
            if _stage_is_pre_staging_clean(staged_root, operation):
                _discard_owned_stage(workspace, operation)
            status = str(extracted.get("status") or LIGHT_LIBRARY_INVALID)
            return closed(status, str(extracted.get("message") or "replacement extraction failed"), paper_id=paper_id, operation_id=operation_id)
        new_paper_id = str(extracted["paper_id"])
        new_digest = paper_digest(new_paper_id)
        if new_paper_id != expected_new_id or new_digest != expected_digest:
            return closed(
                LIGHT_LIBRARY_CONFLICT,
                "extracted replacement digest does not match the intended PDF identity; extras were preserved",
                paper_id=paper_id,
                operation_id=operation_id,
            )
        producer_error = _validate_native_producer_stage(
            staged_root,
            operation,
            new_digest=new_digest,
            prior_notes=False,
        )
        if producer_error is not None:
            return producer_error
        if _complete_live(workspace, new_digest):
            _discard_validated_native_stage(workspace, operation, new_digest, prior_notes=False)
            return closed(LIGHT_LIBRARY_CONFLICT, "replacement digest is already an active paper", paper_id=paper_id, new_paper_id=new_paper_id)
        staged_paper = stage_ws / PAPER_DIRNAME / new_digest
        if scanned_old is None:
            scanned_old = _scan_paper_tree(old_live, original_prefix=f"{PAPER_DIRNAME}/{old_digest}")
            if not scanned_old.get("ok"):
                return closed(str(scanned_old.get("status") or LIGHT_LIBRARY_INVALID), str(scanned_old.get("message")), paper_id=paper_id)
        notes = _prior_notes_markdown(old_paper_id=paper_id, archive_id=archive_id, scanned=scanned_old)
        notes_bytes = notes.encode("utf-8")
        notes_path = staged_paper / PRIOR_NOTES_NAME
        try:
            write_bytes_create_only(notes_path, notes_bytes)
        except FileExistsError:
            return closed(
                LIGHT_LIBRARY_CONFLICT,
                "prior-paper notes already exist in replacement staging; the existing file was preserved",
                paper_id=paper_id,
                new_paper_id=new_paper_id,
                operation_id=operation_id,
            )
        producer_error = _validate_native_producer_stage(
            staged_root,
            operation,
            new_digest=new_digest,
            prior_notes=True,
            prior_notes_bytes=notes_bytes,
        )
        if producer_error is not None:
            return producer_error
        scanned_new = _scan_paper_tree(staged_paper, original_prefix=f"{PAPER_DIRNAME}/{new_digest}")
        if not scanned_new.get("ok"):
            return closed(str(scanned_new.get("status") or LIGHT_LIBRARY_INVALID), str(scanned_new.get("message")), paper_id=paper_id)
        recorded = _scan_stage_tree(staged_root)
        if recorded is None:
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "owned replacement staging could not be inventoried", paper_id=paper_id, operation_id=operation_id)
        expected_files = _native_producer_file_paths(new_digest, prior_notes=True)
        expected_dirs = _native_producer_directories(new_digest)
        if [item["path"] for item in recorded["files"]] != expected_files or list(recorded["directories"]) != expected_dirs:
            return closed(
                LIGHT_LIBRARY_CONFLICT,
                "replacement staging is not the complete owned producer set; the live paper and extras were preserved",
                paper_id=paper_id,
                operation_id=operation_id,
            )
        operation = dict(operation)
        operation["new_paper_id"] = new_paper_id
        operation["new_file_inventory"] = scanned_new["files"]
        operation["new_directories"] = scanned_new["directories"]
        operation["stage_file_inventory"] = recorded["files"]
        operation["stage_directories"] = recorded["directories"]
        operation["phase"] = "staged"
        _write_operation(workspace, operation)
        run_library_inject("after_replace_staged")
        phase = "staged"
    if phase == "staged":
        if new_paper_id is None or not is_paper_id(new_paper_id):
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "staged replacement is missing new paper identity", paper_id=paper_id, operation_id=operation_id)
        new_digest = paper_digest(str(new_paper_id))
        staged_paper = stage_ws / PAPER_DIRNAME / new_digest
        if not is_regular_dir(staged_paper):
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "owned replacement staging is missing after intent", paper_id=paper_id, operation_id=operation_id)
        staged_mismatch = _live_matches_file_inventory(
            staged_paper,
            new_digest,
            list(operation.get("new_file_inventory") or []),
            list(operation.get("new_directories") or []),
        )
        if staged_mismatch:
            return closed(str(staged_mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), staged_mismatch["message"], paper_id=paper_id, operation_id=operation_id)
        if not os.path.lexists(old_live) and is_regular_dir(archive_root / "paper"):
            error = _archive_matches_operation(archive_root, operation)
            if error:
                return closed(str(error.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), error["message"], paper_id=paper_id, archive_id=archive_id, operation_id=operation_id)
            operation = dict(operation)
            operation["phase"] = "old_archived"
            _write_operation(workspace, operation)
            phase = "old_archived"
        elif not os.path.lexists(old_live):
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "old live paper disappeared before it was archived", paper_id=paper_id, operation_id=operation_id)
        elif phase == "staged":
            if not _stage_is_fully_owned(workspace, staged_root, operation):
                return closed(
                    LIGHT_LIBRARY_CONFLICT,
                    "replacement staging is not a complete owned producer set; the live paper was preserved",
                    paper_id=paper_id,
                    operation_id=operation_id,
                )
            producer_error = _validate_native_producer_stage(
                staged_root,
                operation,
                new_digest=new_digest,
                prior_notes=True,
            )
            if producer_error is not None:
                return producer_error
            old_mismatch = _live_matches_file_inventory(old_live, old_digest, list(operation["file_inventory"]), list(operation["directories"]))
            if old_mismatch:
                return closed(str(old_mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), old_mismatch["message"], paper_id=paper_id, operation_id=operation_id)
            frozen_old = {"files": operation["file_inventory"], "directories": operation["directories"]}
            archive_root.mkdir(exist_ok=True)
            manifest = _archive_manifest(archive_id=archive_id, paper_id=paper_id, digest=old_digest, scanned=frozen_old)
            write_persisted_atomic(archive_root / "manifest.json", manifest)
            _write_archive_event(
                archive_root,
                {"schema": ARCHIVE_EVENT_SCHEMA, "archive_id": archive_id, "paper_id": paper_id, "operation_id": operation_id, "state": "archived"},
            )
            run_library_inject("before_old_archive")
            if not _stage_is_fully_owned(workspace, staged_root, operation):
                return closed(
                    LIGHT_LIBRARY_CONFLICT,
                    "replacement staging is not a complete owned producer set; the live paper was preserved",
                    paper_id=paper_id,
                    operation_id=operation_id,
                )
            producer_error = _validate_native_producer_stage(
                staged_root,
                operation,
                new_digest=new_digest,
                prior_notes=True,
            )
            if producer_error is not None:
                return producer_error
            old_mismatch = _live_matches_file_inventory(old_live, old_digest, list(operation["file_inventory"]), list(operation["directories"]))
            if old_mismatch:
                return closed(str(old_mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), old_mismatch["message"], paper_id=paper_id, operation_id=operation_id)
            os.rename(old_live, archive_root / "paper")
            run_library_inject("after_old_archive")
            error = _archive_matches_operation(archive_root, operation)
            if error:
                return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, error["message"], paper_id=paper_id, archive_id=archive_id, operation_id=operation_id)
            operation = dict(operation)
            operation["phase"] = "old_archived"
            _write_operation(workspace, operation)
            phase = "old_archived"
    if phase == "old_archived":
        if new_paper_id is None or not is_paper_id(new_paper_id):
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "new paper identity is missing after the old paper was archived", paper_id=paper_id, archive_id=archive_id)
        new_digest = paper_digest(str(new_paper_id))
        staged_paper = stage_ws / PAPER_DIRNAME / new_digest
        dest = workspace / PAPER_DIRNAME / new_digest
        if os.path.lexists(dest) and is_regular_dir(staged_paper):
            return closed(LIGHT_LIBRARY_CONFLICT, "new live slot and staged replacement both exist", paper_id=paper_id, new_paper_id=new_paper_id)
        if not is_regular_dir(staged_paper) and not os.path.lexists(dest):
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "replacement staging is missing after the old paper was archived; the archive is retained",
                paper_id=paper_id,
                archive_id=archive_id,
                operation_id=operation_id,
            )
        if is_regular_dir(staged_paper):
            staged_mismatch = _live_matches_file_inventory(
                staged_paper,
                new_digest,
                list(operation.get("new_file_inventory") or []),
                list(operation.get("new_directories") or []),
            )
            if staged_mismatch:
                return closed(str(staged_mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), staged_mismatch["message"], paper_id=paper_id, operation_id=operation_id)
            new_lock = _paper_lock(workspace, new_digest)
            if new_lock is None:
                return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation owns the replacement digest", new_paper_id=new_paper_id)
            try:
                run_library_inject("before_new_publish")
                os.rename(staged_paper, dest)
                run_library_inject("after_new_publish")
            finally:
                new_lock.release()
        live_mismatch = _live_matches_file_inventory(
            dest,
            new_digest,
            list(operation.get("new_file_inventory") or []),
            list(operation.get("new_directories") or []),
        )
        if live_mismatch:
            return closed(str(live_mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), live_mismatch["message"], paper_id=paper_id, new_paper_id=new_paper_id)
        classified_new = classify_paper_dir(dest, new_digest)
        if classified_new["kind"] != "complete":
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "published replacement is not a valid live paper", paper_id=paper_id, new_paper_id=new_paper_id)
        error = _archive_matches_operation(archive_root, operation)
        if error:
            return closed(str(error.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), error["message"], paper_id=paper_id, archive_id=archive_id, operation_id=operation_id)
        operation = dict(operation)
        operation["phase"] = "new_published"
        _write_operation(workspace, operation)
        phase = "new_published"
    if phase == "new_published":
        discarded = _discard_owned_stage(workspace, operation)
        if not discarded:
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "replacement published but owned staging still contains unrecognized content",
                paper_id=paper_id,
                new_paper_id=operation.get("new_paper_id"),
                archive_id=archive_id,
                operation_id=operation_id,
            )
        operation = dict(operation)
        operation["phase"] = "complete"
        operation["outcome"] = OUTCOME_REPLACED
        _write_operation(workspace, operation)
        scanned_old = scanned_old or {"files": operation.get("file_inventory") or []}
        return ok_result(
            "replaced paper; old notes remain in the archive and are attributed as prior-paper notes",
            paper_id=paper_id,
            new_paper_id=operation.get("new_paper_id"),
            archive_id=archive_id,
            operation_id=operation_id,
            reused=False,
            retained_note_paths=_retained_note_paths(archive_id, scanned_old, new_paper_id=operation.get("new_paper_id")),
            next_actions=[REINDEX_ACTION],
        )
    return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, f"unrecognized replace phase {phase}", paper_id=paper_id, operation_id=operation_id)


def _recognized_staging_owner(owner: Mapping[str, Any] | None, operation: Mapping[str, Any]) -> bool:
    if owner is None or type(owner) is not dict or set(owner) != STAGING_OWNER_FIELDS:
        return False
    if owner.get("schema") != STAGING_OWNER_SCHEMA:
        return False
    version = owner.get("version")
    if type(version) is not int or version != 1:
        return False
    if type(owner.get("kind")) is not str or owner.get("kind") != "replace":
        return False
    if owner.get("operation_id") != operation["operation_id"]:
        return False
    if owner.get("target_id") != operation.get("paper_id"):
        return False
    intended = f"{LIBRARY_DIRNAME}/{STAGING_DIRNAME}/{operation['operation_id']}/workspace"
    if owner.get("intended_relative_target") != intended:
        return False
    return owner.get("allowed_payload_set") == ["workspace/", "ownership.json"]


def _owned_marker_intact(staged: Path, operation: Mapping[str, Any]) -> bool:
    path = staged / "ownership.json"
    if path.is_symlink() or not is_regular_file(path) or file_is_hardlinked(path):
        return False
    if chain_has_symlink(path, stop_at=staged):
        return False
    owner = load_persisted_object(path)
    if not _recognized_staging_owner(owner, operation):
        return False
    try:
        return path.read_bytes() == persisted_bytes(_ownership_document(operation))
    except OSError:
        return False


def _scan_stage_tree(staged: Path) -> dict[str, Any] | None:
    if staged.is_symlink() or not staged.is_dir() or chain_has_symlink(staged):
        return None
    directories, files, problems = walk_regular_tree(staged)
    if problems:
        return None
    rows: list[dict[str, Any]] = []
    for rel in files:
        child = staged / rel
        if child.is_symlink() or not child.is_file() or file_is_hardlinked(child):
            return None
        if chain_has_symlink(child, stop_at=staged):
            return None
        rows.append(inventory_row(rel, child))
    rel_dirs: list[str] = []
    for directory in directories:
        if directory == staged:
            continue
        if directory.is_symlink() or not directory.is_dir():
            return None
        rel_dirs.append(posix_rel(str(directory.relative_to(staged))))
    rows.sort(key=lambda item: str(item["path"]))
    return {"files": rows, "directories": sorted(rel_dirs)}


def _same_stage_inventory(
    left_files: list[Mapping[str, Any]],
    left_dirs: list[str],
    right_files: list[Mapping[str, Any]],
    right_dirs: list[str],
) -> bool:
    if list(left_dirs) != list(right_dirs):
        return False

    def _rows(items: list[Mapping[str, Any]]) -> list[tuple[str, int, str]] | None:
        rows: list[tuple[str, int, str]] = []
        seen: set[str] = set()
        for item in items:
            if type(item) is not dict or set(item) != {"path", "size_bytes", "sha256"}:
                return None
            path = item.get("path")
            size = item.get("size_bytes")
            digest = item.get("sha256")
            if type(path) is not str or type(size) is not int or type(size) is bool or type(digest) is not str:
                return None
            if path in seen:
                return None
            seen.add(path)
            rows.append((path, size, digest))
        rows.sort()
        return rows

    return _rows(list(left_files)) == _rows(list(right_files))


def _stage_matches_inventory(staged: Path, files: list[Mapping[str, Any]], directories: list[str]) -> bool:
    scanned = _scan_stage_tree(staged)
    if scanned is None:
        return False
    return _same_stage_inventory(list(scanned["files"]), list(scanned["directories"]), list(files), list(directories))


def _expected_stage_inventory(workspace: Path, operation: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]] | None:
    if operation.get("phase") == "intent":
        return _intent_stage_records(operation)
    files = list(operation.get("stage_file_inventory") or [])
    dirs = list(operation.get("stage_directories") or [])
    if not validate_stage_file_inventory(files) or not validate_directory_inventory(dirs):
        return None
    new_paper_id = operation.get("new_paper_id")
    if not is_paper_id(new_paper_id):
        return None
    new_digest = paper_digest(str(new_paper_id))
    dest = workspace / PAPER_DIRNAME / new_digest
    staged_paper = staging_dir(workspace, str(operation["operation_id"])) / "workspace" / PAPER_DIRNAME / new_digest
    remaining = os.path.lexists(dest) and not os.path.lexists(staged_paper)
    if remaining:
        prefix = f"workspace/{PAPER_DIRNAME}/{new_digest}"
        files = [item for item in files if item["path"] != prefix and not str(item["path"]).startswith(prefix + "/")]
        dirs = [item for item in dirs if item != prefix and not item.startswith(prefix + "/")]
    allowlisted = _allowlisted_stage_paths(operation, remaining_after_publish=remaining)
    if allowlisted is None:
        return None
    allowed_files, allowed_dirs = allowlisted
    actual_paths = sorted(str(item["path"]) for item in files)
    if actual_paths != allowed_files or sorted(dirs) != allowed_dirs:
        return None
    return files, dirs


def _stage_is_fully_owned(workspace: Path, staged: Path, operation: Mapping[str, Any]) -> bool:
    if staged.is_symlink() or not staged.is_dir():
        return False
    if not _owned_marker_intact(staged, operation):
        return False
    expected = _expected_stage_inventory(workspace, operation)
    if expected is None:
        return False
    files, directories = expected
    return _stage_matches_inventory(staged, files, directories)


def _stage_is_pre_staging_clean(staged: Path, operation: Mapping[str, Any]) -> bool:
    if not os.path.lexists(staged):
        return True
    if not _owned_marker_intact(staged, operation):
        return False
    files, directories = _intent_stage_records(operation)
    return _stage_matches_inventory(staged, files, directories)


def _discard_owned_stage(workspace: Path, operation: Mapping[str, Any]) -> bool:
    staged = staging_dir(workspace, str(operation["operation_id"]))
    if not os.path.lexists(staged):
        return True
    if not _stage_is_fully_owned(workspace, staged, operation):
        return False
    expected = _expected_stage_inventory(workspace, operation)
    if expected is None:
        return False
    files, directories = expected
    if not _stage_matches_inventory(staged, files, directories):
        return False
    for item in files:
        child = staged / str(item["path"])
        if not is_regular_file(child) or file_is_hardlinked(child):
            return False
        try:
            child.unlink()
        except OSError:
            return False
    for rel in sorted(directories, key=lambda path: path.count("/"), reverse=True):
        child = staged / rel
        try:
            if list_names(child):
                return False
            child.rmdir()
        except OSError:
            return False
    try:
        if list_names(staged):
            return False
        staged.rmdir()
    except OSError:
        return False
    return not os.path.lexists(staged)


def _settle_aborted_before_staging(workspace: Path, operation: Mapping[str, Any]) -> dict[str, Any]:
    paper_id = str(operation["paper_id"])
    digest = paper_digest(paper_id)
    live = workspace / PAPER_DIRNAME / digest
    mismatch = _live_matches_file_inventory(live, digest, list(operation["file_inventory"]), list(operation["directories"]))
    if mismatch:
        return closed(str(mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), mismatch["message"], paper_id=paper_id, operation_id=operation["operation_id"])
    if not _complete_live(workspace, digest):
        return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "old live paper is not a complete unchanged pair", paper_id=paper_id, operation_id=operation["operation_id"])
    staged = staging_dir(workspace, str(operation["operation_id"]))
    if not _stage_is_pre_staging_clean(staged, operation):
        return closed(
            LIGHT_LIBRARY_NEEDS_RECOVERY,
            "pre-staging replacement left unrecognized stage content; the live paper and extras were preserved",
            paper_id=paper_id,
            operation_id=operation["operation_id"],
        )
    if not _discard_owned_stage(workspace, operation):
        return closed(
            LIGHT_LIBRARY_NEEDS_RECOVERY,
            "owned pre-staging state could not be safely discarded",
            paper_id=paper_id,
            operation_id=operation["operation_id"],
        )
    if os.path.lexists(archive_dir(workspace, str(operation["archive_id"])) / "paper"):
        return closed(LIGHT_LIBRARY_CONFLICT, "unexpected archive payload exists for an aborted replacement", paper_id=paper_id, operation_id=operation["operation_id"])
    operation = dict(operation)
    operation["phase"] = "complete"
    operation["outcome"] = OUTCOME_ABORTED_BEFORE_STAGING
    _write_operation(workspace, operation)
    return ok_result(
        "replacement was aborted before staging; the live paper is unchanged and no replacement occurred",
        paper_id=paper_id,
        new_paper_id=None,
        archive_id=operation["archive_id"],
        operation_id=operation["operation_id"],
        reused=False,
        replaced=False,
        outcome=OUTCOME_ABORTED_BEFORE_STAGING,
        retained_note_paths=[],
        next_actions=[],
    )


def recover_library(workspace_root: Path, *, operation_id: str | None = None) -> dict[str, Any]:
    if operation_id is not None:
        operation_id = require_hex_id(operation_id, name="operation_id")
    workspace = require_workspace(workspace_root)
    try:
        with exclusive_workspace_lock(workspace):
            return _recover_locked(workspace, operation_id=operation_id)
    except _Busy:
        return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation currently owns this workspace")


def _recover_locked(workspace: Path, *, operation_id: str | None) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    paths = iter_operation_files(workspace)
    selected: list[Path] = []
    for path in paths:
        loaded = load_persisted_object(path)
        recognized = recognized_operation(loaded, filename=path.name)
        if recognized is None:
            results.append(
                closed(
                    LIGHT_LIBRARY_INVALID,
                    "malformed or foreign operation journal was preserved",
                    path=str(path.relative_to(workspace)),
                )
            )
            continue
        if operation_id is not None and recognized["operation_id"] != operation_id:
            continue
        selected.append(path)
        results.append(_recover_one(workspace, recognized))
    if operation_id is not None and not selected:
        return closed(LIGHT_LIBRARY_INVALID, "operation_id is not a recognized journal", operation_id=operation_id, operations=results)
    failed = [item for item in results if item.get("ok") is not True]
    if failed:
        return closed(
            str(failed[0].get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY),
            "one or more library operations still need attention",
            operations=results,
            next_actions=[RECOVER_ACTION],
        )
    return ok_result("inspected recognized library operations", operations=results)


def _recognized_archive_event(event: Mapping[str, Any] | None, *, archive_id: str, paper_id: str) -> dict[str, Any] | None:
    if event is None or type(event) is not dict or set(event) != ARCHIVE_EVENT_FIELDS:
        return None
    if event.get("schema") != ARCHIVE_EVENT_SCHEMA:
        return None
    if type(event.get("archive_id")) is not str or event.get("archive_id") != archive_id:
        return None
    if type(event.get("paper_id")) is not str or event.get("paper_id") != paper_id:
        return None
    if type(event.get("operation_id")) is not str or not is_hex_id(event.get("operation_id")):
        return None
    if type(event.get("state")) is not str or event.get("state") not in {"archived", "restored"}:
        return None
    return dict(event)


def _completed_operations(workspace: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for _path, operation in _iter_recognized_operations(workspace):
        if operation.get("phase") == "complete":
            found.append(operation)
    return found


def _unique_restore_successor(workspace: Path, archive_op: Mapping[str, Any], *, completed: bool = True) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    source = _completed_operations(workspace) if completed else [item for _path, item in _iter_recognized_operations(workspace)]
    for operation in source:
        if operation.get("kind") != "restore":
            continue
        if completed and operation.get("outcome") != OUTCOME_RESTORED:
            continue
        if operation.get("archive_id") != archive_op["archive_id"] or operation.get("paper_id") != archive_op["paper_id"]:
            continue
        if not _same_file_inventory(list(operation["file_inventory"]), list(archive_op["file_inventory"])):
            continue
        if list(operation["directories"]) != list(archive_op["directories"]):
            continue
        matches.append(operation)
    if len(matches) != 1:
        return None
    return matches[0]


def _unique_archive_successor(
    workspace: Path,
    *,
    paper_id: str,
    files: list[Mapping[str, Any]],
    directories: list[str],
    exclude_archive_id: str,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for operation in _completed_operations(workspace):
        kind = operation.get("kind")
        outcome = operation.get("outcome")
        if kind == "archive" and outcome == OUTCOME_ARCHIVED:
            pass
        elif kind == "replace" and outcome == OUTCOME_REPLACED:
            pass
        else:
            continue
        if operation.get("paper_id") != paper_id or operation.get("archive_id") == exclude_archive_id:
            continue
        if not _same_file_inventory(list(operation["file_inventory"]), list(files)):
            continue
        if list(operation["directories"]) != list(directories):
            continue
        matches.append(operation)
    if len(matches) != 1:
        return None
    return matches[0]


def _exact_complete_ok(operation: Mapping[str, Any], message: str) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if operation.get("outcome") == OUTCOME_ABORTED_BEFORE_STAGING:
        extra["replaced"] = False
    return ok_result(
        message,
        operation_id=operation["operation_id"],
        kind=operation["kind"],
        phase="complete",
        outcome=operation.get("outcome"),
        reused=True,
        **extra,
    )


def _historical_complete_ok(operation: Mapping[str, Any], successor: Mapping[str, Any], message: str) -> dict[str, Any]:
    return ok_result(
        message,
        operation_id=operation["operation_id"],
        kind=operation["kind"],
        phase="complete",
        outcome=operation.get("outcome"),
        reused=False,
        historical=True,
        superseded=True,
        successor_operation_id=successor["operation_id"],
    )


def _explain_completed_replace(workspace: Path, operation: Mapping[str, Any], *, visited: frozenset[str]) -> dict[str, Any]:
    paper_id = str(operation["paper_id"])
    new_paper_id = str(operation["new_paper_id"])
    old_digest = paper_digest(paper_id)
    new_digest = paper_digest(new_paper_id)
    archive_root = archive_dir(workspace, str(operation["archive_id"]))
    old_live = workspace / PAPER_DIRNAME / old_digest
    new_live = workspace / PAPER_DIRNAME / new_digest
    staged = staging_dir(workspace, str(operation["operation_id"]))
    payload = is_regular_dir(archive_root / "paper")
    if os.path.lexists(old_live) and payload:
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "completed replacement has both the old live paper and its archive payload",
            paper_id=paper_id,
            archive_id=operation["archive_id"],
            operation_id=operation["operation_id"],
        )
    successor: dict[str, Any] | None = None
    if payload:
        error = _archive_matches_operation(archive_root, operation)
        if error:
            return closed(str(error.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), error["message"], paper_id=paper_id, operation_id=operation["operation_id"])
        event = _recognized_archive_event(
            load_persisted_object(archive_root / "event.json"),
            archive_id=str(operation["archive_id"]),
            paper_id=paper_id,
        )
        if event is None or event["operation_id"] != operation["operation_id"] or event["state"] != "archived":
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "replacement archive event is missing or does not match the completed replacement",
                paper_id=paper_id,
                operation_id=operation["operation_id"],
            )
        old_exact = True
    else:
        successor = _unique_restore_successor(workspace, operation)
        if successor is None:
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "completed replacement is missing its old archive and has no unique restore successor",
                paper_id=paper_id,
                operation_id=operation["operation_id"],
            )
        event = _recognized_archive_event(
            load_persisted_object(archive_root / "event.json"),
            archive_id=str(operation["archive_id"]),
            paper_id=paper_id,
        )
        if event is None or event["operation_id"] != successor["operation_id"] or event["state"] != "restored":
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "replacement archive event does not prove the restore successor",
                paper_id=paper_id,
                operation_id=operation["operation_id"],
            )
        explained = _explain_completed(workspace, successor, visited=visited)
        if explained.get("ok") is not True:
            return explained
        old_exact = False
    if os.path.lexists(new_live):
        mismatch = _live_matches_file_inventory(
            new_live,
            new_digest,
            list(operation.get("new_file_inventory") or []),
            list(operation.get("new_directories") or []),
        )
        if mismatch:
            return closed(str(mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), mismatch["message"], paper_id=paper_id, new_paper_id=new_paper_id, operation_id=operation["operation_id"])
        if not _complete_live(workspace, new_digest):
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "completed replacement live paper is missing or changed", paper_id=paper_id, new_paper_id=new_paper_id, operation_id=operation["operation_id"])
        new_exact = True
    else:
        new_successor = _unique_archive_successor(
            workspace,
            paper_id=new_paper_id,
            files=list(operation.get("new_file_inventory") or []),
            directories=list(operation.get("new_directories") or []),
            exclude_archive_id=str(operation["archive_id"]),
        )
        if new_successor is None:
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "completed replacement is missing its new live paper and has no unique archive successor",
                paper_id=paper_id,
                new_paper_id=new_paper_id,
                operation_id=operation["operation_id"],
            )
        explained = _explain_completed(workspace, new_successor, visited=visited)
        if explained.get("ok") is not True:
            return explained
        successor = new_successor
        new_exact = False
    if os.path.lexists(staged):
        if not _stage_is_fully_owned(workspace, staged, operation):
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "completed replacement left unrecognized stage content; bytes were preserved",
                paper_id=paper_id,
                operation_id=operation["operation_id"],
            )
        if not _discard_owned_stage(workspace, operation):
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "owned leftover replacement stage could not be safely discarded",
                paper_id=paper_id,
                operation_id=operation["operation_id"],
            )
    if old_exact and new_exact:
        return _exact_complete_ok(operation, "operation is already complete")
    if successor is None:
        return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "completed replacement history is incomplete", paper_id=paper_id, operation_id=operation["operation_id"])
    return _historical_complete_ok(operation, successor, "completed replacement is a superseded historical event")


def _explain_completed(workspace: Path, operation: Mapping[str, Any], *, visited: frozenset[str]) -> dict[str, Any]:
    operation_id = str(operation["operation_id"])
    if operation_id in visited:
        return closed(LIGHT_LIBRARY_CONFLICT, "successor history is cyclic or ambiguous", operation_id=operation_id)
    next_visited = visited | {operation_id}
    kind = operation["kind"]
    paper_id = str(operation["paper_id"])
    digest = paper_digest(paper_id)
    live = workspace / PAPER_DIRNAME / digest
    archive_root = archive_dir(workspace, str(operation["archive_id"]))
    payload = is_regular_dir(archive_root / "paper")
    live_exists = os.path.lexists(live)
    outcome = operation.get("outcome")
    if kind == "archive" and outcome != OUTCOME_ARCHIVED:
        return closed(LIGHT_LIBRARY_INVALID, "completed archive journal has an invalid outcome", operation_id=operation_id)
    if kind == "restore" and outcome != OUTCOME_RESTORED:
        return closed(LIGHT_LIBRARY_INVALID, "completed restore journal has an invalid outcome", operation_id=operation_id)
    if outcome == OUTCOME_ABORTED_BEFORE_STAGING:
        mismatch = _live_matches_file_inventory(live, digest, list(operation["file_inventory"]), list(operation["directories"]))
        if mismatch:
            return closed(str(mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), mismatch["message"], paper_id=paper_id, operation_id=operation_id)
        if payload or os.path.lexists(staging_dir(workspace, operation_id)):
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "aborted-before-staging journal still has leftover replacement state", paper_id=paper_id, operation_id=operation_id)
        return _exact_complete_ok(operation, "replacement was aborted before staging; the live paper is unchanged and no replacement occurred")
    if kind == "replace" and outcome != OUTCOME_REPLACED:
        return closed(LIGHT_LIBRARY_INVALID, "completed replace journal has an invalid outcome", operation_id=operation_id)
    if kind == "replace":
        return _explain_completed_replace(workspace, operation, visited=next_visited)
    if live_exists and payload:
        return closed(
            LIGHT_LIBRARY_CONFLICT,
            "completed journal has both the live paper and its archive payload",
            paper_id=paper_id,
            archive_id=operation["archive_id"],
            operation_id=operation_id,
        )
    event = _recognized_archive_event(
        load_persisted_object(archive_root / "event.json"),
        archive_id=str(operation["archive_id"]),
        paper_id=paper_id,
    )
    if kind == "archive":
        if payload and not live_exists:
            error = _archive_matches_operation(archive_root, operation)
            if error:
                return closed(str(error.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), error["message"], paper_id=paper_id, operation_id=operation_id)
            if event is None or event["operation_id"] != operation_id or event["state"] != "archived":
                return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "archive event is missing or does not match the completed archive", paper_id=paper_id, operation_id=operation_id)
            return _exact_complete_ok(operation, "operation is already complete")
        if live_exists and not payload:
            mismatch = _live_matches_file_inventory(live, digest, list(operation["file_inventory"]), list(operation["directories"]))
            if mismatch:
                return closed(str(mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), mismatch["message"], paper_id=paper_id, operation_id=operation_id)
            successor = _unique_restore_successor(workspace, operation, completed=False)
            if successor is None:
                return closed(
                    LIGHT_LIBRARY_NEEDS_RECOVERY,
                    "completed archive is missing its payload and has no unique restore successor",
                    paper_id=paper_id,
                    operation_id=operation_id,
                )
            if successor.get("phase") == "complete":
                if event is None or event["operation_id"] != successor["operation_id"] or event["state"] != "restored":
                    return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "archive event does not prove the restore successor", paper_id=paper_id, operation_id=operation_id)
                explained = _explain_completed(workspace, successor, visited=next_visited)
                if explained.get("ok") is not True:
                    return explained
            elif event is not None:
                if event["archive_id"] != operation["archive_id"] or event["paper_id"] != paper_id:
                    return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "archive event does not prove the restore successor", paper_id=paper_id, operation_id=operation_id)
                if event["state"] == "archived" and event["operation_id"] != operation_id:
                    return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "archive event does not prove the restore successor", paper_id=paper_id, operation_id=operation_id)
                if event["state"] == "restored" and event["operation_id"] != successor["operation_id"]:
                    return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "archive event does not prove the restore successor", paper_id=paper_id, operation_id=operation_id)
            return _historical_complete_ok(operation, successor, "completed archive is a superseded historical event")
        successor = _unique_restore_successor(workspace, operation)
        if successor is None:
            return closed(
                LIGHT_LIBRARY_NEEDS_RECOVERY,
                "completed archive is missing its payload and has no unique restore successor",
                paper_id=paper_id,
                operation_id=operation_id,
            )
        if event is None or event["operation_id"] != successor["operation_id"] or event["state"] != "restored":
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "archive event does not prove the restore successor", paper_id=paper_id, operation_id=operation_id)
        explained = _explain_completed(workspace, successor, visited=next_visited)
        if explained.get("ok") is not True:
            return explained
        return _historical_complete_ok(operation, successor, "completed archive is a superseded historical event")
    if live_exists and not payload:
        mismatch = _live_matches_file_inventory(live, digest, list(operation["file_inventory"]), list(operation["directories"]))
        if mismatch:
            return closed(str(mismatch.get("status") or LIGHT_LIBRARY_NEEDS_RECOVERY), mismatch["message"], paper_id=paper_id, operation_id=operation_id)
        if not _complete_live(workspace, digest):
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "completed restore live paper is missing or changed", paper_id=paper_id, operation_id=operation_id)
        if event is None or event["operation_id"] != operation_id or event["state"] != "restored":
            return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "restore event is missing or does not match the completed restore", paper_id=paper_id, operation_id=operation_id)
        return _exact_complete_ok(operation, "operation is already complete")
    successor = _unique_archive_successor(
        workspace,
        paper_id=paper_id,
        files=list(operation["file_inventory"]),
        directories=list(operation["directories"]),
        exclude_archive_id=str(operation["archive_id"]),
    )
    if successor is None:
        return closed(
            LIGHT_LIBRARY_NEEDS_RECOVERY,
            "completed restore is missing its live paper and has no unique archive successor",
            paper_id=paper_id,
            operation_id=operation_id,
        )
    if event is None or event["operation_id"] != operation_id or event["state"] != "restored":
        return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "restore event is missing or was rewritten", paper_id=paper_id, operation_id=operation_id)
    explained = _explain_completed(workspace, successor, visited=next_visited)
    if explained.get("ok") is not True:
        return explained
    return _historical_complete_ok(operation, successor, "completed restore is a superseded historical event")


def _completed_operation_state(workspace: Path, operation: Mapping[str, Any]) -> dict[str, Any]:
    return _explain_completed(workspace, operation, visited=frozenset())


def _recover_one(workspace: Path, operation: dict[str, Any]) -> dict[str, Any]:
    if operation.get("phase") == "complete":
        return _completed_operation_state(workspace, operation)
    kind = operation.get("kind")
    paper_id = operation.get("paper_id")
    digest = paper_digest(str(paper_id)) if is_paper_id(paper_id) else None
    lock = _paper_lock(workspace, digest) if digest else None
    if digest and lock is None:
        return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation owns this paper digest", operation_id=operation["operation_id"], paper_id=paper_id)
    try:
        if kind == "archive":
            if not is_paper_id(paper_id):
                return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "archive journal is missing paper_id", operation_id=operation["operation_id"])
            return _archive_locked(workspace, str(paper_id), operation=operation)
        if kind == "restore":
            archive_id = operation.get("archive_id")
            if not is_hex_id(archive_id):
                return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "restore journal is missing archive_id", operation_id=operation["operation_id"])
            return _restore_locked(workspace, str(archive_id), operation=operation, acquire_paper_lock=False)
        if kind == "replace":
            if not is_paper_id(paper_id):
                return closed(LIGHT_LIBRARY_NEEDS_RECOVERY, "replace journal is missing paper_id", operation_id=operation["operation_id"])
            phase = operation.get("phase")
            if phase == "intent":
                return _settle_aborted_before_staging(workspace, operation)
            return _replace_forward(workspace, operation, pdf_path=None, scanned_old=None)
        return closed(LIGHT_LIBRARY_INVALID, "unrecognized operation kind was preserved", operation_id=operation.get("operation_id"))
    finally:
        if lock is not None:
            lock.release()


def library_backup_blockers(workspace: Path) -> dict[str, Any] | None:
    """Return a closed refusal if library/knowledge/PDF publication state is unsafe to back up."""
    pending = pending_operation_ids(workspace)
    if pending:
        return closed(
            LIGHT_LIBRARY_NEEDS_RECOVERY,
            "pending library operations must be recovered before backup",
            pending_operation_ids=pending,
            next_actions=[RECOVER_ACTION],
        )
    diagnostics = library_diagnostics(workspace)
    if any(item["code"] in {"LIBRARY_STAGING_NONEMPTY", "LIBRARY_JOURNAL_FOREIGN"} for item in diagnostics):
        return closed(
            LIGHT_LIBRARY_NEEDS_RECOVERY,
            "library staging or foreign journals must be resolved before backup",
            diagnostics=diagnostics,
            next_actions=[RECOVER_ACTION],
        )
    if knowledge_staging_nonempty(workspace):
        return closed(
            LIGHT_LIBRARY_NEEDS_RECOVERY,
            "nonempty knowledge staging must be recovered by retrying import/build before backup",
            next_actions=["Retry the knowledge import or build that owns the staging directory."],
        )
    transactions = classify_transaction_tree(workspace)
    if transactions["kind"] in {"pending", "unknown", "unsafe"}:
        return closed(
            LIGHT_LIBRARY_NEEDS_RECOVERY,
            transactions.get("message") or "PDF transaction state is unsafe to back up",
        )
    index = classify_index_tree(workspace)
    if index["kind"] in {"unknown", "unsafe"}:
        return closed(LIGHT_LIBRARY_INVALID, index.get("message") or "index tree contains unrecognized extra content")
    return None
