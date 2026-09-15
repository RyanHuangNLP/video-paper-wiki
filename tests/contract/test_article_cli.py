from __future__ import annotations

import json

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_article_revision import _outline_doc, _papers, _question, _write_json
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.jcs import canonicalize


CONTEXT_SCHEMA = "video-paper-wiki.article-context.v1"
RECORD_SCHEMA = "video-paper-wiki.article-revision-record.v1"
HEADS_SCHEMA = "video-paper-wiki.article-heads.v1"
CHECK_SCHEMA = "video-paper-wiki.article-check.v1"


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


def test_cli_help_six_leaves(world):
    proc = run_module_cli(world["checkout"], ["articles", "--help"])
    assert proc.returncode == 0
    leaves = _parent_leaves("articles")
    assert set(leaves) == {"check", "compile", "export", "history", "import", "publish-inspect", "render", "status"}
    export = run_module_cli(world["checkout"], ["articles", "export", "--help"])
    assert export.returncode == 0
    for flag in (
        "--vault-root",
        "--question",
        "--paper-id",
        "--article-id",
        "--revision-id",
        "--batch-id",
        "--section-id",
        "--instructions",
    ):
        assert flag in export.stdout
    assert "--text" not in export.stdout
    assert "--upstream-root" not in export.stdout
    imported = run_module_cli(world["checkout"], ["articles", "import", "--help"])
    assert imported.returncode == 0
    for flag in (
        "--vault-root",
        "--batch-id",
        "--context",
        "--document",
        "--recorded-by",
        "--recorded-at",
        "--previous-revision-id",
        "--target-section-id",
        "--instructions",
    ):
        assert flag in imported.stdout
    check = run_module_cli(world["checkout"], ["articles", "check", "--help"])
    assert check.returncode == 0
    for flag in ("--vault-root", "--article-id", "--revision-id", "--batch-id"):
        assert flag in check.stdout
    render = run_module_cli(world["checkout"], ["articles", "render", "--help"])
    assert render.returncode == 0
    for flag in ("--vault-root", "--batch-id", "--article-id", "--revision-id"):
        assert flag in render.stdout
    status = run_module_cli(world["checkout"], ["articles", "status", "--help"])
    assert status.returncode == 0
    assert "--vault-root" in status.stdout
    assert "--batch-id" in status.stdout
    history = run_module_cli(world["checkout"], ["articles", "history", "--help"])
    assert history.returncode == 0
    for flag in ("--vault-root", "--article-id", "--batch-id"):
        assert flag in history.stdout


def test_cli_roundtrip(world):
    _three_chain(world)
    vault = str(world["vault"])
    question = _question(world)
    papers = _papers(world)
    args = ["articles", "export", "--vault-root", vault, "--question", question]
    for paper in papers:
        args.extend(["--paper-id", paper])
    first = run_module_cli(world["checkout"], args)
    assert first.returncode == 0
    payload = parse_envelope(first)
    assert payload["command"] == "articles.export"
    validate_document(payload["data"]["context"], CONTEXT_SCHEMA)
    second = run_module_cli(world["checkout"], args)
    assert first.stdout == second.stdout
    ctx = world["checkout"] / "ctx.json"
    ctx.write_bytes(first.stdout.encode("utf-8"))
    doc = world["checkout"] / "doc.json"
    _write_json(doc, _outline_doc(payload["data"]["context"]))
    imported = run_module_cli(
        world["checkout"],
        [
            "articles",
            "import",
            "--vault-root",
            vault,
            "--batch-id",
            "b1",
            "--context",
            str(ctx),
            "--document",
            str(doc),
            "--recorded-by",
            "t",
            "--recorded-at",
            "2026-09-15T00:00:00Z",
        ],
    )
    assert imported.returncode == 0
    ipayload = parse_envelope(imported)
    assert ipayload["command"] == "articles.import"
    validate_document(ipayload["data"]["record"], RECORD_SCHEMA)
    validate_document(ipayload["data"]["prospective_heads"], HEADS_SCHEMA)
    rec = ipayload["data"]["record"]
    checked = run_module_cli(
        world["checkout"],
        [
            "articles",
            "check",
            "--vault-root",
            vault,
            "--article-id",
            rec["article_id"],
            "--revision-id",
            rec["revision_id"],
            "--batch-id",
            "b1",
        ],
    )
    assert checked.returncode == 0
    cpayload = parse_envelope(checked)
    validate_document(cpayload["data"], CHECK_SCHEMA)
    assert cpayload["data"]["ranking"] == "not_ranked"
    rendered = run_module_cli(
        world["checkout"],
        [
            "articles",
            "render",
            "--vault-root",
            vault,
            "--batch-id",
            "b1",
            "--article-id",
            rec["article_id"],
            "--revision-id",
            rec["revision_id"],
        ],
    )
    assert rendered.returncode == 0
    rpayload = parse_envelope(rendered)
    assert (world["checkout"] / rpayload["data"]["markdown_path"]).exists()
    status = run_module_cli(world["checkout"], ["articles", "status", "--vault-root", vault, "--batch-id", "b1"])
    assert status.returncode == 0
    history = run_module_cli(
        world["checkout"],
        ["articles", "history", "--vault-root", vault, "--article-id", rec["article_id"], "--batch-id", "b1"],
    )
    assert history.returncode == 0


def test_cli_refusals_and_usage(world, capsys):
    missing = run_module_cli(
        world["checkout"],
        ["articles", "export", "--vault-root", "/nonexistent", "--question", "a", "--paper-id", "x"],
    )
    status = run_module_cli(world["checkout"], ["experiments", "status", "--vault-root", "/nonexistent"])
    assert missing.returncode == 2
    assert parse_envelope(missing)["error"]["code"] == parse_envelope(status)["error"]["code"]
    tokens = run_module_cli(
        world["checkout"],
        ["articles", "export", "--vault-root", "/nonexistent", "--question", "!!!", "--paper-id", "x"],
    )
    assert tokens.returncode == 2
    payload = parse_envelope(tokens)
    assert payload["error"]["code"] == "ARTICLE_CONTEXT_INVALID"
    assert payload["error"]["details"]["reason"] == "no_tokens"
    mode = run_module_cli(
        world["checkout"],
        [
            "articles",
            "export",
            "--vault-root",
            "/nonexistent",
            "--question",
            "a",
            "--paper-id",
            "x",
            "--article-id",
            "art-" + "0" * 20,
        ],
    )
    assert mode.returncode == 2
    assert parse_envelope(mode)["error"]["code"] == "ARTICLE_CONTEXT_INVALID"
    assert parse_envelope(mode)["error"]["details"]["reason"] == "mode"
    imported = run_module_cli(
        world["checkout"],
        [
            "articles",
            "import",
            "--vault-root",
            "/nonexistent",
            "--batch-id",
            "b1",
            "--context",
            "/etc/passwd",
            "--document",
            "/etc/passwd",
            "--recorded-by",
            "t",
            "--recorded-at",
            "2026-09-15T00:00:00Z",
        ],
    )
    assert imported.returncode == 2
    assert parse_envelope(imported)["error"]["code"] in {"ARTICLE_REVISION_INVALID", "WORK_PATH_UNSAFE"}
    check = run_module_cli(
        world["checkout"],
        [
            "articles",
            "check",
            "--vault-root",
            "/nonexistent",
            "--article-id",
            "art-" + "0" * 20,
            "--revision-id",
            "arv-" + "0" * 20,
        ],
    )
    assert check.returncode == 2
    assert parse_envelope(check)["error"]["code"] == "WORK_PATH_UNSAFE"
    code = main(["articles", "export"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(
        [
            "articles",
            "render",
            "--vault-root",
            "/nonexistent",
            "--article-id",
            "art-" + "0" * 20,
            "--revision-id",
            "arv-" + "0" * 20,
        ]
    )
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(["articles", "apply", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    graph = run_module_cli(world["checkout"], ["graph", "--help"])
    assert graph.returncode == 0
    assert set(_parent_leaves("graph")) == {"project", "query"}
    experiments = run_module_cli(world["checkout"], ["experiments", "--help"])
    assert experiments.returncode == 0
    assert set(_parent_leaves("experiments")) == {"record", "status", "compile", "publish-inspect", "matrix"}
    domain = run_module_cli(world["checkout"], ["domain", "--help"])
    assert domain.returncode == 0
    assert len(_parent_leaves("domain")) == 10
    code = main(["domain", "apply", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
