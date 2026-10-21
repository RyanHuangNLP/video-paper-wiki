"""Frozen research questions for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import apply_h2_sentence
from video_paper_wiki.resources import load_string_map

_QUESTIONS_FILE = "engine-mvp-questions.json"
_HEADING = "研究问题"


def load_questions() -> dict[str, str] | None:
    return load_string_map(_QUESTIONS_FILE, "questions")


def apply_frozen_question(text: str, paper_id: str) -> str:
    """Replace ## 研究问题 body with the frozen sentence. Other sections stay."""
    return apply_h2_sentence(text, paper_id, _HEADING, load_questions())
