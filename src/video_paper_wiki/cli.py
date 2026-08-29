"""Agent-safe, zero-egress command-line interface."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .blob_store import BlobStore
from .envelope import EXIT_UNEXPECTED, emit_error, emit_success

Handler = Callable[[argparse.Namespace], int]


class UsageError(Exception):
    """Raised instead of letting argparse terminate without a JSON envelope."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        raise UsageError(message)


def _command_hint(argv: Sequence[str]) -> str:
    parts = [part for part in argv if not part.startswith("-")][:2]
    return ".".join(parts) if parts else "vpwiki"


def _doctor(_: argparse.Namespace) -> int:
    return emit_success(
        "doctor",
        {
            "status": "ok",
            "package": "video-paper-wiki",
            "python": ".".join(map(str, sys.version_info[:3])),
            "vpwiki_admin_on_path": shutil.which("vpwiki-admin") is not None,
        },
    )


def _not_implemented(command: str) -> Handler:
    def handler(_: argparse.Namespace) -> int:
        return emit_error(
            command,
            "NOT_IMPLEMENTED",
            f"The agent-safe command '{command}' is not implemented yet.",
        )

    return handler


def _prepare(command: str) -> Handler:
    def handler(args: argparse.Namespace) -> int:
        blob = Path(args.blob)
        if not blob.is_file():
            return emit_error(
                command,
                "BLOB_NOT_FOUND",
                "The local blob is missing; fetching is available only in the operator environment.",
                {"path": str(blob)},
            )

        dest_dir = args.work_dir / args.batch_id
        digest, staged_path = BlobStore(Path()).stage_file(blob, dest_dir)
        result: dict[str, Any] = {
            "status": "prepared",
            "blob_sha256": digest,
            "staged_path": staged_path.as_posix(),
        }
        if args.approval_ref is not None:
            result["approval_ref"] = args.approval_ref
        return emit_success(command, result)

    return handler


def _add_leaf(
    subparsers: Any,
    name: str,
    command: str,
    handler: Handler | None = None,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name)
    parser.set_defaults(command_name=command, handler=handler or _not_implemented(command))
    return parser


def _add_group(root_subparsers: Any, name: str) -> Any:
    parser = root_subparsers.add_parser(name)
    return parser.add_subparsers(dest=f"{name}_command", required=True)


def _add_prepare_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--blob", required=True)
    parser.add_argument("--approval-ref")
    parser.add_argument("--batch-id", default="default")
    parser.add_argument("--work-dir", type=Path, default=Path.cwd() / ".work")


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="vpwiki")
    commands = parser.add_subparsers(dest="root_command", required=True)

    _add_leaf(commands, "doctor", "doctor", _doctor)

    for group, leaves in (
        ("init", ("plan", "inspect")),
        ("seed", ("validate", "status")),
        ("capture", ("inspect",)),
        ("draft", ("export", "validate")),
        ("review", ("export", "inspect")),
        ("index", ("status",)),
    ):
        children = _add_group(commands, group)
        for leaf in leaves:
            _add_leaf(children, leaf, f"{group}.{leaf}")

    for group in ("ingest", "code-map"):
        children = _add_group(commands, group)
        for leaf in ("plan", "prepare", "inspect"):
            command = f"{group}.{leaf}"
            child = _add_leaf(
                children,
                leaf,
                command,
                _prepare(command) if leaf == "prepare" else None,
            )
            if leaf == "prepare":
                _add_prepare_arguments(child)

    query = _add_leaf(commands, "query", "query")
    query.add_argument("--json", action="store_true")
    _add_leaf(commands, "audit", "audit")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(arguments)
        return args.handler(args)
    except UsageError as exc:
        return emit_error(_command_hint(arguments), "USAGE", str(exc))
    except Exception:
        return emit_error(
            _command_hint(arguments),
            "INTERNAL_ERROR",
            "An unexpected internal error occurred.",
            exit_code=EXIT_UNEXPECTED,
        )


if __name__ == "__main__":
    sys.exit(main())
