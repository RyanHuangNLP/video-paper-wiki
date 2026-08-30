from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import make_checkout
from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_ingest_run_is_removed(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(["ingest", "run", "--path", str(TINY_PDF)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert not (tmp_path / ".work" / "notes").exists()
    assert network_attempts == []


def test_ingest_run_with_copy_flags_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(
        [
            "ingest",
            "run",
            "--path",
            str(TINY_PDF),
            "--paper-id",
            "arxiv-2311.15127",
            "--vault",
            str(dest),
        ]
    )
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert list(dest.iterdir()) == []
    assert network_attempts == []


@pytest.mark.parametrize("paper_id", ["", "/", "..", "a/b", "a\\b", "foo/../bar"])
def test_ingest_run_illegal_paper_id_is_usage(
    paper_id, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--paper-id", paper_id])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert not (tmp_path / ".work").exists() or not any(
        tmp_path.joinpath(".work").rglob("*")
    )
    assert network_attempts == []


def test_ingest_run_pdf_dir_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    code = main(["ingest", "run", "--pdf-dir", str(pdf_dir)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []
