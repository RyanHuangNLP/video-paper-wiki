from __future__ import annotations

import json
import os
import py_compile
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.upstream.test_vpkb001_transaction_inspect import (
    UPSTREAM,
    capture,
    ingest,
    seal,
    stage,
)
from video_paper_wiki import upstream_adapter as adapter
from video_paper_wiki.contracts import ContractError


def refusal(code: str, function, *args, **kwargs) -> ContractError:
    with pytest.raises(ContractError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code
    return caught.value


def setup_capture(tmp_path: Path):
    proposal, supplied, raw = capture()
    work, bundle = stage(tmp_path, proposal, supplied, raw)
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    return proposal, supplied, work, bundle, vault


def clone_upstream(tmp_path: Path) -> Path:
    checkout = tmp_path / "pinned-upstream"
    git = shutil.which("git", path=os.defpath)
    assert git is not None
    git_env = {
        "PATH": os.defpath, "HOME": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
    }
    subprocess.run([git, "clone", "--quiet", "--no-hardlinks", "--no-checkout",
                    str(UPSTREAM), str(checkout)], env=git_env, check=True)
    subprocess.run([git, "-C", str(checkout), "checkout", "--quiet", "--detach",
                    adapter.UPSTREAM_COMMIT], env=git_env, check=True)
    return checkout


def test_hostile_parent_environment_is_replaced_and_ignored_pyc_is_not_copied(tmp_path: Path, monkeypatch) -> None:
    checkout = clone_upstream(tmp_path)
    pycache = checkout / "claude_obsidian/__pycache__"
    pycache.mkdir()
    py_compile.compile(str(checkout / "claude_obsidian/__init__.py"), doraise=True)
    assert any(pycache.glob("*.pyc"))
    hostile = {
        "HOME": str(tmp_path / "vault"), "TEMP": str(tmp_path / "vault"),
        "TMP": str(tmp_path / "vault"), "TMPDIR": str(tmp_path / "vault"),
        "PYTHONHOME": "hostile", "PYTHONPATH": "hostile", "OBSIDIAN_VAULT": "hostile",
        "HTTPS_PROXY": "http://credential.invalid", "AWS_SECRET_ACCESS_KEY": "secret",
    }
    for key, value in hostile.items():
        monkeypatch.setenv(key, value)
    observed = []
    real = subprocess.Popen

    def popen(argv, *args, **kwargs):
        if "cwd" not in kwargs:
            return real(argv, *args, **kwargs)
        environment = kwargs["env"]
        cwd = Path(kwargs["cwd"])
        observed.append((set(environment), set(environment.values()), cwd))
        assert list(environment) == ["HOME", "TEMP", "TMP", "TMPDIR"]
        assert len(set(environment.values())) == 1
        scratch = Path(environment["TMPDIR"])
        assert scratch.stat().st_mode & 0o777 == 0o700
        assert scratch.parent == cwd.parent and scratch != cwd
        assert not list(cwd.rglob("*.pyc")) and not list(cwd.rglob("__pycache__"))
        assert {path.relative_to(cwd).as_posix() for path in cwd.rglob("*") if path.is_file()} == {
            item[0] for item in adapter._profile_entries(adapter._profile()[1])
        }
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(adapter.subprocess, "Popen", popen)
    source_id = adapter.verify_pinned_source_id(
        ".raw/captured/" + "a" * 64 + ".pdf", "a" * 64, upstream_root=checkout,
    )
    assert source_id == "src-42baa0cddcfa30cdd5af" and len(observed) == 1


def test_checkout_local_fsmonitor_is_never_executed(tmp_path: Path) -> None:
    checkout = clone_upstream(tmp_path)
    marker = tmp_path / "fsmonitor-executed"
    hook = tmp_path / "hostile-fsmonitor"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n", encoding="utf-8")
    hook.chmod(0o700)
    git = shutil.which("git", path=os.defpath)
    assert git is not None
    subprocess.run([git, "-C", str(checkout), "config", "core.fsmonitor", str(hook)],
                   env={"PATH": os.defpath, "HOME": os.devnull}, check=True)
    adapter._authenticate(checkout, adapter._profile()[1])
    assert not marker.exists()


@pytest.mark.parametrize("target", ["bundle", "content", "fifo"])
def test_symlink_and_special_transport_refused_without_vault_change(tmp_path: Path, target: str) -> None:
    proposal, supplied, work, bundle, vault = setup_capture(tmp_path)
    external = tmp_path / "external"
    external.write_bytes(bundle.read_bytes() if target == "bundle" else next(iter(supplied.values())))
    if target == "bundle":
        bundle.unlink()
        bundle.symlink_to(external)
    else:
        content = bundle.parent / "content" / proposal["writes"][0]["sha256"]
        content.unlink()
        if target == "content":
            content.symlink_to(external)
        else:
            os.mkfifo(content)
    before = sorted(path.relative_to(vault).as_posix() for path in vault.rglob("*"))
    refusal("UPSTREAM_TRANSPORT_MISMATCH", adapter.inspect_pinned_transaction, proposal,
            upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)
    assert sorted(path.relative_to(vault).as_posix() for path in vault.rglob("*")) == before


def test_transport_race_is_detected_after_real_child(tmp_path: Path, monkeypatch) -> None:
    proposal, _supplied, work, bundle, vault = setup_capture(tmp_path)
    real = adapter._run_bounded

    def race(argv, allocation):
        result = real(argv, allocation)
        bundle.write_bytes(bundle.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(adapter, "_run_bounded", race)
    refusal("UPSTREAM_CONTRACT_MISMATCH", adapter.inspect_pinned_transaction, proposal,
            upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)


def test_parent_directory_replacement_is_detected_after_real_child(tmp_path: Path, monkeypatch) -> None:
    proposal, _supplied, work, bundle, vault = setup_capture(tmp_path)
    real = adapter._run_bounded

    def race(argv, allocation):
        result = real(argv, allocation)
        batch = bundle.parents[1]
        held_batch = tmp_path / "held-batch"
        held_stage = tmp_path / "held-stage"
        batch.rename(held_batch)
        (held_batch / "transaction-inspect").rename(held_stage)
        batch.mkdir()
        held_stage.rename(batch / "transaction-inspect")
        return result

    monkeypatch.setattr(adapter, "_run_bounded", race)
    refusal("UPSTREAM_CONTRACT_MISMATCH", adapter.inspect_pinned_transaction, proposal,
            upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)


@pytest.mark.parametrize("target", ["bundle", "content"])
def test_staging_byte_limits_fail_before_child(tmp_path: Path, monkeypatch, target: str) -> None:
    proposal, _supplied, work, bundle, vault = setup_capture(tmp_path)
    called = False

    def child(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("child started")

    monkeypatch.setattr(adapter, "_run_bounded", child)
    monkeypatch.setattr(adapter, "MAX_BUNDLE_BYTES" if target == "bundle" else "MAX_CONTENT_BYTES", 1)
    refusal("UPSTREAM_LIMIT_EXCEEDED", adapter.inspect_pinned_transaction, proposal,
            upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)
    assert not called


def test_post_child_oversize_transport_is_contract_mismatch(tmp_path: Path, monkeypatch) -> None:
    proposal, _supplied, work, bundle, vault = setup_capture(tmp_path)
    real = adapter._run_bounded

    def race(argv, allocation):
        result = real(argv, allocation)
        monkeypatch.setattr(adapter, "MAX_BUNDLE_BYTES", len(bundle.read_bytes()) - 1)
        return result

    monkeypatch.setattr(adapter, "_run_bounded", race)
    refusal("UPSTREAM_CONTRACT_MISMATCH", adapter.inspect_pinned_transaction, proposal,
            upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)


def test_vault_sentinel_symlink_is_refused(tmp_path: Path) -> None:
    proposal, _supplied, work, bundle, vault = setup_capture(tmp_path)
    (vault / ".obsidian").rmdir()
    (vault / ".obsidian").symlink_to(tmp_path)
    refusal("UPSTREAM_VAULT_INVALID", adapter.inspect_pinned_transaction, proposal,
            upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_profile_source_symlink_and_special_file_refuse_without_blocking(tmp_path: Path, kind: str) -> None:
    target = tmp_path / "source.py"
    if kind == "symlink":
        external = tmp_path / "external.py"
        external.write_bytes(b"x")
        target.symlink_to(external)
    else:
        os.mkfifo(target)
    root_fd = adapter._open_dir(tmp_path, code="UPSTREAM_PIN_MISMATCH")
    try:
        refusal("UPSTREAM_PIN_MISMATCH", adapter._read_source,
                root_fd, "source.py", 1, "2d711642b726b04401627ca9fbac32f5da7e5c8530fb1903cc4db02258717921")
    finally:
        os.close(root_fd)


def test_timeout_and_output_limit_are_bounded(tmp_path: Path, monkeypatch) -> None:
    allocation = adapter._make_allocation({"x.py": b"pass\n"}, (tmp_path,))
    try:
        monkeypatch.setattr(adapter, "TIMEOUT_SECONDS", 0.01)
        refusal("UPSTREAM_EXECUTION_FAILED", adapter._run_bounded,
                [sys.executable, "-I", "-c", "import time; time.sleep(1)"], allocation)
        monkeypatch.setattr(adapter, "TIMEOUT_SECONDS", 30)
        monkeypatch.setattr(adapter, "MAX_OUTPUT_BYTES", 64)
        refusal("UPSTREAM_LIMIT_EXCEEDED", adapter._run_bounded,
                [sys.executable, "-I", "-c", "import sys; sys.stdout.buffer.write(b'x'*65)"], allocation)
    finally:
        adapter._cleanup(allocation)


@pytest.mark.parametrize("result", [
    adapter._ProcessResult(0, b"not-json", b""),
    adapter._ProcessResult(0, b"{}", b"warning"),
    adapter._ProcessResult(2, b"", b"malformed"),
    adapter._ProcessResult(-9, b"", b""),
])
def test_malformed_and_unknown_child_results_fail_closed(tmp_path: Path, monkeypatch, result) -> None:
    proposal, _supplied, work, bundle, vault = setup_capture(tmp_path)
    monkeypatch.setattr(adapter, "_run_bounded", lambda *_args: result)
    expected = "UPSTREAM_CONTRACT_MISMATCH" if result.returncode == 0 else "UPSTREAM_EXECUTION_FAILED"
    refusal(expected, adapter.inspect_pinned_transaction, proposal,
            upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)


def test_cleanup_failure_is_not_hidden(tmp_path: Path, monkeypatch) -> None:
    stored = ".raw/captured/" + "a" * 64 + ".pdf"
    real = adapter._cleanup

    def fail(allocation):
        real(allocation)
        raise ContractError("UPSTREAM_CONTRACT_MISMATCH", "cleanup failed")

    monkeypatch.setattr(adapter, "_cleanup", fail)
    refusal("UPSTREAM_CONTRACT_MISMATCH", adapter.verify_pinned_source_id,
            stored, "a" * 64, upstream_root=UPSTREAM)


@pytest.mark.parametrize("target", ["root_mode", "scratch_file"])
def test_private_allocation_root_and_scratch_shapes_are_reverified(tmp_path: Path, target: str) -> None:
    sources = {"x.py": b"pass\n"}
    allocation = adapter._make_allocation(sources, (tmp_path,))
    try:
        if target == "root_mode":
            allocation.root.chmod(0o755)
        else:
            allocation.scratch.rmdir()
            allocation.scratch.write_bytes(b"")
            allocation.scratch.chmod(0o700)
        refusal("UPSTREAM_CONTRACT_MISMATCH", adapter._verify_allocation, allocation, sources)
    finally:
        if allocation.root.exists():
            allocation.root.chmod(0o700)
            adapter._cleanup(allocation)


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_partial_allocation_failure_is_cleaned_or_cleanup_failure_overrides(
    tmp_path: Path, monkeypatch, cleanup_fails: bool,
) -> None:
    roots: list[Path] = []
    real_mkdtemp = adapter.tempfile.mkdtemp
    real_rmtree = adapter.shutil.rmtree

    def mkdtemp(*args, **kwargs):
        result = real_mkdtemp(*args, **kwargs)
        roots.append(Path(result))
        return result

    def invalid(*_args, **_kwargs):
        raise ContractError("UPSTREAM_PIN_MISMATCH", "forced verification failure")

    def failed_cleanup(*_args, **_kwargs):
        raise OSError("forced cleanup failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(adapter.tempfile, "mkdtemp", mkdtemp)
        scoped.setattr(adapter, "_verify_allocation", invalid)
        if cleanup_fails:
            scoped.setattr(adapter.shutil, "rmtree", failed_cleanup)
        expected = "UPSTREAM_CONTRACT_MISMATCH" if cleanup_fails else "UPSTREAM_PIN_MISMATCH"
        refusal(expected, adapter._make_allocation, {"x.py": b"pass\n"}, (tmp_path,))
    assert len(roots) == 1
    if cleanup_fails:
        assert roots[0].exists()
        real_rmtree(roots[0])
    else:
        assert not roots[0].exists()


def test_refused_child_still_runs_all_postchecks(tmp_path: Path, monkeypatch) -> None:
    proposal, _supplied, work, bundle, vault = setup_capture(tmp_path)
    checked = False
    real = adapter._postcheck

    def postcheck(*args, **kwargs):
        nonlocal checked
        checked = True
        return real(*args, **kwargs)

    monkeypatch.setattr(adapter, "_postcheck", postcheck)
    monkeypatch.setattr(adapter, "_run_bounded", lambda *_args: adapter._ProcessResult(
        2, b"", b"ERR CONTENT_HASH_MISMATCH: hidden path\n"))
    caught = refusal("UPSTREAM_INSPECT_REFUSED", adapter.inspect_pinned_transaction, proposal,
                     upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)
    assert checked
    assert caught.details == {"upstream_code": "CONTENT_HASH_MISMATCH", "upstream_exit_code": 2}


@pytest.mark.parametrize("field", [
    "operation_id", "changed_paths", "hashes", "modes",
    "input_bundle_sha256", "expanded_bundle_sha256", "approval_sha256",
])
def test_schema_closed_success_plan_correlation_errors_are_adapter_mismatch(
    tmp_path: Path, monkeypatch, field: str,
) -> None:
    proposal, _supplied, work, bundle, vault = setup_capture(tmp_path)
    real = adapter._run_bounded

    def wrong(argv, allocation):
        result = real(argv, allocation)
        plan = json.loads(result.stdout)
        if field == "operation_id":
            plan[field] = "different-operation"
        elif field == "changed_paths":
            plan[field] = ["wiki/meta/records/different.json"]
        elif field == "hashes":
            plan[field] = {plan["changed_paths"][0]: "0" * 64}
        elif field == "modes":
            plan[field] = {plan["changed_paths"][0]: 0o644}
        elif field == "approval_sha256":
            plan[field] = "invalid"
        else:
            plan[field] = "0" * 64
        return adapter._ProcessResult(0, json.dumps(plan, sort_keys=True).encode() + b"\n", b"")

    monkeypatch.setattr(adapter, "_run_bounded", wrong)
    caught = refusal("UPSTREAM_CONTRACT_MISMATCH", adapter.inspect_pinned_transaction, proposal,
                     upstream_root=UPSTREAM, work_root=work, vault_root=vault, bundle_path=bundle)
    assert caught.details == {}


def test_original_size_is_preserved_but_not_independently_attested(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    proposal, supplied, _raw = ingest(vault)
    head = proposal["writes"][-1]
    head["original_size_bytes"] += 7
    proposal, raw = seal(proposal, supplied)
    work, bundle = stage(tmp_path, proposal, supplied, raw)
    authority = adapter.inspect_pinned_transaction(proposal, upstream_root=UPSTREAM,
                                                   work_root=work, vault_root=vault,
                                                   bundle_path=bundle)
    assert authority["transaction"]["writes"][-1]["original_size_bytes"] == head["original_size_bytes"]
