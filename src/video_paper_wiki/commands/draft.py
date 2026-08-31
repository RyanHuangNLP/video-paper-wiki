"""Draft export and validate. Local blobs only; no model download."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from video_paper_wiki.blob_store import BlobStore, resolve_blob_root
from video_paper_wiki.contracts import SCHEMA_INVALID, ContractError, validate_document
from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.identity import IdentityError
from video_paper_wiki.parse import (
    build_draft,
    parse_pdf_to_draft_fields,
)
from video_paper_wiki.parse.draft_document import InvalidPaperId, resolve_paper_id, validate_paper_id
from video_paper_wiki.parse.docling_local import ParserUnavailable
from video_paper_wiki.parse.title import resolve_draft_title
from video_paper_wiki.staging import StagingError, stage_bytes

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
DRAFT_SCHEMA_NAME = "video-paper-wiki.paper-analysis-draft.v1"
DRAFT_FILENAME = "paper-analysis-draft.v1.json"


def _attr(args: object | None, name: str) -> Any:
    if args is None:
        return None
    return getattr(args, name, None)


def _contract_error(command: str, exc: ContractError | IdentityError) -> int:
    code = str(getattr(exc, "code", SCHEMA_INVALID))
    details = dict(getattr(exc, "details", {}) or {})
    exit_code = int(getattr(exc, "exit_code", 2))
    if code == SCHEMA_INVALID:
        return emit_error(command, "DRAFT_INVALID", str(exc.message), details, exit_code=exit_code)
    return emit_error(command, code, str(exc.message), details, exit_code=exit_code)


def _validate_document(document: object) -> None:
    validate_document(document, expected_schema=DRAFT_SCHEMA_NAME)


def export(_args: object | None = None) -> int:
    raw = _attr(_args, "sha256")
    explicit = _attr(_args, "paper_id")
    batch_id = _attr(_args, "batch_id")
    if batch_id is None:
        return emit_error(
            "draft.export",
            "USAGE",
            "draft.export requires --batch-id",
        )
    if explicit is not None:
        try:
            validate_paper_id(str(explicit))
        except InvalidPaperId:
            return emit_error(
                "draft.export",
                "INVALID_PAPER_ID",
                "paper_id is not a canonical paper ID",
                {"paper_id": str(explicit)},
            )
    if raw is None or str(raw).strip() == "":
        return emit_error(
            "draft.export",
            "USAGE",
            "draft.export requires --sha256",
        )
    sha = str(raw).strip()
    if not SHA256_RE.fullmatch(sha):
        return emit_error(
            "draft.export",
            "INVALID_SHA256",
            "sha256 must be exactly 64 hexadecimal characters",
            {"sha256": sha},
        )
    sha = sha.lower()
    store = BlobStore(resolve_blob_root())
    blob = store.get(sha)
    if blob is None:
        return emit_error(
            "draft.export",
            "BLOB_NOT_FOUND",
            "local blob is missing; fetch is operator-only and this command does not download",
            {"sha256": sha},
        )
    try:
        fields = parse_pdf_to_draft_fields(blob)
    except ParserUnavailable as exc:
        return emit_error(
            "draft.export",
            "PARSER_MODEL_NOT_FETCHED",
            str(exc),
            {"sha256": sha},
        )
    except Exception as exc:
        return emit_error(
            "draft.export",
            "PARSE_FAILED",
            str(exc),
            {"sha256": sha},
        )
    try:
        paper_id = resolve_paper_id(None if explicit is None else str(explicit), sha)
    except InvalidPaperId:
        return emit_error(
            "draft.export",
            "INVALID_PAPER_ID",
            "paper_id is not a canonical paper ID",
            {"paper_id": str(explicit) if explicit is not None else ""},
        )
    except IdentityError as exc:
        return _contract_error("draft.export", exc)
    raw_title = str(fields.get("title") or "")
    page1_text = ""
    raw_pages = fields.get("pages")
    if isinstance(raw_pages, list) and raw_pages:
        first = raw_pages[0]
        if isinstance(first, dict):
            page1_text = str(first.get("text") or "")
    if not page1_text:
        page1_text = str(fields.get("body_text") or "")
    title = resolve_draft_title(paper_id, raw_title, page1_text)
    # pypdf and incomplete Docling parses are preview-only: no publishable claims.
    document = build_draft(
        paper_id=paper_id,
        title=title,
        title_zh=str(fields.get("title_zh", "")),
        claims=[],
    )
    try:
        _validate_document(document)
    except ContractError as exc:
        return _contract_error("draft.export", exc)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    try:
        staged = stage_bytes(
            batch_id=batch_id,
            relative=("draft", DRAFT_FILENAME),
            data=payload.encode("utf-8"),
        )
    except StagingError as exc:
        return emit_staging_error("draft.export", exc)
    return emit_success(
        "draft.export",
        {
            "path": staged.path.as_posix(),
            "paper_id": paper_id,
            "sha256": sha,
            "batch_id": batch_id,
            "already_staged": staged.already_staged,
            "preview_only": True,
        },
    )


def validate(_args: object | None = None) -> int:
    raw = _attr(_args, "path")
    if raw is None or str(raw).strip() == "":
        return emit_error(
            "draft.validate",
            "USAGE",
            "draft.validate requires --path",
        )
    path = Path(str(raw)).expanduser()
    if not path.is_file():
        return emit_error(
            "draft.validate",
            "DRAFT_INVALID",
            "draft file is missing or not a file",
            {"path": str(raw)},
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return emit_error(
            "draft.validate",
            "INVALID_ENCODING",
            "draft file is not valid UTF-8",
            {"path": path.as_posix()},
        )
    except json.JSONDecodeError as exc:
        return emit_error(
            "draft.validate",
            "DRAFT_INVALID",
            f"draft is not valid JSON: {exc.msg}",
            {"path": path.as_posix()},
        )
    try:
        _validate_document(document)
    except ContractError as exc:
        return _contract_error("draft.validate", exc)
    return emit_success(
        "draft.validate",
        {
            "path": path.as_posix(),
            "valid": True,
        },
    )
