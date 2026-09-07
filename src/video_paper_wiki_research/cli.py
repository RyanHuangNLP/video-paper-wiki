"""Agent-safe vpwiki-research CLI. No network, no vpwiki-admin, no Vault writes."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.identity import IdentityError
from video_paper_wiki.jcs import CanonicalJsonError
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError

from video_paper_wiki_research.contracts import ResearchError
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
