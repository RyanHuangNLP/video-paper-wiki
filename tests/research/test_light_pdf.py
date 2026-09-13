from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tests.support import pdf_bytes
from video_paper_wiki_research.contracts import MANUAL_PDF_INVALID, PARSER_NO_TEXT, ResearchError
from video_paper_wiki_research.light_pdf import TRANSACTIONS_DIR, WORKSPACE_INVALID, extract_pdf


def _pdf_with_page_texts(texts: list[str]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)
    for raw in texts:
        page = writer.add_blank_page(width=400, height=400)
        if not raw:
            continue
        payload = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in raw)
        payload = payload.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 24 200 Td ({payload}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        resources = DictionaryObject()
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = font_ref
        resources[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = resources
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _write_pdf(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_multipage_offsets_match_slices(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "paper.pdf", _pdf_with_page_texts(["Alpha page one.", "Beta page two."]))
    workspace = tmp_path / "workspace"
    result = extract_pdf(pdf, workspace, title="Fixture Paper")
    assert result["ok"] is True
    assert result["status"] == "OK"
    assert result["page_count"] == 2
    assert result["warnings"] == []
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert result["paper_id"] == f"sha256:{digest}"
    markdown_path = Path(result["markdown_path"])
    metadata_path = Path(result["metadata_path"])
    assert markdown_path.is_absolute() and metadata_path.is_absolute()
    assert markdown_path.parent == workspace / "papers" / digest
    markdown = markdown_path.read_text(encoding="utf-8")
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert meta["schema"] == "video-paper-wiki.light-paper.v1"
    assert meta["document"]["path"] == f"papers/{digest}/source.md"
    assert meta["document"]["sha256"] == hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    assert '<a id="page-1"></a>' in markdown
    assert '<a id="page-2"></a>' in markdown
    assert "## PDF 第 1 页" in markdown
    bodies = []
    for row in meta["pages"]:
        slice_text = markdown[row["text_start"] : row["text_end"]]
        bodies.append(slice_text)
        assert hashlib.sha256(slice_text.encode("utf-8")).hexdigest() == row["text_sha256"]
        assert "## PDF" not in slice_text
        assert "<a id=" not in slice_text
        assert row["anchor"] == f"page-{row['page']}"
    assert "Alpha page one." in bodies[0]
    assert "Beta page two." in bodies[1]
    listed = {path.name for path in markdown_path.parent.iterdir()}
    assert listed == {"source.md", "source.json"}


def test_mixed_empty_page_keeps_offset_and_warning(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "mixed.pdf", _pdf_with_page_texts(["Only first page has text.", ""]))
    workspace = tmp_path / "ws"
    result = extract_pdf(pdf, workspace)
    assert result["ok"] is True
    assert result["page_count"] == 2
    assert "page 2 has no native text" in result["warnings"]
    meta = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    empty = meta["pages"][1]
    assert empty["text_start"] == empty["text_end"]
    assert hashlib.sha256(b"").hexdigest() == empty["text_sha256"]
    assert markdown[empty["text_start"] : empty["text_end"]] == ""


def test_all_empty_pdf_is_refused(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "blank.pdf", pdf_bytes(pages=2))
    with pytest.raises(ResearchError) as caught:
        extract_pdf(pdf, tmp_path / "ws")
    assert caught.value.code == PARSER_NO_TEXT
    papers = tmp_path / "ws" / "papers"
    assert not papers.exists() or not any(papers.rglob("source.md"))


def test_invalid_and_encrypted_pdf_are_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-not-a-document")
    with pytest.raises(ResearchError) as invalid:
        extract_pdf(bad, tmp_path / "ws")
    assert invalid.value.code == MANUAL_PDF_INVALID
    enc = tmp_path / "enc.pdf"
    enc.write_bytes(pdf_bytes(pages=1, encrypt=True))
    with pytest.raises(ResearchError) as encrypted:
        extract_pdf(enc, tmp_path / "ws")
    assert encrypted.value.code == MANUAL_PDF_INVALID


def test_rerun_overwrites_same_paper_dir_without_clobbering_notes(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "same.pdf", _pdf_with_page_texts(["Stable native text."]))
    workspace = tmp_path / "ws"
    other = workspace / "papers" / "other-note"
    other.mkdir(parents=True)
    keep = other / "keep.md"
    keep.write_text("do not delete\n", encoding="utf-8")
    first = extract_pdf(pdf, workspace, title="Once")
    paper_dir = Path(first["markdown_path"]).parent
    extra = paper_dir / "user-note.md"
    extra.write_text("local note\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in paper_dir.iterdir()}
    second = extract_pdf(pdf, workspace, title="Once")
    assert second["markdown_path"] == first["markdown_path"]
    assert second["paper_id"] == first["paper_id"]
    names = sorted(path.name for path in paper_dir.iterdir())
    assert names == ["source.json", "source.md", "user-note.md"]
    assert extra.read_text(encoding="utf-8") == "local note\n"
    assert keep.read_text(encoding="utf-8") == "do not delete\n"
    assert not list(paper_dir.glob("*.pdf"))
    assert not list(workspace.rglob("*.png"))
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == second["paper_id"].split(":", 1)[1]
    assert Path(second["markdown_path"]).read_bytes() == before["source.md"]
    assert list(workspace.rglob("*.pdf")) == []


def test_repeat_add_keeps_edited_markdown_and_reports_reuse(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "same.pdf", _pdf_with_page_texts(["Stable native text."]))
    workspace = tmp_path / "ws"
    first = extract_pdf(pdf, workspace, title="Once")
    assert first["disposition"] == "created"
    markdown_path = Path(first["markdown_path"])
    metadata_path = Path(first["metadata_path"])
    edited = markdown_path.read_text(encoding="utf-8") + "\n\n人工笔记：保留这段。\n"
    markdown_path.write_text(edited, encoding="utf-8")
    before_md = markdown_path.read_bytes()
    before_json = metadata_path.read_bytes()
    second = extract_pdf(pdf, workspace)
    assert second["ok"] is True
    assert second["disposition"] == "reused"
    assert second["markdown_path"] == first["markdown_path"]
    assert markdown_path.read_bytes() == before_md
    assert metadata_path.read_bytes() == before_json
    listed = {path.name for path in markdown_path.parent.iterdir() if path.is_file() and not path.is_symlink()}
    assert listed == {"source.md", "source.json"}


def test_explicit_title_conflicts_default_title_does_not(tmp_path: Path) -> None:
    data = _pdf_with_page_texts(["Title conflict body."])
    first_pdf = _write_pdf(tmp_path / "paper.pdf", data)
    workspace = tmp_path / "ws"
    first = extract_pdf(first_pdf, workspace, title="Canonical")
    paper_dir = Path(first["markdown_path"]).parent
    before = {path.name: path.read_bytes() for path in paper_dir.iterdir()}
    conflict = extract_pdf(first_pdf, workspace, title="Different")
    assert conflict["ok"] is False
    assert conflict["status"] == "LIGHT_PAPER_CONFLICT"
    assert {path.name: path.read_bytes() for path in paper_dir.iterdir()} == before
    other = _write_pdf(tmp_path / "copy.pdf", data)
    reused = extract_pdf(other, workspace)
    assert reused["ok"] is True
    assert reused["disposition"] == "reused"
    meta = json.loads((paper_dir / "source.json").read_text(encoding="utf-8"))
    assert meta["title"] == "Canonical"
    assert meta["source"]["path"] == str(first_pdf.resolve())
    assert {path.name: path.read_bytes() for path in paper_dir.iterdir()} == before


def test_unicode_title_and_stale_metadata_are_reused(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "unicode.pdf", _pdf_with_page_texts(["Unicode page one.", ""]))
    workspace = tmp_path / "ws"
    first = extract_pdf(pdf, workspace, title="论文-α-测试")
    assert first["ok"] is True
    assert "page 2 has no native text" in first["warnings"]
    markdown_path = Path(first["markdown_path"])
    metadata_path = Path(first["metadata_path"])
    markdown = markdown_path.read_text(encoding="utf-8") + "\n补充。\n"
    markdown_path.write_text(markdown, encoding="utf-8")
    before_md = markdown_path.read_bytes()
    before_json = metadata_path.read_bytes()
    second = extract_pdf(pdf, workspace, title="论文-α-测试")
    assert second["disposition"] == "reused"
    assert second["page_count"] == 2
    assert markdown_path.read_bytes() == before_md
    assert metadata_path.read_bytes() == before_json


def test_identity_mismatch_is_refused_without_rewrite(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "id.pdf", _pdf_with_page_texts(["Identity body."]))
    workspace = tmp_path / "ws"
    first = extract_pdf(pdf, workspace, title="Identity")
    meta_path = Path(first["metadata_path"])
    markdown_path = Path(first["markdown_path"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["source"]["sha256"] = "0" * 64
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    before_md = markdown_path.read_bytes()
    before_json = meta_path.read_bytes()
    refused = extract_pdf(pdf, workspace, title="Identity")
    assert refused["ok"] is False
    assert refused["status"] == "SOURCE_INVALID"
    assert markdown_path.read_bytes() == before_md
    assert meta_path.read_bytes() == before_json


def test_malformed_utf8_is_refused_and_preserved(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "utf8.pdf", _pdf_with_page_texts(["Valid native text."]))
    workspace = tmp_path / "ws"
    first = extract_pdf(pdf, workspace, title="UTF8")
    markdown_path = Path(first["markdown_path"])
    metadata_path = Path(first["metadata_path"])
    metadata_before = metadata_path.read_bytes()
    markdown_path.write_bytes(b"\xff")
    refused = extract_pdf(pdf, workspace, title="UTF8")
    assert refused["ok"] is False
    assert refused["status"] == "SOURCE_INVALID"
    assert markdown_path.read_bytes() == b"\xff"
    assert metadata_path.read_bytes() == metadata_before


def test_transaction_symlink_is_refused_without_outside_writes(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "link.pdf", _pdf_with_page_texts(["Symlink lock body."]))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("outside-bytes\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in outside.iterdir()}
    (workspace / TRANSACTIONS_DIR).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ResearchError) as caught:
        extract_pdf(pdf, workspace, title="Link")
    assert caught.value.code == WORKSPACE_INVALID
    assert {path.name: path.read_bytes() for path in outside.iterdir()} == before
    assert not any(path.suffix == ".lock" for path in outside.iterdir())
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert not (workspace / "papers" / digest).exists()
