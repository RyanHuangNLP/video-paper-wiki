from __future__ import annotations

import json
from pathlib import Path

from tests.support import make_checkout
from video_paper_wiki.commands import doctor, draft, seed
from video_paper_wiki.cli import main

COMMANDS_DIR = Path(__file__).resolve().parents[2] / "src" / "video_paper_wiki" / "commands"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_doctor_empty_health_no_network_no_vault(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = doctor.run()
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "doctor"
    assert payload["data"]["status"] == "ok"
    assert not (tmp_path / "vault").exists()
    assert network_attempts == []


def test_seed_validate_catalog(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = seed.validate()
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "seed.validate"
    assert payload["data"] == {"valid": True, "paper_count": 67}
    assert not (tmp_path / "vault").exists()
    assert network_attempts == []


def test_seed_status_catalog(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = seed.status()
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["command"] == "seed.status"
    assert payload["ok"] is True
    assert payload["data"]["paper_count"] == 67
    assert network_attempts == []


def test_read_only_domain_commands_do_not_require_checkout(tmp_path, monkeypatch, capsys) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    assert main(["doctor"]) == 0
    assert _stdout_json(capsys)["ok"] is True
    assert main(["seed", "validate"]) == 0
    assert _stdout_json(capsys)["data"]["paper_count"] == 67
    monkeypatch.setattr("video_paper_wiki.commands.domain.query", lambda _args: 0)
    monkeypatch.setattr("video_paper_wiki.commands.domain.audit", lambda _args: 0)
    monkeypatch.setattr("video_paper_wiki.commands.domain.index_status", lambda _args: 0)
    monkeypatch.setattr("video_paper_wiki.commands.domain.init_inspect", lambda _args: 0)
    common = ["--vault-root", str(tmp_path / "vault"), "--upstream-root", str(tmp_path / "upstream")]
    assert main(["query", "--json", "--text", "x", "--config", "c.json", *common]) == 0
    assert main(["audit", *common]) == 0
    assert main(["index", "status", "--config", "c.json", *common]) == 0
    assert main(["init", "inspect", *common]) == 0


def test_code_map_prepare_requires_explicit_source_path(capsys) -> None:
    assert main(["code-map", "prepare", "--plan", "p", "--approval-ref", "r"]) == 2
    assert _stdout_json(capsys)["error"]["code"] == "USAGE"


def test_draft_export_missing_flags_are_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = draft.export()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "draft.export"
    assert payload["error"]["code"] == "USAGE"
    assert not (tmp_path / "vault").exists()
    assert network_attempts == []


def test_draft_validate_missing_path_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = draft.validate()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "draft.validate"
    assert payload["error"]["code"] == "USAGE"
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


def test_deleted_commands_are_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    for argv in (["ingest", "put", "--path", "x"], ["ingest", "run", "--path", "x"], ["vault", "list"], ["wiki", "list"]):
        code = main(argv)
        payload = _stdout_json(capsys)
        assert code == 2
        assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []
