from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "dependencies" / "vpkb-000-upstream.json"
PINNED_DOCLING = "2.117.0"
PINNED_COMMIT = "9f8c1199047eac2c3828496279fbb7ba9540b90b"


def test_docling_is_optional_not_default() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert "jsonschema>=4.23" in deps
    assert "pypdf>=5.0" in deps
    assert all("docling" not in item for item in deps)
    extras = data["project"]["optional-dependencies"]
    assert extras["docling"] == ["docling==2.117.0"]
    assert data["tool"]["uv"]["default-groups"] == ["dev"]
    assert "docling" not in data["tool"]["uv"]["default-groups"]
    assert "docling" not in data.get("dependency-groups", {})
    wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["force-include"]["docs/seed"] == "video_paper_wiki/seed"
    assert wheel["force-include"]["schemas"] == "video_paper_wiki/schemas"


def test_uv_lock_pins_docling_version() -> None:
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert PINNED_DOCLING in lock
    assert 'name = "docling"\nversion = "2.117.0"' in lock


def test_gitmodules_does_not_auto_update() -> None:
    text = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert "vendor/claude-obsidian" in text
    assert "https://github.com/AgriciDaniel/claude-obsidian" in text
    assert "update = none" in text


def test_gitlink_is_pinned_commit() -> None:
    result = subprocess.run(
        ["git", "ls-files", "-s", "vendor/claude-obsidian"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    line = result.stdout.strip()
    assert line.startswith("160000 ")
    assert PINNED_COMMIT in line


def test_upstream_manifest_marks_parser_model_not_fetched() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["schema"] == "vpkb-000-upstream-manifest.v1"
    pins = {item["name"]: item for item in payload["pins"]}

    docling = pins["docling"]
    assert docling["kind"] == "pypi"
    assert docling["version"] == PINNED_DOCLING
    assert docling["license"] == "MIT"
    assert docling["source_url"] == "https://pypi.org/project/docling/2.117.0/"
    assert docling["status"] == "pinned"
    assert docling["parser_model"] == {"status": "not-fetched"}

    claude = pins["claude-obsidian"]
    assert claude["kind"] == "git-submodule"
    assert claude["path"] == "vendor/claude-obsidian"
    assert claude["tag"] == "v2.1.1"
    assert claude["commit"] == PINNED_COMMIT
    assert claude["license"] == "MIT"
    assert claude["source_url"] == "https://github.com/AgriciDaniel/claude-obsidian"
    assert claude["status"] == "pinned"

    dumped = json.dumps(payload)
    assert PINNED_DOCLING in dumped
    assert PINNED_COMMIT in dumped
    assert "not-fetched" in dumped
    assert "verified" not in dumped.lower()


def test_no_parser_model_files_or_cancelled_receipts() -> None:
    forbidden_suffixes = (".safetensors", ".onnx", ".pt", ".pth", ".bin", ".ckpt")
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for path in tracked:
        lower = path.lower()
        assert not lower.endswith(forbidden_suffixes)
        assert "parser-model" not in lower
        assert not path.startswith("artifacts/verification/VPKB-000/upstream/")
