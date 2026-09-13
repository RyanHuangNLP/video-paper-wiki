"""Contract tests for code-evidence CLI leaves using the worktree module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.code_proof_public_fixture import (
    JSON_BODY,
    OUTPUT_LIMITS,
    SRC_BODY,
    default_files,
    dump_json,
    make_checkout,
    make_repo,
    nested_json_object,
    observe_norm_doc,
    observe_raw_doc,
    parse_envelope,
    request_doc,
    run_module_cli,
    seal,
    write_bundle,
    write_bytes,
)
from video_paper_wiki.code_proof_io import open_code_session
from video_paper_wiki.cli import build_parser, main


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = make_checkout(tmp_path / "co")
    monkeypatch.chdir(root)
    return root


def test_cli_five_leaf_flow_via_module(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    write_bytes(
        checkout / "request.json",
        dump_json(request_doc(repo, [
            {
                "path": "config.json",
                "roles": ["configuration"],
                "allow_executable_source": False,
            },
            {
                "path": "src.py",
                "roles": ["implementation"],
                "allow_executable_source": False,
            },
        ])),
    )
    req_proc = run_module_cli(
        checkout,
        ["code-evidence", "request", "--input", "request.json", "--batch-id", "cli1"],
    )
    req = parse_envelope(req_proc)
    assert req_proc.returncode == 0
    assert req["ok"] is True
    assert req["command"] == "code-evidence.request"
    write_bundle(checkout, ".work/raw", repo, req["data"]["request"])
    write_bytes(checkout / "observe.json", dump_json(observe_raw_doc(repo)))
    obs_proc = run_module_cli(
        checkout,
        [
            "code-evidence",
            "observe",
            "--input",
            "observe.json",
            "--bundle-dir",
            ".work/raw",
            "--batch-id",
            "cli1",
        ],
    )
    obs = parse_envelope(obs_proc)
    assert obs_proc.returncode == 0
    assert obs["command"] == "code-evidence.observe"
    assert obs["data"]["status"]["state"] == "observed"
    st_proc = run_module_cli(
        checkout, ["code-evidence", "status", "--batch-id", "cli1"]
    )
    st = parse_envelope(st_proc)
    assert st_proc.returncode == 0
    assert st["command"] == "code-evidence.status"
    assert st["data"]["state"] == "observed"
    cfg_proc = run_module_cli(
        checkout,
        [
            "code-evidence",
            "config",
            "--path",
            "config.json",
            "--format",
            "json",
            "--batch-id",
            "cli1",
        ],
    )
    cfg = parse_envelope(cfg_proc)
    assert cfg_proc.returncode == 0
    assert cfg["command"] == "code-evidence.config"
    hand_proc = run_module_cli(
        checkout, ["code-evidence", "handoff", "--batch-id", "cli1"]
    )
    hand = parse_envelope(hand_proc)
    assert hand_proc.returncode == 0
    assert hand["command"] == "code-evidence.handoff"
    assert [row["path"] for row in hand["data"]["handoffs"]] == [
        "config.json",
        "src.py",
    ]


def test_cli_normalized_and_repeat(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    write_bytes(checkout / "request.json", dump_json(request_doc(repo, [
        {
            "path": "config.json",
            "roles": ["configuration"],
            "allow_executable_source": False,
        },
        {
            "path": "src.py",
            "roles": ["implementation"],
            "allow_executable_source": False,
        },
    ])))
    req_proc = run_module_cli(
        checkout,
        ["code-evidence", "request", "--input", "request.json", "--batch-id", "n1"],
    )
    assert req_proc.returncode == 0
    texts = {
        "config.json": JSON_BODY.decode("utf-8"),
        "src.py": SRC_BODY.decode("utf-8"),
    }
    write_bytes(checkout / "observe.json", dump_json(observe_norm_doc(repo, texts)))
    obs_proc = run_module_cli(
        checkout,
        ["code-evidence", "observe", "--input", "observe.json", "--batch-id", "n1"],
    )
    obs = parse_envelope(obs_proc)
    assert obs_proc.returncode == 0
    assert obs["data"]["status"]["eligibility"]["source_handoff_eligible"] is False
    again = run_module_cli(
        checkout,
        ["code-evidence", "request", "--input", "request.json", "--batch-id", "n1"],
    )
    payload = parse_envelope(again)
    assert again.returncode == 0
    assert payload["data"]["already_staged"] is True


def test_cli_status_empty_and_legacy_tree(checkout: Path, capsys) -> None:
    proc = run_module_cli(checkout, ["code-evidence", "status", "--batch-id", "none"])
    payload = parse_envelope(proc)
    assert proc.returncode == 0
    assert payload["data"]["state"] == "empty"
    assert not (checkout / ".work").exists()
    leaves = []
    parser = build_parser()
    for action in parser._actions:
        if getattr(action, "choices", None) and "code-map" in action.choices:
            leaves.append("code-map")
        if getattr(action, "choices", None) and "code-evidence" in action.choices:
            leaves.append("code-evidence")
    assert "code-map" in leaves
    assert "code-evidence" in leaves
    code = main(["code-map", "plan"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"


def test_cli_help_mentions_recovery() -> None:
    import argparse

    parser = build_parser()
    parent = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction) and "code-evidence" in action.choices:
            parent = action.choices["code-evidence"]
            break
    assert parent is not None
    combined = []
    for action in parent._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                combined.append(child.format_help())
    text = "\n".join(combined)
    assert ".work/<batch-id>/code-evidence-v1/" in text
    assert "resume" in text.lower() or "Repeat" in text


def test_cli_config_non_ascii_path_envelope(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    write_bytes(
        checkout / "request.json",
        dump_json(request_doc(repo, [
            {
                "path": "config.json",
                "roles": ["configuration"],
                "allow_executable_source": False,
            },
            {
                "path": "src.py",
                "roles": ["implementation"],
                "allow_executable_source": False,
            },
        ])),
    )
    req_proc = run_module_cli(
        checkout,
        ["code-evidence", "request", "--input", "request.json", "--batch-id", "cli-ua"],
    )
    req = parse_envelope(req_proc)
    assert req_proc.returncode == 0
    write_bundle(checkout, ".work/raw-ua", repo, req["data"]["request"])
    write_bytes(checkout / "observe.json", dump_json(observe_raw_doc(repo)))
    obs_proc = run_module_cli(
        checkout,
        [
            "code-evidence",
            "observe",
            "--input",
            "observe.json",
            "--bundle-dir",
            ".work/raw-ua",
            "--batch-id",
            "cli-ua",
        ],
    )
    assert obs_proc.returncode == 0
    proc = run_module_cli(
        checkout,
        [
            "code-evidence",
            "config",
            "--path",
            "配置.json",
            "--format",
            "json",
            "--batch-id",
            "cli-ua",
        ],
    )
    payload = parse_envelope(proc)
    assert proc.returncode == 2
    assert "UnicodeEncodeError" not in proc.stderr
    assert payload["ok"] is False
    assert payload["command"] == "code-evidence.config"
    assert payload["error"]["code"] == "CODE_PROOF_DOCUMENT_INVALID"
    assert payload["error"]["details"]["reason"] == "path"


def test_cli_leading_whitespace_and_depth(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    raw = dump_json(request_doc(repo, [
        {
            "path": "config.json",
            "roles": ["configuration"],
            "allow_executable_source": False,
        },
        {
            "path": "src.py",
            "roles": ["implementation"],
            "allow_executable_source": False,
        },
    ]))
    write_bytes(checkout / "ws.json", b"\n  " + raw)
    proc = run_module_cli(
        checkout,
        ["code-evidence", "request", "--input", "ws.json", "--batch-id", "cli-ws"],
    )
    payload = parse_envelope(proc)
    assert proc.returncode == 0
    assert payload["ok"] is True
    write_bytes(checkout / "deep.json", nested_json_object(80))
    deep = run_module_cli(
        checkout,
        ["code-evidence", "request", "--input", "deep.json", "--batch-id", "cli-deep"],
    )
    deep_payload = parse_envelope(deep)
    assert deep.returncode == 2
    assert "RecursionError" not in deep.stderr
    assert deep_payload["ok"] is False
    assert deep_payload["error"]["code"] == "CODE_PROOF_JSON_INVALID"
    assert deep_payload["error"]["details"]["reason"] == "depth"


def test_cli_orphan_intent_request_refuses(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    write_bytes(checkout / "request.json", dump_json(request_doc(repo, [
        {
            "path": "config.json",
            "roles": ["configuration"],
            "allow_executable_source": False,
        },
        {
            "path": "src.py",
            "roles": ["implementation"],
            "allow_executable_source": False,
        },
    ])))
    with open_code_session(batch_id="cli-orphan") as session:
        session.set_output_limits(dict(OUTPUT_LIMITS))
        session.install(
            "intent.json",
            seal(
                "code-acquisition-intent",
                {
                    "request": {
                        "id": "ce1:code-proof-request:" + "a" * 64,
                        "sha256": "b" * 64,
                    },
                    "mode": "git_objects",
                    "acquisition": observe_raw_doc(repo),
                    "bundle": None,
                },
            ),
        )
    ns = checkout / ".work" / "cli-orphan" / "code-evidence-v1"
    original = (ns / "intent.json").read_bytes()
    proc = run_module_cli(
        checkout,
        [
            "code-evidence",
            "request",
            "--input",
            "request.json",
            "--batch-id",
            "cli-orphan",
        ],
    )
    payload = parse_envelope(proc)
    assert proc.returncode == 2
    assert payload["error"]["code"] == "CODE_PROOF_STATE_INVALID"
    assert payload["error"]["details"]["reason"] == "missing_dependency"
    assert not (ns / "request.json").exists()
    assert (ns / "intent.json").read_bytes() == original
