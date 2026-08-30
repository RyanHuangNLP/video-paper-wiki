"""Load one top-level papers/<id>.md. Read-only. No network."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from video_paper_wiki.notes.list import yaml_fields

_PAPERS = "papers"
_RELATED_HEADING = "## 相关论文"
_RELATED_LINK = re.compile(r"\./([^/\s)]+)\.md")


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
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {
            "paper_id": wanted,
            "title": "",
            "arxiv_id": "",
            "year": None,
            "topics": [],
            "related": [],
        }
    fields = yaml_fields(text, wanted)
    return {
        "paper_id": fields["paper_id"],
        "title": fields["title"],
        "arxiv_id": fields["arxiv_id"],
        "year": fields["year"],
        "topics": fields["topics"],
        "related": _related_ids(text),
    }
