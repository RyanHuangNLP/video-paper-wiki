from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import video_paper_wiki.upstream_adapter as adapter
from video_paper_wiki.contracts import ContractError

from tests.upstream._manual_pdf_capture_fixture import (
    PAYLOAD, SOURCE_PATH, UPSTREAM, make_vault, snapshot_tree,
)


def code(exc: pytest.ExceptionInfo[ContractError]) -> str:
    return exc.value.code


def test_phase_one_invalid_argument_has_no_filesystem_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_directory_argument", lambda *_a, **_k: pytest.fail("filesystem access"))
    with pytest.raises(ContractError) as caught:
        adapter.inspect_pinned_manual_pdf_capture(
            source_path="inbox/paper.PDF", operation_id="x", generated_at="bad",
            upstream_root="/missing", vault_root="/missing-two",
        )
    assert code(caught) == "ADAPTER_PATH_INVALID"


def test_phase_one_refusal_observes_zero_network_attempts(network_attempts: list) -> None:
    with pytest.raises(ContractError):
        adapter.inspect_pinned_manual_pdf_capture(
            source_path="inbox/not-lower.PDF", operation_id="x",
            generated_at="2026-09-01T04:00:00Z", upstream_root="/missing",
            vault_root="/also-missing",
        )
    assert network_attempts == []


@pytest.mark.parametrize("layout", ["missing-wiki", "symlink-inbox", "config"])
def test_phase_two_layout_failure_precedes_profile(
    tmp_path: Path, layout: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = make_vault(tmp_path)
    if layout == "missing-wiki":
        (vault / "wiki").rmdir()
    elif layout == "symlink-inbox":
        (vault / SOURCE_PATH).unlink()
        (vault / "inbox").rmdir()
        (vault / "inbox").symlink_to(vault / "wiki")
    else:
        config = vault / ".vault-meta/capture/config.json"
        config.parent.mkdir(parents=True)
        config.write_text("{}")
    monkeypatch.setattr(adapter, "_capture_profile", lambda: pytest.fail("profile read"))
    with pytest.raises(ContractError) as caught:
        adapter.inspect_pinned_manual_pdf_capture(
            source_path=SOURCE_PATH, operation_id="capture-1",
            generated_at="2026-09-01T04:00:00Z", upstream_root=UPSTREAM, vault_root=vault,
        )
    assert code(caught) == "UPSTREAM_VAULT_INVALID"


@pytest.mark.parametrize("kind", ["magic", "symlink", "fifo"])
def test_source_snapshot_refuses_non_regular_or_non_pdf(tmp_path: Path, kind: str) -> None:
    vault = make_vault(tmp_path)
    source = vault / SOURCE_PATH
    source.unlink()
    if kind == "magic":
        source.write_bytes(b"not-pdf")
    elif kind == "symlink":
        source.symlink_to(vault / "wiki")
    else:
        os.mkfifo(source)
    with pytest.raises(ContractError) as caught:
        adapter._capture_snapshot(vault, SOURCE_PATH)
    assert code(caught) == "CAPTURE_SNAPSHOT_INVALID"


def test_source_exact_byte_boundaries(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    source = vault / SOURCE_PATH
    source.write_bytes(b"%PDF-")
    assert len(adapter._capture_snapshot(vault, SOURCE_PATH).payload) == 5
    source.write_bytes(b"%PDF-" + b"x" * (adapter.MAX_CONTENT_BYTES - 5))
    assert len(adapter._capture_snapshot(vault, SOURCE_PATH).payload) == adapter.MAX_CONTENT_BYTES
    source.write_bytes(b"%PDF-" + b"x" * (adapter.MAX_CONTENT_BYTES - 4))
    with pytest.raises(ContractError) as over:
        adapter._capture_snapshot(vault, SOURCE_PATH)
    assert code(over) == "UPSTREAM_LIMIT_EXCEEDED"
    source.write_bytes(b"%PDF")
    with pytest.raises(ContractError) as under:
        adapter._capture_snapshot(vault, SOURCE_PATH)
    assert code(under) == "CAPTURE_SNAPSHOT_INVALID"


@pytest.mark.parametrize("kind", ["wrong", "multiple", "symlink", "fifo", "malformed"])
def test_matching_sibling_refusals(tmp_path: Path, kind: str) -> None:
    vault = make_vault(tmp_path)
    digest = adapter._sha(PAYLOAD)
    captured = vault / ".raw/captured"
    captured.mkdir()
    first = captured / f"{digest}.pdf"
    if kind == "wrong":
        first.write_bytes(b"wrong")
    elif kind == "multiple":
        first.write_bytes(PAYLOAD)
        (captured / f"{digest}.bin").write_bytes(PAYLOAD)
    elif kind == "symlink":
        first.symlink_to(vault / SOURCE_PATH)
    elif kind == "fifo":
        os.mkfifo(first)
    else:
        (captured / f"{digest}.-bad").write_bytes(PAYLOAD)
    with pytest.raises(ContractError) as caught:
        adapter._capture_snapshot(vault, SOURCE_PATH)
    assert code(caught) == "CAPTURE_SNAPSHOT_INVALID"


@pytest.mark.parametrize("count,accepted", [(4096, True), (4097, False)])
def test_captured_entry_limit_is_exact(tmp_path: Path, count: int, accepted: bool) -> None:
    vault = make_vault(tmp_path)
    captured = vault / ".raw/captured"
    captured.mkdir()
    for number in range(count):
        (captured / f"irrelevant-{number:04d}").touch()
    if accepted:
        assert adapter._capture_snapshot(vault, SOURCE_PATH).captured_entry_count == count
    else:
        with pytest.raises(ContractError) as caught:
            adapter._capture_snapshot(vault, SOURCE_PATH)
        assert code(caught) == "UPSTREAM_LIMIT_EXCEEDED"


def test_child_receives_only_private_scratch_environment(tmp_path: Path) -> None:
    root = tmp_path / "allocation"
    execution = root / "execution"
    scratch = root / "scratch"
    execution.mkdir(parents=True, mode=0o700)
    scratch.mkdir(mode=0o700)
    allocation = adapter._Allocation(root, execution, scratch)
    program = "import json,os,pathlib;print(json.dumps({'env':dict(os.environ),'cwd':str(pathlib.Path.cwd())}))"
    result = adapter._run_bounded([os.sys.executable, "-I", "-B", "-X", "utf8", "-c", program],
                                  allocation, cwd=scratch)
    value = json.loads(result.stdout)
    assert value["cwd"] == str(scratch)
    assert {key: value["env"][key] for key in ("HOME", "TEMP", "TMP", "TMPDIR")} == {
        key: str(scratch) for key in ("HOME", "TEMP", "TMP", "TMPDIR")
    }
    assert not ({"PYTHONPATH", "AWS_SECRET_ACCESS_KEY", "HTTP_PROXY"} & value["env"].keys())


def test_capture_profile_is_independent_and_snapshot_has_no_ignored_files() -> None:
    _raw, profile = adapter._capture_profile()
    sources = adapter._authenticate(UPSTREAM, profile)
    assert len(sources) == 21
    assert not any("__pycache__" in path or path.endswith(".pyc") for path in sources)


@pytest.mark.parametrize("mutation", ["source", "config", "captured", "scratch-mode"])
def test_post_child_races_override_child_failure(
    tmp_path: Path, mutation: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = make_vault(tmp_path)
    allocation_roots: list[Path] = []
    real_make = adapter._make_allocation

    def remember(sources, roots):
        allocation = real_make(sources, roots)
        allocation_roots.append(allocation.root)
        return allocation

    def mutate(_argv, allocation, *, cwd=None):
        if mutation == "source":
            (vault / SOURCE_PATH).write_bytes(PAYLOAD + b"changed")
        elif mutation == "config":
            path = vault / ".vault-meta/capture/config.json"
            path.parent.mkdir(parents=True)
            path.write_text("{}")
        elif mutation == "captured":
            path = vault / ".raw/captured"
            path.mkdir()
            (path / "new-entry").touch()
        else:
            allocation.scratch.chmod(0o755)
        return adapter._ProcessResult(3, b"", b"failed")

    monkeypatch.setattr(adapter, "_make_allocation", remember)
    monkeypatch.setattr(adapter, "_run_bounded", mutate)
    with pytest.raises(ContractError) as caught:
        adapter.inspect_pinned_manual_pdf_capture(
            source_path=SOURCE_PATH, operation_id="capture-1",
            generated_at="2026-09-01T04:00:00Z", upstream_root=UPSTREAM, vault_root=vault,
        )
    assert code(caught) == "UPSTREAM_CONTRACT_MISMATCH"
    assert allocation_roots and all(not path.exists() for path in allocation_roots)


@pytest.mark.parametrize("failure_code", ["UPSTREAM_EXECUTION_FAILED", "UPSTREAM_LIMIT_EXCEEDED"])
def test_public_timeout_and_overflow_still_run_postcheck(
    tmp_path: Path, failure_code: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = make_vault(tmp_path)
    before = snapshot_tree(vault)
    postchecks: list[bool] = []
    real_postcheck = adapter._capture_postcheck
    real_run = adapter._run_bounded

    def postcheck(*args, **kwargs):
        postchecks.append(True)
        return real_postcheck(*args, **kwargs)

    def fail_child(argv, allocation, *, cwd=None):
        attribute = "TIMEOUT_SECONDS" if failure_code == "UPSTREAM_EXECUTION_FAILED" else "MAX_OUTPUT_BYTES"
        previous = getattr(adapter, attribute)
        setattr(adapter, attribute, 0.000001 if attribute == "TIMEOUT_SECONDS" else 64)
        try:
            return real_run(argv, allocation, cwd=cwd)
        finally:
            setattr(adapter, attribute, previous)

    monkeypatch.setattr(adapter, "_capture_postcheck", postcheck)
    monkeypatch.setattr(adapter, "_run_bounded", fail_child)
    with pytest.raises(ContractError) as caught:
        adapter.inspect_pinned_manual_pdf_capture(
            source_path=SOURCE_PATH, operation_id="capture-1",
            generated_at="2026-09-01T04:00:00Z", upstream_root=UPSTREAM, vault_root=vault,
        )
    assert code(caught) == failure_code
    assert postchecks == [True]
    assert snapshot_tree(vault) == before


@pytest.mark.parametrize("returncode,upstream_code,expected", [
    (75, "CONCURRENT_MODIFICATION", "UPSTREAM_CONFLICT"),
    (2, "INVALID_ARGUMENT", "UPSTREAM_INSPECT_REFUSED"),
])
def test_public_well_formed_refusals_postcheck_and_fixed_details(
    tmp_path: Path, returncode: int, upstream_code: str, expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = make_vault(tmp_path)
    before = snapshot_tree(vault)
    before = snapshot_tree(vault)
    postchecks: list[bool] = []
    real_postcheck = adapter._capture_postcheck

    def postcheck(*args, **kwargs):
        postchecks.append(True)
        return real_postcheck(*args, **kwargs)

    monkeypatch.setattr(adapter, "_capture_postcheck", postcheck)
    monkeypatch.setattr(
        adapter, "_run_bounded",
        lambda _argv, _allocation, *, cwd=None: adapter._ProcessResult(
            returncode, b"", f"ERR {upstream_code}: fixed refusal\n".encode(),
        ),
    )
    with pytest.raises(ContractError) as caught:
        adapter.inspect_pinned_manual_pdf_capture(
            source_path=SOURCE_PATH, operation_id="capture-1",
            generated_at="2026-09-01T04:00:00Z", upstream_root=UPSTREAM, vault_root=vault,
        )
    assert code(caught) == expected
    assert caught.value.exit_code == returncode
    assert caught.value.details == {"upstream_code": upstream_code, "upstream_exit_code": returncode}
    assert postchecks == [True]
    assert snapshot_tree(vault) == before


def test_public_cleanup_failure_overrides_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = make_vault(tmp_path)
    before = snapshot_tree(vault)
    real_cleanup = adapter._cleanup

    def fail_after_cleanup(allocation):
        real_cleanup(allocation)
        raise ContractError("UPSTREAM_CONTRACT_MISMATCH", "forced cleanup failure")

    monkeypatch.setattr(adapter, "_cleanup", fail_after_cleanup)
    with pytest.raises(ContractError) as caught:
        adapter.inspect_pinned_manual_pdf_capture(
            source_path=SOURCE_PATH, operation_id="capture-1",
            generated_at="2026-09-01T04:00:00Z", upstream_root=UPSTREAM, vault_root=vault,
        )
    assert code(caught) == "UPSTREAM_CONTRACT_MISMATCH"
    assert snapshot_tree(vault) == before


@pytest.mark.parametrize("case", [
    "duplicate", "float", "nonfinite", "huge-int", "trailing", "extra",
    "stderr", "unknown-result", "invalid-utf8",
])
def test_real_child_public_success_transport_is_strict_and_postchecked(
    tmp_path: Path, case: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = make_vault(tmp_path)
    before = snapshot_tree(vault)
    real_run = adapter._run_bounded
    real_postcheck = adapter._capture_postcheck
    postchecks: list[bool] = []

    def alter_after_child(argv, allocation, *, cwd=None):
        result = real_run(argv, allocation, cwd=cwd)
        raw = result.stdout
        stderr = result.stderr
        if case == "duplicate":
            raw = b'{"duplicate":1,"duplicate":2,' + raw.lstrip()[1:]
        elif case == "float":
            raw = b'{"number":1.0,' + raw.lstrip()[1:]
        elif case == "nonfinite":
            raw = b'{"number":NaN,' + raw.lstrip()[1:]
        elif case == "huge-int":
            raw = b'{"number":' + b"9" * 1025 + b',' + raw.lstrip()[1:]
        elif case == "trailing":
            raw += b"trailing"
        elif case in {"extra", "unknown-result"}:
            value = json.loads(raw)
            if case == "extra":
                value["extra"] = True
            else:
                value["status"] = "complete"
            raw = json.dumps(value).encode()
        elif case == "stderr":
            stderr = b"unexpected stderr"
        else:
            raw = b"\xff"
        return adapter._ProcessResult(0, raw, stderr)

    def record_postcheck(*args, **kwargs):
        postchecks.append(True)
        return real_postcheck(*args, **kwargs)

    monkeypatch.setattr(adapter, "_run_bounded", alter_after_child)
    monkeypatch.setattr(adapter, "_capture_postcheck", record_postcheck)
    with pytest.raises(ContractError) as caught:
        adapter.inspect_pinned_manual_pdf_capture(
            source_path=SOURCE_PATH, operation_id="capture-1",
            generated_at="2026-09-01T04:00:00Z", upstream_root=UPSTREAM, vault_root=vault,
        )
    assert code(caught) == "UPSTREAM_CONTRACT_MISMATCH"
    assert postchecks == [True]
    assert snapshot_tree(vault) == before
