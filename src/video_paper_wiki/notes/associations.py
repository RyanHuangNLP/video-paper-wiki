"""Frozen association sentences for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import apply_h2_sentence
from video_paper_wiki.resources import load_string_map

_ASSOCIATIONS_FILE = "engine-mvp-associations.json"
_HEADING = "关联"


def load_associations() -> dict[str, str] | None:
    return load_string_map(_ASSOCIATIONS_FILE, "associations")


def apply_frozen_associations(text: str, paper_id: str) -> str:
    """Replace ## 关联 body with the frozen sentence. Other sections stay."""
    return apply_h2_sentence(text, paper_id, _HEADING, load_associations())
