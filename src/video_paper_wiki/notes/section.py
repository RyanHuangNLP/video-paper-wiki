"""Read one ## section from papers/<id>.md. Read-only. No network."""

from __future__ import annotations

from pathlib import Path

from video_paper_wiki.notes.encoding import read_utf8
from video_paper_wiki.notes.headings import h2_heading_text, is_atx_h2

_PAPERS = "papers"


def _safe_paper_id(paper_id: str) -> str | None:
    wanted = str(paper_id)
    if not wanted or "/" in wanted or "\\" in wanted or wanted in {".", ".."}:
        return None
    return wanted


def paper_note_path(root: Path, paper_id: str) -> Path | None:
    wanted = _safe_paper_id(paper_id)
    if wanted is None:
        return None
    return root / _PAPERS / f"{wanted}.md"


def read_paper_text(root: Path, paper_id: str) -> str | None:
    """Return papers/<paper_id>.md text, or None if the file is missing.

    Invalid UTF-8 raises InvalidEncoding.
    """
    path = paper_note_path(root, paper_id)
    if path is None or not path.is_file():
        return None
    return read_utf8(path)


def list_headings(text: str) -> list[str]:
    """## heading texts in file order, prefix stripped. Empty if none."""
    headings: list[str] = []
    for line in text.splitlines():
        heading = h2_heading_text(line)
        if heading is not None:
            headings.append(heading)
    return headings


def section_text(text: str, section: str) -> str | None:
    """Body under the first exact ## heading, or None if that heading is absent."""
    wanted = str(section)
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if h2_heading_text(line) == wanted:
            start = index + 1
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if is_atx_h2(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end]).strip()
