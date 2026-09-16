from __future__ import annotations

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.cli import build_parser
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.jcs import canonicalize


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


def test_flow_help_and_usage(tmp_path, monkeypatch):
    world = make_world(tmp_path, monkeypatch)
    proc = run_module_cli(world["checkout"], ["flow", "--help"])
    assert proc.returncode == 0
    assert set(_parent_leaves("flow")) == {"prepare", "select", "status"}
    usage = run_module_cli(world["checkout"], ["flow"])
    assert usage.returncode == 2
    envelope = parse_envelope(usage)
    assert envelope["ok"] is False
    assert envelope["command"] == "flow"
    assert envelope["error"]["code"] == "USAGE"
    validate_document(envelope, expected_schema="video-paper-wiki.cli-envelope.v1")
    for leaf, flags in (
        ("status", ("--vault-root", "--batch-id", "--paper-id")),
        ("select", ("--vault-root", "--batch-id", "--paper-id", "--association-id", "--question")),
        ("prepare", ("--vault-root", "--batch-id", "--kind", "--setting-key", "--paper-id", "--question")),
    ):
        help_proc = run_module_cli(world["checkout"], ["flow", leaf, "--help"])
        assert help_proc.returncode == 0
        for flag in flags:
            assert flag in help_proc.stdout
        for forbidden in ("--text", "--upstream-root", "--recorded-at"):
            assert forbidden not in help_proc.stdout


def test_flow_refusals_and_success(tmp_path, monkeypatch):
    world = make_world(tmp_path, monkeypatch)
    work = world["checkout"] / ".work"
    before = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()} if work.exists() else {}
    missing = run_module_cli(world["checkout"], ["flow", "status", "--vault-root", "/nonexistent"])
    exp = run_module_cli(world["checkout"], ["experiments", "status", "--vault-root", "/nonexistent"])
    assert missing.returncode == 2
    assert exp.returncode == 2
    left = parse_envelope(missing)
    right = parse_envelope(exp)
    assert left["error"]["code"] == right["error"]["code"] == "WORK_PATH_UNSAFE"
    after = {path.relative_to(work): path.read_bytes() for path in work.rglob("*") if path.is_file()} if work.exists() else {}
    assert after == before
    invalid = run_module_cli(
        world["checkout"],
        ["flow", "status", "--vault-root", "/nonexistent", "--paper-id", "not-a-paper"],
    )
    assert invalid.returncode == 2
    envelope = parse_envelope(invalid)
    assert envelope["error"]["code"] == "FLOW_INVALID"
    assert envelope["error"]["details"]["instance_pointer"] == "/paper_id"
    select = run_module_cli(
        world["checkout"],
        ["flow", "select", "--vault-root", str(world["vault"]), "--batch-id", "s1"],
    )
    assert select.returncode == 2
    assert parse_envelope(select)["error"]["code"] == "USAGE"
    kind = run_module_cli(
        world["checkout"],
        [
            "flow",
            "prepare",
            "--vault-root",
            "/nonexistent",
            "--batch-id",
            "b1",
            "--kind",
            "article",
            "--setting-key",
            "x",
        ],
    )
    assert kind.returncode == 2
    kind_env = parse_envelope(kind)
    assert kind_env["error"]["code"] == "FLOW_INVALID"
    assert kind_env["error"]["details"]["instance_pointer"] == "/setting_key"
    assert kind_env["error"]["details"]["reason"] == "kind_argument"
    missing_sel = run_module_cli(
        world["checkout"],
        [
            "flow",
            "prepare",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "b1",
            "--kind",
            "experiment",
            "--setting-key",
            "table9-row1-flow",
        ],
    )
    assert missing_sel.returncode == 2
    assert parse_envelope(missing_sel)["error"]["code"] == "FLOW_SELECTION_MISSING"
    ok = run_module_cli(world["checkout"], ["flow", "status", "--vault-root", str(world["vault"])])
    assert ok.returncode == 0
    assert ok.stderr == ""
    success = parse_envelope(ok)
    assert success["ok"] is True
    assert success["command"] == "flow.status"
    validate_document(success, expected_schema="video-paper-wiki.cli-envelope.v1")
    assert canonicalize(success) == ok.stdout.encode("utf-8").removesuffix(b"\n")
    _three_chain(world)
    paper = world["association"]["paper_id"]
    selected = run_module_cli(
        world["checkout"],
        [
            "flow",
            "select",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "cli1",
            "--paper-id",
            paper,
        ],
    )
    assert selected.returncode == 0
    assert selected.stderr == ""
    sel_env = parse_envelope(selected)
    validate_document(sel_env, expected_schema="video-paper-wiki.cli-envelope.v1")
    assert canonicalize(sel_env) == selected.stdout.encode("utf-8").removesuffix(b"\n")


def test_existing_command_trees_unchanged(tmp_path, monkeypatch):
    world = make_world(tmp_path, monkeypatch)
    articles = run_module_cli(world["checkout"], ["articles", "--help"])
    graph = run_module_cli(world["checkout"], ["graph", "--help"])
    experiments = run_module_cli(world["checkout"], ["experiments", "--help"])
    domain = run_module_cli(world["checkout"], ["domain", "--help"])
    assert articles.returncode == graph.returncode == experiments.returncode == domain.returncode == 0
    assert set(_parent_leaves("articles")) == {
        "check",
        "compile",
        "export",
        "history",
        "import",
        "publish-inspect",
        "render",
        "status",
    }
    assert set(_parent_leaves("graph")) == {"project", "query"}
    assert set(_parent_leaves("experiments")) == {
        "compile",
        "matrix",
        "publish-inspect",
        "record",
        "status",
    }
    assert len(_parent_leaves("domain")) == 10
