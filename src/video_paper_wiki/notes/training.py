"""Frozen training sentences for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import apply_h2_sentence
from video_paper_wiki.resources import load_string_map

_TRAINING_FILE = "engine-mvp-training.json"
_HEADING = "训练与数据"


def load_training() -> dict[str, str] | None:
    return load_string_map(_TRAINING_FILE, "training")


def apply_frozen_training(text: str, paper_id: str) -> str:
    """Replace ## 训练与数据 body with the frozen sentence. Other sections stay."""
    return apply_h2_sentence(text, paper_id, _HEADING, load_training())
