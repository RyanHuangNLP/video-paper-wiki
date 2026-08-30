"""Read-only YAML key check for top-level papers/*.md. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.notes.list import _field_value, _opening_frontmatter
from video_paper_wiki.notes.stat import _md_files

_PAPERS = "papers"
_WIKI = "wiki"
_SKIP_WIKI_INDEX = "index.md"
_REQUIRED = ("title", "paper_id", "year", "topics", "related", "backlinks")


def _missing_keys(text: str) -> list[str]:
    block = _opening_frontmatter(text)
    if block is None:
        return list(_REQUIRED)
    return [key for key in _REQUIRED if _field_value(block, key) is None]


def scan_doctor(root: Path) -> dict[str, Any]:
    """Count top-level papers/wiki pages and list papers missing YAML keys."""
    papers = _md_files(root / _PAPERS)
    wiki = [path for path in _md_files(root / _WIKI) if path.name != _SKIP_WIKI_INDEX]
    missing_yaml: list[dict[str, Any]] = []
    for path in papers:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            missing_yaml.append({"paper_id": path.stem, "fields": list(_REQUIRED)})
            continue
        fields = _missing_keys(text)
        if fields:
            missing_yaml.append({"paper_id": path.stem, "fields": fields})
    return {
        "papers": len(papers),
        "wiki_pages": len(wiki),
        "missing_yaml": missing_yaml,
    }
