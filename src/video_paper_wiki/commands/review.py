"""Review export: stage markdown under .work/<batch-id>/review/. No apply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from copy import deepcopy

from video_paper_wiki.commands.draft import _contract_error, _validate_document
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.identity import IdentityError, catalog_seed_key, claim_id, is_canonical_paper_id
from video_paper_wiki.notes import paper_note_link_suffix, render_paper_copy_markdown
from video_paper_wiki.notes.encoding import InvalidEncoding, read_utf8
from video_paper_wiki.notes.frozen import FrozenSeedMissing
from video_paper_wiki.parse.draft_document import InvalidPaperId, validate_paper_id_token
from video_paper_wiki.parse.title import catalog_paper_ids
from video_paper_wiki.staging import StagingError, stage_bytes

COMMAND = "review.export"


def _attr(args: object | None, name: str) -> Any:
    if args is None:
        return None
    return getattr(args, name, None)


def _draft_invalid(message: str, details: dict[str, Any] | None = None) -> int:
    return emit_error(COMMAND, "DRAFT_INVALID", message, details)


def _load_draft(path: Path) -> tuple[dict[str, Any] | None, int | None]:
    if not path.is_file():
        return None, _draft_invalid(
            "draft file is missing or not a file",
            {"path": path.as_posix()},
        )
    try:
        document = json.loads(read_utf8(path))
    except InvalidEncoding:
        return None, emit_error(
            COMMAND,
            "INVALID_ENCODING",
            "draft file is not valid UTF-8",
            {"path": path.as_posix()},
        )
    except json.JSONDecodeError as exc:
        return None, _draft_invalid(
            f"draft is not valid JSON: {exc.msg}",
            {"path": path.as_posix()},
        )
    except OSError as exc:
        return None, _draft_invalid(
            "draft file is missing or not a file",
            {"path": path.as_posix(), "reason": str(exc)},
        )
    if not isinstance(document, dict):
        return None, _draft_invalid(
            "draft document must be an object",
            {"path": path.as_posix()},
        )
    if "paper_id" not in document:
        return None, _draft_invalid(
            "draft document must include paper_id",
            {"path": path.as_posix()},
        )
    if "paper_id" in document:
        try:
            validate_paper_id_token(str(document.get("paper_id", "")))
        except InvalidPaperId:
            return None, emit_error(
                COMMAND,
                "INVALID_PAPER_ID",
                "paper_id is empty or not a safe path segment",
                {"paper_id": str(document.get("paper_id", ""))},
            )
    paper_id = str(document.get("paper_id", "")).strip()
    seed_key = catalog_seed_key(paper_id) if paper_id else ""
    if is_canonical_paper_id(paper_id) or seed_key in catalog_paper_ids():
        to_check = deepcopy(document)
        if paper_id.startswith("arxiv-") and not is_canonical_paper_id(paper_id):
            candidate = "arxiv:" + paper_id[len("arxiv-") :]
            if is_canonical_paper_id(candidate):
                to_check["paper_id"] = candidate
        claims = to_check.get("claims")
        if isinstance(claims, list):
            subject = f"paper:{to_check.get('paper_id', '')}"
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                text = claim.get("claim_text")
                if "claim_id" not in claim and isinstance(text, str) and text:
                    claim["claim_id"] = claim_id(subject, text)
        try:
            _validate_document(to_check)
        except ContractError as exc:
            return None, _contract_error(COMMAND, exc)
        except IdentityError as exc:
            return None, _contract_error(COMMAND, exc)
    return document, None


def export(_args: object | None = None) -> int:
    raw = _attr(_args, "draft")
    batch_id = _attr(_args, "batch_id")
    if batch_id is None:
        return emit_error(COMMAND, "USAGE", "review.export requires --batch-id")
    if raw is None or str(raw).strip() == "":
        return emit_error(COMMAND, "USAGE", "review.export requires --draft")
    draft_path = Path(str(raw)).expanduser()
    document, err = _load_draft(draft_path)
    if err is not None:
        return err
    assert document is not None
    try:
        paper_id = validate_paper_id_token(str(document["paper_id"]))
    except InvalidPaperId:
        return emit_error(
            COMMAND,
            "INVALID_PAPER_ID",
            "paper_id is empty or not a safe path segment",
            {"paper_id": str(document.get("paper_id", ""))},
        )
    try:
        markdown = render_paper_copy_markdown(document) + paper_note_link_suffix(paper_id)
    except FrozenSeedMissing as exc:
        return emit_error(
            COMMAND,
            "FROZEN_SEED_MISSING",
            "paper_id is not in the managed seed catalog or a required overlay is missing",
            {"paper_id": paper_id, "source": exc.source},
        )
    try:
        staged = stage_bytes(
            batch_id=batch_id,
            relative=("review", "paper.md"),
            data=markdown.encode("utf-8"),
        )
    except StagingError as exc:
        return emit_staging_error(COMMAND, exc)
    return emit_success(
        COMMAND,
        {
            "path": staged.path.as_posix(),
            "paper_id": paper_id,
            "batch_id": batch_id,
            "already_staged": staged.already_staged,
        },
    )
