"""Operator confirmation for notes-vault bind-apply and bind-rollback."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from tests.unit.test_pdf_bindings import OTHER, _pdf, _plant, _prepare, _request_item, _world, _write_request

REPO_ROOT = Path(__file__).resolve().parents[2]


def _module():
    path = REPO_ROOT / "operator/src/video_paper_wiki_operator/cli.py"
    spec = importlib.util.spec_from_file_location("vpwiki_operator_cli_bind_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bind_apply_requires_confirmation_then_rolls_back(tmp_path, monkeypatch, capsys) -> None:
    world = _world(tmp_path, monkeypatch)
    pdf = _plant(world["cache"], "arxiv-2209.14792.pdf", _pdf("operator", "2209.14792"))
    plan = _prepare(world, _write_request(tmp_path, [_request_item(pdf, OTHER, session="bind-op")]), "bind-op")
    plan_path = tmp_path / ".work" / "bind-op" / "pdf-bind" / "plan.json"
    module = _module()
    monkeypatch.setattr(module, "_confirm", lambda _words: False)
    denied = module.main(
        [
            "pdf",
            "bind-apply",
            "--plan",
            str(plan_path),
            "--roots",
            str(world["roots"]),
            "--root-id",
            "notes-vault",
            "--approved-plan-sha256",
            plan["plan_sha256"],
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert denied == 2
    assert payload["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
    monkeypatch.setattr(module, "_confirm", lambda _words: True)
    applied = module.main(
        [
            "pdf",
            "bind-apply",
            "--plan",
            str(plan_path),
            "--roots",
            str(world["roots"]),
            "--root-id",
            "notes-vault",
            "--approved-plan-sha256",
            plan["plan_sha256"],
        ]
    )
    success = json.loads(capsys.readouterr().out)
    assert applied == 0 and success["ok"] is True
    page = world["notes"] / "papers" / "arxiv-2209.14792.md"
    binding = world["notes"] / "wiki" / "meta" / "pdf-bindings" / "arxiv-2209.14792.json"
    assert page.is_file() and binding.is_file()
    journal = success["data"]["journal_path"]
    rerun = module.main(
        [
            "pdf",
            "bind-apply",
            "--plan",
            str(plan_path),
            "--roots",
            str(world["roots"]),
            "--root-id",
            "notes-vault",
            "--approved-plan-sha256",
            plan["plan_sha256"],
        ]
    )
    assert rerun == 0
    capsys.readouterr()
    assert page.read_bytes()
    rolled = module.main(["pdf", "bind-rollback", "--journal", journal, "--roots", str(world["roots"])])
    body = json.loads(capsys.readouterr().out)
    assert rolled == 0 and body["ok"] is True
    assert not page.exists()
    assert not binding.exists()
    assert pdf.read_bytes() == _pdf("operator", "2209.14792")
