from __future__ import annotations

import json
import re
from pathlib import Path

from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"

_PAPER_LINK = re.compile(
    r"\[([^\]]+)\]\(\.\./papers/([^/\s)]+)\.md\)(?: \((\d{4})\))?"
)


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _envelope_from_page(topic_id: str, text: str) -> dict:
    heading_zh = ""
    rest = text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            heading_zh = line[2:].strip()
            rest = "\n".join(lines[i + 1 :])
            break
    first = _PAPER_LINK.search(rest)
    if first is None:
        blurb_zh = rest.strip()
        papers: list[dict] = []
    else:
        blurb_zh = rest[: first.start()].strip()
        papers = []
        for match in _PAPER_LINK.finditer(rest):
            year_raw = match.group(3)
            papers.append(
                {
                    "paper_id": match.group(2),
                    "title": match.group(1),
                    "year": int(year_raw) if year_raw is not None else None,
                }
            )
    return {
        "id": topic_id,
        "heading_zh": heading_zh,
        "blurb_zh": blurb_zh,
        "papers": papers,
    }


def test_show_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["wiki", "show", "--vault", str(missing), "evaluation"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "wiki.show"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_show_empty_topic_id_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["wiki", "show", "--vault", str(notes), ""])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "wiki.show"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_show_missing_vault_flag_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["wiki", "show", "evaluation"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_show_unsafe_topic_ids_are_not_found(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    for topic_id in ("../x", "foo/bar", "foo.md", "."):
        code = main(["wiki", "show", "--vault", str(notes), topic_id])
        assert code == 2
        payload = _stdout_json(capsys)
        assert payload["ok"] is False
        assert payload["command"] == "wiki.show"
        assert payload["error"]["code"] == "TOPIC_NOT_FOUND"
    assert list(notes.rglob("*")) == before
    assert not (tmp_path / "x.md").exists()
    assert not (notes / "wiki").exists()
    assert network_attempts == []


def test_show_missing_wiki_page_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    code = main(["wiki", "show", "--vault", str(notes), "evaluation"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "wiki.show"
    assert payload["error"]["code"] == "TOPIC_NOT_FOUND"
    assert not (notes / "wiki").exists()
    assert list(notes.rglob("*")) == before
    assert network_attempts == []


def test_show_handwritten_page_file_order(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
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
    code = main(["wiki", "show", "--vault", str(notes), "evaluation"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "wiki.show"
    data = payload["data"]
    assert data["id"] == "evaluation"
    assert data["heading_zh"] == "评测"
    assert data["blurb_zh"] == "这是简介。"
    assert data["papers"] == [
        {
            "paper_id": "arxiv-1812.01717",
            "title": "Towards Accurate Generative Models of Video",
            "year": 2018,
        },
        {
            "paper_id": "arxiv-2311.15127",
            "title": "VBench",
            "year": 2023,
        },
    ]
    assert isinstance(data["papers"][0]["year"], int)
    assert isinstance(data["papers"][1]["year"], int)
    assert not isinstance(data["papers"][0]["year"], str)
    assert (notes / "wiki" / "evaluation.md").read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_show_h1_only_empty_blurb_and_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(notes / "wiki" / "evaluation.md", "# 评测\n")
    code = main(["wiki", "show", "--vault", str(notes), "evaluation"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    data = payload["data"]
    assert data["id"] == "evaluation"
    assert data["heading_zh"] == "评测"
    assert data["blurb_zh"] == ""
    assert data["papers"] == []
    assert network_attempts == []


def test_show_after_ingest_make_a_video(
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
    page = dest / "wiki" / "video-diffusion.md"
    original = page.read_text(encoding="utf-8")
    expected = _envelope_from_page("video-diffusion", original)
    code = main(["wiki", "show", "--vault", str(dest), "video-diffusion"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "wiki.show"
    data = payload["data"]
    assert data == expected
    assert data["id"] == "video-diffusion"
    assert data["heading_zh"] == "视频扩散"
    assert data["blurb_zh"]
    mav = next(item for item in data["papers"] if item["title"] == "Make-A-Video")
    assert mav["year"] == 2022
    assert isinstance(mav["year"], int)
    assert not isinstance(mav["year"], str)
    assert page.read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_show_ignores_nested_wiki(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "wiki" / "nested" / "evaluation.md",
        "# 评测\n\nnested only\n",
    )
    code = main(["wiki", "show", "--vault", str(notes), "evaluation"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "wiki.show"
    assert payload["error"]["code"] == "TOPIC_NOT_FOUND"
    assert (notes / "wiki" / "nested" / "evaluation.md").is_file()
    assert not (notes / "wiki" / "evaluation.md").exists()
    assert network_attempts == []


def test_show_ignores_related_topic_links(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
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
    original = (notes / "wiki" / "evaluation.md").read_text(encoding="utf-8")
    code = main(["wiki", "show", "--vault", str(notes), "evaluation"])
    assert code == 0
    payload = _stdout_json(capsys)
    data = payload["data"]
    assert data["id"] == "evaluation"
    assert data["heading_zh"] == "评测"
    assert data["blurb_zh"] == "这是简介。"
    assert data["papers"] == [
        {
            "paper_id": "arxiv-2311.17982",
            "title": "VBench",
            "year": 2023,
        }
    ]
    assert "related" not in data
    assert "data" not in {item["paper_id"] for item in data["papers"]}
    assert (notes / "wiki" / "evaluation.md").read_text(encoding="utf-8") == original
    assert network_attempts == []
