"""Agent-safe vpwiki command tree. No network, no vpwiki-admin."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from video_paper_wiki.blob_store import BlobStore, resolve_blob_root
from video_paper_wiki.commands import draft as draft_commands
from video_paper_wiki.commands import ingest as ingest_commands
from video_paper_wiki.commands import review as review_commands
from video_paper_wiki.commands import search as search_commands
from video_paper_wiki.commands import wiki as wiki_commands
from video_paper_wiki.envelope import emit_error, emit_success

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")



class UsageError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)


def _dotted(argv_head: list[str]) -> str:
    if not argv_head:
        return "vpwiki"
    return ".".join(argv_head)


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


def _prepare_command_name(args: argparse.Namespace) -> str:
    return "ingest.prepare" if args._vpkb_family == "ingest" else "code-map.prepare"


def _cmd_prepare(args: argparse.Namespace) -> int:
    command = _prepare_command_name(args)
    sha = args.sha256.strip()
    if not SHA256_RE.fullmatch(sha):
        return emit_error(
            command,
            "INVALID_SHA256",
            "sha256 must be exactly 64 hexadecimal characters",
            {"sha256": sha},
        )
    sha = sha.lower()
    approval_present = args.approval_hash is not None
    store = BlobStore(resolve_blob_root())
    if store.get(sha) is None:
        return emit_error(
            command,
            "BLOB_NOT_FOUND",
            "local blob is missing; fetch is operator-only and this command does not download",
            {"sha256": sha, "approval_hash_present": approval_present},
        )
    work_dir = Path(args.work_dir)
    staged = store.stage(sha, work_dir / args.batch_id)
    return emit_success(
        command,
        {
            "sha256": sha,
            "batch_id": args.batch_id,
            "staged_path": staged.as_posix(),
            "approval_hash_present": approval_present,
        },
    )


def _add_prepare_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--approval-hash", default=None)
    parser.add_argument("--batch-id", default="default")
    parser.add_argument("--work-dir", default=str(Path.cwd() / ".work"))
    parser.set_defaults(handler=_cmd_prepare)


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="vpwiki", add_help=True)
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor")
    doctor.set_defaults(handler=_cmd_doctor)

    init = sub.add_parser("init")
    init_sub = init.add_subparsers(dest="init_cmd", required=True)
    init_sub.add_parser("plan").set_defaults(handler=_cmd_not_implemented("init.plan"))
    init_sub.add_parser("inspect").set_defaults(handler=_cmd_not_implemented("init.inspect"))

    seed = sub.add_parser("seed")
    seed_sub = seed.add_subparsers(dest="seed_cmd", required=True)
    seed_sub.add_parser("validate").set_defaults(handler=_cmd_not_implemented("seed.validate"))
    seed_sub.add_parser("status").set_defaults(handler=_cmd_not_implemented("seed.status"))

    ingest = sub.add_parser("ingest")
    ingest_sub = ingest.add_subparsers(dest="ingest_cmd", required=True)
    ingest_sub.add_parser("plan").set_defaults(handler=_cmd_not_implemented("ingest.plan"))
    ingest_put = ingest_sub.add_parser("put")
    ingest_put.add_argument("--path", required=True)
    ingest_put.set_defaults(handler=ingest_commands.put)
    ingest_run = ingest_sub.add_parser("run")
    ingest_run.add_argument("--path", default=None)
    ingest_run.add_argument("--pdf-dir", dest="pdf_dir", default=None)
    ingest_run.add_argument("--vault", dest="notes_root", default=None)
    ingest_run.add_argument("--paper-id", dest="paper_id", default=None)
    ingest_run.add_argument("--seed", dest="seed_path", default=None)
    ingest_run.set_defaults(handler=ingest_commands.run)
    ingest_prepare = ingest_sub.add_parser("prepare")
    ingest_prepare.set_defaults(_vpkb_family="ingest")
    _add_prepare_flags(ingest_prepare)
    ingest_sub.add_parser("inspect").set_defaults(handler=_cmd_not_implemented("ingest.inspect"))

    capture = sub.add_parser("capture")
    capture_sub = capture.add_subparsers(dest="capture_cmd", required=True)
    capture_sub.add_parser("inspect").set_defaults(handler=_cmd_not_implemented("capture.inspect"))

    draft = sub.add_parser("draft")
    draft_sub = draft.add_subparsers(dest="draft_cmd", required=True)
    draft_export = draft_sub.add_parser("export")
    draft_export.add_argument("--sha256", required=True)
    draft_export.add_argument("--paper-id", dest="paper_id", default=None)
    draft_export.set_defaults(handler=draft_commands.export)
    draft_validate = draft_sub.add_parser("validate")
    draft_validate.add_argument("--path", required=True)
    draft_validate.set_defaults(handler=draft_commands.validate)

    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_cmd", required=True)
    review_export = review_sub.add_parser("export")
    review_export.add_argument("--draft", required=True)
    review_export.add_argument("--vault", dest="notes_root", default=None)
    review_export.set_defaults(handler=review_commands.export)
    review_sub.add_parser("inspect").set_defaults(handler=_cmd_not_implemented("review.inspect"))

    code_map = sub.add_parser("code-map")
    code_map_sub = code_map.add_subparsers(dest="code_map_cmd", required=True)
    code_map_sub.add_parser("plan").set_defaults(handler=_cmd_not_implemented("code-map.plan"))
    code_map_prepare = code_map_sub.add_parser("prepare")
    code_map_prepare.set_defaults(_vpkb_family="code-map")
    _add_prepare_flags(code_map_prepare)
    code_map_sub.add_parser("inspect").set_defaults(handler=_cmd_not_implemented("code-map.inspect"))

    index = sub.add_parser("index")
    index_sub = index.add_subparsers(dest="index_cmd", required=True)
    index_sub.add_parser("status").set_defaults(handler=_cmd_not_implemented("index.status"))

    vault = sub.add_parser("vault")
    vault_sub = vault.add_subparsers(dest="vault_cmd", required=True)
    grep = vault_sub.add_parser("grep")
    grep.add_argument("--vault", dest="notes_root", required=True)
    grep.add_argument("query")
    grep.set_defaults(handler=search_commands.grep)
    stat = vault_sub.add_parser("stat")
    stat.add_argument("--vault", dest="notes_root", required=True)
    stat.set_defaults(handler=search_commands.stat)
    listing = vault_sub.add_parser("list")
    listing.add_argument("--vault", dest="notes_root", required=True)
    listing.set_defaults(handler=search_commands.list_papers)
    show = vault_sub.add_parser("show")
    show.add_argument("--vault", dest="notes_root", required=True)
    show.add_argument("paper_id")
    show.set_defaults(handler=search_commands.show)

    wiki = sub.add_parser("wiki")
    wiki_sub = wiki.add_subparsers(dest="wiki_cmd", required=True)
    wiki_show = wiki_sub.add_parser("show")
    wiki_show.add_argument("--vault", dest="notes_root", required=True)
    wiki_show.add_argument("topic_id")
    wiki_show.set_defaults(handler=wiki_commands.show)

    wiki_list = wiki_sub.add_parser("list")
    wiki_list.add_argument("--vault", dest="notes_root", required=True)
    wiki_list.set_defaults(handler=wiki_commands.list_pages)

    query = sub.add_parser("query")
    query.add_argument("--json", action="store_true")
    query.set_defaults(handler=_cmd_not_implemented("query"))

    audit = sub.add_parser("audit")
    audit.set_defaults(handler=_cmd_not_implemented("audit"))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        ns = parser.parse_args(args)
    except UsageError as exc:
        command = _dotted(args[:2]) if args else "vpwiki"
        sys.stderr.write(f"{exc.message}\n")
        return emit_error(command, "USAGE", exc.message)
    handler = getattr(ns, "handler", None)
    if handler is None:
        sys.stderr.write("missing command\n")
        return emit_error(_dotted(args[:2]) if args else "vpwiki", "USAGE", "missing command")
    return handler(ns)


if __name__ == "__main__":
    sys.exit(main())
