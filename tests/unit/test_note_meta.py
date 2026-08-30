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
    assert fm.count("\n") == 2
    return body


def _assert_copy_frontmatter_keys(text: str) -> str:
    assert text.startswith("---\ntitle:")
    fm, body = _frontmatter_and_body(text)
    lines = fm.splitlines()
    assert lines[1].startswith("paper_id:")
    assert lines[2].startswith("arxiv_id:")
    assert lines[-1].startswith("topics:")
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
    _assert_frozen_headings(work)
    _assert_frozen_headings(copied)
    assert "[视频扩散](../wiki/video-diffusion.md)" in copied
    assert copy_body.startswith(work_body)
    assert "## 相关论文" in copy_body
    assert "## 相关论文" not in work_body
    assert "arxiv_id" not in work
    assert "year:" not in work
    assert "topics:" not in work
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
    assert "topics:" not in work
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
    assert "title_zh:" in work
    assert "arxiv_id" not in work
    assert "topics:" not in work
    assert network_attempts == []


def test_ingest_non_catalog_paper_id_x_empty_topics(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "x", dest)
    assert code == 0
    _stdout_json(capsys)

    work = (tmp_path / ".work" / "notes" / "x.md").read_text(encoding="utf-8")
    copied = (dest / "papers" / "x.md").read_text(encoding="utf-8")
    work_body = _assert_work_frontmatter(work)
    copy_body = _assert_copy_frontmatter_keys(copied)
    assert "paper_id: x" in copied
    assert 'arxiv_id: ""' in copied
    assert "year:" not in _frontmatter_and_body(copied)[0]
    assert "topics: []" in copied
    assert copy_body == work_body
    assert "## 相关论文" not in copied
    assert copied != work
    assert network_attempts == []


def test_export_minimal_fixture_copy_frontmatter(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(MINIMAL), "--vault", str(dest)])
    assert code == 0
    _stdout_json(capsys)
    work = (tmp_path / ".work" / "notes" / "fixture-minimal.md").read_text(encoding="utf-8")
    copied = (dest / "papers" / "fixture-minimal.md").read_text(encoding="utf-8")
    work_body = _assert_work_frontmatter(work)
    copy_body = _assert_copy_frontmatter_keys(copied)
    assert work.startswith("---\npaper_id:")
    assert "title: Minimal Draft Fixture" in work
    assert "title_zh: 最小草稿夹具" in work
    assert "title: Minimal Draft Fixture" in copied
    assert "paper_id: fixture-minimal" in copied
    assert 'arxiv_id: ""' in copied
    assert "year:" not in _frontmatter_and_body(copied)[0]
    assert "topics: []" in copied
    assert copy_body == work_body
    assert copied != work
    assert "## 相关论文" not in copied
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []
