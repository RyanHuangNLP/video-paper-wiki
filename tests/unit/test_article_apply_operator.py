from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from tests.unit.test_article_publication import _compile, _stage_complete
from tests.unit.test_domain_proposal import _snapshot, make_world
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.jcs import canonicalize

RESULT_SCHEMA = "video-paper-wiki.article-publication-apply-result.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _module():
    path = REPO_ROOT / "operator/src/video_paper_wiki_operator/cli.py"
    spec = importlib.util.spec_from_file_location("vpwiki_operator_cli_articles_apply_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _prepared(world, batch):
    return str(world["checkout"] / ".work" / batch / "article-publication" / "request.json")


def _guard(module, monkeypatch):
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("articles apply spawned a subprocess")),
    )
    monkeypatch.setattr(
        module,
        "_verified_root",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("articles apply called _verified_root")),
    )


def _argv(world, batch="op1"):
    return [
        "articles",
        "apply",
        "--prepared",
        _prepared(world, batch),
        "--vault-root",
        str(world["vault"]),
    ]


def test_articles_apply_non_tty_requires_confirmation(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _stage_complete(world, batch="op1")
    _compile(world, "op1")
    vault_before = _snapshot(world["vault"])
    assert module.main(_argv(world, "op1")) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
    assert payload["error"]["details"]["next_action"] == "confirm_interactively"
    assert _snapshot(world["vault"]) == vault_before


def test_articles_apply_confirm_success_changed_and_already_applied(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _stage_complete(world, batch="op2")
    _compile(world, "op2")
    extra = world["vault"] / "wiki/meta/articles" / "extra.json"

    def tamper(_words):
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_bytes(b"{}")
        os.chmod(extra, 0o600)
        return True

    monkeypatch.setattr(module, "_confirm", tamper)
    assert module.main(_argv(world, "op2")) == 75
    changed = json.loads(capsys.readouterr().out)
    assert changed["error"]["code"] == "ARTICLE_APPLY_CHANGED"
    if extra.exists():
        extra.unlink()
        if extra.parent.exists() and not any(extra.parent.iterdir()):
            extra.parent.rmdir()
    monkeypatch.setattr(module, "_confirm", lambda _words: True)
    assert module.main(_argv(world, "op2")) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    validate_document(payload["data"], RESULT_SCHEMA)
    summary_lines = [line for line in captured.err.splitlines() if line.strip()]
    assert summary_lines
    summary = json.loads(summary_lines[-1])
    assert summary["batch_id"] == "op2"
    assert canonicalize(summary) == summary_lines[-1].encode("utf-8")
    assert module.main(_argv(world, "op2")) == 2
    again = json.loads(capsys.readouterr().out)
    assert again["error"]["code"] == "ARTICLE_APPLY_ALREADY_APPLIED"


def test_articles_apply_upstream_root_and_unsafe_prepared(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _stage_complete(world, batch="op4")
    _compile(world, "op4")
    assert (
        module.main(
            [
                "--upstream-root",
                str(world["checkout"]),
                "articles",
                "apply",
                "--prepared",
                _prepared(world, "op4"),
                "--vault-root",
                str(world["vault"]),
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "USAGE_INVALID"
    monkeypatch.setattr(module, "_confirm", lambda _words: True)
    assert (
        module.main(
            [
                "articles",
                "apply",
                "--prepared",
                str(world["checkout"] / ".work/op4/experiment-publication/request.json"),
                "--vault-root",
                str(world["vault"]),
            ]
        )
        == 2
    )
    unsafe = json.loads(capsys.readouterr().out)
    assert unsafe["error"]["code"] == "WORK_PATH_UNSAFE"
