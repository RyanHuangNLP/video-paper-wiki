from __future__ import annotations

from pathlib import Path

from tests.support import make_checkout
from video_paper_wiki.cli import main
from video_paper_wiki.notes.wiki_show import load_topic


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_show_unsafe_topic_ids_are_not_found(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    for topic_id in ("../x", "foo/bar", "foo.md", "."):
        assert load_topic(notes, topic_id) is None
    assert list(notes.rglob("*")) == before
    assert not (tmp_path / "x.md").exists()
    assert network_attempts == []


def test_show_missing_wiki_page_does_not_create(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    assert load_topic(notes, "evaluation") is None
    assert not (notes / "wiki").exists()
    assert list(notes.rglob("*")) == before
    assert network_attempts == []


def test_show_handwritten_page_file_order(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(
        notes / "wiki" / "evaluation.md",
        "# 评测\n"
        "\n"
        "这是简介。\n"
        "\n"
        "[Towards Accurate Generative Models of Video](../papers/arxiv-1812.01717.md) (2018)\n"
        "[VBench](../papers/arxiv-2311.15127.md) (2023)\n",
    )
    original = (notes / "wiki" / "evaluation.md").read_text(encoding="utf-8")
    data = load_topic(notes, "evaluation")
    assert data is not None
    assert data["id"] == "evaluation"
    assert data["heading_zh"] == "评测"
    assert data["blurb_zh"] == "这是简介。"
    assert data["papers"] == [
        {
            "paper_id": "arxiv-1812.01717",
            "title": "Towards Accurate Generative Models of Video",
            "year": 2018,
        },
        {"paper_id": "arxiv-2311.15127", "title": "VBench", "year": 2023},
    ]
    assert (notes / "wiki" / "evaluation.md").read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_show_h1_only_empty_blurb_and_papers(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(notes / "wiki" / "evaluation.md", "# 评测\n")
    data = load_topic(notes, "evaluation")
    assert data is not None
    assert data["heading_zh"] == "评测"
    assert data["blurb_zh"] == ""
    assert data["papers"] == []
    assert network_attempts == []


def test_show_ignores_nested_wiki(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(notes / "wiki" / "nested" / "evaluation.md", "# 评测\n\nnested only\n")
    assert load_topic(notes, "evaluation") is None
    assert (notes / "wiki" / "nested" / "evaluation.md").is_file()
    assert not (notes / "wiki" / "evaluation.md").exists()
    assert network_attempts == []


def test_show_ignores_related_topic_links(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(
        notes / "wiki" / "evaluation.md",
        "# 评测\n"
        "\n"
        "这是简介。\n"
        "\n"
        "[VBench](../papers/arxiv-2311.17982.md) (2023)\n"
        "\n"
        "## 相关主题\n"
        "[数据](./data.md)\n"
        "[视频扩散](./video-diffusion.md)\n",
    )
    data = load_topic(notes, "evaluation")
    assert data is not None
    assert data["papers"] == [
        {"paper_id": "arxiv-2311.17982", "title": "VBench", "year": 2023}
    ]
    assert "related" not in data
    assert network_attempts == []


def test_deleted_wiki_show_cli_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["wiki", "show", "evaluation"]) == 2
    assert main(["wiki", "show", "--vault", str(tmp_path), "evaluation"]) == 2
    assert network_attempts == []
