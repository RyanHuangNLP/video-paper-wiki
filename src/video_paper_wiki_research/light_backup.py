"""Deterministic lightweight workspace backup and fresh-root restore. No Vault reuse."""

from __future__ import annotations

import os
import secrets
import stat
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki_research.light_index import classify_index_tree
from video_paper_wiki_research.light_knowledge_batch import (
    LIGHT_BATCH_CONFLICT,
    knowledge_batch_backup_blockers,
)
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
    chain_has_symlink,
    classify_text_file,
    closed,
    decode_utf8_text,
    exclusive_rename,
    exclusive_workspace_lock,
    fail,
    file_is_hardlinked,
    has_work_component,
    is_regular_dir,
    is_regular_file,
    require_explicit_extra_markdown,
    knowledge_staging_nonempty,
    limits_ok,
    list_names,
    looks_binary,
    ok_result,
    persisted_bytes,
    posix_rel,
    require_work_path,
    require_workspace,
    run_library_inject,
    sha256_bytes,
    sha256_canonical,
    text_name_allowed,
    validate_relpath,
)
from video_paper_wiki_research.light_pdf import classify_transaction_tree, lock_is_held
from video_paper_wiki_research.light_writing_project import (
    LIGHT_WRITING_PROJECT_CONFLICT,
    STAGING_DIRNAME as WRITING_STAGING,
    WRITING_DIRNAME,
    writing_backup_blockers,
)

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
    batch_blockers = knowledge_batch_backup_blockers(workspace)
    if batch_blockers:
        first = batch_blockers[0]
        code = LIGHT_BACKUP_CONFLICT if first.get("status") == LIGHT_BATCH_CONFLICT else LIGHT_BACKUP_INVALID
        return closed(code, first["message"], path=first.get("path"))
    writing_blockers = writing_backup_blockers(workspace)
    if writing_blockers:
        first = writing_blockers[0]
        status = first.get("status")
        code = LIGHT_BACKUP_CONFLICT if status in {LIGHT_WRITING_PROJECT_CONFLICT, "conflict"} else LIGHT_BACKUP_INVALID
        return closed(code, first["message"], path=first.get("path"))
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
        f"{WRITING_DIRNAME}/{WRITING_STAGING}/",
    )
    skip_exact = {
        INDEX_DIRNAME,
        TRANSACTIONS_DIR,
        f"{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}",
        f"{WORKFLOW_DIRNAME}/{WORKFLOW_STAGING}",
        f"{KNOWLEDGE_DIRNAME}/{KNOWLEDGE_STAGING}",
        f"{WRITING_DIRNAME}/{WRITING_STAGING}",
    }

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
                if rel == INDEX_DIRNAME or rel == TRANSACTIONS_DIR or rel == f"{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}" or rel == f"{WORKFLOW_DIRNAME}/{WORKFLOW_STAGING}" or rel == f"{KNOWLEDGE_DIRNAME}/{KNOWLEDGE_STAGING}" or rel == f"{WRITING_DIRNAME}/{WRITING_STAGING}":
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
        given = require_explicit_extra_markdown(extra)
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


def _snapshot_identity(snapshot: Mapping[str, Any]) -> str:
    return sha256_canonical(
        {
            "workspace_id": snapshot["workspace_id"],
            "files": snapshot["files"],
            "exclusions": snapshot["exclusions"],
            "extra_outputs": snapshot["extra_outputs"],
            "restore_remaps": snapshot["restore_remaps"],
        }
    )


def _prefix_collisions(paths: list[str]) -> str | None:
    ordered = sorted(paths)
    for index, left in enumerate(ordered):
        prefix = left + "/"
        for right in ordered[index + 1 :]:
            if right.startswith(prefix):
                return f"file/directory prefix collision: {left} vs {right}"
            if not right.startswith(left[:1]):
                break
    return None


def _require_backup_archive(archive_path: Path) -> Path:
    path = Path(archive_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = Path(os.path.normpath(path))
    if chain_has_symlink(path):
        fail(LIGHT_BACKUP_INVALID, "archive_path must not traverse a symlink", {"path": str(path)})
    if path.is_symlink() or not path.is_file():
        fail(LIGHT_BACKUP_INVALID, "archive_path must be a regular file")
    if file_is_hardlinked(path):
        fail(LIGHT_BACKUP_INVALID, "archive_path must not be hardlinked")
    return path


def _read_bounded_archive(archive_path: Path) -> tuple[bytes | None, str | None]:
    try:
        st = archive_path.stat()
    except OSError:
        return None, "archive_path is unreadable"
    if st.st_size > MAX_ZIP_BYTES:
        return None, "backup container exceeds the 136 MiB limit"
    identity = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    try:
        with archive_path.open("rb") as handle:
            data = handle.read(MAX_ZIP_BYTES + 1)
    except OSError:
        return None, "archive_path is unreadable"
    if len(data) > MAX_ZIP_BYTES:
        return None, "backup container exceeds the 136 MiB limit"
    try:
        now = archive_path.stat()
    except OSError:
        return None, "archive_path is unreadable"
    if (now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns) != identity:
        return None, "archive identity changed while reading"
    if len(data) != st.st_size:
        return None, "archive size changed while reading"
    return data, None


def _extra_has_zip64(extra: bytes) -> bool:
    offset = 0
    while offset + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, offset)
        offset += 4
        if header_id == 0x0001:
            return True
        offset += size
        if offset > len(extra):
            return True
    return False


ZIP_LOCAL_NEEDED = 20
ZIP_CENTRAL_MADE = 788
ZIP_CENTRAL_NEEDED = 20
ZIP_UTF8_FLAG = 0x0800


def _zip_filename_and_flags(name: bytes, flags: int) -> tuple[str | None, str | None]:
    """Accept the stdlib writer's ASCII flag 0 and non-ASCII UTF-8 flag 0x0800 only."""
    if flags & ~ZIP_UTF8_FLAG:
        return None, "ZIP64, encrypted, compressed, or data-descriptor members are refused"
    try:
        filename = name.decode("utf-8")
    except UnicodeError:
        return None, "ZIP member name is not UTF-8"
    expected = ZIP_UTF8_FLAG if any(byte > 127 for byte in name) else 0
    if flags != expected:
        return None, "ZIP member filename encoding flag is not the supported writer convention"
    return filename, None


def _unpack(fmt: str, data: bytes, offset: int) -> tuple[Any, ...]:
    size = struct.calcsize(fmt)
    if offset < 0 or offset + size > len(data):
        raise ValueError("truncated ZIP structure")
    return struct.unpack_from(fmt, data, offset)


def _inspect_zip_container(data: bytes) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        return _parse_deterministic_zip(data)
    except (struct.error, ValueError):
        return None, "archive is not a valid ZIP"


def _parse_deterministic_zip(data: bytes) -> tuple[list[dict[str, Any]] | None, str | None]:
    if type(data) is not bytes or len(data) < 22:
        return None, "archive is not a valid ZIP"
    search = data[-(65535 + 22) :] if len(data) > 65535 + 22 else data
    pos = search.rfind(b"PK\x05\x06")
    if pos < 0:
        return None, "archive is missing a standard end-of-central-directory"
    eocd_off = len(data) - len(search) + pos
    if eocd_off + 22 > len(data):
        return None, "archive is not a valid ZIP"
    disk, disk_cd, nthis, ntotal, cd_size, cd_off, comment_len = _unpack("<HHHHIIH", data, eocd_off + 4)
    if disk != 0 or disk_cd != 0:
        return None, "multi-disk ZIP archives are refused"
    if comment_len != 0:
        return None, "ZIP comments are refused"
    if eocd_off + 22 + comment_len != len(data):
        return None, "ZIP trailing bytes are refused"
    if nthis == 0xFFFF or ntotal == 0xFFFF or cd_size == 0xFFFFFFFF or cd_off == 0xFFFFFFFF:
        return None, "ZIP64 metadata is refused"
    if nthis != ntotal or ntotal == 0:
        return None, "ZIP entry counts are inconsistent"
    if eocd_off >= 20 and data[eocd_off - 20 : eocd_off - 16] == b"PK\x06\x07":
        return None, "ZIP64 metadata is refused"
    if b"PK\x06\x06" in data[max(0, eocd_off - 56) : eocd_off]:
        return None, "ZIP64 metadata is refused"
    if cd_off + cd_size != eocd_off:
        return None, "ZIP central directory is not contiguous with EOCD"
    cursor = cd_off
    centrals: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for _ in range(ntotal):
        if cursor + 4 > len(data) or data[cursor : cursor + 4] != b"PK\x01\x02":
            return None, "ZIP central directory entry is malformed"
        (
            made,
            needed,
            flags,
            method,
            mtime,
            mdate,
            crc,
            csize,
            usize,
            name_len,
            extra_len,
            comment_len_c,
            disk_start,
            internal,
            external,
            local_off,
        ) = _unpack("<HHHHHHIIIHHHHHII", data, cursor + 4)
        name_start = cursor + 46
        extra_start = name_start + name_len
        comment_start = extra_start + extra_len
        next_cursor = comment_start + comment_len_c
        if next_cursor > len(data):
            return None, "ZIP central directory entry is malformed"
        name = data[name_start:extra_start]
        extra = data[extra_start:comment_start]
        comment = data[comment_start:next_cursor]
        if made != ZIP_CENTRAL_MADE or needed != ZIP_CENTRAL_NEEDED:
            return None, "ZIP member versions are not the supported writer format"
        if method != 0 or disk_start != 0 or internal != 0:
            return None, "ZIP64, encrypted, compressed, or data-descriptor members are refused"
        filename, flag_error = _zip_filename_and_flags(name, flags)
        if flag_error is not None or filename is None:
            return None, flag_error
        if mtime != 0 or mdate != 0x0021:
            return None, "member timestamp must be 1980-01-01 00:00:00"
        if csize == 0xFFFFFFFF or usize == 0xFFFFFFFF or local_off == 0xFFFFFFFF:
            return None, "ZIP64 metadata is refused"
        if csize != usize:
            return None, "ZIP stored sizes must match"
        if extra or comment or _extra_has_zip64(extra):
            return None, "ZIP extra fields and comments are refused"
        if external != ZIP_EXTERNAL_ATTR:
            return None, "ZIP member attributes must be private regular files"
        if filename in seen_names:
            return None, "archive contains duplicate members"
        seen_names.add(filename)
        centrals.append(
            {
                "name": filename,
                "flags": flags,
                "crc": crc,
                "size": usize,
                "local_off": local_off,
            }
        )
        cursor = next_cursor
    if cursor != eocd_off:
        return None, "ZIP central directory size is inconsistent"
    expected_off = 0
    members: list[dict[str, Any]] = []
    for item in centrals:
        local_off = item["local_off"]
        if local_off != expected_off:
            return None, "ZIP local headers have unaccounted gaps or overlaps"
        if local_off + 4 > len(data) or data[local_off : local_off + 4] != b"PK\x03\x04":
            return None, "ZIP local header is malformed"
        needed, flags, method, mtime, mdate, crc, csize, usize, name_len, extra_len = _unpack(
            "<HHHHHIIIHH", data, local_off + 4
        )
        name_start = local_off + 30
        extra_start = name_start + name_len
        data_off = extra_start + extra_len
        if data_off > len(data):
            return None, "ZIP local header is malformed"
        name = data[name_start:extra_start]
        extra = data[extra_start:data_off]
        if needed != ZIP_LOCAL_NEEDED or method != 0:
            return None, "ZIP64, encrypted, compressed, or data-descriptor members are refused"
        filename, flag_error = _zip_filename_and_flags(name, flags)
        if flag_error is not None or filename is None:
            return None, flag_error
        if mtime != 0 or mdate != 0x0021:
            return None, "member timestamp must be 1980-01-01 00:00:00"
        if csize == 0xFFFFFFFF or usize == 0xFFFFFFFF or csize != usize:
            return None, "ZIP64 metadata is refused"
        if extra or _extra_has_zip64(extra):
            return None, "ZIP extra fields and comments are refused"
        if (
            filename != item["name"]
            or flags != item["flags"]
            or crc != item["crc"]
            or usize != item["size"]
            or csize != item["size"]
        ):
            return None, "ZIP local and central metadata are inconsistent"
        if data_off + usize > len(data):
            return None, "ZIP member payload overruns the central directory"
        payload = data[data_off : data_off + usize]
        if len(payload) != usize:
            return None, "ZIP member payload is truncated"
        if (zlib.crc32(payload) & 0xFFFFFFFF) != crc:
            return None, f"member CRC mismatch for {filename}"
        members.append({"name": filename, "crc": crc, "size": usize, "payload": payload})
        expected_off = data_off + usize
    if expected_off != cd_off:
        return None, "ZIP local members are not contiguous with the central directory"
    return members, None


def _absolute_normalized_posix(value: object, *, require_work: bool) -> bool:
    if type(value) is not str or not value or "\x00" in value or "\\" in value:
        return False
    if not value.startswith("/") or value != value.strip():
        return False
    if value != os.path.normpath(value):
        return False
    parts = value.split("/")[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    if require_work and ".work" not in parts:
        return False
    return True


def _path_is_within_root(child: str, root: str) -> bool:
    if child == root:
        return True
    prefix = root if root.endswith("/") else root + "/"
    return child.startswith(prefix)


def _known_exclusion_path(path: str) -> bool:
    if path == INDEX_DIRNAME or path.startswith(INDEX_DIRNAME + "/"):
        return True
    if path == TRANSACTIONS_DIR or path.startswith(TRANSACTIONS_DIR + "/"):
        return True
    locks = f"{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}"
    if path == locks or path.startswith(locks + "/"):
        return True
    workflow_stage = f"{WORKFLOW_DIRNAME}/{WORKFLOW_STAGING}"
    if path == workflow_stage or path.startswith(workflow_stage + "/"):
        return True
    knowledge_stage = f"{KNOWLEDGE_DIRNAME}/{KNOWLEDGE_STAGING}"
    if path == knowledge_stage or path.startswith(knowledge_stage + "/"):
        return True
    return False


def _documented_exclusion_rule(path: str) -> str | None:
    if not _known_exclusion_path(path):
        return None
    return _exclusion_rule(path)


def _validate_manifest_object(manifest: Mapping[str, Any], *, zip_names: list[str]) -> str | None:
    expected_keys = {
        "schema",
        "workspace_root",
        "workspace_id",
        "files",
        "exclusions",
        "extra_outputs",
        "restore_remaps",
        "manifest_sha256",
    }
    if set(manifest) != expected_keys:
        return "manifest has unknown or missing top-level fields"
    if type(manifest.get("schema")) is not str or manifest.get("schema") != BACKUP_SCHEMA:
        return "manifest schema is not video-paper-wiki.light-backup.v1"
    workspace_root = manifest.get("workspace_root")
    if not _absolute_normalized_posix(workspace_root, require_work=True):
        return "workspace_root must be an absolute normalized POSIX .work path"
    workspace_id = manifest.get("workspace_id")
    if type(workspace_id) is not str or HEX64.fullmatch(workspace_id) is None:
        return "workspace_id must be 64 lowercase hex characters"
    if workspace_id != sha256_canonical({"workspace_root": workspace_root}):
        return "workspace_id does not match canonical {workspace_root}"
    files = manifest.get("files")
    if type(files) is not list:
        return "manifest files must be an array"
    expected_names: list[str] = []
    for item in files:
        if type(item) is not dict or set(item) != {"path", "size_bytes", "sha256"}:
            return "each file inventory row must be {path,size_bytes,sha256}"
        path = item.get("path")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if type(path) is not str or validate_relpath(path) is not None:
            return "manifest file path is unsafe"
        if type(size) is not int or type(size) is bool or size < 0 or size > MAX_FILE_BYTES:
            return f"claimed size is invalid for {path}"
        if type(digest) is not str or HEX64.fullmatch(digest) is None:
            return f"file hash is invalid for {path}"
        expected_names.append(path)
    if expected_names != sorted(expected_names) or len(expected_names) != len(set(expected_names)):
        return "manifest files must be unique and sorted by path"
    if zip_names[1:] != expected_names:
        return "ZIP members after the manifest must match the sorted file inventory"
    collision = _prefix_collisions(expected_names)
    if collision:
        return collision
    exclusions = manifest.get("exclusions")
    if type(exclusions) is not list:
        return "exclusions must be an array of {path,rule} objects"
    included = {item["path"] for item in files}
    seen_ex: set[str] = set()
    for item in exclusions:
        if type(item) is not dict or set(item) != {"path", "rule"}:
            return "each exclusion row must be {path,rule}"
        path = item.get("path")
        rule = item.get("rule")
        if type(path) is not str or type(rule) is not str or not path or not rule:
            return "exclusion path and rule must be nonempty strings"
        if validate_relpath(path) is not None:
            return "exclusion path is unsafe"
        expected_rule = _documented_exclusion_rule(path)
        if expected_rule is None or rule != expected_rule:
            return "exclusion path/rule is not a recognized producer policy row"
        if path in included or any(member == path or member.startswith(path + "/") for member in included):
            return "exclusion row contradicts an included inventory member"
        if path in seen_ex:
            return "exclusions contain duplicate paths"
        seen_ex.add(path)
    if [item["path"] for item in exclusions] != sorted(item["path"] for item in exclusions):
        return "exclusions must be sorted by path"
    remaps = manifest.get("restore_remaps")
    if type(remaps) is not dict or set(remaps) != {f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/"}:
        return "restore_remaps must map sessions/ to history/<workspace_id>/sessions/"
    expected_remap = f"{WORKFLOW_DIRNAME}/{HISTORY_DIRNAME}/{workspace_id}/{SESSIONS_DIRNAME}/"
    if remaps.get(f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/") != expected_remap:
        return "restore_remaps target does not match workspace_id"
    extras = manifest.get("extra_outputs")
    if type(extras) is not list:
        return "extra_outputs must be an array"
    files_by_path = {item["path"]: item for item in files}
    seen_extra: set[str] = set()
    for extra in extras:
        if type(extra) is not dict or set(extra) != {"original_path", "archive_path", "restore_path", "hash"}:
            return "each extra_outputs row must be {original_path,archive_path,restore_path,hash}"
        original = extra.get("original_path")
        archive_path = extra.get("archive_path")
        restore_path = extra.get("restore_path")
        digest = extra.get("hash")
        if not _absolute_normalized_posix(original, require_work=False):
            return "extra_outputs original_path is not a safe path string"
        if type(original) is not str or not original.endswith(".md"):
            return "extra_outputs original_path must be an absolute .md path"
        if _path_is_within_root(str(original), str(workspace_root)):
            return "extra_outputs original_path must be outside the original workspace"
        if type(archive_path) is not str or type(restore_path) is not str or archive_path != restore_path:
            return "extra_outputs archive_path and restore_path must match"
        if validate_relpath(archive_path) is not None or Path(archive_path).suffix.casefold() != ".md":
            return "extra_outputs paths must be safe .md members"
        if type(digest) is not str or HEX64.fullmatch(digest) is None:
            return "extra_outputs hash is invalid"
        prefix = f"exports/external/{digest}/"
        if not archive_path.startswith(prefix) or archive_path.count("/") != 3:
            return "extra_outputs must map to exports/external/<sha256>/<basename>.md"
        if Path(archive_path).name != Path(original).name:
            return "extra_outputs basename does not match the mapped archive member"
        member = files_by_path.get(archive_path)
        if member is None:
            return "extra_outputs path is not an inventory member"
        if member["sha256"] != digest:
            return "extra_outputs hash does not match the inventory member"
        if archive_path in seen_extra:
            return "extra_outputs contains duplicate archive paths"
        seen_extra.add(archive_path)
    return None


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


def _member_metadata_error(info: zipfile.ZipInfo) -> str | None:
    unix_mode = (info.external_attr >> 16) & 0o170777
    if stat.S_ISLNK(unix_mode) or ((info.external_attr >> 16) & 0o170000) == 0o120000:
        return f"symlink ZIP members are refused: {info.filename}"
    if info.external_attr != ZIP_EXTERNAL_ATTR:
        return f"ZIP member attributes must be private regular files: {info.filename}"
    if info.date_time != ZIP_TIMESTAMP:
        return f"member timestamp must be 1980-01-01 00:00:00: {info.filename}"
    if info.extra != b"" or info.comment != b"" or _extra_has_zip64(info.extra):
        return f"ZIP extra fields and comments are refused: {info.filename}"
    if getattr(info, "extract_version", 0) >= 45 or getattr(info, "create_version", 0) >= 45:
        return f"ZIP64 metadata is refused: {info.filename}"
    if info.compress_type != zipfile.ZIP_STORED:
        return "archive members must use ZIP_STORED"
    if info.flag_bits & 0x1:
        return "encrypted ZIP members are refused"
    if getattr(info, "file_size", 0) > 0xFFFFFFFF or getattr(info, "compress_size", 0) > 0xFFFFFFFF:
        return "ZIP64 members are refused"
    return None


def _verify_zip(archive_path: Path) -> dict[str, Any]:
    raw_container, read_error = _read_bounded_archive(archive_path)
    if read_error:
        return closed(LIGHT_BACKUP_INVALID, read_error)
    if raw_container is None:
        return closed(LIGHT_BACKUP_INVALID, "archive_path is unreadable")
    members, container_error = _inspect_zip_container(raw_container)
    if container_error or members is None:
        return closed(LIGHT_BACKUP_INVALID, container_error or "archive is not a valid ZIP")
    try:
        if not members:
            return closed(LIGHT_BACKUP_INVALID, "archive has no members")
        if members[0]["name"] != MANIFEST_NAME:
            return closed(LIGHT_BACKUP_INVALID, "LIGHT-LIBRARY-MANIFEST.json must be the first ZIP member")
        names = [item["name"] for item in members]
        if len(names) != len(set(names)):
            return closed(LIGHT_BACKUP_INVALID, "archive contains duplicate members")
        folded = [name.casefold() for name in names]
        if len(folded) != len(set(folded)):
            return closed(LIGHT_BACKUP_INVALID, "archive contains casefold-colliding members")
        uncompressed = 0
        file_count = 0
        for item in members:
            filename = item["name"]
            if filename.endswith("/"):
                return closed(LIGHT_BACKUP_INVALID, "archive must not contain directory members")
            error = validate_relpath(filename)
            if error:
                return closed(LIGHT_BACKUP_INVALID, error, path=filename)
            size = item["size"]
            if filename == MANIFEST_NAME and size > MAX_FILE_BYTES:
                return closed(LIGHT_BACKUP_INVALID, "manifest exceeds the 8 MiB text limit")
            if filename != MANIFEST_NAME:
                file_count += 1
                uncompressed += size
                if size > MAX_FILE_BYTES:
                    return closed(LIGHT_BACKUP_INVALID, f"member exceeds the 8 MiB text limit: {filename}")
        if file_count > MAX_FILES:
            return closed(LIGHT_BACKUP_INVALID, "inventory exceeds the 10,000 file limit")
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            return closed(LIGHT_BACKUP_INVALID, "inventory exceeds the 128 MiB uncompressed limit")
        raw_manifest = members[0]["payload"]
        if len(raw_manifest) != members[0]["size"]:
            return closed(LIGHT_BACKUP_INVALID, "manifest claimed size does not match bytes read")
        try:
            manifest = __import__("json").loads(raw_manifest.decode("utf-8"))
        except (UnicodeError, ValueError):
            return closed(LIGHT_BACKUP_INVALID, "manifest is not UTF-8 JSON")
        if type(manifest) is not dict:
            return closed(LIGHT_BACKUP_INVALID, "manifest root must be an object")
        try:
            if raw_manifest != persisted_bytes(manifest):
                return closed(LIGHT_BACKUP_INVALID, "manifest ZIP member is not canonical JSON plus one LF")
        except (TypeError, ValueError):
            return closed(LIGHT_BACKUP_INVALID, "manifest is not canonical JSON")
        body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        if manifest.get("manifest_sha256") != sha256_canonical(body):
            return closed(LIGHT_BACKUP_INVALID, "manifest_sha256 does not match the canonical manifest")
        shape_error = _validate_manifest_object(manifest, zip_names=names)
        if shape_error:
            return closed(LIGHT_BACKUP_INVALID, shape_error)
        files = manifest["files"]
        contents: dict[str, bytes] = {}
        for member, item in zip(members[1:], files):
            if member["name"] != item["path"]:
                return closed(LIGHT_BACKUP_INVALID, "ZIP member order does not match the manifest")
            data = member["payload"]
            if len(data) != item["size_bytes"] or member["size"] != item["size_bytes"]:
                return closed(LIGHT_BACKUP_INVALID, f"member size mismatch for {member['name']}")
            if sha256_bytes(data) != item["sha256"]:
                return closed(LIGHT_BACKUP_INVALID, f"member hash mismatch for {member['name']}")
            if looks_binary(data) or decode_utf8_text(data) is None:
                return closed(LIGHT_BACKUP_INVALID, f"member is not allowed UTF-8 text: {member['name']}")
            if not text_name_allowed(Path(member["name"]).name):
                return closed(LIGHT_BACKUP_INVALID, f"member name is not an allowed text/code file: {member['name']}")
            contents[member["name"]] = data
        return ok_result(
            "backup archive is valid",
            schema=BACKUP_SCHEMA,
            workspace_root=manifest.get("workspace_root"),
            workspace_id=manifest.get("workspace_id"),
            file_count=len(files),
            exclusions=manifest.get("exclusions"),
            extra_outputs=manifest.get("extra_outputs"),
            restore_remaps=manifest.get("restore_remaps"),
            manifest_sha256=manifest.get("manifest_sha256"),
            manifest=manifest,
            contents=contents,
        )
    except zipfile.BadZipFile:
        return closed(LIGHT_BACKUP_INVALID, "archive is not a valid ZIP")


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
                third = _snapshot_workspace(workspace, extra_outputs=extras, held_workspace_lock=True)
                if third.get("ok") is not True:
                    if is_regular_file(tmp):
                        tmp.unlink()
                    return third
                if _snapshot_identity(second) != _snapshot_identity(third):
                    if is_regular_file(tmp):
                        tmp.unlink()
                    return closed(LIGHT_BACKUP_CONFLICT, "workspace files changed after archive construction and before publication")
                produced = tmp.read_bytes()
                if os.path.lexists(output_path):
                    if output_path.is_symlink() or not output_path.is_file() or file_is_hardlinked(output_path):
                        tmp.unlink()
                        return closed(LIGHT_BACKUP_CONFLICT, "backup output exists and is not a reusable regular file")
                    existing = output_path.read_bytes()
                    tmp.unlink()
                    if existing == produced:
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
                    return closed(LIGHT_BACKUP_CONFLICT, "backup output already exists and is not byte-identical")
                run_library_inject("before_backup_rename")
                try:
                    os.link(tmp, output_path)
                except FileExistsError:
                    existing = None
                    if is_regular_file(output_path) and not output_path.is_symlink():
                        existing = output_path.read_bytes()
                    tmp.unlink()
                    if existing == produced:
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
                    return closed(LIGHT_BACKUP_CONFLICT, "backup output appeared before publication and was preserved")
                except OSError:
                    if is_regular_file(tmp):
                        tmp.unlink()
                    return closed(LIGHT_BACKUP_CONFLICT, "could not publish the backup archive without replacing an existing path")
                tmp.unlink()
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
    path = _require_backup_archive(archive_path)
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
    archive = _require_backup_archive(archive_path)
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
    owned_snapshot: dict[str, Any] | None = None
    published = False
    result: dict[str, Any] | None = None
    try:
        stage.mkdir(exist_ok=False)
        payload.mkdir(exist_ok=False)
        owned_snapshot = _scan_owned_tree(stage)
        collision = _prefix_collisions([item["path"] for item in manifest["files"]])
        if collision:
            result = closed(LIGHT_BACKUP_INVALID, collision)
            return result
        for item in manifest["files"]:
            relative = item["path"]
            error = validate_relpath(relative)
            if error:
                result = closed(LIGHT_BACKUP_INVALID, error, path=relative)
                return result
            target = payload / relative
            if os.path.lexists(target) or target.is_symlink():
                result = closed(LIGHT_BACKUP_CONFLICT, f"restore path already exists: {relative}")
                return result
            for ancestor in target.parents:
                if ancestor == payload:
                    break
                if ancestor.is_file() or ancestor.is_symlink():
                    result = closed(LIGHT_BACKUP_INVALID, f"file/directory prefix collision before extract: {relative}")
                    return result
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.parent.is_symlink() or not target.parent.is_dir() or target.parent.is_file():
                result = closed(LIGHT_BACKUP_INVALID, f"restore parent is unsafe for {relative}")
                return result
            target.write_bytes(contents[relative])
            os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
            if sha256_bytes(target.read_bytes()) != item["sha256"]:
                result = closed(LIGHT_BACKUP_INVALID, f"restored bytes do not match the manifest for {relative}")
                return result
            owned_snapshot = _scan_owned_tree(stage)
        from video_paper_wiki_research.light_library_state import write_persisted_atomic

        restoration_rel = f"{LIBRARY_DIRNAME}/restorations/{manifest['workspace_id']}.json"
        reserved = f"{LIBRARY_DIRNAME}/restoration.json"
        wrote_restoration = False
        if restoration_rel not in contents:
            record = {
                "schema": RESTORATION_SCHEMA,
                "source_archive": str(archive.resolve()),
                "source_workspace_root": manifest["workspace_root"],
                "source_workspace_id": manifest["workspace_id"],
                "destination": str(dest),
                "historical_session_root": manifest["restore_remaps"][f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/"],
                "restore_remaps": manifest["restore_remaps"],
            }
            record_path = payload / restoration_rel
            record_path.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(payload / reserved) and reserved in contents:
                pass
            if not os.path.lexists(record_path):
                write_persisted_atomic(record_path, record)
                wrote_restoration = True
                owned_snapshot = _scan_owned_tree(stage)
        actual: dict[str, str] = {}
        for dirpath, _dirnames, filenames in os.walk(payload, followlinks=False):
            base = Path(dirpath)
            for name in filenames:
                child = base / name
                rel = posix_rel(str(child.relative_to(payload)))
                if child.is_symlink() or not child.is_file():
                    result = closed(LIGHT_BACKUP_INVALID, f"restored payload is unsafe: {rel}")
                    return result
                actual[rel] = sha256_bytes(child.read_bytes())
        expected = {name: sha256_bytes(data) for name, data in contents.items()}
        if wrote_restoration:
            expected[restoration_rel] = actual.get(restoration_rel, "")
        if actual != expected:
            result = closed(LIGHT_BACKUP_INVALID, "restored inventory does not match the archive")
            return result
        if reserved in contents and actual.get(reserved) != sha256_bytes(contents[reserved]):
            result = closed(LIGHT_BACKUP_INVALID, "archived restoration record was overwritten")
            return result
        owned_snapshot = _scan_owned_tree(stage)
        try:
            run_library_inject("before_restore_publish")
            exclusive_rename(payload, dest)
            published = True
        except FileExistsError:
            result = closed(LIGHT_BACKUP_CONFLICT, "restore destination appeared before publication")
            return result
        except OSError:
            result = closed(LIGHT_BACKUP_INVALID, f"restore publication failed; staged bytes remain at {stage}", path=str(stage))
            return result
    finally:
        if os.path.lexists(stage):
            current = _scan_owned_tree(stage)
            if published:
                if current is not None and not current["files"]:
                    _cleanup_owned_restore_stage(stage, current)
            elif owned_snapshot is not None and current == owned_snapshot:
                _cleanup_owned_restore_stage(stage, owned_snapshot)
            elif result is not None:
                result["path"] = str(stage)
    if result is not None:
        return result
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


def _scan_owned_tree(root: Path) -> dict[str, Any] | None:
    if root.is_symlink() or not root.is_dir():
        return None
    files: list[dict[str, Any]] = []
    directories: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        dirnames.sort()
        filenames.sort()
        for name in dirnames:
            child = base / name
            if child.is_symlink() or not child.is_dir():
                return None
            directories.append(posix_rel(str(child.relative_to(root))))
        for name in filenames:
            child = base / name
            if child.is_symlink() or not child.is_file() or file_is_hardlinked(child):
                return None
            rel = posix_rel(str(child.relative_to(root)))
            data = child.read_bytes()
            files.append({"path": rel, "size_bytes": len(data), "sha256": sha256_bytes(data)})
    files.sort(key=lambda item: item["path"])
    return {"files": files, "directories": sorted(directories)}


def _cleanup_owned_restore_stage(stage: Path, expected: Mapping[str, Any]) -> bool:
    current = _scan_owned_tree(stage)
    if current is None or current["files"] != list(expected.get("files") or []) or current["directories"] != list(expected.get("directories") or []):
        return False
    for item in current["files"]:
        child = stage / str(item["path"])
        if not is_regular_file(child) or file_is_hardlinked(child):
            return False
        try:
            child.unlink()
        except OSError:
            return False
    for rel in sorted(current["directories"], key=lambda path: path.count("/"), reverse=True):
        child = stage / rel
        try:
            if list_names(child):
                return False
            child.rmdir()
        except OSError:
            return False
    try:
        if list_names(stage):
            return False
        stage.rmdir()
    except OSError:
        return False
    return not os.path.lexists(stage)
