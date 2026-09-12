"""Resumable current-model research workflow. No model client or network."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol

from video_paper_wiki_research.contracts import ResearchError

OK = "OK"
NO_RESULTS = "NO_RESULTS"
INDEX_STALE = "INDEX_STALE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
WORKSPACE_INVALID = "WORKSPACE_INVALID"
LIGHT_SESSION_INVALID = "LIGHT_SESSION_INVALID"
LIGHT_SESSION_CONFLICT = "LIGHT_SESSION_CONFLICT"
LIGHT_WORKSPACE_BUSY = "LIGHT_WORKSPACE_BUSY"
LIGHT_SELECTION_INVALID = "LIGHT_SELECTION_INVALID"
LIGHT_OUTPUT_CONFLICT = "LIGHT_OUTPUT_CONFLICT"
LIGHT_CONTEXT_INVALID = "LIGHT_CONTEXT_INVALID"
LIGHT_WORKSPACE_MISMATCH = "LIGHT_WORKSPACE_MISMATCH"

WORKFLOW_SCHEMA = "video-paper-wiki.light-workflow.v1"
REQUEST_SCHEMA = "video-paper-wiki.light-workflow-request.v1"
MANIFEST_SCHEMA = "video-paper-wiki.light-workflow-manifest.v1"
IDENTITY_SCHEMA = "video-paper-wiki.light-workflow-identity.v1"
INTENT_SCHEMA = "video-paper-wiki.light-workflow-intent.v1"
RECEIPT_SCHEMA = "video-paper-wiki.light-workflow-completion.v1"
STAGING_SCHEMA = "video-paper-wiki.light-workflow-staging.v1"
CONTEXT_SCHEMA = "video-paper-wiki.light-context.v1"

WORKFLOW_DIRNAME = ".light-workflow"
SESSIONS_DIRNAME = "sessions"
STAGING_DIRNAME = "staging"
LOCKS_DIRNAME = "locks"
OWNERSHIP_NAME = "ownership.json"
REQUEST_NAME = "request.json"
CONTEXT_NAME = "context.json"
MANIFEST_NAME = "manifest.json"
INTENT_NAME = "completion-intent.json"
RECEIPT_NAME = "completion.json"
PREPARED_NAMES = frozenset({REQUEST_NAME, CONTEXT_NAME, MANIFEST_NAME})
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PAPER_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
KINDS = frozenset({"qa", "writing"})
CLOSED_NO_SESSION = frozenset({NO_RESULTS, INSUFFICIENT_EVIDENCE})
LIVE_UNUSABLE = frozenset(
    {
        INDEX_STALE,
        LIGHT_CONTEXT_INVALID,
        LIGHT_WORKSPACE_MISMATCH,
        LIGHT_SELECTION_INVALID,
        NO_RESULTS,
        INSUFFICIENT_EVIDENCE,
    }
)

STATE_AWAITING = "awaiting_model"
STATE_COMPLETE = "complete"
STATE_STALE = "stale"
STATE_NEEDS_ATTENTION = "needs_attention"

NEXT_READ_CONTEXT = "read the exported context and construct a model document in the current session"
NEXT_COMPLETE = "call complete_workflow with the same session_id, model document, and output path"
NEXT_RETRY_COMPLETE = "retry complete_workflow with the same model document and output path"
NEXT_REPREPARE = "call prepare_workflow again after refreshing sources or the index"
NEXT_INSPECT = "inspect session diagnostics; do not overwrite user-edited output"
NEXT_NO_EVIDENCE = "do not ask the current model to invent an answer; adjust the query or paper selection"

HOOK_AFTER_INTENT = "after_intent"
HOOK_AFTER_OUTPUT = "after_output"
HOOK_BEFORE_RECEIPT = "before_receipt"
HOOK_BEFORE_SESSION_PUBLISH = "before_session_publish"
HOOK_AFTER_INTENT_STAGED = "after_intent_staged"
HOOK_AFTER_RECEIPT_STAGED = "after_receipt_staged"

REQUEST_FIELDS = frozenset(
    {"schema", "workspace_root", "kind", "query", "requirements", "selected_paper_ids"}
)


class _PublishRefused(Exception):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class WorkflowBackend(Protocol):
    def extract_pdf(self, pdf_path: Path, workspace_root: Path, *, title: str | None = None) -> dict[str, Any]: ...

    def inspect_workspace(self, workspace_root: Path) -> dict[str, Any]: ...

    def build_index(self, workspace_root: Path) -> dict[str, Any]: ...

    def export_context(
        self,
        workspace_root: Path,
        *,
        kind: str,
        query: str,
        requirements: str = "",
        paper_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def validate_live_context(self, workspace_root: Path, context: Mapping[str, Any]) -> dict[str, Any]: ...

    def render_document(
        self,
        workspace_root: Path,
        context: Mapping[str, Any],
        document: Mapping[str, Any],
        *,
        output: Path,
    ) -> dict[str, Any]: ...

    def import_document(
        self,
        workspace_root: Path,
        context: Mapping[str, Any],
        document: Mapping[str, Any],
        *,
        output: Path,
        overwrite: bool = True,
    ) -> dict[str, Any]: ...


class LiveWorkflowBackend:
    """Thin adapter over T1/T2 public functions. Import happens at call time."""

    def extract_pdf(self, pdf_path: Path, workspace_root: Path, *, title: str | None = None) -> dict[str, Any]:
        from video_paper_wiki_research.light_pdf import extract_pdf

        if title is None:
            return extract_pdf(pdf_path, workspace_root)
        return extract_pdf(pdf_path, workspace_root, title=title)

    def inspect_workspace(self, workspace_root: Path) -> dict[str, Any]:
        from video_paper_wiki_research.light_workspace import inspect_workspace

        return inspect_workspace(workspace_root)

    def build_index(self, workspace_root: Path) -> dict[str, Any]:
        from video_paper_wiki_research.light_index import build_index

        return build_index(workspace_root)

    def export_context(
        self,
        workspace_root: Path,
        *,
        kind: str,
        query: str,
        requirements: str = "",
        paper_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        from video_paper_wiki_research.light_context import export_context

        return export_context(
            workspace_root,
            kind=kind,
            query=query,
            requirements=requirements,
            paper_ids=paper_ids,
        )

    def validate_live_context(self, workspace_root: Path, context: Mapping[str, Any]) -> dict[str, Any]:
        from video_paper_wiki_research.light_context import validate_live_context

        return validate_live_context(workspace_root, context)

    def render_document(
        self,
        workspace_root: Path,
        context: Mapping[str, Any],
        document: Mapping[str, Any],
        *,
        output: Path,
    ) -> dict[str, Any]:
        from video_paper_wiki_research.light_context import render_document

        return render_document(workspace_root, context, document, output=output)

    def import_document(
        self,
        workspace_root: Path,
        context: Mapping[str, Any],
        document: Mapping[str, Any],
        *,
        output: Path,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        from video_paper_wiki_research.light_context import import_document

        return import_document(workspace_root, context, document, output=output, overwrite=overwrite)


def live_backend() -> LiveWorkflowBackend:
    return LiveWorkflowBackend()


def _select_backend(explicit: WorkflowBackend | None) -> WorkflowBackend:
    return live_backend() if explicit is None else explicit


def _fail(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise ResearchError(code, message, details)


def _closed(*, status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "status": status, "message": message}
    payload.update(extra)
    return payload


def _reject_nonfinite(value: object) -> None:
    if type(value) is float and not math.isfinite(value):
        _fail(LIGHT_SESSION_INVALID, "workflow JSON cannot contain nonfinite numbers")
    if type(value) is dict:
        for item in value.values():
            _reject_nonfinite(item)
        return
    if type(value) is list:
        for item in value:
            _reject_nonfinite(item)


def canonical_bytes(value: object) -> bytes:
    """C(x): UTF-8 JSON, sorted keys, no trailing LF."""

    _reject_nonfinite(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        _fail(LIGHT_SESSION_INVALID, "workflow JSON is not canonicalizable")
        raise AssertionError("unreachable") from exc


def persisted_bytes(value: object) -> bytes:
    """B(x) = C(x) + one LF."""

    return canonical_bytes(value) + b"\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_canonical(value: object) -> str:
    return sha256_bytes(canonical_bytes(value))


def sha256_persisted(value: object) -> str:
    return sha256_bytes(persisted_bytes(value))


def _write_persisted(path: Path, value: object) -> bytes:
    encoded = persisted_bytes(value)
    path.write_bytes(encoded)
    return encoded


def _as_path(value: object, name: str) -> Path:
    if isinstance(value, Path):
        return value
    if type(value) is str:
        return Path(value)
    _fail(LIGHT_SESSION_INVALID, f"{name} must be a path")
    raise AssertionError("unreachable")


def _absolute_output(output: object) -> Path:
    path = _as_path(output, "output")
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return Path(os.path.normpath(path))


def _resolve_existing_dir(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        _fail(WORKSPACE_INVALID, "workspace_root must be a regular directory")
    return path.resolve()


def _workspace_path(workspace_root: object) -> Path:
    path = _as_path(workspace_root, "workspace_root")
    if path.exists():
        return _resolve_existing_dir(path)
    return Path(os.path.normpath(path.expanduser()))


def _workflow_root(workspace: Path) -> Path:
    return workspace / WORKFLOW_DIRNAME


def _sessions_root(workspace: Path) -> Path:
    return _workflow_root(workspace) / SESSIONS_DIRNAME


def _staging_root(workspace: Path) -> Path:
    return _workflow_root(workspace) / STAGING_DIRNAME


def _locks_root(workspace: Path) -> Path:
    return _workflow_root(workspace) / LOCKS_DIRNAME


def _is_regular_dir(path: Path) -> bool:
    return (not path.is_symlink()) and path.is_dir()


def _is_regular_file(path: Path) -> bool:
    return (not path.is_symlink()) and path.is_file()


def _symlink_in_chain(path: Path, stop_at: Path) -> bool:
    cursor = path
    while True:
        try:
            if cursor.is_symlink():
                return True
        except OSError:
            return True
        if cursor == stop_at or cursor.parent == cursor:
            return False
        cursor = cursor.parent


def _refuse_existing_state_dir(path: Path, label: str) -> None:
    if path.is_symlink():
        _fail(LIGHT_SESSION_INVALID, f"{label} must not be a symlink")
    if path.exists() and not path.is_dir():
        _fail(LIGHT_SESSION_INVALID, f"{label} must be a regular directory")


def _assert_workflow_state_paths(workspace: Path) -> None:
    root = _workflow_root(workspace)
    _refuse_existing_state_dir(root, ".light-workflow")
    _refuse_existing_state_dir(root / SESSIONS_DIRNAME, "workflow sessions")
    _refuse_existing_state_dir(root / STAGING_DIRNAME, "workflow staging")
    _refuse_existing_state_dir(root / LOCKS_DIRNAME, "workflow locks")


def _ensure_regular_dir(path: Path, *, stop_at: Path) -> None:
    if path.is_symlink():
        _fail(LIGHT_SESSION_INVALID, "workflow state path must not be a symlink")
    if path.exists():
        if not path.is_dir():
            _fail(LIGHT_SESSION_INVALID, "workflow state path must be a regular directory")
        return
    if path == stop_at:
        _fail(WORKSPACE_INVALID, "workspace_root must be a regular directory")
    _ensure_regular_dir(path.parent, stop_at=stop_at)
    path.mkdir(exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        _fail(LIGHT_SESSION_INVALID, "workflow state path must be a regular directory")


def _workflow_state_diagnostics(workspace: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = _workflow_root(workspace)
    mapping = (
        (root, WORKFLOW_DIRNAME),
        (root / SESSIONS_DIRNAME, f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}"),
        (root / STAGING_DIRNAME, f"{WORKFLOW_DIRNAME}/{STAGING_DIRNAME}"),
        (root / LOCKS_DIRNAME, f"{WORKFLOW_DIRNAME}/{LOCKS_DIRNAME}"),
    )
    for path, rel in mapping:
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            rows.append(
                {
                    "relative_path": rel,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "workflow state path is not a regular directory",
                }
            )
    return rows


def _normalize_kind(kind: object) -> str:
    if type(kind) is not str or kind not in KINDS:
        _fail(LIGHT_SESSION_INVALID, "kind must be exactly qa or writing")
    return kind


def _normalize_query(query: object) -> str:
    if type(query) is not str or not query.strip():
        _fail(LIGHT_SESSION_INVALID, "query must be a nonempty string")
    return query


def _normalize_requirements(requirements: object) -> str:
    if type(requirements) is not str:
        _fail(LIGHT_SESSION_INVALID, "requirements must be a string")
    return requirements


def normalize_selected_paper_ids(paper_ids: object) -> list[str]:
    if paper_ids is None or paper_ids == []:
        return []
    if type(paper_ids) is not list:
        _fail(LIGHT_SELECTION_INVALID, "paper_ids must be a list of sha256:<64 lowercase hex> strings")
    selected: list[str] = []
    seen: set[str] = set()
    for item in paper_ids:
        if type(item) is not str or not PAPER_ID.fullmatch(item):
            _fail(LIGHT_SELECTION_INVALID, "paper_ids must be sha256:<64 lowercase hex> strings")
        if item in seen:
            continue
        seen.add(item)
        selected.append(item)
    return selected


def _normalize_pdf_paths(pdf_paths: object) -> list[Path]:
    if pdf_paths is None:
        return []
    if type(pdf_paths) is not list:
        _fail(LIGHT_SESSION_INVALID, "pdf_paths must be a list")
    paths: list[Path] = []
    for item in pdf_paths:
        paths.append(_as_path(item, "pdf_paths item"))
    return paths


def _require_session_id(session_id: object) -> str:
    if type(session_id) is not str or not HEX64.fullmatch(session_id):
        _fail(LIGHT_SESSION_INVALID, "session_id must be 64 lowercase hex characters")
    return session_id


def _session_dir(workspace: Path, session_id: str) -> Path:
    ident = _require_session_id(session_id)
    root = _sessions_root(workspace)
    path = root / ident
    if _symlink_in_chain(path, workspace) or root.is_symlink() or path.is_symlink():
        _fail(LIGHT_SESSION_INVALID, "session directory must not be a symlink")
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            _fail(LIGHT_SESSION_INVALID, "session directory must not be a symlink")
        resolved = path.resolve()
        parent = root.resolve() if root.exists() else root
        if resolved.parent != parent or resolved.name != ident:
            _fail(LIGHT_SESSION_INVALID, "session path escaped the sessions directory")
    return path


def session_identity(request_sha256: str, context_sha256: str) -> str:
    return sha256_canonical(
        {
            "context_sha256": context_sha256,
            "request_sha256": request_sha256,
            "schema": IDENTITY_SCHEMA,
        }
    )


def build_request(
    *,
    workspace_root: Path,
    kind: str,
    query: str,
    requirements: str,
    selected_paper_ids: list[str],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "query": query,
        "requirements": requirements,
        "schema": REQUEST_SCHEMA,
        "selected_paper_ids": list(selected_paper_ids),
        "workspace_root": str(workspace_root),
    }


def build_manifest(
    *,
    session_id: str,
    workspace_root: Path,
    index_id: object,
    request_sha256: str,
    context_sha256: str,
) -> dict[str, Any]:
    return {
        "context_sha256": context_sha256,
        "index_id": index_id,
        "request_sha256": request_sha256,
        "schema": MANIFEST_SCHEMA,
        "session_id": session_id,
        "workspace_root": str(workspace_root),
    }


class _Busy(Exception):
    pass


@contextmanager
def _exclusive_lock(lock_path: Path, workspace: Path) -> Iterator[None]:
    _assert_workflow_state_paths(workspace)
    _ensure_regular_dir(lock_path.parent, stop_at=workspace)
    if lock_path.is_symlink() or (lock_path.exists() and not lock_path.is_file()):
        _fail(LIGHT_SESSION_INVALID, "workflow lock path is unsafe")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise _Busy() from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def _load_persisted_object(path: Path) -> tuple[dict[str, Any], bytes, str] | None:
    if path.is_symlink() or not path.is_file():
        return None
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    if type(value) is not dict:
        return None
    try:
        expected = persisted_bytes(value)
    except ResearchError:
        return None
    if raw != expected:
        return None
    return value, raw, sha256_bytes(raw)


def _entry_names(directory: Path) -> list[str] | None:
    if not _is_regular_dir(directory):
        return None
    names: list[str] = []
    for item in directory.iterdir():
        names.append(item.name)
    return sorted(names)


def _allowed_session_names(names: set[str]) -> bool:
    if not PREPARED_NAMES <= names:
        return False
    extra = names - PREPARED_NAMES
    if extra == set():
        return True
    if extra == {INTENT_NAME}:
        return True
    if extra == {INTENT_NAME, RECEIPT_NAME}:
        return True
    return False


def _file_diagnostics(session_dir: Path, names: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted(names):
        path = session_dir / name
        if path.is_symlink():
            rows.append({"relative_path": name, "code": LIGHT_SESSION_INVALID, "message": "session entry is a symlink"})
        elif not path.is_file():
            rows.append(
                {"relative_path": name, "code": LIGHT_SESSION_INVALID, "message": "session entry is not a regular file"}
            )
    return rows


def _request_structure_diagnostics(request: Mapping[str, Any], workspace: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if type(request) is not dict or set(request) != REQUEST_FIELDS:
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request fields are not the exact contract C set",
            }
        )
        return rows
    if request.get("schema") != REQUEST_SCHEMA:
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request schema is not the contract C request schema",
            }
        )
    if request.get("workspace_root") != str(workspace):
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request workspace_root does not match the inspected workspace",
            }
        )
    if type(request.get("kind")) is not str or request.get("kind") not in KINDS:
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request kind must be exactly qa or writing",
            }
        )
    query = request.get("query")
    if type(query) is not str or not query.strip():
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request query must be a nonempty string",
            }
        )
    if type(request.get("requirements")) is not str:
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request requirements must be a string",
            }
        )
    selected = request.get("selected_paper_ids")
    if type(selected) is not list:
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request selected_paper_ids must be a list",
            }
        )
        return rows
    seen: list[str] = []
    for item in selected:
        if type(item) is not str or not PAPER_ID.fullmatch(item):
            rows.append(
                {
                    "relative_path": REQUEST_NAME,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "request selected_paper_ids must be normalized sha256:<64 lowercase hex> strings",
                }
            )
            return rows
        if item in seen:
            rows.append(
                {
                    "relative_path": REQUEST_NAME,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "request selected_paper_ids must be normalized without duplicates",
                }
            )
            return rows
        seen.append(item)
    return rows


def _request_context_diagnostics(request: Mapping[str, Any], context: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if type(context) is not dict:
        rows.append(
            {
                "relative_path": CONTEXT_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "context is not an object",
            }
        )
        return rows
    if request.get("kind") != context.get("kind"):
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request kind does not match the persisted context",
            }
        )
    if request.get("query") != context.get("query"):
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request query does not match the persisted context",
            }
        )
    context_requirements = context.get("requirements")
    if context_requirements is None:
        context_requirements = ""
    if request.get("requirements") != context_requirements:
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request requirements do not match the persisted context",
            }
        )
    context_selected = context.get("selected_paper_ids")
    request_selected = request.get("selected_paper_ids")
    if context_selected is None:
        if request_selected not in ([], None):
            rows.append(
                {
                    "relative_path": REQUEST_NAME,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "request selection does not match the persisted context",
                }
            )
    elif type(context_selected) is not list or list(request_selected or []) != list(context_selected):
        rows.append(
            {
                "relative_path": REQUEST_NAME,
                "code": LIGHT_SESSION_INVALID,
                "message": "request selection does not match the persisted context",
            }
        )
    return rows


def _validate_loaded_session(workspace: Path, session_dir: Path) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    if session_dir.is_symlink() or not session_dir.is_dir():
        return {
            "ok": False,
            "state": STATE_NEEDS_ATTENTION,
            "diagnostics": [
                {
                    "relative_path": str(session_dir),
                    "code": LIGHT_SESSION_INVALID,
                    "message": "session must be a regular directory",
                }
            ],
        }
    names = _entry_names(session_dir)
    if names is None:
        return {
            "ok": False,
            "state": STATE_NEEDS_ATTENTION,
            "diagnostics": [
                {
                    "relative_path": session_dir.name,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "session directory cannot be listed",
                }
            ],
        }
    name_set = set(names)
    if session_dir.name != session_dir.resolve().name or not HEX64.fullmatch(session_dir.name):
        diagnostics.append(
            {
                "relative_path": session_dir.name,
                "code": LIGHT_SESSION_INVALID,
                "message": "session directory name is not a canonical session id",
            }
        )
    if not _allowed_session_names(name_set):
        diagnostics.append(
            {
                "relative_path": session_dir.name,
                "code": LIGHT_SESSION_INVALID,
                "message": "session contains unknown, incomplete, or disallowed entries",
            }
        )
    diagnostics.extend(_file_diagnostics(session_dir, name_set))
    loaded: dict[str, tuple[dict[str, Any], bytes, str]] = {}
    for name in PREPARED_NAMES:
        item = _load_persisted_object(session_dir / name)
        if item is None:
            diagnostics.append(
                {"relative_path": name, "code": LIGHT_SESSION_INVALID, "message": "prepared file is missing or not B(x)"}
            )
        else:
            loaded[name] = item
    intent_item = None
    receipt_item = None
    if INTENT_NAME in name_set:
        intent_item = _load_persisted_object(session_dir / INTENT_NAME)
        if intent_item is None:
            diagnostics.append(
                {"relative_path": INTENT_NAME, "code": LIGHT_SESSION_INVALID, "message": "intent is missing or not B(x)"}
            )
    if RECEIPT_NAME in name_set:
        if INTENT_NAME not in name_set:
            diagnostics.append(
                {
                    "relative_path": RECEIPT_NAME,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "completion receipt requires a completion intent",
                }
            )
        receipt_item = _load_persisted_object(session_dir / RECEIPT_NAME)
        if receipt_item is None:
            diagnostics.append(
                {
                    "relative_path": RECEIPT_NAME,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "receipt is missing or not B(x)",
                }
            )
    if diagnostics or REQUEST_NAME not in loaded or CONTEXT_NAME not in loaded or MANIFEST_NAME not in loaded:
        return {"ok": False, "state": STATE_NEEDS_ATTENTION, "diagnostics": diagnostics}

    request, _request_raw, request_sha = loaded[REQUEST_NAME]
    context, _context_raw, context_sha = loaded[CONTEXT_NAME]
    manifest, manifest_raw, manifest_sha = loaded[MANIFEST_NAME]
    structure = _request_structure_diagnostics(request, workspace)
    if structure:
        return {"ok": False, "state": STATE_NEEDS_ATTENTION, "diagnostics": structure}
    correspondence = _request_context_diagnostics(request, context)
    if correspondence:
        return {"ok": False, "state": STATE_NEEDS_ATTENTION, "diagnostics": correspondence}
    expected_id = session_identity(request_sha, context_sha)
    expected_manifest = build_manifest(
        session_id=expected_id,
        workspace_root=workspace,
        index_id=context.get("index_id"),
        request_sha256=request_sha,
        context_sha256=context_sha,
    )
    if (
        session_dir.name != expected_id
        or request.get("schema") != REQUEST_SCHEMA
        or request.get("workspace_root") != str(workspace)
        or manifest_raw != persisted_bytes(expected_manifest)
        or manifest.get("session_id") != expected_id
        or manifest.get("request_sha256") != request_sha
        or manifest.get("context_sha256") != context_sha
        or manifest.get("workspace_root") != str(workspace)
        or set(manifest) != set(expected_manifest)
    ):
        return {
            "ok": False,
            "state": STATE_NEEDS_ATTENTION,
            "diagnostics": [
                {
                    "relative_path": MANIFEST_NAME,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "session identity or manifest bytes do not match request and context",
                }
            ],
        }

    intent = None
    intent_sha = None
    if intent_item is not None:
        intent, _intent_raw, intent_sha = intent_item
        expected_intent_keys = {
            "schema",
            "session_id",
            "context_sha256",
            "document_sha256",
            "output_path",
            "output_sha256",
        }
        if (
            intent.get("schema") != INTENT_SCHEMA
            or set(intent) != expected_intent_keys
            or intent.get("session_id") != expected_id
            or intent.get("context_sha256") != context_sha
            or type(intent.get("document_sha256")) is not str
            or not HEX64.fullmatch(str(intent.get("document_sha256")))
            or type(intent.get("output_path")) is not str
            or type(intent.get("output_sha256")) is not str
            or not HEX64.fullmatch(str(intent.get("output_sha256")))
        ):
            return {
                "ok": False,
                "state": STATE_NEEDS_ATTENTION,
                "diagnostics": [
                    {
                        "relative_path": INTENT_NAME,
                        "code": LIGHT_SESSION_INVALID,
                        "message": "completion intent bindings are invalid",
                    }
                ],
            }

    receipt = None
    receipt_sha = None
    if receipt_item is not None:
        receipt, _receipt_raw, receipt_sha = receipt_item
        expected_receipt_keys = {
            "schema",
            "session_id",
            "request_sha256",
            "context_sha256",
            "manifest_sha256",
            "index_id",
            "intent_sha256",
            "document_sha256",
            "output_path",
            "output_sha256",
        }
        if (
            intent is None
            or intent_sha is None
            or receipt.get("schema") != RECEIPT_SCHEMA
            or set(receipt) != expected_receipt_keys
            or receipt.get("session_id") != expected_id
            or receipt.get("request_sha256") != request_sha
            or receipt.get("context_sha256") != context_sha
            or receipt.get("manifest_sha256") != manifest_sha
            or receipt.get("index_id") != manifest.get("index_id")
            or receipt.get("intent_sha256") != intent_sha
            or receipt.get("document_sha256") != intent.get("document_sha256")
            or receipt.get("output_path") != intent.get("output_path")
            or receipt.get("output_sha256") != intent.get("output_sha256")
        ):
            return {
                "ok": False,
                "state": STATE_NEEDS_ATTENTION,
                "diagnostics": [
                    {
                        "relative_path": RECEIPT_NAME,
                        "code": LIGHT_SESSION_INVALID,
                        "message": "completion receipt bindings are invalid",
                    }
                ],
            }

    return {
        "ok": True,
        "state": STATE_AWAITING,
        "diagnostics": [],
        "session_id": expected_id,
        "request": request,
        "context": context,
        "manifest": manifest,
        "request_sha256": request_sha,
        "context_sha256": context_sha,
        "manifest_sha256": manifest_sha,
        "intent": intent,
        "intent_sha256": intent_sha,
        "receipt": receipt,
        "receipt_sha256": receipt_sha,
        "session_dir": session_dir,
    }


def _output_file_state(path_text: str, expected_sha256: str) -> str:
    path = Path(path_text)
    if path.is_symlink():
        return "mismatch"
    if not path.exists():
        return "missing"
    if not path.is_file():
        return "mismatch"
    actual = sha256_bytes(path.read_bytes())
    if actual != expected_sha256:
        return "mismatch"
    return "match"


def _live_status(backend: WorkflowBackend, workspace: Path, context: Mapping[str, Any]) -> dict[str, Any]:
    try:
        result = backend.validate_live_context(workspace, context)
    except ResearchError as exc:
        return {"ok": False, "status": exc.code, "message": exc.message}
    if type(result) is not dict:
        return {"ok": False, "status": LIGHT_CONTEXT_INVALID, "message": "live context validation did not return an object"}
    return result


def _decide_state(validated: Mapping[str, Any], live: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    diagnostics = list(validated.get("diagnostics") or [])
    if not validated.get("ok"):
        return STATE_NEEDS_ATTENTION, diagnostics, [NEXT_INSPECT]
    live_ok = live.get("ok") is True and live.get("status") == OK
    intent = validated.get("intent")
    receipt = validated.get("receipt")
    if receipt is not None:
        output_state = _output_file_state(str(receipt["output_path"]), str(receipt["output_sha256"]))
        if output_state != "match":
            diagnostics.append(
                {
                    "relative_path": str(receipt["output_path"]),
                    "code": LIGHT_SESSION_INVALID,
                    "message": "completed output is missing, not regular, or no longer matches the receipt",
                }
            )
            return STATE_NEEDS_ATTENTION, diagnostics, [NEXT_INSPECT]
        if not live_ok:
            return STATE_STALE, diagnostics, [NEXT_REPREPARE]
        return STATE_COMPLETE, diagnostics, []
    if intent is not None:
        output_state = _output_file_state(str(intent["output_path"]), str(intent["output_sha256"]))
        if output_state == "mismatch":
            diagnostics.append(
                {
                    "relative_path": str(intent["output_path"]),
                    "code": LIGHT_SESSION_CONFLICT,
                    "message": "existing output does not match the validated completion intent",
                }
            )
            return STATE_NEEDS_ATTENTION, diagnostics, [NEXT_INSPECT]
        if not live_ok:
            return STATE_STALE, diagnostics, [NEXT_REPREPARE, NEXT_RETRY_COMPLETE]
        return STATE_AWAITING, diagnostics, [NEXT_RETRY_COMPLETE]
    if not live_ok:
        return STATE_STALE, diagnostics, [NEXT_REPREPARE]
    return STATE_AWAITING, diagnostics, [NEXT_READ_CONTEXT, NEXT_COMPLETE]


def _session_paths(session_dir: Path) -> dict[str, str]:
    return {
        "context_path": str((session_dir / CONTEXT_NAME).resolve()) if _is_regular_file(session_dir / CONTEXT_NAME) else str(session_dir / CONTEXT_NAME),
        "request_path": str((session_dir / REQUEST_NAME).resolve()) if _is_regular_file(session_dir / REQUEST_NAME) else str(session_dir / REQUEST_NAME),
        "manifest_path": str((session_dir / MANIFEST_NAME).resolve()) if _is_regular_file(session_dir / MANIFEST_NAME) else str(session_dir / MANIFEST_NAME),
    }


def _inspect_staging(workspace: Path) -> list[dict[str, Any]]:
    unsafe = _workflow_state_diagnostics(workspace)
    if unsafe:
        return unsafe
    root = _staging_root(workspace)
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        return [
            {
                "relative_path": f"{WORKFLOW_DIRNAME}/{STAGING_DIRNAME}",
                "code": LIGHT_SESSION_INVALID,
                "message": "workflow staging path is not a regular directory",
            }
        ]
    rows: list[dict[str, Any]] = []
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        rel = f"{WORKFLOW_DIRNAME}/{STAGING_DIRNAME}/{item.name}"
        if item.is_symlink() or not item.is_dir():
            rows.append({"relative_path": rel, "code": LIGHT_SESSION_INVALID, "message": "unknown staging entry"})
            continue
        marker = _load_persisted_object(item / OWNERSHIP_NAME)
        if marker is None:
            rows.append({"relative_path": rel, "code": LIGHT_SESSION_INVALID, "message": "unknown staging entry"})
            continue
        ownership = marker[0]
        owned = ownership.get("owned_names")
        if (
            ownership.get("schema") != STAGING_SCHEMA
            or type(ownership.get("session_id")) is not str
            or type(owned) is not list
            or any(type(name) is not str for name in owned)
        ):
            rows.append({"relative_path": rel, "code": LIGHT_SESSION_INVALID, "message": "unknown staging entry"})
            continue
        names = set(_entry_names(item) or [])
        expected = set(owned) | {OWNERSHIP_NAME}
        if names != expected:
            rows.append(
                {
                    "relative_path": rel,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "abandoned staging has extra or missing owned names",
                }
            )
            continue
        rows.append(
            {
                "relative_path": rel,
                "code": "LIGHT_STAGING_ABANDONED",
                "message": "recognized abandoned workflow staging",
                "session_id": ownership.get("session_id"),
            }
        )
    return rows


def _recover_owned_staging(workspace: Path, session_id: str, owned_names: set[str]) -> None:
    root = _staging_root(workspace)
    if not _is_regular_dir(root):
        return
    for item in list(root.iterdir()):
        if item.is_symlink() or not item.is_dir():
            continue
        marker = _load_persisted_object(item / OWNERSHIP_NAME)
        if marker is None:
            continue
        ownership = marker[0]
        owned = ownership.get("owned_names")
        if (
            ownership.get("schema") != STAGING_SCHEMA
            or ownership.get("session_id") != session_id
            or type(owned) is not list
            or set(owned) != owned_names
        ):
            continue
        names = set(_entry_names(item) or [])
        if names != (owned_names | {OWNERSHIP_NAME}):
            continue
        for name in list(owned_names) + [OWNERSHIP_NAME]:
            target = item / name
            if _is_regular_file(target):
                target.unlink()
        try:
            item.rmdir()
        except OSError:
            continue


def _publish_session(
    workspace: Path,
    session_id: str,
    request: dict[str, Any],
    context: dict[str, Any],
    manifest: dict[str, Any],
    backend: WorkflowBackend,
    _hook: Callable[[str], None] | None = None,
) -> Path:
    dest = _sessions_root(workspace) / session_id
    if dest.is_symlink() or _symlink_in_chain(dest, workspace):
        _fail(LIGHT_SESSION_INVALID, "session directory must not be a symlink")
    if dest.exists() or dest.is_symlink():
        return dest
    _assert_workflow_state_paths(workspace)
    staging_root = _staging_root(workspace)
    _ensure_regular_dir(staging_root, stop_at=workspace)
    _ensure_regular_dir(_sessions_root(workspace), stop_at=workspace)
    staged = Path(tempfile.mkdtemp(prefix=f"{session_id}-", dir=str(staging_root)))
    owned = [REQUEST_NAME, CONTEXT_NAME, MANIFEST_NAME]
    try:
        _write_persisted(
            staged / OWNERSHIP_NAME,
            {"owned_names": owned, "schema": STAGING_SCHEMA, "session_id": session_id},
        )
        _write_persisted(staged / REQUEST_NAME, request)
        _write_persisted(staged / CONTEXT_NAME, context)
        _write_persisted(staged / MANIFEST_NAME, manifest)
        names = set(_entry_names(staged) or [])
        if names != {OWNERSHIP_NAME, REQUEST_NAME, CONTEXT_NAME, MANIFEST_NAME}:
            _fail(LIGHT_SESSION_INVALID, "refusing to publish session with unexpected staging entries")
        live = _live_status(backend, workspace, context)
        if live.get("ok") is not True or live.get("status") != OK:
            status = str(live.get("status") or INDEX_STALE)
            raise _PublishRefused(status, str(live.get("message") or status))
        publish = staged / "session"
        publish.mkdir()
        for name in owned:
            (staged / name).replace(publish / name)
        if _hook is not None:
            _hook(HOOK_BEFORE_SESSION_PUBLISH)
        try:
            os.rename(publish, dest)
        except OSError:
            if dest.exists():
                if publish.exists():
                    for child in publish.iterdir():
                        if _is_regular_file(child):
                            child.unlink()
                    publish.rmdir()
            else:
                raise
        marker = staged / OWNERSHIP_NAME
        if _is_regular_file(marker):
            marker.unlink()
    finally:
        publish = staged / "session"
        if _is_regular_dir(publish) and not dest.exists():
            for name in owned:
                child = publish / name
                if _is_regular_file(child):
                    child.unlink()
            if list(publish.iterdir()) == []:
                try:
                    publish.rmdir()
                except OSError:
                    pass
        _recover_owned_staging(workspace, session_id, set(owned))
        if staged.exists() and _is_regular_dir(staged) and list(staged.iterdir()) == []:
            try:
                staged.rmdir()
            except OSError:
                pass
    return dest


def _install_session_file(
    workspace: Path,
    session_dir: Path,
    name: str,
    value: object,
    _hook: Callable[[str], None] | None = None,
) -> bytes:
    dest = session_dir / name
    encoded = persisted_bytes(value)
    if dest.exists() or dest.is_symlink():
        current = dest.read_bytes() if _is_regular_file(dest) else b""
        if current != encoded:
            _fail(LIGHT_SESSION_CONFLICT, f"{name} already exists and does not match the validated bytes")
        return encoded
    _assert_workflow_state_paths(workspace)
    staging_root = _staging_root(workspace)
    _ensure_regular_dir(staging_root, stop_at=workspace)
    leftover = staging_root / f".{session_dir.name}.{name}.tmp"
    if leftover.exists() or leftover.is_symlink():
        if leftover.is_symlink() or not leftover.is_file():
            _fail(LIGHT_SESSION_INVALID, "unrecognized workflow temporary path is unsafe")
    staged = Path(tempfile.mkdtemp(prefix=f"{session_dir.name}-{name}-", dir=str(staging_root)))
    try:
        _write_persisted(
            staged / OWNERSHIP_NAME,
            {"owned_names": [name], "schema": STAGING_SCHEMA, "session_id": session_dir.name},
        )
        tmp = staged / name
        tmp.write_bytes(encoded)
        names = set(_entry_names(staged) or [])
        if names != {OWNERSHIP_NAME, name}:
            _fail(LIGHT_SESSION_INVALID, "refusing to install a session file from unexpected staging entries")
        if _hook is not None:
            if name == INTENT_NAME:
                _hook(HOOK_AFTER_INTENT_STAGED)
            elif name == RECEIPT_NAME:
                _hook(HOOK_AFTER_RECEIPT_STAGED)
        tmp.replace(dest)
        marker = staged / OWNERSHIP_NAME
        if _is_regular_file(marker):
            marker.unlink()
    finally:
        _recover_owned_staging(workspace, session_dir.name, {name})
        if staged.exists() and _is_regular_dir(staged) and list(staged.iterdir()) == []:
            try:
                staged.rmdir()
            except OSError:
                pass
    return encoded


def _workspace_lock_path(workspace: Path) -> Path:
    return _locks_root(workspace) / "workspace.lock"


def _session_lock_path(workspace: Path, session_id: str) -> Path:
    return _locks_root(workspace) / f"{session_id}.lock"


def _busy_result(message: str, **extra: Any) -> dict[str, Any]:
    return _closed(status=LIGHT_WORKSPACE_BUSY, message=message, **extra)


def _index_if_needed(
    backend: WorkflowBackend,
    workspace: Path,
    *,
    added: bool,
    inspect: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    index_state = None if inspect is None else inspect.get("index_state")
    needs = added or index_state in {None, "missing", "stale"}
    if not needs:
        index_path = workspace / ".light-index" / "index.v1.json"
        needs = not _is_regular_file(index_path)
    if not needs:
        return None
    result = backend.build_index(workspace)
    if type(result) is not dict:
        _fail(INDEX_STALE, "index build did not return an object")
    return result


def _safe_inspect(backend: WorkflowBackend, workspace: Path) -> dict[str, Any] | None:
    try:
        result = backend.inspect_workspace(workspace)
    except ImportError:
        return None
    if type(result) is not dict:
        return None
    return result


def _prepare_additions(
    backend: WorkflowBackend,
    workspace: Path,
    pdf_paths: list[Path],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    additions: list[dict[str, Any]] = []
    for pdf_path in pdf_paths:
        try:
            added = backend.extract_pdf(pdf_path, workspace)
        except ResearchError as exc:
            return additions, _closed(
                status=exc.code,
                message=exc.message,
                session_id=None,
                additions=additions,
            )
        if type(added) is not dict:
            return additions, _closed(
                status=LIGHT_SESSION_INVALID,
                message="PDF add did not return an object",
                session_id=None,
                additions=additions,
            )
        additions.append(added)
        if added.get("ok") is not True:
            return additions, _closed(
                status=str(added.get("status") or LIGHT_SESSION_INVALID),
                message=str(added.get("message") or "PDF add failed"),
                session_id=None,
                additions=additions,
            )
    return additions, None


def _export_and_validate(
    backend: WorkflowBackend,
    workspace: Path,
    *,
    kind: str,
    query: str,
    requirements: str,
    selected_paper_ids: list[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    exported = backend.export_context(
        workspace,
        kind=kind,
        query=query,
        requirements=requirements,
        paper_ids=selected_paper_ids or None,
    )
    if type(exported) is not dict:
        return None, _closed(status=LIGHT_CONTEXT_INVALID, message="export_context did not return an object", session_id=None)
    if exported.get("ok") is not True:
        status = str(exported.get("status") or LIGHT_CONTEXT_INVALID)
        extra: dict[str, Any] = {"session_id": None, "context": exported}
        if status in CLOSED_NO_SESSION:
            extra["next_actions"] = [NEXT_NO_EVIDENCE]
        return None, _closed(
            status=status,
            message=str(exported.get("message") or status),
            **extra,
        )
    live = _live_status(backend, workspace, exported)
    if live.get("ok") is not True or live.get("status") != OK:
        status = str(live.get("status") or LIGHT_CONTEXT_INVALID)
        extra = {"session_id": None, "context": exported}
        if status in CLOSED_NO_SESSION:
            extra["next_actions"] = [NEXT_NO_EVIDENCE]
        return None, _closed(status=status, message=str(live.get("message") or status), **extra)
    return exported, None


def _detail_payload(
    *,
    workspace: Path,
    session_dir: Path,
    validated: Mapping[str, Any],
    state: str,
    diagnostics: list[dict[str, Any]],
    next_actions: list[str],
    reused: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "status": OK,
        "schema": WORKFLOW_SCHEMA,
        "session_id": session_dir.name,
        "state": state,
        "workspace_root": str(workspace),
        "diagnostics": diagnostics,
        "next_actions": next_actions,
        "message": f"workflow session is {state}",
    }
    payload.update(_session_paths(session_dir))
    if validated.get("ok"):
        payload["context"] = validated["context"]
        payload["index_id"] = validated["manifest"].get("index_id")
        payload["request_sha256"] = validated["request_sha256"]
        payload["context_sha256"] = validated["context_sha256"]
        payload["manifest_sha256"] = validated["manifest_sha256"]
        intent = validated.get("intent")
        receipt = validated.get("receipt")
        if intent is not None:
            payload["document_sha256"] = intent["document_sha256"]
            payload["output_path"] = intent["output_path"]
            payload["output_sha256"] = intent["output_sha256"]
            payload["intent_sha256"] = validated.get("intent_sha256")
        if receipt is not None:
            payload["path"] = receipt["output_path"]
            payload["output_sha256"] = receipt["output_sha256"]
            payload["receipt_sha256"] = validated.get("receipt_sha256")
    if reused is not None:
        payload["reused"] = reused
    return payload


def prepare_workflow(
    workspace_root: Path,
    *,
    kind: str,
    query: str,
    requirements: str = "",
    paper_ids: list[str] | None = None,
    pdf_paths: list[Path] | None = None,
    _backend: WorkflowBackend | None = None,
    _hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    backend = _select_backend(_backend)
    kind_value = _normalize_kind(kind)
    query_value = _normalize_query(query)
    requirements_value = _normalize_requirements(requirements)
    selected = normalize_selected_paper_ids(paper_ids)
    pdfs = _normalize_pdf_paths(pdf_paths)
    raw_workspace = _as_path(workspace_root, "workspace_root")
    exists = raw_workspace.exists()
    if exists:
        workspace = _resolve_existing_dir(raw_workspace)
    else:
        if not pdfs:
            return _closed(
                status=WORKSPACE_INVALID,
                message="workspace_root does not exist",
                session_id=None,
            )
        raw_workspace.mkdir(parents=True, exist_ok=True)
        workspace = _resolve_existing_dir(raw_workspace)

    additions, failed = _prepare_additions(backend, workspace, pdfs)
    if failed is not None:
        failed["additions"] = additions
        return failed

    inspect = _safe_inspect(backend, workspace)
    try:
        _assert_workflow_state_paths(workspace)
        with _exclusive_lock(_workspace_lock_path(workspace), workspace):
            index_result = _index_if_needed(backend, workspace, added=bool(additions), inspect=inspect)
            if index_result is not None and index_result.get("ok") is not True:
                return _closed(
                    status=str(index_result.get("status") or INDEX_STALE),
                    message=str(index_result.get("message") or "index build failed"),
                    session_id=None,
                    additions=additions,
                    index=index_result,
                )
            exported, export_error = _export_and_validate(
                backend,
                workspace,
                kind=kind_value,
                query=query_value,
                requirements=requirements_value,
                selected_paper_ids=selected,
            )
            if export_error is not None:
                export_error["additions"] = additions
                if index_result is not None:
                    export_error["index"] = index_result
                return export_error
            assert exported is not None
            request = build_request(
                workspace_root=workspace,
                kind=kind_value,
                query=query_value,
                requirements=requirements_value,
                selected_paper_ids=selected,
            )
            request_sha = sha256_persisted(request)
            context_sha = sha256_persisted(exported)
            session_id = session_identity(request_sha, context_sha)
            manifest = build_manifest(
                session_id=session_id,
                workspace_root=workspace,
                index_id=exported.get("index_id"),
                request_sha256=request_sha,
                context_sha256=context_sha,
            )
            dest = _sessions_root(workspace) / session_id
            if dest.is_symlink() or _symlink_in_chain(dest, workspace):
                return _closed(
                    status=LIGHT_SESSION_INVALID,
                    message="session directory must not be a symlink",
                    session_id=None,
                    additions=additions,
                )
            reused = dest.exists()
            if not reused:
                dest = _publish_session(
                    workspace,
                    session_id,
                    request,
                    exported,
                    manifest,
                    backend,
                    _hook=_hook,
                )
            validated = _validate_loaded_session(workspace, dest)
            live = (
                _live_status(backend, workspace, validated["context"])
                if validated.get("ok")
                else {"ok": False, "status": LIGHT_SESSION_INVALID, "message": "session is damaged"}
            )
            state, diagnostics, next_actions = _decide_state(validated, live)
            payload = _detail_payload(
                workspace=workspace,
                session_dir=dest,
                validated=validated,
                state=state,
                diagnostics=diagnostics,
                next_actions=next_actions,
                reused=reused,
            )
            payload["additions"] = additions
            if index_result is not None:
                payload["index"] = index_result
            if validated.get("ok"):
                payload["context"] = validated["context"]
            else:
                payload["context"] = exported
            return payload
    except _Busy:
        return _busy_result("another workflow prepare holds the workspace lock", session_id=None, additions=additions)
    except _PublishRefused as exc:
        return _closed(status=exc.status, message=exc.message, session_id=None, additions=additions)
    except ResearchError as exc:
        if exc.code in {LIGHT_SESSION_INVALID, WORKSPACE_INVALID}:
            return _closed(status=exc.code, message=exc.message, session_id=None, additions=additions)
        raise


def _status_missing_workspace(workspace: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "status": OK,
        "schema": WORKFLOW_SCHEMA,
        "workspace_root": str(workspace),
        "sessions": [],
        "diagnostics": [
            {
                "relative_path": str(workspace),
                "code": "WORKSPACE_MISSING",
                "message": "workspace does not exist",
            }
        ],
        "next_actions": [],
        "message": "workspace does not exist",
    }


def _list_session_rows(workspace: Path, backend: WorkflowBackend) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics = _inspect_staging(workspace)
    if any(row.get("relative_path") == WORKFLOW_DIRNAME for row in diagnostics):
        return [], diagnostics
    root = _sessions_root(workspace)
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows, diagnostics
    if root.is_symlink() or not root.is_dir():
        diagnostics.append(
            {
                "relative_path": f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}",
                "code": LIGHT_SESSION_INVALID,
                "message": "sessions path is not a regular directory",
            }
        )
        return rows, diagnostics
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        rel = f"{WORKFLOW_DIRNAME}/{SESSIONS_DIRNAME}/{item.name}"
        if item.is_symlink() or not item.is_dir() or not HEX64.fullmatch(item.name):
            diagnostics.append(
                {
                    "relative_path": rel,
                    "code": LIGHT_SESSION_INVALID,
                    "message": "unknown session entry",
                }
            )
            continue
        try:
            if item.resolve().parent != root.resolve() or item.resolve().name != item.name:
                diagnostics.append(
                    {
                        "relative_path": rel,
                        "code": LIGHT_SESSION_INVALID,
                        "message": "unknown session entry",
                    }
                )
                continue
        except OSError:
            diagnostics.append(
                {"relative_path": rel, "code": LIGHT_SESSION_INVALID, "message": "unknown session entry"}
            )
            continue
        validated = _validate_loaded_session(workspace, item)
        live = (
            _live_status(backend, workspace, validated["context"])
            if validated.get("ok")
            else {"ok": False, "status": LIGHT_SESSION_INVALID, "message": "session is damaged"}
        )
        state, session_diagnostics, next_actions = _decide_state(validated, live)
        diagnostics.extend(session_diagnostics)
        row = {
            "session_id": item.name,
            "state": state,
            "next_actions": next_actions,
        }
        if validated.get("ok"):
            row["index_id"] = validated["manifest"].get("index_id")
            row["kind"] = validated["request"].get("kind")
        rows.append(row)
    rows.sort(key=lambda item: item["session_id"])
    return rows, diagnostics


def workflow_status(
    workspace_root: Path,
    *,
    session_id: str | None = None,
    _backend: WorkflowBackend | None = None,
) -> dict[str, Any]:
    backend = _select_backend(_backend)
    raw = _as_path(workspace_root, "workspace_root")
    if not raw.exists():
        if session_id is not None:
            _require_session_id(session_id)
            return _closed(
                status=LIGHT_SESSION_INVALID,
                message="session does not exist",
                session_id=session_id,
            )
        return _status_missing_workspace(Path(os.path.normpath(raw.expanduser())))
    workspace = _resolve_existing_dir(raw)
    if session_id is None:
        inspect = _safe_inspect(backend, workspace)
        rows, diagnostics = _list_session_rows(workspace, backend)
        payload: dict[str, Any] = {
            "ok": True,
            "status": OK,
            "schema": WORKFLOW_SCHEMA,
            "workspace_root": str(workspace),
            "sessions": rows,
            "diagnostics": diagnostics,
            "next_actions": [],
            "message": "listed workflow sessions",
        }
        if inspect is not None:
            payload["workspace"] = inspect
        return payload
    ident = _require_session_id(session_id)
    path = _session_dir(workspace, ident)
    if not path.exists():
        return _closed(status=LIGHT_SESSION_INVALID, message="session does not exist", session_id=ident)
    validated = _validate_loaded_session(workspace, path)
    live = (
        _live_status(backend, workspace, validated["context"])
        if validated.get("ok")
        else {"ok": False, "status": LIGHT_SESSION_INVALID, "message": "session is damaged"}
    )
    state, diagnostics, next_actions = _decide_state(validated, live)
    diagnostics.extend(_inspect_staging(workspace))
    return _detail_payload(
        workspace=workspace,
        session_dir=path,
        validated=validated,
        state=state,
        diagnostics=diagnostics,
        next_actions=next_actions,
    )


def _require_document(document: object) -> dict[str, Any]:
    if type(document) is not dict:
        _fail(LIGHT_SESSION_INVALID, "document must be an object")
    return document


def _intent_object(
    *,
    session_id: str,
    context_sha256: str,
    document_sha256: str,
    output_path: Path,
    output_sha256: str,
) -> dict[str, Any]:
    return {
        "context_sha256": context_sha256,
        "document_sha256": document_sha256,
        "output_path": str(output_path),
        "output_sha256": output_sha256,
        "schema": INTENT_SCHEMA,
        "session_id": session_id,
    }


def _receipt_object(
    *,
    session_id: str,
    request_sha256: str,
    context_sha256: str,
    manifest_sha256: str,
    index_id: object,
    intent_sha256: str,
    document_sha256: str,
    output_path: Path,
    output_sha256: str,
) -> dict[str, Any]:
    return {
        "context_sha256": context_sha256,
        "document_sha256": document_sha256,
        "index_id": index_id,
        "intent_sha256": intent_sha256,
        "manifest_sha256": manifest_sha256,
        "output_path": str(output_path),
        "output_sha256": output_sha256,
        "request_sha256": request_sha256,
        "schema": RECEIPT_SCHEMA,
        "session_id": session_id,
    }


def _complete_success(
    *,
    session_id: str,
    output_path: Path,
    output_sha256: str,
    reused: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "status": OK,
        "state": STATE_COMPLETE,
        "session_id": session_id,
        "path": str(output_path),
        "output_sha256": output_sha256,
        "reused": reused,
        "message": "workflow output is complete",
    }


def complete_workflow(
    workspace_root: Path,
    session_id: str,
    document: object,
    *,
    output: Path,
    _backend: WorkflowBackend | None = None,
    _hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    backend = _select_backend(_backend)
    workspace = _workspace_path(workspace_root)
    if not workspace.exists():
        _fail(WORKSPACE_INVALID, "workspace_root does not exist")
    workspace = _resolve_existing_dir(workspace)
    ident = _require_session_id(session_id)
    output_path = _absolute_output(output)
    model_document = _require_document(document)
    document_sha = sha256_canonical(model_document)

    def fire(name: str) -> None:
        if _hook is not None:
            _hook(name)

    try:
        with _exclusive_lock(_session_lock_path(workspace, ident), workspace):
            path = _session_dir(workspace, ident)
            if not path.exists():
                return _closed(status=LIGHT_SESSION_INVALID, message="session does not exist", session_id=ident)
            validated = _validate_loaded_session(workspace, path)
            if not validated.get("ok"):
                return _closed(
                    status=LIGHT_SESSION_INVALID,
                    message="session is damaged and cannot be completed",
                    session_id=ident,
                    diagnostics=validated.get("diagnostics") or [],
                )
            live = _live_status(backend, workspace, validated["context"])
            if live.get("ok") is not True or live.get("status") != OK:
                status = str(live.get("status") or LIGHT_CONTEXT_INVALID)
                return _closed(
                    status=status,
                    message=str(live.get("message") or status),
                    session_id=ident,
                )
            try:
                rendered = backend.render_document(
                    workspace,
                    validated["context"],
                    model_document,
                    output=output_path,
                )
            except ResearchError as exc:
                return _closed(status=exc.code, message=exc.message, session_id=ident)
            if type(rendered) is not dict or rendered.get("ok") is not True:
                status = str((rendered or {}).get("status") or LIGHT_SESSION_INVALID)
                return _closed(
                    status=status,
                    message=str((rendered or {}).get("message") or "model document failed validation"),
                    session_id=ident,
                )
            output_sha = rendered.get("output_sha256")
            if type(output_sha) is not str or not HEX64.fullmatch(output_sha):
                markdown = rendered.get("markdown")
                if type(markdown) is not str:
                    return _closed(
                        status=LIGHT_SESSION_INVALID,
                        message="render_document did not return output bytes",
                        session_id=ident,
                    )
                output_sha = sha256_bytes(markdown.encode("utf-8"))
            expected_intent = _intent_object(
                session_id=ident,
                context_sha256=validated["context_sha256"],
                document_sha256=document_sha,
                output_path=output_path,
                output_sha256=output_sha,
            )
            existing_intent = validated.get("intent")
            existing_receipt = validated.get("receipt")
            if existing_intent is not None and existing_intent != expected_intent:
                return _closed(
                    status=LIGHT_SESSION_CONFLICT,
                    message="completion document or output diverges from the persisted intent",
                    session_id=ident,
                )
            if existing_receipt is not None:
                expected_receipt = _receipt_object(
                    session_id=ident,
                    request_sha256=validated["request_sha256"],
                    context_sha256=validated["context_sha256"],
                    manifest_sha256=validated["manifest_sha256"],
                    index_id=validated["manifest"].get("index_id"),
                    intent_sha256=validated["intent_sha256"],
                    document_sha256=document_sha,
                    output_path=output_path,
                    output_sha256=output_sha,
                )
                if existing_receipt != expected_receipt:
                    return _closed(
                        status=LIGHT_SESSION_CONFLICT,
                        message="completion document or output diverges from the persisted receipt",
                        session_id=ident,
                    )
                if _output_file_state(str(output_path), output_sha) != "match":
                    return _closed(
                        status=LIGHT_SESSION_CONFLICT,
                        message="completed output no longer matches the receipt",
                        session_id=ident,
                    )
                return _complete_success(
                    session_id=ident,
                    output_path=output_path,
                    output_sha256=output_sha,
                    reused=True,
                )
            if existing_intent is None and output_path.exists():
                return _closed(
                    status=LIGHT_OUTPUT_CONFLICT,
                    message="output exists without a matching completion intent",
                    session_id=ident,
                )
            if existing_intent is not None:
                output_state = _output_file_state(str(existing_intent["output_path"]), str(existing_intent["output_sha256"]))
                if output_state == "mismatch":
                    return _closed(
                        status=LIGHT_SESSION_CONFLICT,
                        message="existing output does not match the validated completion intent",
                        session_id=ident,
                    )
                if output_state == "match":
                    fire(HOOK_BEFORE_RECEIPT)
                    receipt = _receipt_object(
                        session_id=ident,
                        request_sha256=validated["request_sha256"],
                        context_sha256=validated["context_sha256"],
                        manifest_sha256=validated["manifest_sha256"],
                        index_id=validated["manifest"].get("index_id"),
                        intent_sha256=sha256_persisted(expected_intent),
                        document_sha256=document_sha,
                        output_path=output_path,
                        output_sha256=output_sha,
                    )
                    _install_session_file(workspace, path, RECEIPT_NAME, receipt, _hook=fire)
                    return _complete_success(
                        session_id=ident,
                        output_path=output_path,
                        output_sha256=output_sha,
                        reused=True,
                    )
            _install_session_file(workspace, path, INTENT_NAME, expected_intent, _hook=fire)
            fire(HOOK_AFTER_INTENT)
            try:
                imported = backend.import_document(
                    workspace,
                    validated["context"],
                    model_document,
                    output=output_path,
                    overwrite=False,
                )
            except ResearchError as exc:
                return _closed(status=exc.code, message=exc.message, session_id=ident)
            if type(imported) is not dict or imported.get("ok") is not True:
                status = str((imported or {}).get("status") or LIGHT_SESSION_INVALID)
                return _closed(
                    status=status,
                    message=str((imported or {}).get("message") or "output installation failed"),
                    session_id=ident,
                )
            installed_sha = imported.get("output_sha256") or output_sha
            if installed_sha != output_sha or _output_file_state(str(output_path), output_sha) != "match":
                return _closed(
                    status=LIGHT_SESSION_CONFLICT,
                    message="installed output does not match the validated intent",
                    session_id=ident,
                )
            fire(HOOK_AFTER_OUTPUT)
            fire(HOOK_BEFORE_RECEIPT)
            receipt = _receipt_object(
                session_id=ident,
                request_sha256=validated["request_sha256"],
                context_sha256=validated["context_sha256"],
                manifest_sha256=validated["manifest_sha256"],
                index_id=validated["manifest"].get("index_id"),
                intent_sha256=sha256_persisted(expected_intent),
                document_sha256=document_sha,
                output_path=output_path,
                output_sha256=output_sha,
            )
            _install_session_file(workspace, path, RECEIPT_NAME, receipt, _hook=fire)
            return _complete_success(
                session_id=ident,
                output_path=output_path,
                output_sha256=output_sha,
                reused=False,
            )
    except _Busy:
        return _busy_result("another complete_workflow holds the session lock", session_id=ident)
    except ResearchError as exc:
        if exc.code in {LIGHT_SESSION_CONFLICT, LIGHT_SESSION_INVALID, LIGHT_OUTPUT_CONFLICT, WORKSPACE_INVALID}:
            return _closed(status=exc.code, message=exc.message, session_id=ident)
        raise
