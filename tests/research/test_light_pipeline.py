from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from video_paper_wiki_research.light_index import build_index, search
from video_paper_wiki_research.light_pdf import extract_pdf
from video_paper_wiki_research.light_qa import export_qa_context, render_answer
from video_paper_wiki_research.light_writing import export_writing_context, render_draft


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


def test_shipped_extract_index_search_qa_writing(tmp_path: Path) -> None:
    workspace = tmp_path / ".work" / "light-pipe"
    workspace.mkdir(parents=True)
    pdf = tmp_path / "paper.pdf"
    body = "Hybrid linear attention with attention residuals for efficient video generation."
    pdf.write_bytes(_pdf_with_page_texts([body]))
    extracted = extract_pdf(pdf, workspace, title="Pipeline Paper")
    assert extracted["ok"] is True
    markdown_path = Path(extracted["markdown_path"])
    markdown = markdown_path.read_text(encoding="utf-8")
    built = build_index(workspace)
    assert built["ok"] is True
    found = search(workspace, "hybrid linear attention")
    assert found["ok"] is True
    assert found["status"] == "OK"
    item = found["evidence"][0]
    assert item["text"] == markdown[item["text_start"] : item["text_end"]]
    assert body in item["text"]
    context = export_qa_context("What attention method is used?", found)
    assert context["ok"] is True
    assert context["evidence"][0]["text"] == item["text"]
    chunk_id = item["chunk_id"]
    rendered = render_answer(
        context,
        {
            "text": f"The paper uses hybrid linear attention. [@{chunk_id}]",
            "citations": [{"chunk_id": chunk_id}],
        },
    )
    assert rendered["ok"] is True
    assert "PDF 第" in rendered["markdown"]
    assert f"#page-{item['page']}" in rendered["markdown"]
    assert "Pipeline Paper" in rendered["markdown"]
    writing_context = export_writing_context("efficient video generation", "one paragraph", [], found)
    draft = render_draft(
        writing_context,
        {
            "markdown": f"Draft cites the method. [@{chunk_id}]",
            "citations": [{"chunk_id": chunk_id}],
        },
    )
    assert draft["ok"] is True
    assert f"#page-{item['page']}" in draft["markdown"]
    markdown_path.write_text(markdown + "\nchanged\n", encoding="utf-8")
    stale = search(workspace, "hybrid linear attention")
    assert stale["status"] == "INDEX_STALE"
    rebuilt = build_index(workspace)
    assert rebuilt["ok"] is True
    fresh = search(workspace, "hybrid linear attention")
    assert fresh["status"] == "OK"
    assert fresh["evidence"][0]["text"] == markdown_path.read_text(encoding="utf-8")[
        fresh["evidence"][0]["text_start"] : fresh["evidence"][0]["text_end"]
    ]


def _assert_hit(workspace: Path, word: str, page: int, markdown: str) -> None:
    found = search(workspace, word)
    assert found["ok"] is True
    assert found["status"] == "OK"
    item = found["evidence"][0]
    assert item["page"] == page
    assert word in item["text"]
    assert item["text"] == markdown[item["text_start"] : item["text_end"]]
    assert item["text_sha256"] == hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
    assert "## PDF" not in item["text"]
    assert "<a id=" not in item["text"]


def test_preface_before_anchors_keeps_quasar_and_nebula_pages(tmp_path: Path) -> None:
    workspace = tmp_path / ".work" / "quasar"
    workspace.mkdir(parents=True)
    pdf = tmp_path / "two-pages.pdf"
    pdf.write_bytes(
        _pdf_with_page_texts(
            [
                "quasar describes the first PDF page only.",
                "nebula describes the second PDF page only.",
            ]
        )
    )
    added = extract_pdf(pdf, workspace, title="Two Page Fixture")
    md_path = Path(added["markdown_path"])
    meta_path = Path(added["metadata_path"])
    original_md = md_path.read_text(encoding="utf-8")
    original_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    source_sha = original_meta["source"]["sha256"]
    paper_id = added["paper_id"]
    build_index(workspace)
    _assert_hit(workspace, "quasar", 1, original_md)
    _assert_hit(workspace, "nebula", 2, original_md)
    offset_difference = original_meta["pages"][1]["text_start"] - original_meta["pages"][0]["text_start"]
    prefix = "Reader note: " + "." * (offset_difference - len("Reader note: ") - 2) + "\n\n"
    assert len(prefix) == offset_difference
    md_path.write_text(prefix + original_md, encoding="utf-8")
    stale = search(workspace, "quasar")
    assert stale["status"] == "INDEX_STALE"
    rebuilt = build_index(workspace)
    assert rebuilt["ok"] is True
    edited = md_path.read_text(encoding="utf-8")
    _assert_hit(workspace, "quasar", 1, edited)
    _assert_hit(workspace, "nebula", 2, edited)
    final_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert final_meta["paper_id"] == paper_id
    assert final_meta["source"]["sha256"] == source_sha
    assert final_meta["document"]["sha256"] == hashlib.sha256(md_path.read_bytes()).hexdigest()
    assert [(p["text_start"], p["text_end"]) for p in final_meta["pages"]] != [
        (p["text_start"], p["text_end"]) for p in original_meta["pages"]
    ]
