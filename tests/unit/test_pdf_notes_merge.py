from __future__ import annotations

from video_paper_wiki.notes.merge import merge_paper_copy
from video_paper_wiki.notes.section import section_text
from video_paper_wiki.pdf_locations import build_locations_document, build_pdf_entry, render_pdf_section

CUSTOM = "user kept this paragraph"


def test_notes_merge_keeps_pdf_links_and_user_body() -> None:
    entry = build_pdf_entry(file_id="1AbCdefGhijkLMNOPqrstUVwxyz0123456", verified=False)
    locations = build_locations_document("arxiv:2204.03458", [entry])
    pdf_block = render_pdf_section(locations)
    existing = (
        "---\n"
        "title: Video Diffusion Models\n"
        "paper_id: arxiv-2204.03458\n"
        "---\n"
        "\n"
        "## 一句话结论\n"
        "\n"
        "old conclusion\n"
        "\n"
        "## 自定义\n"
        "\n"
        f"{CUSTOM}\n"
        + pdf_block
    )
    new_entry = build_pdf_entry(
        file_id="1AbCdefGhijkLMNOPqrstUVwxyz0123456",
        url="https://drive.google.com/file/d/1AbCdefGhijkLMNOPqrstUVwxyz0123456/view",
        verified=False,
    )
    rendered_locations = build_locations_document("arxiv:2204.03458", [new_entry])
    rendered = (
        "---\n"
        "title: Video Diffusion Models\n"
        "paper_id: arxiv-2204.03458\n"
        "---\n"
        "\n"
        "## 一句话结论\n"
        "\n"
        "new conclusion\n"
        + render_pdf_section(rendered_locations)
    )
    merged = merge_paper_copy(existing, rendered)
    assert section_text(merged, "自定义") == CUSTOM
    assert section_text(merged, "一句话结论") == "new conclusion"
    pdf = section_text(merged, "PDF")
    assert pdf is not None
    assert "Drive PDF" in pdf
    assert "1AbCdefGhijkLMNOPqrstUVwxyz0123456" in merged
