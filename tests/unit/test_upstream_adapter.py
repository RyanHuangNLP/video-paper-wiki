from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError
from video_paper_wiki import upstream_adapter as adapter

ROOT = Path(__file__).resolve().parents[2]
VALID = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.upstream-authority.v1.json"


def proposal() -> dict:
    document = json.loads(VALID.read_text(encoding="utf-8"))["transaction"]
    document["phase"] = "proposal"
    document["inspection"] = None
    return document


def raises(expected_code: str, function, *args, **kwargs) -> ContractError:
    with pytest.raises(ContractError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == expected_code
    return caught.value


def test_proposal_is_validated_before_path_or_process_access(monkeypatch) -> None:
    touched = False

    def touch(*_args, **_kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("I/O occurred")

    monkeypatch.setattr(adapter, "_directory_argument", touch)
    bad = proposal()
    bad["phase"] = "inspected"
    raises("TRANSACTION_UPSTREAM_MISMATCH", adapter.inspect_pinned_transaction, bad,
           upstream_root="/missing", work_root="/missing", vault_root="/missing",
           bundle_path="/missing")
    assert not touched


@pytest.mark.parametrize("field,value", [
    ("stored_path", 1),
    ("stored_path", ".raw/captured/" + "a" * 64 + ".pdf\n"),
    ("source_identity", "A" * 64),
    ("expected_source_id", "src-" + "a" * 20 + "\n"),
])
def test_source_id_arguments_refuse_before_pin(monkeypatch, field: str, value: object) -> None:
    called = False

    def pin(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("pin touched")

    monkeypatch.setattr(adapter, "_directory_argument", pin)
    values = {
        "stored_path": ".raw/captured/" + "a" * 64 + ".pdf",
        "source_identity": "a" * 64,
        "expected_source_id": None,
    }
    values[field] = value
    raises("ADAPTER_PATH_INVALID", adapter.verify_pinned_source_id,
           values["stored_path"], values["source_identity"],
           upstream_root="/missing", expected_source_id=values["expected_source_id"])
    assert not called


@pytest.mark.parametrize("raw", [
    b'{"x":1,"x":2}', b'{"x":1.0}', b'{"x":NaN}', b'{"x":1}x', b'\xff',
])
def test_strict_json_refuses_duplicate_float_constant_trailing_and_encoding(raw: bytes) -> None:
    raises("UPSTREAM_TRANSPORT_MISMATCH", adapter._strict_json, raw,
           code="UPSTREAM_TRANSPORT_MISMATCH", label="fixture")


def test_upstream_failure_mapping_has_closed_details() -> None:
    conflict = raises("UPSTREAM_CONFLICT", adapter._failure,
                      adapter._ProcessResult(75, b"", b"ERR BUSY: private message\n"))
    assert conflict.exit_code == 75
    assert conflict.details == {"upstream_code": "BUSY", "upstream_exit_code": 75}
    refused = raises("UPSTREAM_INSPECT_REFUSED", adapter._failure,
                     adapter._ProcessResult(2, b"", b"ERR CONTENT_HASH_MISMATCH: secret\n"))
    assert refused.details == {"upstream_code": "CONTENT_HASH_MISMATCH", "upstream_exit_code": 2}
    raises("UPSTREAM_EXECUTION_FAILED", adapter._failure,
           adapter._ProcessResult(2, b"leak", b"ERR BAD: secret\n"))
    raises("UPSTREAM_EXECUTION_FAILED", adapter._failure,
           adapter._ProcessResult(9, b"", b"ERR BAD: secret\n"))


def test_success_output_requires_exact_closed_plan() -> None:
    document = json.loads(VALID.read_text(encoding="utf-8"))
    plan = copy.deepcopy(document["transaction"]["inspection"])
    raw = (json.dumps(plan, sort_keys=True) + "\n").encode()
    assert adapter._success_plan(adapter._ProcessResult(0, raw, b"")) == plan
    plan["extra"] = True
    raises("UPSTREAM_CONTRACT_MISMATCH", adapter._success_plan,
           adapter._ProcessResult(0, json.dumps(plan).encode(), b""))
    raises("UPSTREAM_CONTRACT_MISMATCH", adapter._success_plan,
           adapter._ProcessResult(0, raw, b"warning"))


def test_private_allocation_modes_exact_tree_and_cleanup(tmp_path: Path) -> None:
    sources = {"pkg/__init__.py": b"x", "scripts/tool.py": b"y"}
    allocation = adapter._make_allocation(sources, (tmp_path,))
    try:
        adapter._verify_allocation(allocation, sources)
        assert allocation.root.stat().st_mode & 0o777 == 0o700
        assert allocation.scratch.stat().st_mode & 0o777 == 0o700
        assert all(path.stat().st_mode & 0o777 == 0o400 for path in allocation.execution.rglob("*.py"))
        (allocation.execution / "extra").write_text("bad")
        raises("UPSTREAM_CONTRACT_MISMATCH", adapter._verify_allocation, allocation, sources)
        (allocation.execution / "extra").unlink()
    finally:
        adapter._cleanup(allocation)
    assert not allocation.root.exists()


def test_wrong_commit_and_dirty_checkout_fail_at_pin(monkeypatch) -> None:
    profile = adapter._profile()[1]
    monkeypatch.setattr(adapter, "_git", lambda *_args: b"0" * 40 + b"\n")
    raises("UPSTREAM_PIN_MISMATCH", adapter._authenticate, Path("/not-opened"), profile)

    def dirty(_root, *arguments):
        if arguments[0] == "rev-parse" and arguments[1] == "HEAD^{commit}":
            return (adapter.UPSTREAM_COMMIT + "\n").encode()
        if arguments[0] == "rev-parse":
            return (adapter.UPSTREAM_TREE + "\n").encode()
        return b"?? hostile.py\n"

    monkeypatch.setattr(adapter, "_git", dirty)
    raises("UPSTREAM_PIN_MISMATCH", adapter._authenticate, Path("/not-opened"), profile)


def test_missing_upstream_fails_closed_without_download() -> None:
    raises("ADAPTER_PATH_INVALID", adapter.verify_pinned_source_id,
           ".raw/captured/" + "a" * 64 + ".pdf", "a" * 64,
           upstream_root="/private/tmp/definitely-missing-vpkb-upstream")


@pytest.mark.parametrize("case", ["wrong_work_name", "wrong_layout", "invalid_batch"])
def test_staging_layout_is_phase_two_before_profile(tmp_path: Path, monkeypatch, case: str) -> None:
    upstream = tmp_path / "upstream"
    vault = tmp_path / "vault"
    upstream.mkdir()
    vault.mkdir()
    if case == "wrong_work_name":
        work = tmp_path / "work"
        bundle = work / "adapter-batch/transaction-inspect/bundle.json"
    elif case == "wrong_layout":
        work = tmp_path / ".work"
        bundle = work / "adapter-batch/wrong/bundle.json"
    else:
        work = tmp_path / ".work"
        bundle = work / "bad batch/transaction-inspect/bundle.json"
    work.mkdir()
    touched = False

    def profile():
        nonlocal touched
        touched = True
        raise AssertionError("profile touched")

    monkeypatch.setattr(adapter, "_profile", profile)
    raises("ADAPTER_PATH_INVALID", adapter.inspect_pinned_transaction, proposal(),
           upstream_root=upstream, work_root=work, vault_root=vault, bundle_path=bundle)
    assert not touched


@pytest.mark.parametrize("label", ["upstream_root", "work_root", "vault_root", "bundle_path"])
@pytest.mark.parametrize("hostile", [
    "/private/tmp/hidden\0path",
    "/private/tmp/hidden\ud800path",
    "/private/tmp/hidden\udc80path",
    "/private/tmp/hidden\ud83d\ude00path",
])
def test_encoding_invalid_paths_are_sanitized(tmp_path: Path, label: str, hostile: str) -> None:
    upstream = tmp_path / "upstream"
    work = tmp_path / ".work"
    vault = tmp_path / "vault"
    for path in (upstream, work, vault):
        path.mkdir()
    arguments = {
        "upstream_root": upstream,
        "work_root": work,
        "vault_root": vault,
        "bundle_path": work / "adapter-batch/transaction-inspect/bundle.json",
    }
    arguments[label] = hostile
    caught = raises("ADAPTER_PATH_INVALID", adapter.inspect_pinned_transaction,
                    proposal(), **arguments)
    assert caught.details == {}
    assert "hidden" not in str(caught)


def test_source_id_encoding_invalid_upstream_path_is_sanitized() -> None:
    caught = raises(
        "ADAPTER_PATH_INVALID", adapter.verify_pinned_source_id,
        ".raw/captured/" + "a" * 64 + ".pdf", "a" * 64,
        upstream_root="/private/tmp/hidden\ud800path",
    )
    assert caught.details == {}
    assert "hidden" not in str(caught)
