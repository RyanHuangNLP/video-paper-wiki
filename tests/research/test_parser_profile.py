from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.research.conftest import SESSION, stdout_json
from video_paper_wiki_parser_executor.cli import main as parser_main
from video_paper_wiki_research.parser_profile import create_profile, inventory_models
from video_paper_wiki_research.storage import open_research_session


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki_research.parser_profile.importlib.metadata.version",
        lambda name: {"docling": "2.117.0", "docling-core": "2.92.0"}[name],
    )


def test_profile_success_and_idempotent(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _patch_runtime(monkeypatch)
    code = parser_main(["profile", "--artifacts-path", str(models), "--session", SESSION])
    payload = stdout_json(capsys)
    assert code == 0
    assert payload["command"] == "parser.profile"
    assert payload["data"]["next_action"] == "awaiting_parser_export"
    profile = Path(payload["data"]["path"])
    assert profile.name == "profile.json"
    assert Path(payload["data"]["parser_config_path"]).is_file()
    again = parser_main(["profile", "--artifacts-path", str(models), "--session", SESSION])
    second = stdout_json(capsys)
    assert again == 0
    assert second["data"]["already_staged"] is True


def test_profile_missing_runtime(checkout: Path, models: Path, capsys) -> None:
    code = parser_main(["profile", "--artifacts-path", str(models), "--session", SESSION])
    payload = stdout_json(capsys)
    assert code == 2
    assert payload["error"]["code"] in {"PARSER_RUNTIME_MISSING", "PARSER_RUNTIME_INCOMPATIBLE"}


def test_profile_empty_and_symlink(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime(monkeypatch)
    empty = checkout / "empty-models"
    empty.mkdir()
    with open_research_session(SESSION) as session:
        with pytest.raises(Exception) as exc:
            create_profile(session, empty, version_loader=lambda: ("2.117.0", "2.92.0"))
    assert exc.value.code == "PARSER_MODELS_MISSING"
    linked = checkout / "link-models"
    linked.symlink_to(models)
    with pytest.raises(Exception) as exc2:
        inventory_models(linked)
    assert exc2.value.code in {"PARSER_MODELS_MISSING", "PARSER_PROFILE_INVALID"}
    nested = models / "layout" / "alias.bin"
    nested.symlink_to(models / "layout" / "weights.bin")
    with pytest.raises(Exception) as exc3:
        inventory_models(models)
    assert exc3.value.code == "PARSER_PROFILE_INVALID"


def test_profile_drift_and_runtime_mismatch(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime(monkeypatch)
    with open_research_session(SESSION) as session:
        create_profile(session, models, version_loader=lambda: ("2.117.0", "2.92.0"))
        (models / "extra.bin").write_bytes(b"drift")
        with pytest.raises(Exception) as exc:
            create_profile(session, models, version_loader=lambda: ("2.117.0", "2.92.0"))
        assert exc.value.code in {"PARSER_PROFILE_CHANGED", "STAGING_CONFLICT"}
    monkeypatch.setattr(
        "video_paper_wiki_research.parser_profile.importlib.metadata.version",
        lambda name: {"docling": "0.0.1", "docling-core": "0.0.1"}[name],
    )
    with open_research_session("s2") as session:
        with pytest.raises(Exception) as exc2:
            create_profile(session, models)
        assert exc2.value.code == "PARSER_RUNTIME_INCOMPATIBLE"
