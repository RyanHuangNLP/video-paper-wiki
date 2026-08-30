from __future__ import annotations

from pathlib import Path
import re

from tests.support import make_checkout
from video_paper_wiki.cli import main
from video_paper_wiki.notes.wiki_show import load_topic, scan_wiki_list

ROOT = Path(__file__).resolve().parents[2]
_PAPER_LINK = re.compile(r"\[([^\]]+)\]\(\.\./papers/([^/\s)]+)\.md\)(?: \((\d{4})\))?")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _link_count(text: str) -> int:
    return len(_PAPER_LINK.findall(text))


def test_list_exists_without_wiki_is_empty_pages(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    assert scan_wiki_list(notes)["pages"] == []
    assert not (notes / "wiki").exists()
    assert list(notes.rglob("*")) == before
    assert network_attempts == []


def test_list_empty_wiki_is_empty_pages(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    (notes / "wiki").mkdir(parents=True)
    assert scan_wiki_list(notes)["pages"] == []
    assert network_attempts == []


def test_list_handwritten_pages_sorted_by_id(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    evaluation_text = (
        "# 评测\n"
        "\n"
        "评测简介。\n"
        "\n"
        "[Towards Accurate Generative Models of Video](../papers/arxiv-1812.01717.md) (2018)\n"
        "[VBench](../papers/arxiv-2311.15127.md) (2023)\n"
    )
    data_text = (
        "# 数据\n"
        "\n"
        "数据简介。\n"
        "\n"
        "[WebVid](../papers/arxiv-2104.00655.md) (2021)\n"
    )
    _write(notes / "wiki" / "evaluation.md", evaluation_text)
    _write(notes / "wiki" / "data.md", data_text)
    pages = scan_wiki_list(notes)["pages"]
    assert [item["id"] for item in pages] == ["data", "evaluation"]
    assert pages[0]["heading_zh"] == "数据"
    assert pages[0]["blurb_zh"] == "数据简介。"
    assert pages[0]["paper_count"] == _link_count(data_text)
    assert pages[1]["heading_zh"] == "评测"
    shown = load_topic(notes, "evaluation")
    assert shown is not None
    assert pages[1]["paper_count"] == len(shown["papers"])
    assert network_attempts == []


def test_list_ignores_nested_wiki_and_rejected_stems(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(notes / "wiki" / "nested" / "x.md", "# nested\n\nnested only\n")
    _write(notes / "wiki" / "foo.bar.md", "# dotted\n\nshould be skipped\n")
    _write(notes / "wiki" / "keep.md", "# 保留\n\n顶层页面。\n")
    pages = scan_wiki_list(notes)["pages"]
    assert [item["id"] for item in pages] == ["keep"]
    assert pages[0]["heading_zh"] == "保留"
    assert network_attempts == []


def test_deleted_wiki_cli_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["wiki", "list"]) == 2
    assert main(["wiki", "list", "--vault", str(tmp_path)]) == 2
    assert network_attempts == []
