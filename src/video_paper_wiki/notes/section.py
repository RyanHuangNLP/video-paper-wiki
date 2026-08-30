"""Read one ## section from papers/<id>.md. Read-only. No network."""

from __future__ import annotations

from pathlib import Path

_PAPERS = "papers"


def _safe_paper_id(paper_id: str) -> str | None:
    wanted = str(paper_id)
    if not wanted or "/" in wanted or "\\" in wanted or wanted in {".", ".."}:
        return None
    return wanted


def read_paper_text(root: Path, paper_id: str) -> str | None:
    """Return papers/<paper_id>.md text, or None if the file is missing."""
    wanted = _safe_paper_id(paper_id)
    if wanted is None:
        return None
    path = root / _PAPERS / f"{wanted}.md"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _is_heading(line: str) -> bool:
    return line.startswith("##")


def _heading_text(line: str) -> str:
    return line[2:].strip()


def section_text(text: str, section: str) -> str | None:
    """Body under the first exact ## heading, or None if that heading is absent."""
    wanted = str(section)
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if _is_heading(line) and _heading_text(line) == wanted:
            start = index + 1
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if _is_heading(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end]).strip()
