from __future__ import annotations

import json
from pathlib import Path

from tests.support import make_checkout
from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_ingest_put_is_removed(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["ingest", "put", "--path", str(TINY_PDF)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert not (tmp_path / "blobs").exists()
    assert network_attempts == []


def test_ingest_put_missing_path_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["ingest", "put", "--path", str(tmp_path / "missing.pdf")])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []
