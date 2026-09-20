from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests.support import make_checkout
from video_paper_wiki.pdf_migration import prepare_unverified_link

REPO_ROOT = Path(__file__).resolve().parents[2]
FILE_ID = "1AbCdefGhijkLMNOPqrstUVwxyz0123456"


def _module():
    path = REPO_ROOT / "operator/src/video_paper_wiki_operator/cli.py"
    spec = importlib.util.spec_from_file_location("vpwiki_operator_cli_pdf_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migrate_apply_requires_confirmation_then_reruns(tmp_path, monkeypatch, capsys) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    vault.mkdir()
    roots = vault / "roots.json"
    roots.write_text(
        json.dumps(
            {
                "roots": [
                    {
                        "root_id": "notes-main",
                        "kind": "notes-vault",
                        "path": str(vault),
                        "role": "target",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        batch_id="op-link",
        drive_file_id=FILE_ID,
    )
    plan_path = tmp_path / ".work" / "op-link" / "pdf-migration" / "plan.json"
    module = _module()
    monkeypatch.setattr(module, "_confirm", lambda _words: False)
    denied = module.main(
        [
            "pdf",
            "migrate-apply",
            "--plan",
            str(plan_path),
            "--roots",
            str(roots),
            "--root-id",
            "notes-main",
            "--approved-plan-sha256",
            plan["plan_sha256"],
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert denied == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
    monkeypatch.setattr(module, "_confirm", lambda _words: True)
    applied = module.main(
        [
            "pdf",
            "migrate-apply",
            "--plan",
            str(plan_path),
            "--roots",
            str(roots),
            "--root-id",
            "notes-main",
            "--approved-plan-sha256",
            plan["plan_sha256"],
        ]
    )
    success = json.loads(capsys.readouterr().out)
    assert applied == 0
    assert success["ok"] is True
    loc = vault / "wiki/meta/pdf-locations/arxiv-2204.03458.json"
    assert loc.is_file()
    journal = Path(success["data"]["journal_path"])
    loc.write_text("{}\n", encoding="utf-8")
    rolled = module.main(["pdf", "migrate-rollback", "--journal", str(journal), "--roots", str(roots)])
    rollback = json.loads(capsys.readouterr().out)
    assert rolled == 2
    assert rollback["error"]["code"] == "PDF_ROLLBACK_CONFLICT"
