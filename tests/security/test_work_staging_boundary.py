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
from video_paper_wiki.resources import _package_text, _repo_file
from video_paper_wiki.staging import (
    CODE_WORK_PATH_ESCAPE,
    CODE_WORK_PATH_UNSAFE,
    StagingError,
    _assert_inside_work,
)

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


def test_resolved_path_outside_work_is_exactly_escape(
    tmp_path, monkeypatch, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    work = checkout / ".work"
    work.mkdir()
    target = work / "b1" / ".." / ".." / "secret.md"
    with pytest.raises(StagingError) as exc:
        _assert_inside_work(target, work)
    assert exc.value.code == CODE_WORK_PATH_ESCAPE
    assert exc.value.code != CODE_WORK_PATH_UNSAFE
    assert not (external / "paper.md").exists()
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_intermediate_dir_swap_after_mkdir_is_unsafe(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    real_mkdir = os.mkdir

    def racing_mkdir(name, mode=0o777, **kwargs):
        result = real_mkdir(name, mode, **kwargs)
        review = checkout / ".work" / "b1" / "review"
        if name == "review" and review.is_dir() and not review.is_symlink():
            stolen = tmp_path / "stolen-review"
            review.rename(stolen)
            review.symlink_to(external)
        return result

    monkeypatch.setattr(os, "mkdir", racing_mkdir)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert not (external / "paper.md").exists()
    assert _snapshot(external) == before
    assert network_attempts == []


def test_intermediate_dir_swap_during_link_does_not_escape(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    review_dir = checkout / ".work" / "b1" / "review"
    review_dir.mkdir(parents=True)
    draft = _clone_mav_draft(checkout)
    real_link = os.link

    def racing_link(src, dst, *args, **kwargs):
        if review_dir.exists() and not review_dir.is_symlink():
            stolen = tmp_path / "stolen-review"
            review_dir.rename(stolen)
            review_dir.symlink_to(external)
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert not (external / "paper.md").exists()
    assert not (tmp_path / "stolen-review" / "paper.md").exists()
    assert _snapshot(external) == before
    assert network_attempts == []


@pytest.mark.parametrize("slot", ["batch", "intermediate"])
@pytest.mark.parametrize("kind", ["fifo", "socket"])
def test_batch_or_intermediate_fifo_or_socket_is_unsafe_json(
    slot, kind, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    if slot == "batch":
        (checkout / ".work").mkdir()
        target = checkout / ".work" / "b1"
    else:
        (checkout / ".work" / "b1").mkdir(parents=True)
        target = checkout / ".work" / "b1" / "review"
    server = None
    if kind == "fifo":
        os.mkfifo(target)
    else:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(target))
        server.listen(1)
    try:
        draft = _clone_mav_draft(checkout)
        code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
        captured = capsys.readouterr()
        assert "Traceback" not in captured.out
        assert "Traceback" not in captured.err
        lines = [line for line in captured.out.splitlines() if line.strip()]
        assert len(lines) == 1, captured.out
        payload = json.loads(lines[0])
        Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
        assert code == 2
        assert payload["ok"] is False
        assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
        assert _snapshot(external) == before
        assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
        assert network_attempts == []
    finally:
        if server is not None:
            server.close()


def test_batch_file_slot_is_unsafe_json_envelope(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    work = checkout / ".work"
    work.mkdir()
    (work / "b1").write_bytes(b"not-a-dir")
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "NotADirectoryError" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert network_attempts == []


def test_intermediate_file_slot_is_unsafe_json_envelope(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    parent = checkout / ".work" / "b1"
    parent.mkdir(parents=True)
    (parent / "review").write_bytes(b"not-a-dir")
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "NotADirectoryError" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert network_attempts == []


def test_project_not_table_is_workspace_invalid_json(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text('project = "video-paper-wiki"\n', encoding="utf-8")
    monkeypatch.chdir(root)
    code = main(["doctor"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "AttributeError" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORKSPACE_ROOT_INVALID"
    assert network_attempts == []


def test_corrupt_engine_mvp_json_rejected_via_cli(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    draft = _clone_mav_draft(checkout)
    bad = tmp_path / "bad-engine-mvp.json"
    bad.write_bytes(b'{"papers": []}\n' + bytes([0xFF]))

    def fake_package(*parts: str):
        if parts and parts[-1] == "engine-mvp.json":
            return None
        return _package_text(*parts)

    def fake_repo(relative: Path):
        if Path(relative).name == "engine-mvp.json":
            return bad
        return _repo_file(relative)

    monkeypatch.setattr("video_paper_wiki.resources._package_text", fake_package)
    monkeypatch.setattr("video_paper_wiki.resources._repo_file", fake_repo)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ENCODING"
    work = checkout / ".work"
    assert not work.exists() or list(work.rglob("*")) == []
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
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
