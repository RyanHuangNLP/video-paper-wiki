from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.research.conftest import SESSION, TEXT, fixture_converter, stdout_json, synthetic_document, write_pdf
from video_paper_wiki.extraction_artifact import validate_docling_artifact_set
from video_paper_wiki_parser_executor.cli import main as parser_main
from video_paper_wiki_parser_executor.exporter import export_run, set_test_converter
from video_paper_wiki_research.cli import main as research_main
from video_paper_wiki_research.parser_profile import create_profile
from video_paper_wiki_research.storage import open_research_session


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki_research.parser_profile.importlib.metadata.version",
        lambda name: {"docling": "2.117.0", "docling-core": "2.92.0"}[name],
    )


def _intake_and_profile(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> tuple[Path, Path]:
    _patch_runtime(monkeypatch)
    pdf = write_pdf(checkout / "paper.pdf")
    assert research_main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION]) == 0
    intake = Path(stdout_json(capsys)["data"]["path"])
    with open_research_session(SESSION) as session:
        created = create_profile(session, models, version_loader=lambda: ("2.117.0", "2.92.0"))
    return intake, Path(created["path"])


def test_export_success_reuse_conflict_empty(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    intake, profile = _intake_and_profile(checkout, models, monkeypatch, capsys)
    set_test_converter(fixture_converter())
    try:
        with open_research_session(SESSION) as session:
            result = export_run(
                session,
                intake_path=intake,
                profile_path=profile,
                artifacts_path=models,
                run_id="run-1",
            )
            reused = export_run(
                session,
                intake_path=intake,
                profile_path=profile,
                artifacts_path=models,
                run_id="run-1",
            )
        assert result["state"] == "staged_extraction"
        assert result["capture_authorized"] is False
        assert reused["already_staged"] is True
        for rel in result["paths"].values():
            assert (checkout / rel).is_file()
        other = write_pdf(checkout / "other.pdf", pages=2)
        assert research_main(["pdf", "intake", "--pdf", str(other), "--session", "s2"]) == 0
        other_intake = Path(stdout_json(capsys)["data"]["path"])
        with open_research_session(SESSION) as session:
            with pytest.raises(Exception) as exc:
                export_run(
                    session,
                    intake_path=other_intake,
                    profile_path=profile,
                    artifacts_path=models,
                    run_id="run-1",
                )
            assert exc.value.code in {"PARSER_RUN_CONFLICT", "PARSER_SOURCE_UNBOUND"}
        set_test_converter(fixture_converter({"texts": [], "pages": {"1": {"page_no": 1, "size": {"width": 72.0, "height": 72.0}}}}))
        with open_research_session(SESSION) as session:
            with pytest.raises(Exception) as empty:
                export_run(
                    session,
                    intake_path=intake,
                    profile_path=profile,
                    artifacts_path=models,
                    run_id="run-empty",
                )
            assert empty.value.code == "PARSER_NO_TEXT"
    finally:
        set_test_converter(None)


def test_export_non_finite_and_package_compat(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    intake, profile = _intake_and_profile(checkout, models, monkeypatch, capsys)
    bad = synthetic_document()
    bad["pages"]["1"]["size"]["width"] = float("nan")
    set_test_converter(fixture_converter(bad))
    try:
        with open_research_session(SESSION) as session:
            with pytest.raises(Exception) as exc:
                export_run(
                    session,
                    intake_path=intake,
                    profile_path=profile,
                    artifacts_path=models,
                    run_id="run-nan",
                )
            assert exc.value.code in {"PARSER_OUTPUT_INVALID", "PARSER_FAILED"}
        set_test_converter(fixture_converter())
        with open_research_session(SESSION) as session:
            result = export_run(
                session,
                intake_path=intake,
                profile_path=profile,
                artifacts_path=models,
                run_id="run-pkg",
            )
        run_dir = checkout / Path(result["paths"]["document_json"]).parent
        bytes_map = {
            "document_json": (run_dir / "document.json").read_bytes(),
            "parser_config": (run_dir / "parser-config.json").read_bytes(),
            "model_manifest": (run_dir / "model-manifest.json").read_bytes(),
            "run_manifest": (run_dir / "run.json").read_bytes(),
        }
        from video_paper_wiki_research.contracts import sha256_bytes

        intake_json = json.loads(intake.read_text(encoding="utf-8"))
        pdf_digest = intake_json["data"]["pdf_sha256"]
        fp = result["pipeline_fingerprint"]
        kinds = (
            ("document_json", f".raw/derived/{pdf_digest}/docling/{fp}/document.json"),
            ("model_manifest", f".raw/derived/{pdf_digest}/docling/{fp}/model-manifest.json"),
            ("parser_config", f".raw/derived/{pdf_digest}/docling/{fp}/parser-config.json"),
            ("run_manifest", f".raw/derived/{pdf_digest}/runs/run-pkg.json"),
        )
        artifacts = [
            {
                "kind": kind,
                "path": path,
                "sha256": sha256_bytes(bytes_map[kind]),
                "size_bytes": len(bytes_map[kind]),
            }
            for kind, path in kinds
        ]
        packaged = validate_docling_artifact_set(
            {
                "schema": "video-paper-wiki.docling-artifact-set.v1",
                "captured_pdf_sha256": pdf_digest,
                "engine": "docling",
                "engine_version": "2.117.0",
                "core_version": "2.92.0",
                "pipeline_fingerprint": fp,
                "artifacts": artifacts,
            },
            bytes_map=bytes_map,
        )
        assert packaged["pipeline_fingerprint"] == fp
        assert TEXT in json.loads(bytes_map["document_json"].decode("utf-8"))["texts"][0]["text"]
    finally:
        set_test_converter(None)


def test_export_failed_status_keeps_failed_run(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    intake, profile = _intake_and_profile(checkout, models, monkeypatch, capsys)
    set_test_converter(fixture_converter(status="FAILURE"))
    try:
        with open_research_session(SESSION) as session:
            with pytest.raises(Exception) as exc:
                export_run(
                    session,
                    intake_path=intake,
                    profile_path=profile,
                    artifacts_path=models,
                    run_id="run-fail",
                )
            assert exc.value.code == "PARSER_FAILED"
            failed = session.path("failed-runs", "run-fail.json")
            assert failed.is_file()
    finally:
        set_test_converter(None)
