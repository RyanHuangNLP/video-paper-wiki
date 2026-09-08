"""Agent-safe vpwiki-research CLI. No network, no vpwiki-admin, no Vault writes."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.identity import IdentityError
from video_paper_wiki.jcs import CanonicalJsonError
from video_paper_wiki.secure_io import SecureIOError, read_regular_file
from video_paper_wiki.staging import StagingError

from video_paper_wiki_research.contracts import JSON_MAX_BYTES, JSON_MAX_DEPTH, ResearchError, _json_depth
from video_paper_wiki_research.manual_pdf import intake_pdf, plan_handoff
from video_paper_wiki_research.source_context import analyze_proposal, build_context
from video_paper_wiki_research.storage import open_research_session, session_from_research_path

LIGHT_CONTEXT_SCHEMA = "video-paper-wiki.light-context.v1"
_OLD_EXPORT_FLAGS = ("vault_root", "upstream_root", "config")
_MD_SOURCE_LINK = re.compile(r"\]\((?:<)?(papers/[0-9a-f]{64}/source\.md#page-\d+)(?:>)?\)")
_TICK_SOURCE_LINK = re.compile(r"`(papers/[0-9a-f]{64}/source\.md#page-\d+)`")


class UsageError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _JsonArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> None:
        raise UsageError(message)

    def add_subparsers(self, **kwargs):
        kwargs["parser_class"] = type(self)
        return super().add_subparsers(**kwargs)


def _command_from_argv(args: list[str]) -> str:
    parts: list[str] = []
    for token in args:
        if token.startswith("-"):
            continue
        parts.append(token)
        if len(parts) >= 2:
            break
    return ".".join(parts) if parts else "vpwiki-research"


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="vpwiki-research", add_help=True, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command")
    pdf = sub.add_parser("pdf", allow_abbrev=False)
    pdf_sub = pdf.add_subparsers(dest="pdf_cmd", required=True)

    intake = pdf_sub.add_parser("intake", allow_abbrev=False)
    intake.add_argument("--pdf", required=True)
    intake.add_argument("--session", required=True)
    intake.add_argument("--paper-id", dest="paper_id", default=None)
    intake.set_defaults(handler=_cmd_intake)

    plan = pdf_sub.add_parser("plan", allow_abbrev=False)
    plan.add_argument("--intake", required=True)
    plan.add_argument("--profile", required=True)
    plan.add_argument("--batch-id", dest="batch_id", required=True)
    plan.set_defaults(handler=_cmd_plan)

    context = pdf_sub.add_parser("context", allow_abbrev=False)
    context.add_argument("--intake", required=True)
    context.add_argument("--profile", required=True)
    context.add_argument("--run", required=True)
    context.add_argument("--upstream-root", dest="upstream_root", required=True)
    context.add_argument("--session", required=True)
    context.set_defaults(handler=_cmd_context)

    analyze = pdf_sub.add_parser("analyze", allow_abbrev=False)
    analyze.add_argument("--context", required=True)
    analyze.add_argument("--proposal", required=True)
    analyze.add_argument("--upstream-root", dest="upstream_root", required=True)
    analyze.add_argument("--session", required=True)
    analyze.set_defaults(handler=_cmd_analyze)

    pdf_add = pdf_sub.add_parser("add", allow_abbrev=False)
    pdf_add.add_argument("--pdf", required=True)
    pdf_add.add_argument("--workspace", required=True)
    pdf_add.add_argument("--title", default=None)
    pdf_add.set_defaults(handler=_cmd_pdf_add)

    index = sub.add_parser("index", allow_abbrev=False)
    index_sub = index.add_subparsers(dest="index_cmd", required=True)
    index_build = index_sub.add_parser("build", allow_abbrev=False)
    index_build.add_argument("--workspace", required=True)
    index_build.set_defaults(handler=_cmd_index_build)

    qa = sub.add_parser("qa", allow_abbrev=False)
    qa_sub = qa.add_subparsers(dest="qa_cmd", required=True)
    qa_export = qa_sub.add_parser("export", allow_abbrev=False)
    qa_export.add_argument("--question", required=True)
    qa_export.add_argument("--paper-id", dest="paper_ids", action="append", default=None)
    qa_export.add_argument("--workspace", default=None)
    qa_export.add_argument("--vault-root", dest="vault_root", default=None)
    qa_export.add_argument("--upstream-root", dest="upstream_root", default=None)
    qa_export.add_argument("--config", default=None)
    qa_export.set_defaults(handler=_cmd_qa_export)
    qa_import = qa_sub.add_parser("import", allow_abbrev=False)
    qa_import.add_argument("--context", required=True)
    qa_import.add_argument("--answer", required=True)
    qa_import.add_argument("--output", default=None)
    qa_import.add_argument("--workspace", default=None)
    qa_import.set_defaults(handler=_cmd_qa_import)

    writing = sub.add_parser("writing", allow_abbrev=False)
    writing_sub = writing.add_subparsers(dest="writing_cmd", required=True)
    writing_export = writing_sub.add_parser("export", allow_abbrev=False)
    writing_export.add_argument("--topic", required=True)
    writing_export.add_argument("--requirements", required=True)
    writing_export.add_argument("--paper-id", dest="paper_ids", action="append", default=None)
    writing_export.add_argument("--workspace", default=None)
    writing_export.add_argument("--vault-root", dest="vault_root", default=None)
    writing_export.add_argument("--upstream-root", dest="upstream_root", default=None)
    writing_export.add_argument("--config", default=None)
    writing_export.set_defaults(handler=_cmd_writing_export)
    writing_import = writing_sub.add_parser("import", allow_abbrev=False)
    writing_import.add_argument("--context", required=True)
    writing_import.add_argument("--draft", required=True)
    writing_import.add_argument("--output", default=None)
    writing_import.add_argument("--workspace", default=None)
    writing_import.set_defaults(handler=_cmd_writing_import)

    workspace = sub.add_parser("workspace", allow_abbrev=False)
    workspace_sub = workspace.add_subparsers(dest="workspace_cmd", required=True)
    inspect = workspace_sub.add_parser("inspect", allow_abbrev=False)
    inspect.add_argument("--workspace", required=True)
    inspect.set_defaults(handler=_cmd_workspace_inspect)

    workflow = sub.add_parser("workflow", allow_abbrev=False)
    workflow_sub = workflow.add_subparsers(dest="workflow_cmd", required=True)
    prepare = workflow_sub.add_parser("prepare", allow_abbrev=False)
    prepare.add_argument("--workspace", required=True)
    prepare.add_argument("--kind", required=True, choices=("qa", "writing"))
    prepare.add_argument("--query", required=True)
    prepare.add_argument("--requirements", default="")
    prepare.add_argument("--paper-id", dest="paper_ids", action="append", default=None)
    prepare.add_argument("--pdf", dest="pdf_paths", action="append", default=None)
    prepare.set_defaults(handler=_cmd_workflow_prepare)
    status = workflow_sub.add_parser("status", allow_abbrev=False)
    status.add_argument("--workspace", required=True)
    status.add_argument("--session-id", dest="session_id", default=None)
    status.set_defaults(handler=_cmd_workflow_status)
    complete = workflow_sub.add_parser("complete", allow_abbrev=False)
    complete.add_argument("--workspace", required=True)
    complete.add_argument("--session-id", dest="session_id", required=True)
    complete.add_argument("--document", required=True)
    complete.add_argument("--output", required=True)
    complete.set_defaults(handler=_cmd_workflow_complete)

    library = sub.add_parser("library", allow_abbrev=False)
    library_sub = library.add_subparsers(dest="library_cmd", required=True)
    library_list = library_sub.add_parser("list", allow_abbrev=False)
    library_list.add_argument("--workspace", required=True)
    library_list.set_defaults(handler=_cmd_library_list)
    library_edit = library_sub.add_parser("edit", allow_abbrev=False)
    library_edit.add_argument("--workspace", required=True)
    library_edit.add_argument("--paper-id", dest="paper_id", required=True)
    library_edit.add_argument("--title", default=None)
    library_edit.add_argument("--tag", dest="tags", action="append", default=None)
    library_edit.add_argument("--clear-tags", dest="clear_tags", action="store_true")
    library_edit.set_defaults(handler=_cmd_library_edit)
    library_remove = library_sub.add_parser("remove", allow_abbrev=False)
    library_remove.add_argument("--workspace", required=True)
    library_remove.add_argument("--paper-id", dest="paper_id", required=True)
    library_remove.set_defaults(handler=_cmd_library_remove)
    library_restore = library_sub.add_parser("restore", allow_abbrev=False)
    library_restore.add_argument("--workspace", required=True)
    library_restore.add_argument("--archive-id", dest="archive_id", required=True)
    library_restore.set_defaults(handler=_cmd_library_restore)
    library_replace = library_sub.add_parser("replace", allow_abbrev=False)
    library_replace.add_argument("--workspace", required=True)
    library_replace.add_argument("--paper-id", dest="paper_id", required=True)
    library_replace.add_argument("--pdf", required=True)
    library_replace.add_argument("--title", default=None)
    library_replace.set_defaults(handler=_cmd_library_replace)
    library_recover = library_sub.add_parser("recover", allow_abbrev=False)
    library_recover.add_argument("--workspace", required=True)
    library_recover.add_argument("--operation-id", dest="operation_id", default=None)
    library_recover.set_defaults(handler=_cmd_library_recover)

    knowledge = sub.add_parser("knowledge", allow_abbrev=False)
    knowledge_sub = knowledge.add_subparsers(dest="knowledge_cmd", required=True)
    knowledge_export = knowledge_sub.add_parser("export", allow_abbrev=False)
    knowledge_export.add_argument("--workspace", required=True)
    knowledge_export.add_argument("--paper-id", dest="paper_id", required=True)
    knowledge_export.set_defaults(handler=_cmd_knowledge_export)
    knowledge_import = knowledge_sub.add_parser("import", allow_abbrev=False)
    knowledge_import.add_argument("--workspace", required=True)
    knowledge_import.add_argument("--context", required=True)
    knowledge_import.add_argument("--document", required=True)
    knowledge_import.set_defaults(handler=_cmd_knowledge_import)
    knowledge_list = knowledge_sub.add_parser("list", allow_abbrev=False)
    knowledge_list.add_argument("--workspace", required=True)
    knowledge_list.set_defaults(handler=_cmd_knowledge_list)
    knowledge_build = knowledge_sub.add_parser("build", allow_abbrev=False)
    knowledge_build.add_argument("--workspace", required=True)
    knowledge_build.set_defaults(handler=_cmd_knowledge_build)

    compare = sub.add_parser("compare", allow_abbrev=False)
    compare_sub = compare.add_subparsers(dest="compare_cmd", required=True)
    compare_export = compare_sub.add_parser("export", allow_abbrev=False)
    compare_export.add_argument("--workspace", required=True)
    compare_export.add_argument("--query", required=True)
    compare_export.add_argument("--paper-id", dest="paper_ids", action="append", required=True)
    compare_export.add_argument("--dimension", dest="dimensions", action="append", default=None)
    compare_export.set_defaults(handler=_cmd_compare_export)
    compare_import = compare_sub.add_parser("import", allow_abbrev=False)
    compare_import.add_argument("--workspace", required=True)
    compare_import.add_argument("--context", required=True)
    compare_import.add_argument("--document", required=True)
    compare_import.add_argument("--output", required=True)
    compare_import.set_defaults(handler=_cmd_compare_import)

    backup = sub.add_parser("backup", allow_abbrev=False)
    backup_sub = backup.add_subparsers(dest="backup_cmd", required=True)
    backup_create = backup_sub.add_parser("create", allow_abbrev=False)
    backup_create.add_argument("--workspace", required=True)
    backup_create.add_argument("--output", required=True)
    backup_create.add_argument("--include-output", dest="extra_outputs", action="append", default=None)
    backup_create.set_defaults(handler=_cmd_backup_create)
    backup_verify = backup_sub.add_parser("verify", allow_abbrev=False)
    backup_verify.add_argument("--archive", required=True)
    backup_verify.set_defaults(handler=_cmd_backup_verify)
    backup_restore = backup_sub.add_parser("restore", allow_abbrev=False)
    backup_restore.add_argument("--archive", required=True)
    backup_restore.add_argument("--destination", required=True)
    backup_restore.set_defaults(handler=_cmd_backup_restore)
    return parser


def _emit(command: str, exc: BaseException) -> int:
    if isinstance(exc, StagingError):
        return emit_staging_error(command, exc)
    if isinstance(exc, UsageError):
        return emit_error(command, "USAGE", exc.message)
    if isinstance(exc, ResearchError):
        return emit_error(command, exc.code, exc.message, exc.details, exit_code=exc.exit_code)
    if isinstance(exc, SecureIOError):
        return emit_error(command, exc.code, exc.message, dict(exc.details), exit_code=int(exc.exit_code))
    if isinstance(exc, (IdentityError, CanonicalJsonError)):
        return emit_error(
            command,
            str(getattr(exc, "code", "INTAKE_INVALID")),
            str(getattr(exc, "message", exc)),
            dict(getattr(exc, "details", {}) or {}),
            exit_code=int(getattr(exc, "exit_code", 2)),
        )
    return emit_error(command, "INTAKE_INVALID", str(exc))


def _load_light(module: str):
    name = f"video_paper_wiki_research.{module}"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name not in {name, module}:
            raise
        raise ResearchError(
            "LIGHT_MODULE_UNAVAILABLE",
            f"{module} is not integrated yet",
            {"module": module},
        ) from exc


def _workspace_root(raw: str, *, create: bool, allow_missing: bool = False) -> Path:
    given = Path(raw).expanduser()
    if ".work" not in given.parts:
        raise ResearchError(
            "WORKSPACE_INVALID",
            "workspace must be under .work/**",
            {"path": str(given)},
        )
    if create:
        given.mkdir(parents=True, exist_ok=True)
    resolved = given.resolve()
    if ".work" not in resolved.parts:
        raise ResearchError(
            "WORKSPACE_INVALID",
            "workspace must be under .work/**",
            {"path": str(resolved)},
        )
    if resolved.exists():
        if resolved.is_symlink() or not resolved.is_dir():
            raise ResearchError(
                "WORKSPACE_INVALID",
                "workspace must be a regular directory under .work/**",
                {"path": str(resolved)},
            )
        return resolved
    if allow_missing and not create:
        return resolved
    raise ResearchError(
        "WORKSPACE_INVALID",
        "workspace must be a regular directory under .work/**",
        {"path": str(resolved)},
    )


def _try_light_attr(module: str, attr: str):
    loaded = _load_light(module)
    func = getattr(loaded, attr, None)
    if callable(func):
        return func
    raise ResearchError(
        "LIGHT_MODULE_UNAVAILABLE",
        f"{module}.{attr} is not integrated yet",
        {"module": module, "attribute": attr},
    )


def _optional_light_attr(module: str, attr: str):
    try:
        return _try_light_attr(module, attr)
    except ResearchError as exc:
        if exc.code == "LIGHT_MODULE_UNAVAILABLE":
            return None
        raise


def _paper_ids_from_args(args: argparse.Namespace) -> list[str] | None:
    raw = getattr(args, "paper_ids", None)
    if raw is None:
        return None
    return list(raw)


def _pdf_paths_from_args(args: argparse.Namespace) -> list[Path] | None:
    raw = getattr(args, "pdf_paths", None)
    if raw is None:
        return None
    return [Path(item).expanduser() for item in raw]


def _old_export_values(args: argparse.Namespace) -> dict[str, str | None]:
    return {name: getattr(args, name, None) for name in _OLD_EXPORT_FLAGS}


def _reject_mixed_export(args: argparse.Namespace) -> None:
    workspace = getattr(args, "workspace", None)
    old = {name: value for name, value in _old_export_values(args).items() if value}
    if workspace and old:
        raise UsageError("do not combine --workspace with --vault-root/--upstream-root/--config")
    if workspace:
        return
    missing = [name for name in _OLD_EXPORT_FLAGS if not getattr(args, name, None)]
    if missing:
        raise UsageError("provide --workspace or the vault/config arguments")


def _read_json(path: str) -> dict[str, Any]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchError("LIGHT_HANDOFF_INVALID", "JSON is not readable", {"path": str(target)}) from exc
    if type(payload) is not dict:
        raise ResearchError("LIGHT_HANDOFF_INVALID", "JSON must be an object", {"path": str(target)})
    return payload


def _input_path_edges(given: Path) -> tuple[Path, ...]:
    if given.is_absolute():
        cursor = Path(given.anchor)
        edges = [cursor]
        for part in given.parts[1:]:
            cursor = cursor / part
            edges.append(cursor)
        return tuple(edges)
    cursor = Path()
    edges: list[Path] = []
    for part in given.parts:
        cursor = cursor / part
        edges.append(cursor)
    return tuple(edges)


def _reject_unsafe_input_edges(given: Path, *, code: str, label: str) -> None:
    """Refuse symlink/hardlink/non-regular edges before any resolve() sanitizing."""

    for edge in _input_path_edges(given):
        try:
            st = os.lstat(edge)
        except FileNotFoundError as exc:
            raise ResearchError(code, f"{label} is missing", {"path": str(given), "edge": str(edge)}) from exc
        except OSError as exc:
            raise ResearchError(code, f"{label} is not readable", {"path": str(given), "edge": str(edge)}) from exc
        if stat.S_ISLNK(st.st_mode):
            raise ResearchError(
                code,
                f"{label} path must not traverse a symlink",
                {"path": str(given), "edge": str(edge)},
            )
    try:
        st = os.lstat(given)
    except OSError as exc:
        raise ResearchError(code, f"{label} is not readable", {"path": str(given)}) from exc
    if not stat.S_ISREG(st.st_mode):
        raise ResearchError(code, f"{label} must be a regular file", {"path": str(given)})
    if int(st.st_nlink) != 1:
        raise ResearchError(
            code,
            f"{label} must not be a hardlink",
            {"path": str(given), "nlink": int(st.st_nlink)},
        )


def _read_safe_regular_bytes(
    raw: str,
    *,
    code: str,
    label: str,
    suffix: str | None = None,
    suffix_message: str | None = None,
) -> tuple[Path, bytes]:
    given = Path(raw).expanduser()
    if suffix and given.suffix.lower() != suffix.lower():
        raise ResearchError(
            code,
            suffix_message or f"{label} must use the {suffix} suffix",
            {"path": str(given)},
        )
    _reject_unsafe_input_edges(given, code=code, label=label)
    try:
        data = read_regular_file(
            given,
            missing_code=code,
            unsafe_code=code,
            changed_code=code,
            max_bytes=JSON_MAX_BYTES,
            limit_code=code,
        )
    except SecureIOError as exc:
        raise ResearchError(code, str(exc.message), dict(exc.details)) from exc
    except OSError as exc:
        raise ResearchError(code, f"{label} is not readable", {"path": str(given)}) from exc
    try:
        st = os.lstat(given)
    except OSError as exc:
        raise ResearchError(code, f"{label} is not readable", {"path": str(given)}) from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or int(st.st_nlink) != 1:
        raise ResearchError(code, f"{label} must be a regular file", {"path": str(given)})
    if len(data) > JSON_MAX_BYTES:
        raise ResearchError(
            code,
            f"{label} exceeds the 8 MiB limit",
            {"path": str(given), "size": len(data)},
        )
    return given, data


def _decode_strict_utf8(data: bytes, *, path: Path, code: str, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResearchError(code, f"{label} is not valid UTF-8", {"path": str(path)}) from exc


def _reject_nonfinite_json(value: Any, *, path: Path) -> None:
    pending: list[Any] = [value]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            pending.extend(current.values())
        elif type(current) is list:
            pending.extend(current)
        elif type(current) is float and not math.isfinite(current):
            raise ResearchError(
                "LIGHT_HANDOFF_INVALID",
                "JSON must not contain NaN or Infinity",
                {"path": str(path)},
            )


def _reject_oversized_json_integers(text: str, *, path: Path) -> None:
    limit = sys.get_int_max_str_digits()
    if limit <= 0:
        return
    run = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            run = 0
            continue
        if char == '"':
            in_string = True
            run = 0
            continue
        if char.isdigit():
            run += 1
            if run > limit:
                raise ResearchError(
                    "LIGHT_HANDOFF_INVALID",
                    "JSON integer exceeds the supported digit limit",
                    {"path": str(path), "digits": run},
                )
            continue
        run = 0


def _parse_library_json_object(data: bytes, *, path: Path) -> dict[str, Any]:
    text = _decode_strict_utf8(data, path=path, code="LIGHT_HANDOFF_INVALID", label="JSON input")
    if text.startswith("\ufeff"):
        raise ResearchError("LIGHT_HANDOFF_INVALID", "JSON must not contain a UTF-8 BOM", {"path": str(path)})

    def _reject_constant(_value: str) -> Any:
        raise ResearchError(
            "LIGHT_HANDOFF_INVALID",
            "JSON must not contain NaN or Infinity",
            {"path": str(path)},
        )

    def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ResearchError(
                    "LIGHT_HANDOFF_INVALID",
                    "JSON must not contain duplicate keys",
                    {"path": str(path)},
                )
            out[key] = value
        return out

    decoder = json.JSONDecoder(parse_constant=_reject_constant, object_pairs_hook=_no_duplicate_keys)
    stripped = text.lstrip(" \t\r\n")
    _json_depth(stripped, limit=JSON_MAX_DEPTH, code="LIGHT_HANDOFF_INVALID")
    _reject_oversized_json_integers(stripped, path=path)
    try:
        obj, index = decoder.raw_decode(stripped)
    except ResearchError:
        raise
    except RecursionError as exc:
        raise ResearchError(
            "LIGHT_HANDOFF_INVALID",
            "JSON nesting exceeds the supported limit",
            {"path": str(path)},
        ) from exc
    except json.JSONDecodeError as exc:
        raise ResearchError("LIGHT_HANDOFF_INVALID", "JSON is not readable", {"path": str(path)}) from exc
    except ValueError as exc:
        raise ResearchError("LIGHT_HANDOFF_INVALID", "JSON is not readable", {"path": str(path)}) from exc
    trailing = stripped[index:]
    if trailing.strip(" \t\r\n"):
        raise ResearchError("LIGHT_HANDOFF_INVALID", "JSON is not readable", {"path": str(path)})
    if type(obj) is not dict:
        raise ResearchError("LIGHT_HANDOFF_INVALID", "JSON must be an object", {"path": str(path)})
    try:
        _reject_nonfinite_json(obj, path=path)
    except RecursionError as exc:
        raise ResearchError(
            "LIGHT_HANDOFF_INVALID",
            "JSON nesting exceeds the supported limit",
            {"path": str(path)},
        ) from exc
    return obj


def _read_library_json(raw: str) -> dict[str, Any]:
    path, data = _read_safe_regular_bytes(raw, code="LIGHT_HANDOFF_INVALID", label="JSON input")
    return _parse_library_json_object(data, path=path)


def _is_light_context(document: dict[str, Any]) -> bool:
    return document.get("schema") == LIGHT_CONTEXT_SCHEMA


def _write_markdown(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path.resolve()


def _with_workspace_root(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    if payload.get("ok") is True and payload.get("schema") == LIGHT_CONTEXT_SCHEMA:
        payload = dict(payload)
        payload["workspace_root"] = str(workspace)
    return payload


def _resolve_import_workspace(args: argparse.Namespace, context: dict[str, Any]) -> Path:
    flagged = args.workspace
    stored = context.get("workspace_root")
    stored_path = Path(stored).expanduser() if type(stored) is str and stored.strip() else None
    if flagged and stored_path is not None:
        left = _workspace_root(flagged, create=False)
        right = _workspace_root(str(stored_path), create=False)
        if left != right:
            raise ResearchError(
                "LIGHT_WORKSPACE_MISMATCH",
                "--workspace does not match context workspace_root",
                {"workspace": str(left), "workspace_root": str(right)},
            )
        return left
    if flagged:
        return _workspace_root(flagged, create=False)
    if stored_path is not None:
        return _workspace_root(str(stored_path), create=False)
    raise ResearchError(
        "LIGHT_WORKSPACE_REQUIRED",
        "provide --workspace or re-export a context with workspace_root",
    )


def _display_source_href(workspace_href: str, *, workspace: Path, output_parent: Path) -> str:
    relative, anchor = workspace_href.split("#", 1)
    source = (workspace / relative).resolve()
    workspace = workspace.resolve()
    output_parent = output_parent.resolve()
    if not source.is_file():
        raise ResearchError("LIGHT_SOURCE_MISSING", "cited source.md is missing", {"path": str(source)})
    try:
        source.relative_to(workspace)
    except ValueError as exc:
        raise ResearchError(
            "LIGHT_SOURCE_MISSING",
            "cited source.md is outside the declared workspace",
            {"path": str(source), "workspace": str(workspace)},
        ) from exc
    text = source.read_text(encoding="utf-8")
    if f'id="{anchor}"' not in text:
        raise ResearchError(
            "LIGHT_ANCHOR_MISSING",
            "cited page anchor is missing from source.md",
            {"path": str(source), "anchor": anchor},
        )
    display = Path(os.path.relpath(source, output_parent)).as_posix()
    return f"{display}#{anchor}"


def _rewrite_markdown_links(markdown: str, *, workspace: Path, output: Path) -> str:
    output_parent = output.parent

    def as_href(workspace_href: str) -> str:
        return _display_source_href(workspace_href, workspace=workspace, output_parent=output_parent)

    def link_sub(match: re.Match[str]) -> str:
        href = as_href(match.group(1))
        if any(ch in href for ch in " ()"):
            return f"](<{href}>)"
        return f"]({href})"

    rewritten = _MD_SOURCE_LINK.sub(link_sub, markdown)
    rewritten = _TICK_SOURCE_LINK.sub(lambda match: f"`{as_href(match.group(1))}`", rewritten)
    return rewritten


def _finish_light_import(result: dict[str, Any], args: argparse.Namespace, context: dict[str, Any]) -> int:
    if result.get("ok") is not True:
        return _dump_handoff(result)
    workspace = _resolve_import_workspace(args, context)
    output = Path(args.output) if args.output else Path(args.context).with_suffix(".md")
    markdown = _rewrite_markdown_links(str(result.get("markdown") or ""), workspace=workspace, output=output)
    path = _write_markdown(output, markdown)
    result = dict(result)
    result["markdown"] = markdown
    result["path"] = str(path)
    return _dump_handoff(result)


def _cmd_intake(args: argparse.Namespace) -> int:
    command = "pdf.intake"
    with open_research_session(args.session) as session:
        result = intake_pdf(session, Path(args.pdf), paper_id=args.paper_id)
    data = {
        "intake": result["ref"],
        "path": result["path"],
        "blob_path": result["blob_path"],
        "paper_id": result["intake"]["data"]["paper_id"],
        "pdf_sha256": result["intake"]["data"]["pdf_sha256"],
        "already_staged": result["already_staged"],
        "next_action": result["next_action"],
        "state": result["state"],
        "capture_authorized": False,
        "receipt_backed": False,
        "published": False,
    }
    return emit_success(command, data)


def _cmd_plan(args: argparse.Namespace) -> int:
    command = "pdf.plan"
    session_id = session_from_research_path(Path(args.intake), kind_dir="intakes")
    with open_research_session(session_id) as session:
        result = plan_handoff(session, Path(args.intake), Path(args.profile), args.batch_id)
    return emit_success(
        command,
        {
            "plan_path": result["plan_path"],
            "plan_sha256": result["plan_sha256"],
            "approval_hash": result["plan"]["approval_hash"],
            "pipeline_fingerprint": result["plan"]["pipeline_fingerprint"],
            "intake": result["intake"],
            "profile": result["profile"],
            "already_staged": result["already_staged"],
            "next_action": result["next_action"],
            "capture_authorized": False,
            "receipt_backed": False,
            "published": False,
        },
    )


def _cmd_context(args: argparse.Namespace) -> int:
    command = "pdf.context"
    with open_research_session(args.session) as session:
        result = build_context(
            session,
            intake_path=Path(args.intake),
            profile_path=Path(args.profile),
            run_dir=Path(args.run),
            upstream_root=Path(args.upstream_root),
        )
    return emit_success(
        command,
        {
            "context": result["ref"],
            "path": result["path"],
            "prompt": result["prompt"],
            "prompt_sha256": result["prompt_sha256"],
            "already_staged": result["already_staged"],
            "next_action": result["next_action"],
            "state": result["state"],
            "capture_authorized": False,
            "receipt_backed": False,
            "published": False,
        },
    )


def _cmd_analyze(args: argparse.Namespace) -> int:
    command = "pdf.analyze"
    with open_research_session(args.session) as session:
        result = analyze_proposal(
            session,
            context_path=Path(args.context),
            proposal_path=Path(args.proposal),
            upstream_root=Path(args.upstream_root),
        )
    return emit_success(
        command,
        {
            "proposal": result["ref"],
            "path": result["path"],
            "legacy_draft_path": result["legacy_draft_path"],
            "markdown_path": result["markdown_path"],
            "legacy_draft_sha256": result["legacy_draft_sha256"],
            "already_staged": result["already_staged"],
            "state": result["state"],
            "capture_authorized": False,
            "receipt_backed": False,
            "published": False,
            "next_action": result["next_action"],
        },
    )


def _dump_handoff(payload: dict) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0 if payload.get("ok") else 2


def _cmd_pdf_add(args: argparse.Namespace) -> int:
    light_pdf = _load_light("light_pdf")
    workspace = _workspace_root(args.workspace, create=True)
    title = args.title.strip() if isinstance(args.title, str) and args.title.strip() else None
    return _dump_handoff(light_pdf.extract_pdf(Path(args.pdf).expanduser(), workspace, title=title))


def _cmd_index_build(args: argparse.Namespace) -> int:
    light_index = _load_light("light_index")
    workspace = _workspace_root(args.workspace, create=False)
    return _dump_handoff(light_index.build_index(workspace))


def _export_light_context(
    workspace: Path,
    *,
    kind: str,
    query: str,
    requirements: str = "",
    paper_ids: list[str] | None,
) -> dict[str, Any]:
    export_context = _optional_light_attr("light_context", "export_context")
    if export_context is not None:
        return export_context(
            workspace,
            kind=kind,
            query=query,
            requirements=requirements,
            paper_ids=paper_ids,
        )
    light_index = _load_light("light_index")
    if kind == "qa":
        light_qa = _load_light("light_qa")
        retrieval = light_index.search(workspace, query, paper_ids=paper_ids)
        return light_qa.export_qa_context(query, retrieval)
    light_writing = _load_light("light_writing")
    selected = list(paper_ids or [])
    retrieval = light_index.search(workspace, query, paper_ids=paper_ids)
    return light_writing.export_writing_context(query, requirements, selected, retrieval)


def _import_light_document(
    args: argparse.Namespace,
    context: dict[str, Any],
    document: dict[str, Any],
) -> int:
    workspace = _resolve_import_workspace(args, context)
    output = Path(args.output) if args.output else Path(args.context).with_suffix(".md")
    import_document = _optional_light_attr("light_context", "import_document")
    if import_document is not None:
        return _dump_handoff(
            import_document(workspace, context, document, output=output, overwrite=True)
        )
    if context.get("kind") == "writing":
        rendered = _load_light("light_writing").render_draft(context, document)
    else:
        rendered = _load_light("light_qa").render_answer(context, document)
    return _finish_light_import(rendered, args, context)


def _cmd_qa_export(args: argparse.Namespace) -> int:
    _reject_mixed_export(args)
    if args.workspace:
        workspace = _workspace_root(args.workspace, create=False)
        return _dump_handoff(
            _with_workspace_root(
                _export_light_context(
                    workspace,
                    kind="qa",
                    query=args.question,
                    paper_ids=_paper_ids_from_args(args),
                ),
                workspace,
            )
        )
    from video_paper_wiki_research.qa import export_from_question

    return _dump_handoff(
        export_from_question(
            question=args.question,
            vault_root=args.vault_root,
            upstream_root=args.upstream_root,
            retrieval_config=args.config,
        )
    )


def _cmd_qa_import(args: argparse.Namespace) -> int:
    context = _read_json(args.context)
    if _is_light_context(context):
        return _import_light_document(args, context, _read_json(args.answer))
    if args.workspace:
        raise UsageError("--workspace applies only to light-context import")
    from video_paper_wiki_research.qa import import_and_check

    result = import_and_check(context=args.context, answer=args.answer)
    if args.output and result.get("ok") is True and type(result.get("text")) is str:
        output = Path(args.output)
        result = dict(result)
        result["path"] = str(_write_markdown(output, result["text"]))
    return _dump_handoff(result)


def _cmd_writing_export(args: argparse.Namespace) -> int:
    _reject_mixed_export(args)
    paper_ids = _paper_ids_from_args(args)
    if args.workspace:
        workspace = _workspace_root(args.workspace, create=False)
        return _dump_handoff(
            _with_workspace_root(
                _export_light_context(
                    workspace,
                    kind="writing",
                    query=args.topic,
                    requirements=args.requirements,
                    paper_ids=paper_ids,
                ),
                workspace,
            )
        )
    selected = list(paper_ids or [])
    if not selected:
        raise UsageError("--paper-id is required without --workspace")
    from video_paper_wiki_research.writing import export_from_request

    return _dump_handoff(
        export_from_request(
            topic=args.topic,
            requirements=args.requirements,
            paper_ids=selected,
            vault_root=args.vault_root,
            upstream_root=args.upstream_root,
            retrieval_config=args.config,
        )
    )


def _cmd_writing_import(args: argparse.Namespace) -> int:
    context = _read_json(args.context)
    if _is_light_context(context):
        return _import_light_document(args, context, _read_json(args.draft))
    if args.workspace:
        raise UsageError("--workspace applies only to light-context import")
    from video_paper_wiki_research.writing import import_and_render

    result = import_and_render(context=args.context, draft=args.draft)
    if args.output and result.get("ok") is True and type(result.get("markdown")) is str:
        output = Path(args.output)
        result = dict(result)
        result["path"] = str(_write_markdown(output, result["markdown"]))
    return _dump_handoff(result)


def _cmd_workspace_inspect(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False, allow_missing=True)
    inspect_workspace = _try_light_attr("light_workspace", "inspect_workspace")
    return _dump_handoff(inspect_workspace(workspace))


def _cmd_workflow_prepare(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False, allow_missing=True)
    prepare_workflow = _try_light_attr("light_workflow", "prepare_workflow")
    return _dump_handoff(
        prepare_workflow(
            workspace,
            kind=args.kind,
            query=args.query,
            requirements=args.requirements,
            paper_ids=_paper_ids_from_args(args),
            pdf_paths=_pdf_paths_from_args(args),
        )
    )


def _cmd_workflow_status(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False, allow_missing=True)
    workflow_status = _try_light_attr("light_workflow", "workflow_status")
    return _dump_handoff(workflow_status(workspace, session_id=args.session_id))


def _cmd_workflow_complete(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    document = _read_json(args.document)
    complete_workflow = _try_light_attr("light_workflow", "complete_workflow")
    return _dump_handoff(
        complete_workflow(
            workspace,
            args.session_id,
            document,
            output=Path(args.output).expanduser(),
        )
    )


def _work_bound_path(
    raw: str,
    *,
    must_exist: bool = False,
    allow_missing: bool = False,
    require_suffix: str | None = None,
    label: str = "path",
) -> Path:
    given = Path(raw).expanduser()
    if require_suffix and given.suffix.lower() != require_suffix.lower():
        raise ResearchError(
            "WORKSPACE_INVALID",
            f"{label} must use the {require_suffix} suffix",
            {"path": str(given)},
        )
    if ".work" not in given.parts:
        raise ResearchError(
            "WORKSPACE_INVALID",
            f"{label} must be under .work/**",
            {"path": str(given)},
        )
    if given.is_symlink() or (given.exists() and not (given.is_file() or given.is_dir())):
        raise ResearchError(
            "WORKSPACE_INVALID",
            f"{label} must be a regular file or directory under .work/**",
            {"path": str(given)},
        )
    resolved = given.resolve()
    if ".work" not in resolved.parts:
        raise ResearchError(
            "WORKSPACE_INVALID",
            f"{label} must be under .work/**",
            {"path": str(resolved)},
        )
    if resolved.exists():
        if resolved.is_symlink() or not (resolved.is_file() or resolved.is_dir()):
            raise ResearchError(
                "WORKSPACE_INVALID",
                f"{label} must be a regular file or directory under .work/**",
                {"path": str(resolved)},
            )
        return resolved
    if allow_missing or not must_exist:
        return resolved
    raise ResearchError(
        "WORKSPACE_INVALID",
        f"{label} must exist under .work/**",
        {"path": str(resolved)},
    )


def _regular_markdown(raw: str) -> Path:
    path, data = _read_safe_regular_bytes(
        raw,
        code="LIGHT_BACKUP_INVALID",
        label="--include-output",
        suffix=".md",
        suffix_message="--include-output must be a regular .md file",
    )
    _decode_strict_utf8(data, path=path, code="LIGHT_BACKUP_INVALID", label="--include-output")
    return path


def _extra_outputs_from_args(args: argparse.Namespace) -> list[Path] | None:
    raw = getattr(args, "extra_outputs", None)
    if raw is None:
        return None
    return [_regular_markdown(item) for item in raw]


def _edit_tags(args: argparse.Namespace) -> list[str] | None:
    if args.clear_tags and args.tags:
        raise UsageError("--clear-tags cannot be combined with --tag")
    if args.clear_tags:
        return []
    if args.tags is None:
        return None
    return list(args.tags)


def _compare_paper_ids(args: argparse.Namespace) -> list[str]:
    paper_ids = list(args.paper_ids or [])
    if len(paper_ids) < 2:
        raise UsageError("compare export requires at least two --paper-id values")
    return paper_ids


def _cmd_library_list(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False, allow_missing=True)
    list_papers = _try_light_attr("light_library", "list_papers")
    return _dump_handoff(list_papers(workspace))


def _cmd_library_edit(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    tags = _edit_tags(args)
    title = args.title.strip() if isinstance(args.title, str) and args.title.strip() else args.title
    update_paper_metadata = _try_light_attr("light_library", "update_paper_metadata")
    return _dump_handoff(update_paper_metadata(workspace, args.paper_id, title=title, tags=tags))


def _cmd_library_remove(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    archive_paper = _try_light_attr("light_library", "archive_paper")
    return _dump_handoff(archive_paper(workspace, args.paper_id))


def _cmd_library_restore(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    restore_paper = _try_light_attr("light_library", "restore_paper")
    return _dump_handoff(restore_paper(workspace, args.archive_id))


def _cmd_library_replace(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    title = args.title.strip() if isinstance(args.title, str) and args.title.strip() else args.title
    replace_paper = _try_light_attr("light_library", "replace_paper")
    return _dump_handoff(
        replace_paper(workspace, args.paper_id, Path(args.pdf).expanduser(), title=title)
    )


def _cmd_library_recover(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    recover_library = _try_light_attr("light_library", "recover_library")
    return _dump_handoff(recover_library(workspace, operation_id=args.operation_id))


def _cmd_knowledge_export(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    export_knowledge_context = _try_light_attr("light_knowledge", "export_knowledge_context")
    return _dump_handoff(export_knowledge_context(workspace, paper_id=args.paper_id))


def _cmd_knowledge_import(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    context = _read_library_json(args.context)
    document = _read_library_json(args.document)
    import_knowledge = _try_light_attr("light_knowledge", "import_knowledge")
    return _dump_handoff(import_knowledge(workspace, context, document))


def _cmd_knowledge_list(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False, allow_missing=True)
    list_knowledge = _try_light_attr("light_knowledge", "list_knowledge")
    return _dump_handoff(list_knowledge(workspace))


def _cmd_knowledge_build(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    build_knowledge_views = _try_light_attr("light_knowledge", "build_knowledge_views")
    return _dump_handoff(build_knowledge_views(workspace))


def _cmd_compare_export(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    paper_ids = _compare_paper_ids(args)
    dimensions = list(args.dimensions) if args.dimensions else None
    export_comparison_context = _try_light_attr("light_compare", "export_comparison_context")
    return _dump_handoff(
        export_comparison_context(
            workspace,
            query=args.query,
            paper_ids=paper_ids,
            dimensions=dimensions,
        )
    )


def _cmd_compare_import(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    output = _work_bound_path(args.output, require_suffix=".md", label="comparison output")
    context = _read_library_json(args.context)
    document = _read_library_json(args.document)
    import_comparison = _try_light_attr("light_compare", "import_comparison")
    return _dump_handoff(import_comparison(workspace, context, document, output=output))


def _cmd_backup_create(args: argparse.Namespace) -> int:
    workspace = _workspace_root(args.workspace, create=False)
    output = _work_bound_path(args.output, allow_missing=True, label="backup output")
    try:
        output.relative_to(workspace)
    except ValueError:
        pass
    else:
        raise ResearchError(
            "LIGHT_BACKUP_INVALID",
            "backup output must be outside the backed-up workspace",
            {"output": str(output), "workspace": str(workspace)},
        )
    create_backup = _try_light_attr("light_backup", "create_backup")
    return _dump_handoff(
        create_backup(workspace, output=output, extra_outputs=_extra_outputs_from_args(args))
    )


def _cmd_backup_verify(args: argparse.Namespace) -> int:
    archive = _work_bound_path(args.archive, must_exist=True, label="backup archive")
    if archive.exists() and not archive.is_file():
        raise ResearchError(
            "LIGHT_BACKUP_INVALID",
            "backup archive must be a regular file",
            {"path": str(archive)},
        )
    verify_backup = _try_light_attr("light_backup", "verify_backup")
    return _dump_handoff(verify_backup(archive))


def _cmd_backup_restore(args: argparse.Namespace) -> int:
    archive = _work_bound_path(args.archive, must_exist=True, label="backup archive")
    destination = _work_bound_path(args.destination, allow_missing=True, label="restore destination")
    if archive.exists() and not archive.is_file():
        raise ResearchError(
            "LIGHT_BACKUP_INVALID",
            "backup archive must be a regular file",
            {"path": str(archive)},
        )
    restore_backup = _try_light_attr("light_backup", "restore_backup")
    return _dump_handoff(restore_backup(archive, destination=destination))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        ns = parser.parse_args(args)
    except UsageError as exc:
        return emit_error(_command_from_argv(args), "USAGE", exc.message)
    handler = getattr(ns, "handler", None)
    if handler is None:
        return emit_error(_command_from_argv(args), "USAGE", "missing command")
    try:
        return handler(ns)
    except (ResearchError, StagingError, SecureIOError, IdentityError, CanonicalJsonError, UsageError) as exc:
        return _emit(_command_from_argv(args), exc)
