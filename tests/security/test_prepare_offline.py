from __future__ import annotations

import json
import os
from pathlib import Path

from video_paper_wiki.blob_store import BlobStore
from video_paper_wiki.cli import main


def _stdout_json(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


def test_prepare_success_with_local_blob(tmp_path: Path, monkeypatch, capsys, network_attempts) -> None:
    blob_root = tmp_path / "blobs"
    work = tmp_path / "work"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    src = tmp_path / "payload.bin"
    src.write_bytes(b"vpkb-000-02-blob")
    digest = BlobStore(blob_root).put_from_path(src)
    code = main(
        [
            "ingest",
            "prepare",
            "--sha256",
            digest,
            "--batch-id",
            "t1",
            "--work-dir",
            str(work),
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    staged = Path(payload["data"]["staged_path"])
    assert staged.is_file()
    assert staged.read_bytes() == b"vpkb-000-02-blob"
    assert network_attempts == []


def test_prepare_missing_blob_exit_2_no_network(tmp_path: Path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    missing = "a" * 64
    code = main(["ingest", "prepare", "--sha256", missing])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert network_attempts == []


def test_prepare_approval_hash_does_not_download_or_reject_existing_blob(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    work = tmp_path / "work"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    src = tmp_path / "payload.bin"
    src.write_bytes(b"keep-me")
    digest = BlobStore(blob_root).put_from_path(src)
    approval = "b" * 64
    code = main(
        [
            "ingest",
            "prepare",
            "--sha256",
            digest,
            "--approval-hash",
            approval,
            "--batch-id",
            "t2",
            "--work-dir",
            str(work),
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["data"]["approval_hash_present"] is True
    assert Path(payload["data"]["staged_path"]).is_file()
    assert network_attempts == []


def test_prepare_approval_hash_without_blob_still_exit_2_no_network(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(
        ["ingest", "prepare", "--sha256", "c" * 64, "--approval-hash", "d" * 64]
    )
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert payload["error"]["details"]["approval_hash_present"] is True
    assert network_attempts == []


def test_code_map_prepare_same_contract(tmp_path: Path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(["code-map", "prepare", "--sha256", "e" * 64])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "code-map.prepare"
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert network_attempts == []


def test_code_map_prepare_success(tmp_path: Path, monkeypatch, capsys, network_attempts) -> None:
    blob_root = tmp_path / "blobs"
    work = tmp_path / "work"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    src = tmp_path / "payload.bin"
    src.write_bytes(b"code-map")
    digest = BlobStore(blob_root).put_from_path(src)
    code = main(
        [
            "code-map",
            "prepare",
            "--sha256",
            digest,
            "--batch-id",
            "cm1",
            "--work-dir",
            str(work),
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "code-map.prepare"
    assert Path(payload["data"]["staged_path"]).is_file()
    assert network_attempts == []


def test_doctor_json_valid(capsys, network_attempts) -> None:
    code = main(["doctor"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "doctor"
    assert network_attempts == []
