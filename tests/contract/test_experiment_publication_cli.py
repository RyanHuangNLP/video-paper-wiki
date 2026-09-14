from __future__ import annotations

import json

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


def test_cli_help_five_leaves(capsys):
    leaves = _leaves()
    assert set(leaves) == {"record", "status", "compile", "publish-inspect", "matrix"}
    compile_help = leaves["compile"].format_help()
    assert "--vault-root" in compile_help
    assert "--batch-id" in compile_help
    assert "--input" not in compile_help
    inspect_help = leaves["publish-inspect"].format_help()
    assert "--prepared" in inspect_help
    assert "--vault-root" in inspect_help
    matrix_help = leaves["matrix"].format_help()
    assert "--vault-root" in matrix_help
    assert "--paper-id" in matrix_help
    assert "--batch-id" not in matrix_help
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
    code = main(["experiments", "apply", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(["experiments", "compare", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(["domain", "apply", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"


def test_cli_record_compile_inspect_matrix_and_errors(world, capsys):
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
    assert record_proc.returncode == 0
    compile_proc = run_module_cli(
        world["checkout"],
        ["experiments", "compile", "--vault-root", str(world["vault"]), "--batch-id", BATCH],
    )
    compile_payload = parse_envelope(compile_proc)
    assert compile_proc.returncode == 0
    assert compile_payload["command"] == "experiments.compile"
    assert compile_payload["data"]["state"] == "experiment_publication_prepared"
    assert _snapshot(world["vault"]) == vault_before
    inspect_proc = run_module_cli(
        world["checkout"],
        [
            "experiments",
            "publish-inspect",
            "--prepared",
            ".work/" + BATCH + "/experiment-publication/request.json",
            "--vault-root",
            str(world["vault"]),
        ],
    )
    inspect_payload = parse_envelope(inspect_proc)
    assert inspect_proc.returncode == 0
    assert inspect_payload["command"] == "experiments.publish-inspect"
    validate_document(inspect_payload["data"], "video-paper-wiki.experiment-publication-inspection.v1")
    inspect_again = run_module_cli(
        world["checkout"],
        [
            "experiments",
            "publish-inspect",
            "--prepared",
            ".work/" + BATCH + "/experiment-publication/request.json",
            "--vault-root",
            str(world["vault"]),
        ],
    )
    assert inspect_again.returncode == 0
    assert inspect_again.stdout == inspect_proc.stdout
    matrix_proc = run_module_cli(
        world["checkout"],
        ["experiments", "matrix", "--vault-root", str(world["vault"])],
    )
    matrix_payload = parse_envelope(matrix_proc)
    assert matrix_proc.returncode == 0
    assert matrix_payload["command"] == "experiments.matrix"
    validate_document(matrix_payload["data"], "video-paper-wiki.experiment-comparison-matrix.v1")
    assert matrix_payload["data"]["ranking"] == "not_ranked"
    matrix_again = run_module_cli(
        world["checkout"],
        ["experiments", "matrix", "--vault-root", str(world["vault"])],
    )
    assert matrix_again.returncode == 0
    assert matrix_again.stdout == matrix_proc.stdout
    unknown = run_module_cli(
        world["checkout"],
        [
            "experiments",
            "matrix",
            "--vault-root",
            str(world["vault"]),
            "--paper-id",
            "sha256:" + "f" * 64,
        ],
    )
    unknown_payload = parse_envelope(unknown)
    assert unknown.returncode == 2
    assert unknown_payload["error"]["code"] == "EXPERIMENT_MATRIX_PAPER_UNKNOWN"
    missing_matrix = run_module_cli(
        world["checkout"],
        ["experiments", "matrix", "--vault-root", "/nonexistent"],
    )
    missing_status = run_module_cli(
        world["checkout"],
        ["experiments", "status", "--vault-root", "/nonexistent"],
    )
    matrix_missing = parse_envelope(missing_matrix)
    status_missing = parse_envelope(missing_status)
    assert missing_matrix.returncode == 2
    assert matrix_missing["error"]["code"] == status_missing["error"]["code"]
    assert matrix_missing["error"]["code"] == "WORK_PATH_UNSAFE"
    compile_missing = run_module_cli(
        world["checkout"],
        ["experiments", "compile", "--vault-root", str(world["vault"]), "--batch-id", "nope"],
    )
    compile_payload_err = parse_envelope(compile_missing)
    assert compile_missing.returncode == 2
    assert compile_payload_err["error"]["code"] == "EXPERIMENT_COMPILE_INVALID"
    unsafe = run_module_cli(
        world["checkout"],
        [
            "experiments",
            "publish-inspect",
            "--prepared",
            "/etc/passwd",
            "--vault-root",
            str(world["vault"]),
        ],
    )
    unsafe_payload = parse_envelope(unsafe)
    assert unsafe.returncode == 2
    assert unsafe_payload["error"]["code"] == "WORK_PATH_UNSAFE"
    usage = main(["experiments", "compile"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert usage == 2
    assert envelope["error"]["code"] == "USAGE"
    usage = main(["experiments", "matrix"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert usage == 2
    assert envelope["error"]["code"] == "USAGE"
