from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.upstream_adapter import (
    _CaptureSnapshot,
    _ProcessResult,
    _capture_arguments,
    _capture_success,
)


PAYLOAD = b"%PDF-unit\n"
DIGEST = "5" * 64
SOURCE = "inbox/paper.pdf"
TARGET = f".raw/captured/{DIGEST}.pdf"


def snapshot(*, reuse: bool = False) -> _CaptureSnapshot:
    siblings = ((TARGET, "regular", DIGEST, 0o600),) if reuse else ()
    return _CaptureSnapshot(PAYLOAD, DIGEST, "paper.pdf", TARGET, siblings, (), int(reuse))


def stdout(*, reuse: bool = False) -> bytes:
    item = {
        "schema": "claude-obsidian.filesystem-capture-plan.v1",
        "adapter": "filesystem", "source_identity": DIGEST, "source": SOURCE,
        "stored_path": TARGET, "would_change": not reuse,
        "skip_reason": "content-unchanged" if reuse else None, "execute": False,
        "metadata": {"name": "paper.pdf", "extension": ".pdf",
                     "size_bytes": len(PAYLOAD), "sha256": DIGEST, "kind": "pdf",
                     "media_type": "application/pdf", "detected_by": "magic"},
    }
    operation = {
        "schema": "claude-obsidian.transaction.v1", "operation_id": "capture-1",
        "operation_type": "capture", "expected_hashes": {} if reuse else {TARGET: None},
        "writes": [] if reuse else [{"path": TARGET, "mode": "create",
                                      "content_file": "/vault/inbox/paper.pdf", "sha256": DIGEST}],
        "address_requests": [], "source_manifest_updates": {},
    }
    value = {"schema": "claude-obsidian.capture-plan.v1",
             "status": "noop" if reuse else "dry-run", "items": [item], "operation": operation}
    if not reuse:
        approval = "a" * 64
        value.update({"approved_plan_sha256": approval, "generated_at": "2026-09-01T04:00:00Z",
                      "approval_hint": "review the operation, then repeat the exact pinned command with "
                                       f"--approved-plan-sha256 {approval} --apply"})
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


@pytest.mark.parametrize("reuse", [False, True])
def test_success_projection_create_and_noop(reuse: bool) -> None:
    raw = stdout(reuse=reuse)
    result = _capture_success(_ProcessResult(0, raw, b""), snapshot(reuse=reuse), SOURCE,
                              "capture-1", "2026-09-01T04:00:00Z", Path("/vault"))
    assert result["status"] == ("noop" if reuse else "dry-run")
    assert (result["operation"]["write"] is None) is reuse


@pytest.mark.parametrize("source", ["Inbox/paper.pdf", "inbox/paper.PDF", "inbox/../paper.pdf",
                                     "inbox/CON.pdf", "inbox/a b.pdf", "inbox/paper.pdf\n"])
def test_pure_argument_path_refusals(source: str) -> None:
    with pytest.raises(ContractError) as caught:
        _capture_arguments(source, "capture-1", "2026-09-01T04:00:00Z")
    assert caught.value.code == "ADAPTER_PATH_INVALID"


@pytest.mark.parametrize("operation,time", [("x\n", "2026-09-01T04:00:00Z"),
                                              ("x", "2026-02-29T04:00:00Z"),
                                              ("x", "2026-09-01T04:00:00.0Z")])
def test_operation_and_calendar_refusals(operation: str, time: str) -> None:
    with pytest.raises(ContractError) as caught:
        _capture_arguments(SOURCE, operation, time)
    assert caught.value.code == "ADAPTER_PATH_INVALID"


def test_argument_byte_and_length_boundaries() -> None:
    longest_filename = "a" * 236 + ".pdf"
    assert _capture_arguments(f"inbox/{longest_filename}", "x" * 128,
                              "2024-02-29T23:59:59Z")[0].endswith(longest_filename)
    for source, operation in (("inbox/" + "a" * 237 + ".pdf", "x"),
                              (SOURCE, "x" * 129),
                              ("inbox/" + "a/" * 510 + "p.pdf", "x")):
        with pytest.raises(ContractError) as caught:
            _capture_arguments(source, operation, "2026-09-01T04:00:00Z")
        assert caught.value.code == "ADAPTER_PATH_INVALID"


@pytest.mark.parametrize("value", [None, True, 1, Path("inbox/paper.pdf")])
def test_argument_types_are_not_coerced(value: object) -> None:
    with pytest.raises(ContractError) as caught:
        _capture_arguments(value, "capture-1", "2026-09-01T04:00:00Z")
    assert caught.value.code == "ADAPTER_PATH_INVALID"


@pytest.mark.parametrize("raw", [
    b"{}", b'{"a":1,"a":2}', b'{"a":1.0}', b'{"a":NaN}',
    b'{"a":' + b"9" * 1025 + b'}', b'{}x', b'\xff',
])
def test_malformed_success_is_contract_mismatch(raw: bytes) -> None:
    with pytest.raises(ContractError) as caught:
        _capture_success(_ProcessResult(0, raw, b""), snapshot(), SOURCE, "capture-1",
                         "2026-09-01T04:00:00Z", Path("/vault"))
    assert caught.value.code == "UPSTREAM_CONTRACT_MISMATCH"


@pytest.mark.parametrize("mutation", ["extra", "unknown-status", "stderr"])
def test_success_extra_unknown_or_stderr_is_refused(mutation: str) -> None:
    raw = stdout()
    stderr = b""
    if mutation != "stderr":
        value = json.loads(raw)
        if mutation == "extra":
            value["extra"] = True
        else:
            value["status"] = "complete"
        raw = json.dumps(value).encode()
    else:
        stderr = b"unexpected"
    with pytest.raises(ContractError) as caught:
        _capture_success(_ProcessResult(0, raw, stderr), snapshot(), SOURCE, "capture-1",
                         "2026-09-01T04:00:00Z", Path("/vault"))
    assert caught.value.code == "UPSTREAM_CONTRACT_MISMATCH"


@pytest.mark.parametrize("returncode,stderr,code", [
    (75, b"ERR CONCURRENT_MODIFICATION: changed\n", "UPSTREAM_CONFLICT"),
    (2, b"ERR INVALID_ARGUMENT: bad\n", "UPSTREAM_INSPECT_REFUSED"),
    (3, b"bad", "UPSTREAM_EXECUTION_FAILED"),
])
def test_failure_transport_mapping(returncode: int, stderr: bytes, code: str) -> None:
    with pytest.raises(ContractError) as caught:
        _capture_success(_ProcessResult(returncode, b"", stderr), snapshot(), SOURCE,
                         "capture-1", "2026-09-01T04:00:00Z", Path("/vault"))
    assert caught.value.code == code
