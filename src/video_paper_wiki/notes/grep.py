"""Literal case-insensitive scan of papers/*.md and wiki/*.md. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_SCAN_FOLDERS = ("papers", "wiki")
_SKIP_WIKI_INDEX = "index.md"


def scan_matches(root: Path, query: str) -> list[dict[str, Any]]:
    """Return {path, line, text} hits under papers/ and wiki/, wiki/index.md excluded."""
    needle = query.casefold()
    matches: list[dict[str, Any]] = []
    for folder in _SCAN_FOLDERS:
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix != ".md" or not path.is_file():
                continue
            if folder == "wiki" and path.name == _SKIP_WIKI_INDEX:
                continue
            rel = f"{folder}/{path.name}"
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if needle in line.casefold():
                    matches.append({"path": rel, "line": line_no, "text": line})
    matches.sort(key=lambda item: (item["path"], item["line"]))
    return matches
