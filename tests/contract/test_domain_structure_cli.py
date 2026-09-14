from __future__ import annotations

import json

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_domain_apply import _apply
from tests.unit.test_domain_proposal import (
    _snapshot,
    make_world,
    valid_proposal,
    write_proposal,
)
from tests.unit.test_domain_store import BATCH, RECORDED_AT, RECORDED_BY
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_structure import VIEW_SCHEMA
from video_paper_wiki.jcs import canonicalize

UNKNOWN_PAPER = "sha256:" + "f" * 64


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def test_structure_help_flags(world):
    proc = run_module_cli(world["checkout"], ["domain", "structure", "--help"])
    assert proc.returncode == 0
    assert "--vault-root" in proc.stdout
    assert "--paper-id" in proc.stdout
    assert "--batch-id" not in proc.stdout


def test_structure_requires_vault_root(world, capsys):
    code = main(["domain", "structure"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "USAGE"


def test_cli_record_compile_apply_structure_and_unknown_paper(world):
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
    assert record_proc.returncode == 0
    compile_proc = run_module_cli(
        world["checkout"],
        ["domain", "compile", "--vault-root", str(world["vault"]), "--batch-id", BATCH],
    )
    assert compile_proc.returncode == 0
    assert _snapshot(world["vault"]) == vault_before
    _apply(world, BATCH)
    work_before = _snapshot(world["checkout"] / ".work")
    vault_applied = _snapshot(world["vault"])
    struct_proc = run_module_cli(
        world["checkout"],
        ["domain", "structure", "--vault-root", str(world["vault"])],
    )
    payload = parse_envelope(struct_proc)
    assert struct_proc.returncode == 0
    assert payload["ok"] is True
    assert payload["command"] == "domain.structure"
    validate_document(payload["data"], VIEW_SCHEMA)
    assert payload["data"]["write_kind"] == "read_only"
    assert payload["data"]["canonical_official"] is False
    assert payload["data"]["evidence_recheck"] == "not_performed"
    assert _snapshot(world["vault"]) == vault_applied
    assert _snapshot(world["checkout"] / ".work") == work_before
    again = run_module_cli(
        world["checkout"],
        ["domain", "structure", "--vault-root", str(world["vault"])],
    )
    assert again.returncode == 0
    assert again.stdout == struct_proc.stdout
    assert canonicalize(payload) == struct_proc.stdout.encode("utf-8").strip()
    unknown = run_module_cli(
        world["checkout"],
        [
            "domain",
            "structure",
            "--vault-root",
            str(world["vault"]),
            "--paper-id",
            UNKNOWN_PAPER,
        ],
    )
    unknown_payload = parse_envelope(unknown)
    assert unknown.returncode == 2
    assert unknown_payload["error"]["code"] == "DOMAIN_STRUCTURE_PAPER_UNKNOWN"
    assert unknown_payload["error"]["details"]["next_action"] == "check_paper_id"


def test_domain_apply_is_still_usage(world, capsys):
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
    assert "apply" not in leaves
    assert "structure" in leaves
    assert len(leaves) == 8
    code = main(["domain", "apply", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    _ = world
