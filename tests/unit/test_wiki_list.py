from __future__ import annotations

import json
import re
from pathlib import Path

from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"

_PAPER_LINK = re.compile(r"\[([^\]]+)\]\(\.\./papers/([^/\s)]+)\.md\)(?: \((\d{4})\))?")


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _link_count(text: str) -> int:
    return len(_PAPER_LINK.findall(text))


def test_list_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["wiki", "list", "--vault", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "wiki.list"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_list_missing_vault_flag_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["wiki", "list"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_list_exists_without_wiki_is_empty_pages(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    code = main(["wiki", "list", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "wiki.list"
    assert payload["data"]["pages"] == []
    assert not (notes / "wiki").exists()
    assert list(notes.rglob("*")) == before
    assert network_attempts == []


def test_list_empty_wiki_is_empty_pages(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    (notes / "wiki").mkdir(parents=True)
    code = main(["wiki", "list", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "wiki.list"
    assert payload["data"]["pages"] == []
    assert network_attempts == []


def test_list_handwritten_pages_sorted_by_id(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
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
    # evaluation is later in alpha; write it first so disk order is not id order.
    _write(notes / "wiki" / "evaluation.md", evaluation_text)
    _write(notes / "wiki" / "data.md", data_text)
    originals = {
        "evaluation": (notes / "wiki" / "evaluation.md").read_text(encoding="utf-8"),
        "data": (notes / "wiki" / "data.md").read_text(encoding="utf-8"),
    }

    code = main(["wiki", "list", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "wiki.list"
    pages = payload["data"]["pages"]
    assert [item["id"] for item in pages] == ["data", "evaluation"]
    assert pages[0]["heading_zh"] == "数据"
    assert pages[0]["blurb_zh"] == "数据简介。"
    assert pages[0]["paper_count"] == _link_count(data_text)
    assert pages[1]["heading_zh"] == "评测"
    assert pages[1]["blurb_zh"] == "评测简介。"
    assert pages[1]["paper_count"] == _link_count(evaluation_text)
    for item in pages:
        assert "papers" not in item
        assert set(item) == {"id", "heading_zh", "blurb_zh", "paper_count"}
        assert isinstance(item["paper_count"], int)
        assert not isinstance(item["paper_count"], bool)

    for topic_id in ("data", "evaluation"):
        code = main(["wiki", "show", "--vault", str(notes), topic_id])
        assert code == 0
        shown = _stdout_json(capsys)["data"]
        listed = next(item for item in pages if item["id"] == topic_id)
        assert listed["heading_zh"] == shown["heading_zh"]
        assert listed["blurb_zh"] == shown["blurb_zh"]
        assert listed["paper_count"] == len(shown["papers"])

    assert (notes / "wiki" / "evaluation.md").read_text(encoding="utf-8") == originals[
        "evaluation"
    ]
    assert (notes / "wiki" / "data.md").read_text(encoding="utf-8") == originals["data"]
    assert network_attempts == []


def test_list_ignores_nested_wiki_and_rejected_stems(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(notes / "wiki" / "nested" / "x.md", "# nested\n\nnested only\n")
    _write(notes / "wiki" / "foo.bar.md", "# dotted\n\nshould be skipped\n")
    _write(notes / "wiki" / "keep.md", "# 保留\n\n顶层页面。\n")
    code = main(["wiki", "list", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    pages = payload["data"]["pages"]
    assert [item["id"] for item in pages] == ["keep"]
    assert pages[0]["heading_zh"] == "保留"
    assert pages[0]["blurb_zh"] == "顶层页面。"
    assert pages[0]["paper_count"] == 0
    assert "papers" not in pages[0]
    assert (notes / "wiki" / "nested" / "x.md").is_file()
    assert (notes / "wiki" / "foo.bar.md").is_file()
    assert network_attempts == []


def test_list_after_ingest_make_a_video(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(
        [
            "ingest",
            "run",
            "--path",
            str(TINY_PDF),
            "--paper-id",
            "arxiv-2209.14792",
            "--vault",
            str(dest),
        ]
    )
    assert code == 0
    capsys.readouterr()
    wiki_dir = dest / "wiki"
    originals = {
        path.name: path.read_text(encoding="utf-8")
        for path in wiki_dir.iterdir()
        if path.is_file() and path.suffix == ".md"
    }
    code = main(["wiki", "list", "--vault", str(dest)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "wiki.list"
    pages = payload["data"]["pages"]
    ids = [item["id"] for item in pages]
    assert len(pages) == 6
    assert ids == sorted(ids)
    for item in pages:
        assert "papers" not in item
        assert set(item) == {"id", "heading_zh", "blurb_zh", "paper_count"}
        assert isinstance(item["paper_count"], int)
    video = next(item for item in pages if item["id"] == "video-diffusion")
    assert video["heading_zh"] == "视频扩散"
    assert video["paper_count"] >= 1
    for name, text in originals.items():
        assert (wiki_dir / name).read_text(encoding="utf-8") == text
    assert network_attempts == []
