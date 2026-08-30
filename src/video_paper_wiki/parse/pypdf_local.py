"""Local pypdf adapter. Never downloads papers or models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.parse.docling_local import ParserUnavailable


def parse_pdf_to_draft_fields(pdf_path: Path) -> dict[str, Any]:
    """Extract title and body text from a local PDF with pypdf."""

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ParserUnavailable("pypdf is not installed") from exc

    reader = PdfReader(str(pdf_path))
    title = ""
    meta = getattr(reader, "metadata", None)
    if meta is not None:
        raw_title = getattr(meta, "title", None)
        if raw_title:
            title = str(raw_title).strip()

    body_text = ""
    page_no = 1
    for index, page in enumerate(reader.pages, start=1):
        extracted = (page.extract_text() or "").strip()
        if extracted:
            body_text = extracted
            page_no = index
            break

    if not title and body_text:
        for line in body_text.splitlines():
            stripped = line.strip()
            if stripped:
                title = stripped
                break

    return {
        "title": title,
        "title_zh": "",
        "body_text": body_text,
        "page": page_no,
        "parser": "pypdf",
    }
