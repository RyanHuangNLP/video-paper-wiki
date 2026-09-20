from __future__ import annotations

import json
from pathlib import Path

from tests.support import make_checkout
from video_paper_wiki.cli import main
from video_paper_wiki.pdf_locations import PDF_PARAMETER_CONFLICT


def _stdout(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_pdf_leaves_and_resolve_offline_conflict(tmp_path, monkeypatch, capsys) -> None:
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
    code = main(
        [
            "pdf",
            "link-prepare",
            "--roots",
            str(roots),
            "--root-id",
            "notes-main",
            "--paper-id",
            "arxiv:2204.03458",
            "--drive-file-id",
            "1AbCdefGhijkLMNOPqrstUVwxyz0123456",
            "--batch-id",
            "cli-link",
        ]
    )
    payload = _stdout(capsys)
    assert code == 0
    assert payload["ok"] is True
    assert payload["command"] == "pdf.link-prepare"
    assert payload["data"]["kind"] == "unverified-link"
    conflict = main(
        [
            "pdf",
            "resolve",
            "--roots",
            str(roots),
            "--root-id",
            "notes-main",
            "--paper-id",
            "arxiv:2204.03458",
            "--prefer",
            "drive",
            "--offline",
        ]
    )
    denied = _stdout(capsys)
    assert conflict == 2
    assert denied["ok"] is False
    assert denied["error"]["code"] == PDF_PARAMETER_CONFLICT
    report = main(
        [
            "pdf",
            "migrate-report",
            "--plan",
            str(Path(".work/cli-link/pdf-migration/plan.json")),
            "--roots",
            str(roots),
        ]
    )
    reported = _stdout(capsys)
    assert report == 0
    assert reported["data"]["schema"] == "video-paper-wiki.pdf-migration-report.v1"
