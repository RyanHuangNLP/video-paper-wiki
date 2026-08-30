from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
HEADING_ZH = [
    "一句话结论",
    "研究问题",
    "方法",
    "表示与架构",
    "训练与数据",
    "实验与结果",
    "局限",
    "代码与资源",
    "证据状态",
    "关联",
]
CLAIM_TEXT = "The model uses a diffusion transformer."
CLAIM_SHA = "a" * 64
TEXT_SHA = "b" * 64


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _claim_draft(tmp_path: Path) -> Path:
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = "fixture-claims"
    document["claims"] = [
        {
            "claim_text": CLAIM_TEXT,
            "section": "method",
            "core": True,
            "assessment": "provisional",
            "locators": [
                {
                    "kind": "pdf",
                    "source_id": "src-paper",
                    "page": 3,
                    "ref": "#/texts/7",
                    "artifact_path": "sources/src-paper/paper.pdf",
                    "artifact_sha256": CLAIM_SHA,
                    "text_sha256": TEXT_SHA,
                }
            ],
        }
    ]
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_export_minimal_fixture_writes_work_notes(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["review", "export", "--draft", str(MINIMAL)])
    assert code == 0
    payload = _stdout_json(capsys)
    written = tmp_path / ".work" / "notes" / "fixture-minimal.md"
    assert payload["ok"] is True
    assert payload["command"] == "review.export"
    assert payload["data"]["path"] == written.as_posix()
    assert payload["data"]["paper_id"] == "fixture-minimal"
    assert "vault_path" not in payload["data"]
    assert written.is_file()
    text = written.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "paper_id: fixture-minimal" in text
    assert "title: Minimal Draft Fixture" in text
    assert "title_zh: 最小草稿夹具" in text
    for heading in HEADING_ZH:
        assert f"## {heading}" in text
    positions = [text.index(f"## {heading}") for heading in HEADING_ZH]
    assert positions == sorted(positions)
    assert not (tmp_path / "index.md").exists()
    assert list(tmp_path.rglob("index.md")) == []
    assert network_attempts == []


def test_export_existing_dir_fixture_missing_frozen_seed(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "obsidian-root"
    existing.mkdir()
    code = main(["review", "export", "--draft", str(MINIMAL), "--vault", str(existing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "review.export"
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == "fixture-minimal"
    assert not (existing / "papers").exists()
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []


def test_export_missing_dir_refuses_and_does_not_create(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["review", "export", "--draft", str(MINIMAL), "--vault", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "review.export"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []


def test_export_invalid_draft(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "video-paper-wiki.paper-analysis-draft.v1"}\n', encoding="utf-8")
    code = main(["review", "export", "--draft", str(bad)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "DRAFT_INVALID"
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []


def test_export_bad_json_and_missing_file(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    code = main(["review", "export", "--draft", str(broken)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "DRAFT_INVALID"
    code = main(["review", "export", "--draft", str(tmp_path / "nope.json")])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "DRAFT_INVALID"
    assert network_attempts == []


def test_export_claims_under_frozen_headings(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    draft_path = _claim_draft(tmp_path)
    code = main(["review", "export", "--draft", str(draft_path)])
    assert code == 0
    payload = _stdout_json(capsys)
    written = tmp_path / ".work" / "notes" / "fixture-claims.md"
    assert payload["data"]["paper_id"] == "fixture-claims"
    assert payload["data"]["path"] == written.as_posix()
    text = written.read_text(encoding="utf-8")
    method_at = text.index("## 方法")
    next_at = text.index("## 表示与架构")
    block = text[method_at:next_at]
    assert CLAIM_TEXT in block
    assert CLAIM_TEXT not in text[:method_at]
    for heading in HEADING_ZH:
        assert f"## {heading}" in text
    assert network_attempts == []



def _clone_draft(tmp_path: Path, paper_id: str, title: str) -> Path:
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    document["title"] = title
    path = tmp_path / f"{paper_id}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_export_two_drafts_keeps_both_index_lines(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "obsidian-root"
    existing.mkdir()
    first = _clone_draft(tmp_path, "arxiv-2209.14792", "Make-A-Video")
    second = _clone_draft(tmp_path, "arxiv-2408.06072", "CogVideoX")
    code = main(["review", "export", "--draft", str(first), "--vault", str(existing)])
    assert code == 0
    capsys.readouterr()
    code = main(["review", "export", "--draft", str(second), "--vault", str(existing)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    index_text = (existing / "index.md").read_text(encoding="utf-8")
    assert "papers/arxiv-2209.14792.md" in index_text
    assert "papers/arxiv-2408.06072.md" in index_text
    assert "Make-A-Video" in index_text
    assert "CogVideoX" in index_text
    assert not (existing / "wiki" / "index.md").exists()
    assert network_attempts == []


@pytest.mark.parametrize("paper_id", ["/tmp", "../", "a\\b", "..", "foo/../bar"])
def test_export_illegal_paper_id_does_not_write(
    paper_id, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    draft = tmp_path / "bad-id.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(draft), "--vault", str(dest)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "review.export"
    assert payload["error"]["code"] == "INVALID_PAPER_ID"
    assert not (tmp_path / ".work" / "notes").exists()
    assert list(dest.iterdir()) == []
    assert network_attempts == []


def test_export_without_notes_root_does_not_write_index(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["review", "export", "--draft", str(MINIMAL)])
    assert code == 0
    capsys.readouterr()
    assert not (tmp_path / "index.md").exists()
    assert list(tmp_path.rglob("index.md")) == []
    assert network_attempts == []
