from __future__ import annotations

import shutil
import sys
import tomllib
from pathlib import Path

from tests.security._source_policy import assert_no_network_imports
from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]


def test_vpwiki_script_exists() -> None:
    script = Path(sys.executable).parent / "vpwiki"
    assert script.is_file()


def test_vpwiki_admin_not_on_path() -> None:
    assert shutil.which("vpwiki-admin") is None
    assert not (Path(sys.executable).parent / "vpwiki-admin").exists()


def test_root_package_has_no_admin_script() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    scripts = data["project"]["scripts"]
    assert "vpwiki-admin" not in scripts
    assert scripts == {"vpwiki": "video_paper_wiki.cli:main"}


def test_operator_is_not_workspace_member() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    uv = data.get("tool", {}).get("uv", {})
    workspace = uv.get("workspace")
    if workspace is not None:
        members = workspace.get("members", [])
        assert "operator" not in members
        assert "operator/" not in members
    operator = tomllib.loads((ROOT / "operator" / "pyproject.toml").read_text())
    assert operator["project"]["scripts"]["vpwiki-admin"] == (
        "video_paper_wiki_operator.cli:main"
    )


def test_forbidden_subcommands_absent() -> None:
    for argv in (
        ["fetch"],
        ["apply"],
        ["index", "build"],
        ["parser-model"],
        ["ingest", "put"],
        ["ingest", "run"],
        ["vault"],
        ["wiki"],
    ):
        code = main(argv)
        assert code == 2


def test_command_tree_registered() -> None:
    assert main(["doctor"]) == 0


def test_agent_source_has_no_network_client_imports() -> None:
    for path in (ROOT / "src" / "video_paper_wiki").rglob("*.py"):
        assert_no_network_imports(path.read_text(encoding="utf-8"), filename=str(path))
