"""Local pypdf adapter. Never downloads papers or models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.parse.docling_local import ParserUnavailable

_MAX_PAGES = 20


def parse_pdf_to_draft_fields(pdf_path: Path) -> dict[str, Any]:
    """Extract title and up to 20 pages of body text from a local PDF with pypdf."""

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

    pages: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages[:_MAX_PAGES], start=1):
        extracted = (page.extract_text() or "").strip()
        if extracted:
            pages.append({"page": index, "text": extracted})

    body_text = "\n".join(item["text"] for item in pages)
    page_no = int(pages[0]["page"]) if pages else 1

    if not title:
        source = pages[0]["text"] if pages else body_text
        for line in source.splitlines():
            stripped = line.strip()
            if stripped:
                title = stripped
                break

    return {
        "title": title,
        "title_zh": "",
        "body_text": body_text,
        "page": page_no,
        "pages": pages,
        "parser": "pypdf",
        "preview_only": True,
        "claims": [],
    }
