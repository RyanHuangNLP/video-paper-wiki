"""Frozen method sentences for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import apply_h2_sentence
from video_paper_wiki.resources import load_string_map

_METHODS_FILE = "engine-mvp-methods.json"
_HEADING = "方法"


def load_methods() -> dict[str, str] | None:
    return load_string_map(_METHODS_FILE, "methods")


def apply_frozen_method(text: str, paper_id: str) -> str:
    """Replace ## 方法 body with the frozen sentence. Other sections stay."""
    return apply_h2_sentence(text, paper_id, _HEADING, load_methods())
