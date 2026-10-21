"""Frozen one-sentence conclusions for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import apply_h2_sentence
from video_paper_wiki.resources import load_string_map

_CONCLUSIONS_FILE = "engine-mvp-conclusions.json"
_HEADING = "一句话结论"


def load_conclusions() -> dict[str, str] | None:
    return load_string_map(_CONCLUSIONS_FILE, "conclusions")


def apply_frozen_conclusion(text: str, paper_id: str) -> str:
    """Replace ## 一句话结论 body with the frozen sentence. Other sections stay."""
    return apply_h2_sentence(text, paper_id, _HEADING, load_conclusions())
