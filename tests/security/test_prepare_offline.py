from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from video_paper_wiki.cli import main

APPROVAL_REF = "a" * 64


@pytest.mark.parametrize("command", ["ingest", "code-map"])
@pytest.mark.parametrize("with_approval", [False, True])
def test_missing_blob_is_offline_rejection(
    command: str, with_approval: bool, tmp_path: Path, network_attempts: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = [command, "prepare", "--blob", str(tmp_path / "missing.bin"),
            "--work-dir", str(tmp_path / "work")]
    if with_approval:
        argv.extend(["--approval-ref", APPROVAL_REF])
    assert main(argv) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert network_attempts == []


@pytest.mark.parametrize("command", ["ingest", "code-map"])
@pytest.mark.parametrize("with_approval", [False, True])
def test_existing_blob_is_staged_without_network(
    command: str, with_approval: bool, tmp_path: Path, network_attempts: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = b"local-only blob\x00bytes"
    blob = tmp_path / "input.bin"
    blob.write_bytes(content)
    argv = [command, "prepare", "--blob", str(blob), "--work-dir",
            str(tmp_path / "work"), "--batch-id", "test-batch"]
    if with_approval:
        argv.extend(["--approval-ref", APPROVAL_REF])
    assert main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    result = payload["result"]
    assert payload["ok"] is True
    assert result["status"] == "prepared"
    assert result["blob_sha256"] == hashlib.sha256(content).hexdigest()
    staged = Path(result["staged_path"])
    assert staged.is_file() and staged.read_bytes() == content
    assert (result.get("approval_ref") == APPROVAL_REF) is with_approval
    assert network_attempts == []
