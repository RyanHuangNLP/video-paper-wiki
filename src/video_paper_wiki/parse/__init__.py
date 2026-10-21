"""Local PDF parse adapters. Zero network; no model download."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from video_paper_wiki.parse.draft_document import (
    DRAFT_SCHEMA_NAME,
    SECTION_IDS,
    SECTION_SPECS,
    build_draft,
    paper_id_from_sha256,
)


def _force_offline_env() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def parse_pdf_to_draft_fields(pdf_path: Path) -> dict[str, Any]:
    """Docling when extra+models exist; otherwise local pypdf. Never download."""

    from video_paper_wiki.parse.docling_local import ParserUnavailable
    from video_paper_wiki.parse.docling_local import parse_pdf_to_draft_fields as parse_docling

    _force_offline_env()
    try:
        return parse_docling(pdf_path)
    except ParserUnavailable:
        pass

    try:
        from video_paper_wiki.parse.pypdf_local import parse_pdf_to_draft_fields as parse_pypdf
    except ImportError as exc:
        raise ParserUnavailable("parser models are not fetched") from exc

    try:
        return parse_pypdf(pdf_path)
    except ParserUnavailable:
        raise
    except ImportError as exc:
        raise ParserUnavailable("parser models are not fetched") from exc


__all__ = [
    "DRAFT_SCHEMA_NAME",
    "SECTION_IDS",
    "SECTION_SPECS",
    "build_draft",
    "paper_id_from_sha256",
    "parse_pdf_to_draft_fields",
]
