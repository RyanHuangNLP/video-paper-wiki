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
from video_paper_wiki.code_proof_public import run_code_evidence_command
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

    code_evidence = _add_parser(
        sub,
        "code-evidence",
        help="Request, observe, status, config, and handoff for code evidence",
    )
    code_evidence_sub = code_evidence.add_subparsers(
        dest="code_evidence_cmd", required=True
    )
    code_evidence_request = _add_parser(
        code_evidence_sub,
        "request",
        help=(
            "Save an immutable code-evidence request and return host acquisition "
            "targets. Input is a JSON request file. Results are stored under "
            ".work/<batch-id>/code-evidence-v1/. Repeat the same input to reuse a "
            "valid request; recover a changed request with a new batch."
        ),
        description=(
            "Save an immutable code-evidence request and return host acquisition "
            "targets. Input is a JSON request file. Results are stored under "
            ".work/<batch-id>/code-evidence-v1/. Repeat the same input to reuse a "
            "valid request; recover a changed request with a new batch."
        ),
    )
    code_evidence_request.add_argument("--input", required=True)
    code_evidence_request.add_argument("--batch-id", required=True)
    code_evidence_request.set_defaults(handler=run_code_evidence_command)
    code_evidence_observe = _add_parser(
        code_evidence_sub,
        "observe",
        help=(
            "Validate an external acquisition record and save evidence. Raw mode "
            "requires --bundle-dir; normalized mode forbids it. Results are stored "
            "under .work/<batch-id>/code-evidence-v1/. Interrupted installs resume "
            "from the same bound inputs; a changed acquisition needs a new batch."
        ),
        description=(
            "Validate an external acquisition record and save evidence. Raw mode "
            "requires --bundle-dir; normalized mode forbids it. Results are stored "
            "under .work/<batch-id>/code-evidence-v1/. Interrupted installs resume "
            "from the same bound inputs; a changed acquisition needs a new batch."
        ),
    )
    code_evidence_observe.add_argument("--input", required=True)
    code_evidence_observe.add_argument("--bundle-dir")
    code_evidence_observe.add_argument("--batch-id", required=True)
    code_evidence_observe.set_defaults(handler=run_code_evidence_command)
    code_evidence_status = _add_parser(
        code_evidence_sub,
        "status",
        help=(
            "Read-only report of code-evidence state, missing files, and the next "
            "action. This command never creates or repairs files. Recover by "
            "repeating request or observe with the original bound inputs."
        ),
        description=(
            "Read-only report of code-evidence state, missing files, and the next "
            "action. This command never creates or repairs files. Recover by "
            "repeating request or observe with the original bound inputs."
        ),
    )
    code_evidence_status.add_argument("--batch-id", required=True)
    code_evidence_status.set_defaults(handler=run_code_evidence_command)
    code_evidence_config = _add_parser(
        code_evidence_sub,
        "config",
        help=(
            "Derive a configuration record from saved raw evidence for one requested "
            "path. Input is a logical git path and json, toml, or source-only format. "
            "Results are stored under .work/<batch-id>/code-evidence-v1/configs/. "
            "Repeat the same path and format to reuse; a different format needs a new batch."
        ),
        description=(
            "Derive a configuration record from saved raw evidence for one requested "
            "path. Input is a logical git path and json, toml, or source-only format. "
            "Results are stored under .work/<batch-id>/code-evidence-v1/configs/. "
            "Repeat the same path and format to reuse; a different format needs a new batch."
        ),
    )
    code_evidence_config.add_argument("--path", required=True)
    code_evidence_config.add_argument(
        "--format",
        dest="format",
        required=True,
        choices=("json", "toml", "source-only"),
    )
    code_evidence_config.add_argument("--batch-id", required=True)
    code_evidence_config.set_defaults(handler=run_code_evidence_command)
    code_evidence_handoff = _add_parser(
        code_evidence_sub,
        "handoff",
        help=(
            "Validate the complete source-text target set and write successor-only "
            "handoff records. Results are stored under "
            ".work/<batch-id>/code-evidence-v1/handoffs/ and reference existing body "
            "files. Interrupted handoffs resume as a path prefix; do not repair or force."
        ),
        description=(
            "Validate the complete source-text target set and write successor-only "
            "handoff records. Results are stored under "
            ".work/<batch-id>/code-evidence-v1/handoffs/ and reference existing body "
            "files. Interrupted handoffs resume as a path prefix; do not repair or force."
        ),
    )
    code_evidence_handoff.add_argument("--batch-id", required=True)
    code_evidence_handoff.set_defaults(handler=run_code_evidence_command)

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

    from video_paper_wiki.domain_proposal_cli import run_domain_inspect_command
    from video_paper_wiki.domain_publication_cli import (
        run_domain_compile_command,
        run_domain_publish_inspect_command,
    )
    from video_paper_wiki.domain_relations_cli import run_domain_relations_command
    from video_paper_wiki.domain_structure_cli import run_domain_structure_command
    from video_paper_wiki.domain_claims_cli import run_domain_claims_command
    from video_paper_wiki.domain_versions_cli import run_domain_versions_command
    from video_paper_wiki.domain_store_cli import (
        run_domain_record_command,
        run_domain_review_command,
        run_domain_status_command,
    )
    from video_paper_wiki.experiment_store_cli import (
        run_experiments_record_command,
        run_experiments_status_command,
    )
    from video_paper_wiki.experiment_publication_cli import (
        run_experiments_compile_command,
        run_experiments_publish_inspect_command,
    )
    from video_paper_wiki.experiment_matrix_cli import run_experiments_matrix_command
    from video_paper_wiki.graph_cli import (
        run_graph_project_command,
        run_graph_query_command,
    )
    from video_paper_wiki.article_cli import (
        run_articles_check_command,
        run_articles_export_command,
        run_articles_history_command,
        run_articles_import_command,
        run_articles_render_command,
        run_articles_status_command,
    )
    from video_paper_wiki.article_publication_cli import (
        run_articles_compile_command,
        run_articles_publish_inspect_command,
    )
    from video_paper_wiki.reading.cli import run_reading_build_command
    from video_paper_wiki.reading_publication_cli import (
        run_reading_compile_command,
        run_reading_publish_inspect_command,
    )
    domain = _add_parser(
        sub,
        "domain",
        help="Read-only domain annotation and paper-code relation candidate inspect",
        description=(
            "Read-only domain proposal inspect. Input is a closed versioned proposal. "
            "The command reads one paper source version and one repository commit from "
            "existing source and code-evidence authority. JSON is written to stdout. "
            "Output is proposal-only, unpublished, and pending semantic review. "
            "This command does not write a Vault, create a fact store, or publish a current head."
        ),
    )
    domain_sub = domain.add_subparsers(dest="domain_cmd", required=True)
    domain_inspect = _add_parser(
        domain_sub,
        "inspect",
        help=(
            "Validate a domain proposal against existing source, claim, and C2 handoff "
            "authority. JSON report to stdout. Repeat the same input for identical bytes."
        ),
        description=(
            "Validate a domain proposal against existing source, claim, and C2 handoff "
            "authority. Input is --input JSON. Source records are read from --vault-root. "
            "Code evidence is read from --code-batch-id under .work/<batch-id>/code-evidence-v1/. "
            "The command is read-only: it does not write the Vault or code-evidence tree. "
            "The report is proposal-only, unpublished, and pending semantic review. "
            "Repair a refused proposal and repeat inspect; do not force officiality."
        ),
    )
    domain_inspect.add_argument("--input", required=True)
    domain_inspect.add_argument("--vault-root", dest="vault_root", required=True)
    domain_inspect.add_argument("--code-batch-id", dest="code_batch_id", required=True)
    domain_inspect.set_defaults(handler=run_domain_inspect_command)
    domain_record = _add_parser(
        domain_sub,
        "record",
        help=(
            "Re-run domain inspect and stage a closed annotation plus derived heads "
            "under .work/<batch-id>/domain/. Does not write the Vault."
        ),
        description=(
            "Re-execute domain inspect on --input, read wiki/meta/domain from "
            "--vault-root, and stage an annotation record plus derived heads under "
            ".work/<batch-id>/domain/. Output is unpublished and pending semantic "
            "review. This command does not write the Vault or publish a current head."
        ),
    )
    domain_record.add_argument("--input", required=True)
    domain_record.add_argument("--vault-root", dest="vault_root", required=True)
    domain_record.add_argument("--code-batch-id", dest="code_batch_id", required=True)
    domain_record.add_argument("--batch-id", dest="batch_id", required=True)
    domain_record.add_argument("--recorded-by", dest="recorded_by", required=True)
    domain_record.add_argument("--recorded-at", dest="recorded_at", required=True)
    domain_record.add_argument("--previous-annotation-id", dest="previous_annotation_id")
    domain_record.set_defaults(handler=run_domain_record_command)
    domain_review = _add_parser(
        domain_sub,
        "review",
        help=(
            "Validate a closed human review decision against the domain store and "
            "stage the review plus derived heads under .work/<batch-id>/domain/. "
            "Does not write the Vault."
        ),
        description=(
            "Load a closed domain-review-decision.v1 from --decision, read "
            "wiki/meta/domain from --vault-root, and stage a review record plus "
            "derived heads under .work/<batch-id>/domain/. This command does not "
            "write the Vault or produce a canonical official fact."
        ),
    )
    domain_review.add_argument("--decision", required=True)
    domain_review.add_argument("--vault-root", dest="vault_root", required=True)
    domain_review.add_argument("--batch-id", dest="batch_id", required=True)
    domain_review.set_defaults(handler=run_domain_review_command)
    domain_status = _add_parser(
        domain_sub,
        "status",
        help=(
            "Read-only domain store status, derived heads, and claim freshness. "
            "JSON to stdout. Does not write the Vault."
        ),
        description=(
            "Read and validate wiki/meta/domain under --vault-root. JSON report of "
            "derived heads, lineage freshness, and typed-fact candidates. The "
            "command is read-only: it does not write the Vault or .work staging. "
            "canonical_official and current_supported_typed_fact remain false."
        ),
    )
    domain_status.add_argument("--vault-root", dest="vault_root", required=True)
    domain_status.set_defaults(handler=run_domain_status_command)
    domain_compile = _add_parser(
        domain_sub,
        "compile",
        help=(
            "Compile a staged domain batch into an unpublished publication request "
            "under .work/<batch-id>/domain-publication/. Does not write the Vault."
        ),
        description=(
            "Read wiki/meta/domain from --vault-root and .work/<batch-id>/domain/, "
            "then stage a closed unpublished domain-publication-request.v1 plus "
            "content under .work/<batch-id>/domain-publication/. The command does "
            "not write the Vault, apply a transaction, or attach receipt, audit, "
            "backup, or transaction authority. canonical_official and "
            "current_supported_typed_fact remain false."
        ),
    )
    domain_compile.add_argument("--vault-root", dest="vault_root", required=True)
    domain_compile.add_argument("--batch-id", dest="batch_id", required=True)
    domain_compile.set_defaults(handler=run_domain_compile_command)
    domain_publish_inspect = _add_parser(
        domain_sub,
        "publish-inspect",
        help=(
            "Read-only inspect of a staged domain publication request. JSON to "
            "stdout. Does not write the Vault or .work staging."
        ),
        description=(
            "Load a closed domain-publication-request.v1 from --prepared, recompute "
            "the write set against --vault-root, and emit a closed unpublished "
            "inspection. The command is read-only: it does not write the Vault or "
            ".work staging. Apply requires a later slice. canonical_official and "
            "current_supported_typed_fact remain false."
        ),
    )
    domain_publish_inspect.add_argument("--prepared", required=True)
    domain_publish_inspect.add_argument("--vault-root", dest="vault_root", required=True)
    domain_publish_inspect.set_defaults(handler=run_domain_publish_inspect_command)
    domain_relations = _add_parser(
        domain_sub,
        "relations",
        help=(
            "Read-only typed paper-repository relation view with Vault byte "
            "recheck, conflict report, and relation history. JSON to stdout. "
            "Does not write the Vault."
        ),
        description=(
            "Read wiki/meta/domain under --vault-root and emit a closed "
            "unpublished domain-relation-view.v1. Optional --paper-id filters "
            "to one paper. The command is read-only: it does not write the "
            "Vault or .work staging. canonical_official and "
            "current_supported_typed_fact remain false."
        ),
    )
    domain_relations.add_argument("--vault-root", dest="vault_root", required=True)
    domain_relations.add_argument("--paper-id", dest="paper_id")
    domain_relations.set_defaults(handler=run_domain_relations_command)
    domain_structure = _add_parser(
        domain_sub,
        "structure",
        help=(
            "Read-only typed concept registry and capability matrix with "
            "absence search scope, history change detection, and divergence "
            "findings. JSON to stdout. Does not write the Vault."
        ),
        description=(
            "Read wiki/meta/domain under --vault-root and emit a closed "
            "unpublished domain-structure-view.v1. Optional --paper-id filters "
            "to one paper. The command is read-only: it does not write the "
            "Vault or .work staging. canonical_official and "
            "current_supported_typed_fact remain false."
        ),
    )
    domain_structure.add_argument("--vault-root", dest="vault_root", required=True)
    domain_structure.add_argument("--paper-id", dest="paper_id")
    domain_structure.set_defaults(handler=run_domain_structure_command)
    domain_claims = _add_parser(
        domain_sub,
        "claims",
        help=(
            "Read-only typed claim-kind coverage view with untyped search "
            "scope, annotation-chain change detection, and divergence "
            "findings. JSON to stdout. Does not write the Vault."
        ),
        description=(
            "Read wiki/meta/domain under --vault-root and emit a closed "
            "unpublished domain-claim-coverage-view.v1. Optional --paper-id "
            "filters to one paper. The command is read-only: it does not write "
            "the Vault or .work staging. canonical_official and "
            "current_supported_typed_fact remain false."
        ),
    )
    domain_claims.add_argument("--vault-root", dest="vault_root", required=True)
    domain_claims.add_argument("--paper-id", dest="paper_id")
    domain_claims.set_defaults(handler=run_domain_claims_command)
    domain_versions = _add_parser(
        domain_sub,
        "versions",
        help=(
            "Read-only typed source-version view with association and captured "
            "source byte recheck, unlabeled search scope, rebind history, and "
            "divergence findings. JSON to stdout. Does not write the Vault."
        ),
        description=(
            "Read wiki/meta/domain under --vault-root and emit a closed "
            "unpublished domain-source-version-view.v1. Optional --paper-id "
            "filters to one paper. The command is read-only: it does not write "
            "the Vault or .work staging. canonical_official and "
            "current_supported_typed_fact remain false."
        ),
    )
    domain_versions.add_argument("--vault-root", dest="vault_root", required=True)
    domain_versions.add_argument("--paper-id", dest="paper_id")
    domain_versions.set_defaults(handler=run_domain_versions_command)

    experiments = _add_parser(
        sub,
        "experiments",
        help=(
            "Record unpublished experiment conditions or read store status. "
            "Does not write the Vault, write canonical official facts, or rank settings."
        ),
        description=(
            "Record unpublished experiment-condition settings under .work staging, "
            "or read wiki/meta/experiments status. These commands do not write the "
            "Vault, write canonical official facts, or rank settings."
        ),
    )
    experiments_sub = experiments.add_subparsers(dest="experiments_cmd", required=True)
    experiments_record = _add_parser(
        experiments_sub,
        "record",
        help=(
            "Stage a closed experiment-condition record plus derived heads under "
            ".work/<batch-id>/experiments/. Does not write the Vault, write "
            "canonical official facts, or rank settings."
        ),
        description=(
            "Load a closed experiment-condition input from --input, read "
            "wiki/meta/experiments from --vault-root, and stage an unpublished "
            "experiment-condition-record.v1 plus derived heads under "
            ".work/<batch-id>/experiments/. The command does not write the Vault, "
            "write canonical official facts, or rank settings."
        ),
    )
    experiments_record.add_argument("--input", required=True)
    experiments_record.add_argument("--vault-root", dest="vault_root", required=True)
    experiments_record.add_argument("--batch-id", dest="batch_id", required=True)
    experiments_record.add_argument("--recorded-by", dest="recorded_by", required=True)
    experiments_record.add_argument("--recorded-at", dest="recorded_at", required=True)
    experiments_record.add_argument("--previous-record-id", dest="previous_record_id")
    experiments_record.set_defaults(handler=run_experiments_record_command)
    experiments_status = _add_parser(
        experiments_sub,
        "status",
        help=(
            "Read-only experiment store status. Does not write the Vault, write "
            "canonical official facts, or rank settings."
        ),
        description=(
            "Read wiki/meta/experiments under --vault-root. JSON report of "
            "condition chains, bindings, and freshness. The command is read-only: "
            "it does not write the Vault or .work staging. It does not write "
            "canonical official facts or rank settings."
        ),
    )
    experiments_status.add_argument("--vault-root", dest="vault_root", required=True)
    experiments_status.add_argument("--paper-id", dest="paper_id")
    experiments_status.set_defaults(handler=run_experiments_status_command)
    experiments_compile = _add_parser(
        experiments_sub,
        "compile",
        help=(
            "Compile a staged experiment batch into an unpublished publication "
            "request under .work/<batch-id>/experiment-publication/. Does not write "
            "the Vault, write canonical official facts, or rank settings. Apply is "
            "only via vpwiki-admin."
        ),
        description=(
            "Read wiki/meta/experiments from --vault-root and "
            ".work/<batch-id>/experiments/, then stage a closed unpublished "
            "experiment-publication-request.v1 plus content under "
            ".work/<batch-id>/experiment-publication/. The command does not write "
            "the Vault, write canonical official facts, or rank settings. Apply is "
            "only via vpwiki-admin."
        ),
    )
    experiments_compile.add_argument("--vault-root", dest="vault_root", required=True)
    experiments_compile.add_argument("--batch-id", dest="batch_id", required=True)
    experiments_compile.set_defaults(handler=run_experiments_compile_command)
    experiments_publish_inspect = _add_parser(
        experiments_sub,
        "publish-inspect",
        help=(
            "Read-only inspect of a staged experiment publication request. Does not "
            "write the Vault or .work staging, write canonical official facts, or "
            "rank settings. Apply is only via vpwiki-admin."
        ),
        description=(
            "Load a closed experiment-publication-request.v1 from --prepared, "
            "recompute the write set against --vault-root, and emit a closed "
            "unpublished inspection. The command is read-only: it does not write "
            "the Vault or .work staging, write canonical official facts, or rank "
            "settings. Apply is only via vpwiki-admin."
        ),
    )
    experiments_publish_inspect.add_argument("--prepared", required=True)
    experiments_publish_inspect.add_argument("--vault-root", dest="vault_root", required=True)
    experiments_publish_inspect.set_defaults(handler=run_experiments_publish_inspect_command)
    experiments_matrix = _add_parser(
        experiments_sub,
        "matrix",
        help=(
            "Read-only experiment comparison matrix. Does not write the Vault or "
            ".work staging, write canonical official facts, or rank settings. Apply "
            "is only via vpwiki-admin."
        ),
        description=(
            "Read wiki/meta/experiments under --vault-root and emit a closed "
            "unpublished experiment-comparison-matrix.v1. Optional --paper-id "
            "filters to one paper. The command is read-only: it does not write the "
            "Vault or .work staging, write canonical official facts, or rank "
            "settings. Apply is only via vpwiki-admin."
        ),
    )
    experiments_matrix.add_argument("--vault-root", dest="vault_root", required=True)
    experiments_matrix.add_argument("--paper-id", dest="paper_id")
    experiments_matrix.set_defaults(handler=run_experiments_matrix_command)

    graph = _add_parser(
        sub,
        "graph",
        help=(
            "Read-only typed relation-graph projection and query. Does not write the "
            "Vault or .work, write canonical official facts, or rank settings. Not a "
            "second fact source. The third ranking-file route consumes a vpwiki query "
            "--json file; generation hashes are echoed, not verified."
        ),
        description=(
            "Read-only typed relation-graph projection and query from D1 and D2 formal "
            "records under --vault-root. JSON to stdout. The commands do not write the "
            "Vault or .work, write canonical official facts, or rank settings. Output is "
            "not a second fact source. The third ranking-file route only consumes a "
            "vpwiki query --json output file; catalog generation hashes are echoed and "
            "not verified."
        ),
    )
    graph_sub = graph.add_subparsers(dest="graph_cmd", required=True)
    graph_project = _add_parser(
        graph_sub,
        "project",
        help=(
            "Read-only typed relation-graph projection. Does not write the Vault or "
            ".work, write canonical official facts, or rank settings. Not a second fact "
            "source."
        ),
        description=(
            "Read wiki/meta/domain and wiki/meta/experiments under --vault-root and emit "
            "a closed unpublished domain-graph-projection.v1. Optional --paper-id filters "
            "to one paper. The command is read-only: it does not write the Vault or .work "
            "staging, write canonical official facts, or rank settings. Output is not a "
            "second fact source."
        ),
    )
    graph_project.add_argument("--vault-root", dest="vault_root", required=True)
    graph_project.add_argument("--paper-id", dest="paper_id")
    graph_project.set_defaults(handler=run_graph_project_command)
    graph_query = _add_parser(
        graph_sub,
        "query",
        help=(
            "Read-only typed graph query with exact/graph/third-route rank fusion. Does "
            "not write the Vault or .work, write canonical official facts, or rank "
            "settings. Not a second fact source. The third ranking-file route consumes a "
            "vpwiki query --json file; generation hashes are echoed, not verified."
        ),
        description=(
            "Read wiki/meta/domain and wiki/meta/experiments under --vault-root, project "
            "the typed relation graph, and emit a closed unpublished domain-graph-query.v1 "
            "for --text. Optional --kind, --concept-kind, --paper-id, --limit, and a "
            "ranking-file path from vpwiki query --json. Generation hashes are echoed "
            "and not verified. The command is "
            "read-only: it does not write the Vault or .work staging, write canonical "
            "official facts, or rank settings. Output is not a second fact source."
        ),
    )
    graph_query.add_argument("--vault-root", dest="vault_root", required=True)
    graph_query.add_argument("--text", required=True)
    graph_query.add_argument(
        "--kind",
        dest="kind",
        choices=("all", "paper", "claim", "concept", "code", "config", "experiment"),
        default="all",
    )
    graph_query.add_argument(
        "--concept-kind",
        dest="concept_kind",
        choices=(
            "Method",
            "Model",
            "ArchitectureComponent",
            "TrainingRecipe",
            "Dataset",
            "Benchmark",
            "InferenceRecipe",
            "EvaluationMetric",
        ),
    )
    graph_query.add_argument("--paper-id", dest="paper_id")
    graph_query.add_argument("--limit", dest="limit", type=int, default=8)
    graph_query.add_argument("--" + "bm" + "25-ranking", dest="ranking_path")
    graph_query.set_defaults(handler=run_graph_query_command)

    articles = _add_parser(
        sub,
        "articles",
        help=(
            "文章上下文 / 修订 / 检查 / 渲染 / 谱系只读或只写 .work/<batch-id>/articles/："
            "不写 Vault、不写 wiki/**/*.md、不写 canonical official、不排优劣、"
            "publication 恒 unpublished；写出 Markdown 不是发布；进 Vault 只经后续 "
            "vpwiki-admin articles apply（本刀未提供）。"
        ),
        description=(
            "文章上下文 / 修订 / 检查 / 渲染 / 谱系只读或只写 .work/<batch-id>/articles/："
            "不写 Vault、不写 wiki/**/*.md、不写 canonical official、不排优劣、"
            "publication 恒 unpublished；写出 Markdown 不是发布；进 Vault 只经后续 "
            "vpwiki-admin articles apply（本刀未提供）。"
        ),
    )
    articles_sub = articles.add_subparsers(dest="articles_cmd", required=True)
    articles_check = _add_parser(
        articles_sub,
        "check",
        help=(
            "Recheck one article revision against current formal records. "
            "文章检查只读：不写 Vault、不写 wiki/**/*.md、不写 canonical official、"
            "不排优劣、publication 恒 unpublished。"
        ),
        description=(
            "Read wiki/meta/articles and optional .work/<batch-id>/articles/ and emit "
            "a closed unpublished article-check.v1. 不写 Vault、不写 wiki/**/*.md、"
            "不写 canonical official、不排优劣、publication 恒 unpublished。"
        ),
    )
    articles_check.add_argument("--vault-root", dest="vault_root", required=True)
    articles_check.add_argument("--article-id", dest="article_id", required=True)
    articles_check.add_argument("--revision-id", dest="revision_id", required=True)
    articles_check.add_argument("--batch-id", dest="batch_id")
    articles_check.set_defaults(handler=run_articles_check_command)
    articles_export = _add_parser(
        articles_sub,
        "export",
        help=(
            "Export a closed article writing context. 文章上下文只读：不写 Vault、"
            "不写 wiki/**/*.md、不写 canonical official、不排优劣、publication 恒 unpublished。"
        ),
        description=(
            "Read D1/D2/D3 formal records under --vault-root and emit a closed "
            "unpublished article-context.v1. 不写 Vault、不写 wiki/**/*.md、"
            "不写 canonical official、不排优劣、publication 恒 unpublished。"
        ),
    )
    articles_export.add_argument("--vault-root", dest="vault_root", required=True)
    articles_export.add_argument("--question", dest="question")
    articles_export.add_argument("--paper-id", dest="paper_ids", action="append")
    articles_export.add_argument("--article-id", dest="article_id")
    articles_export.add_argument("--revision-id", dest="revision_id")
    articles_export.add_argument("--batch-id", dest="batch_id")
    articles_export.add_argument("--section-id", dest="section_id")
    articles_export.add_argument("--instructions", dest="instructions", default="")
    articles_export.set_defaults(handler=run_articles_export_command)
    articles_history = _add_parser(
        articles_sub,
        "history",
        help=(
            "Read one article revision chain. 谱系只读：不写 Vault、不写 wiki/**/*.md、"
            "不写 canonical official、不排优劣、publication 恒 unpublished。"
        ),
        description=(
            "Read wiki/meta/articles and optional .work/<batch-id>/articles/ and list "
            "the revision chain. 不写 Vault、不写 wiki/**/*.md、不写 canonical official、"
            "不排优劣、publication 恒 unpublished。"
        ),
    )
    articles_history.add_argument("--vault-root", dest="vault_root", required=True)
    articles_history.add_argument("--article-id", dest="article_id", required=True)
    articles_history.add_argument("--batch-id", dest="batch_id")
    articles_history.set_defaults(handler=run_articles_history_command)
    articles_import = _add_parser(
        articles_sub,
        "import",
        help=(
            "Validate a model document and stage one article revision under "
            ".work/<batch-id>/articles/. 只写 .work/<batch-id>/articles/：不写 Vault、"
            "不写 wiki/**/*.md、不写 canonical official、不排优劣、publication 恒 unpublished。"
            "进 Vault 只经后续 vpwiki-admin articles apply（本刀未提供）。"
        ),
        description=(
            "Validate a video-paper-wiki.article-document.v1 against an exported context "
            "and stage one revision JSON. 只写 .work/<batch-id>/articles/：不写 Vault、"
            "不写 wiki/**/*.md、不写 canonical official、不排优劣、publication 恒 unpublished。"
            "写出 Markdown 不是发布；进 Vault 只经后续 vpwiki-admin articles apply（本刀未提供）。"
        ),
    )
    articles_import.add_argument("--vault-root", dest="vault_root", required=True)
    articles_import.add_argument("--batch-id", dest="batch_id", required=True)
    articles_import.add_argument("--context", dest="context", required=True)
    articles_import.add_argument("--document", dest="document", required=True)
    articles_import.add_argument("--recorded-by", dest="recorded_by", required=True)
    articles_import.add_argument("--recorded-at", dest="recorded_at", required=True)
    articles_import.add_argument("--previous-revision-id", dest="previous_revision_id")
    articles_import.add_argument("--target-section-id", dest="target_section_id")
    articles_import.add_argument("--instructions", dest="instructions", default="")
    articles_import.set_defaults(handler=run_articles_import_command)
    articles_render = _add_parser(
        articles_sub,
        "render",
        help=(
            "Render one revision to .work/<batch-id>/articles/render/. "
            "写出 Markdown 不是发布；不写 Vault、不写 wiki/**/*.md、不写 canonical official、"
            "不排优劣、publication 恒 unpublished。"
        ),
        description=(
            "Render a stored or staged revision to Markdown under "
            ".work/<batch-id>/articles/render/. 只写 .work/<batch-id>/articles/："
            "不写 Vault、不写 wiki/**/*.md、不写 canonical official、不排优劣、"
            "publication 恒 unpublished。写出 Markdown 不是发布；进 Vault 只经后续 "
            "vpwiki-admin articles apply（本刀未提供）。"
        ),
    )
    articles_render.add_argument("--vault-root", dest="vault_root", required=True)
    articles_render.add_argument("--batch-id", dest="batch_id", required=True)
    articles_render.add_argument("--article-id", dest="article_id", required=True)
    articles_render.add_argument("--revision-id", dest="revision_id", required=True)
    articles_render.set_defaults(handler=run_articles_render_command)
    articles_status = _add_parser(
        articles_sub,
        "status",
        help=(
            "Read article lineage status. 谱系只读：不写 Vault、不写 wiki/**/*.md、"
            "不写 canonical official、不排优劣、publication 恒 unpublished。"
        ),
        description=(
            "Read wiki/meta/articles and optional .work/<batch-id>/articles/ and emit "
            "lineage status. 不写 Vault、不写 wiki/**/*.md、不写 canonical official、"
            "不排优劣、publication 恒 unpublished。"
        ),
    )
    articles_status.add_argument("--vault-root", dest="vault_root", required=True)
    articles_status.add_argument("--batch-id", dest="batch_id")
    articles_status.set_defaults(handler=run_articles_status_command)
    articles_compile = _add_parser(
        articles_sub,
        "compile",
        help=(
            "Compile staged article revisions into an unpublished publication request. "
            "不写 Vault（compile 只写 .work/<batch-id>/article-publication/；"
            "publish-inspect 零写入）、不写 wiki/**/*.md、不写 canonical official、"
            "不排优劣、publication 恒 unpublished；compile 要求每个谱系头 "
            "progress.unwritten == 0 且 check 为 current；apply 只经 vpwiki-admin。"
        ),
        description=(
            "Read .work/<batch-id>/articles/records and emit a closed unpublished "
            "article-publication-request.v1 under .work/<batch-id>/article-publication/. "
            "不写 Vault（compile 只写 .work/<batch-id>/article-publication/；"
            "publish-inspect 零写入）、不写 wiki/**/*.md、不写 canonical official、"
            "不排优劣、publication 恒 unpublished。compile 要求每个谱系头 "
            "progress.unwritten == 0 且 check 为 current；apply 只经 vpwiki-admin。"
        ),
    )
    articles_compile.add_argument("--vault-root", dest="vault_root", required=True)
    articles_compile.add_argument("--batch-id", dest="batch_id", required=True)
    articles_compile.set_defaults(handler=run_articles_compile_command)
    articles_publish_inspect = _add_parser(
        articles_sub,
        "publish-inspect",
        help=(
            "Inspect a staged article publication request. "
            "不写 Vault（compile 只写 .work/<batch-id>/article-publication/；"
            "publish-inspect 零写入）、不写 wiki/**/*.md、不写 canonical official、"
            "不排优劣、publication 恒 unpublished；compile 要求每个谱系头 "
            "progress.unwritten == 0 且 check 为 current；apply 只经 vpwiki-admin。"
        ),
        description=(
            "Read the fixed .work/<batch-id>/article-publication/request.json slot and "
            "recheck it against the current Vault. 不写 Vault（compile 只写 "
            ".work/<batch-id>/article-publication/；publish-inspect 零写入）、"
            "不写 wiki/**/*.md、不写 canonical official、不排优劣、publication 恒 unpublished。"
            "compile 要求每个谱系头 progress.unwritten == 0 且 check 为 current；"
            "apply 只经 vpwiki-admin。"
        ),
    )
    articles_publish_inspect.add_argument("--prepared", dest="prepared", required=True)
    articles_publish_inspect.add_argument("--vault-root", dest="vault_root", required=True)
    articles_publish_inspect.set_defaults(handler=run_articles_publish_inspect_command)

    reading = _add_parser(
        sub,
        "reading",
        help=(
            "只读 D1 / D2 / D3 / S1 正式记录，把阅读页与 manifest 暂存到 `.work/<batch-id>/reading/`；"
            "不写 Vault、不写 `wiki/**`、不 apply、不发布（publication 恒 unpublished）、不排优劣；"
            "进 Vault 走 `vpwiki reading compile` → `vpwiki reading publish-inspect` → `vpwiki-admin reading apply`（只覆盖带 `generated_by: video-paper-wiki.reading.v1` 标记的生成页，绝不触碰无标记文件与 `wiki/reading-notes/**`）。"
        ),
        description=(
            "只读 D1 / D2 / D3 / S1 正式记录，把阅读页与 manifest 暂存到 `.work/<batch-id>/reading/`；"
            "不写 Vault、不写 `wiki/**`、不 apply、不发布（publication 恒 unpublished）、不排优劣；"
            "进 Vault 走 `vpwiki reading compile` → `vpwiki reading publish-inspect` → `vpwiki-admin reading apply`（只覆盖带 `generated_by: video-paper-wiki.reading.v1` 标记的生成页，绝不触碰无标记文件与 `wiki/reading-notes/**`）。"
        ),
    )
    reading_sub = reading.add_subparsers(dest="reading_cmd", required=True)
    reading_build = _add_parser(
        reading_sub,
        "build",
        help=(
            "只读 D1 / D2 / D3 / S1 正式记录，把阅读页与 manifest 暂存到 `.work/<batch-id>/reading/`；"
            "不写 Vault、不写 `wiki/**`、不 apply、不发布（publication 恒 unpublished）、不排优劣；"
            "进 Vault 走 `vpwiki reading compile` → `vpwiki reading publish-inspect` → `vpwiki-admin reading apply`（只覆盖带 `generated_by: video-paper-wiki.reading.v1` 标记的生成页，绝不触碰无标记文件与 `wiki/reading-notes/**`）。"
        ),
        description=(
            "只读 D1 / D2 / D3 / S1 正式记录，把阅读页与 manifest 暂存到 `.work/<batch-id>/reading/`；"
            "不写 Vault、不写 `wiki/**`、不 apply、不发布（publication 恒 unpublished）、不排优劣；"
            "进 Vault 走 `vpwiki reading compile` → `vpwiki reading publish-inspect` → `vpwiki-admin reading apply`（只覆盖带 `generated_by: video-paper-wiki.reading.v1` 标记的生成页，绝不触碰无标记文件与 `wiki/reading-notes/**`）。"
        ),
    )
    reading_build.add_argument("--vault-root", dest="vault_root", required=True)
    reading_build.add_argument("--batch-id", dest="batch_id", required=True)
    reading_build.add_argument("--paper-id", dest="paper_id", required=False, default=None)
    reading_build.add_argument("--articles-batch", dest="articles_batch", required=False, default=None)
    reading_build.set_defaults(handler=run_reading_build_command)
    reading_compile = _add_parser(
        reading_sub,
        "compile",
        help=(
            "compile 只读 `.work/<batch-id>/reading/**` 与 Vault，只写 `.work/<batch-id>/reading-publication/request.json`；"
            "publish-inspect 零写入；不写 Vault、不写 `wiki/**`、不发布（publication 恒 unpublished）、不排优劣；"
            "apply 只经 `vpwiki-admin reading apply`；只覆盖带标记生成页、不触碰 `wiki/reading-notes/**`。"
        ),
        description=(
            "compile 只读 `.work/<batch-id>/reading/**` 与 Vault，只写 `.work/<batch-id>/reading-publication/request.json`；"
            "publish-inspect 零写入；不写 Vault、不写 `wiki/**`、不发布（publication 恒 unpublished）、不排优劣；"
            "apply 只经 `vpwiki-admin reading apply`；只覆盖带标记生成页、不触碰 `wiki/reading-notes/**`。"
        ),
    )
    reading_compile.add_argument("--vault-root", dest="vault_root", required=True)
    reading_compile.add_argument("--batch-id", dest="batch_id", required=True)
    reading_compile.set_defaults(handler=run_reading_compile_command)
    reading_publish_inspect = _add_parser(
        reading_sub,
        "publish-inspect",
        help=(
            "compile 只读 `.work/<batch-id>/reading/**` 与 Vault，只写 `.work/<batch-id>/reading-publication/request.json`；"
            "publish-inspect 零写入；不写 Vault、不写 `wiki/**`、不发布（publication 恒 unpublished）、不排优劣；"
            "apply 只经 `vpwiki-admin reading apply`；只覆盖带标记生成页、不触碰 `wiki/reading-notes/**`。"
        ),
        description=(
            "compile 只读 `.work/<batch-id>/reading/**` 与 Vault，只写 `.work/<batch-id>/reading-publication/request.json`；"
            "publish-inspect 零写入；不写 Vault、不写 `wiki/**`、不发布（publication 恒 unpublished）、不排优劣；"
            "apply 只经 `vpwiki-admin reading apply`；只覆盖带标记生成页、不触碰 `wiki/reading-notes/**`。"
        ),
    )
    reading_publish_inspect.add_argument("--prepared", dest="prepared", required=True)
    reading_publish_inspect.add_argument("--vault-root", dest="vault_root", required=True)
    reading_publish_inspect.set_defaults(handler=run_reading_publish_inspect_command)

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

    from video_paper_wiki.pdf_cli import (
        run_pdf_inventory_command,
        run_pdf_link_prepare_command,
        run_pdf_migrate_prepare_command,
        run_pdf_migrate_report_command,
        run_pdf_resolve_command,
    )
    pdf = _add_parser(
        sub,
        "pdf",
        help="PDF location inventory, link prepare, resolve, and migration report. No upload.",
        description=(
            "Read-only inventory and resolve, plus staging of link plans under "
            ".work/<batch-id>/pdf-migration/. Commands do not upload to Drive, start a "
            "browser, or mutate a Vault. Apply, open, and rollback are vpwiki-admin only."
        ),
    )
    pdf_sub = pdf.add_subparsers(dest="pdf_cmd", required=True)
    pdf_inventory = _add_parser(pdf_sub, "inventory")
    pdf_inventory.add_argument("--roots", required=True)
    pdf_inventory.add_argument("--batch-id", dest="batch_id", required=True)
    pdf_inventory.set_defaults(handler=run_pdf_inventory_command)
    pdf_prepare = _add_parser(pdf_sub, "migrate-prepare")
    pdf_prepare.add_argument("--inventory", required=True)
    pdf_prepare.add_argument("--uploaded-manifest", dest="uploaded_manifest", required=True)
    pdf_prepare.add_argument("--roots", required=True)
    pdf_prepare.add_argument("--batch-id", dest="batch_id", required=True)
    pdf_prepare.set_defaults(handler=run_pdf_migrate_prepare_command)
    pdf_link = _add_parser(pdf_sub, "link-prepare")
    pdf_link.add_argument("--roots", required=True)
    pdf_link.add_argument("--root-id", dest="root_id", required=True)
    pdf_link.add_argument("--paper-id", dest="paper_id", required=True)
    pdf_link.add_argument("--drive-file-id", dest="drive_file_id")
    pdf_link.add_argument("--drive-url", dest="drive_url")
    pdf_link.add_argument("--batch-id", dest="batch_id", required=True)
    pdf_link.set_defaults(handler=run_pdf_link_prepare_command)
    pdf_resolve = _add_parser(pdf_sub, "resolve")
    pdf_resolve.add_argument("--roots", required=True)
    pdf_resolve.add_argument("--root-id", dest="root_id", required=True)
    pdf_resolve.add_argument("--paper-id", dest="paper_id", required=True)
    pdf_resolve.add_argument("--prefer", choices=("auto", "local", "drive"), default="auto")
    pdf_resolve.add_argument("--offline", action="store_true")
    pdf_resolve.add_argument("--pdf-sha256", dest="pdf_sha256")
    pdf_resolve.set_defaults(handler=run_pdf_resolve_command)
    pdf_report = _add_parser(pdf_sub, "migrate-report")
    pdf_report.add_argument("--plan", required=True)
    pdf_report.add_argument("--roots", required=True)
    pdf_report.set_defaults(handler=run_pdf_migrate_report_command)

    from video_paper_wiki.flow.cli import run_flow_prepare_command, run_flow_select_command, run_flow_status_command
    _flow_help=("只读正式记录与本会话 `.work/<batch-id>/flow/` 暂存，生成进度、缺失输入与下一步命令；" "不写 Vault、不 apply、不发布（publication 恒 unpublished）、不排优劣；" "进 Vault 仍需各功能自己的 `vpwiki-admin … apply`（本命令不提供）")
    flow=_add_parser(sub,"flow",help=_flow_help,description=_flow_help)
    flow_sub=flow.add_subparsers(dest="flow_cmd",required=True)
    flow_status=_add_parser(flow_sub,"status",help=_flow_help,description=_flow_help)
    flow_status.add_argument("--vault-root",dest="vault_root",required=True)
    flow_status.add_argument("--batch-id",dest="batch_id")
    flow_status.add_argument("--paper-id",dest="paper_id")
    flow_status.set_defaults(handler=run_flow_status_command)
    flow_select=_add_parser(flow_sub,"select",help=_flow_help,description=_flow_help)
    flow_select.add_argument("--vault-root",dest="vault_root",required=True)
    flow_select.add_argument("--batch-id",dest="batch_id",required=True)
    flow_select.add_argument("--paper-id",dest="paper_ids",action="append",required=True)
    flow_select.add_argument("--association-id",dest="association_id")
    flow_select.add_argument("--question",dest="question")
    flow_select.set_defaults(handler=run_flow_select_command)
    flow_prepare=_add_parser(flow_sub,"prepare",help=_flow_help,description=_flow_help)
    flow_prepare.add_argument("--vault-root",dest="vault_root",required=True)
    flow_prepare.add_argument("--batch-id",dest="batch_id",required=True)
    flow_prepare.add_argument("--kind",dest="kind",choices=("experiment","article"),required=True)
    flow_prepare.add_argument("--setting-key",dest="setting_key")
    flow_prepare.add_argument("--paper-id",dest="paper_ids",action="append")
    flow_prepare.add_argument("--question",dest="question")
    flow_prepare.set_defaults(handler=run_flow_prepare_command)

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
