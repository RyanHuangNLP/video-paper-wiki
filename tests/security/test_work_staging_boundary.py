from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import stat
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.support import make_checkout, plant_blob, work_draft, work_prepared, work_review
from video_paper_wiki.cli import main
from video_paper_wiki.staging import stage_bytes

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
ENVELOPE = ROOT / "schemas" / "video-paper-wiki.cli-envelope.v1.schema.json"
SRC = ROOT / "src" / "video_paper_wiki"
MAV = "arxiv-2209.14792"


def _snapshot(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"__missing__": True}
    out: dict[str, object] = {}
    for current, dirs, files in os.walk(path, followlinks=False):
        rel_dir = os.path.relpath(current, path)
        dir_path = Path(current)
        st = os.lstat(dir_path)
        out[rel_dir] = ("dir", st.st_mode)
        for name in dirs + files:
            child = dir_path / name
            rel = os.path.relpath(child, path)
            cst = os.lstat(child)
            if stat.S_ISLNK(cst.st_mode):
                out[rel] = ("symlink", os.readlink(child), cst.st_mtime_ns)
            elif stat.S_ISREG(cst.st_mode):
                out[rel] = ("file", child.read_bytes())
            elif stat.S_ISFIFO(cst.st_mode):
                out[rel] = ("fifo", cst.st_mode)
            elif stat.S_ISSOCK(cst.st_mode):
                out[rel] = ("sock", cst.st_mode)
            else:
                out[rel] = ("other", cst.st_mode)
    return out


def _stdout_payload(capsys) -> dict:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    return payload


def _clone_mav_draft(tmp_path: Path) -> Path:
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = MAV
    document["title"] = "Make-A-Video"
    path = tmp_path / "mav.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _prepare_checkout(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "secret.bin"
    sentinel.write_bytes(b"SENTINEL-BYTES")
    return checkout, external


@pytest.mark.parametrize(
    "batch_id",
    ["", "/tmp/out", "..", "../x", "a/b", "a\\b", "x" * 129],
)
def test_illegal_batch_id_does_not_touch_external(
    batch_id, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    sentinel = (external / "secret.bin").read_bytes()
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", batch_id])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_BATCH_ID"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == sentinel
    assert network_attempts == []


def test_malicious_paper_id_is_not_used_in_output_path(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    blob_root = checkout / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    paper_id = "../../secret"
    code = main(
        [
            "draft",
            "export",
            "--sha256",
            digest,
            "--paper-id",
            paper_id,
            "--batch-id",
            "b1",
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "INVALID_PAPER_ID"
    assert paper_id not in json.dumps(payload.get("data", {}))
    assert not (checkout / ".work").exists() or paper_id not in str(
        list((checkout / ".work").rglob("*"))
    )
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_work_symlink_refuses_and_leaves_sentinel(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    (checkout / ".work").symlink_to(external)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_batch_symlink_refuses_and_leaves_sentinel(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    work = checkout / ".work"
    work.mkdir()
    (work / "b1").symlink_to(external)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_intermediate_symlink_refuses_and_leaves_sentinel(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    review_dir = checkout / ".work" / "b1" / "review"
    review_dir.parent.mkdir(parents=True)
    review_dir.symlink_to(external)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_target_symlink_refuses_and_leaves_sentinel(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    target = work_review(checkout, "b1")
    target.parent.mkdir(parents=True)
    target.symlink_to(external / "secret.bin")
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_different_byte_target_is_conflict(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    target = work_review(checkout, "b1")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"other-content")
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 75
    assert payload["error"]["code"] == "STAGING_CONFLICT"
    assert target.read_bytes() == b"other-content"
    assert _snapshot(external) == before
    assert network_attempts == []


def test_fifo_and_special_files_are_unsafe(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    fifo_work = checkout / ".work"
    os.mkfifo(fifo_work)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert stat.S_ISFIFO(os.lstat(fifo_work).st_mode)
    os.unlink(fifo_work)
    work_dir = checkout / ".work" / "b1" / "review"
    work_dir.mkdir(parents=True)
    os.mkfifo(work_dir / "paper.md")
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_prepare_symlink_and_conflict_leave_external(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    blob_root = checkout / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, b"vpkb-prepare")
    (checkout / ".work").symlink_to(external)
    before = _snapshot(external)
    code = main(["ingest", "prepare", "--sha256", digest, "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert payload["error"]["details"].get("approval_hash_present") is not True
    assert "verified" not in payload["error"]["message"].lower()
    assert _snapshot(external) == before
    assert network_attempts == []


def test_writable_commands_share_one_batch_tree(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    blob_root = checkout / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    code = main(
        [
            "ingest",
            "prepare",
            "--sha256",
            digest,
            "--batch-id",
            "shared",
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 0
    assert payload["data"]["already_staged"] is False
    assert payload["data"]["approval_hash_present"] is False
    staged = Path(payload["data"]["staged_path"])
    assert staged == work_prepared(checkout, "shared", digest)
    assert staged.is_file()
    code = main(
        [
            "draft",
            "export",
            "--sha256",
            digest,
            "--paper-id",
            MAV,
            "--batch-id",
            "shared",
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 0
    draft_path = Path(payload["data"]["path"])
    assert draft_path == work_draft(checkout, "shared")
    assert MAV not in draft_path.as_posix().split(".work", 1)[1]
    code = main(
        [
            "review",
            "export",
            "--draft",
            str(draft_path),
            "--batch-id",
            "shared",
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 0
    review_path = Path(payload["data"]["path"])
    assert review_path == work_review(checkout, "shared")
    assert MAV not in review_path.as_posix().split(".work", 1)[1]
    work = checkout / ".work" / "shared"
    assert staged.resolve().is_relative_to(work.resolve())
    assert draft_path.resolve().is_relative_to(work.resolve())
    assert review_path.resolve().is_relative_to(work.resolve())
    assert _snapshot(external) == before
    assert network_attempts == []


def test_no_network_clients_or_boundary_bypasses(network_attempts) -> None:
    forbidden_mods = ("requests", "httpx", "urllib.request", "http.client", "aiohttp")
    concat_vault = False
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in forbidden_mods:
            assert name not in text, f"{path} contains {name}"
        if path.parent.name == "commands":
            assert "vault" not in text, f"{path.name} contains lowercase vault"
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "lower":
                # Command/path boundary tests must not be bypassed via .lower().
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    lowered = node.value.value.lower()
                    assert "vault" not in lowered
                    assert "wiki" not in lowered or node.value.value == node.value.value.lower()
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                chunks = []
                for part in (node.left, node.right):
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        chunks.append(part.value)
                joined = "".join(chunks).lower()
                if "vault" in joined:
                    concat_vault = True
    assert concat_vault is False
    staging = (SRC / "staging.py").read_text(encoding="utf-8")
    assert "paper_id" not in staging
    assert network_attempts == []


def test_unix_socket_sentinel_unchanged(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    sock_path = external / "sentinel.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(1)
    try:
        before = _snapshot(external)
        draft = _clone_mav_draft(checkout)
        (checkout / ".work").symlink_to(external)
        code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
        payload = _stdout_payload(capsys)
        assert code == 2
        assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
        assert _snapshot(external) == before
        assert sock_path.exists()
    finally:
        server.close()
    assert network_attempts == []
