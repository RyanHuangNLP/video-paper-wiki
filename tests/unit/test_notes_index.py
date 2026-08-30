from __future__ import annotations

from pathlib import Path

from video_paper_wiki.notes import upsert_index_entry
from video_paper_wiki.notes.index import upsert_index_entry as upsert_direct


def test_upsert_index_entry_writes_updates_and_preserves(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    (root / "index.md").write_text("# Papers\n\n[other](papers/other.md)\n", encoding="utf-8")

    first = upsert_index_entry(root, "alpha", "Alpha Paper")
    assert first == root / "index.md"
    text = first.read_text(encoding="utf-8")
    assert "[Alpha Paper](papers/alpha.md)" in text
    assert "[other](papers/other.md)" in text
    assert text.startswith("# Papers\n")
    assert "# Video Paper Wiki" not in text
    assert text.endswith("\n")

    upsert_index_entry(root, "beta", "Beta Paper")
    text = first.read_text(encoding="utf-8")
    assert "[Alpha Paper](papers/alpha.md)" in text
    assert "[Beta Paper](papers/beta.md)" in text
    assert "[other](papers/other.md)" in text
    assert text.count("](papers/") == 3

    upsert_index_entry(root, "alpha", "Alpha Renamed")
    text = first.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert "[Alpha Renamed](papers/alpha.md)" in lines
    assert "[Alpha Paper](papers/alpha.md)" not in lines
    assert "[Beta Paper](papers/beta.md)" in lines
    assert "[other](papers/other.md)" in lines
    assert "# Papers" in lines
    assert lines.count("[Alpha Renamed](papers/alpha.md)") == 1
    assert text.endswith("\n")
    assert not (root / "wiki" / "index.md").exists()
    assert upsert_direct is upsert_index_entry


def test_upsert_index_entry_creates_file_and_falls_back_title(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    path = upsert_index_entry(root, "empty-title", "   ")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Video Paper Wiki\n")
    assert text == "# Video Paper Wiki\n[empty-title](papers/empty-title.md)\n"
    upsert_index_entry(root, "brackets", "Hello [World]")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Video Paper Wiki\n")
    assert "[Hello (World)](papers/brackets.md)" in text
    assert "[empty-title](papers/empty-title.md)" in text
    assert "# Video Paper Wiki" in text.splitlines()[0]


def test_upsert_index_entry_inserts_papers_before_topics_section(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    (root / "index.md").write_text(
        "# Video Paper Wiki\n"
        "[Alpha Paper](papers/alpha.md)\n"
        "## 主题\n"
        "[视频扩散](wiki/video-diffusion.md)\n",
        encoding="utf-8",
    )
    upsert_index_entry(root, "beta", "Beta Paper")
    text = (root / "index.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert text.startswith("# Video Paper Wiki\n")
    assert "# Papers" not in text
    assert lines.index("[Beta Paper](papers/beta.md)") < lines.index("## 主题")
    assert lines.index("[Alpha Paper](papers/alpha.md)") < lines.index("## 主题")
    assert "[视频扩散](wiki/video-diffusion.md)" in lines
    assert text.count("## 主题") == 1
    assert text.endswith("\n")

    upsert_index_entry(root, "alpha", "Alpha Renamed")
    text = (root / "index.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert text.startswith("# Video Paper Wiki\n")
    assert lines.index("[Alpha Renamed](papers/alpha.md)") < lines.index("## 主题")
    assert "[Alpha Paper](papers/alpha.md)" not in lines
    assert lines.count("[Alpha Renamed](papers/alpha.md)") == 1


def test_upsert_index_entry_keeps_papers_heading_and_inserts_above_topics(
    tmp_path: Path,
) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    (root / "index.md").write_text(
        "# Papers\n"
        "\n"
        "[other](papers/other.md)\n"
        "## 主题\n"
        "[评测](wiki/evaluation.md)\n",
        encoding="utf-8",
    )
    upsert_index_entry(root, "alpha", "Alpha Paper")
    text = (root / "index.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert text.startswith("# Papers\n")
    assert "# Video Paper Wiki" not in text
    assert lines.index("[Alpha Paper](papers/alpha.md)") < lines.index("## 主题")
    assert lines.index("[other](papers/other.md)") < lines.index("## 主题")
    assert "[评测](wiki/evaluation.md)" in lines
