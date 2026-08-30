"""Local PDF parse adapters. Zero network; no model download."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.parse.draft_document import (
    DRAFT_SCHEMA_NAME,
    SECTION_SPECS,
    build_draft,
    paper_id_from_sha256,
)


def parse_pdf_to_draft_fields(pdf_path: Path) -> dict[str, Any]:
    """Lazy-import the local Docling adapter so missing extras stay cheap."""

    from video_paper_wiki.parse.docling_local import parse_pdf_to_draft_fields as _parse

    return _parse(pdf_path)


__all__ = [
    "DRAFT_SCHEMA_NAME",
    "SECTION_SPECS",
    "build_draft",
    "paper_id_from_sha256",
    "parse_pdf_to_draft_fields",
]
