from __future__ import annotations

import json

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli, write_bytes
from tests.unit.test_domain_proposal import (
    _snapshot,
    inspect_file,
    make_world,
    valid_proposal,
    write_proposal,
)
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def test_cli_source_c2_proposal_report(world):
    proposal = valid_proposal(world)
    write_proposal(world["checkout"], proposal)
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    proc = run_module_cli(
        world["checkout"],
        [
            "domain",
            "inspect",
            "--input",
            "proposal.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
        ],
    )
    payload = parse_envelope(proc)
    assert proc.returncode == 0
    assert payload["ok"] is True
    assert payload["command"] == "domain.inspect"
    data = payload["data"]
    assert data["status"] == "proposal_only"
    assert data["publication"] == "unpublished"
    assert data["review"] == "pending_semantic_review"
    assert data["successor_only"] is True
    assert data["source_association_verified"] is False
    assert data["canonical_official"] is False
    assert data["current_supported_typed_fact"] is False
    assert data["next_action"] == "semantic_review_required"
    assert canonicalize(payload) == proc.stdout.encode("utf-8").strip()
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    again = run_module_cli(
        world["checkout"],
        [
            "domain",
            "inspect",
            "--input",
            "proposal.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
        ],
    )
    assert again.returncode == 0
    assert again.stdout == proc.stdout
    direct = inspect_file(world, proposal, name="direct.json")
    assert canonicalize(direct) == canonicalize(data)


def test_cli_error_envelope_exit_codes(world):
    proposal = valid_proposal(world)
    proposal["source_association"]["sha256"] = "0" * 64
    write_proposal(world["checkout"], proposal, "bad.json")
    proc = run_module_cli(
        world["checkout"],
        [
            "domain",
            "inspect",
            "--input",
            "bad.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
        ],
    )
    payload = parse_envelope(proc)
    assert proc.returncode == 2
    assert payload["ok"] is False
    assert payload["command"] == "domain.inspect"
    assert payload["error"]["code"] == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    assert payload["error"]["details"]["instance_pointer"]
    assert payload["error"]["details"]["next_action"]
    assert "data" not in payload
    missing = run_module_cli(
        world["checkout"],
        ["domain", "inspect", "--vault-root", str(world["vault"]), "--code-batch-id", "d1"],
    )
    missing_payload = parse_envelope(missing)
    assert missing.returncode == 2
    assert missing_payload["ok"] is False
    assert missing_payload["error"]["code"] == "USAGE"
    empty = run_module_cli(
        world["checkout"],
        [
            "domain",
            "inspect",
            "--input",
            "proposal-missing.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
        ],
    )
    empty_payload = parse_envelope(empty)
    assert empty.returncode == 2
    assert empty_payload["error"]["code"] in {"DOMAIN_PROPOSAL_INPUT_MISSING", "WORK_PATH_UNSAFE"}
    assert empty_payload["error"]["details"]["next_action"]


def test_cli_help_and_parser_flags(capsys):
    parser = build_parser()
    help_text = parser.format_help()
    assert "domain" in help_text
    parent = None
    for action in parser._actions:
        if getattr(action, "choices", None) and "domain" in action.choices:
            parent = action.choices["domain"]
            break
    assert parent is not None
    inspect_help = None
    for action in parent._actions:
        if getattr(action, "choices", None) and "inspect" in action.choices:
            inspect_help = action.choices["inspect"].format_help()
    assert inspect_help is not None
    assert "--input" in inspect_help
    assert "--vault-root" in inspect_help
    assert "--code-batch-id" in inspect_help
    assert "read-only" in inspect_help.lower() or "Read-only" in inspect_help
    code = main(["domain", "inspect"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"


def test_cli_does_not_rewrite_claims_or_vault(world):
    proposal = valid_proposal(world)
    write_proposal(world["checkout"], proposal)
    before_ledger = (world["vault"] / CLAIM_LEDGER).read_bytes()
    before_ids = json.loads(before_ledger)["claims"].keys()
    proc = run_module_cli(
        world["checkout"],
        [
            "domain",
            "inspect",
            "--input",
            "proposal.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
        ],
    )
    assert proc.returncode == 0
    after_ledger = (world["vault"] / CLAIM_LEDGER).read_bytes()
    assert after_ledger == before_ledger
    assert json.loads(after_ledger)["claims"].keys() == before_ids
    payload = parse_envelope(proc)
    assert payload["data"]["unannotated_claims"][0]["claim_id"] == world["extra"]["claim_id"]
