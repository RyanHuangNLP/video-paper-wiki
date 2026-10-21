"""CLI adapters for domain record, review, and status. Vault writes are forbidden."""

from __future__ import annotations

import sys

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_store import (
    RECORD_COMMAND,
    REVIEW_COMMAND,
    STATUS_COMMAND,
    DomainStoreError,
    record_domain_annotation,
    review_domain_annotation,
    status_domain_store,
)
from video_paper_wiki.envelope import emit_error, emit_staging_error
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError


def _emit_success(command, data):
    envelope = {"ok": True, "command": command, "data": data}
    sys.stdout.buffer.write(canonicalize(envelope) + b"\n")
    sys.stdout.buffer.flush()
    return 0


def _emit_domain_error(command, exc):
    return emit_error(
        command,
        exc.code,
        exc.message,
        exc.details,
        exit_code=exc.exit_code,
    )


def _run(command, function):
    try:
        return _emit_success(command, function())
    except DomainStoreError as exc:
        return _emit_domain_error(command, exc)
    except DomainProposalError as exc:
        return _emit_domain_error(command, exc)
    except StagingError as exc:
        return emit_staging_error(command, exc)
    except ContractError as exc:
        return emit_error(
            command,
            exc.code,
            exc.message,
            {
                "instance_pointer": exc.details.get("instance_pointer", ""),
                "next_action": "repair_input",
                **exc.details,
            },
            exit_code=getattr(exc, "exit_code", 2),
        )
    except SecureIOError as exc:
        return emit_error(
            command,
            exc.code,
            exc.message,
            {"instance_pointer": "/input", "next_action": "repair_input", **exc.details},
            exit_code=getattr(exc, "exit_code", 2),
        )


def run_domain_record_command(args):
    return _run(
        RECORD_COMMAND,
        lambda: record_domain_annotation(
            input_path=args.input,
            vault_root=args.vault_root,
            code_batch_id=args.code_batch_id,
            batch_id=args.batch_id,
            recorded_by=args.recorded_by,
            recorded_at=args.recorded_at,
            previous_annotation_id=getattr(args, "previous_annotation_id", None),
        ),
    )


def run_domain_review_command(args):
    return _run(
        REVIEW_COMMAND,
        lambda: review_domain_annotation(
            decision_path=args.decision,
            vault_root=args.vault_root,
            batch_id=args.batch_id,
        ),
    )


def run_domain_status_command(args):
    return _run(STATUS_COMMAND, lambda: status_domain_store(vault_root=args.vault_root))
