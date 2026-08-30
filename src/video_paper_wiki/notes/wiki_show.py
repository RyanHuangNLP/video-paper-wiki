"""Load one top-level wiki/<id>.md. Read-only. No network."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PAPER_LINK = re.compile(
    r"\[([^\]]+)\]\(\.\./papers/([^/\s)]+)\.md\)(?: \((\d{4})\))?"
)


def load_topic(root: Path, topic_id: str) -> dict[str, Any] | None:
    """Return parsed wiki/<topic_id>.md, or None if missing or unsafe."""
    wanted = str(topic_id)
    if not wanted or "/" in wanted or "\\" in wanted or "." in wanted or wanted == "..":
        return None
    path = root / "wiki" / f"{wanted}.md"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {
            "id": wanted,
            "heading_zh": "",
            "blurb_zh": "",
            "papers": [],
        }
    return _parse_topic(wanted, text)


def _parse_topic(topic_id: str, text: str) -> dict[str, Any]:
    heading_zh = ""
    rest = text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            heading_zh = line[2:].strip()
            rest = "\n".join(lines[i + 1 :])
            break
    first = _PAPER_LINK.search(rest)
    if first is None:
        blurb_zh = rest.strip()
        papers: list[dict[str, Any]] = []
    else:
        blurb_zh = rest[: first.start()].strip()
        papers = []
        for match in _PAPER_LINK.finditer(rest):
            year_raw = match.group(3)
            papers.append(
                {
                    "paper_id": match.group(2),
                    "title": match.group(1),
                    "year": int(year_raw) if year_raw is not None else None,
                }
            )
    return {
        "id": topic_id,
        "heading_zh": heading_zh,
        "blurb_zh": blurb_zh,
        "papers": papers,
    }
