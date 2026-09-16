"""CLI adapters for flow status, select, and prepare."""

from __future__ import annotations

import sys

from video_paper_wiki.article_context import ArticleContextError
from video_paper_wiki.article_revision import ArticleRevisionError
from video_paper_wiki.article_store import ArticleStoreError
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.domain_versions import DomainVersionsError
from video_paper_wiki.envelope import emit_error, emit_staging_error
from video_paper_wiki.experiment_comparability import ExperimentComparabilityError
from video_paper_wiki.experiment_matrix import ExperimentMatrixError
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.flow.actions import FlowError
from video_paper_wiki.flow.prepare import prepare_flow
from video_paper_wiki.flow.selection import select_flow
from video_paper_wiki.flow.status import build_flow_status
from video_paper_wiki.identity import IdentityError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError

STATUS_COMMAND = "flow.status"
SELECT_COMMAND = "flow.select"
PREPARE_COMMAND = "flow.prepare"


def _emit_success(command, data):
    envelope = {"ok": True, "command": command, "data": data}
    sys.stdout.buffer.write(canonicalize(envelope) + b"\n")
    sys.stdout.buffer.flush()
    return 0


def _emit_coded_error(command, exc):
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
    except FlowError as exc:
        return _emit_coded_error(command, exc)
    except ArticleStoreError as exc:
        return _emit_coded_error(command, exc)
    except ArticleContextError as exc:
        return _emit_coded_error(command, exc)
    except ArticleRevisionError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentMatrixError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentComparabilityError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentStoreError as exc:
        return _emit_coded_error(command, exc)
    except DomainVersionsError as exc:
        return _emit_coded_error(command, exc)
    except DomainStoreError as exc:
        return _emit_coded_error(command, exc)
    except DomainProposalError as exc:
        return _emit_coded_error(command, exc)
    except IdentityError as exc:
        return _emit_coded_error(command, exc)
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


def run_flow_status_command(args):
    return _run(
        STATUS_COMMAND,
        lambda: build_flow_status(
            vault_root=args.vault_root,
            batch_id=getattr(args, "batch_id", None),
            paper_id=getattr(args, "paper_id", None),
        ),
    )


def run_flow_select_command(args):
    return _run(
        SELECT_COMMAND,
        lambda: select_flow(
            vault_root=args.vault_root,
            batch_id=args.batch_id,
            paper_ids=getattr(args, "paper_ids", None),
            association_id=getattr(args, "association_id", None),
            question=getattr(args, "question", None),
        ),
    )


def run_flow_prepare_command(args):
    return _run(
        PREPARE_COMMAND,
        lambda: prepare_flow(
            vault_root=args.vault_root,
            batch_id=args.batch_id,
            kind=args.kind,
            setting_key=getattr(args, "setting_key", None),
            paper_ids=getattr(args, "paper_ids", None),
            question=getattr(args, "question", None),
        ),
    )
