from __future__ import annotations

import json
import os
import socket
import stat

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli, write_bytes
from tests.unit.test_domain_proposal import (
    _snapshot,
    make_world,
    valid_proposal,
    write_proposal,
)
from tests.unit.test_domain_store import (
    BATCH,
    LATER_AT,
    RECORDED_AT,
    RECORDED_BY,
    REVIEW_AT,
    _apply_staged,
    _decision_for,
    _record,
    _relation_review,
)
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def test_cli_record_review_status_flow(world):
    proposal = valid_proposal(world)
    write_proposal(world["checkout"], proposal)
    vault_before = _snapshot(world["vault"])
    record_proc = run_module_cli(
        world["checkout"],
        [
            "domain",
            "record",
            "--input",
            "proposal.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
            "--batch-id",
            BATCH,
            "--recorded-by",
            RECORDED_BY,
            "--recorded-at",
            RECORDED_AT,
        ],
    )
    record_payload = parse_envelope(record_proc)
    assert record_proc.returncode == 0
    assert record_payload["ok"] is True
    assert record_payload["command"] == "domain.record"
    data = record_payload["data"]
    assert data["publication"] == "unpublished"
    assert data["next_action"] == "semantic_review_required"
    assert data["record"]["report"]["canonical_official"] is False
    assert all(item["relative"].startswith("domain/") for item in data["staged"])
    staged_root = world["checkout"] / ".work" / BATCH / "domain"
    assert staged_root.is_dir()
    assert (staged_root / "heads.json").is_file()
    assert _snapshot(world["vault"]) == vault_before
    _apply_staged(world)
    decision = _decision_for(world, data, officiality="official")
    write_bytes(world["checkout"] / "decision.json", canonicalize(decision) + b"\n")
    vault_mid = _snapshot(world["vault"])
    review_proc = run_module_cli(
        world["checkout"],
        [
            "domain",
            "review",
            "--decision",
            "decision.json",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "d2r",
        ],
    )
    review_payload = parse_envelope(review_proc)
    assert review_proc.returncode == 0
    assert review_payload["command"] == "domain.review"
    assert review_payload["data"]["next_action"] == "publication_pending_later_slice"
    assert review_payload["data"]["canonical_official"] is False
    assert review_payload["data"]["current_supported_typed_fact"] is False
    assert _snapshot(world["vault"]) == vault_mid
    _apply_staged(world, "d2r")
    status_proc = run_module_cli(
        world["checkout"],
        ["domain", "status", "--vault-root", str(world["vault"])],
    )
    status_payload = parse_envelope(status_proc)
    assert status_proc.returncode == 0
    assert status_payload["command"] == "domain.status"
    status = status_payload["data"]
    assert status["publication"] == "unpublished"
    assert status["audit_coverage"] == "not_wired"
    assert status["code_freshness"] == "not_checked"
    assert status["canonical_official"] is False
    assert status["current_supported_typed_fact"] is False
    assert status["lineages"][0]["typed_fact_status"] == "reviewed_accepted"
    again = run_module_cli(
        world["checkout"],
        ["domain", "status", "--vault-root", str(world["vault"])],
    )
    assert again.returncode == 0
    assert again.stdout == status_proc.stdout
    assert canonicalize(status_payload) == status_proc.stdout.encode("utf-8").strip()


def test_cli_help_four_leaves(capsys):
    parser = build_parser()
    parent = None
    for action in parser._actions:
        if getattr(action, "choices", None) and "domain" in action.choices:
            parent = action.choices["domain"]
            break
    assert parent is not None
    leaves = {}
    for action in parent._actions:
        if getattr(action, "choices", None):
            leaves.update(action.choices)
    assert set(leaves) == {"inspect", "record", "review", "status", "compile", "publish-inspect"}
    record_help = leaves["record"].format_help()
    assert "--input" in record_help
    assert "--vault-root" in record_help
    assert "--code-batch-id" in record_help
    assert "--batch-id" in record_help
    assert "--recorded-by" in record_help
    assert "--recorded-at" in record_help
    review_help = leaves["review"].format_help()
    assert "--decision" in review_help
    assert "--batch-id" in review_help
    status_help = leaves["status"].format_help()
    assert "--vault-root" in status_help
    code = main(["domain", "record"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"


def test_cli_error_envelope_exit_codes(world):
    missing = run_module_cli(
        world["checkout"],
        ["domain", "status"],
    )
    payload = parse_envelope(missing)
    assert missing.returncode == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    write_proposal(world["checkout"], valid_proposal(world), "proposal.json")
    bad = run_module_cli(
        world["checkout"],
        [
            "domain",
            "record",
            "--input",
            "proposal.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
            "--batch-id",
            BATCH,
            "--recorded-by",
            RECORDED_BY,
            "--recorded-at",
            "not-a-timestamp",
        ],
    )
    bad_payload = parse_envelope(bad)
    assert bad.returncode == 2
    assert bad_payload["error"]["code"] == "DOMAIN_STORE_INVALID"
    assert bad_payload["error"]["details"]["next_action"]
    assert "data" not in bad_payload
    inspect_fail = run_module_cli(
        world["checkout"],
        [
            "domain",
            "record",
            "--input",
            "missing-proposal.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
            "--batch-id",
            BATCH,
            "--recorded-by",
            RECORDED_BY,
            "--recorded-at",
            RECORDED_AT,
        ],
    )
    inspect_payload = parse_envelope(inspect_fail)
    assert inspect_fail.returncode == 2
    assert inspect_payload["error"]["code"] in {"DOMAIN_PROPOSAL_INPUT_MISSING", "WORK_PATH_UNSAFE"}


def test_cli_determinism_zero_writes_and_no_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    write_proposal(world["checkout"], valid_proposal(world))
    argv = [
        "domain",
        "record",
        "--input",
        "proposal.json",
        "--vault-root",
        str(world["vault"]),
        "--code-batch-id",
        "d1",
        "--batch-id",
        BATCH,
        "--recorded-by",
        RECORDED_BY,
        "--recorded-at",
        RECORDED_AT,
    ]
    vault_before = _snapshot(world["vault"])
    ledger_before = (world["vault"] / CLAIM_LEDGER).read_bytes()
    first = run_module_cli(world["checkout"], argv)
    second = run_module_cli(world["checkout"], argv)
    assert first.returncode == 0
    assert first.stdout == second.stdout
    assert _snapshot(world["vault"]) == vault_before
    assert (world["vault"] / CLAIM_LEDGER).read_bytes() == ledger_before
    payload = parse_envelope(first)
    for item in payload["data"]["staged"]:
        path = world["checkout"] / ".work" / BATCH / item["relative"]
        assert path.read_bytes()
        st = path.lstat()
        assert not stat.S_ISLNK(st.st_mode)
        again = world["checkout"] / ".work" / BATCH / item["relative"]
        assert again.read_bytes() == path.read_bytes()
