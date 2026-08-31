from __future__ import annotations

import json
from pathlib import Path

from tests.support import (
    ROOT,
    code_evidence_request,
    complete_ingest_plan,
    make_approval_ref,
    make_checkout,
    paper_source_request,
    plant_blob,
    work_prepared,
    write_json,
)
from video_paper_wiki.cli import main
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staging import stage_bytes

TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"


def _stdout_json(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


def _stage_plan(request: dict) -> Path:
    plan = complete_ingest_plan(request)
    staged = stage_bytes(
        batch_id=plan["batch_id"],
        relative=("plan", "ingest-plan.v1.json"),
        data=canonicalize(plan),
    )
    return staged.path, plan


def test_prepare_success_with_local_blob(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = TINY_PDF.read_bytes()
    digest = plant_blob(blob_root, data)
    plan_path, plan = _stage_plan(paper_source_request(batch_id="t1", local_sha256=digest))
    ref_path = write_json(tmp_path / "ref.json", make_approval_ref(plan))
    code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    staged = Path(payload["data"]["staged_path"])
    assert staged == work_prepared(tmp_path, "t1", digest)
    assert staged.is_file()
    assert staged.read_bytes() == data
    assert payload["data"]["already_staged"] is False
    assert payload["data"]["approval_ref_bound"] is True
    assert "human_approved" not in payload["data"]
    assert "approval_hash_present" not in payload["data"]
    assert network_attempts == []


def test_prepare_missing_blob_exit_2_no_network(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    missing = "a" * 64
    plan_path, plan = _stage_plan(paper_source_request(batch_id="t1", local_sha256=missing))
    ref_path = write_json(tmp_path / "ref.json", make_approval_ref(plan))
    code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert network_attempts == []


def test_prepare_approval_ref_does_not_download_or_reject_existing_blob(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = TINY_PDF.read_bytes()
    digest = plant_blob(blob_root, data)
    plan_path, plan = _stage_plan(paper_source_request(batch_id="t2", local_sha256=digest))
    ref_path = write_json(tmp_path / "ref.json", make_approval_ref(plan))
    code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["data"]["approval_ref_bound"] is True
    assert "verified" not in payload["data"]
    assert Path(payload["data"]["staged_path"]).is_file()
    assert network_attempts == []


def test_prepare_approval_ref_without_blob_still_exit_2_no_network(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    plan_path, plan = _stage_plan(paper_source_request(batch_id="t3", local_sha256="c" * 64))
    ref_path = write_json(tmp_path / "ref.json", make_approval_ref(plan))
    code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert "approval_hash_present" not in payload["error"]["details"]
    assert network_attempts == []


def test_code_map_prepare_same_contract(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    plan_path, plan = _stage_plan(code_evidence_request(batch_id="cm0"))
    ref_path = write_json(tmp_path / "ref.json", make_approval_ref(plan, input_sha256="e" * 64))
    code = main(["code-map", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
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
    plan_path, plan = _stage_plan(code_evidence_request(batch_id="cm1"))
    ref_path = write_json(tmp_path / "ref.json", make_approval_ref(plan, input_sha256=digest))
    code = main(["code-map", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "code-map.prepare"
    assert payload["data"]["approval_ref_bound"] is True
    assert Path(payload["data"]["staged_path"]).is_file()
    assert Path(payload["data"]["staged_path"]) == work_prepared(tmp_path, "cm1", digest)
    assert network_attempts == []


def test_prepare_missing_plan_is_usage(
    tmp_path: Path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["ingest", "prepare", "--approval-ref", "ref.json"])
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
