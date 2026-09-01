from __future__ import annotations

import os
import shutil
import json
from pathlib import Path

import pytest

import video_paper_wiki.upstream_adapter as adapter
from video_paper_wiki.upstream_adapter import inspect_pinned_manual_pdf_capture

from tests.upstream._manual_pdf_capture_fixture import (
    GENERATED_AT,
    OPERATION_ID,
    PAYLOAD,
    SOURCE_PATH,
    UPSTREAM,
    make_vault,
    sha256,
    snapshot_tree,
)


@pytest.mark.parametrize("reuse_suffix", [None, ".pdf", ".bin"])
def test_real_pinned_manual_capture_is_read_only(
    tmp_path: Path, reuse_suffix: str | None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/hostile/caller/path")
    monkeypatch.setenv("HTTP_PROXY", "http://hostile.invalid")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-enter-child")
    reuse = reuse_suffix is not None
    vault = make_vault(tmp_path, reuse=reuse)
    if reuse_suffix == ".bin":
        captured = vault / ".raw/captured"
        (captured / f"{sha256(PAYLOAD)}.pdf").rename(captured / f"{sha256(PAYLOAD)}.bin")
    before = snapshot_tree(vault)
    seen: list[tuple[list[str], Path]] = []
    real_run = adapter._run_bounded

    def record(argv: list[str], allocation: adapter._Allocation, *, cwd: Path | None = None):
        seen.append((argv, cwd or allocation.execution))
        return real_run(argv, allocation, cwd=cwd)

    monkeypatch.setattr(adapter, "_run_bounded", record)
    authority = inspect_pinned_manual_pdf_capture(
        source_path=SOURCE_PATH,
        operation_id=OPERATION_ID,
        generated_at=GENERATED_AT,
        upstream_root=UPSTREAM,
        vault_root=vault,
    )
    assert snapshot_tree(vault) == before
    assert authority["request"]["source_path"] == SOURCE_PATH
    assert authority["inspection"]["payload"] == {
        "sha256": sha256(PAYLOAD), "size_bytes": len(PAYLOAD),
    }
    expected_status = "noop" if reuse else "dry-run"
    assert authority["observation"]["status"] == expected_status
    assert authority["inspection"]["would_change"] is (not reuse)
    assert len(authority["inspection"]["siblings"]) == int(reuse)
    if reuse_suffix is not None:
        assert authority["inspection"]["stored_path"].endswith(reuse_suffix)
    assert len(seen) == 1
    argv, cwd = seen[0]
    assert argv[1:5] == ["-I", "-B", "-X", "utf8"]
    assert argv[6:] == [
        "capture", "apply", "--vault", str(vault), "--inbox", "inbox",
        "--max-items", "1", "--max-total-bytes", "67108864",
        "--max-file-bytes", "67108864", "--operation-id", OPERATION_ID,
        "--generated-at", GENERATED_AT, SOURCE_PATH,
    ]
    assert "--apply" not in argv and "--approved-plan-sha256" not in argv
    assert cwd.name == "scratch"
    serialized = json.dumps(authority, sort_keys=True)
    assert str(vault) not in serialized
    assert "approval_hint" not in serialized
    assert PAYLOAD.decode() not in serialized


def _replace_directory_identity(path: Path) -> None:
    old = path.with_name(path.name + "-old")
    path.rename(old)
    shutil.copytree(old, path, copy_function=shutil.copy2)
    shutil.rmtree(old)


@pytest.mark.parametrize("component", ["root", "execution", "scratch"])
def test_real_child_private_directory_replacement_is_refused(
    tmp_path: Path, component: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = make_vault(tmp_path)
    before = snapshot_tree(vault)
    real_run = adapter._run_bounded

    def replace_after_child(argv, allocation, *, cwd=None):
        result = real_run(argv, allocation, cwd=cwd)
        _replace_directory_identity(getattr(allocation, component))
        return result

    monkeypatch.setattr(adapter, "_run_bounded", replace_after_child)
    with pytest.raises(adapter.ContractError) as caught:
        inspect_pinned_manual_pdf_capture(
            source_path=SOURCE_PATH, operation_id=OPERATION_ID, generated_at=GENERATED_AT,
            upstream_root=UPSTREAM, vault_root=vault,
        )
    assert caught.value.code == "UPSTREAM_CONTRACT_MISMATCH"
    assert snapshot_tree(vault) == before


def test_real_child_equal_sibling_inode_replacement_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = make_vault(tmp_path, reuse=True)
    before = snapshot_tree(vault)
    sibling = vault / ".raw/captured" / f"{sha256(PAYLOAD)}.pdf"
    captured = sibling.parent
    real_run = adapter._run_bounded

    def replace_after_child(argv, allocation, *, cwd=None):
        result = real_run(argv, allocation, cwd=cwd)
        directory_info = captured.stat()
        old_inode = sibling.stat().st_ino
        mode = sibling.stat().st_mode & 0o7777
        replacement = captured / "replacement"
        replacement.write_bytes(sibling.read_bytes())
        replacement.chmod(mode)
        os.replace(replacement, sibling)
        os.utime(captured, ns=(directory_info.st_atime_ns, directory_info.st_mtime_ns))
        assert sibling.stat().st_ino != old_inode
        return result

    monkeypatch.setattr(adapter, "_run_bounded", replace_after_child)
    with pytest.raises(adapter.ContractError) as caught:
        inspect_pinned_manual_pdf_capture(
            source_path=SOURCE_PATH, operation_id=OPERATION_ID, generated_at=GENERATED_AT,
            upstream_root=UPSTREAM, vault_root=vault,
        )
    assert caught.value.code == "UPSTREAM_CONTRACT_MISMATCH"
    assert snapshot_tree(vault) == before
