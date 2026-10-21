"""vpwiki-parser CLI. Optional producer; never dispatches vpwiki-admin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.identity import IdentityError
from video_paper_wiki.jcs import CanonicalJsonError
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError

from video_paper_wiki_parser_executor.exporter import export_run
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.parser_profile import create_profile
from video_paper_wiki_research.storage import open_research_session, session_from_research_path


class UsageError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> None:
        raise UsageError(message)

    def add_subparsers(self, **kwargs):
        kwargs["parser_class"] = type(self)
        return super().add_subparsers(**kwargs)


def _command_from_argv(args: list[str]) -> str:
    parts = [token for token in args if not token.startswith("-")]
    if not parts:
        return "vpwiki-parser"
    return "parser." + parts[0]


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="vpwiki-parser", add_help=True, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    profile = sub.add_parser("profile", allow_abbrev=False)
    profile.add_argument("--artifacts-path", dest="artifacts_path", required=True)
    profile.add_argument("--session", required=True)
    profile.set_defaults(handler=_cmd_profile)
    export = sub.add_parser("export", allow_abbrev=False)
    export.add_argument("--intake", required=True)
    export.add_argument("--profile", required=True)
    export.add_argument("--artifacts-path", dest="artifacts_path", required=True)
    export.add_argument("--session", required=True)
    export.add_argument("--run-id", dest="run_id", required=True)
    export.set_defaults(handler=_cmd_export)
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
        return emit_error(command, str(getattr(exc, "code", "PARSER_FAILED")), str(getattr(exc, "message", exc)))
    return emit_error(command, "PARSER_FAILED", str(exc))


def _cmd_profile(args: argparse.Namespace) -> int:
    with open_research_session(args.session) as session:
        result = create_profile(session, Path(args.artifacts_path))
    return emit_success(
        "parser.profile",
        {
            "profile": result["ref"],
            "path": result["path"],
            "parser_config_path": result["parser_config_path"],
            "model_manifest_path": result["model_manifest_path"],
            "pipeline_fingerprint": result["pipeline_fingerprint"],
            "already_staged": result["already_staged"],
            "next_action": result["next_action"],
        },
    )


def _cmd_export(args: argparse.Namespace) -> int:
    with open_research_session(args.session) as session:
        result = export_run(
            session,
            intake_path=Path(args.intake),
            profile_path=Path(args.profile),
            artifacts_path=Path(args.artifacts_path),
            run_id=args.run_id,
        )
    return emit_success("parser.export", result)


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
