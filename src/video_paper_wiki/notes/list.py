"""List papers/*.md as {paper_id, title, year, topics}. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_PAPERS = "papers"


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


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    return value


def _field_value(block: str, key: str) -> str | None:
    prefix = f"{key}:"
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return None


def _parse_year(raw: str | None) -> int | None:
    if raw is None:
        return None
    value = _unquote(raw.strip())
    if value.isdigit():
        return int(value)
    return None


def _parse_topics(raw: str | None) -> list[str]:
    if raw is None:
        return []
    value = raw.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    for part in inner.split(","):
        item = _unquote(part.strip())
        if item:
            items.append(item)
    return items


def yaml_fields(text: str, stem: str) -> dict[str, Any]:
    """paper_id, title, arxiv_id, year, topics. Missing arxiv_id -> empty string."""
    paper_id = stem
    title = ""
    arxiv_id = ""
    year: int | None = None
    topics: list[str] = []
    block = _opening_frontmatter(text)
    if block is not None:
        raw_id = _field_value(block, "paper_id")
        if raw_id:
            paper_id = _unquote(raw_id) or paper_id
        raw_title = _field_value(block, "title")
        if raw_title is not None:
            title = _unquote(raw_title)
        raw_arxiv = _field_value(block, "arxiv_id")
        if raw_arxiv is not None:
            arxiv_id = _unquote(raw_arxiv)
        year = _parse_year(_field_value(block, "year"))
        topics = _parse_topics(_field_value(block, "topics"))
    return {
        "paper_id": paper_id,
        "title": title,
        "arxiv_id": arxiv_id,
        "year": year,
        "topics": topics,
    }


def _parse_paper(path: Path) -> dict[str, Any]:
    stem = path.stem
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {
            "paper_id": stem,
            "title": "",
            "year": None,
            "topics": [],
        }
    fields = yaml_fields(text, stem)
    return {
        "paper_id": fields["paper_id"],
        "title": fields["title"],
        "year": fields["year"],
        "topics": fields["topics"],
    }


def _sort_key(item: dict[str, Any]) -> tuple[bool, int, str]:
    year = item["year"]
    return (year is None, year if year is not None else 0, item["paper_id"])


def scan_list(root: Path, topic: str | None = None) -> dict[str, Any]:
    """Return papers metadata from top-level papers/*.md. Does not create files."""
    papers = [_parse_paper(path) for path in _md_files(root / _PAPERS)]
    if topic is not None:
        papers = [item for item in papers if topic in item["topics"]]
    papers.sort(key=_sort_key)
    return {"papers": papers}
