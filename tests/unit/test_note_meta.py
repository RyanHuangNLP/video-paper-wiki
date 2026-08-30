from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.cli import main
from video_paper_wiki.notes import year_from_arxiv_id
from video_paper_wiki.notes.frontmatter import resolve_arxiv_id, topic_ids_for_paper
from video_paper_wiki.parse.draft_document import SECTION_SPECS
from video_paper_wiki.parse.title import catalog_arxiv_id_for_paper_id

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _prepare(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))


def _ingest(path, paper_id, dest):
    return main(
        [
            "ingest",
            "run",
            "--path",
            str(path),
            "--paper-id",
            paper_id,
            "--vault",
            str(dest),
        ]
    )


def _frontmatter_and_body(text: str) -> tuple[str, str]:
    assert text.startswith("---\n")
    end = text.find("\n---\n", 3)
    assert end != -1
    return text[4:end], text[end + 5:]


def _assert_work_frontmatter(text: str) -> str:
    assert text.startswith("---\npaper_id:")
    fm, body = _frontmatter_and_body(text)
    assert "title:" in fm
    assert "title_zh:" in fm
    assert "arxiv_id" not in fm
    assert "year:" not in fm
    assert "topics:" not in fm
    assert "related:" not in fm
    assert "backlinks:" not in fm
    assert fm.count("\n") == 2
    return body


def _assert_copy_frontmatter_keys(text: str) -> str:
    assert text.startswith("---\ntitle:")
    fm, body = _frontmatter_and_body(text)
    lines = fm.splitlines()
    assert lines[0].startswith("title:")
    assert lines[1].startswith("paper_id:")
    assert lines[2].startswith("arxiv_id:")
    names = [line.split(":", 1)[0] for line in lines]
    if "year" in names:
        assert names == [
            "title",
            "paper_id",
            "arxiv_id",
            "year",
            "topics",
            "related",
            "backlinks",
        ]
    else:
        assert names == [
            "title",
            "paper_id",
            "arxiv_id",
            "topics",
            "related",
            "backlinks",
        ]
    assert lines[-3].startswith("topics:")
    assert lines[-2].startswith("related:")
    assert lines[-1].startswith("backlinks:")
    assert "title_zh" not in fm
    assert text.count("\n---\n") == 1
    return body


def _assert_frozen_headings(text: str) -> None:
    for _section_id, heading in SECTION_SPECS:
        assert f"## {heading}" in text
    positions = [text.index(f"## {heading}") for _section_id, heading in SECTION_SPECS]
    assert positions == sorted(positions)


def test_year_from_arxiv_id_yymm_prefix() -> None:
    assert year_from_arxiv_id("1812.01717") == 2018
    assert year_from_arxiv_id("2408.06072") == 2024
    assert year_from_arxiv_id("2311.15127") == 2023
    assert year_from_arxiv_id("") is None
    assert year_from_arxiv_id("181201717") == 2018
    assert year_from_arxiv_id("0704.0001") == 2007
    assert year_from_arxiv_id("x") is None
    assert year_from_arxiv_id("ab12.34567") is None


def test_resolve_arxiv_id_catalog_prefix_and_empty() -> None:
    assert catalog_arxiv_id_for_paper_id("arxiv-2209.14792") == "2209.14792"
    assert resolve_arxiv_id("arxiv-2209.14792") == "2209.14792"
    assert resolve_arxiv_id("arxiv-9999.00000") == "9999.00000"
    assert resolve_arxiv_id("x") == ""
    assert resolve_arxiv_id("fixture-minimal") == ""
    assert topic_ids_for_paper("arxiv-2209.14792") == ["video-diffusion"]
    assert topic_ids_for_paper("arxiv-2408.06072") == ["video-diffusion", "tokenization"]
    assert topic_ids_for_paper("arxiv-1812.01717") == ["evaluation"]
    assert topic_ids_for_paper("x") == []


def test_ingest_make_a_video_papers_copy_frontmatter(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "arxiv-2209.14792", dest)
    assert code == 0
    _stdout_json(capsys)

    work = (tmp_path / ".work" / "notes" / "arxiv-2209.14792.md").read_text(encoding="utf-8")
    copied = (dest / "papers" / "arxiv-2209.14792.md").read_text(encoding="utf-8")
    work_body = _assert_work_frontmatter(work)
    copy_body = _assert_copy_frontmatter_keys(copied)
    assert copied.startswith("---\n")
    assert "title: Make-A-Video" in copied
    assert "paper_id: arxiv-2209.14792" in copied
    assert "arxiv_id: 2209.14792" in copied
    assert "year: 2022" in copied
    assert "topics: [video-diffusion]" in copied
    from video_paper_wiki.notes.links import backlink_catalog_ids, related_catalog_papers

    related_ids = [pid for pid, _title in related_catalog_papers("arxiv-2209.14792")]
    assert related_ids
    assert f"related: [{', '.join(related_ids)}]" in copied
    backlinks = backlink_catalog_ids("arxiv-2209.14792")
    assert backlinks
    assert f"backlinks: [{', '.join(backlinks)}]" in copied
    import re

    link_ids = re.findall(r"\]\(\./([^)]+)\.md\)", copied.split("## 相关论文", 1)[1])
    assert link_ids == related_ids
    _assert_frozen_headings(work)
    _assert_frozen_headings(copied)
    assert "[视频扩散](../wiki/video-diffusion.md)" in copied
    from video_paper_wiki.notes.section import section_text
    assert section_text(copied, "一句话结论") == "用图像扩散先验做文生视频，不必成对的视频-文本数据。"
    assert section_text(copied, "研究问题") == "没有成对视频-文本数据时，怎样做文生视频？"
    assert section_text(copied, "方法") == "先训图像扩散，再加时空卷积和注意力，用图像-文本对齐做文生视频。"
    assert section_text(copied, "表示与架构") == "图像 U-Net 加上伪 3D 时空卷积和时空注意力。"
    assert section_text(copied, "训练与数据") == "先用图像-文本数据训图像扩散，再用无标签视频学时空模块。"
    assert section_text(copied, "实验与结果") == "无成对视频-文本数据也能做出有竞争力的文生视频。"
    assert section_text(copied, "局限") == "没有成对视频-文本，细粒度文本控制偏弱。"
    assert section_text(copied, "关联") == "证明图像先验可以迁到视频，后面 SVD、DynamiCrafter 也走这条路。"
    assert "Tiny VPKB paper" in section_text(work, "一句话结论")
    assert section_text(copied, "证据状态") == "provisional"
    assert "local pypdf extract" not in section_text(copied, "证据状态")
    assert section_text(copied, "代码与资源") == ""
    assert "## 相关论文" in copy_body
    assert "## 相关论文" not in work_body
    assert "arxiv_id" not in work
    assert "year:" not in work
    assert "topics:" not in work
    assert "related:" not in work
    assert "backlinks:" not in work
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_cogvideox_year_and_two_topics(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "arxiv-2408.06072", dest)
    assert code == 0
    _stdout_json(capsys)

    work = (tmp_path / ".work" / "notes" / "arxiv-2408.06072.md").read_text(encoding="utf-8")
    copied = (dest / "papers" / "arxiv-2408.06072.md").read_text(encoding="utf-8")
    _assert_work_frontmatter(work)
    _assert_copy_frontmatter_keys(copied)
    assert "title: CogVideoX" in copied
    assert "paper_id: arxiv-2408.06072" in copied
    assert "arxiv_id: 2408.06072" in copied
    assert "year: 2024" in copied
    assert "topics: [video-diffusion, tokenization]" in copied
    from video_paper_wiki.notes.links import backlink_catalog_ids, related_catalog_papers

    related_ids = [pid for pid, _title in related_catalog_papers("arxiv-2408.06072")]
    assert related_ids
    assert f"related: [{', '.join(related_ids)}]" in copied
    backlinks = backlink_catalog_ids("arxiv-2408.06072")
    assert f"backlinks: [{', '.join(backlinks)}]" in copied
    assert "topics:" not in work
    assert "related:" not in work
    assert "backlinks:" not in work
    assert "year:" not in work
    assert "[视频扩散](../wiki/video-diffusion.md)" in copied
    assert "[视频 tokenizer](../wiki/tokenization.md)" in copied
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_towards_accurate_year_2018_evaluation(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "arxiv-1812.01717", dest)
    assert code == 0
    _stdout_json(capsys)

    work = (tmp_path / ".work" / "notes" / "arxiv-1812.01717.md").read_text(encoding="utf-8")
    copied = (dest / "papers" / "arxiv-1812.01717.md").read_text(encoding="utf-8")
    _assert_work_frontmatter(work)
    _assert_copy_frontmatter_keys(copied)
    assert "title: Towards Accurate Generative Models of Video" in copied
    assert "arxiv_id: 1812.01717" in copied
    assert "year: 2018" in copied
    assert "topics: [evaluation]" in copied
    from video_paper_wiki.notes.links import backlink_catalog_ids, related_catalog_papers

    related_ids = [pid for pid, _title in related_catalog_papers("arxiv-1812.01717")]
    assert related_ids
    assert f"related: [{', '.join(related_ids)}]" in copied
    backlinks = backlink_catalog_ids("arxiv-1812.01717")
    assert f"backlinks: [{', '.join(backlinks)}]" in copied
    assert "title_zh:" in work
    assert "arxiv_id" not in work
    assert "topics:" not in work
    assert "related:" not in work
    assert "backlinks:" not in work
    assert network_attempts == []


def test_ingest_non_catalog_paper_id_x_frozen_seed_missing(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "x", dest)
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == "x"
    assert not (dest / "papers").exists()
    assert not (tmp_path / ".work" / "notes" / "x.md").exists()
    assert network_attempts == []


def test_export_minimal_fixture_copy_frontmatter(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(MINIMAL), "--vault", str(dest)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == "fixture-minimal"
    assert not (dest / "papers").exists()
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []
