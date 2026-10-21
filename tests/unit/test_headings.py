from __future__ import annotations

from video_paper_wiki.notes.clear_draft import apply_empty_draft_sections
from video_paper_wiki.notes.headings import H2_LINE_RE, h2_heading_text, is_atx_h2
from video_paper_wiki.notes.section import list_headings, section_text


def test_is_atx_h2_exact_level_two() -> None:
    assert is_atx_h2("## 方法")
    assert is_atx_h2("##")
    assert is_atx_h2("  ## 方法")
    assert is_atx_h2("   ## 方法")
    assert is_atx_h2("##\t方法")
    assert not is_atx_h2("### 方法")
    assert not is_atx_h2("# 方法")
    assert not is_atx_h2("#### 方法")
    assert not is_atx_h2("    ## 方法")
    assert not is_atx_h2("##方法")
    assert h2_heading_text("## 方法") == "方法"
    assert h2_heading_text("  ## 方法") == "方法"
    assert h2_heading_text("### 方法") is None
    assert H2_LINE_RE.pattern == r"^ {0,3}##(?!#)(?:[ \t]+|$)"


def test_section_and_headings_ignore_h3_and_four_space_indent() -> None:
    text = (
        "## 方法\n"
        "keep me\n"
        "### 方法\n"
        "still method\n"
        "## 局限\n"
        "lim\n"
    )
    assert list_headings(text) == ["方法", "局限"]
    assert section_text(text, "方法") == "keep me\n### 方法\nstill method"
    assert section_text(text, "局限") == "lim"
    indented = "  ## 方法\nbody\n"
    assert list_headings(indented) == ["方法"]
    assert section_text(indented, "方法") == "body"
    code_indented = "    ## 方法\nbody\n"
    assert list_headings(code_indented) == []
    assert section_text(code_indented, "方法") is None


def test_empty_draft_does_not_treat_h3_as_section_boundary() -> None:
    text = "## 方法\nkeep\n### 下一节\nstill method\n## 局限\nlim\n"
    out = apply_empty_draft_sections(text)
    assert section_text(out, "方法") == ""
    assert "still method" not in out
    assert "### 下一节" not in out
    assert section_text(out, "局限") == ""
