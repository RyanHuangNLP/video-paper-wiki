from __future__ import annotations

import json
from pathlib import Path

from tests.support import make_checkout, plant_blob, work_prepared
from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]


def _stdout_json(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


def test_prepare_success_with_local_blob(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, b"vpkb-000-02-blob")
    code = main(
        [
            "ingest",
            "prepare",
            "--sha256",
            digest,
            "--batch-id",
            "t1",
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    staged = Path(payload["data"]["staged_path"])
    assert staged == work_prepared(tmp_path, "t1", digest)
    assert staged.is_file()
    assert staged.read_bytes() == b"vpkb-000-02-blob"
    assert payload["data"]["already_staged"] is False
    assert payload["data"]["approval_hash_present"] is False
    assert network_attempts == []


def test_prepare_missing_blob_exit_2_no_network(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    missing = "a" * 64
    code = main(["ingest", "prepare", "--sha256", missing, "--batch-id", "t1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert network_attempts == []


def test_prepare_approval_hash_does_not_download_or_reject_existing_blob(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, b"keep-me")
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
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["data"]["approval_hash_present"] is True
    assert "verified" not in payload["data"]
    assert Path(payload["data"]["staged_path"]).is_file()
    assert network_attempts == []


def test_prepare_approval_hash_without_blob_still_exit_2_no_network(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(
        [
            "ingest",
            "prepare",
            "--sha256",
            "c" * 64,
            "--approval-hash",
            "d" * 64,
            "--batch-id",
            "t3",
        ]
    )
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert payload["error"]["details"]["approval_hash_present"] is True
    assert network_attempts == []


def test_code_map_prepare_same_contract(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(["code-map", "prepare", "--sha256", "e" * 64, "--batch-id", "cm0"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "code-map.prepare"
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert network_attempts == []


def test_code_map_prepare_success(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, b"code-map")
    code = main(
        [
            "code-map",
            "prepare",
            "--sha256",
            digest,
            "--batch-id",
            "cm1",
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "code-map.prepare"
    assert Path(payload["data"]["staged_path"]).is_file()
    assert Path(payload["data"]["staged_path"]) == work_prepared(tmp_path, "cm1", digest)
    assert network_attempts == []


def test_prepare_missing_batch_id_is_usage(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["ingest", "prepare", "--sha256", "a" * 64])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_doctor_json_valid(capsys, network_attempts) -> None:
    code = main(["doctor"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "doctor"
    assert network_attempts == []
