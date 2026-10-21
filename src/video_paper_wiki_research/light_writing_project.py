"""Content-addressed writing projects with outline and section revision history.

This module does not change legacy light_writing. The current conversation model
stays outside Python. CLI/Skill/backup integration is a later explicit handoff.
"""
from __future__ import annotations

import math
import os
import re
import secrets
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import (
    LIGHT_CONTEXT_INVALID,
    LIGHT_SELECTION_INVALID,
    SOURCE_INVALID,
    WORKSPACE_INVALID,
    rewrite_markdown_links,
    validate_live_context,
)
from video_paper_wiki_research.light_index import INDEX_STALE, OK
from video_paper_wiki_research.light_knowledge import require_product_workspace
from video_paper_wiki_research.light_library_state import exclusive_rename
from video_paper_wiki_research.light_qa import (
    CONTEXT_SCHEMA,
    _CITE_MARK,
    _anchor,
    _readable_mark,
    body_chunk_ids,
    check_model_document,
    copy_evidence,
)
from video_paper_wiki_research.light_workflow import (
    LIGHT_WORKSPACE_BUSY,
    LIGHT_WORKSPACE_MISMATCH,
    _Busy,
    _exclusive_lock,
    _workspace_lock_path,
    canonical_bytes,
    persisted_bytes,
    sha256_bytes,
    sha256_canonical,
)

LIGHT_WRITING_PROJECT_INVALID = "LIGHT_WRITING_PROJECT_INVALID"
LIGHT_WRITING_PROJECT_CONFLICT = "LIGHT_WRITING_PROJECT_CONFLICT"

WRITING_DIRNAME = ".light-writing"
PROJECTS_DIRNAME = "projects"
REVISIONS_DIRNAME = "revisions"
STAGING_DIRNAME = "staging"
HEAD_NAME = "HEAD.json"
CONTEXT_NAME = "context.json"
DOCUMENT_NAME = "document.json"
MANIFEST_NAME = "manifest.json"
DRAFT_NAME = "draft.md"
OWNERSHIP_NAME = "ownership.json"
PAYLOAD_DIRNAME = "payload"
INTENT_NAME = "intent.json"
PENDING_HEAD_KIND = "pending-head"
PENDING_HEAD_SCHEMA = "video-paper-wiki.light-writing-pending-head.v1"

OUTLINE_CONTEXT_SCHEMA = "video-paper-wiki.light-writing-outline-context.v1"
OUTLINE_DOCUMENT_SCHEMA = "video-paper-wiki.light-writing-outline.v1"
SECTION_CONTEXT_SCHEMA = "video-paper-wiki.light-writing-section-context.v1"
SECTION_DOCUMENT_SCHEMA = "video-paper-wiki.light-writing-section.v1"
PROJECT_SCHEMA = "video-paper-wiki.light-writing-project.v1"
REVISION_SCHEMA = "video-paper-wiki.light-writing-revision.v1"
REVISION_IDENTITY_SCHEMA = "video-paper-wiki.light-writing-revision-identity.v1"
MANIFEST_SCHEMA = "video-paper-wiki.light-writing-revision-manifest.v1"
HEAD_SCHEMA = "video-paper-wiki.light-writing-head.v1"
RESULT_SCHEMA = "video-paper-wiki.light-writing-result.v1"
HISTORY_SCHEMA = "video-paper-wiki.light-writing-history.v1"
EXPORT_SCHEMA = "video-paper-wiki.light-writing-export.v1"
OWNERSHIP_SCHEMA = "video-paper-wiki.light-writing-ownership.v1"

OUTLINE_EXPORT_KEYS = ("ok", "status", "message", "schema", "context", "context_sha256", "prompt")
SECTION_EXPORT_KEYS = (
    "ok",
    "status",
    "message",
    "schema",
    "project_id",
    "parent_revision_id",
    "section_id",
    "context",
    "context_sha256",
    "outline",
    "previous_section",
    "instructions",
    "prompt",
    "wrapper_sha256",
)
RESULT_KEYS = (
    "ok",
    "status",
    "message",
    "schema",
    "project_id",
    "revision_id",
    "parent_revision_id",
    "page_path",
    "reused",
    "progress",
)
HISTORY_KEYS = (
    "ok",
    "status",
    "message",
    "schema",
    "project_id",
    "head_revision_id",
    "revisions",
    "diagnostics",
)
EXPORT_KEYS = ("ok", "status", "message", "schema", "project_id", "revision_id", "path", "reused", "progress")
REVISION_DOC_KEYS = (
    "schema",
    "project_id",
    "parent_revision_id",
    "kind",
    "target_section_id",
    "instructions",
    "title",
    "outline",
    "sections",
)
SECTION_STATE_KEYS = ("section_id", "status", "markdown", "citations")
REVISION_FILE_NAMES = (CONTEXT_NAME, DOCUMENT_NAME, DRAFT_NAME)
REVISION_DIR_NAMES = frozenset({CONTEXT_NAME, DOCUMENT_NAME, DRAFT_NAME, MANIFEST_NAME})

STATUS_PROVISIONAL = "provisional"
STATUS_UNKNOWN = "unknown"
STATUS_UNWRITTEN = "unwritten"
KIND_OUTLINE = "outline"
KIND_SECTION = "section"
UNKNOWN_TEXT = "证据不足"
UNWRITTEN_TEXT = "尚未撰写"
PROVISIONAL_LABEL = "模型建议草稿，非正式科学评审。"

MAX_OUTLINE_SECTIONS = 16
MAX_TITLE = 300
MAX_GOAL = 2_000
MAX_INSTRUCTIONS = 4_000
MAX_SECTION_MARKDOWN = 16_000
MAX_CITATIONS = 32
MAX_WRAPPER_CHARS = 80_000
MAX_OUTLINE_DOCUMENT_CHARS = 32_000
MAX_SECTION_REVISIONS = 128
MAX_DIAGNOSTICS = 32

HEX64 = re.compile(r"^[0-9a-f]{64}$")
SECTION_ID = re.compile(r"^s[1-9][0-9]?$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MARKDOWN_WS = frozenset("\n\r\t")
_MANAGED_OUTPUT_ROOTS = frozenset(
    {
        WRITING_DIRNAME,
        ".light-index",
        "papers",
        ".light-knowledge",
        ".light-library",
        ".light-workflow",
        ".light-transactions",
        "knowledge",
    }
)

OUTLINE_MESSAGE = "exported writing outline context for the current conversation model"
OUTLINE_PROMPT = (
    "Write one video-paper-wiki.light-writing-outline.v1 object for this writing topic "
    "using only the evidence chunks below. Include a title and 1-16 ordered sections. "
    "Each section has section_id matching s[1-9][0-9]?, title, goal, status provisional or "
    "unknown, and citations. Provisional sections cite 1-32 distinct current evidence "
    "chunk ids. Unknown sections use goal 证据不足 and no citations. At least one section "
    "must be provisional. Do not invent papers, pages, chunk ids, or sources. "
    "Do not put [@chunk_id] marks in titles or goals."
)
SECTION_MESSAGE = "exported writing section context for the current conversation model"
SECTION_PROMPT = (
    "Revise only the selected section using the original writing evidence, outline, and "
    "current section text. Return one video-paper-wiki.light-writing-section.v1 object. "
    "Provisional markdown must be nonblank, cite current evidence as [@chunk_id], and "
    "list the same chunk ids. Unknown sections use markdown 证据不足 and no citations. "
    "Do not invent papers, pages, chunk ids, or sources."
)
HISTORY_OK_MESSAGE = "listed writing project revision history"
EXPORT_OK_MESSAGE = "exported writing project markdown"
EXPORT_INCOMPLETE_MESSAGE = "exported writing project markdown with incomplete sections"

LIVE_STATUSES = frozenset(
    {
        INDEX_STALE,
        SOURCE_INVALID,
        LIGHT_SELECTION_INVALID,
        LIGHT_CONTEXT_INVALID,
        LIGHT_WORKSPACE_MISMATCH,
        LIGHT_WORKSPACE_BUSY,
        WORKSPACE_INVALID,
    }
)


def _raise(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise ResearchError(code, message, details)


def _closed(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "status": status, "message": message}
    payload.update(extra)
    return payload


def _live_closed(live: Mapping[str, Any]) -> dict[str, Any]:
    status = str(live.get("status") or LIGHT_WRITING_PROJECT_INVALID)
    message = live.get("message") if type(live.get("message")) is str else status
    return _closed(status, message)


def _catch(exc: ResearchError) -> dict[str, Any]:
    return _closed(exc.code, exc.message)


@contextmanager
def _workspace_lock(workspace: Path) -> Iterator[None]:
    try:
        with _exclusive_lock(_workspace_lock_path(workspace), workspace):
            yield
    except _Busy as exc:
        raise ResearchError(LIGHT_WORKSPACE_BUSY, "workspace is busy") from exc


def _is_regular_dir(path: Path) -> bool:
    return (not path.is_symlink()) and path.is_dir()


def _is_regular_file(path: Path) -> bool:
    return (not path.is_symlink()) and path.is_file()


def _hardlinked(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink() and path.stat().st_nlink > 1
    except OSError:
        return True


def _symlink_in_chain(path: Path) -> bool:
    cursor = path
    seen: set[Path] = set()
    while cursor not in seen:
        seen.add(cursor)
        try:
            if cursor.is_symlink():
                return True
        except OSError:
            return True
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent
    return True


def _unsafe_ancestor(path: Path) -> bool:
    cursor = path
    seen: set[Path] = set()
    while cursor not in seen:
        seen.add(cursor)
        try:
            if cursor.is_symlink():
                return True
            if cursor.exists() and cursor.is_file() and _hardlinked(cursor):
                return True
        except OSError:
            return True
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent
    return True


def _has_work_component(path: Path) -> bool:
    return ".work" in path.parts


def _as_supplied_path(value: object, name: str) -> Path:
    if isinstance(value, Path):
        path = value
    elif type(value) is str:
        path = Path(value)
    else:
        _raise(LIGHT_WRITING_PROJECT_INVALID, f"{name} must be a path")
        raise AssertionError("unreachable")
    return path.expanduser()


def _raw_absolute_path(value: object, name: str) -> Path:
    path = _as_supplied_path(value, name)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _reject_raw_traversal(path: Path, name: str) -> None:
    if ".." in path.parts:
        _raise(WORKSPACE_INVALID, f"{name} must not contain parent-traversal components", {"path": str(path)})


def _absolute_path(value: object, name: str) -> Path:
    raw = _raw_absolute_path(value, name)
    _reject_raw_traversal(raw, name)
    return Path(os.path.normpath(raw))


def _lexical_relative(path: Path, root: Path) -> Path | None:
    try:
        return Path(os.path.normpath(path)).relative_to(Path(os.path.normpath(root)))
    except ValueError:
        return None


def _managed_output_alias(workspace: Path, target: Path) -> bool:
    candidates = [target]
    suffix: list[str] = []
    cursor = target
    seen: set[Path] = set()
    while cursor not in seen:
        seen.add(cursor)
        if cursor.exists() or os.path.lexists(cursor):
            try:
                reconstructed = cursor.resolve()
                for part in suffix:
                    reconstructed = reconstructed / part
                candidates.append(reconstructed)
            except (OSError, RuntimeError):
                return True
            break
        suffix.insert(0, cursor.name)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    for candidate in candidates:
        relative = _lexical_relative(candidate, workspace)
        if relative is not None and relative.parts and relative.parts[0] in _MANAGED_OUTPUT_ROOTS:
            return True
    return False


def _require_writing_workspace(workspace_root: object) -> Path:
    raw = _raw_absolute_path(workspace_root, "workspace_root")
    _reject_raw_traversal(raw, "workspace_root")
    if _unsafe_ancestor(raw):
        _raise(WORKSPACE_INVALID, "workspace path must not traverse a symlink or hardlinked file", {"path": str(raw)})
    return require_product_workspace(workspace_root)


def _require_writing_output(workspace: Path, output: object) -> Path:
    raw = _raw_absolute_path(output, "output")
    _reject_raw_traversal(raw, "output")
    if raw.suffix != ".md" or raw.name in {"", ".", ".."}:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "output must be a .md file path", {"path": str(raw)})
    if not _has_work_component(raw):
        _raise(WORKSPACE_INVALID, "output must be under .work/**", {"path": str(raw)})
    if _unsafe_ancestor(raw) or _symlink_in_chain(raw):
        _raise(WORKSPACE_INVALID, "output path must not traverse a symlink or hardlinked file", {"path": str(raw)})
    given = Path(os.path.normpath(raw))
    if not _has_work_component(given):
        _raise(WORKSPACE_INVALID, "output must be under .work/**", {"path": str(given)})
    if _managed_output_alias(workspace, given):
        _raise(WORKSPACE_INVALID, "output must not alias workspace papers, index, or session state", {"path": str(given)})
    parent = given.parent
    if parent.exists() or os.path.lexists(parent):
        if parent.is_symlink() or not parent.is_dir() or _symlink_in_chain(parent) or _unsafe_ancestor(parent):
            _raise(WORKSPACE_INVALID, "output path must not traverse a symlink or hardlinked file", {"path": str(given)})
        resolved = parent.resolve() / given.name
        if not _has_work_component(resolved):
            _raise(WORKSPACE_INVALID, "output must be under .work/**", {"path": str(resolved)})
        if _managed_output_alias(workspace, resolved):
            _raise(WORKSPACE_INVALID, "output must not alias workspace papers, index, or session state", {"path": str(resolved)})
        return resolved
    return given


def _canonical_len(value: object) -> int:
    return len(canonical_bytes(value).decode("utf-8"))


def _has_surrogate_or_undecodable(text: str) -> bool:
    try:
        text.encode("utf-8").decode("utf-8")
    except UnicodeError:
        return True
    return any(0xD800 <= ord(char) <= 0xDFFF for char in text)


def _unsafe_text(text: str, *, allow_markdown_ws: bool) -> bool:
    if _has_surrogate_or_undecodable(text):
        return True
    for char in text:
        if allow_markdown_ws and char in _MARKDOWN_WS:
            continue
        if _CONTROL.search(char):
            return True
        if unicodedata.category(char).startswith("C"):
            return True
    return False


def _control_in(text: str) -> bool:
    return _unsafe_text(text, allow_markdown_ws=False)


def _unsafe_body_text(text: str) -> bool:
    return _unsafe_text(text, allow_markdown_ws=True)


def _has_cite_marks(text: str) -> bool:
    return _CITE_MARK.search(text) is not None


def _escape_md(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("`", "\\`")
        .replace("#", "\\#")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )
    return escaped.replace("\r\n", "\n").replace("\r", "\n")


def _exact_keys(value: object, keys: tuple[str, ...] | set[str] | frozenset[str]) -> bool:
    return type(value) is dict and set(value) == set(keys)


def _is_hex64(value: object) -> bool:
    return type(value) is str and HEX64.fullmatch(value) is not None


def _require_hex64(value: object, name: str) -> str:
    if not _is_hex64(value):
        _raise(LIGHT_WRITING_PROJECT_INVALID, f"{name} must be 64 lowercase hex")
    return str(value)


def _require_dict(value: object, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        _raise(LIGHT_WRITING_PROJECT_INVALID, f"{name} must be an object")
    return value


def _bounded_text(value: object, *, name: str, minimum: int, maximum: int) -> str:
    if type(value) is not str:
        _raise(LIGHT_WRITING_PROJECT_INVALID, f"{name} must be a string")
    if _control_in(value):
        _raise(LIGHT_WRITING_PROJECT_INVALID, f"{name} must not contain control characters")
    if _has_cite_marks(value):
        _raise(LIGHT_WRITING_PROJECT_INVALID, f"{name} must not contain citation marks")
    if not (minimum <= len(value) <= maximum):
        _raise(LIGHT_WRITING_PROJECT_INVALID, f"{name} length is outside the allowed bounds")
    return value


def _writing_root(workspace: Path) -> Path:
    return workspace / WRITING_DIRNAME


def _projects_root(workspace: Path) -> Path:
    return _writing_root(workspace) / PROJECTS_DIRNAME


def _project_dir(workspace: Path, project_id: str) -> Path:
    return _projects_root(workspace) / project_id


def _revisions_root(workspace: Path, project_id: str) -> Path:
    return _project_dir(workspace, project_id) / REVISIONS_DIRNAME


def _revision_dir(workspace: Path, project_id: str, revision_id: str) -> Path:
    return _revisions_root(workspace, project_id) / revision_id


def _head_path(workspace: Path, project_id: str) -> Path:
    return _project_dir(workspace, project_id) / HEAD_NAME


def _staging_root(workspace: Path) -> Path:
    return _writing_root(workspace) / STAGING_DIRNAME


def _page_path(project_id: str, revision_id: str) -> str:
    return f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{project_id}/{REVISIONS_DIRNAME}/{revision_id}/{DRAFT_NAME}"


def _relative_to_workspace(workspace: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(workspace).as_posix()
    except ValueError:
        return path.as_posix()


def _ensure_regular_dir(path: Path, *, stop_at: Path) -> None:
    if path == stop_at:
        if not _is_regular_dir(path):
            _raise(WORKSPACE_INVALID, "workspace_root must be a regular directory")
        return
    if path.exists() or os.path.lexists(path):
        if path.is_symlink() or not path.is_dir() or _symlink_in_chain(path):
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "managed directory is unsafe", {"path": str(path)})
        return
    _ensure_regular_dir(path.parent, stop_at=stop_at)
    path.mkdir(exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "managed directory is unsafe", {"path": str(path)})


def _write_bytes(path: Path, data: bytes) -> None:
    if path.is_symlink() or (os.path.lexists(path) and not path.is_file()):
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "managed file path is unsafe", {"path": str(path)})
    path.write_bytes(data)
    if not _is_regular_file(path) or path.read_bytes() != data:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "managed file bytes changed while writing", {"path": str(path)})


def _file_row(relative: str, data: bytes) -> dict[str, Any]:
    return {"path": relative, "sha256": sha256_bytes(data), "size_bytes": len(data)}


def _sorted_file_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: str(item["path"]))


def _expected_parent_dirs(paths: Mapping[str, bytes] | list[str]) -> set[str]:
    names = list(paths) if not isinstance(paths, Mapping) else list(paths)
    parents: set[str] = set()
    for relative in names:
        current = Path(relative).parent
        while current.as_posix() not in {".", ""}:
            parents.add(current.as_posix())
            current = current.parent
    return parents


def _inspect_tree(directory: Path) -> tuple[dict[str, bytes], set[str]] | None:
    if not _is_regular_dir(directory):
        return None
    files: dict[str, bytes] = {}
    dirs: set[str] = set()
    pending = [directory]
    while pending:
        current = pending.pop()
        if current is not directory:
            if current.is_symlink() or not current.is_dir():
                return None
            dirs.add(current.relative_to(directory).as_posix())
        try:
            entries = sorted(current.iterdir(), key=lambda item: item.name)
        except OSError:
            return None
        for item in entries:
            if item.is_symlink():
                return None
            if item.is_dir():
                pending.append(item)
                continue
            if not item.is_file() or _hardlinked(item):
                return None
            files[item.relative_to(directory).as_posix()] = item.read_bytes()
    return files, dirs


def _complete_set_match(directory: Path, expected: Mapping[str, bytes]) -> bool:
    inspected = _inspect_tree(directory)
    if inspected is None:
        return False
    files, dirs = inspected
    if set(files) != set(expected) or dirs != _expected_parent_dirs(expected):
        return False
    return all(files[key] == expected[key] for key in expected)


def _load_persisted_object(path: Path) -> dict[str, Any] | None:
    if not _is_regular_file(path) or _hardlinked(path):
        return None
    try:
        raw = path.read_bytes()
        value = json_object(raw)
    except (OSError, UnicodeError, ValueError, TypeError):
        return None
    if type(value) is not dict:
        return None
    try:
        if raw != persisted_bytes(value):
            return None
    except (TypeError, ValueError, ResearchError):
        return None
    return value


def json_object(raw: bytes) -> object:
    import json

    return json.loads(raw.decode("utf-8"))


def _progress(sections: list[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(sections)
    written = 0
    unknown = 0
    unwritten = 0
    for item in sections:
        status = item.get("status")
        if status == STATUS_PROVISIONAL:
            written += 1
        elif status == STATUS_UNKNOWN:
            unknown += 1
        elif status == STATUS_UNWRITTEN:
            unwritten += 1
    return {
        "total": total,
        "written": written,
        "unknown": unknown,
        "unwritten": unwritten,
        "complete": unwritten == 0 and written >= 1,
    }


def _result(
    *,
    message: str,
    project_id: str,
    revision_id: str,
    parent_revision_id: str | None,
    reused: bool,
    sections: list[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "message": message,
        "ok": True,
        "page_path": _page_path(project_id, revision_id),
        "parent_revision_id": parent_revision_id,
        "progress": _progress(sections),
        "project_id": project_id,
        "reused": reused,
        "revision_id": revision_id,
        "schema": RESULT_SCHEMA,
        "status": OK,
    }
    return {key: payload[key] for key in RESULT_KEYS}


def _ownership_payload(
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
) -> dict[str, Any]:
    return {
        "allowed_payload_set": sorted(allowed_payload_set),
        "intended_relative_target": intended_relative_target,
        "kind": kind,
        "schema": OWNERSHIP_SCHEMA,
        "target_id": target_id,
        "version": 1,
    }


def _valid_ownership_shape(marker: Mapping[str, Any] | None) -> bool:
    if marker is None:
        return False
    allowed = marker.get("allowed_payload_set")
    return (
        set(marker) == {"allowed_payload_set", "intended_relative_target", "kind", "schema", "target_id", "version"}
        and marker.get("schema") == OWNERSHIP_SCHEMA
        and marker.get("version") == 1
        and type(marker.get("kind")) is str
        and type(marker.get("target_id")) is str
        and type(marker.get("intended_relative_target")) is str
        and type(allowed) is list
        and allowed == sorted(str(item) for item in allowed)
        and all(type(item) is str and item and "\\" not in item and ".." not in Path(item).parts for item in allowed)
    )


def _ownership_matches(
    marker: Mapping[str, Any] | None,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
) -> bool:
    expected = _ownership_payload(
        kind=kind,
        target_id=target_id,
        intended_relative_target=intended_relative_target,
        allowed_payload_set=allowed_payload_set,
    )
    return _valid_ownership_shape(marker) and canonical_bytes(marker) == canonical_bytes(expected)


def _stage_surface_ok(directory: Path) -> bool:
    try:
        names = {item.name for item in directory.iterdir()}
    except OSError:
        return False
    return names <= {OWNERSHIP_NAME, PAYLOAD_DIRNAME}


def _prefix_staging_dirs(workspace: Path, *, kind: str, target_id: str) -> list[Path]:
    root = _staging_root(workspace)
    found: list[Path] = []
    if not _is_regular_dir(root):
        return found
    prefix = f"{kind}-{target_id}-"
    for item in root.iterdir():
        if item.name.startswith(prefix):
            found.append(item)
    return found


def _classify_owned_stage(
    directory: Path,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
    expected: Mapping[str, bytes],
) -> str:
    if directory.is_symlink() or not directory.is_dir() or not _stage_surface_ok(directory):
        return "conflict"
    marker = _load_persisted_object(directory / OWNERSHIP_NAME)
    if not _ownership_matches(
        marker,
        kind=kind,
        target_id=target_id,
        intended_relative_target=intended_relative_target,
        allowed_payload_set=allowed_payload_set,
    ):
        return "conflict"
    payload = directory / PAYLOAD_DIRNAME
    if not payload.exists() and not payload.is_symlink():
        return "owned-empty"
    inspected = _inspect_tree(payload)
    if inspected is None:
        return "conflict"
    files, dirs = inspected
    if dirs != _expected_parent_dirs(files) or set(files) - set(expected):
        return "conflict"
    if any(files[name] != expected[name] for name in files):
        return "conflict"
    if not files:
        return "owned-empty"
    if set(files) == set(expected):
        return "owned-complete"
    return "owned-partial"


def _remove_validated_owned_stage(directory: Path, expected: Mapping[str, bytes]) -> bool:
    if not _is_regular_dir(directory) or not _stage_surface_ok(directory):
        return False
    marker = _load_persisted_object(directory / OWNERSHIP_NAME)
    if not _valid_ownership_shape(marker):
        return False
    payload = directory / PAYLOAD_DIRNAME
    if payload.exists() or payload.is_symlink():
        inspected = _inspect_tree(payload)
        if inspected is None:
            return False
        files, dirs = inspected
        if set(files) - set(expected) or dirs != _expected_parent_dirs(files):
            return False
        if any(files[name] != expected[name] for name in files):
            return False
        for rel in list(files):
            path = payload / rel
            if not _is_regular_file(path):
                return False
            path.unlink()
        for dirpath, dirnames, filenames in os.walk(payload, topdown=False, followlinks=False):
            root = Path(dirpath)
            if not filenames and not dirnames and root != payload and _is_regular_dir(root):
                try:
                    root.rmdir()
                except OSError:
                    return False
        try:
            payload.rmdir()
        except OSError:
            return False
    marker_path = directory / OWNERSHIP_NAME
    if _is_regular_file(marker_path):
        marker_path.unlink()
    try:
        directory.rmdir()
    except OSError:
        return False
    return True


def _cleanup_empty_staging(staged: Path, expected: Mapping[str, bytes] | None = None) -> None:
    if not _is_regular_dir(staged) or not _stage_surface_ok(staged):
        return
    marker = _load_persisted_object(staged / OWNERSHIP_NAME)
    if not _valid_ownership_shape(marker):
        return
    payload = staged / PAYLOAD_DIRNAME
    if payload.exists() or payload.is_symlink():
        inspected = _inspect_tree(payload)
        if inspected is None:
            return
        files, dirs = inspected
        if files or dirs:
            if expected is None or not _complete_set_match(payload, expected):
                return
            return
        try:
            payload.rmdir()
        except OSError:
            return
    marker_path = staged / OWNERSHIP_NAME
    if _is_regular_file(marker_path):
        try:
            marker_path.unlink()
        except OSError:
            return
    try:
        staged.rmdir()
    except OSError:
        return


def _reconcile_prefix_staging(
    workspace: Path,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
    expected: Mapping[str, bytes],
    destination_ready: bool = False,
) -> Path | None:
    complete: Path | None = None
    for staged in _prefix_staging_dirs(workspace, kind=kind, target_id=target_id):
        status = _classify_owned_stage(
            staged,
            kind=kind,
            target_id=target_id,
            intended_relative_target=intended_relative_target,
            allowed_payload_set=allowed_payload_set,
            expected=expected,
        )
        if status == "conflict":
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging contains unknown or edited bytes")
        if status == "owned-complete":
            if complete is not None:
                _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging contains duplicate complete payloads")
            complete = staged
            continue
        if not _remove_validated_owned_stage(staged, expected):
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging contains unknown or edited bytes")
    if complete is not None and destination_ready:
        if not _remove_validated_owned_stage(complete, expected):
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging contains unknown or edited bytes")
        return None
    return complete


def _create_staging(
    workspace: Path,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
) -> Path:
    root = _staging_root(workspace)
    _ensure_regular_dir(root, stop_at=workspace)
    token = secrets.token_hex(8)
    staged = root / f"{kind}-{target_id}-{token}"
    if staged.exists() or staged.is_symlink():
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging path already exists", {"path": str(staged)})
    staged.mkdir()
    if staged.is_symlink() or not staged.is_dir():
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging path must be a regular directory")
    ownership = _ownership_payload(
        kind=kind,
        target_id=target_id,
        intended_relative_target=intended_relative_target,
        allowed_payload_set=allowed_payload_set,
    )
    _write_bytes(staged / OWNERSHIP_NAME, persisted_bytes(ownership))
    payload = staged / PAYLOAD_DIRNAME
    payload.mkdir()
    return staged


def _write_payload_tree(payload: Path, files: Mapping[str, bytes]) -> None:
    for relative, data in files.items():
        if Path(relative).is_absolute() or "\\" in relative or ".." in Path(relative).parts:
            _raise(LIGHT_WRITING_PROJECT_INVALID, "payload path is unsafe")
        target = payload / relative
        _ensure_regular_dir(target.parent, stop_at=payload)
        _write_bytes(target, data)


def _publish_directory(payload: Path, destination: Path) -> None:
    if destination.is_symlink() or _symlink_in_chain(destination):
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "publication destination must not be a symlink")
    if destination.exists() or os.path.lexists(destination):
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "publication destination already exists", {"path": str(destination)})
    exclusive_rename(payload, destination)
    if not _is_regular_dir(destination):
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "publication destination is unsafe")


def _is_finite_number(value: object) -> bool:
    if type(value) is bool or type(value) not in (int, float):
        return False
    try:
        return bool(math.isfinite(value))
    except (OverflowError, ValueError, TypeError):
        return False


def _guard_evidence_scores(evidence: object, *, stored: bool) -> None:
    if type(evidence) is not list:
        return
    for item in evidence:
        if type(item) is not dict or "score" not in item:
            continue
        if not _is_finite_number(item.get("score")):
            status = LIGHT_WRITING_PROJECT_CONFLICT if stored else LIGHT_CONTEXT_INVALID
            _raise(status, "evidence score must be a finite number")


def _copy_checked_evidence(evidence: object, *, stored: bool) -> list[dict[str, Any]]:
    _guard_evidence_scores(evidence, stored=stored)
    try:
        return copy_evidence(evidence)
    except OverflowError as exc:
        status = LIGHT_WRITING_PROJECT_CONFLICT if stored else LIGHT_CONTEXT_INVALID
        _raise(status, "evidence score must be a finite number")
        raise AssertionError("unreachable") from exc
    except ResearchError as exc:
        if stored:
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, exc.message)
        _raise(LIGHT_CONTEXT_INVALID, exc.message)
        raise AssertionError("unreachable") from exc


def _validate_writing_context(workspace: Path, context: object) -> dict[str, Any]:
    if type(context) is not dict:
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "writing context must be an object")
    try:
        _guard_evidence_scores(context.get("evidence"), stored=False)
        live = validate_live_context(workspace, context)
    except OverflowError:
        return _closed(LIGHT_CONTEXT_INVALID, "evidence score must be a finite number")
    except ResearchError as exc:
        if exc.code in LIVE_STATUSES:
            return _catch(exc)
        return _closed(LIGHT_CONTEXT_INVALID, exc.message)
    if live.get("ok") is not True:
        return _live_closed(live)
    if context.get("kind") != "writing":
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "outline input must be a successful kind=writing context")
    try:
        _copy_checked_evidence(context.get("evidence"), stored=False)
    except ResearchError as exc:
        if exc.code in LIVE_STATUSES:
            return _catch(exc)
        return _closed(LIGHT_CONTEXT_INVALID, exc.message)
    return {"ok": True, "status": OK, "message": live.get("message") or "context matches the current source"}


def _validate_historical_writing_context(context: object) -> dict[str, Any]:
    payload = _require_dict(context, "stored writing context")
    if payload.get("schema") != CONTEXT_SCHEMA:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing context schema is invalid")
    if payload.get("kind") != "writing":
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing context kind is invalid")
    if payload.get("ok") is not True or payload.get("status") != OK:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing context is not a successful export")
    if type(payload.get("query")) is not str or type(payload.get("requirements")) is not str:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing context query or requirements are malformed")
    if type(payload.get("index_id")) is not str or not payload.get("index_id"):
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing context index_id is malformed")
    if type(payload.get("prompt")) is not str:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing context prompt is malformed")
    paper_ids = payload.get("paper_ids")
    if type(paper_ids) is not list or any(type(item) is not str for item in paper_ids):
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing context paper_ids are malformed")
    try:
        evidence = _copy_checked_evidence(payload.get("evidence"), stored=True)
    except OverflowError as exc:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "evidence score must be a finite number")
        raise AssertionError("unreachable") from exc
    if not evidence:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing context must contain evidence")
    return payload


def _pending_head_body(project_id: str, revision_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "revision_id": revision_id,
        "schema": PENDING_HEAD_SCHEMA,
    }


def _pending_head_expected(project_id: str, revision_id: str) -> dict[str, bytes]:
    return {INTENT_NAME: persisted_bytes(_pending_head_body(project_id, revision_id))}


def _pending_head_target_id(project_id: str, revision_id: str) -> str:
    return sha256_canonical(_pending_head_body(project_id, revision_id))


def _pending_head_args(project_id: str, revision_id: str) -> dict[str, Any]:
    return {
        "kind": PENDING_HEAD_KIND,
        "target_id": _pending_head_target_id(project_id, revision_id),
        "intended_relative_target": f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{project_id}/{HEAD_NAME}",
        "allowed_payload_set": [INTENT_NAME],
        "expected": _pending_head_expected(project_id, revision_id),
    }


def _ensure_pending_head_intent(workspace: Path, project_id: str, revision_id: str) -> None:
    args = _pending_head_args(project_id, revision_id)
    complete = _reconcile_prefix_staging(workspace, destination_ready=False, **args)
    if complete is None:
        staged = _create_staging(
            workspace,
            kind=str(args["kind"]),
            target_id=str(args["target_id"]),
            intended_relative_target=str(args["intended_relative_target"]),
            allowed_payload_set=list(args["allowed_payload_set"]),
        )
        _write_payload_tree(staged / PAYLOAD_DIRNAME, args["expected"])
        complete = staged
    status = _classify_owned_stage(
        complete,
        kind=PENDING_HEAD_KIND,
        target_id=str(args["target_id"]),
        intended_relative_target=str(args["intended_relative_target"]),
        allowed_payload_set=list(args["allowed_payload_set"]),
        expected=args["expected"],
    )
    if status != "owned-complete":
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing publication intent is incomplete")


def _has_pending_head_intent(workspace: Path, project_id: str, revision_id: str) -> bool:
    args = _pending_head_args(project_id, revision_id)
    for staged in _prefix_staging_dirs(workspace, kind=PENDING_HEAD_KIND, target_id=str(args["target_id"])):
        status = _classify_owned_stage(
            staged,
            kind=PENDING_HEAD_KIND,
            target_id=str(args["target_id"]),
            intended_relative_target=str(args["intended_relative_target"]),
            allowed_payload_set=list(args["allowed_payload_set"]),
            expected=args["expected"],
        )
        if status == "owned-complete":
            return True
        if status == "conflict":
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging contains unknown or edited bytes")
    return False


def _cleanup_pending_head_intent(workspace: Path, project_id: str, revision_id: str) -> None:
    args = _pending_head_args(project_id, revision_id)
    _reconcile_prefix_staging(workspace, destination_ready=True, **args)


def _assert_staging_recognizable(workspace: Path) -> None:
    root = _staging_root(workspace)
    if not (root.exists() or os.path.lexists(root)):
        return
    if root.is_symlink() or not root.is_dir() or _symlink_in_chain(root):
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging is not a regular directory")
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, f"writing staging is unreadable: {exc}")
    for item in entries:
        if item.is_symlink() or not item.is_dir() or not _stage_surface_ok(item):
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging contains unknown or edited bytes")
        marker = _load_persisted_object(item / OWNERSHIP_NAME)
        if not _valid_ownership_shape(marker):
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing staging contains unknown or edited bytes")


def _section_model_from_state(
    row: Mapping[str, Any],
    *,
    project_id: str,
) -> dict[str, Any]:
    return {
        "citations": list(row["citations"]),
        "markdown": row["markdown"],
        "project_id": project_id,
        "schema": SECTION_DOCUMENT_SCHEMA,
        "section_id": row["section_id"],
        "status": row["status"],
    }


def _validate_stored_section_against_evidence(
    row: Mapping[str, Any],
    *,
    project_id: str,
    context: Mapping[str, Any],
) -> None:
    if row["status"] == STATUS_UNWRITTEN:
        return
    _validate_section_document(
        _section_model_from_state(row, project_id=project_id),
        project_id=project_id,
        section_id=str(row["section_id"]),
        context=context,
    )


def _validate_successor_target(
    row: Mapping[str, Any],
    *,
    project_id: str,
    context: Mapping[str, Any],
) -> None:
    _validate_section_document(
        _section_model_from_state(row, project_id=project_id),
        project_id=project_id,
        section_id=str(row["section_id"]),
        context=context,
    )


def _evidence_ids(context: Mapping[str, Any]) -> list[str]:
    return [item["chunk_id"] for item in _copy_checked_evidence(context["evidence"], stored=True)]


def _validate_outline_section(item: object, *, evidence_ids: set[str], seen_ids: set[str]) -> dict[str, Any]:
    if not _exact_keys(item, {"section_id", "title", "goal", "status", "citations"}):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline section must have exactly section_id, title, goal, status, citations")
    assert type(item) is dict
    section_id = item["section_id"]
    if type(section_id) is not str or SECTION_ID.fullmatch(section_id) is None:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section_id must match s[1-9][0-9]?")
    if section_id in seen_ids:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section_id is duplicated")
    title = _bounded_text(item["title"], name="section title", minimum=1, maximum=MAX_TITLE)
    goal = _bounded_text(item["goal"], name="section goal", minimum=1, maximum=MAX_GOAL)
    status = item["status"]
    citations = item["citations"]
    if status == STATUS_UNKNOWN:
        if goal != UNKNOWN_TEXT:
            _raise(LIGHT_WRITING_PROJECT_INVALID, "unknown outline section goal must be exactly 证据不足")
        if citations != []:
            _raise(LIGHT_WRITING_PROJECT_INVALID, "unknown outline section must have no citations")
        return {
            "citations": [],
            "goal": UNKNOWN_TEXT,
            "section_id": section_id,
            "status": STATUS_UNKNOWN,
            "title": title,
        }
    if status != STATUS_PROVISIONAL:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline section status must be provisional or unknown")
    if type(citations) is not list:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "citations must be a list of chunk_id strings")
    if type(len(citations)) is bool or not (1 <= len(citations) <= MAX_CITATIONS):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "provisional outline section must cite 1-32 unique evidence ids")
    unique: list[str] = []
    seen_cite: set[str] = set()
    for cite in citations:
        if type(cite) is not str or not cite:
            _raise(LIGHT_WRITING_PROJECT_INVALID, "citation chunk_id must be a nonempty string")
        if cite in seen_cite:
            _raise(LIGHT_WRITING_PROJECT_INVALID, "outline section citations must be unique")
        if cite not in evidence_ids:
            _raise(LIGHT_WRITING_PROJECT_INVALID, "outline citation is not in the current writing evidence")
        seen_cite.add(cite)
        unique.append(cite)
    return {
        "citations": unique,
        "goal": goal,
        "section_id": section_id,
        "status": STATUS_PROVISIONAL,
        "title": title,
    }


def _validate_outline_document(document: object, *, evidence_ids: set[str]) -> dict[str, Any]:
    payload = _require_dict(document, "outline document")
    if not _exact_keys(payload, {"schema", "title", "sections"}):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline document must have exactly schema, title, sections")
    if payload.get("schema") != OUTLINE_DOCUMENT_SCHEMA:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline document schema is invalid")
    title = _bounded_text(payload["title"], name="title", minimum=1, maximum=MAX_TITLE)
    sections = payload["sections"]
    if type(sections) is not list:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline sections must be a list")
    if type(len(sections)) is bool or not (1 <= len(sections) <= MAX_OUTLINE_SECTIONS):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline must contain 1-16 sections")
    seen: set[str] = set()
    checked: list[dict[str, Any]] = []
    provisional = 0
    for item in sections:
        row = _validate_outline_section(item, evidence_ids=evidence_ids, seen_ids=seen)
        seen.add(row["section_id"])
        if row["status"] == STATUS_PROVISIONAL:
            provisional += 1
        checked.append(row)
    if provisional < 1:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "at least one outline section must be provisional")
    outline = {"schema": OUTLINE_DOCUMENT_SCHEMA, "sections": checked, "title": title}
    if _canonical_len(outline) > MAX_OUTLINE_DOCUMENT_CHARS:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline document exceeds the 32,000-character canonical cap")
    return outline


def _initial_sections(outline: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"citations": [], "markdown": "", "section_id": item["section_id"], "status": STATUS_UNWRITTEN}
        for item in outline["sections"]
    ]


def _section_state(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "citations": list(item["citations"]),
        "markdown": item["markdown"],
        "section_id": item["section_id"],
        "status": item["status"],
    }


def _validate_section_states(rows: object, *, outline: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_ids = [item["section_id"] for item in outline["sections"]]
    if type(rows) is not list or len(rows) != len(expected_ids):
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, "revision sections do not match the original outline order")
    checked: list[dict[str, Any]] = []
    for item, expected in zip(rows, expected_ids):
        if not _exact_keys(item, SECTION_STATE_KEYS):
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "revision section state keys are invalid")
        assert type(item) is dict
        if item.get("section_id") != expected:
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "revision section order does not match the outline")
        status = item.get("status")
        markdown = item.get("markdown")
        citations = item.get("citations")
        if type(markdown) is not str or type(citations) is not list:
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "revision section values are malformed")
        if status == STATUS_UNWRITTEN:
            if markdown != "" or citations != []:
                _raise(LIGHT_WRITING_PROJECT_CONFLICT, "unwritten section must have empty markdown and citations")
        elif status == STATUS_UNKNOWN:
            if markdown != UNKNOWN_TEXT or citations != []:
                _raise(LIGHT_WRITING_PROJECT_CONFLICT, "unknown section must use 证据不足 and no citations")
        elif status == STATUS_PROVISIONAL:
            if markdown.strip() == "" or _unsafe_body_text(markdown) or len(markdown) > MAX_SECTION_MARKDOWN:
                _raise(LIGHT_WRITING_PROJECT_CONFLICT, "provisional section markdown is invalid")
            if any(type(cite) is not str or not cite for cite in citations):
                _raise(LIGHT_WRITING_PROJECT_CONFLICT, "section citations must be chunk_id strings")
        else:
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "revision section status is invalid")
        checked.append(_section_state(item))
    return checked


def _revision_document(
    *,
    project_id: str,
    parent_revision_id: str | None,
    kind: str,
    target_section_id: str | None,
    instructions: str,
    outline: Mapping[str, Any],
    sections: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "instructions": instructions,
        "kind": kind,
        "outline": {
            "schema": outline["schema"],
            "sections": [dict(item) for item in outline["sections"]],
            "title": outline["title"],
        },
        "parent_revision_id": parent_revision_id,
        "project_id": project_id,
        "schema": REVISION_SCHEMA,
        "sections": [_section_state(item) for item in sections],
        "target_section_id": target_section_id,
        "title": outline["title"],
    }


def _revision_identity(
    *,
    project_id: str,
    parent_revision_id: str | None,
    context_sha256: str,
    document: Mapping[str, Any],
) -> str:
    return sha256_canonical(
        {
            "context_sha256": context_sha256,
            "document": document,
            "parent_revision_id": parent_revision_id,
            "project_id": project_id,
            "schema": REVISION_IDENTITY_SCHEMA,
        }
    )


def _project_id_for(context: Mapping[str, Any], outline: Mapping[str, Any]) -> str:
    return sha256_canonical({"context": context, "outline": outline, "schema": PROJECT_SCHEMA})


def _render_project_markdown(
    *,
    workspace: Path,
    output: Path,
    title: str,
    sections: list[Mapping[str, Any]],
    outline: Mapping[str, Any],
    context: Mapping[str, Any],
) -> str:
    by_id = {item["section_id"]: item for item in sections}
    evidence = {row["chunk_id"]: row for row in _copy_checked_evidence(context["evidence"], stored=True)}
    lines = [f"# {_escape_md(title)}", "", PROVISIONAL_LABEL, ""]
    cited: list[str] = []
    seen: set[str] = set()
    for outline_section in outline["sections"]:
        section = by_id[outline_section["section_id"]]
        lines.append(f"## {_escape_md(str(outline_section['title']))}")
        lines.append("")
        status = section["status"]
        if status == STATUS_UNWRITTEN:
            lines.append(UNWRITTEN_TEXT)
        elif status == STATUS_UNKNOWN:
            lines.append(UNKNOWN_TEXT)
        else:
            body = str(section["markdown"])

            def replace(match: re.Match[str], *, _evidence: dict[str, dict[str, Any]] = evidence) -> str:
                chunk_id = match.group(1)
                item = _evidence.get(chunk_id)
                if item is None:
                    return match.group(0)
                if chunk_id not in seen:
                    seen.add(chunk_id)
                    cited.append(chunk_id)
                return _readable_mark(item)

            lines.append(_CITE_MARK.sub(replace, body).rstrip())
        lines.append("")
    if cited:
        lines.append("## 参考文献")
        lines.append("")
        for index, chunk_id in enumerate(cited, start=1):
            item = evidence[chunk_id]
            label = item["title"] or item["paper_id"]
            lines.append(f"{index}. {label} — PDF 第 {item['page']} 页 — `{item['markdown_path']}#{_anchor(item)}`")
            quote = item["text"].replace("\n", " ").strip()
            if quote:
                lines.append(f"   > {quote}")
        lines.append("")
    markdown = "\n".join(lines).rstrip() + "\n"
    return rewrite_markdown_links(markdown, workspace=workspace, output=output)


def _revision_files(
    *,
    workspace: Path,
    project_id: str,
    revision_id: str,
    parent_revision_id: str | None,
    context: Mapping[str, Any],
    document: Mapping[str, Any],
) -> dict[str, bytes]:
    context_bytes = persisted_bytes(context)
    document_bytes = persisted_bytes(document)
    output = workspace / _page_path(project_id, revision_id)
    draft = _render_project_markdown(
        workspace=workspace,
        output=output,
        title=str(document["title"]),
        sections=list(document["sections"]),
        outline=document["outline"],
        context=context,
    )
    if not draft.endswith("\n") or draft.endswith("\n\n"):
        draft = draft.rstrip("\n") + "\n"
    draft_bytes = draft.encode("utf-8")
    files = {
        CONTEXT_NAME: context_bytes,
        DOCUMENT_NAME: document_bytes,
        DRAFT_NAME: draft_bytes,
    }
    manifest = {
        "context_sha256": sha256_canonical(context),
        "document_sha256": sha256_canonical(document),
        "files": _sorted_file_rows([_file_row(name, files[name]) for name in REVISION_FILE_NAMES]),
        "parent_revision_id": parent_revision_id,
        "project_id": project_id,
        "revision_id": revision_id,
        "schema": MANIFEST_SCHEMA,
    }
    files[MANIFEST_NAME] = persisted_bytes(manifest)
    return files


def _validate_manifest(manifest: Mapping[str, Any], files: Mapping[str, bytes], *, project_id: str, revision_id: str, parent_revision_id: str | None, context: Mapping[str, Any], document: Mapping[str, Any]) -> bool:
    if not _exact_keys(manifest, {"schema", "project_id", "revision_id", "parent_revision_id", "context_sha256", "document_sha256", "files"}):
        return False
    if manifest.get("schema") != MANIFEST_SCHEMA:
        return False
    if manifest.get("project_id") != project_id or manifest.get("revision_id") != revision_id:
        return False
    if manifest.get("parent_revision_id") != parent_revision_id:
        return False
    if manifest.get("context_sha256") != sha256_canonical(context):
        return False
    if manifest.get("document_sha256") != sha256_canonical(document):
        return False
    rows = manifest.get("files")
    expected_rows = _sorted_file_rows([_file_row(name, files[name]) for name in REVISION_FILE_NAMES])
    return type(rows) is list and canonical_bytes(rows) == canonical_bytes(expected_rows)


def _load_revision_bundle(workspace: Path, project_id: str, revision_id: str) -> dict[str, Any] | None:
    directory = _revision_dir(workspace, project_id, revision_id)
    if not _is_regular_dir(directory):
        return None
    inspected = _inspect_tree(directory)
    if inspected is None:
        return None
    files, dirs = inspected
    if dirs or set(files) != set(REVISION_DIR_NAMES):
        return None
    try:
        context = json_object(files[CONTEXT_NAME])
        document = json_object(files[DOCUMENT_NAME])
        manifest = json_object(files[MANIFEST_NAME])
    except (UnicodeError, ValueError, TypeError):
        return None
    if type(context) is not dict or type(document) is not dict or type(manifest) is not dict:
        return None
    try:
        if files[CONTEXT_NAME] != persisted_bytes(context) or files[DOCUMENT_NAME] != persisted_bytes(document):
            return None
        if files[MANIFEST_NAME] != persisted_bytes(manifest):
            return None
    except (TypeError, ValueError, OverflowError, ResearchError):
        return None
    if not _exact_keys(document, REVISION_DOC_KEYS) or document.get("schema") != REVISION_SCHEMA:
        return None
    if document.get("project_id") != project_id:
        return None
    parent = document.get("parent_revision_id")
    if parent is not None and not _is_hex64(parent):
        return None
    kind = document.get("kind")
    if type(kind) is not str or kind not in {KIND_OUTLINE, KIND_SECTION}:
        return None
    if kind == KIND_OUTLINE:
        if parent is not None or document.get("target_section_id") is not None or document.get("instructions") != "":
            return None
    else:
        if not _is_hex64(parent) or type(document.get("target_section_id")) is not str:
            return None
        if type(document.get("instructions")) is not str:
            return None
    outline = document.get("outline")
    if type(outline) is not dict or outline.get("title") != document.get("title"):
        return None
    try:
        historical = _validate_historical_writing_context(context)
        evidence_ids = set(_evidence_ids(historical))
        checked_outline = _validate_outline_document(outline, evidence_ids=evidence_ids)
        if _project_id_for(historical, checked_outline) != project_id:
            return None
        if canonical_bytes(checked_outline) != canonical_bytes(
            {"schema": outline.get("schema"), "sections": outline.get("sections"), "title": outline.get("title")}
        ):
            return None
        sections = _validate_section_states(document.get("sections"), outline=checked_outline)
        for row in sections:
            _validate_stored_section_against_evidence(row, project_id=project_id, context=historical)
        if kind == KIND_SECTION:
            target_id = document.get("target_section_id")
            target_state = next((row for row in sections if row["section_id"] == target_id), None)
            if target_state is None:
                return None
            _validate_successor_target(target_state, project_id=project_id, context=historical)
        if type(document.get("instructions")) is str:
            _normalize_instructions(document["instructions"])
        expected_files = _revision_files(
            workspace=workspace,
            project_id=project_id,
            revision_id=revision_id,
            parent_revision_id=parent,
            context=historical,
            document=document,
        )
    except (ResearchError, KeyError, TypeError, OverflowError, UnicodeError, ValueError):
        return None
    if any(files.get(name) != expected_files.get(name) for name in REVISION_DIR_NAMES):
        return None
    if not _validate_manifest(
        manifest,
        files,
        project_id=project_id,
        revision_id=revision_id,
        parent_revision_id=parent,
        context=context,
        document=document,
    ):
        return None
    try:
        identity = _revision_identity(
            project_id=project_id,
            parent_revision_id=parent,
            context_sha256=sha256_canonical(context),
            document=document,
        )
    except (ResearchError, KeyError, TypeError, OverflowError, UnicodeError, ValueError):
        return None
    if identity != revision_id:
        return None
    return {
        "context": context,
        "directory": directory,
        "document": document,
        "files": files,
        "outline": checked_outline,
        "parent_revision_id": parent,
        "sections": sections,
    }


def _load_head(workspace: Path, project_id: str) -> dict[str, Any] | None:
    path = _head_path(workspace, project_id)
    if not (path.exists() or os.path.lexists(path)):
        return None
    payload = _load_persisted_object(path)
    if payload is None or not _exact_keys(payload, {"schema", "project_id", "revision_id"}):
        return {"ok": False, "status": LIGHT_WRITING_PROJECT_CONFLICT, "message": "HEAD.json is not a validated pointer"}
    if payload.get("schema") != HEAD_SCHEMA or payload.get("project_id") != project_id or not _is_hex64(payload.get("revision_id")):
        return {"ok": False, "status": LIGHT_WRITING_PROJECT_CONFLICT, "message": "HEAD.json is not a validated pointer"}
    return {"ok": True, "revision_id": payload["revision_id"], "payload": payload}


def _walk_ancestry(workspace: Path, project_id: str, head_revision_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = head_revision_id
    while current is not None:
        if current in seen:
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing revision ancestry contains a cycle")
        if len(chain) > MAX_SECTION_REVISIONS:
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing revision ancestry exceeds 128 section revisions")
        if not _is_hex64(current):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision_id must be 64 lowercase hex")
        bundle = _load_revision_bundle(workspace, project_id, current)
        if bundle is None:
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision bundle is missing, edited, or incomplete")
        seen.add(current)
        chain.append({"bundle": bundle, "revision_id": current})
        parent = bundle["parent_revision_id"]
        if parent is None:
            if bundle["document"]["kind"] != KIND_OUTLINE:
                return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision ancestry root is not a valid outline")
            break
        if bundle["document"]["kind"] != KIND_SECTION:
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "non-root revision must be a section revision")
        current = parent
    else:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision ancestry is missing an outline root")
    outline_id = chain[-1]["revision_id"]
    outline_doc = chain[-1]["bundle"]["document"]
    if outline_doc["kind"] != KIND_OUTLINE:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision ancestry root is not a valid outline")
    for item in chain:
        document = item["bundle"]["document"]
        if canonical_bytes(document["outline"]) != canonical_bytes(outline_doc["outline"]):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision outline does not match the original outline")
        if document["title"] != outline_doc["title"]:
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision title does not match the original outline")
        if canonical_bytes(item["bundle"]["context"]) != canonical_bytes(chain[-1]["bundle"]["context"]):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision context does not match the original writing context")
        if item["revision_id"] != outline_id and item["bundle"]["parent_revision_id"] not in seen:
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision parent is foreign to this project")
    ordered = list(reversed(chain))
    replayed = _replay_parent_transitions(workspace, project_id, ordered)
    if replayed is not None:
        return replayed
    return ordered


def _replay_parent_transitions(
    workspace: Path,
    project_id: str,
    chain: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        root = chain[0]
        context = root["bundle"]["context"]
        outline = root["bundle"]["outline"]
        root_doc = root["bundle"]["document"]
        if root_doc["kind"] != KIND_OUTLINE:
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision ancestry root is not a valid outline")
        if (
            root_doc["parent_revision_id"] is not None
            or root_doc["target_section_id"] is not None
            or root_doc["instructions"] != ""
        ):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "outline revision fields are invalid")
        expected_initial = _initial_sections(outline)
        if canonical_bytes(root["bundle"]["sections"]) != canonical_bytes(expected_initial):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "outline revision sections are not the initial unwritten state")
        expected_root = _revision_document(
            project_id=project_id,
            parent_revision_id=None,
            kind=KIND_OUTLINE,
            target_section_id=None,
            instructions="",
            outline=outline,
            sections=expected_initial,
        )
        if canonical_bytes(root_doc) != canonical_bytes(expected_root):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "outline revision document does not replay")
        prev_sections = root["bundle"]["sections"]
        prev_id = root["revision_id"]
        for item in chain[1:]:
            document = item["bundle"]["document"]
            if document["kind"] != KIND_SECTION or document["parent_revision_id"] != prev_id:
                return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "section revision parent is skipped or foreign")
            target = document["target_section_id"]
            instructions = _normalize_instructions(document["instructions"])
            child_sections = item["bundle"]["sections"]
            if len(child_sections) != len(prev_sections):
                return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision sections do not match the original outline order")
            target_state = None
            for current, previous in zip(child_sections, prev_sections):
                if current["section_id"] != previous["section_id"]:
                    return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision section order does not match the outline")
                if current["section_id"] == target:
                    target_state = current
                elif canonical_bytes(current) != canonical_bytes(previous):
                    return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "only the named target section may change")
            if target_state is None:
                return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "target section_id is not in the outline")
            _validate_successor_target(target_state, project_id=project_id, context=context)
            expected_sections = _replace_section(prev_sections, target_state)
            if canonical_bytes(expected_sections) != canonical_bytes(child_sections):
                return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "section revision does not replay from its parent")
            expected_document = _revision_document(
                project_id=project_id,
                parent_revision_id=prev_id,
                kind=KIND_SECTION,
                target_section_id=target,
                instructions=instructions,
                outline=outline,
                sections=expected_sections,
            )
            if canonical_bytes(document) != canonical_bytes(expected_document):
                return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "section revision document does not replay")
            expected_id = _revision_identity(
                project_id=project_id,
                parent_revision_id=prev_id,
                context_sha256=sha256_canonical(context),
                document=expected_document,
            )
            if expected_id != item["revision_id"]:
                return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision identity does not replay")
            expected_files = _revision_files(
                workspace=workspace,
                project_id=project_id,
                revision_id=item["revision_id"],
                parent_revision_id=prev_id,
                context=context,
                document=expected_document,
            )
            if any(item["bundle"]["files"].get(name) != expected_files.get(name) for name in REVISION_DIR_NAMES):
                return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revision bytes are not deterministic from context and document")
            prev_sections = child_sections
            prev_id = item["revision_id"]
    except (ResearchError, KeyError, TypeError, OverflowError, UnicodeError, ValueError):
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "stored writing revision chain is malformed")
    return None


def _list_revision_ids(workspace: Path, project_id: str) -> list[str] | dict[str, Any]:
    root = _revisions_root(workspace, project_id)
    if not (root.exists() or os.path.lexists(root)):
        return []
    if not _is_regular_dir(root):
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revisions directory is unsafe")
    names: list[str] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revisions directory is unreadable")
    for item in entries:
        if item.is_symlink() or not item.is_dir() or not _is_hex64(item.name):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "revisions directory contains an unknown or edited entry")
        names.append(item.name)
    return sorted(names)


def _source_status(workspace: Path, context: Mapping[str, Any]) -> str:
    evidence = context.get("evidence")
    missing = False
    if type(evidence) is list:
        for row in evidence:
            if type(row) is not dict or type(row.get("markdown_path")) is not str:
                continue
            path = workspace / row["markdown_path"]
            if not path.exists() and not os.path.lexists(path):
                missing = True
                break
    try:
        live = validate_live_context(workspace, context)
    except OverflowError:
        return "conflict"
    except (KeyError, TypeError, UnicodeError, ValueError):
        return "conflict"
    if live.get("ok") is True:
        return "current"
    status = live.get("status")
    if status == LIGHT_WORKSPACE_MISMATCH:
        return "historical"
    if missing or status == SOURCE_INVALID:
        return "missing-source"
    if status in {INDEX_STALE, LIGHT_CONTEXT_INVALID, LIGHT_SELECTION_INVALID}:
        return "stale"
    return "conflict"


def _publish_revision(workspace: Path, project_id: str, revision_id: str, files: Mapping[str, bytes]) -> bool:
    try:
        dest = _revision_dir(workspace, project_id, revision_id)
        _ensure_regular_dir(_revisions_root(workspace, project_id), stop_at=workspace)
        dest_ready = False
        if dest.exists() or dest.is_symlink():
            if dest.is_symlink() or not dest.is_dir():
                _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing revision destination is unsafe")
            if not _complete_set_match(dest, files):
                _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing revision already exists with different bytes")
            dest_ready = True
        intended = f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{project_id}/{REVISIONS_DIRNAME}/{revision_id}"
        allowed = list(REVISION_DIR_NAMES)
        complete = _reconcile_prefix_staging(
            workspace,
            kind="revision",
            target_id=revision_id,
            intended_relative_target=intended,
            allowed_payload_set=allowed,
            expected=files,
            destination_ready=dest_ready,
        )
        if dest_ready:
            return True
        if complete is not None:
            _publish_directory(complete / PAYLOAD_DIRNAME, dest)
            _cleanup_empty_staging(complete, files)
            return False
        staged = _create_staging(
            workspace,
            kind="revision",
            target_id=revision_id,
            intended_relative_target=intended,
            allowed_payload_set=allowed,
        )
        try:
            _write_payload_tree(staged / PAYLOAD_DIRNAME, files)
            _publish_directory(staged / PAYLOAD_DIRNAME, dest)
        finally:
            _cleanup_empty_staging(staged, files)
        return False
    except OSError as exc:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, f"cannot publish writing revision: {exc}")
        raise AssertionError("unreachable") from exc


def _publish_head(workspace: Path, project_id: str, revision_id: str, *, expected: str | None) -> None:
    try:
        payload = {"project_id": project_id, "revision_id": revision_id, "schema": HEAD_SCHEMA}
        encoded = persisted_bytes(payload)
        destination = _head_path(workspace, project_id)
        expected_files = {HEAD_NAME: encoded}
        allowed = [HEAD_NAME]
        intended = f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{project_id}/{HEAD_NAME}"
        already = False
        if destination.exists() or destination.is_symlink():
            if not _is_regular_file(destination) or _hardlinked(destination):
                _raise(LIGHT_WRITING_PROJECT_CONFLICT, "HEAD.json is not a safe regular file")
            current = destination.read_bytes()
            if current == encoded:
                already = True
            else:
                existing = _load_persisted_object(destination)
                if existing is None or existing.get("schema") != HEAD_SCHEMA or existing.get("project_id") != project_id:
                    _raise(LIGHT_WRITING_PROJECT_CONFLICT, "existing HEAD.json is not a validated pointer")
                current_id = existing.get("revision_id")
                if expected is None or current_id != expected:
                    _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD is not the expected parent revision")
        elif expected is not None:
            _raise(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD is not the expected parent revision")
        complete = _reconcile_prefix_staging(
            workspace,
            kind="head",
            target_id=sha256_canonical(payload),
            intended_relative_target=intended,
            allowed_payload_set=allowed,
            expected=expected_files,
            destination_ready=already,
        )
        if already:
            return
        _ensure_regular_dir(destination.parent, stop_at=workspace)
        if complete is not None:
            tmp = complete / PAYLOAD_DIRNAME / HEAD_NAME
            os.replace(tmp, destination)
            _cleanup_empty_staging(complete, expected_files)
            return
        staged = _create_staging(
            workspace,
            kind="head",
            target_id=sha256_canonical(payload),
            intended_relative_target=intended,
            allowed_payload_set=allowed,
        )
        try:
            _write_bytes(staged / PAYLOAD_DIRNAME / HEAD_NAME, encoded)
            os.replace(staged / PAYLOAD_DIRNAME / HEAD_NAME, destination)
        finally:
            _cleanup_empty_staging(staged, expected_files)
    except OSError as exc:
        _raise(LIGHT_WRITING_PROJECT_CONFLICT, f"cannot publish writing HEAD: {exc}")


def _outline_wrapper(*, context: Mapping[str, Any]) -> dict[str, Any]:
    wrapper = {
        "context": context,
        "context_sha256": sha256_canonical(context),
        "message": OUTLINE_MESSAGE,
        "ok": True,
        "prompt": OUTLINE_PROMPT,
        "schema": OUTLINE_CONTEXT_SCHEMA,
        "status": OK,
    }
    if _canonical_len(wrapper) > MAX_WRAPPER_CHARS:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline export exceeds the 80,000-character canonical cap")
    return {key: wrapper[key] for key in OUTLINE_EXPORT_KEYS}


def _section_wrapper(
    *,
    project_id: str,
    parent_revision_id: str,
    section_id: str,
    context: Mapping[str, Any],
    outline: Mapping[str, Any],
    previous_section: Mapping[str, Any],
    instructions: str,
) -> dict[str, Any]:
    wrapper = {
        "context": context,
        "context_sha256": sha256_canonical(context),
        "instructions": instructions,
        "message": SECTION_MESSAGE,
        "ok": True,
        "outline": {
            "schema": outline["schema"],
            "sections": [dict(item) for item in outline["sections"]],
            "title": outline["title"],
        },
        "parent_revision_id": parent_revision_id,
        "previous_section": _section_state(previous_section),
        "project_id": project_id,
        "prompt": SECTION_PROMPT,
        "schema": SECTION_CONTEXT_SCHEMA,
        "section_id": section_id,
        "status": OK,
    }
    wrapper["wrapper_sha256"] = sha256_canonical({key: wrapper[key] for key in wrapper})
    if _canonical_len(wrapper) > MAX_WRAPPER_CHARS:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section export exceeds the 80,000-character canonical cap")
    return {key: wrapper[key] for key in SECTION_EXPORT_KEYS}


def _export_outline_unlocked(workspace: Path, context: object) -> dict[str, Any]:
    live = _validate_writing_context(workspace, context)
    if live.get("ok") is not True:
        return live
    assert type(context) is dict
    try:
        return _outline_wrapper(context=context)
    except ResearchError as exc:
        return _catch(exc)


def _require_outline_wrapper(wrapper: object) -> dict[str, Any]:
    payload = _require_dict(wrapper, "outline context")
    if not _exact_keys(payload, OUTLINE_EXPORT_KEYS):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline export wrapper keys are invalid")
    if payload.get("ok") is not True or payload.get("status") != OK:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "failed outline exports are not usable imports")
    if payload.get("schema") != OUTLINE_CONTEXT_SCHEMA:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline export schema is invalid")
    if payload.get("message") != OUTLINE_MESSAGE or payload.get("prompt") != OUTLINE_PROMPT:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline export constants are invalid")
    context = payload.get("context")
    if type(context) is not dict:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline wrapper context must be an object")
    if payload.get("context_sha256") != sha256_canonical(context):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "outline context_sha256 does not match the inner context")
    return payload


def _require_section_wrapper(wrapper: object) -> dict[str, Any]:
    payload = _require_dict(wrapper, "section context")
    if not _exact_keys(payload, SECTION_EXPORT_KEYS):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section export wrapper keys are invalid")
    if payload.get("ok") is not True or payload.get("status") != OK:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "failed section exports are not usable imports")
    if payload.get("schema") != SECTION_CONTEXT_SCHEMA:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section export schema is invalid")
    if payload.get("message") != SECTION_MESSAGE or payload.get("prompt") != SECTION_PROMPT:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section export constants are invalid")
    project_id = _require_hex64(payload.get("project_id"), "project_id")
    parent = _require_hex64(payload.get("parent_revision_id"), "parent_revision_id")
    section_id = payload.get("section_id")
    if type(section_id) is not str or SECTION_ID.fullmatch(section_id) is None:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section_id must match s[1-9][0-9]?")
    context = payload.get("context")
    if type(context) is not dict:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section wrapper context must be an object")
    if payload.get("context_sha256") != sha256_canonical(context):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section context_sha256 does not match the inner context")
    if type(payload.get("instructions")) is not str:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "instructions must be a string")
    if _unsafe_body_text(str(payload["instructions"])):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "instructions must not contain unsafe control characters")
    if len(str(payload["instructions"])) > MAX_INSTRUCTIONS:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "instructions exceed the 4,000-character bound")
    outline = payload.get("outline")
    previous = payload.get("previous_section")
    if type(outline) is not dict or type(previous) is not dict:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section wrapper outline and previous_section must be objects")
    expected_hash = sha256_canonical({key: payload[key] for key in SECTION_EXPORT_KEYS if key != "wrapper_sha256"})
    if payload.get("wrapper_sha256") != expected_hash:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section wrapper_sha256 does not match the wrapper fields")
    return payload


def _validate_section_document(
    document: object,
    *,
    project_id: str,
    section_id: str,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _require_dict(document, "section document")
    if not _exact_keys(payload, {"schema", "project_id", "section_id", "status", "markdown", "citations"}):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section document keys are invalid")
    if payload.get("schema") != SECTION_DOCUMENT_SCHEMA:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section document schema is invalid")
    if payload.get("project_id") != project_id:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section document project_id does not match the wrapper")
    if payload.get("section_id") != section_id:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section document section_id does not match the wrapper")
    status = payload.get("status")
    markdown = payload.get("markdown")
    citations = payload.get("citations")
    if type(markdown) is not str:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section markdown must be a string")
    if type(citations) is not list:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section citations must be a list")
    if status == STATUS_UNKNOWN:
        if markdown != UNKNOWN_TEXT or citations != []:
            _raise(LIGHT_WRITING_PROJECT_INVALID, "unknown section must use markdown 证据不足 and no citations")
        return {
            "citations": [],
            "markdown": UNKNOWN_TEXT,
            "project_id": project_id,
            "schema": SECTION_DOCUMENT_SCHEMA,
            "section_id": section_id,
            "status": STATUS_UNKNOWN,
        }
    if status != STATUS_PROVISIONAL:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section status must be provisional or unknown")
    if markdown.strip() == "" or _unsafe_body_text(markdown) or len(markdown) > MAX_SECTION_MARKDOWN:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "provisional markdown must be nonblank and at most 16,000 characters")
    if any(type(item) is not str or not item for item in citations):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "section citations must be chunk_id strings")
    unique = list(dict.fromkeys(citations))
    if len(unique) != len(citations) or not (1 <= len(unique) <= MAX_CITATIONS):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "provisional section must cite 1-32 distinct evidence ids")
    if set(body_chunk_ids(markdown)) != set(unique):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "body [@chunk_id] marks and citations list do not name the same chunks")
    checked = check_model_document(
        dict(context),
        {"citations": [{"chunk_id": item} for item in unique], "markdown": markdown},
        body_key="markdown",
    )
    if checked.get("ok") is not True:
        _raise(LIGHT_WRITING_PROJECT_INVALID, str(checked.get("message") or "section citations are invalid"))
    return {
        "citations": unique,
        "markdown": markdown,
        "project_id": project_id,
        "schema": SECTION_DOCUMENT_SCHEMA,
        "section_id": section_id,
        "status": STATUS_PROVISIONAL,
    }


def _replace_section(sections: list[Mapping[str, Any]], replacement: Mapping[str, Any]) -> list[dict[str, Any]]:
    next_rows: list[dict[str, Any]] = []
    found = False
    for item in sections:
        if item["section_id"] == replacement["section_id"]:
            next_rows.append(
                {
                    "citations": list(replacement["citations"]),
                    "markdown": replacement["markdown"],
                    "section_id": replacement["section_id"],
                    "status": replacement["status"],
                }
            )
            found = True
        else:
            next_rows.append(_section_state(item))
    if not found:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "target section_id is not in the outline")
    return next_rows


def _unexpected_revisions(workspace: Path, project_id: str, allowed: set[str]) -> dict[str, Any] | None:
    listed = _list_revision_ids(workspace, project_id)
    if type(listed) is dict:
        return listed
    extras = [item for item in listed if item not in allowed]
    if extras:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project contains an unexpected revision")
    return None


def _project_extra_names(workspace: Path, project_id: str) -> list[str]:
    directory = _project_dir(workspace, project_id)
    if not _is_regular_dir(directory):
        return []
    names = []
    for item in directory.iterdir():
        if item.name not in {HEAD_NAME, REVISIONS_DIRNAME}:
            names.append(item.name)
    return names


def _import_outline_unlocked(workspace: Path, wrapper: object, document: object) -> dict[str, Any]:
    checked = _require_outline_wrapper(wrapper)
    inner = checked["context"]
    live = _validate_writing_context(workspace, inner)
    if live.get("ok") is not True:
        return live
    fresh = _export_outline_unlocked(workspace, inner)
    if fresh.get("ok") is not True:
        return fresh
    if canonical_bytes(fresh) != canonical_bytes({key: checked[key] for key in OUTLINE_EXPORT_KEYS}):
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "outline wrapper does not match a fresh live export")
    evidence_ids = set(_evidence_ids(inner))
    outline = _validate_outline_document(document, evidence_ids=evidence_ids)
    project_id = _project_id_for(inner, outline)
    revision_document = _revision_document(
        project_id=project_id,
        parent_revision_id=None,
        kind=KIND_OUTLINE,
        target_section_id=None,
        instructions="",
        outline=outline,
        sections=_initial_sections(outline),
    )
    context_sha256 = sha256_canonical(inner)
    revision_id = _revision_identity(
        project_id=project_id,
        parent_revision_id=None,
        context_sha256=context_sha256,
        document=revision_document,
    )
    files = _revision_files(
        workspace=workspace,
        project_id=project_id,
        revision_id=revision_id,
        parent_revision_id=None,
        context=inner,
        document=revision_document,
    )
    extras = _project_extra_names(workspace, project_id)
    if extras:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project directory contains unknown entries")
    _assert_staging_recognizable(workspace)
    head = _load_head(workspace, project_id)
    if head is not None and head.get("ok") is not True:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, str(head.get("message") or "HEAD.json is not a validated pointer"))
    current_head = None if head is None else head.get("revision_id")
    if current_head not in {None, revision_id}:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD is not the expected parent revision")
    listed = _list_revision_ids(workspace, project_id)
    if type(listed) is dict:
        return listed
    unexpected = [item for item in listed if item != revision_id]
    if unexpected:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project contains an unexpected revision")
    if current_head is None and revision_id in listed and not _has_pending_head_intent(workspace, project_id, revision_id):
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD is missing or edited")
    if current_head is None:
        _ensure_pending_head_intent(workspace, project_id, revision_id)
        if not _has_pending_head_intent(workspace, project_id, revision_id):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing publication intent is incomplete")
    reused = _publish_revision(workspace, project_id, revision_id, files)
    live = _validate_writing_context(workspace, inner)
    if live.get("ok") is not True:
        return live
    head_after = _load_head(workspace, project_id)
    if head_after is not None and head_after.get("ok") is not True:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, str(head_after.get("message") or "HEAD.json is not a validated pointer"))
    after_id = None if head_after is None else head_after.get("revision_id")
    if after_id not in {None, revision_id}:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD changed before pointer publication")
    _publish_head(workspace, project_id, revision_id, expected=after_id)
    _cleanup_pending_head_intent(workspace, project_id, revision_id)
    return _result(
        message="reused writing outline project" if reused and after_id == revision_id else "published writing outline project",
        project_id=project_id,
        revision_id=revision_id,
        parent_revision_id=None,
        reused=reused and after_id == revision_id,
        sections=list(revision_document["sections"]),
    )


def _normalize_instructions(value: object) -> str:
    if type(value) is not str:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "instructions must be a string")
    if _unsafe_body_text(value):
        _raise(LIGHT_WRITING_PROJECT_INVALID, "instructions must not contain unsafe control characters")
    if len(value) > MAX_INSTRUCTIONS:
        _raise(LIGHT_WRITING_PROJECT_INVALID, "instructions exceed the 4,000-character bound")
    return value


def _export_section_from_parent(
    workspace: Path,
    *,
    project_id: str,
    parent_revision_id: str,
    section_id: str,
    instructions: str,
) -> dict[str, Any]:
    bundle = _load_revision_bundle(workspace, project_id, parent_revision_id)
    if bundle is None:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "parent revision is missing, edited, or incomplete")
    live = _validate_writing_context(workspace, bundle["context"])
    if live.get("ok") is not True:
        return live
    previous = None
    for item in bundle["sections"]:
        if item["section_id"] == section_id:
            previous = item
            break
    if previous is None:
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "section_id is not in the current outline")
    try:
        return _section_wrapper(
            project_id=project_id,
            parent_revision_id=parent_revision_id,
            section_id=section_id,
            context=bundle["context"],
            outline=bundle["outline"],
            previous_section=previous,
            instructions=instructions,
        )
    except ResearchError as exc:
        return _catch(exc)


def _export_section_unlocked(
    workspace: Path,
    *,
    project_id: object,
    section_id: object,
    instructions: object,
) -> dict[str, Any]:
    ident = _require_hex64(project_id, "project_id")
    if type(section_id) is not str or SECTION_ID.fullmatch(section_id) is None:
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "section_id must match s[1-9][0-9]?")
    text = _normalize_instructions(instructions)
    extras = _project_extra_names(workspace, ident)
    if extras:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project directory contains unknown entries")
    head = _load_head(workspace, ident)
    if head is None:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD is pending or missing")
    if head.get("ok") is not True:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, str(head.get("message") or "HEAD.json is not a validated pointer"))
    ancestry = _walk_ancestry(workspace, ident, str(head["revision_id"]))
    if type(ancestry) is dict:
        return ancestry
    unexpected = _unexpected_revisions(workspace, ident, {item["revision_id"] for item in ancestry})
    if unexpected is not None:
        return unexpected
    return _export_section_from_parent(
        workspace,
        project_id=ident,
        parent_revision_id=str(head["revision_id"]),
        section_id=section_id,
        instructions=text,
    )


def _import_section_unlocked(workspace: Path, wrapper: object, document: object) -> dict[str, Any]:
    checked = _require_section_wrapper(wrapper)
    project_id = str(checked["project_id"])
    parent_revision_id = str(checked["parent_revision_id"])
    section_id = str(checked["section_id"])
    instructions = str(checked["instructions"])
    extras = _project_extra_names(workspace, project_id)
    if extras:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project directory contains unknown entries")
    _assert_staging_recognizable(workspace)
    head = _load_head(workspace, project_id)
    if head is None:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD is missing or edited")
    if head.get("ok") is not True:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, str(head.get("message") or "HEAD.json is not a validated pointer"))
    current_head = head.get("revision_id")
    parent_bundle = _load_revision_bundle(workspace, project_id, parent_revision_id)
    if parent_bundle is None:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "parent revision is missing, edited, or incomplete")
    live = _validate_writing_context(workspace, parent_bundle["context"])
    if live.get("ok") is not True:
        return live
    reconstructed = _export_section_from_parent(
        workspace,
        project_id=project_id,
        parent_revision_id=parent_revision_id,
        section_id=section_id,
        instructions=instructions,
    )
    if reconstructed.get("ok") is not True:
        return reconstructed
    if canonical_bytes(reconstructed) != canonical_bytes({key: checked[key] for key in SECTION_EXPORT_KEYS}):
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "section wrapper does not match the checked parent export")
    section_doc = _validate_section_document(
        document,
        project_id=project_id,
        section_id=section_id,
        context=parent_bundle["context"],
    )
    next_sections = _replace_section(parent_bundle["sections"], section_doc)
    revision_document = _revision_document(
        project_id=project_id,
        parent_revision_id=parent_revision_id,
        kind=KIND_SECTION,
        target_section_id=section_id,
        instructions=instructions,
        outline=parent_bundle["outline"],
        sections=next_sections,
    )
    revision_id = _revision_identity(
        project_id=project_id,
        parent_revision_id=parent_revision_id,
        context_sha256=sha256_canonical(parent_bundle["context"]),
        document=revision_document,
    )
    files = _revision_files(
        workspace=workspace,
        project_id=project_id,
        revision_id=revision_id,
        parent_revision_id=parent_revision_id,
        context=parent_bundle["context"],
        document=revision_document,
    )
    if current_head not in {parent_revision_id, revision_id}:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD is not the expected parent revision")
    ancestry = _walk_ancestry(workspace, project_id, parent_revision_id)
    if type(ancestry) is dict:
        return ancestry
    unexpected = _unexpected_revisions(
        workspace,
        project_id,
        {item["revision_id"] for item in ancestry} | {revision_id},
    )
    if unexpected is not None:
        return unexpected
    section_count = sum(1 for item in ancestry if item["bundle"]["document"]["kind"] == KIND_SECTION)
    if current_head != revision_id and section_count >= MAX_SECTION_REVISIONS:
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "writing revision ancestry exceeds 128 section revisions")
    reused = _publish_revision(workspace, project_id, revision_id, files)
    live = _validate_writing_context(workspace, parent_bundle["context"])
    if live.get("ok") is not True:
        return live
    head_after = _load_head(workspace, project_id)
    if head_after is not None and head_after.get("ok") is not True:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, str(head_after.get("message") or "HEAD.json is not a validated pointer"))
    after_id = None if head_after is None else head_after.get("revision_id")
    if after_id not in {parent_revision_id, revision_id}:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD changed before pointer publication")
    _publish_head(workspace, project_id, revision_id, expected=after_id)
    return _result(
        message="reused writing section revision" if reused and after_id == revision_id else "published writing section revision",
        project_id=project_id,
        revision_id=revision_id,
        parent_revision_id=parent_revision_id,
        reused=reused and after_id == revision_id,
        sections=next_sections,
    )


def _history_unlocked(workspace: Path, project_id: object) -> dict[str, Any]:
    ident = _require_hex64(project_id, "project_id")
    diagnostics: list[dict[str, str]] = []
    extras = _project_extra_names(workspace, ident)
    if extras:
        return _closed(
            LIGHT_WRITING_PROJECT_CONFLICT,
            "writing project directory contains unknown entries",
            diagnostics=_bounded_diagnostics(
                [
                    {
                        "message": "unknown project entry",
                        "path": f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{ident}/{name}",
                        "status": LIGHT_WRITING_PROJECT_CONFLICT,
                    }
                    for name in extras
                ]
            ),
            head_revision_id=None,
            project_id=ident,
            revisions=[],
            schema=HISTORY_SCHEMA,
        )
    project = _project_dir(workspace, ident)
    if not (project.exists() or os.path.lexists(project)):
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "writing project does not exist", project_id=ident, schema=HISTORY_SCHEMA)
    if not _is_regular_dir(project):
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project directory is unsafe", project_id=ident, schema=HISTORY_SCHEMA)
    head = _load_head(workspace, ident)
    listed = _list_revision_ids(workspace, ident)
    if type(listed) is dict:
        listed["project_id"] = ident
        listed["schema"] = HISTORY_SCHEMA
        listed["head_revision_id"] = None
        listed["revisions"] = []
        listed["diagnostics"] = _bounded_diagnostics(
            [
                {
                    "message": str(listed.get("message") or "revisions are unsafe"),
                    "path": f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{ident}/{REVISIONS_DIRNAME}",
                    "status": LIGHT_WRITING_PROJECT_CONFLICT,
                }
            ]
        )
        return listed
    if head is None:
        pending_path = f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{ident}/{HEAD_NAME}"
        owned = False
        if type(listed) is list and len(listed) == 1:
            try:
                owned = _has_pending_head_intent(workspace, ident, listed[0])
            except ResearchError:
                owned = False
        if owned:
            diagnostics.append(
                {
                    "path": pending_path,
                    "status": "pending",
                    "message": "recognized writing publication is incomplete; retry the last import",
                }
            )
            message = "writing project HEAD is pending"
        else:
            diagnostics.append(
                {
                    "path": pending_path,
                    "status": LIGHT_WRITING_PROJECT_CONFLICT,
                    "message": "writing project HEAD is missing or edited",
                }
            )
            message = "writing project HEAD is missing or edited"
        return {
            "diagnostics": _bounded_diagnostics(diagnostics),
            "head_revision_id": None,
            "message": message,
            "ok": False,
            "project_id": ident,
            "revisions": [],
            "schema": HISTORY_SCHEMA,
            "status": LIGHT_WRITING_PROJECT_CONFLICT,
        }
    if head.get("ok") is not True:
        return _closed(
            LIGHT_WRITING_PROJECT_CONFLICT,
            str(head.get("message") or "HEAD.json is not a validated pointer"),
            diagnostics=_bounded_diagnostics(
                [
                    {
                        "message": str(head.get("message") or "HEAD.json is not a validated pointer"),
                        "path": f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{ident}/{HEAD_NAME}",
                        "status": LIGHT_WRITING_PROJECT_CONFLICT,
                    }
                ]
            ),
            head_revision_id=None,
            project_id=ident,
            revisions=[],
            schema=HISTORY_SCHEMA,
        )
    ancestry = _walk_ancestry(workspace, ident, str(head["revision_id"]))
    if type(ancestry) is dict:
        ancestry["project_id"] = ident
        ancestry["schema"] = HISTORY_SCHEMA
        ancestry["head_revision_id"] = head.get("revision_id")
        ancestry["revisions"] = []
        ancestry["diagnostics"] = _bounded_diagnostics(
            [
                {
                    "message": str(ancestry.get("message") or "revision ancestry is invalid"),
                    "path": f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{ident}/{REVISIONS_DIRNAME}",
                    "status": LIGHT_WRITING_PROJECT_CONFLICT,
                }
            ]
        )
        return ancestry
    known = {item["revision_id"] for item in ancestry}
    extras_rev = [item for item in listed if item not in known]
    if extras_rev:
        return _closed(
            LIGHT_WRITING_PROJECT_CONFLICT,
            "writing project contains an unexpected revision",
            diagnostics=_bounded_diagnostics(
                [
                    {
                        "message": "revision is not in the validated HEAD ancestry",
                        "path": f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{ident}/{REVISIONS_DIRNAME}/{item}",
                        "status": LIGHT_WRITING_PROJECT_CONFLICT,
                    }
                    for item in extras_rev
                ]
            ),
            head_revision_id=head.get("revision_id"),
            project_id=ident,
            revisions=[],
            schema=HISTORY_SCHEMA,
        )
    context = ancestry[0]["bundle"]["context"]
    source_status = _source_status(workspace, context)
    if source_status == "conflict":
        return _closed(
            LIGHT_WRITING_PROJECT_CONFLICT,
            "writing context bytes conflict with live source diagnosis",
            diagnostics=_bounded_diagnostics(
                [
                    {
                        "message": "original writing context is not diagnosable",
                        "path": f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}/{ident}/{REVISIONS_DIRNAME}/{ancestry[0]['revision_id']}/{CONTEXT_NAME}",
                        "status": LIGHT_WRITING_PROJECT_CONFLICT,
                    }
                ]
            ),
            head_revision_id=head.get("revision_id"),
            project_id=ident,
            revisions=[],
            schema=HISTORY_SCHEMA,
        )
    rows = []
    head_id = str(head["revision_id"])
    for item in ancestry:
        document = item["bundle"]["document"]
        rows.append(
            {
                "revision_id": item["revision_id"],
                "parent_revision_id": document["parent_revision_id"],
                "is_head": item["revision_id"] == head_id,
                "kind": document["kind"],
                "target_section_id": document["target_section_id"],
                "source_status": source_status,
                "progress": _progress(item["bundle"]["sections"]),
                "page_path": _page_path(ident, item["revision_id"]),
            }
        )
    payload = {
        "diagnostics": _bounded_diagnostics(diagnostics),
        "head_revision_id": head_id,
        "message": HISTORY_OK_MESSAGE,
        "ok": True,
        "project_id": ident,
        "revisions": rows,
        "schema": HISTORY_SCHEMA,
        "status": OK,
    }
    return {key: payload[key] for key in HISTORY_KEYS}


def _bounded_diagnostics(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in rows[:MAX_DIAGNOSTICS]:
        cleaned.append({"path": item["path"], "status": item["status"], "message": item["message"]})
    return cleaned


def _export_project_unlocked(workspace: Path, *, project_id: object, output: object) -> dict[str, Any]:
    ident = _require_hex64(project_id, "project_id")
    target = _require_writing_output(workspace, output)
    extras = _project_extra_names(workspace, ident)
    if extras:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project directory contains unknown entries")
    head = _load_head(workspace, ident)
    if head is None:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project HEAD is pending or missing")
    if head.get("ok") is not True:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, str(head.get("message") or "HEAD.json is not a validated pointer"))
    ancestry = _walk_ancestry(workspace, ident, str(head["revision_id"]))
    if type(ancestry) is dict:
        return ancestry
    unexpected = _unexpected_revisions(workspace, ident, {item["revision_id"] for item in ancestry})
    if unexpected is not None:
        return unexpected
    current = ancestry[-1]["bundle"]
    live = _validate_writing_context(workspace, current["context"])
    if live.get("ok") is not True:
        return live
    progress = _progress(current["sections"])
    if progress["written"] == 0:
        return _closed(LIGHT_WRITING_PROJECT_INVALID, "refuse exporting a wholly unwritten or all-unknown article as a completed draft")
    markdown = _render_project_markdown(
        workspace=workspace,
        output=target,
        title=str(current["document"]["title"]),
        sections=list(current["sections"]),
        outline=current["outline"],
        context=current["context"],
    )
    encoded = markdown.encode("utf-8")
    reused = False
    if target.exists() or os.path.lexists(target):
        if not _is_regular_file(target) or _hardlinked(target):
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "export target must be a regular file", path=str(target))
        existing = target.read_bytes()
        if existing != encoded:
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "export already exists with different bytes", path=str(target))
        reused = True
    else:
        tmp = target.with_name(f".{target.name}.{secrets.token_hex(8)}.light-out.tmp")
        try:
            if not target.parent.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
            _write_bytes(tmp, encoded)
            exclusive_rename(tmp, target)
        except FileExistsError:
            if tmp.exists() and _is_regular_file(tmp):
                tmp.unlink()
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "export already exists", path=str(target))
        except OSError as exc:
            if tmp.exists() and _is_regular_file(tmp):
                tmp.unlink()
            return _closed(LIGHT_WRITING_PROJECT_CONFLICT, f"cannot install export: {exc}", path=str(target))
    payload = {
        "message": EXPORT_OK_MESSAGE if progress["complete"] else EXPORT_INCOMPLETE_MESSAGE,
        "ok": True,
        "path": str(target),
        "progress": progress,
        "project_id": ident,
        "reused": reused,
        "revision_id": ancestry[-1]["revision_id"],
        "schema": EXPORT_SCHEMA,
        "status": OK,
    }
    return {key: payload[key] for key in EXPORT_KEYS}


def _diagnostic(path: str, status: str, message: str) -> dict[str, str]:
    return {"path": path, "status": status, "message": message}


def _staging_blockers(workspace: Path) -> list[dict[str, str]]:
    root = _staging_root(workspace)
    rel = f"{WRITING_DIRNAME}/{STAGING_DIRNAME}"
    if not (root.exists() or os.path.lexists(root)):
        return []
    if root.is_symlink() or not root.is_dir() or _symlink_in_chain(root):
        return [_diagnostic(rel, "unsafe", "writing staging is not a regular directory")]
    try:
        names = sorted(item.name for item in root.iterdir())
    except OSError:
        return [_diagnostic(rel, "unsafe", "writing staging is unreadable")]
    if not names:
        return []
    return [_diagnostic(rel, "pending", "nonempty writing staging must be recovered by exact retry before backup")]


def _project_blockers(workspace: Path) -> list[dict[str, str]]:
    root = _projects_root(workspace)
    rel = f"{WRITING_DIRNAME}/{PROJECTS_DIRNAME}"
    if not (root.exists() or os.path.lexists(root)):
        return []
    if root.is_symlink() or not root.is_dir() or _symlink_in_chain(root):
        return [_diagnostic(rel, "unsafe", "writing projects directory is not a regular directory")]
    blockers: list[dict[str, str]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return [_diagnostic(rel, "unsafe", "writing projects directory is unreadable")]
    for item in entries:
        path = f"{rel}/{item.name}"
        if item.is_symlink() or not item.is_dir() or not _is_hex64(item.name):
            blockers.append(_diagnostic(path, "conflict", "writing project entry is unknown or unsafe"))
            continue
        extras = _project_extra_names(workspace, item.name)
        if extras:
            blockers.append(_diagnostic(path, "conflict", "writing project directory contains unknown entries"))
            continue
        try:
            history = _history_unlocked(workspace, item.name)
        except (ResearchError, OSError, KeyError, TypeError, OverflowError, UnicodeError, ValueError):
            blockers.append(_diagnostic(path, "conflict", "writing project stored state is malformed"))
            continue
        if history.get("ok") is True:
            continue
        status = "pending" if any(row.get("status") == "pending" for row in history.get("diagnostics") or []) else "conflict"
        blockers.append(_diagnostic(path, status, str(history.get("message") or "writing project is incomplete")))
    return blockers


def writing_backup_blockers(workspace_root: object) -> list[dict[str, str]]:
    """Read-only pending/conflict diagnostics. Backup holds the workspace lock."""
    try:
        workspace = _require_writing_workspace(workspace_root)
    except ResearchError as exc:
        return [_diagnostic(str(workspace_root), exc.code, exc.message)]
    except (OSError, KeyError, TypeError, UnicodeError, ValueError):
        return [_diagnostic(str(workspace_root), LIGHT_WRITING_PROJECT_CONFLICT, "writing workspace is malformed")]
    root = _writing_root(workspace)
    if not (root.exists() or os.path.lexists(root)):
        return []
    if root.is_symlink() or not root.is_dir() or _symlink_in_chain(root):
        return [_diagnostic(WRITING_DIRNAME, "unsafe", ".light-writing is not a regular directory")]
    try:
        names = sorted(item.name for item in root.iterdir())
    except OSError:
        return [_diagnostic(WRITING_DIRNAME, "unsafe", ".light-writing is unreadable")]
    blockers: list[dict[str, str]] = []
    for name in names:
        if name not in {PROJECTS_DIRNAME, STAGING_DIRNAME}:
            blockers.append(
                _diagnostic(f"{WRITING_DIRNAME}/{name}", "unknown", "unrecognized .light-writing entry")
            )
    try:
        blockers.extend(_staging_blockers(workspace))
        blockers.extend(_project_blockers(workspace))
    except (ResearchError, OSError, KeyError, TypeError, OverflowError, UnicodeError, ValueError):
        blockers.append(_diagnostic(WRITING_DIRNAME, LIGHT_WRITING_PROJECT_CONFLICT, "writing stored state is malformed"))
    return blockers[:MAX_DIAGNOSTICS]


def _locked_call(workspace_root: object, fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        workspace = _require_writing_workspace(workspace_root)
        with _workspace_lock(workspace):
            return fn(workspace, *args, **kwargs)
    except ResearchError as exc:
        if exc.code in LIVE_STATUSES or exc.code in {LIGHT_WRITING_PROJECT_INVALID, LIGHT_WRITING_PROJECT_CONFLICT}:
            return _catch(exc)
        return _closed(LIGHT_WRITING_PROJECT_INVALID, exc.message)
    except OSError as exc:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, f"publication filesystem failure: {exc}")
    except OverflowError:
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project numeric value is not a finite number")
    except (KeyError, TypeError, UnicodeError, ValueError):
        return _closed(LIGHT_WRITING_PROJECT_CONFLICT, "writing project input or stored object is malformed")


def export_writing_outline(workspace_root: object, context: object) -> dict[str, Any]:
    return _locked_call(workspace_root, _export_outline_unlocked, context)


def import_writing_outline(workspace_root: object, context: object, document: object) -> dict[str, Any]:
    return _locked_call(workspace_root, _import_outline_unlocked, context, document)


def export_writing_section(
    workspace_root: object,
    *,
    project_id: object,
    section_id: object,
    instructions: object = "",
) -> dict[str, Any]:
    return _locked_call(
        workspace_root,
        _export_section_unlocked,
        project_id=project_id,
        section_id=section_id,
        instructions=instructions,
    )


def import_writing_section(workspace_root: object, context: object, document: object) -> dict[str, Any]:
    return _locked_call(workspace_root, _import_section_unlocked, context, document)


def writing_project_history(workspace_root: object, *, project_id: object) -> dict[str, Any]:
    return _locked_call(workspace_root, _history_unlocked, project_id)


def export_writing_project(workspace_root: object, *, project_id: object, output: object) -> dict[str, Any]:
    return _locked_call(workspace_root, _export_project_unlocked, project_id=project_id, output=output)
