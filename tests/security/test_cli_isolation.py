from __future__ import annotations

import argparse
import json
import shutil
import sys
import tomllib
from pathlib import Path

import pytest

from video_paper_wiki.cli import build_parser, main

ROOT = Path(__file__).parents[2]


def _project(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _command_paths(parser: argparse.ArgumentParser) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()

    def walk(current: argparse.ArgumentParser, prefix: tuple[str, ...]) -> None:
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    path = (*prefix, name)
                    paths.add(path)
                    walk(child, path)

    walk(parser, ())
    return paths


def test_root_and_operator_projects_are_isolated() -> None:
    root = _project(ROOT / "pyproject.toml")
    assert root["project"]["scripts"] == {"vpwiki": "video_paper_wiki.cli:main"}
    assert "workspace" not in root.get("tool", {}).get("uv", {})
    operator = _project(ROOT / "operator" / "pyproject.toml")
    assert operator["project"]["scripts"] == {"vpwiki-admin": "vpwiki_admin.cli:main"}


def test_agent_command_tree_contains_no_operator_mutations() -> None:
    paths = _command_paths(build_parser())
    assert ("index", "status") in paths
    assert not any("fetch" in path or "apply" in path or "parser-model" in path for path in paths)
    assert ("index", "build") not in paths


@pytest.mark.parametrize("argv", [["fetch"], ["ingest", "apply"]])
def test_forbidden_argv_is_json_usage_rejection(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"


def test_agent_source_has_no_network_client_imports() -> None:
    forbidden = ("requests", "httpx", "urllib.request", "http.client", "aiohttp")
    for source in (ROOT / "src" / "video_paper_wiki").glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert not any(name in text for name in forbidden), source


def test_admin_executable_is_not_in_agent_environment() -> None:
    assert shutil.which("vpwiki-admin") is None
    scripts_dir = Path(sys.executable).parent
    assert (scripts_dir / "vpwiki").is_file()
    assert not (scripts_dir / "vpwiki-admin").exists()
