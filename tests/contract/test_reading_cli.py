from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.contracts import validate_document


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _run_reading_cli(checkout: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    previous = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not previous else str(SRC) + os.pathsep + previous
    return subprocess.run(
        [sys.executable, "-m", "video_paper_wiki.reading", *argv],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_reading_cli_help_usage_and_refusals(world):
    checkout = world["checkout"]
    help_root = _run_reading_cli(checkout, ["--help"])
    assert help_root.returncode == 0
    help_build = _run_reading_cli(checkout, ["build", "--help"])
    assert help_build.returncode == 0
    for flag in ("--vault-root", "--batch-id", "--paper-id", "--articles-batch"):
        assert flag in help_build.stdout
    assert "--text" not in help_build.stdout
    assert "--upstream-root" not in help_build.stdout
    assert "--work-dir" not in help_build.stdout
    missing = _run_reading_cli(checkout, [])
    assert missing.returncode == 2
    payload = parse_envelope(missing)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    no_batch = _run_reading_cli(checkout, ["build", "--vault-root", "/tmp"])
    assert no_batch.returncode == 2
    assert parse_envelope(no_batch)["error"]["code"] == "USAGE"
    missing_root = _run_reading_cli(checkout, ["build", "--batch-id", "b1"])
    assert missing_root.returncode == 2
    assert parse_envelope(missing_root)["error"]["code"] == "USAGE"
    before = list((checkout / ".work").rglob("*")) if (checkout / ".work").exists() else []
    unsafe = _run_reading_cli(checkout, ["build", "--vault-root", "/nonexistent", "--batch-id", "b1"])
    articles = run_module_cli(checkout, ["articles", "status", "--vault-root", "/nonexistent"])
    assert unsafe.returncode == 2
    assert articles.returncode == 2
    assert parse_envelope(unsafe)["error"]["code"] == parse_envelope(articles)["error"]["code"]
    assert parse_envelope(unsafe)["error"]["code"] == "WORK_PATH_UNSAFE"
    after = list((checkout / ".work").rglob("*")) if (checkout / ".work").exists() else []
    assert after == before
    bad = _run_reading_cli(
        checkout,
        ["build", "--vault-root", "/nonexistent", "--batch-id", "BAD/ID"],
    )
    articles_bad = run_module_cli(
        checkout,
        ["articles", "status", "--vault-root", "/nonexistent", "--batch-id", "BAD/ID"],
    )
    assert bad.returncode == 2
    assert parse_envelope(bad)["error"]["code"] == parse_envelope(articles_bad)["error"]["code"]
    after_bad = list((checkout / ".work").rglob("*")) if (checkout / ".work").exists() else []
    assert after_bad == before
    same = _run_reading_cli(
        checkout,
        [
            "build",
            "--vault-root",
            "/nonexistent",
            "--batch-id",
            "b1",
            "--articles-batch",
            "b1",
        ],
    )
    assert same.returncode == 2
    same_payload = parse_envelope(same)
    assert same_payload["error"]["code"] == "READING_INVALID"
    assert same_payload["error"]["details"]["reason"] == "same_batch"
    after_same = list((checkout / ".work").rglob("*")) if (checkout / ".work").exists() else []
    assert after_same == before
    not_canon = _run_reading_cli(
        checkout,
        [
            "build",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "b1",
            "--paper-id",
            "not-canonical",
        ],
    )
    assert not_canon.returncode == 2
    not_payload = parse_envelope(not_canon)
    assert not_payload["error"]["code"] == "READING_INVALID"
    assert not_payload["error"]["details"]["instance_pointer"] == "/paper_id"
    unknown = "sha256:" + "f" * 64
    _three_chain(world)
    unknown_reading = _run_reading_cli(
        checkout,
        [
            "build",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "unk",
            "--paper-id",
            unknown,
        ],
    )
    unknown_graph = run_module_cli(
        checkout,
        ["graph", "project", "--vault-root", str(world["vault"]), "--paper-id", unknown],
    )
    assert unknown_reading.returncode == 2
    assert parse_envelope(unknown_reading)["error"]["code"] == parse_envelope(unknown_graph)["error"]["code"]
    assert not (checkout / ".work" / "unk" / "reading").exists()


def test_reading_cli_success_replay_and_envelope(world):
    _three_chain(world)
    checkout = world["checkout"]
    vault = str(world["vault"])
    first = _run_reading_cli(
        checkout,
        ["build", "--vault-root", vault, "--batch-id", "cli1"],
    )
    assert first.returncode == 0
    payload = parse_envelope(first)
    assert payload["command"] == "reading.build"
    data = payload["data"]
    assert data["view_kind"] == "obsidian-reading.v1"
    assert data["state"] == "reading_staged"
    n_pages = len(data["pages"])
    assert n_pages == 2 + 1 + 2 + 2 + 1 + data["counts"]["articles"]
    assert data["staging"]["new"] == n_pages + 1
    validate_document(payload, "video-paper-wiki.cli-envelope.v1")
    second = _run_reading_cli(
        checkout,
        ["build", "--vault-root", vault, "--batch-id", "cli1"],
    )
    assert second.returncode == 0
    again = parse_envelope(second)
    assert again["data"]["staging"]["already_staged"] == n_pages + 1
    assert again["data"]["staging"]["new"] == 0
    assert again["data"]["pages"] == payload["data"]["pages"]
    assert again["data"]["batch_id"] == payload["data"]["batch_id"]
    envelope = json.loads(first.stdout)
    assert envelope["ok"] is True
