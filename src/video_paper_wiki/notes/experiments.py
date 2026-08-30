"""Frozen experiment sentences for vault paper notes. No network."""

from __future__ import annotations

import json
from pathlib import Path

_EXPERIMENTS_RELATIVE = Path("docs") / "seed" / "engine-mvp-experiments.json"
_HEADING = "实验与结果"


def _resolve_experiments_path() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _EXPERIMENTS_RELATIVE
        if candidate.is_file():
            return candidate
    cwd_candidate = Path.cwd() / _EXPERIMENTS_RELATIVE
    if cwd_candidate.is_file():
        return cwd_candidate
    return None


def load_experiments() -> dict[str, str] | None:
    path = _resolve_experiments_path()
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("experiments"), dict):
        return None
    experiments: dict[str, str] = {}
    for raw_id, raw_text in payload["experiments"].items():
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        experiments[raw_id.strip()] = raw_text.strip()
    return experiments


def apply_frozen_experiments(text: str, paper_id: str) -> str:
    """Replace ## 实验与结果 body with the frozen sentence. Other sections stay."""
    wanted = str(paper_id).strip()
    if not wanted:
        return text
    experiments = load_experiments()
    if not experiments:
        return text
    sentence = experiments.get(wanted)
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
