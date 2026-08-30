"""Load one top-level papers/<id>.md. Read-only. No network."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from video_paper_wiki.notes.encoding import read_utf8
from video_paper_wiki.notes.list import (
    _field_value,
    _opening_frontmatter,
    _parse_topics,
    yaml_fields,
)

_PAPERS = "papers"
_RELATED_HEADING = "## 相关论文"
_RELATED_LINK = re.compile(r"\./([^/\s)]+)\.md")


def _yaml_id_list(text: str, key: str) -> list[str] | None:
    """Parsed inline list if the YAML key exists; None if the key is absent."""
    block = _opening_frontmatter(text)
    if block is None:
        return None
    raw = _field_value(block, key)
    if raw is None:
        return None
    return _parse_topics(raw)


def _related_from_yaml(text: str) -> list[str] | None:
    """Parsed related if the YAML key exists; None if the key is absent."""
    return _yaml_id_list(text, "related")


def _related_ids(text: str) -> list[str]:
    idx = text.find(_RELATED_HEADING)
    if idx == -1:
        return []
    body = text[idx + len(_RELATED_HEADING) :]
    newline = body.find("\n")
    if newline == -1:
        body = ""
    else:
        body = body[newline + 1 :]
    next_heading = body.find("\n## ")
    if next_heading != -1:
        body = body[:next_heading]
    related: list[str] = []
    for match in _RELATED_LINK.finditer(body):
        paper_id = match.group(1)
        if paper_id:
            related.append(paper_id)
    return related


def load_paper(root: Path, paper_id: str) -> dict[str, Any] | None:
    """Return YAML + related ids for papers/<paper_id>.md, or None if missing."""
    wanted = str(paper_id)
    if not wanted or "/" in wanted or "\\" in wanted or wanted in {".", ".."}:
        return None
    path = (root / _PAPERS / f"{wanted}.md")
    if not path.is_file():
        return None
    empty = {
        "paper_id": wanted,
        "title": "",
        "arxiv_id": "",
        "year": None,
        "topics": [],
        "related": [],
        "backlinks": [],
    }
    try:
        text = read_utf8(path)
    except OSError:
        return empty
    fields = yaml_fields(text, wanted)
    yaml_related = _related_from_yaml(text)
    related = _related_ids(text) if yaml_related is None else yaml_related
    yaml_backlinks = _yaml_id_list(text, "backlinks")
    backlinks = [] if yaml_backlinks is None else yaml_backlinks
    return {
        "paper_id": fields["paper_id"],
        "title": fields["title"],
        "arxiv_id": fields["arxiv_id"],
        "year": fields["year"],
        "topics": fields["topics"],
        "related": related,
        "backlinks": backlinks,
    }
