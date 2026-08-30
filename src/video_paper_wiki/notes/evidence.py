"""Frozen evidence-status line for vault paper notes. No network."""

from __future__ import annotations

import json
from pathlib import Path

_SEED_RELATIVE = Path("docs") / "seed" / "engine-mvp.json"
_HEADING = "证据状态"
_SENTENCE = "provisional"


def _resolve_seed_path() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _SEED_RELATIVE
        if candidate.is_file():
            return candidate
    cwd_candidate = Path.cwd() / _SEED_RELATIVE
    if cwd_candidate.is_file():
        return cwd_candidate
    return None


def catalog_paper_ids() -> set[str]:
    path = _resolve_seed_path()
    if path is None:
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    papers = payload.get("papers") if isinstance(payload, dict) else None
    if not isinstance(papers, list):
        return set()
    ids: set[str] = set()
    for item in papers:
        if not isinstance(item, dict):
            continue
        raw = item.get("paper_id")
        if isinstance(raw, str) and raw.strip():
            ids.add(raw.strip())
    return ids


def apply_frozen_evidence(text: str, paper_id: str) -> str:
    """Replace ## 证据状态 body with provisional. Other sections stay."""
    wanted = str(paper_id).strip()
    if not wanted or wanted not in catalog_paper_ids():
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
    replaced = lines[: start + 1] + ["", _SENTENCE, ""] + lines[end:]
    out = "\n".join(replaced)
    if not out.endswith("\n"):
        out += "\n"
    return out
