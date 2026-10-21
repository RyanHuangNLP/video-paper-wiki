from __future__ import annotations

import json

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_article_publication import (
    _export_ctx,
    _fill_full,
    _import_doc,
    _outline_doc,
    _provisional_section,
    _ts,
)
from tests.unit.test_article_revision import _claim_and_value, _write_json
from tests.unit.test_domain_proposal import _snapshot, make_world
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
        if getattr(action, "choices", None) and "articles" in action.choices:
            parent = action.choices["articles"]
            break
    assert parent is not None
    leaves = {}
    for action in parent._actions:
        if getattr(action, "choices", None):
            leaves.update(action.choices)
    return leaves


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


def test_cli_help_eight_leaves(capsys):
    leaves = _leaves()
    assert set(leaves) == {
        "check",
        "compile",
        "export",
        "history",
        "import",
        "publish-inspect",
        "render",
        "status",
    }
    compile_help = leaves["compile"].format_help()
    assert "--vault-root" in compile_help
    assert "--batch-id" in compile_help
    assert "--input" not in compile_help
    assert "--prepared" not in compile_help
    inspect_help = leaves["publish-inspect"].format_help()
    assert "--prepared" in inspect_help
    assert "--vault-root" in inspect_help
    assert "--batch-id" not in inspect_help
    code = main(["articles", "apply", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(["articles", "outline", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    assert set(_parent_leaves("graph")) == {"project", "query"}
    assert set(_parent_leaves("experiments")) == {
        "record",
        "status",
        "compile",
        "publish-inspect",
        "matrix",
    }
    assert set(_parent_leaves("domain")) == {
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
    code = main(["domain", "apply", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(["experiments", "apply", "--help"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"


def test_cli_compile_inspect_and_errors(world, capsys):
    data = _export_ctx(world)
    claim, value = _claim_and_value(data["context"])
    ctx = world["checkout"] / "ctx.json"
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    outline_path = world["checkout"] / "doc-o.json"
    _write_json(outline_path, _outline_doc(data["context"]))
    vault_before = _snapshot(world["vault"])
    export_args = [
        "articles",
        "export",
        "--vault-root",
        str(world["vault"]),
        "--question",
        data["context"]["question"],
    ]
    for paper in data["context"]["paper_ids"]:
        export_args.extend(["--paper-id", paper])
    export_proc = run_module_cli(world["checkout"], export_args)
    assert export_proc.returncode == 0
    import1 = run_module_cli(
        world["checkout"],
        [
            "articles",
            "import",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "b1",
            "--context",
            "ctx.json",
            "--document",
            "doc-o.json",
            "--recorded-by",
            "t",
            "--recorded-at",
            _ts(0),
        ],
    )
    assert import1.returncode == 0
    rec = parse_envelope(import1)["data"]["record"]
    s1 = _provisional_section(rec["sections"][0], data["context"], [claim["evidence_id"], value["evidence_id"]])
    _write_json(
        world["checkout"] / "doc-s.json",
        {"schema": "video-paper-wiki.article-document.v1", "title": rec["title"], "sections": [s1] + rec["sections"][1:]},
    )
    import2 = run_module_cli(
        world["checkout"],
        [
            "articles",
            "import",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "b1",
            "--context",
            "ctx.json",
            "--document",
            "doc-s.json",
            "--recorded-by",
            "t",
            "--recorded-at",
            _ts(1),
            "--previous-revision-id",
            rec["revision_id"],
            "--target-section-id",
            "s1",
        ],
    )
    assert import2.returncode == 0
    rec2 = parse_envelope(import2)["data"]["record"]
    _write_json(world["checkout"] / "doc-f.json", _fill_full(rec2, data["context"], [claim["evidence_id"]]))
    import3 = run_module_cli(
        world["checkout"],
        [
            "articles",
            "import",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "b1",
            "--context",
            "ctx.json",
            "--document",
            "doc-f.json",
            "--recorded-by",
            "t",
            "--recorded-at",
            _ts(2),
            "--previous-revision-id",
            rec2["revision_id"],
        ],
    )
    assert import3.returncode == 0
    compile_proc = run_module_cli(
        world["checkout"],
        ["articles", "compile", "--vault-root", str(world["vault"]), "--batch-id", "b1"],
    )
    compile_payload = parse_envelope(compile_proc)
    assert compile_proc.returncode == 0
    assert compile_payload["command"] == "articles.compile"
    assert compile_payload["data"]["state"] == "article_publication_prepared"
    assert _snapshot(world["vault"]) == vault_before
    inspect_proc = run_module_cli(
        world["checkout"],
        [
            "articles",
            "publish-inspect",
            "--prepared",
            ".work/b1/article-publication/request.json",
            "--vault-root",
            str(world["vault"]),
        ],
    )
    inspect_payload = parse_envelope(inspect_proc)
    assert inspect_proc.returncode == 0
    assert inspect_payload["command"] == "articles.publish-inspect"
    validate_document(inspect_payload["data"], "video-paper-wiki.article-publication-inspection.v1")
    inspect_again = run_module_cli(
        world["checkout"],
        [
            "articles",
            "publish-inspect",
            "--prepared",
            ".work/b1/article-publication/request.json",
            "--vault-root",
            str(world["vault"]),
        ],
    )
    assert inspect_again.returncode == 0
    assert inspect_again.stdout == inspect_proc.stdout
    _import_doc(world, data, _outline_doc(data["context"]), batch="b2", recorded_at=_ts(3), tag="-o")
    incomplete = run_module_cli(
        world["checkout"],
        ["articles", "compile", "--vault-root", str(world["vault"]), "--batch-id", "b2"],
    )
    assert incomplete.returncode == 2
    assert parse_envelope(incomplete)["error"]["code"] == "ARTICLE_COMPILE_INCOMPLETE"
    missing_vault = run_module_cli(
        world["checkout"],
        ["articles", "compile", "--vault-root", "/nonexistent", "--batch-id", "b1"],
    )
    status_missing = run_module_cli(
        world["checkout"],
        ["articles", "status", "--vault-root", "/nonexistent"],
    )
    assert missing_vault.returncode == 2
    assert status_missing.returncode == 2
    assert parse_envelope(missing_vault)["error"]["code"] == parse_envelope(status_missing)["error"]["code"]
    assert parse_envelope(missing_vault)["error"]["code"] == "WORK_PATH_UNSAFE"
    empty = run_module_cli(
        world["checkout"],
        ["articles", "compile", "--vault-root", str(world["vault"]), "--batch-id", "nope"],
    )
    assert empty.returncode == 2
    assert parse_envelope(empty)["error"]["code"] == "ARTICLE_COMPILE_EMPTY"
    unsafe = run_module_cli(
        world["checkout"],
        [
            "articles",
            "publish-inspect",
            "--prepared",
            "/etc/passwd",
            "--vault-root",
            str(world["vault"]),
        ],
    )
    assert unsafe.returncode == 2
    assert parse_envelope(unsafe)["error"]["code"] == "WORK_PATH_UNSAFE"
    code = main(["articles", "compile"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    code = main(["articles", "publish-inspect", "--vault-root", "/nonexistent"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"
    assert canonicalize(inspect_payload["data"])
