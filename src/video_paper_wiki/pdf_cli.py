"""Agent-safe vpwiki pdf leaves. JSON envelope. No Drive upload. No browser."""

from __future__ import annotations

from pathlib import Path

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.pdf_bindings import PdfBindingError, prepare_bindings
from video_paper_wiki.pdf_locations import PREFER_AUTO, PdfLocationError
from video_paper_wiki.pdf_migration import (
    PdfMigrationError,
    build_inventory,
    build_report,
    prepare_migration,
    prepare_unverified_link,
    resolve_from_root,
)
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError

INVENTORY_COMMAND = "pdf.inventory"
PREPARE_COMMAND = "pdf.migrate-prepare"
LINK_COMMAND = "pdf.link-prepare"
RESOLVE_COMMAND = "pdf.resolve"
REPORT_COMMAND = "pdf.migrate-report"
BIND_COMMAND = "pdf.bind-prepare"


def _emit_coded(command: str, exc) -> int:
    details = dict(getattr(exc, "details", {}) or {})
    return emit_error(
        command,
        exc.code,
        getattr(exc, "message", str(exc)),
        details,
        exit_code=int(getattr(exc, "exit_code", 2)),
    )


def _run(command: str, function):
    try:
        return emit_success(command, function())
    except StagingError as exc:
        return emit_staging_error(command, exc)
    except (PdfLocationError, PdfMigrationError, PdfBindingError, ContractError, SecureIOError) as exc:
        return _emit_coded(command, exc)


def run_pdf_inventory_command(args):
    return _run(
        INVENTORY_COMMAND,
        lambda: build_inventory(roots_path=Path(args.roots), batch_id=args.batch_id),
    )


def run_pdf_migrate_prepare_command(args):
    return _run(
        PREPARE_COMMAND,
        lambda: prepare_migration(
            inventory_path=Path(args.inventory),
            manifest_path=Path(args.uploaded_manifest),
            roots_path=Path(args.roots),
            batch_id=args.batch_id,
        ),
    )


def run_pdf_link_prepare_command(args):
    return _run(
        LINK_COMMAND,
        lambda: prepare_unverified_link(
            roots_path=Path(args.roots),
            root_id=args.root_id,
            paper_id=args.paper_id,
            batch_id=args.batch_id,
            drive_file_id=args.drive_file_id,
            drive_url=args.drive_url,
        ),
    )


def run_pdf_resolve_command(args):
    return _run(
        RESOLVE_COMMAND,
        lambda: resolve_from_root(
            roots_path=Path(args.roots),
            root_id=args.root_id,
            paper_id=args.paper_id,
            prefer=args.prefer or PREFER_AUTO,
            offline=bool(args.offline),
            pdf_sha256=args.pdf_sha256,
        ),
    )


def run_pdf_migrate_report_command(args):
    return _run(
        REPORT_COMMAND,
        lambda: build_report(plan_path=Path(args.plan), roots_path=Path(args.roots)),
    )


def run_pdf_bind_prepare_command(args):
    return _run(
        BIND_COMMAND,
        lambda: prepare_bindings(
            roots_path=Path(args.roots),
            root_id=args.root_id,
            request_path=Path(args.request),
            batch_id=args.batch_id,
        ),
    )
