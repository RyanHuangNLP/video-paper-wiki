"""CLI adapters for experiments compile and publish-inspect. Vault writes are forbidden."""

from __future__ import annotations

import sys

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_publication import DomainPublicationError
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.envelope import emit_error, emit_staging_error
from video_paper_wiki.experiment_comparability import ExperimentComparabilityError
from video_paper_wiki.experiment_publication import (
    COMPILE_COMMAND,
    INSPECT_COMMAND,
    ExperimentPublicationError,
    compile_experiment_publication,
    inspect_experiment_publication,
)
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError


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
    except ExperimentPublicationError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentStoreError as exc:
        return _emit_coded_error(command, exc)
    except ExperimentComparabilityError as exc:
        return _emit_coded_error(command, exc)
    except DomainPublicationError as exc:
        return _emit_coded_error(command, exc)
    except DomainStoreError as exc:
        return _emit_coded_error(command, exc)
    except DomainProposalError as exc:
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


def run_experiments_compile_command(args):
    return _run(
        COMPILE_COMMAND,
        lambda: compile_experiment_publication(
            vault_root=args.vault_root,
            batch_id=args.batch_id,
        ),
    )


def run_experiments_publish_inspect_command(args):
    return _run(
        INSPECT_COMMAND,
        lambda: inspect_experiment_publication(
            prepared=args.prepared,
            vault_root=args.vault_root,
        ),
    )
