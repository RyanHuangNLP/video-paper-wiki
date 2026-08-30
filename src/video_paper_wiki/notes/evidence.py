"""Frozen evidence-status line for paper notes. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import replace_h2_body
from video_paper_wiki.parse.title import catalog_paper_ids as catalog_paper_id_list

_HEADING = "证据状态"
_SENTENCE = "provisional"


def catalog_paper_ids() -> set[str]:
    """paper_id values from engine-mvp.json."""
    return set(catalog_paper_id_list())


def apply_frozen_evidence(text: str, paper_id: str) -> str:
    """Replace ## 证据状态 body with provisional. Other sections stay."""
    wanted = str(paper_id).strip()
    if not wanted or wanted not in catalog_paper_ids():
        return text
    return replace_h2_body(text, _HEADING, ["", _SENTENCE, ""])
