from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.cli import main
from video_paper_wiki.notes import paper_note_link_suffix, related_catalog_papers
from video_paper_wiki.notes.links import paper_note_link_suffix as suffix_direct
from video_paper_wiki.parse.draft_document import SECTION_SPECS
from video_paper_wiki.parse.title import catalog_title_for_paper_id

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


def _assert_frozen_headings(text: str) -> None:
    for _section_id, heading in SECTION_SPECS:
        assert f"## {heading}" in text
    positions = [text.index(f"## {heading}") for _section_id, heading in SECTION_SPECS]
    assert positions == sorted(positions)


def _trailer_after_related(text: str) -> str:
    marker = "## 关联"
    assert marker in text
    return text.split(marker, 1)[1]


def test_suffix_empty_when_paper_not_in_topics() -> None:
    assert paper_note_link_suffix("fixture-minimal") == ""
    assert paper_note_link_suffix("x") == ""
    assert paper_note_link_suffix("not-a-topic") == ""
    assert related_catalog_papers("fixture-minimal") == []
    assert suffix_direct is paper_note_link_suffix


def test_suffix_topic_paper_deduped_related_stable_order() -> None:
    first = paper_note_link_suffix("arxiv-2209.14792")
    second = paper_note_link_suffix("arxiv-2209.14792")
    assert first == second
    assert first.startswith("\n## 主题\n")
    assert "[视频扩散](../wiki/video-diffusion.md)" in first
    assert "[视频 tokenizer](../wiki/tokenization.md)" not in first
    assert "## 相关论文" in first
    related = related_catalog_papers("arxiv-2209.14792")
    ids = [paper_id for paper_id, _title in related]
    assert ids[0] == "arxiv-2204.03458"
    assert "arxiv-2209.14792" not in ids
    assert len(ids) == len(set(ids))
    assert related == related_catalog_papers("arxiv-2209.14792")
    assert "[Video Diffusion Models](./arxiv-2204.03458.md)" in first
    assert "](./arxiv-2209.14792.md)" not in first


def test_suffix_cogvideox_unions_topics_and_skips_self() -> None:
    text = paper_note_link_suffix("arxiv-2408.06072")
    topic_vd = "[视频扩散](../wiki/video-diffusion.md)"
    topic_tok = "[视频 tokenizer](../wiki/tokenization.md)"
    assert topic_vd in text
    assert topic_tok in text
    assert text.index(topic_vd) < text.index(topic_tok)
    related = related_catalog_papers("arxiv-2408.06072")
    ids = [paper_id for paper_id, _title in related]
    assert "arxiv-2408.06072" not in ids
    assert len(ids) == len(set(ids))
    assert "arxiv-2204.03458" in ids
    assert "arxiv-2210.02399" in ids
    assert ids.index("arxiv-2204.03458") < ids.index("arxiv-2210.02399")
    assert "[Phenaki](./arxiv-2210.02399.md)" in text
    assert "[Video Diffusion Models](./arxiv-2204.03458.md)" in text
    assert "](./arxiv-2408.06072.md)" not in text


def test_related_skips_sibling_without_catalog_title(monkeypatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki.notes.links.load_topics",
        lambda: [
            {
                "id": "video-diffusion",
                "heading_zh": "视频扩散",
                "paper_ids": ["arxiv-2209.14792", "ghost", "arxiv-2204.03458"],
            }
        ],
    )

    def _titles(paper_id: str) -> str | None:
        if paper_id == "ghost":
            return None
        return catalog_title_for_paper_id(paper_id)

    monkeypatch.setattr("video_paper_wiki.notes.links.catalog_title_for_paper_id", _titles)
    related = related_catalog_papers("arxiv-2209.14792")
    assert [paper_id for paper_id, _title in related] == ["arxiv-2204.03458"]
    text = paper_note_link_suffix("arxiv-2209.14792")
    assert "ghost" not in text
    assert "[Video Diffusion Models](./arxiv-2204.03458.md)" in text


def test_ingest_make_a_video_appends_trailers_only_on_papers_copy(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "arxiv-2209.14792", dest)
    assert code == 0
    _stdout_json(capsys)

    work = tmp_path / ".work" / "notes" / "arxiv-2209.14792.md"
    copied = dest / "papers" / "arxiv-2209.14792.md"
    work_text = work.read_text(encoding="utf-8")
    copied_text = copied.read_text(encoding="utf-8")
    _assert_frozen_headings(work_text)
    _assert_frozen_headings(copied_text)
    assert "../wiki/" not in work_text
    assert "## 相关论文" not in work_text
    assert "[视频扩散](../wiki/video-diffusion.md)" in copied_text
    assert "](./arxiv-" in copied_text
    assert "](./arxiv-2209.14792.md)" not in copied_text
    assert "## 相关论文" in copied_text
    assert copied_text != work_text
    assert work_text.startswith("---\npaper_id:")
    assert "title_zh:" in work_text
    assert "arxiv_id" not in work_text.split("---", 2)[1]
    assert "topics:" not in work_text.split("---", 2)[1]
    assert copied_text.startswith("---\ntitle:")
    assert "title: Make-A-Video" in copied_text
    assert "year: 2022" in copied_text
    assert "topics: [video-diffusion]" in copied_text
    assert not (dest / "wiki" / "index.md").exists()
    index_text = (dest / "index.md").read_text(encoding="utf-8")
    assert "[Make-A-Video](papers/arxiv-2209.14792.md)" in index_text
    assert "## 主题" in index_text
    assert "[视频扩散](wiki/video-diffusion.md)" in index_text
    assert (dest / "wiki" / "video-diffusion.md").is_file()
    assert network_attempts == []


def test_ingest_cogvideox_unions_both_topics(
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
    _assert_frozen_headings(work)
    assert "../wiki/" not in work
    assert "## 相关论文" not in work
    assert "[视频扩散](../wiki/video-diffusion.md)" in copied
    assert "[视频 tokenizer](../wiki/tokenization.md)" in copied
    assert "[Phenaki](./arxiv-2210.02399.md)" in copied
    assert "[Video Diffusion Models](./arxiv-2204.03458.md)" in copied
    assert "](./arxiv-2408.06072.md)" not in copied
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_non_topic_paper_omits_trailers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "not-a-topic", dest)
    assert code == 0
    _stdout_json(capsys)

    work = (tmp_path / ".work" / "notes" / "not-a-topic.md").read_text(encoding="utf-8")
    copied = (dest / "papers" / "not-a-topic.md").read_text(encoding="utf-8")
    assert copied != work
    assert work.startswith("---\npaper_id:")
    assert "title_zh:" in work
    assert "topics:" not in work.split("---", 2)[1]
    assert copied.startswith("---\ntitle:")
    assert "topics: []" in copied
    _assert_frozen_headings(copied)
    after = _trailer_after_related(copied)
    assert "## 主题" not in after
    assert "## 相关论文" not in copied
    assert "../wiki/" not in copied
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_export_minimal_fixture_omits_trailers(
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
    assert copied != work
    assert work.startswith("---\npaper_id:")
    assert "title_zh:" in work
    assert "topics:" not in work.split("---", 2)[1]
    assert copied.startswith("---\ntitle:")
    assert "topics: []" in copied
    _assert_frozen_headings(copied)
    after = _trailer_after_related(copied)
    assert "## 主题" not in after
    assert "## 相关论文" not in copied
    assert "../wiki/" not in work
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []
