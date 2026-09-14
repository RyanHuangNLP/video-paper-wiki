from __future__ import annotations

import json

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_domain_proposal import make_world
from video_paper_wiki.cli import build_parser, main


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def test_matrix_help_flags(world):
    proc = run_module_cli(world["checkout"], ["experiments", "matrix", "--help"])
    assert proc.returncode == 0
    assert "--vault-root" in proc.stdout
    assert "--paper-id" in proc.stdout
    assert "--batch-id" not in proc.stdout


def test_matrix_requires_vault_root(world, capsys):
    code = main(["experiments", "matrix"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "USAGE"


def test_matrix_missing_vault_matches_status(world):
    missing = run_module_cli(world["checkout"], ["experiments", "matrix", "--vault-root", "/nonexistent"])
    status = run_module_cli(world["checkout"], ["experiments", "status", "--vault-root", "/nonexistent"])
    missing_payload = parse_envelope(missing)
    status_payload = parse_envelope(status)
    assert missing.returncode == 2
    assert missing_payload["error"]["code"] == status_payload["error"]["code"]
    parser = build_parser()
    parent = None
    for action in parser._actions:
        if getattr(action, "choices", None) and "experiments" in action.choices:
            parent = action.choices["experiments"]
            break
    leaves = {}
    for action in parent._actions:
        if getattr(action, "choices", None):
            leaves.update(action.choices)
    assert "matrix" in leaves
