from __future__ import annotations

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_article_revision import _papers, _question
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.article_store import MAX_TITLE
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


def _fill(argv, mapping):
    filled = [mapping[token] if token in mapping else token for token in argv]
    assert all(not str(token).startswith("<") for token in filled)
    return filled


def test_cli_title_cite_mark_and_experiment_primary(tmp_path, monkeypatch):
    world = make_world(tmp_path, monkeypatch)
    _three_chain(world)
    vault = str(world["vault"])
    papers = _papers(world)
    p1 = world["association"]["paper_id"]
    p2 = next(item for item in papers if item != p1)
    long_q = _question(world) + " " + ("😀" * (301 - len(_question(world)) - 1))
    assert len(long_q) == 301
    selected = run_module_cli(
        world["checkout"],
        [
            "flow",
            "select",
            "--vault-root",
            vault,
            "--batch-id",
            "cli-title",
            "--paper-id",
            p1,
            "--question",
            long_q,
        ],
    )
    assert selected.returncode == 0, selected.stdout + selected.stderr
    prepared = run_module_cli(
        world["checkout"],
        ["flow", "prepare", "--vault-root", vault, "--batch-id", "cli-title", "--kind", "article"],
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    env = parse_envelope(prepared)
    import_action = next(item for item in env["data"]["next_actions"] if item["id"] == "survey-import-article")
    imported = run_module_cli(
        world["checkout"],
        _fill(import_action["argv"], {"<recorded_by>": "fixture", "<recorded_at>": "2026-09-15T00:00:00Z"}),
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr
    cite_q = long_q[:MAX_TITLE] + "[@late]"
    assert "[@" not in cite_q[:MAX_TITLE]
    refused = run_module_cli(
        world["checkout"],
        [
            "flow",
            "prepare",
            "--vault-root",
            vault,
            "--batch-id",
            "cli-title",
            "--kind",
            "article",
            "--question",
            cite_q,
        ],
    )
    assert refused.returncode == 2
    refused_env = parse_envelope(refused)
    assert refused_env["error"]["code"] == "FLOW_INVALID"
    assert refused_env["error"]["details"]["reason"] == "cite_mark_in_title"
    assert refused_env["error"]["details"]["instance_pointer"] == "/question"
    refused_argv = refused_env["error"]["details"]["argv"]
    assert refused_argv.count("--paper-id") == 1
    assert refused_argv[refused_argv.index("--paper-id") + 1] == p1
    multi = run_module_cli(
        world["checkout"],
        [
            "flow",
            "select",
            "--vault-root",
            vault,
            "--batch-id",
            "cli-exp",
            "--paper-id",
            p2,
            "--paper-id",
            p1,
        ],
    )
    assert multi.returncode == 0, multi.stdout + multi.stderr
    multi_env = parse_envelope(multi)
    action = next(
        item for item in multi_env["data"]["next_actions"] if item["id"].startswith("compare-prepare-experiment-")
    )
    assert action["argv"].count("--paper-id") == 1
    assert action["argv"][action["argv"].index("--paper-id") + 1] == p1
    executed = run_module_cli(
        world["checkout"],
        _fill(action["argv"], {"<setting_key>": "table9-row1-flow"}),
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    prepared_exp = parse_envelope(executed)["data"]
    assert prepared_exp["paper_ids"] == [p1]
    assert prepared_exp["experiment_binding"]["paper_id"] == p1
