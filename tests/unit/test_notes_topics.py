from __future__ import annotations

from pathlib import Path

from video_paper_wiki.notes import load_topics, refresh_topic_pages
from video_paper_wiki.notes.topics import refresh_topic_pages as refresh_direct


def test_refresh_skips_unknown_and_missing_papers(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    papers = root / "papers"
    papers.mkdir()
    (papers / "arxiv-2209.14792.md").write_text("# Make-A-Video\n", encoding="utf-8")
    (papers / "not-in-catalog.md").write_text("# ghost\n", encoding="utf-8")
    (root / "index.md").write_text("# Video Paper Wiki\n", encoding="utf-8")

    refresh_topic_pages(root)

    vd = (root / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert vd.startswith("# 视频扩散\n")
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md)" in vd
    assert "not-in-catalog" not in vd
    assert "arxiv-2311.15127" not in vd
    assert "Stable Video Diffusion" not in vd
    assert not (root / "wiki" / "index.md").exists()


def test_refresh_never_writes_wiki_index(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    refresh_topic_pages(root)
    assert not (root / "wiki" / "index.md").exists()
    assert (root / "wiki" / "video-diffusion.md").is_file()
    assert (root / "wiki" / "evaluation.md").read_text(encoding="utf-8").startswith("# 评测\n")


def test_refresh_never_creates_notes_root(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    refresh_topic_pages(missing)
    assert not missing.exists()
    assert list(tmp_path.iterdir()) == []
    assert refresh_direct is refresh_topic_pages
    topics = load_topics()
    assert topics is not None
    assert [topic["id"] for topic in topics][0] == "video-diffusion"


def test_refresh_skips_unknown_paper_id_even_if_note_exists(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    papers = root / "papers"
    papers.mkdir()
    (papers / "ghost.md").write_text("# ghost\n", encoding="utf-8")
    (papers / "arxiv-2209.14792.md").write_text("# mav\n", encoding="utf-8")
    (root / "index.md").write_text("# Video Paper Wiki\n", encoding="utf-8")

    monkeypatch.setattr(
        "video_paper_wiki.notes.topics.load_topics",
        lambda: [
            {
                "id": "video-diffusion",
                "heading_zh": "视频扩散",
                "paper_ids": ["ghost", "arxiv-2209.14792"],
            }
        ],
    )
    refresh_direct(root)
    text = (root / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md)" in text
    assert "ghost" not in text
    assert not (root / "wiki" / "index.md").exists()
