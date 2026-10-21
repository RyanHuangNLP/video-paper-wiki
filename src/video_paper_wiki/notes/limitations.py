"""Frozen limitation sentences for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import apply_h2_sentence
from video_paper_wiki.resources import load_string_map

_LIMITATIONS_FILE = "engine-mvp-limitations.json"
_HEADING = "局限"


def load_limitations() -> dict[str, str] | None:
    return load_string_map(_LIMITATIONS_FILE, "limitations")


def apply_frozen_limitations(text: str, paper_id: str) -> str:
    """Replace ## 局限 body with the frozen sentence. Other sections stay."""
    return apply_h2_sentence(text, paper_id, _HEADING, load_limitations())
