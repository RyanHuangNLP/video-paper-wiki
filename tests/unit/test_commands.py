from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.commands import doctor, draft, seed

COMMANDS_DIR = Path(__file__).resolve().parents[2] / "src" / "video_paper_wiki" / "commands"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_doctor_empty_health_no_network_no_vault(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = doctor.run()
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "doctor"
    assert payload["data"]["status"] == "ok"
    assert not (tmp_path / "vault").exists()
    assert network_attempts == []


def test_seed_validate_empty_stub(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = seed.validate()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "seed.validate"
    assert payload["error"]["code"] == "NOT_IMPLEMENTED"
    assert not (tmp_path / "vault").exists()
    assert network_attempts == []


def test_seed_status_empty_stub(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = seed.status()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "seed.status"
    assert payload["error"]["code"] == "NOT_IMPLEMENTED"
    assert network_attempts == []


def test_draft_export_empty_stub(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = draft.export()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "draft.export"
    assert payload["error"]["code"] == "NOT_IMPLEMENTED"
    assert not (tmp_path / "vault").exists()
    assert network_attempts == []


def test_draft_validate_empty_stub(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = draft.validate()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "draft.validate"
    assert payload["error"]["code"] == "NOT_IMPLEMENTED"
    assert network_attempts == []


def test_command_modules_have_no_network_or_vault_imports() -> None:
    forbidden = (
        "requests",
        "httpx",
        "urllib.request",
        "http.client",
        "aiohttp",
        "vault",
    )
    for path in COMMANDS_DIR.glob("*.py"):
        text = path.read_text()
        for name in forbidden:
            assert name not in text, f"{path.name} contains {name}"
