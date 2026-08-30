from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_ingest_run_without_copy_writes_work_drafts_and_notes(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    code = main(["ingest", "run", "--path", str(TINY_PDF)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.run"
    data = payload["data"]
    sha256 = data["sha256"]
    paper_id = data["paper_id"]
    draft_path = Path(data["draft_path"])
    note_path = Path(data["note_path"])
    assert paper_id == sha256[:12]
    assert draft_path == tmp_path / ".work" / "drafts" / paper_id / "paper-analysis-draft.v1.json"
    assert note_path == tmp_path / ".work" / "notes" / f"{paper_id}.md"
    assert draft_path.is_file()
    assert note_path.is_file()
    assert "vault_path" not in data
    assert network_attempts == []


def test_ingest_run_existing_dir_copies_papers_and_reports_copy(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    existing = tmp_path / "obsidian-root"
    existing.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--vault", str(existing)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.run"
    data = payload["data"]
    paper_id = data["paper_id"]
    copied = existing / "papers" / f"{paper_id}.md"
    assert Path(data["draft_path"]).is_file()
    assert Path(data["note_path"]).is_file()
    assert data["vault_path"] == copied.as_posix()
    assert copied.is_file()
    assert copied.read_text(encoding="utf-8") == Path(data["note_path"]).read_text(encoding="utf-8")
    assert network_attempts == []


def test_ingest_run_missing_pdf_blob_source_not_found(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    missing = tmp_path / "missing.pdf"
    code = main(["ingest", "run", "--path", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "ingest.put"
    assert payload["error"]["code"] == "BLOB_SOURCE_NOT_FOUND"
    assert not (tmp_path / ".work").exists()
    assert network_attempts == []


def test_ingest_run_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    missing = tmp_path / "missing-root"
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--vault", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []
