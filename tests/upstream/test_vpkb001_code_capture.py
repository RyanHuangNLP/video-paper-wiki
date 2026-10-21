from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import code_evidence_request, complete_ingest_plan, make_approval_ref, make_checkout, plant_blob, write_json
from video_paper_wiki.cli import main
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staged_code_capture import validate_staged_code_capture_authority
from video_paper_wiki.staging import stage_bytes


def _run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True)


def _prepared_code(tmp_path, monkeypatch, capsys, batch="code-race"):
    checkout = tmp_path / "work"; checkout.mkdir(); make_checkout(checkout); monkeypatch.chdir(checkout)
    source = b"def model():\n    return 1\n"; blob_root = tmp_path / "blobs"
    digest = plant_blob(blob_root, source); monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    plan = complete_ingest_plan(code_evidence_request(batch_id=batch))
    plan_path = stage_bytes(batch_id=batch, relative=("plan", "ingest-plan.v1.json"), data=canonicalize(plan)).path
    ref_path = write_json(tmp_path / "approval.json", make_approval_ref(plan, input_sha256=digest))
    assert main(["code-map", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path), "--source-path", "src/model.py"]) == 0
    prepared = Path(json.loads(capsys.readouterr().out)["data"]["request_path"])
    vault = tmp_path / "vault"; vault.mkdir()
    return checkout, prepared, vault


def test_real_code_create_apply_then_reuse(tmp_path, monkeypatch, capsys):
    root = Path(__file__).resolve().parents[2]
    upstream = root / "vendor/claude-obsidian"
    cli = [sys.executable, "-I", "-B", "-X", "utf8", str(upstream / "scripts/claude-obsidian.py")]
    checkout = tmp_path / "work"; checkout.mkdir(); make_checkout(checkout)
    vault = tmp_path / "vault"
    init = json.loads(_run([*cli, "init", str(vault), "--operation-id", "code-init", "--generated-at", "2026-09-02T00:00:00Z"]).stdout)
    _run([*cli, "init", str(vault), "--operation-id", "code-init", "--generated-at", "2026-09-02T00:00:00Z", "--approved-plan-sha256", init["approved_plan_sha256"], "--apply"])
    monkeypatch.chdir(checkout)
    source = b"def model():\n    return 1\n"
    blob_root = tmp_path / "blobs"; digest = plant_blob(blob_root, source); monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    plan = complete_ingest_plan(code_evidence_request(batch_id="code-public"))
    plan_path = stage_bytes(batch_id="code-public", relative=("plan", "ingest-plan.v1.json"), data=canonicalize(plan)).path
    ref_path = write_json(tmp_path / "approval.json", make_approval_ref(plan, input_sha256=digest))
    assert main(["code-map", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path), "--source-path", "src/model.py"]) == 0
    prepared = json.loads(capsys.readouterr().out)["data"]["request_path"]
    args = ["code-map", "inspect", "--prepared", prepared, "--operation-id", "code-capture", "--upstream-root", str(upstream), "--vault-root", str(vault)]
    assert main(args) == 0
    authority = json.loads(capsys.readouterr().out)["data"]
    assert authority["disposition"] == "create" and authority["manifest"]["state"] == "inspected"
    crossed = copy.deepcopy(authority); crossed["transaction_staging"]["operation_type"] = "ingest"
    with pytest.raises(ContractError): validate_staged_code_capture_authority(crossed)
    unrelated = copy.deepcopy(authority)
    unrelated["upstream_authority"] = json.loads((root / "tests/fixtures/contracts/valid/video-paper-wiki.upstream-authority.v1.json").read_text())
    with pytest.raises(ContractError): validate_staged_code_capture_authority(unrelated)
    bundle = checkout / ".work/code-public/transaction-inspect/bundle.json"
    _run([*cli, "transaction", "apply", str(bundle), "--vault", str(vault), "--approved-plan-sha256", authority["upstream_authority"]["transaction"]["inspection"]["approval_sha256"]])
    assert main(args) == 0
    reused = json.loads(capsys.readouterr().out)["data"]
    assert reused["disposition"] == "reuse" and reused["transaction_staging"] is None and reused["upstream_authority"] is None


def test_code_inspect_refuses_symlinked_fixed_request(tmp_path, monkeypatch, capsys):
    checkout = tmp_path / "work"; checkout.mkdir(); make_checkout(checkout); monkeypatch.chdir(checkout)
    target = tmp_path / "outside.json"; target.write_text("{}")
    prepared = checkout / ".work/code-link/prepared/staged-code-capture-request.v1.json"
    prepared.parent.mkdir(parents=True); prepared.symlink_to(target)
    vault = tmp_path / "vault"; vault.mkdir()
    assert main(["code-map", "inspect", "--prepared", str(prepared), "--operation-id", "op", "--upstream-root", str(tmp_path / "upstream"), "--vault-root", str(vault)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "WORK_PATH_UNSAFE"


def test_code_inspect_refuses_renamed_fixed_request(tmp_path, monkeypatch, capsys):
    _checkout, prepared, vault = _prepared_code(tmp_path, monkeypatch, capsys, "code-rename")
    prepared.rename(prepared.with_suffix(".moved"))
    assert main(["code-map", "inspect", "--prepared", str(prepared), "--operation-id", "op", "--upstream-root", str(tmp_path / "upstream"), "--vault-root", str(vault)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "WORK_PATH_UNSAFE"


def test_code_inspect_input_replacement_overrides_child_error(tmp_path, monkeypatch, capsys):
    _checkout, prepared, vault = _prepared_code(tmp_path, monkeypatch, capsys, "code-replace")
    from video_paper_wiki import staged_code_capture
    def replace_then_fail(*_args, **_kwargs):
        replacement = prepared.parent / "replacement"
        replacement.write_bytes(prepared.read_bytes())
        replacement.chmod(prepared.stat().st_mode & 0o777)
        replacement.replace(prepared)
        raise ContractError("UPSTREAM_CONTRACT_MISMATCH", "fixture child failed")
    monkeypatch.setattr(staged_code_capture, "inspect_pinned_transaction", replace_then_fail)
    assert main(["code-map", "inspect", "--prepared", str(prepared), "--operation-id", "op", "--upstream-root", str(tmp_path / "upstream"), "--vault-root", str(vault)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "WORK_PATH_UNSAFE"


def test_code_inspect_request_validation_rechecks_named_edge(tmp_path, monkeypatch, capsys):
    _checkout, prepared, vault = _prepared_code(tmp_path, monkeypatch, capsys, "code-parse-race")
    from video_paper_wiki import staged_code_capture
    original = staged_code_capture.validate_staged_code_capture_request
    def replace_then_reject(value):
        replacement=prepared.parent/"replacement.json";replacement.write_bytes(prepared.read_bytes());replacement.chmod(prepared.stat().st_mode & 0o777);replacement.replace(prepared)
        original(value)
        raise ContractError("SCHEMA_INVALID","fixture validation failure")
    monkeypatch.setattr(staged_code_capture,"validate_staged_code_capture_request",replace_then_reject)
    assert main(["code-map","inspect","--prepared",str(prepared),"--operation-id","op","--upstream-root",str(tmp_path/"upstream"),"--vault-root",str(vault)])==2
    assert json.loads(capsys.readouterr().out)["error"]["code"]=="WORK_PATH_UNSAFE"
