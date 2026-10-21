"""Empty the ten frozen H2 bodies on paper copies. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import replace_h2_body
from video_paper_wiki.parse.draft_document import SECTION_SPECS

_CLEAR_HEADINGS = tuple(heading for _section_id, heading in SECTION_SPECS)


def apply_empty_draft_sections(text: str) -> str:
    """Keep the ten frozen ## headings; replace each body with one blank line."""
    out = text
    for heading in _CLEAR_HEADINGS:
        out = replace_h2_body(out, heading, [""])
    if not out.endswith("\n"):
        out += "\n"
    return out
