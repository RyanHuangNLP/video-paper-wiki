from __future__ import annotations

import hashlib
import json
from pathlib import Path

from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_ingest_put_tiny_pdf_writes_blob(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    expected = hashlib.sha256(TINY_PDF.read_bytes()).hexdigest()
    code = main(["ingest", "put", "--path", str(TINY_PDF)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.put"
    assert payload["data"]["sha256"] == expected
    stored = blob_root / expected
    assert stored.is_file()
    assert stored.read_bytes() == TINY_PDF.read_bytes()
    assert payload["data"]["path"] == stored.as_posix()
    assert network_attempts == []


def test_ingest_put_missing_path_no_network(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    missing = tmp_path / "missing.pdf"
    code = main(["ingest", "put", "--path", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "ingest.put"
    assert payload["error"]["code"] == "BLOB_SOURCE_NOT_FOUND"
    assert not (tmp_path / "blobs").exists()
    assert network_attempts == []
