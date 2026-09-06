"""Native pypdf extraction to page-anchored Markdown. No Docling, no blob copy."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError, PdfStreamError

from video_paper_wiki_research.contracts import MANUAL_PDF_INVALID, PARSER_NO_TEXT, ResearchError

SCHEMA = "video-paper-wiki.light-paper.v1"
ENGINE = "pypdf-native-text"
EMPTY_PAGE_WARNING = "page {page} has no native text"
NO_TEXT_MESSAGE = "No native text found. This lightweight path does not run OCR or download models."
DISCLAIMER = (
    "按 PDF 文件页码保留原生文本。未运行 OCR、版面模型或表格重建；"
    "图中内容可能缺失，多栏、公式和表格的文字顺序需对照原 PDF。"
)


def _fail(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise ResearchError(code, message, details)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _normalize_page_text(raw: str | None) -> str:
    text = unicodedata.normalize("NFC", raw or "")
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _read_pdf(pdf_path: Path) -> tuple[Path, bytes, str]:
    source = Path(pdf_path)
    if not source.is_file() or source.is_symlink():
        _fail(MANUAL_PDF_INVALID, "PDF path must be a regular file", {"path": str(source)})
    try:
        data = source.read_bytes()
    except OSError as exc:
        _fail(MANUAL_PDF_INVALID, "PDF is not readable", {"path": str(source)})
        raise AssertionError("unreachable") from exc
    if not data.startswith(b"%PDF-"):
        _fail(MANUAL_PDF_INVALID, "PDF must start with %PDF-", {"path": str(source)})
    digest = _sha256_bytes(data)
    return source.resolve(), data, digest


def _page_texts(data: bytes) -> list[str]:
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, PdfStreamError, OSError, ValueError) as exc:
        _fail(MANUAL_PDF_INVALID, "PDF is not parseable")
        raise AssertionError("unreachable") from exc
    if bool(getattr(reader, "is_encrypted", False)):
        _fail(MANUAL_PDF_INVALID, "Encrypted PDF: provide an unlocked source file")
    try:
        pages = list(reader.pages)
    except FileNotDecryptedError as exc:
        _fail(MANUAL_PDF_INVALID, "Encrypted PDF: provide an unlocked source file")
        raise AssertionError("unreachable") from exc
    except Exception as exc:
        _fail(MANUAL_PDF_INVALID, "PDF is not parseable")
        raise AssertionError("unreachable") from exc
    if not pages:
        _fail(MANUAL_PDF_INVALID, "PDF has no pages")
    return [_normalize_page_text(page.extract_text() or "") for page in pages]


def _build_markdown(title: str, source: Path, digest: str, bodies: list[str]) -> tuple[str, list[dict[str, Any]], list[str]]:
    header = (
        f"# {title}\n"
        f"\n"
        f"原始 PDF：[本机文件](<{source}>)\n"
        f"\n"
        f"SHA-256：`{digest}`\n"
        f"\n"
        f"{DISCLAIMER}\n"
        f"\n"
    )
    markdown = header
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []
    for number, body in enumerate(bodies, start=1):
        markdown += f'<a id="page-{number}"></a>\n\n## PDF 第 {number} 页\n\n'
        start = len(markdown)
        markdown += body
        end = len(markdown)
        markdown += "\n"
        if start == end:
            warnings.append(EMPTY_PAGE_WARNING.format(page=number))
        slice_text = markdown[start:end]
        pages.append(
            {
                "page": number,
                "anchor": f"page-{number}",
                "text_start": start,
                "text_end": end,
                "text_sha256": _sha256_text(slice_text),
            }
        )
    return markdown, pages, warnings


def extract_pdf(pdf_path: Path, workspace_root: Path, *, title: str | None = None) -> dict[str, Any]:
    """Extract native PDF text into workspace/papers/<sha256>/{source.md,source.json}."""

    source, data, digest = _read_pdf(Path(pdf_path))
    bodies = _page_texts(data)
    if not any(bodies):
        _fail(PARSER_NO_TEXT, NO_TEXT_MESSAGE, {"path": str(source)})
    display_title = title.strip() if isinstance(title, str) and title.strip() else source.stem
    markdown, page_records, warnings = _build_markdown(display_title, source, digest, bodies)
    if _sha256_bytes(source.read_bytes()) != digest:
        _fail(MANUAL_PDF_INVALID, "Source PDF changed during extraction", {"path": str(source)})

    workspace = Path(workspace_root)
    paper_dir = workspace / "papers" / digest
    paper_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = paper_dir / "source.md"
    metadata_path = paper_dir / "source.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    markdown_sha = _sha256_bytes(markdown.encode("utf-8"))
    rel_document = f"papers/{digest}/source.md"
    metadata = {
        "schema": SCHEMA,
        "paper_id": f"sha256:{digest}",
        "title": display_title,
        "source": {
            "path": str(source),
            "sha256": digest,
            "size_bytes": len(data),
        },
        "parser": {
            "engine": ENGINE,
            "version": importlib.metadata.version("pypdf"),
        },
        "page_count": len(bodies),
        "document": {"path": rel_document, "sha256": markdown_sha},
        "pages": page_records,
        "warnings": warnings,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "status": "OK",
        "paper_id": metadata["paper_id"],
        "metadata_path": str(metadata_path.resolve()),
        "markdown_path": str(markdown_path.resolve()),
        "page_count": len(bodies),
        "warnings": list(warnings),
    }
