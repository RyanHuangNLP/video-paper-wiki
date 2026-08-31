"""Malformed control JSON must fail before staging and preserve the CLI envelope."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import (
    code_evidence_request,
    complete_ingest_plan,
    make_approval_ref,
    paper_source_request,
    pdf_bytes,
    plant_blob,
    work_plan,
    write_json,
)
from video_paper_wiki.cli import main
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import JSON_MAX_DEPTH


def _payload(capsys) -> dict:
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert "Traceback" not in captured.err
    return json.loads(captured.out)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _request(family: str, digest: str) -> dict:
    if family == "ingest":
        return paper_source_request(local_sha256=digest)
    return code_evidence_request()


@pytest.mark.parametrize("family", ["ingest", "code-map"])
def test_plan_and_prepare_accept_json_whitespace(
    checkout, family, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = checkout / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = pdf_bytes() if family == "ingest" else b"local code evidence"
    digest = plant_blob(blob_root, data)
    request = _request(family, digest)
    request_path = checkout / "request.json"
    request_path.write_bytes(b" \n\t" + canonicalize(request) + b"\r\n ")
    assert main([family, "plan", "--request", str(request_path)]) == 0
    result = _payload(capsys)
    plan = result["data"]["plan"]
    plan_path = Path(result["data"]["plan_path"])
    ref_path = checkout / "ref.json"
    # Fixture-only binding; the production CLI never issues an approval ref.
    ref = make_approval_ref(plan, input_sha256=digest)
    ref_path.write_bytes(b"\t\r\n " + canonicalize(ref) + b"\n\t")
    plan_path.write_bytes(b"\n\t " + canonicalize(plan) + b"\r\n")
    assert main([family, "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 0
    result = _payload(capsys)
    assert Path(result["data"]["staged_path"]).read_bytes() == data
    assert result["data"]["approval_ref_bound"] is True
    assert network_attempts == []


@pytest.mark.parametrize("family", ["ingest", "code-map"])
@pytest.mark.parametrize("target", ["request", "plan", "approval-ref"])
@pytest.mark.parametrize("malformation", ["deep-json", "deep-field", "non-json-whitespace", "surrogate"])
def test_invalid_json_returns_one_error_without_writes(
    checkout, family, target, malformation, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = checkout / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, pdf_bytes() if family == "ingest" else b"code")
    request = _request(family, digest)
    plan = complete_ingest_plan(request)
    request_path = write_json(checkout / "request.json", request)
    plan_path = write_json(work_plan(checkout, plan["batch_id"]), plan)
    ref_path = write_json(checkout / "ref.json", make_approval_ref(plan, input_sha256=digest))
    target_path = {"request": request_path, "plan": plan_path, "approval-ref": ref_path}[target]
    if malformation == "deep-json":
        raw = b"[" * 10_000 + b"0" + b"]" * 10_000
    elif malformation == "deep-field":
        raw = target_path.read_bytes()[:-1] + b',"extra":' + b"[" * JSON_MAX_DEPTH + b"0" + b"]" * JSON_MAX_DEPTH + b"}"
    elif malformation == "non-json-whitespace":
        raw = target_path.read_bytes() + "\u00a0".encode("utf-8")
    else:
        raw = b'{"schema":"\\ud800"}'
    target_path.write_bytes(raw)
    before = _snapshot(checkout)
    if target == "request":
        argv = [family, "plan", "--request", str(request_path)]
    else:
        argv = [family, "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]
    assert main(argv) == 2
    result = _payload(capsys)
    expected_code = {"request": "PLAN_REQUEST_INVALID", "plan": "SCHEMA_INVALID", "approval-ref": "APPROVAL_REF_INVALID"}[target]
    assert result["ok"] is False
    assert result["error"]["code"] == expected_code
    assert _snapshot(checkout) == before
    assert network_attempts == []
