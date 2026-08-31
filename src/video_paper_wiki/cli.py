"""Agent-safe vpwiki command tree. No network, no vpwiki-admin."""

from __future__ import annotations

import argparse
import shutil
import sys

from video_paper_wiki.commands import draft as draft_commands
from video_paper_wiki.commands import plan as plan_commands
from video_paper_wiki.commands import prepare as prepare_commands
from video_paper_wiki.commands import review as review_commands
from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.notes.encoding import InvalidEncoding
from video_paper_wiki.staging import StagingError, resolve_checkout_root


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


def _add_parser(sub: argparse._SubParsersAction, name: str, **kwargs) -> argparse.ArgumentParser:
    kwargs["allow_abbrev"] = False
    return sub.add_parser(name, **kwargs)


def _dotted(argv_head: list[str]) -> str:
    if not argv_head:
        return "vpwiki"
    return ".".join(argv_head)


def _command_from_argv(args: list[str]) -> str:
    parts: list[str] = []
    for token in args:
        if token.startswith("-"):
            continue
        parts.append(token)
        if len(parts) >= 2:
            break
    return _dotted(parts) if parts else "vpwiki"


def _cmd_doctor(_args: argparse.Namespace) -> int:
    py = sys.version_info
    return emit_success(
        "doctor",
        {
            "status": "ok",
            "package": "video-paper-wiki",
            "python": f"{py.major}.{py.minor}.{py.micro}",
            "vpwiki_admin_on_path": shutil.which("vpwiki-admin") is not None,
        },
    )


def _cmd_not_implemented(command: str):
    def _run(_args: argparse.Namespace) -> int:
        return emit_error(
            command,
            "NOT_IMPLEMENTED",
            f"{command} is not implemented in VPKB-000-02",
        )

    return _run


def _cmd_query(args: argparse.Namespace) -> int:
    if not args.json:
        return emit_error("query", "USAGE", "query requires --json")
    return emit_error(
        "query",
        "NOT_IMPLEMENTED",
        "query is not implemented in VPKB-000-02",
    )


def _add_plan_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--request", required=True)
    parser.set_defaults(handler=plan_commands.run)


def _add_prepare_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan", required=True)
    parser.add_argument("--approval-ref", required=True)
    parser.set_defaults(handler=prepare_commands.run)


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="vpwiki", add_help=True, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command")

    doctor = _add_parser(sub, "doctor")
    doctor.set_defaults(handler=_cmd_doctor)

    init = _add_parser(sub, "init")
    init_sub = init.add_subparsers(dest="init_cmd", required=True)
    _add_parser(init_sub, "plan").set_defaults(handler=_cmd_not_implemented("init.plan"))
    _add_parser(init_sub, "inspect").set_defaults(handler=_cmd_not_implemented("init.inspect"))

    seed = _add_parser(sub, "seed")
    seed_sub = seed.add_subparsers(dest="seed_cmd", required=True)
    _add_parser(seed_sub, "validate").set_defaults(handler=_cmd_not_implemented("seed.validate"))
    _add_parser(seed_sub, "status").set_defaults(handler=_cmd_not_implemented("seed.status"))

    ingest = _add_parser(sub, "ingest")
    ingest_sub = ingest.add_subparsers(dest="ingest_cmd", required=True)
    ingest_plan = _add_parser(ingest_sub, "plan")
    ingest_plan.set_defaults(_vpkb_family="ingest")
    _add_plan_flags(ingest_plan)
    ingest_prepare = _add_parser(ingest_sub, "prepare")
    ingest_prepare.set_defaults(_vpkb_family="ingest")
    _add_prepare_flags(ingest_prepare)
    _add_parser(ingest_sub, "inspect").set_defaults(handler=_cmd_not_implemented("ingest.inspect"))

    capture = _add_parser(sub, "capture")
    capture_sub = capture.add_subparsers(dest="capture_cmd", required=True)
    _add_parser(capture_sub, "inspect").set_defaults(handler=_cmd_not_implemented("capture.inspect"))

    draft = _add_parser(sub, "draft")
    draft_sub = draft.add_subparsers(dest="draft_cmd", required=True)
    draft_export = _add_parser(draft_sub, "export")
    draft_export.add_argument("--sha256", required=True)
    draft_export.add_argument("--paper-id", dest="paper_id", default=None)
    draft_export.add_argument("--batch-id", required=True)
    draft_export.set_defaults(handler=draft_commands.export)
    draft_validate = _add_parser(draft_sub, "validate")
    draft_validate.add_argument("--path", required=True)
    draft_validate.set_defaults(handler=draft_commands.validate)

    review = _add_parser(sub, "review")
    review_sub = review.add_subparsers(dest="review_cmd", required=True)
    review_export = _add_parser(review_sub, "export")
    review_export.add_argument("--draft", required=True)
    review_export.add_argument("--batch-id", required=True)
    review_export.set_defaults(handler=review_commands.export)
    _add_parser(review_sub, "inspect").set_defaults(handler=_cmd_not_implemented("review.inspect"))

    code_map = _add_parser(sub, "code-map")
    code_map_sub = code_map.add_subparsers(dest="code_map_cmd", required=True)
    code_map_plan = _add_parser(code_map_sub, "plan")
    code_map_plan.set_defaults(_vpkb_family="code-map")
    _add_plan_flags(code_map_plan)
    code_map_prepare = _add_parser(code_map_sub, "prepare")
    code_map_prepare.set_defaults(_vpkb_family="code-map")
    _add_prepare_flags(code_map_prepare)
    _add_parser(code_map_sub, "inspect").set_defaults(handler=_cmd_not_implemented("code-map.inspect"))

    index = _add_parser(sub, "index")
    index_sub = index.add_subparsers(dest="index_cmd", required=True)
    _add_parser(index_sub, "status").set_defaults(handler=_cmd_not_implemented("index.status"))

    query = _add_parser(sub, "query")
    query.add_argument("--json", action="store_true")
    query.set_defaults(handler=_cmd_query)

    audit = _add_parser(sub, "audit")
    audit.set_defaults(handler=_cmd_not_implemented("audit"))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        ns = parser.parse_args(args)
    except UsageError as exc:
        command = _command_from_argv(args)
        sys.stderr.write(f"{exc.message}\n")
        return emit_error(command, "USAGE", exc.message)
    handler = getattr(ns, "handler", None)
    if handler is None:
        sys.stderr.write("missing command\n")
        return emit_error(_command_from_argv(args), "USAGE", "missing command")
    if getattr(ns, "command", None) == "query" and not getattr(ns, "json", False):
        sys.stderr.write("query requires --json\n")
        return emit_error("query", "USAGE", "query requires --json")
    try:
        resolve_checkout_root()
    except StagingError as exc:
        sys.stderr.write(f"{exc.message}\n")
        return emit_staging_error(_command_from_argv(args), exc)
    try:
        return handler(ns)
    except StagingError as exc:
        sys.stderr.write(f"{exc.message}\n")
        return emit_staging_error(_command_from_argv(args), exc)
    except InvalidEncoding as exc:
        command = _command_from_argv(args)
        return emit_error(
            command,
            "INVALID_ENCODING",
            "file is not valid UTF-8; this command does not rewrite it",
            {"path": exc.path.as_posix()},
        )
    except NotADirectoryError:
        return emit_error(
            _command_from_argv(args),
            "WORK_PATH_UNSAFE",
            "directory slot is not a directory",
        )


if __name__ == "__main__":
    sys.exit(main())
