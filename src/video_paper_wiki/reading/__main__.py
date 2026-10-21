"""python -m video_paper_wiki.reading entry. No vpwiki reading leaf."""

from __future__ import annotations

import argparse
import sys

from video_paper_wiki.envelope import emit_error
from video_paper_wiki.reading.cli import run_reading_build_command


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
    for token in args:
        if token.startswith("-"):
            continue
        return "reading.build"
    return "reading"


def build_parser():
    parser = _JsonArgumentParser(prog="python -m video_paper_wiki.reading")
    sub = parser.add_subparsers(dest="reading_cmd", required=False)
    build = sub.add_parser("build")
    build.add_argument("--vault-root", dest="vault_root", required=True)
    build.add_argument("--batch-id", dest="batch_id", required=True)
    build.add_argument("--paper-id", dest="paper_id", required=False, default=None)
    build.add_argument("--articles-batch", dest="articles_batch", required=False, default=None)
    build.set_defaults(handler=run_reading_build_command)
    return parser


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        ns = parser.parse_args(args)
    except UsageError as exc:
        return emit_error(_command_from_argv(args), "USAGE", exc.message)
    handler = getattr(ns, "handler", None)
    if handler is None:
        return emit_error(_command_from_argv(args), "USAGE", "missing command")
    return handler(ns)


if __name__ == "__main__":
    raise SystemExit(main())
