from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.cli import main
from video_paper_wiki.notes import upsert_index_entry, year_from_arxiv_id
from video_paper_wiki.notes.frontmatter import resolve_arxiv_id
from video_paper_wiki.notes.index import (
    format_index_line,
    paper_index_year,
    sort_paper_ids,
    upsert_index_entry as upsert_direct,
)

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"

COGVIDEOX = "arxiv-2408.06072"
TOWARDS = "arxiv-1812.01717"
MAKE_A_VIDEO = "arxiv-2209.14792"
VBENCH = "arxiv-2311.17982"
SVD = "arxiv-2311.15127"

LINE_2018 = (
    "[Towards Accurate Generative Models of Video]"
    f"(papers/{TOWARDS}.md) (2018)"
)
LINE_2022 = f"[Make-A-Video](papers/{MAKE_A_VIDEO}.md) (2022)"
LINE_2024 = f"[CogVideoX](papers/{COGVIDEOX}.md) (2024)"
LINE_SVD = f"[Stable Video Diffusion](papers/{SVD}.md) (2023)"
LINE_VBENCH = f"[VBench](papers/{VBENCH}.md) (2023)"


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


def _paper_lines(text: str) -> list[str]:
    lines = text.splitlines()
    topics_at = lines.index("## 主题") if "## 主题" in lines else len(lines)
    return [line for line in lines[1:topics_at] if "](papers/" in line]


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


def test_paper_index_year_uses_year_from_arxiv_id() -> None:
    assert year_from_arxiv_id(resolve_arxiv_id(TOWARDS)) == 2018
    assert year_from_arxiv_id(resolve_arxiv_id(MAKE_A_VIDEO)) == 2022
    assert year_from_arxiv_id(resolve_arxiv_id(COGVIDEOX)) == 2024
    assert paper_index_year(TOWARDS) == 2018
    assert paper_index_year(MAKE_A_VIDEO) == 2022
    assert paper_index_year(COGVIDEOX) == 2024
    assert paper_index_year("x") is None
    assert paper_index_year("fixture-minimal") is None
    assert paper_index_year("arxiv-2311.15127") == 2023
    assert paper_index_year("arxiv-2311.17982") == 2023


def test_sort_paper_ids_year_then_paper_id() -> None:
    assert sort_paper_ids([COGVIDEOX, TOWARDS, MAKE_A_VIDEO]) == [
        TOWARDS,
        MAKE_A_VIDEO,
        COGVIDEOX,
    ]
    assert sort_paper_ids([VBENCH, SVD]) == [SVD, VBENCH]
    assert sort_paper_ids([COGVIDEOX, "x", TOWARDS]) == [TOWARDS, COGVIDEOX, "x"]
    assert sort_paper_ids(["z", MAKE_A_VIDEO, "x"]) == [MAKE_A_VIDEO, "x", "z"]


def test_format_index_line_year_and_catalog_title() -> None:
    assert format_index_line(TOWARDS, "ignored") == LINE_2018
    assert format_index_line(MAKE_A_VIDEO, "ignored") == LINE_2022
    assert format_index_line(COGVIDEOX, "ignored") == LINE_2024
    assert format_index_line(SVD, "ignored") == LINE_SVD
    assert format_index_line(VBENCH, "ignored") == LINE_VBENCH
    assert format_index_line("x", "Custom") == "[Custom](papers/x.md)"
    assert format_index_line("fixture-minimal", "Minimal Draft Fixture") == (
        "[Minimal Draft Fixture](papers/fixture-minimal.md)"
    )
    assert "(YYYY)" not in format_index_line("x", "Custom")
    assert format_index_line("x", "Custom").endswith(".md)")


def test_upsert_sorts_catalog_papers_by_year_and_upgrades_old_lines(
    tmp_path: Path,
) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    upsert_index_entry(root, COGVIDEOX, "wrong-title")
    upsert_index_entry(root, TOWARDS, "also-wrong")
    upsert_index_entry(root, MAKE_A_VIDEO, "Make-A-Video")
    text = (root / "index.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Video Paper Wiki"
    assert lines[1] == LINE_2018
    assert lines[2] == LINE_2022
    assert lines[3] == LINE_2024
    assert "## 主题" not in lines
    assert not (root / "wiki" / "index.md").exists()

    (root / "index.md").write_text(
        "# Video Paper Wiki\n"
        "[Make-A-Video](papers/arxiv-2209.14792.md)\n"
        "## 主题\n"
        "[视频扩散](wiki/video-diffusion.md)\n"
        "[评测](wiki/evaluation.md)\n",
        encoding="utf-8",
    )
    upsert_index_entry(root, TOWARDS, "ignored")
    text = (root / "index.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Video Paper Wiki"
    assert lines[1] == LINE_2018
    assert lines[2] == LINE_2022
    assert lines[3] == "## 主题"
    assert lines[4] == "[视频扩散](wiki/video-diffusion.md)"
    assert lines[5] == "[评测](wiki/evaluation.md)"
    assert "[Make-A-Video](papers/arxiv-2209.14792.md)" not in lines
    assert not (root / "wiki" / "index.md").exists()


def test_upsert_same_year_sorts_by_paper_id_and_undated_last(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    upsert_index_entry(root, VBENCH, "VBench")
    upsert_index_entry(root, SVD, "Stable Video Diffusion")
    upsert_index_entry(root, "x", "Non Catalog")
    text = (root / "index.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Video Paper Wiki"
    assert lines[1] == LINE_SVD
    assert lines[2] == LINE_VBENCH
    assert lines[3] == "[Non Catalog](papers/x.md)"
    assert " (" not in lines[3]
    assert lines[3].endswith(".md)")


def test_ingest_out_of_order_catalog_papers_sorts_year_then_id(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    assert _ingest(TINY_PDF, COGVIDEOX, dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, TOWARDS, dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, MAKE_A_VIDEO, dest) == 0
    _stdout_json(capsys)

    text = (dest / "index.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Video Paper Wiki"
    papers = _paper_lines(text)
    assert papers == [LINE_2018, LINE_2022, LINE_2024]
    assert lines.index("## 主题") == lines.index(LINE_2024) + 1
    assert "[视频扩散](wiki/video-diffusion.md)" in lines
    topics_links = [line for line in lines if line.startswith("[") and "](wiki/" in line]
    assert topics_links[0] == "[视频扩散](wiki/video-diffusion.md)"
    assert not (dest / "wiki" / "index.md").exists()
    work = tmp_path / ".work" / "notes"
    for paper_id in (COGVIDEOX, TOWARDS, MAKE_A_VIDEO):
        fm = work.joinpath(f"{paper_id}.md").read_text(encoding="utf-8").split("---", 2)[1]
        assert "arxiv_id" not in fm
        assert "year:" not in fm
        assert "topics:" not in fm
    assert network_attempts == []


def test_ingest_same_year_by_paper_id_and_undated_after(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    assert _ingest(TINY_PDF, VBENCH, dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, SVD, dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, "x", dest) == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    (dest / "papers" / "x.md").write_text("---\ntitle: x\npaper_id: x\n---\n", encoding="utf-8")
    upsert_index_entry(dest, "x", "x")
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--paper-id", "x"])
    assert code == 0
    capsys.readouterr()

    text = (dest / "index.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Video Paper Wiki"
    papers = _paper_lines(text)
    assert papers[0] == LINE_SVD
    assert papers[1] == LINE_VBENCH
    assert papers[2].startswith("[") and f"](papers/x.md)" in papers[2]
    assert " (20" not in papers[2]
    assert papers[2].endswith(".md)")
    assert lines.index("## 主题") == lines.index(papers[2]) + 1
    assert not (dest / "wiki" / "index.md").exists()
    work_x = (tmp_path / ".work" / "notes" / "x.md").read_text(encoding="utf-8")
    fm = work_x.split("---", 2)[1]
    assert "arxiv_id" not in fm
    assert "year:" not in fm
    assert "topics:" not in fm
    assert network_attempts == []
