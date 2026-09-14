from __future__ import annotations

import json
import socket

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli, write_bytes
from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_experiment_store import (
    BATCH,
    RECORDED_AT,
    RECORDED_BY,
    valid_condition_input,
)
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.jcs import canonicalize


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _leaves():
    parser = build_parser()
    parent = None
    for action in parser._actions:
        if getattr(action, "choices", None) and "experiments" in action.choices:
            parent = action.choices["experiments"]
            break
    assert parent is not None
    leaves = {}
    for action in parent._actions:
        if getattr(action, "choices", None):
            leaves.update(action.choices)
    return leaves


def test_cli_help_two_leaves(capsys):
    leaves = _leaves()
    assert set(leaves) == {"record", "status"}
    record_help = leaves["record"].format_help()
    for flag in ("--input", "--vault-root", "--batch-id", "--recorded-by", "--recorded-at", "--previous-record-id"):
        assert flag in record_help
    assert "--code-batch-id" not in record_help
    status_help = leaves["status"].format_help()
    assert "--vault-root" in status_help
    assert "--paper-id" in status_help
    assert "--batch-id" not in status_help
    domain = None
    parser = build_parser()
    for action in parser._actions:
        if getattr(action, "choices", None) and "domain" in action.choices:
            domain = action.choices["domain"]
            break
    domain_leaves = {}
    for action in domain._actions:
        if getattr(action, "choices", None):
            domain_leaves.update(action.choices)
    assert set(domain_leaves) == {
        "inspect",
        "record",
        "review",
        "status",
        "compile",
        "publish-inspect",
        "relations",
        "structure",
        "claims",
        "versions",
    }
    code = main(["domain", "apply"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"


def test_cli_record_status_and_errors(world, capsys):
    payload = valid_condition_input(world)
    write_bytes(world["checkout"] / "condition.json", canonicalize(payload) + b"\n")
    vault_before = _snapshot(world["vault"])
    record_proc = run_module_cli(
        world["checkout"],
        [
            "experiments",
            "record",
            "--input",
            "condition.json",
            "--vault-root",
            str(world["vault"]),
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
    assert record_payload["command"] == "experiments.record"
    validate_document(record_payload["data"]["record"], "video-paper-wiki.experiment-condition-record.v1")
    assert _snapshot(world["vault"]) == vault_before
    status_proc = run_module_cli(
        world["checkout"],
        ["experiments", "status", "--vault-root", str(world["vault"])],
    )
    status_payload = parse_envelope(status_proc)
    assert status_proc.returncode == 0
    assert status_payload["command"] == "experiments.status"
    assert status_payload["data"]["ranking"] == "not_ranked"
    assert status_payload["data"]["canonical_official"] is False
    again = run_module_cli(
        world["checkout"],
        ["experiments", "status", "--vault-root", str(world["vault"])],
    )
    assert again.returncode == 0
    assert again.stdout == status_proc.stdout
    unknown = run_module_cli(
        world["checkout"],
        [
            "experiments",
            "status",
            "--vault-root",
            str(world["vault"]),
            "--paper-id",
            "sha256:" + "f" * 64,
        ],
    )
    unknown_payload = parse_envelope(unknown)
    assert unknown.returncode == 2
    assert unknown_payload["error"]["code"] == "EXPERIMENT_STATUS_PAPER_UNKNOWN"
    missing = run_module_cli(
        world["checkout"],
        ["experiments", "status", "--vault-root", "/nonexistent"],
    )
    missing_payload = parse_envelope(missing)
    domain_missing = run_module_cli(
        world["checkout"],
        ["domain", "status", "--vault-root", "/nonexistent"],
    )
    domain_payload = parse_envelope(domain_missing)
    assert missing.returncode == 2
    assert missing_payload["error"]["code"] == domain_payload["error"]["code"]
    assert missing_payload["error"]["code"] == "WORK_PATH_UNSAFE"
    usage = main(["experiments", "status"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert usage == 2
    assert envelope["error"]["code"] == "USAGE"


def test_cli_forbidden_leaves_and_no_network(world, monkeypatch, capsys):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    for leaf in ("apply", "compile", "publish-inspect", "matrix", "compare"):
        code = main(["experiments", leaf, "--help"])
        out = capsys.readouterr().out
        envelope = json.loads(out.strip().splitlines()[-1])
        assert code == 2
        assert envelope["error"]["code"] == "USAGE"


def test_cli_malformed_source_association_record(world):
    payload = valid_condition_input(world)
    payload["source_association"] = "sva-not-a-dict"
    write_bytes(world["checkout"] / "bad-assoc.json", canonicalize(payload) + b"\n")
    proc = run_module_cli(
        world["checkout"],
        [
            "experiments",
            "record",
            "--input",
            "bad-assoc.json",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            BATCH,
            "--recorded-by",
            RECORDED_BY,
            "--recorded-at",
            RECORDED_AT,
        ],
    )
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert "Traceback" not in proc.stdout
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    envelope = json.loads(lines[0])
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "EXPERIMENT_RECORD_INVALID"
