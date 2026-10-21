from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.support import make_checkout, pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
EXECUTOR_SRC = ROOT / "operator" / "parser_executor" / "src"
if str(EXECUTOR_SRC) not in sys.path:
    sys.path.insert(0, str(EXECUTOR_SRC))


PINNED_UPSTREAM = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/vendor/claude-obsidian")


def pinned_upstream() -> Path:
    local = ROOT / "vendor" / "claude-obsidian"
    if (local / ".git").exists() and (local / "scripts" / "claude-obsidian.py").is_file():
        return local
    if (PINNED_UPSTREAM / ".git").exists() and (PINNED_UPSTREAM / "scripts" / "claude-obsidian.py").is_file():
        return PINNED_UPSTREAM
    marker = ROOT / ".git" / "grok-worktree-source"
    if marker.is_file():
        source = Path(marker.read_text(encoding="utf-8").strip()) / "vendor" / "claude-obsidian"
        if (source / ".git").exists() and (source / "scripts" / "claude-obsidian.py").is_file():
            return source
    pytest.fail("pinned claude-obsidian checkout is required")


UPSTREAM = pinned_upstream()

SESSION = "s1"
TEXT = "Synthetic paper claims a method."


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def models(tmp_path: Path) -> Path:
    root = tmp_path / "models"
    nested = root / "layout"
    nested.mkdir(parents=True)
    (nested / "weights.bin").write_bytes(b"synthetic-model-bytes")
    (root / "config.json").write_text('{"synthetic":true}\n', encoding="utf-8")
    return root


def stdout_json(capsys) -> dict:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    return json.loads(lines[0])


def synthetic_document(*, origin: str = "TOPLEFT", text: str = TEXT) -> dict:
    bbox = {"l": 0.0, "t": 0.0, "r": 72.0, "b": 12.0, "coord_origin": origin}
    if origin == "BOTTOMLEFT":
        bbox = {"l": 0.0, "t": 12.0, "r": 72.0, "b": 0.0, "coord_origin": origin}
    return {
        "texts": [
            {
                "self_ref": "#/texts/0",
                "text": text,
                "prov": [{"page_no": 1, "charspan": [0, len(text)], "bbox": bbox}],
            }
        ],
        "tables": [],
        "pictures": [],
        "groups": [],
        "pages": {"1": {"page_no": 1, "size": {"width": 72.0, "height": 72.0}}},
    }


class _FakeDocument:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def export_to_dict(self) -> dict:
        return self._payload


class _FakeResult:
    def __init__(self, payload: dict, status: str = "SUCCESS") -> None:
        self.status = status
        self.document = _FakeDocument(payload)


def fixture_converter(payload: dict | None = None, status: str = "SUCCESS"):
    document = payload if payload is not None else synthetic_document()

    def _convert(*, pdf_bytes: bytes, name: str, artifacts_path: Path):
        del pdf_bytes, name, artifacts_path
        return _FakeResult(document, status=status)

    return _convert


def write_pdf(path: Path, *, pages: int = 1) -> Path:
    path.write_bytes(pdf_bytes(pages=pages))
    return path
