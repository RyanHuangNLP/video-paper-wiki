from __future__ import annotations

import os
from pathlib import Path

from tests.research.conftest import SESSION, UPSTREAM, fixture_converter, stdout_json, write_pdf
from tests.support import make_checkout
from video_paper_wiki.cli import main as vpwiki_main
from video_paper_wiki_parser_executor.cli import main as parser_main
from video_paper_wiki_parser_executor.exporter import export_run, set_test_converter
from video_paper_wiki_research.cli import main as research_main
from video_paper_wiki_research.parser_profile import create_profile
from video_paper_wiki_research.storage import open_research_session


def test_usage_and_entrypoint(checkout: Path, capsys) -> None:
    assert research_main([]) == 2
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert parser_main([]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"


def test_cli_does_not_call_admin(checkout: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "admin.called"
    script = bin_dir / "vpwiki-admin"
    script.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n", encoding="utf-8")
    script.chmod(0o700)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    pdf = write_pdf(checkout / "paper.pdf")
    assert research_main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION]) == 0
    stdout_json(capsys)
    assert not marker.exists()


def test_cli_plan_and_vertical_commands(checkout: Path, models: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "video_paper_wiki_research.parser_profile.importlib.metadata.version",
        lambda name: {"docling": "2.117.0", "docling-core": "2.92.0"}[name],
    )
    pdf = write_pdf(checkout / "paper.pdf")
    assert research_main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION]) == 0
    intake = Path(stdout_json(capsys)["data"]["path"])
    with open_research_session(SESSION) as session:
        profile = Path(create_profile(session, models, version_loader=lambda: ("2.117.0", "2.92.0"))["path"])
        set_test_converter(fixture_converter())
        try:
            exported = export_run(
                session,
                intake_path=intake,
                profile_path=profile,
                artifacts_path=models,
                run_id="run-cli",
            )
        finally:
            set_test_converter(None)
    assert research_main(
        ["pdf", "plan", "--intake", str(intake), "--profile", str(profile), "--batch-id", "plan-1"]
    ) == 0
    planned = stdout_json(capsys)
    assert planned["data"]["next_action"] == "awaiting_external_approval_ref"
    assert Path(planned["data"]["plan_path"]).is_file()
    run_dir = checkout / Path(exported["paths"]["document_json"]).parent
    assert research_main(
        [
            "pdf",
            "context",
            "--intake",
            str(intake),
            "--profile",
            str(profile),
            "--run",
            str(run_dir),
            "--upstream-root",
            str(UPSTREAM),
            "--session",
            SESSION,
        ]
    ) == 0
    context = stdout_json(capsys)
    assert context["data"]["state"] == "staged_extraction"
    assert "prompt" in context["data"]
    seed = vpwiki_main(["seed", "validate"])
    assert seed == 0
    seed_payload = stdout_json(capsys)
    assert seed_payload["data"]["paper_count"] == 67
