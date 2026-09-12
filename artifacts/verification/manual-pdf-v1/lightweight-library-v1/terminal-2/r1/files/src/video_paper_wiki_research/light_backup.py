"""Deterministic lightweight workspace backup and fresh-root restore. No Vault reuse."""

from __future__ import annotations

import os
import secrets
import stat
import zipfile
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki_research.light_index import classify_index_tree
from video_paper_wiki_research.light_library import library_backup_blockers
from video_paper_wiki_research.light_library_state import (
    BACKUP_SCHEMA,
    HISTORY_DIRNAME,
    INDEX_DIRNAME,
    KNOWLEDGE_DIRNAME,
    KNOWLEDGE_STAGING,
    LIBRARY_DIRNAME,
    LIGHT_BACKUP_CONFLICT,
    LIGHT_BACKUP_INVALID,
    LIGHT_WORKSPACE_BUSY,
    LOCKS_DIRNAME,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_UNCOMPRESSED_BYTES,
    MAX_ZIP_BYTES,
    RESTORATION_SCHEMA,
    SESSIONS_DIRNAME,
    TRANSACTIONS_DIR,
    WORKFLOW_DIRNAME,
    WORKFLOW_STAGING,
    WORKSPACE_INVALID,
    WORKSPACE_LOCK_NAME,
    HEX64,
    _Busy,
    classify_text_file,
    closed,
    exclusive_workspace_lock,
    fail,
    file_is_hardlinked,
    has_work_component,
    is_regular_dir,
    is_regular_file,
    knowledge_staging_nonempty,
    limits_ok,
    list_names,
    ok_result,
    persisted_bytes,
    posix_rel,
    require_work_path,
    require_workspace,
    run_library_inject,
    sha256_bytes,
    sha256_canonical,
    validate_relpath,
)
from video_paper_wiki_research.light_pdf import classify_transaction_tree, lock_is_held

MANIFEST_NAME = "LIGHT-LIBRARY-MANIFEST.json"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_EXTERNAL_ATTR = (0o100600 << 16)
SESSION_NAMES = frozenset(
    {"request.json", "context.json", "manifest.json", "completion-intent.json", "completion.json"}
)
REINDEX_ACTION = "Rebuild the lexical index with build_index in the restored workspace."
REPREPARE_ACTION = "Call prepare_workflow again for any new session; restored sessions are history only."


def _workspace_id(workspace: Path) -> str:
    return sha256_canonical({"workspace_root": str(workspace)})


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _known_session_lock(name: str) -> bool:
    if name == WORKSPACE_LOCK_NAME:
        return True
    if name.endswith(".lock") and HEX64.fullmatch(name[: -len(".lock")]):
        return True
    return False


def _classify_workflow(workspace: Path, *, held_workspace_lock: bool) -> dict[str, Any]:
    root = workspace / WORKFLOW_DIRNAME
    exclude: list[str] = []
    remap_prefix = f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/"
    include_from_sessions: list[str] = []
    if not os.path.lexists(root):
        return {"kind": "absent", "exclude": exclude, "session_files": include_from_sessions, "message": None}
    if root.is_symlink() or not root.is_dir():
        return {"kind": "unsafe", "exclude": [], "session_files": [], "message": ".light-workflow is not a regular directory"}
    locks = root / LOCKS_DIRNAME
    if os.path.lexists(locks):
        if locks.is_symlink() or not locks.is_dir():
            return {"kind": "unsafe", "exclude": [], "session_files": [], "message": "workflow locks path is not a regular directory"}
        for item in sorted(locks.iterdir(), key=lambda path: path.name):
            relative = f"{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}/{item.name}"
            if item.is_symlink() or not item.is_file() or not _known_session_lock(item.name):
                return {"kind": "unknown", "exclude": [], "session_files": [], "message": f"unrecognized workflow lock {relative}"}
            held = lock_is_held(item)
            if item.name == WORKSPACE_LOCK_NAME and held_workspace_lock:
                held = False
            if held:
                return {"kind": "pending", "exclude": [], "session_files": [], "message": f"active workflow lock {relative}"}
            exclude.append(relative)
    staging = root / WORKFLOW_STAGING
    if os.path.lexists(staging):
        if staging.is_symlink() or not staging.is_dir():
            return {"kind": "unsafe", "exclude": [], "session_files": [], "message": "workflow staging is not a regular directory"}
        if list_names(staging):
            return {"kind": "pending", "exclude": [], "session_files": [], "message": "pending or unknown workflow staging must be resolved before backup"}
        exclude.append(f"{WORKFLOW_DIRNAME}/{WORKFLOW_STAGING}")
    sessions = root / SESSIONS_DIRNAME
    if os.path.lexists(sessions):
        if sessions.is_symlink() or not sessions.is_dir():
            return {"kind": "unsafe", "exclude": [], "session_files": [], "message": "workflow sessions path is not a regular directory"}
        for item in sorted(sessions.iterdir(), key=lambda path: path.name):
            rel = f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/{item.name}"
            if item.is_symlink() or not item.is_dir() or not HEX64.fullmatch(item.name):
                return {"kind": "unknown", "exclude": [], "session_files": [], "message": f"unknown session entry {rel}"}
            lock_path = workspace / WORKFLOW_DIRNAME / LOCKS_DIRNAME / f"{item.name}.lock"
            if is_regular_file(lock_path) and lock_is_held(lock_path):
                return {"kind": "pending", "exclude": [], "session_files": [], "message": f"active completion lock for session {item.name}"}
            names = set(list_names(item))
            extras = names - SESSION_NAMES
            if extras:
                return {"kind": "unknown", "exclude": [], "session_files": [], "message": f"session {item.name} contains unsupported extra files"}
            required = {"request.json", "context.json", "manifest.json"}
            if names and not required <= names and names - required:
                # allow incomplete prepared set only when the present names are allowed session documents
                pass
            for name in sorted(names):
                child = item / name
                classified = classify_text_file(child, label=f"{rel}/{name}")
                if classified["kind"] != "ok":
                    return {"kind": "unknown", "exclude": [], "session_files": [], "message": classified.get("reason") or f"session file is unsafe: {rel}/{name}"}
                include_from_sessions.append(f"{rel}/{name}")
    return {"kind": "ok", "exclude": exclude, "session_files": include_from_sessions, "message": None, "remap_prefix": remap_prefix}


def _snapshot_workspace(workspace: Path, *, extra_outputs: list[Path], held_workspace_lock: bool) -> dict[str, Any]:
    blockers = library_backup_blockers(workspace)
    if blockers is not None:
        return blockers
    if knowledge_staging_nonempty(workspace):
        return closed(
            LIGHT_BACKUP_INVALID,
            "nonempty knowledge staging must be recovered by retrying import/build before backup",
        )
    index = classify_index_tree(workspace)
    if index["kind"] in {"unknown", "unsafe"}:
        return closed(LIGHT_BACKUP_INVALID, index.get("message") or "index tree is not a recognized rebuildable tree")
    transactions = classify_transaction_tree(workspace)
    if transactions["kind"] in {"pending", "unknown", "unsafe"}:
        return closed(LIGHT_BACKUP_INVALID, transactions.get("message") or "transaction tree is unsafe")
    workflow = _classify_workflow(workspace, held_workspace_lock=held_workspace_lock)
    if workflow["kind"] not in {"ok", "absent"}:
        return closed(LIGHT_BACKUP_INVALID, workflow.get("message") or "workflow tree is unsafe")

    exclude_set = set(index.get("exclude") or []) | set(transactions.get("exclude") or []) | set(workflow.get("exclude") or [])
    workspace_id = _workspace_id(workspace)
    remap_to = f"{WORKFLOW_DIRNAME}/{HISTORY_DIRNAME}/{workspace_id}/{SESSIONS_DIRNAME}/"
    files: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    total = 0

    def _add_file(relative: str, path: Path, *, archive_path: str | None = None) -> dict[str, Any] | None:
        nonlocal total
        classified = classify_text_file(path, label=relative)
        if classified["kind"] == "unsupported-size":
            return closed(LIGHT_BACKUP_INVALID, classified["reason"], path=relative)
        if classified["kind"] != "ok":
            return closed(LIGHT_BACKUP_INVALID, classified.get("reason") or f"refusing unsupported file {relative}", path=relative)
        dest = archive_path or relative
        files.append({"path": dest, "size_bytes": classified["size_bytes"], "sha256": classified["sha256"]})
        total += classified["size_bytes"]
        return None

    skip_prefixes = (
        f"{INDEX_DIRNAME}/",
        f"{TRANSACTIONS_DIR}/",
        f"{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}/",
        f"{WORKFLOW_DIRNAME}/{WORKFLOW_STAGING}/",
        f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/",
        f"{KNOWLEDGE_DIRNAME}/{KNOWLEDGE_STAGING}/",
    )
    skip_exact = {INDEX_DIRNAME, TRANSACTIONS_DIR, f"{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}", f"{WORKFLOW_DIRNAME}/{WORKFLOW_STAGING}", f"{KNOWLEDGE_DIRNAME}/{KNOWLEDGE_STAGING}"}

    for dirpath, dirnames, filenames in os.walk(workspace, followlinks=False):
        base = Path(dirpath)
        dirnames.sort()
        filenames.sort()
        rel_dir = posix_rel(str(base.relative_to(workspace))) if base != workspace else ""
        for name in list(dirnames):
            child = base / name
            rel = f"{rel_dir}/{name}".lstrip("/") if rel_dir else name
            if child.is_symlink():
                return closed(LIGHT_BACKUP_INVALID, f"refusing symlink directory {rel}")
            if rel in skip_exact or any(rel == prefix[:-1] for prefix in skip_prefixes if prefix.endswith("/")):
                if rel == f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}":
                    dirnames.remove(name)
                    continue
                if rel == INDEX_DIRNAME or rel == TRANSACTIONS_DIR or rel == f"{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}" or rel == f"{WORKFLOW_DIRNAME}/{WORKFLOW_STAGING}" or rel == f"{KNOWLEDGE_DIRNAME}/{KNOWLEDGE_STAGING}":
                    dirnames.remove(name)
                    continue
            if not child.is_dir():
                return closed(LIGHT_BACKUP_INVALID, f"refusing non-directory entry {rel}")
        for name in filenames:
            child = base / name
            rel = f"{rel_dir}/{name}".lstrip("/") if rel_dir else name
            if rel in exclude_set or any(rel.startswith(prefix) for prefix in skip_prefixes):
                continue
            if child.is_symlink():
                return closed(LIGHT_BACKUP_INVALID, f"refusing symlink {rel}")
            if file_is_hardlinked(child):
                return closed(LIGHT_BACKUP_INVALID, f"refusing hardlinked file {rel}")
            refused = _add_file(rel, child)
            if refused is not None:
                return refused

    for relative in workflow.get("session_files") or []:
        live = workspace / relative
        archive_path = remap_to + relative[len(f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/") :]
        if any(item["path"] == archive_path for item in files):
            return closed(LIGHT_BACKUP_CONFLICT, f"session restore path collides with an existing member {archive_path}")
        refused = _add_file(relative, live, archive_path=archive_path)
        if refused is not None:
            return refused

    for path in exclude_set:
        exclusions.append({"path": path, "rule": _exclusion_rule(path)})
    exclusions.sort(key=lambda item: item["path"])

    extra_rows: list[dict[str, Any]] = []
    for extra in extra_outputs:
        given = require_work_path(extra, name="extra_outputs item", must_exist=True, kind="file")
        if _is_inside(given, workspace):
            return closed(LIGHT_BACKUP_INVALID, "extra_outputs path is already inside the workspace and must not be repeated")
        if given.suffix.casefold() != ".md":
            return closed(LIGHT_BACKUP_INVALID, "extra_outputs must be regular .md text files", path=str(given))
        classified = classify_text_file(given, label=str(given))
        if classified["kind"] != "ok":
            return closed(LIGHT_BACKUP_INVALID, classified.get("reason") or "extra output is not allowed text", path=str(given))
        archive_path = f"exports/external/{classified['sha256']}/{given.name}"
        if any(item["path"].casefold() == archive_path.casefold() and item["path"] != archive_path for item in files):
            return closed(LIGHT_BACKUP_CONFLICT, f"extra output collides by casefold with {archive_path}")
        if any(item["path"] == archive_path and item["sha256"] != classified["sha256"] for item in files):
            return closed(LIGHT_BACKUP_CONFLICT, f"extra output collides with a different workspace member {archive_path}")
        if all(item["path"] != archive_path for item in files):
            files.append({"path": archive_path, "size_bytes": classified["size_bytes"], "sha256": classified["sha256"]})
            total += classified["size_bytes"]
        extra_rows.append(
            {
                "original_path": str(given),
                "archive_path": archive_path,
                "restore_path": archive_path,
                "hash": classified["sha256"],
            }
        )

    files.sort(key=lambda item: item["path"])
    folded: dict[str, str] = {}
    for item in files:
        key = item["path"].casefold()
        if key in folded and folded[key] != item["path"]:
            return closed(LIGHT_BACKUP_CONFLICT, f"archive member casefold collision: {item['path']}")
        folded[key] = item["path"]
        error = validate_relpath(item["path"])
        if error:
            return closed(LIGHT_BACKUP_INVALID, error, path=item["path"])
    limit = limits_ok(len(files), total)
    if limit:
        return closed(LIGHT_BACKUP_INVALID, limit)

    extra_by_archive = {row["archive_path"]: row["original_path"] for row in extra_rows}
    contents: dict[str, bytes] = {}
    for item in files:
        archive_path = item["path"]
        if archive_path in extra_by_archive:
            source = Path(extra_by_archive[archive_path])
        elif archive_path.startswith(remap_to):
            source = workspace / f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/" / archive_path[len(remap_to) :]
        else:
            source = workspace / archive_path
        data = source.read_bytes()
        if sha256_bytes(data) != item["sha256"] or len(data) != item["size_bytes"]:
            return closed(LIGHT_BACKUP_CONFLICT, f"file changed while snapshotting {archive_path}")
        contents[archive_path] = data

    return {
        "ok": True,
        "workspace": workspace,
        "workspace_id": workspace_id,
        "files": files,
        "exclusions": exclusions,
        "extra_outputs": extra_rows,
        "restore_remaps": {f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/": remap_to},
        "contents": contents,
        "total_bytes": total,
    }


def _exclusion_rule(path: str) -> str:
    if path.startswith(INDEX_DIRNAME):
        return "rebuildable-index"
    if path.startswith(TRANSACTIONS_DIR):
        return "unlocked-paper-lock" if path.endswith(".lock") else "empty-transaction-staging"
    if path.endswith(WORKSPACE_LOCK_NAME):
        return "unlocked-workspace-lock"
    if f"/{LOCKS_DIRNAME}/" in path:
        return "unlocked-session-lock"
    if path.endswith(f"/{WORKFLOW_STAGING}") or path.endswith(WORKFLOW_STAGING):
        return "empty-workflow-staging"
    return "recognized-ephemeral"


def _manifest_object(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "schema": BACKUP_SCHEMA,
        "workspace_root": str(snapshot["workspace"]),
        "workspace_id": snapshot["workspace_id"],
        "files": list(snapshot["files"]),
        "exclusions": list(snapshot["exclusions"]),
        "extra_outputs": list(snapshot["extra_outputs"]),
        "restore_remaps": dict(snapshot["restore_remaps"]),
    }
    body["manifest_sha256"] = sha256_canonical({key: value for key, value in body.items() if key != "manifest_sha256"})
    return body


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = ZIP_EXTERNAL_ATTR
    info.internal_attr = 0
    info.extra = b""
    info.comment = b""
    return info


def _write_zip(path: Path, manifest: Mapping[str, Any], contents: Mapping[str, bytes]) -> bytes:
    manifest_bytes = persisted_bytes(manifest)
    with path.open("wb") as handle:
        with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            archive.writestr(_zip_info(MANIFEST_NAME), manifest_bytes)
            for item in manifest["files"]:
                member = item["path"]
                archive.writestr(_zip_info(member), contents[member])
    data = path.read_bytes()
    if len(data) > MAX_ZIP_BYTES:
        path.unlink()
        fail(LIGHT_BACKUP_INVALID, "backup container exceeds the 136 MiB limit")
    return data


def _open_zip(archive_path: Path) -> zipfile.ZipFile:
    if archive_path.is_symlink() or not archive_path.is_file():
        fail(LIGHT_BACKUP_INVALID, "archive_path must be a regular file")
    if file_is_hardlinked(archive_path):
        fail(LIGHT_BACKUP_INVALID, "archive_path must not be hardlinked")
    size = archive_path.stat().st_size
    if size > MAX_ZIP_BYTES:
        fail(LIGHT_BACKUP_INVALID, "backup container exceeds the 136 MiB limit")
    try:
        archive = zipfile.ZipFile(archive_path, "r", allowZip64=False)
    except zipfile.BadZipFile as exc:
        fail(LIGHT_BACKUP_INVALID, "archive is not a valid ZIP")
        raise AssertionError("unreachable") from exc
    return archive


def _verify_zip(archive_path: Path) -> dict[str, Any]:
    archive = _open_zip(archive_path)
    try:
        infos = archive.infolist()
        if not infos:
            return closed(LIGHT_BACKUP_INVALID, "archive has no members")
        if infos[0].filename != MANIFEST_NAME:
            return closed(LIGHT_BACKUP_INVALID, "LIGHT-LIBRARY-MANIFEST.json must be the first ZIP member")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            return closed(LIGHT_BACKUP_INVALID, "archive contains duplicate members")
        folded = [name.casefold() for name in names]
        if len(folded) != len(set(folded)):
            return closed(LIGHT_BACKUP_INVALID, "archive contains casefold-colliding members")
        uncompressed = 0
        file_count = 0
        for info in infos:
            if info.filename.endswith("/") or info.is_dir():
                return closed(LIGHT_BACKUP_INVALID, "archive must not contain directory members")
            if info.compress_type != zipfile.ZIP_STORED:
                return closed(LIGHT_BACKUP_INVALID, "archive members must use ZIP_STORED")
            if info.flag_bits & 0x1:
                return closed(LIGHT_BACKUP_INVALID, "encrypted ZIP members are refused")
            if getattr(info, "file_size", 0) > 0xFFFFFFFF or getattr(info, "compress_size", 0) > 0xFFFFFFFF:
                return closed(LIGHT_BACKUP_INVALID, "ZIP64 members are refused")
            error = validate_relpath(info.filename)
            if error:
                return closed(LIGHT_BACKUP_INVALID, error, path=info.filename)
            if info.filename != MANIFEST_NAME and info.date_time != ZIP_TIMESTAMP:
                return closed(LIGHT_BACKUP_INVALID, f"member timestamp must be 1980-01-01 00:00:00: {info.filename}")
            if info.filename == MANIFEST_NAME and info.file_size > MAX_FILE_BYTES:
                return closed(LIGHT_BACKUP_INVALID, "manifest exceeds the 8 MiB text limit")
            if info.filename != MANIFEST_NAME:
                file_count += 1
                uncompressed += info.file_size
                if info.file_size > MAX_FILE_BYTES:
                    return closed(LIGHT_BACKUP_INVALID, f"member exceeds the 8 MiB text limit: {info.filename}")
        if file_count > MAX_FILES:
            return closed(LIGHT_BACKUP_INVALID, "inventory exceeds the 10,000 file limit")
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            return closed(LIGHT_BACKUP_INVALID, "inventory exceeds the 128 MiB uncompressed limit")
        raw_manifest = archive.read(MANIFEST_NAME)
        if len(raw_manifest) != infos[0].file_size:
            return closed(LIGHT_BACKUP_INVALID, "manifest claimed size does not match bytes read")
        try:
            manifest = __import__("json").loads(raw_manifest.decode("utf-8"))
        except (UnicodeError, ValueError):
            return closed(LIGHT_BACKUP_INVALID, "manifest is not UTF-8 JSON")
        if type(manifest) is not dict:
            return closed(LIGHT_BACKUP_INVALID, "manifest root must be an object")
        expected_keys = {"schema", "workspace_root", "workspace_id", "files", "exclusions", "extra_outputs", "restore_remaps", "manifest_sha256"}
        if set(manifest) != expected_keys:
            return closed(LIGHT_BACKUP_INVALID, "manifest has unknown or missing top-level fields")
        if manifest.get("schema") != BACKUP_SCHEMA:
            return closed(LIGHT_BACKUP_INVALID, "manifest schema is not video-paper-wiki.light-backup.v1")
        try:
            if raw_manifest != persisted_bytes(manifest):
                return closed(LIGHT_BACKUP_INVALID, "manifest ZIP member is not canonical JSON plus one LF")
        except (TypeError, ValueError):
            return closed(LIGHT_BACKUP_INVALID, "manifest is not canonical JSON")
        body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        if manifest.get("manifest_sha256") != sha256_canonical(body):
            return closed(LIGHT_BACKUP_INVALID, "manifest_sha256 does not match the canonical manifest")
        files = manifest.get("files")
        if type(files) is not list:
            return closed(LIGHT_BACKUP_INVALID, "manifest files must be an array")
        expected_names = [item.get("path") for item in files if type(item) is dict]
        if expected_names != sorted(name for name in expected_names if type(name) is str):
            return closed(LIGHT_BACKUP_INVALID, "manifest files must be sorted by path")
        zip_files = names[1:]
        if zip_files != expected_names:
            return closed(LIGHT_BACKUP_INVALID, "ZIP members after the manifest must match the sorted file inventory")
        contents: dict[str, bytes] = {}
        for info, item in zip(infos[1:], files):
            if type(item) is not dict or set(item) != {"path", "size_bytes", "sha256"}:
                return closed(LIGHT_BACKUP_INVALID, "each file inventory row must be {path,size_bytes,sha256}")
            if info.filename != item["path"]:
                return closed(LIGHT_BACKUP_INVALID, "ZIP member order does not match the manifest")
            handle = archive.open(info, "r")
            try:
                chunks: list[bytes] = []
                remaining = item["size_bytes"]
                if type(remaining) is not int or remaining < 0 or remaining != info.file_size:
                    return closed(LIGHT_BACKUP_INVALID, f"claimed size is invalid for {info.filename}")
                while True:
                    chunk = handle.read(65536)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    if remaining < 0:
                        return closed(LIGHT_BACKUP_INVALID, f"member is larger than its claimed size: {info.filename}")
                    chunks.append(chunk)
                data = b"".join(chunks)
            finally:
                handle.close()
            if len(data) != item["size_bytes"]:
                return closed(LIGHT_BACKUP_INVALID, f"member size mismatch for {info.filename}")
            if sha256_bytes(data) != item["sha256"]:
                return closed(LIGHT_BACKUP_INVALID, f"member hash mismatch for {info.filename}")
            if classify_text_file.__module__:
                from video_paper_wiki_research.light_library_state import decode_utf8_text, looks_binary, text_name_allowed

                if looks_binary(data) or decode_utf8_text(data) is None:
                    return closed(LIGHT_BACKUP_INVALID, f"member is not allowed UTF-8 text: {info.filename}")
                basename = Path(info.filename).name
                if not text_name_allowed(basename) and not info.filename.startswith("exports/external/"):
                    return closed(LIGHT_BACKUP_INVALID, f"member name is not an allowed text/code file: {info.filename}")
            contents[info.filename] = data
        remaps = manifest.get("restore_remaps")
        if type(remaps) is not dict or set(remaps) != {f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/"}:
            return closed(LIGHT_BACKUP_INVALID, "restore_remaps must map sessions/ to history/<workspace_id>/sessions/")
        expected_remap = f"{WORKFLOW_DIRNAME}/{HISTORY_DIRNAME}/{manifest['workspace_id']}/{SESSIONS_DIRNAME}/"
        if remaps.get(f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/") != expected_remap:
            return closed(LIGHT_BACKUP_INVALID, "restore_remaps target does not match workspace_id")
        extras = manifest.get("extra_outputs")
        if type(extras) is not list:
            return closed(LIGHT_BACKUP_INVALID, "extra_outputs must be an array")
        return ok_result(
            "backup archive is valid",
            schema=BACKUP_SCHEMA,
            workspace_root=manifest.get("workspace_root"),
            workspace_id=manifest.get("workspace_id"),
            file_count=len(files),
            exclusions=manifest.get("exclusions"),
            extra_outputs=extras,
            restore_remaps=remaps,
            manifest_sha256=manifest.get("manifest_sha256"),
            manifest=manifest,
            contents=contents,
        )
    finally:
        archive.close()


def create_backup(workspace_root: Path, *, output: Path, extra_outputs: list[Path] | None = None) -> dict[str, Any]:
    workspace = require_workspace(workspace_root)
    output_path = require_work_path(output, name="output", must_exist=False, allow_missing=True, kind="file")
    if output_path.suffix.casefold() != ".zip":
        fail(LIGHT_BACKUP_INVALID, "backup output must be a .zip path")
    if _is_inside(output_path, workspace):
        fail(LIGHT_BACKUP_INVALID, "backup output must be outside the backed-up workspace")
    parent = output_path.parent
    if not is_regular_dir(parent):
        fail(WORKSPACE_INVALID, "backup output parent must be an existing regular .work directory")
    extras = list(extra_outputs or [])
    try:
        with exclusive_workspace_lock(workspace):
            first = _snapshot_workspace(workspace, extra_outputs=extras, held_workspace_lock=True)
            if first.get("ok") is not True:
                return first
            run_library_inject("after_backup_snapshot")
            second = _snapshot_workspace(workspace, extra_outputs=extras, held_workspace_lock=True)
            if second.get("ok") is not True:
                return second
            if sha256_canonical({"files": first["files"], "extra": first["extra_outputs"]}) != sha256_canonical({"files": second["files"], "extra": second["extra_outputs"]}):
                return closed(LIGHT_BACKUP_CONFLICT, "workspace files changed while creating the backup snapshot")
            manifest = _manifest_object(second)
            encoded = persisted_bytes(manifest)
            token = secrets.token_hex(8)
            tmp = parent / f".{output_path.name}.{token}.tmp"
            if os.path.lexists(tmp):
                return closed(LIGHT_BACKUP_CONFLICT, "owned backup staging path already exists")
            try:
                _write_zip(tmp, manifest, second["contents"])
                run_library_inject("before_backup_publish")
                if output_path.exists():
                    existing = output_path.read_bytes()
                    produced = tmp.read_bytes()
                    if existing == produced:
                        tmp.unlink()
                        return ok_result(
                            "reused an exact existing backup archive",
                            archive_path=str(output_path),
                            workspace_id=second["workspace_id"],
                            file_count=len(second["files"]),
                            reused=True,
                            exclusions=second["exclusions"],
                            extra_outputs=second["extra_outputs"],
                            restore_remaps=second["restore_remaps"],
                            manifest_sha256=manifest["manifest_sha256"],
                            next_actions=[],
                        )
                    tmp.unlink()
                    return closed(LIGHT_BACKUP_CONFLICT, "backup output already exists and is not byte-identical")
                os.rename(tmp, output_path)
            except BaseException:
                if is_regular_file(tmp):
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                raise
            return ok_result(
                "created a deterministic lightweight workspace backup",
                archive_path=str(output_path),
                workspace_id=second["workspace_id"],
                file_count=len(second["files"]),
                reused=False,
                exclusions=second["exclusions"],
                extra_outputs=second["extra_outputs"],
                restore_remaps=second["restore_remaps"],
                manifest_sha256=manifest["manifest_sha256"],
                next_actions=["Keep original PDFs external; restore into a new .work destination and rebuild the index."],
            )
    except _Busy:
        return closed(LIGHT_WORKSPACE_BUSY, "another cooperating operation currently owns this workspace")


def verify_backup(archive_path: Path) -> dict[str, Any]:
    path = Path(archive_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if path.is_symlink() or not path.is_file():
        fail(LIGHT_BACKUP_INVALID, "archive_path must be a regular file")
    verified = _verify_zip(path)
    if verified.get("ok") is not True:
        return {key: value for key, value in verified.items() if key not in {"manifest", "contents"}}
    return {
        "ok": True,
        "status": "OK",
        "message": verified["message"],
        "schema": BACKUP_SCHEMA,
        "workspace_root": verified["workspace_root"],
        "workspace_id": verified["workspace_id"],
        "file_count": verified["file_count"],
        "exclusions": verified["exclusions"],
        "extra_outputs": verified["extra_outputs"],
        "restore_remaps": verified["restore_remaps"],
        "manifest_sha256": verified["manifest_sha256"],
    }


def restore_backup(archive_path: Path, *, destination: Path) -> dict[str, Any]:
    archive = Path(archive_path).expanduser()
    if not archive.is_absolute():
        archive = Path.cwd() / archive
    if archive.is_symlink() or not archive.is_file():
        fail(LIGHT_BACKUP_INVALID, "archive_path must be a regular file")
    dest_given = Path(destination).expanduser()
    if not dest_given.is_absolute():
        dest_given = Path.cwd() / dest_given
    dest_given = Path(os.path.normpath(dest_given))
    if not has_work_component(dest_given):
        fail(WORKSPACE_INVALID, "destination must be under .work/**", {"path": str(dest_given)})
    if os.path.lexists(dest_given):
        return closed(LIGHT_BACKUP_CONFLICT, "restore destination already exists, including an empty directory")
    parent = dest_given.parent
    parent_resolved = require_work_path(parent, name="destination parent", must_exist=True, kind="dir")
    dest = dest_given
    if dest.resolve().parent != parent_resolved and dest.parent.resolve() != parent_resolved:
        fail(WORKSPACE_INVALID, "destination parent must be a safe .work directory")
    verified = _verify_zip(archive)
    if verified.get("ok") is not True:
        return {key: value for key, value in verified.items() if key not in {"manifest", "contents"}}
    manifest = verified["manifest"]
    contents: dict[str, bytes] = verified["contents"]
    token = secrets.token_hex(8)
    stage = parent_resolved / f".light-backup-stage-{token}"
    payload = stage / "payload"
    if os.path.lexists(stage):
        return closed(LIGHT_BACKUP_CONFLICT, "owned restore staging path already exists")
    try:
        stage.mkdir(exist_ok=False)
        payload.mkdir(exist_ok=False)
        for item in manifest["files"]:
            relative = item["path"]
            error = validate_relpath(relative)
            if error:
                return closed(LIGHT_BACKUP_INVALID, error, path=relative)
            target = payload / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.parent.is_symlink() or not target.parent.is_dir():
                return closed(LIGHT_BACKUP_INVALID, f"restore parent is unsafe for {relative}")
            target.write_bytes(contents[relative])
            os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
            if sha256_bytes(target.read_bytes()) != item["sha256"]:
                return closed(LIGHT_BACKUP_INVALID, f"restored bytes do not match the manifest for {relative}")
        record = {
            "schema": RESTORATION_SCHEMA,
            "source_archive": str(archive.resolve()),
            "source_workspace_root": manifest["workspace_root"],
            "source_workspace_id": manifest["workspace_id"],
            "destination": str(dest),
            "historical_session_root": manifest["restore_remaps"][f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/"],
            "restore_remaps": manifest["restore_remaps"],
        }
        from video_paper_wiki_research.light_library_state import write_persisted_atomic

        (payload / LIBRARY_DIRNAME).mkdir(exist_ok=True)
        write_persisted_atomic(payload / LIBRARY_DIRNAME / "restoration.json", record)
        if os.path.lexists(dest):
            return closed(LIGHT_BACKUP_CONFLICT, "restore destination appeared before publication")
        os.rename(payload, dest)
    finally:
        if os.path.lexists(stage):
            _cleanup_stage(stage)
    historical = dest / manifest["restore_remaps"][f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/"].rstrip("/")
    return ok_result(
        "restored a fresh workspace; historical sessions are not active",
        destination=str(dest.resolve()),
        historical_session_root=str(historical),
        workspace_id=manifest["workspace_id"],
        file_count=len(manifest["files"]),
        extra_outputs=manifest["extra_outputs"],
        exclusions=manifest["exclusions"],
        restore_remaps=manifest["restore_remaps"],
        next_actions=[REINDEX_ACTION, REPREPARE_ACTION],
    )


def _cleanup_stage(stage: Path) -> None:
    if stage.is_symlink() or not stage.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(stage, topdown=False, followlinks=False):
        base = Path(dirpath)
        for name in filenames:
            child = base / name
            if child.is_symlink() or not child.is_file():
                continue
            try:
                child.unlink()
            except OSError:
                pass
        try:
            base.rmdir()
        except OSError:
            pass
