"""Frozen experiment sentences for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import apply_h2_sentence
from video_paper_wiki.resources import load_string_map

_EXPERIMENTS_FILE = "engine-mvp-experiments.json"
_HEADING = "实验与结果"


def load_experiments() -> dict[str, str] | None:
    return load_string_map(_EXPERIMENTS_FILE, "experiments")


def apply_frozen_experiments(text: str, paper_id: str) -> str:
    """Replace ## 实验与结果 body with the frozen sentence. Other sections stay."""
    return apply_h2_sentence(text, paper_id, _HEADING, load_experiments())
