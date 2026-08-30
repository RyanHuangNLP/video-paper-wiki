"""Frozen architecture sentences for vault paper notes. No network."""

from __future__ import annotations

import json
from pathlib import Path

_ARCH_RELATIVE = Path("docs") / "seed" / "engine-mvp-architectures.json"
_HEADING = "表示与架构"


def _resolve_architectures_path() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _ARCH_RELATIVE
        if candidate.is_file():
            return candidate
    cwd_candidate = Path.cwd() / _ARCH_RELATIVE
    if cwd_candidate.is_file():
        return cwd_candidate
    return None


def load_architectures() -> dict[str, str] | None:
    path = _resolve_architectures_path()
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("architectures"), dict):
        return None
    architectures: dict[str, str] = {}
    for raw_id, raw_text in payload["architectures"].items():
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        architectures[raw_id.strip()] = raw_text.strip()
    return architectures


def apply_frozen_architecture(text: str, paper_id: str) -> str:
    """Replace ## 表示与架构 body with the frozen sentence. Other sections stay."""
    wanted = str(paper_id).strip()
    if not wanted:
        return text
    architectures = load_architectures()
    if not architectures:
        return text
    sentence = architectures.get(wanted)
    if not sentence:
        return text
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("##") and line[2:].strip() == _HEADING:
            start = index
            break
    if start is None:
        return text
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("##"):
            end = index
            break
    replaced = lines[: start + 1] + ["", sentence, ""] + lines[end:]
    out = "\n".join(replaced)
    if not out.endswith("\n"):
        out += "\n"
    return out
