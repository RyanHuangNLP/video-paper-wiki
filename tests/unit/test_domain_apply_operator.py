from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from tests.unit.test_domain_proposal import _snapshot, make_world, valid_proposal
from tests.unit.test_domain_store import _record
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_publication import compile_domain_publication
from video_paper_wiki.jcs import canonicalize

RESULT_SCHEMA = "video-paper-wiki.domain-publication-apply-result.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _module():
    path = REPO_ROOT / "operator/src/video_paper_wiki_operator/cli.py"
    spec = importlib.util.spec_from_file_location("vpwiki_operator_cli_domain_apply_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _prepared(world, batch):
    return str(world["checkout"] / ".work" / batch / "domain-publication" / "request.json")


def _guard(module, monkeypatch):
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("domain apply spawned a subprocess")),
    )
    monkeypatch.setattr(
        module,
        "_verified_root",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("domain apply called _verified_root")),
    )


def _argv(world, batch="op1"):
    return [
        "domain",
        "apply",
        "--prepared",
        _prepared(world, batch),
        "--vault-root",
        str(world["vault"]),
    ]


def test_domain_apply_non_tty_requires_confirmation(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _record(world, valid_proposal(world), name="g.json", batch="op1")
    compile_domain_publication(vault_root=str(world["vault"]), batch_id="op1")
    vault_before = _snapshot(world["vault"])
    assert module.main(_argv(world, "op1")) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
    assert payload["error"]["details"]["next_action"] == "confirm_interactively"
    assert _snapshot(world["vault"]) == vault_before


def test_domain_apply_confirm_success_changed_and_already_applied(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _record(world, valid_proposal(world), name="g.json", batch="op2")
    compile_domain_publication(vault_root=str(world["vault"]), batch_id="op2")
    extra = world["vault"] / "wiki/meta/domain" / "extra.json"

    def tamper(_words):
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_bytes(b"{}")
        os.chmod(extra, 0o600)
        return True

    monkeypatch.setattr(module, "_confirm", tamper)
    assert module.main(_argv(world, "op2")) == 75
    changed = json.loads(capsys.readouterr().out)
    assert changed["error"]["code"] == "DOMAIN_APPLY_CHANGED"
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
    assert again["error"]["code"] == "DOMAIN_APPLY_ALREADY_APPLIED"


def test_domain_apply_upstream_root_is_usage_invalid(world, monkeypatch, capsys):
    module = _module()
    _guard(module, monkeypatch)
    _record(world, valid_proposal(world), name="g.json", batch="op4")
    compile_domain_publication(vault_root=str(world["vault"]), batch_id="op4")
    assert (
        module.main(
            [
                "--upstream-root",
                str(world["checkout"]),
                "domain",
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
