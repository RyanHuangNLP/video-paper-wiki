"""Operator notes-vault PDF bind-apply and bind-rollback. No Drive upload."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.pdf_bindings import apply_bind_plan, rollback_bind_journal


def apply_pdf_bindings(
    *,
    plan_path: Path,
    roots_path: Path,
    root_id: str,
    approved_plan_sha256: str,
    confirm,
) -> dict[str, Any]:
    accepted = bool(
        confirm(
            {
                "plan_sha256": approved_plan_sha256,
                "root_id": root_id,
                "kind": "notes-vault",
                "operation": "bind-apply",
            }
        )
    )
    return apply_bind_plan(
        plan_path=plan_path,
        roots_path=roots_path,
        root_id=root_id,
        approved_plan_sha256=approved_plan_sha256,
        confirm=accepted,
    )


def rollback_pdf_bindings(*, journal_path: Path, roots_path: Path, confirm) -> dict[str, Any]:
    summary = {"journal_path": str(journal_path), "operation": "bind-rollback"}
    accepted = bool(confirm(summary))
    _ = canonicalize(summary)
    return rollback_bind_journal(journal_path=journal_path, roots_path=roots_path, confirm=accepted)
