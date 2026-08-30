"""Count papers/*.md, wiki/*.md (minus index.md), and year: histogram. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_PAPERS = "papers"
_WIKI = "wiki"
_SKIP_WIKI_INDEX = "index.md"
_YEAR_PREFIX = "year:"


def _md_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.iterdir() if path.is_file() and path.suffix == ".md"
    )


def _opening_frontmatter(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    rest = text[3:]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    else:
        return None
    closer = rest.find("\n---")
    if closer == -1:
        return None
    return rest[:closer]


def year_from_frontmatter(text: str) -> str | None:
    """First parseable `year:` value in the opening YAML block, else None."""
    block = _opening_frontmatter(text)
    if block is None:
        return None
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith(_YEAR_PREFIX):
            continue
        value = stripped[len(_YEAR_PREFIX) :].strip()
        if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
            value = value[1:-1].strip()
        if value.isdigit():
            return value
        return None
    return None


def scan_stat(root: Path) -> dict[str, Any]:
    """Return papers, wiki_pages, and years histogram. Does not create files."""
    papers = _md_files(root / _PAPERS)
    wiki = [path for path in _md_files(root / _WIKI) if path.name != _SKIP_WIKI_INDEX]
    histogram: dict[str, int] = {}
    for path in papers:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        year = year_from_frontmatter(text)
        if year is None:
            continue
        histogram[year] = histogram.get(year, 0) + 1
    years = {key: histogram[key] for key in sorted(histogram, key=int)}
    return {
        "papers": len(papers),
        "wiki_pages": len(wiki),
        "years": years,
    }
