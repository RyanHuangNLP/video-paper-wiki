from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import make_checkout, work_review
from video_paper_wiki.cli import main
from video_paper_wiki.notes.section import section_text

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
from video_paper_wiki.identity import claim_id

MAV = "arxiv:2209.14792"
MAV_QUESTION = "没有成对视频-文本数据时，怎样做文生视频？"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _claim_draft(tmp_path: Path, paper_id: str = "sha256:" + "0" * 64) -> Path:
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    document["title"] = "Make-A-Video" if paper_id == MAV else "Claims"
    document["claims"] = [
        {
            "claim_id": claim_id(f"paper:{paper_id}", CLAIM_TEXT),
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
                    "artifact_path": ".raw/derived/" + CLAIM_SHA + "/docling/fp/document.json",
                    "artifact_sha256": CLAIM_SHA,
                    "text_sha256": TEXT_SHA,
                }
            ],
        }
    ]
    path = tmp_path / f"{paper_id}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _clone_draft(tmp_path: Path, paper_id: str, title: str) -> Path:
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    document["title"] = title
    path = tmp_path / f"{paper_id}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_export_minimal_fixture_missing_frozen_seed(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["review", "export", "--draft", str(MINIMAL), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "review.export"
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == json.loads(MINIMAL.read_text(encoding="utf-8"))["paper_id"]
    assert not work_review(tmp_path, "b1").exists()
    assert network_attempts == []


def test_export_vault_flag_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "obsidian-root"
    existing.mkdir()
    code = main(
        [
            "review",
            "export",
            "--draft",
            str(MINIMAL),
            "--batch-id",
            "b1",
            "--vault",
            str(existing),
        ]
    )
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert list(existing.iterdir()) == []
    assert network_attempts == []


def test_export_missing_batch_id_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["review", "export", "--draft", str(MINIMAL)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_export_invalid_draft(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "video-paper-wiki.paper-analysis-draft.v1"}\n', encoding="utf-8")
    code = main(["review", "export", "--draft", str(bad), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "DRAFT_INVALID"
    assert not work_review(tmp_path, "b1").exists()
    assert network_attempts == []


def test_export_bad_json_and_missing_file(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    code = main(["review", "export", "--draft", str(broken), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "DRAFT_INVALID"
    code = main(["review", "export", "--draft", str(tmp_path / "nope.json"), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "DRAFT_INVALID"
    assert network_attempts == []


def test_export_catalog_paper_writes_work_review(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    draft_path = _clone_draft(tmp_path, MAV, "Make-A-Video")
    code = main(["review", "export", "--draft", str(draft_path), "--batch-id", "b1"])
    assert code == 0
    payload = _stdout_json(capsys)
    written = work_review(tmp_path, "b1")
    assert payload["ok"] is True
    assert payload["command"] == "review.export"
    assert payload["data"]["path"] == written.as_posix()
    assert payload["data"]["paper_id"] == MAV
    assert payload["data"]["batch_id"] == "b1"
    assert payload["data"]["already_staged"] is False
    assert "vault_path" not in payload["data"]
    assert written.is_file()
    text = written.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert f"paper_id: {MAV}" in text or f'paper_id: "{MAV}"' in text
    assert "title: Make-A-Video" in text
    for heading in HEADING_ZH:
        assert f"## {heading}" in text
    positions = [text.index(f"## {heading}") for heading in HEADING_ZH]
    assert positions == sorted(positions)
    assert section_text(text, "研究问题") == MAV_QUESTION
    assert MAV not in written.as_posix().split(".work", 1)[1]
    assert not (tmp_path / "index.md").exists()
    assert list(tmp_path.rglob("index.md")) == []
    assert network_attempts == []


def test_export_claims_under_frozen_headings(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    draft_path = _claim_draft(tmp_path, MAV)
    code = main(["review", "export", "--draft", str(draft_path), "--batch-id", "b1"])
    assert code == 0
    payload = _stdout_json(capsys)
    written = work_review(tmp_path, "b1")
    assert payload["data"]["paper_id"] == MAV
    assert payload["data"]["path"] == written.as_posix()
    text = written.read_text(encoding="utf-8")
    assert CLAIM_TEXT not in text
    for heading in HEADING_ZH:
        assert f"## {heading}" in text
    assert network_attempts == []


def test_export_page_slug_paper_id_is_invalid(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = "arxiv-2209.14792"
    draft = tmp_path / "slug.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "INVALID_PAPER_ID"
    assert not work_review(tmp_path, "b1").exists()
    assert network_attempts == []


def test_export_missing_claim_id_does_not_exit_zero(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = MAV
    document["title"] = "Make-A-Video"
    document["claims"] = [
        {
            "claim_text": CLAIM_TEXT,
            "section": "method",
            "core": True,
            "assessment": "provisional",
            "locators": [],
        }
    ]
    draft = tmp_path / "missing-claim-id.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] in {"DRAFT_INVALID", "CLAIM_ID_MISMATCH"}
    assert not work_review(tmp_path, "b1").exists()
    assert network_attempts == []


def test_export_old_style_arxiv_is_not_rejected_as_path_token(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = "arxiv:hep-th/9901001"
    draft = tmp_path / "old-arxiv.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == "arxiv:hep-th/9901001"
    assert not work_review(tmp_path, "b1").exists()
    assert network_attempts == []


@pytest.mark.parametrize("paper_id", ["/tmp", "../", "a\\b", "..", "foo/../bar"])
def test_export_illegal_paper_id_does_not_write(
    paper_id, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    draft = tmp_path / "bad-id.json"
    draft.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "review.export"
    assert payload["error"]["code"] == "INVALID_PAPER_ID"
    assert not work_review(tmp_path, "b1").exists()
    assert network_attempts == []


def test_export_does_not_write_index(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    draft_path = _clone_draft(tmp_path, MAV, "Make-A-Video")
    code = main(["review", "export", "--draft", str(draft_path), "--batch-id", "b1"])
    assert code == 0
    capsys.readouterr()
    assert not (tmp_path / "index.md").exists()
    assert list(tmp_path.rglob("index.md")) == []
    assert network_attempts == []
