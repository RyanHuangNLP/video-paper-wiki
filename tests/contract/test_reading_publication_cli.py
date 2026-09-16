from __future__ import annotations

import json
import subprocess
import sys

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staging import validate_batch_id


def _leaves(name: str) -> dict:
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


def test_reading_help_and_leaf_flags(world_checkout=None):
    leaves = _leaves("reading")
    assert set(leaves) == {"build", "compile", "publish-inspect"}
    compile_help = leaves["compile"].format_help()
    assert "--vault-root" in compile_help
    assert "--batch-id" in compile_help
    assert "--prepared" not in compile_help
    assert "--paper-id" not in compile_help
    inspect_help = leaves["publish-inspect"].format_help()
    assert "--prepared" in inspect_help
    assert "--vault-root" in inspect_help
    assert "--batch-id" not in inspect_help
    build_help = leaves["build"].format_help()
    assert "--vault-root" in build_help
    assert "--batch-id" in build_help
    assert "--paper-id" in build_help
    assert "--articles-batch" in build_help


def test_cli_help_and_usage(tmp_path, monkeypatch, capsys):
    world = make_world(tmp_path, monkeypatch)
    checkout = world["checkout"]
    help_parent = run_module_cli(checkout, ["reading", "--help"])
    assert help_parent.returncode == 0
    assert "{build,compile,publish-inspect}" in help_parent.stdout
    assert "本刀未提供" not in help_parent.stdout
    help_compile = run_module_cli(checkout, ["reading", "compile", "--help"])
    assert help_compile.returncode == 0
    assert "--vault-root" in help_compile.stdout
    assert "--batch-id" in help_compile.stdout
    assert "--prepared" not in help_compile.stdout
    assert "--paper-id" not in help_compile.stdout
    help_inspect = run_module_cli(checkout, ["reading", "publish-inspect", "--help"])
    assert help_inspect.returncode == 0
    assert "--prepared" in help_inspect.stdout
    assert "--vault-root" in help_inspect.stdout
    assert "--batch-id" not in help_inspect.stdout
    apply_help = run_module_cli(checkout, ["reading", "apply", "--help"])
    assert apply_help.returncode == 2
    payload = parse_envelope(apply_help)
    assert payload["error"]["code"] == "USAGE"
    help_build = run_module_cli(checkout, ["reading", "build", "--help"])
    assert help_build.returncode == 0
    assert "--paper-id" in help_build.stdout
    assert "--articles-batch" in help_build.stdout
    module_help = subprocess.run(
        [sys.executable, "-m", "video_paper_wiki.reading", "--help"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert module_help.returncode == 0
    assert "{build}" in module_help.stdout
    assert "{build,compile" not in module_help.stdout
    missing = run_module_cli(checkout, ["reading", "compile", "--vault-root", "/nonexistent", "--batch-id", "b1"])
    articles = run_module_cli(checkout, ["articles", "compile", "--vault-root", "/nonexistent", "--batch-id", "b1"])
    assert missing.returncode == 2
    assert articles.returncode == 2
    assert parse_envelope(missing)["error"]["code"] == parse_envelope(articles)["error"]["code"]
    assert parse_envelope(missing)["error"]["code"] == "WORK_PATH_UNSAFE"
    from tests.code_proof_public_fixture import make_checkout

    empty = tmp_path / "empty-co"
    make_checkout(empty)
    empty_run = run_module_cli(empty, ["reading", "compile", "--vault-root", "/nonexistent", "--batch-id", "b1"])
    assert empty_run.returncode == 2
    assert parse_envelope(empty_run)["error"]["code"] == "WORK_PATH_UNSAFE"
    assert not (empty / ".work").exists()
    empty = run_module_cli(
        checkout,
        ["reading", "compile", "--vault-root", str(world["vault"]), "--batch-id", "nope"],
    )
    assert empty.returncode == 2
    empty_payload = parse_envelope(empty)
    assert empty_payload["error"]["code"] == "READING_COMPILE_EMPTY"
    assert empty_payload["error"]["details"]["next_action"] == "build_reading"
    bad = run_module_cli(
        checkout,
        ["reading", "compile", "--vault-root", str(world["vault"]), "--batch-id", "BAD/ID"],
    )
    build_bad = run_module_cli(
        checkout,
        ["reading", "build", "--vault-root", str(world["vault"]), "--batch-id", "BAD/ID"],
    )
    assert parse_envelope(bad)["error"]["code"] == parse_envelope(build_bad)["error"]["code"]
    assert parse_envelope(bad)["error"]["code"] == "INVALID_BATCH_ID"
    unsafe = run_module_cli(
        checkout,
        ["reading", "publish-inspect", "--prepared", "/etc/passwd", "--vault-root", str(world["vault"])],
    )
    assert unsafe.returncode == 2
    assert parse_envelope(unsafe)["error"]["code"] == "WORK_PATH_UNSAFE"
    usage = run_module_cli(checkout, ["reading", "compile"])
    assert usage.returncode == 2
    assert parse_envelope(usage)["error"]["code"] == "USAGE"
    usage2 = run_module_cli(checkout, ["reading", "publish-inspect", "--vault-root", "/nonexistent"])
    assert usage2.returncode == 2
    assert parse_envelope(usage2)["error"]["code"] == "USAGE"
    articles_help = run_module_cli(checkout, ["articles", "--help"])
    graph_help = run_module_cli(checkout, ["graph", "--help"])
    flow_help = run_module_cli(checkout, ["flow", "--help"])
    assert articles_help.returncode == 0
    assert graph_help.returncode == 0
    assert flow_help.returncode == 0
    assert "compile" in articles_help.stdout
    assert "publish-inspect" in articles_help.stdout
    assert "project" in graph_help.stdout
    assert "query" in graph_help.stdout
    assert len(_leaves("articles")) == 8
    assert len(_leaves("graph")) == 2
    assert len(_leaves("flow")) == 3


def test_cli_success_chain_and_slots(tmp_path, monkeypatch):
    world = make_world(tmp_path, monkeypatch)
    _three_chain(world)
    checkout = world["vault"].parent if False else world["checkout"]
    vault = str(world["vault"])
    built = run_module_cli(
        world["checkout"],
        ["reading", "build", "--vault-root", vault, "--batch-id", "r1"],
    )
    assert built.returncode == 0
    compiled = run_module_cli(
        world["checkout"],
        ["reading", "compile", "--vault-root", vault, "--batch-id", "r1"],
    )
    assert compiled.returncode == 0
    payload = parse_envelope(compiled)
    assert payload["command"] == "reading.compile"
    assert payload["data"]["state"] == "reading_publication_prepared"
    validate_document(
        json.loads((world["checkout"] / ".work/r1/reading-publication/request.json").read_bytes()),
        "video-paper-wiki.reading-publication-request.v1",
    )
    assert payload["data"]["write_plan_counts"]["create"] == payload["data"]["write_plan_counts"]["create"]
    prepared = str(world["checkout"] / ".work/r1/reading-publication/request.json")
    inspect = run_module_cli(
        world["checkout"],
        ["reading", "publish-inspect", "--prepared", prepared, "--vault-root", vault],
    )
    assert inspect.returncode == 0
    inspected = parse_envelope(inspect)
    assert inspected["command"] == "reading.publish-inspect"
    validate_document(inspected["data"], "video-paper-wiki.reading-publication-inspection.v1")
    again = run_module_cli(
        world["checkout"],
        ["reading", "publish-inspect", "--prepared", prepared, "--vault-root", vault],
    )
    assert again.stdout.encode("utf-8") == inspect.stdout.encode("utf-8")
    conflict = run_module_cli(
        world["checkout"],
        ["reading", "compile", "--vault-root", vault, "--batch-id", "r1"],
    )
    assert conflict.returncode == 75
    assert parse_envelope(conflict)["error"]["code"] == "STAGING_CONFLICT"
    validate_batch_id("r1")
    assert canonicalize(payload) == canonicalize(json.loads(compiled.stdout.strip()))
    manifest_prepared = run_module_cli(
        world["checkout"],
        [
            "reading",
            "publish-inspect",
            "--prepared",
            str(world["checkout"] / ".work/r1/reading/manifest.json"),
            "--vault-root",
            vault,
        ],
    )
    assert parse_envelope(manifest_prepared)["error"]["code"] == "WORK_PATH_UNSAFE"
    article_slot = world["checkout"] / ".work/r1/article-publication/request.json"
    article_slot.parent.mkdir(parents=True, exist_ok=True)
    article_slot.write_bytes(b"{}\n")
    article_prepared = run_module_cli(
        world["checkout"],
        ["reading", "publish-inspect", "--prepared", str(article_slot), "--vault-root", vault],
    )
    assert parse_envelope(article_prepared)["error"]["code"] == "WORK_PATH_UNSAFE"
