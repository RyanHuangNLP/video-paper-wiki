"""Frozen architecture sentences for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import apply_h2_sentence
from video_paper_wiki.resources import load_string_map

_ARCH_FILE = "engine-mvp-architectures.json"
_HEADING = "表示与架构"


def load_architectures() -> dict[str, str] | None:
    return load_string_map(_ARCH_FILE, "architectures")


def apply_frozen_architecture(text: str, paper_id: str) -> str:
    """Replace ## 表示与架构 body with the frozen sentence. Other sections stay."""
    return apply_h2_sentence(text, paper_id, _HEADING, load_architectures())
