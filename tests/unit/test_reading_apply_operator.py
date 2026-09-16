from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_graph_projection import _three_chain
from tests.unit.test_reading_view import _build
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.reading_publication import compile_reading_publication

RESULT_SCHEMA = "video-paper-wiki.reading-publication-apply-result.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _module():
    path = REPO_ROOT / "operator/src/video_paper_wiki_operator/cli.py"
    spec = importlib.util.spec_from_file_location("vpwiki_operator_cli_reading_apply_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _prepared(world, batch):
    return str(world["checkout"] / ".work" / batch / "reading-publication" / "request.json")


def _guard(module, monkeypatch):
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("reading apply spawned a subprocess")),
    )
    monkeypatch.setattr(
        module,
        "_verified_root",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("reading apply called _verified_root")),
    )


def _argv(world, batch="op1"):
    return [
        "reading",
        "apply",
        "--prepared",
        _prepared(world, batch),
        "--vault-root",
        str(world["vault"]),
    ]


def _stage(world, batch):
    _three_chain(world)
    _build(world, batch)
    compile_reading_publication(vault_root=str(world["vault"]), batch_id=batch)


def test_reading_apply_non_tty_requires_confirmation(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _stage(world, "op1")
    vault_before = _snapshot(world["vault"])
    assert module.main(_argv(world, "op1")) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
    assert payload["error"]["details"]["next_action"] == "confirm_interactively"
    assert _snapshot(world["vault"]) == vault_before


def test_reading_apply_confirm_success_changed_and_already_applied(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _stage(world, "op2")
    ledger = world["vault"] / "wiki/meta/ledgers/claim-ledger.json"
    original = ledger.read_bytes()

    def tamper(_words):
        ledger.write_bytes(original + b" ")
        return True

    monkeypatch.setattr(module, "_confirm", tamper)
    assert module.main(_argv(world, "op2")) == 75
    changed = json.loads(capsys.readouterr().out)
    assert changed["error"]["code"] == "READING_APPLY_CHANGED"
    ledger.write_bytes(original)
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
    assert again["error"]["code"] == "READING_APPLY_ALREADY_APPLIED"


def test_reading_apply_upstream_root_and_unsafe_prepared(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _stage(world, "op4")
    assert (
        module.main(
            [
                "--upstream-root",
                str(world["checkout"]),
                "reading",
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
                "reading",
                "apply",
                "--prepared",
                str(world["checkout"] / ".work/op4/article-publication/request.json"),
                "--vault-root",
                str(world["vault"]),
            ]
        )
        == 2
    )
    unsafe = json.loads(capsys.readouterr().out)
    assert unsafe["error"]["code"] == "WORK_PATH_UNSAFE"
    assert unsafe["error"]["details"].get("instance_pointer") == "/prepared"
    assert unsafe["error"]["details"].get("next_action") == "repair_input"
