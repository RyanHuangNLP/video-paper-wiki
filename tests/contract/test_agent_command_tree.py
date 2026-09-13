from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from video_paper_wiki.cli import build_parser, main

from .paths import FIXTURES, ROOT, load_json

TREE = FIXTURES / "agent-safe-command-tree.v1.json"
ENVELOPE = ROOT / "schemas" / "video-paper-wiki.cli-envelope.v1.schema.json"

FORBIDDEN = (
    ["ingest", "put"],
    ["ingest", "run"],
    ["vault"],
    ["vault", "grep"],
    ["vault", "stat"],
    ["vault", "list"],
    ["vault", "show"],
    ["vault", "section"],
    ["vault", "headings"],
    ["vault", "doctor"],
    ["wiki"],
    ["wiki", "show"],
    ["wiki", "list"],
)


def _leaves(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()) -> list[list[str]]:
    subparsers = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if not subparsers:
        return [list(prefix)]
    out: list[list[str]] = []
    for action in subparsers:
        for name, child in action.choices.items():
            out.extend(_leaves(child, prefix + (name,)))
    return out


def _stdout_payload(capsys) -> tuple[dict, str]:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    return payload, captured.err


def _assert_usage(code: int, payload: dict) -> None:
    schema = load_json(ENVELOPE)
    Draft202012Validator(schema).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert "data" not in payload
    assert set(payload) == {"ok", "command", "error"}
    assert set(payload["error"]) == {"code", "message", "details"}


def test_leaf_set_equals_fixture() -> None:
    expected = load_json(TREE)
    actual = _leaves(build_parser())
    assert sorted(actual) == sorted(expected["leaves"])
    assert {tuple(item) for item in actual} == {tuple(item) for item in expected["leaves"]}


def test_forbidden_commands_are_usage(capsys) -> None:
    for argv in FORBIDDEN:
        code = main(argv)
        payload, _err = _stdout_payload(capsys)
        _assert_usage(code, payload)


def test_review_export_vault_flag_is_usage(capsys) -> None:
    code = main(
        [
            "review",
            "export",
            "--draft",
            "draft.json",
            "--batch-id",
            "b1",
            "--vault",
            "/tmp",
        ]
    )
    payload, _err = _stdout_payload(capsys)
    _assert_usage(code, payload)


def test_prepare_work_dir_flag_is_usage(capsys) -> None:
    for family in ("ingest", "code-map"):
        for argv in (
            [
                family,
                "prepare",
                "--sha256",
                "a" * 64,
                "--batch-id",
                "b1",
                "--work-dir",
                "/tmp",
            ],
            [family, "prepare", "--sha256", "a" * 64],
            [family, "prepare", "--approval-hash", "b" * 64],
            [family, "prepare", "--batch-id", "b1"],
            [family, "prepare", "--work-dir", "/tmp"],
        ):
            code = main(argv)
            payload, _err = _stdout_payload(capsys)
            _assert_usage(code, payload)


def test_query_without_json_is_usage(capsys) -> None:
    code = main(["query"])
    payload, _err = _stdout_payload(capsys)
    _assert_usage(code, payload)
    assert payload["command"] == "query"


def test_query_with_json_is_single_envelope(capsys) -> None:
    code = main(["query", "--json"])
    payload, _err = _stdout_payload(capsys)
    schema = load_json(ENVELOPE)
    Draft202012Validator(schema).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["command"] == "query"


def test_query_abbrev_json_is_usage(capsys) -> None:
    code = main(["query", "--j"])
    payload, _err = _stdout_payload(capsys)
    _assert_usage(code, payload)
    assert payload["command"] == "query"
    assert payload["error"]["code"] == "USAGE"


def _walk_parsers(parser: argparse.ArgumentParser) -> list[argparse.ArgumentParser]:
    found = [parser]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                found.extend(_walk_parsers(child))
    return found


def test_allow_abbrev_disabled_on_every_parser() -> None:
    for parser in _walk_parsers(build_parser()):
        assert parser.allow_abbrev is False
