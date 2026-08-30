"""Upsert local notes-root index.md. No network, no apply."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from video_paper_wiki.notes.frontmatter import resolve_arxiv_id, year_from_arxiv_id
from video_paper_wiki.parse.title import catalog_title_for_paper_id

_TOPICS_HEADING = "## 主题"
_PAPER_NEEDLE = re.compile(r"\]\(papers/([^)/]+)\.md\)")
_PAPER_LINK = re.compile(r"\[([^\]]*)\]\(papers/([^)/]+)\.md\)")


def _is_h1(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("# ") and not stripped.startswith("## ")


def _link_label(title: str, paper_id: str) -> str:
    label = title.strip() if title else ""
    if not label:
        label = paper_id
    return label.replace("[", "(").replace("]", ")")


def paper_index_year(paper_id: str) -> int | None:
    """Year for an index row: resolve_arxiv_id then year_from_arxiv_id."""
    return year_from_arxiv_id(resolve_arxiv_id(paper_id))


def _sort_key(paper_id: str) -> tuple[int, int, str]:
    year = paper_index_year(paper_id)
    if year is None:
        return (1, 0, paper_id)
    return (0, year, paper_id)


def sort_paper_ids(paper_ids: Iterable[str]) -> list[str]:
    """Year ascending, then paper_id. Undated papers sort after dated ones."""
    return sorted(paper_ids, key=_sort_key)


def format_index_line(paper_id: str, title: str) -> str:
    """`[title](papers/<id>.md) (YYYY)` when year is parseable; else no year."""
    catalog = catalog_title_for_paper_id(paper_id)
    label = _link_label(catalog if catalog is not None else title, paper_id)
    line = f"[{label}](papers/{paper_id}.md)"
    year = paper_index_year(paper_id)
    if year is not None:
        return f"{line} ({year})"
    return line


def _topics_heading_index(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if line.strip() == _TOPICS_HEADING:
            return i
    return None


def _collect_papers(lines: Iterable[str]) -> tuple[set[str], dict[str, str]]:
    paper_ids: set[str] = set()
    titles: dict[str, str] = {}
    for line in lines:
        needle = _PAPER_NEEDLE.search(line)
        if needle is None:
            continue
        paper_id = needle.group(1)
        paper_ids.add(paper_id)
        titled = _PAPER_LINK.search(line)
        if titled is not None and titled.group(1).strip():
            titles[paper_id] = titled.group(1)
    return paper_ids, titles


def upsert_index_entry(root: Path, paper_id: str, title: str) -> Path:
    """Write or replace one papers/ link in root/index.md.

    Does not create *root* itself. Creates index.md inside an existing root.
    Rewrites the paper-list region (after the H1, before ## 主题) sorted by
    year then paper_id. Other paper ids are kept. Does not write wiki/index.md.
    """
    index_path = root / "index.md"
    if index_path.is_file():
        lines = index_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["# Video Paper Wiki"]
    if lines and _is_h1(lines[0]):
        heading = lines[0]
        body = lines[1:]
    else:
        heading = "# Video Paper Wiki"
        body = list(lines)
    topics_at = _topics_heading_index(body)
    if topics_at is None:
        paper_region = body
        tail = []
    else:
        paper_region = body[:topics_at]
        tail = body[topics_at:]
    paper_ids, titles = _collect_papers(paper_region)
    paper_ids.add(paper_id)
    titles[paper_id] = title
    paper_lines = [
        format_index_line(pid, titles.get(pid, pid)) for pid in sort_paper_ids(paper_ids)
    ]
    result = [heading, *paper_lines, *tail]
    text = "\n".join(result)
    if not text.endswith("\n"):
        text += "\n"
    index_path.write_text(text, encoding="utf-8")
    return index_path
