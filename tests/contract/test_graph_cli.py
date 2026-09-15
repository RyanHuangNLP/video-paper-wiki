from __future__ import annotations

import json

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from tests.unit.test_graph_query import _empirical_text, _two_words
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.graph_projection import PROJECTION_SCHEMA
from video_paper_wiki.graph_query import QUERY_SCHEMA


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _parent_leaves(name: str) -> dict:
    parser = build_parser()
    parent = None
    for action in parser._actions:
        if getattr(action, "choices", None) and name in action.choices:
            parent = action.choices[name]
            break
    leaves = {}
    for action in parent._actions:
        if getattr(action, "choices", None):
            leaves.update(action.choices)
    return leaves


def test_cli_help_two_leaves(world):
    proc = run_module_cli(world["checkout"], ["graph", "--help"])
    assert proc.returncode == 0
    assert "project" in proc.stdout
    assert "query" in proc.stdout
    leaves = _parent_leaves("graph")
    assert set(leaves) == {"project", "query"}
    project = run_module_cli(world["checkout"], ["graph", "project", "--help"])
    assert project.returncode == 0
    assert "--vault-root" in project.stdout
    assert "--paper-id" in project.stdout
    assert "--text" not in project.stdout
    query = run_module_cli(world["checkout"], ["graph", "query", "--help"])
    assert query.returncode == 0
    for flag in ("--vault-root", "--text", "--kind", "--concept-kind", "--paper-id", "--limit", "--bm25-ranking"):
        assert flag in query.stdout
    assert "--upstream-root" not in query.stdout
    assert "--config" not in query.stdout


def test_cli_project_and_query_roundtrip(world):
    _three_chain(world)
    vault = str(world["vault"])
    first = run_module_cli(world["checkout"], ["graph", "project", "--vault-root", vault])
    assert first.returncode == 0
    payload = parse_envelope(first)
    assert payload["command"] == "graph.project"
    validate_document(payload["data"], PROJECTION_SCHEMA)
    second = run_module_cli(world["checkout"], ["graph", "project", "--vault-root", vault])
    assert first.stdout == second.stdout
    text = _two_words(_empirical_text(world))
    query = run_module_cli(
        world["checkout"],
        ["graph", "query", "--vault-root", vault, "--text", text],
    )
    assert query.returncode == 0
    qpayload = parse_envelope(query)
    assert qpayload["command"] == "graph.query"
    validate_document(qpayload["data"], QUERY_SCHEMA)
    assert qpayload["data"]["ranking"] == "not_ranked"
    again = run_module_cli(
        world["checkout"],
        ["graph", "query", "--vault-root", vault, "--text", text],
    )
    assert query.stdout == again.stdout


def test_cli_refusals_and_usage(world, capsys):
    code = main(["graph", "query", "--vault-root", "/nonexistent", "--text", "a", "--kind", "bogus"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(["graph", "query", "--vault-root", "/nonexistent", "--text", "a", "--limit", "x"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(["graph", "query", "--vault-root", "/nonexistent", "--text", "a", "--limit", "0"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "GRAPH_QUERY_LIMIT"
    missing = run_module_cli(world["checkout"], ["graph", "project", "--vault-root", "/nonexistent"])
    status = run_module_cli(world["checkout"], ["experiments", "status", "--vault-root", "/nonexistent"])
    assert missing.returncode == 2
    assert parse_envelope(missing)["error"]["code"] == parse_envelope(status)["error"]["code"]
    query_missing = run_module_cli(
        world["checkout"],
        ["graph", "query", "--vault-root", "/nonexistent", "--text", "a"],
    )
    assert query_missing.returncode == 2
    assert parse_envelope(query_missing)["error"]["code"] == parse_envelope(status)["error"]["code"]
    bm25 = run_module_cli(
        world["checkout"],
        [
            "graph",
            "query",
            "--vault-root",
            "/nonexistent",
            "--text",
            "a",
            "--bm25-ranking",
            "/etc/passwd",
        ],
    )
    assert bm25.returncode == 2
    assert parse_envelope(bm25)["error"]["code"] in {"GRAPH_QUERY_BM25_INVALID", "WORK_PATH_UNSAFE"}
    code = main(["graph", "project"])
    out = capsys.readouterr().out
    assert code == 2
    assert json.loads(out.strip().splitlines()[-1])["error"]["code"] == "USAGE"
    code = main(["graph", "query", "--vault-root", "/nonexistent"])
    out = capsys.readouterr().out
    assert code == 2
    assert json.loads(out.strip().splitlines()[-1])["error"]["code"] == "USAGE"
    for leaf in ("build", "fuse", "apply"):
        proc = run_module_cli(world["checkout"], ["graph", leaf, "--help"])
        assert proc.returncode == 2
    experiments = run_module_cli(world["checkout"], ["experiments", "--help"])
    assert experiments.returncode == 0
    for leaf in ("record", "status", "compile", "publish-inspect", "matrix"):
        assert leaf in experiments.stdout
    domain = run_module_cli(world["checkout"], ["domain", "--help"])
    assert domain.returncode == 0
    for leaf in (
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
    ):
        assert leaf in domain.stdout
    apply_help = run_module_cli(world["checkout"], ["domain", "apply", "--help"])
    assert apply_help.returncode == 2
    leaves = _parent_leaves("experiments")
    assert set(leaves) == {"record", "status", "compile", "publish-inspect", "matrix"}
    domain_leaves = _parent_leaves("domain")
    assert len(domain_leaves) == 10
