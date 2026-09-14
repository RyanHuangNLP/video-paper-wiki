"""CLI adapter for read-only domain proposal inspect."""

from __future__ import annotations

import sys

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.domain_proposal import (
    COMMAND,
    DomainProposalError,
    inspect_domain_proposal,
)
from video_paper_wiki.envelope import emit_error, emit_staging_error
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError


def run_domain_inspect_command(args):
    command = COMMAND
    try:
        report = inspect_domain_proposal(
            input_path=args.input,
            vault_root=args.vault_root,
            code_batch_id=args.code_batch_id,
        )
        envelope = {"ok": True, "command": command, "data": report}
        sys.stdout.buffer.write(canonicalize(envelope) + b"\n")
        sys.stdout.buffer.flush()
        return 0
    except DomainProposalError as exc:
        return emit_error(
            command,
            exc.code,
            exc.message,
            exc.details,
            exit_code=exc.exit_code,
        )
    except StagingError as exc:
        return emit_staging_error(command, exc)
    except ContractError as exc:
        return emit_error(
            command,
            exc.code,
            exc.message,
            {"instance_pointer": exc.details.get("instance_pointer", ""), "next_action": "repair_input", **exc.details},
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
