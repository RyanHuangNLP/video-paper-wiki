"""Agent-safe vpwiki command tree. No network, no vpwiki-admin."""

from __future__ import annotations

import argparse
import shutil
import sys

from video_paper_wiki.commands import capture as capture_commands
from video_paper_wiki.commands import domain as domain_commands
from video_paper_wiki.commands import draft as draft_commands
from video_paper_wiki.commands import plan as plan_commands
from video_paper_wiki.commands import prepare as prepare_commands
from video_paper_wiki.commands import review as review_commands
from video_paper_wiki.commands import publication as publication_commands
from video_paper_wiki.staged_code_capture import run_code_inspect_command
from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.notes.encoding import InvalidEncoding
from video_paper_wiki.staging import StagingError


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


def _cmd_query(args: argparse.Namespace) -> int:
    return domain_commands.query(args)


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
    _add_parser(init_sub, "plan").set_defaults(handler=domain_commands.init_plan)
    init_inspect = _add_parser(init_sub, "inspect"); init_inspect.add_argument("--upstream-root", required=True); init_inspect.add_argument("--vault-root", required=True); init_inspect.set_defaults(handler=domain_commands.init_inspect)

    seed = _add_parser(sub, "seed")
    seed_sub = seed.add_subparsers(dest="seed_cmd", required=True)
    for name, handler in (("validate", domain_commands.seed_validate), ("status", domain_commands.seed_status)):
        command = _add_parser(seed_sub, name); command.add_argument("--catalog"); command.set_defaults(handler=handler)
    seed_render = _add_parser(seed_sub, "render"); seed_render.add_argument("--batch-id", required=True); seed_render.set_defaults(handler=domain_commands.seed_render)

    ingest = _add_parser(sub, "ingest")
    ingest_sub = ingest.add_subparsers(dest="ingest_cmd", required=True)
    ingest_plan = _add_parser(ingest_sub, "plan")
    ingest_plan.set_defaults(_vpkb_family="ingest")
    _add_plan_flags(ingest_plan)
    ingest_prepare = _add_parser(ingest_sub, "prepare")
    ingest_prepare.set_defaults(_vpkb_family="ingest")
    _add_prepare_flags(ingest_prepare)
    ingest_inspect = _add_parser(ingest_sub, "inspect"); ingest_inspect.add_argument("--path", required=True); ingest_inspect.add_argument("--schema"); ingest_inspect.set_defaults(handler=lambda a: domain_commands.inspect_document(a,"ingest.inspect"))
    ingest_package = _add_parser(ingest_sub, "package")
    for flag in ("request", "captured-pdf", "document-json", "parser-config", "model-manifest", "run-manifest", "batch-id", "vault-root"):
        ingest_package.add_argument("--" + flag, dest=flag.replace("-", "_"), required=True)
    ingest_package.set_defaults(handler=publication_commands.ingest_package)

    capture = _add_parser(sub, "capture")
    capture_sub = capture.add_subparsers(dest="capture_cmd", required=True)
    capture_inspect = _add_parser(capture_sub, "inspect")
    capture_inspect.add_argument("--prepared", required=True)
    capture_inspect.add_argument("--operation-id", dest="operation_id", required=True)
    capture_inspect.add_argument("--upstream-root", dest="upstream_root", required=True)
    capture_inspect.add_argument("--vault-root", dest="vault_root", required=True)
    capture_inspect.set_defaults(handler=capture_commands.run)

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
    review_inspect = _add_parser(review_sub, "inspect"); review_inspect.add_argument("--path", required=True); review_inspect.add_argument("--schema"); review_inspect.set_defaults(handler=lambda a: domain_commands.inspect_document(a,"review.inspect"))
    review_prepare = _add_parser(review_sub, "prepare")
    for flag in ("decision", "state", "batch-id", "vault-root"): review_prepare.add_argument("--"+flag,dest=flag.replace("-","_"),required=True)
    review_prepare.set_defaults(handler=publication_commands.review_prepare)
    review_invalidate = _add_parser(review_sub, "invalidate")
    for flag in ("change", "state", "batch-id", "vault-root"): review_invalidate.add_argument("--"+flag,dest=flag.replace("-","_"),required=True)
    review_invalidate.set_defaults(handler=publication_commands.review_invalidate)

    publication = _add_parser(sub, "publication")
    publication_sub = publication.add_subparsers(dest="publication_cmd", required=True)
    publication_prepare = _add_parser(publication_sub, "prepare")
    publication_prepare.add_argument("--request", required=True);publication_prepare.add_argument("--batch-id",required=True)
    publication_prepare.set_defaults(handler=publication_commands.prepare)
    publication_inspect = _add_parser(publication_sub, "inspect")
    for flag in ("prepared", "operation-id", "upstream-root", "vault-root"):
        publication_inspect.add_argument("--"+flag,dest=flag.replace("-","_"),required=True)
    publication_inspect.set_defaults(handler=publication_commands.inspect)

    from video_paper_wiki.source_publication import run_source_publication_command
    source_publication = _add_parser(sub, "source-publication")
    source_sub = source_publication.add_subparsers(dest="source_publication_cmd", required=True)
    for name, flags in (("prepare", ("proposal", "batch-id", "operation-id", "vault-root")),
                        ("inspect", ("prepared", "operation-id", "vault-root", "upstream-root")),
                        ("audit", ("vault-root",))):
        source_parser = _add_parser(source_sub, name)
        for flag in flags:
            source_parser.add_argument("--" + flag, required=True)
        source_parser.set_defaults(handler=run_source_publication_command)

    from video_paper_wiki.source_catalog import run_source_catalog_command
    source_catalog = _add_parser(sub, "source-catalog")
    catalog_sub = source_catalog.add_subparsers(dest="source_catalog_cmd", required=True)
    for name in ("build", "status", "lookup", "query", "resolve"):
        command = _add_parser(catalog_sub, name)
        command.add_argument("--vault-root", required=True)
        command.add_argument("--batch-id", required=True)
        command.set_defaults(handler=run_source_catalog_command)
        if name in {"lookup", "query", "resolve"}:
            command.add_argument("--catalog-sha256")
        if name == "lookup":
            command.add_argument("--kind", required=True)
            command.add_argument("--key", required=True)
        elif name == "resolve":
            command.add_argument("--claim-id", required=True)
            command.add_argument("--evidence-ordinal", type=int, required=True)
        elif name == "query":
            command.add_argument("--text", required=True)
            command.add_argument("--scope", default="all")
            command.add_argument("--paper-id")
            command.add_argument("--assessment", default="all")
            command.add_argument("--lifecycle", default="active")
            command.add_argument("--limit", type=int, default=20)
            command.add_argument("--offset", type=int, default=0)

    code_map = _add_parser(sub, "code-map")
    code_map_sub = code_map.add_subparsers(dest="code_map_cmd", required=True)
    code_map_plan = _add_parser(code_map_sub, "plan")
    code_map_plan.set_defaults(_vpkb_family="code-map")
    _add_plan_flags(code_map_plan)
    code_map_prepare = _add_parser(code_map_sub, "prepare")
    code_map_prepare.set_defaults(_vpkb_family="code-map")
    _add_prepare_flags(code_map_prepare)
    code_map_prepare.add_argument("--source-path", required=True)
    code_inspect = _add_parser(code_map_sub, "inspect")
    for flag in ("prepared", "operation-id", "upstream-root", "vault-root"):
        code_inspect.add_argument("--"+flag, dest=flag.replace("-","_"), required=True)
    code_inspect.set_defaults(handler=run_code_inspect_command)

    index = _add_parser(sub, "index")
    index_sub = index.add_subparsers(dest="index_cmd", required=True)
    index_status = _add_parser(index_sub, "status"); index_status.add_argument("--vault-root", required=True); index_status.add_argument("--upstream-root", required=True); index_status.add_argument("--config",required=True); index_status.set_defaults(handler=domain_commands.index_status)

    query = _add_parser(sub, "query")
    query.add_argument("--json", action="store_true")
    query.add_argument("--text", required=True)
    query.add_argument("--vault-root", required=True); query.add_argument("--upstream-root", required=True)
    query.add_argument("--config",required=True)
    query.set_defaults(handler=_cmd_query)

    catalog = _add_parser(sub,"catalog");catalog_sub=catalog.add_subparsers(dest="catalog_cmd",required=True)
    catalog_report=_add_parser(catalog_sub,"report");catalog_report.add_argument("--json",action="store_true",required=True);catalog_report.add_argument("--vault-root",required=True);catalog_report.add_argument("--upstream-root",required=True);catalog_report.add_argument("--config",required=True);catalog_report.add_argument("--kind",required=True,choices=("code-openness","paper-lifecycle","evidence-coverage"));catalog_report.add_argument("--paper-id");catalog_report.set_defaults(handler=domain_commands.catalog_report)

    audit = _add_parser(sub, "audit")
    audit.add_argument("--vault-root", required=True); audit.add_argument("--upstream-root", required=True); audit.add_argument("--as-of")
    audit.set_defaults(handler=domain_commands.audit)

    compile_cmd = _add_parser(sub, "compile"); compile_sub=compile_cmd.add_subparsers(dest="compile_cmd",required=True)
    compile_validate=_add_parser(compile_sub,"validate");compile_validate.add_argument("--path",required=True);compile_validate.set_defaults(handler=domain_commands.compile_validate)
    compile_render=_add_parser(compile_sub,"render");compile_render.add_argument("--path",required=True);compile_render.add_argument("--batch-id",required=True);compile_render.set_defaults(handler=domain_commands.compile_render)
    evidence=_add_parser(sub,"evidence"); evidence_sub=evidence.add_subparsers(dest="evidence_cmd",required=True)
    evidence_join=_add_parser(evidence_sub,"join");evidence_join.add_argument("--path",required=True);evidence_join.add_argument("--vault-root",required=True);evidence_join.set_defaults(handler=domain_commands.evidence_join)
    retrieval=_add_parser(sub,"retrieval");retrieval_sub=retrieval.add_subparsers(dest="retrieval_cmd",required=True)
    rv=_add_parser(retrieval_sub,"validate")
    for flag in ("config","gold","inventory"):rv.add_argument("--"+flag,required=True)
    rv.set_defaults(handler=domain_commands.retrieval_validate)
    reval=_add_parser(retrieval_sub,"evaluate")
    for flag in ("gold","inventory","config","mapping","results"):reval.add_argument("--"+flag,required=True)
    reval.set_defaults(handler=domain_commands.retrieval_evaluate)
    backup=_add_parser(sub,"backup");backup_sub=backup.add_subparsers(dest="backup_cmd",required=True)
    bm=_add_parser(backup_sub,"manifest");bm.add_argument("--vault-root",required=True);bm.add_argument("--expected-operation-head");bm.add_argument("--expected-claimed-raw");bm.set_defaults(handler=domain_commands.backup_build)
    bv=_add_parser(backup_sub,"verify");bv.add_argument("--restore-root",required=True);bv.add_argument("--source-root",required=True);bv.add_argument("--manifest",required=True);bv.add_argument("--upstream-root",required=True);bv.add_argument("--config",required=True);bv.set_defaults(handler=domain_commands.backup_verify)

    gate=_add_parser(sub,"gate");gate_sub=gate.add_subparsers(dest="gate_cmd",required=True)
    gp=_add_parser(gate_sub,"prepare");gp.add_argument("--decision",required=True);gp.add_argument("--baseline-manifest",required=True);gp.add_argument("--batch-id",required=True);gp.set_defaults(handler=domain_commands.gate_prepare)
    gi=_add_parser(gate_sub,"inspect");gi.add_argument("--prepared",required=True);gi.add_argument("--operation-id",required=True);gi.add_argument("--upstream-root",required=True);gi.add_argument("--vault-root",required=True);gi.set_defaults(handler=domain_commands.gate_inspect)

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
