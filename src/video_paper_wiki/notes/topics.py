"""Write topic wiki pages under an existing notes root. No network, no apply."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.notes.encoding import read_utf8
from video_paper_wiki.parse.title import catalog_title_for_paper_id
from video_paper_wiki.resources import load_seed_json

_TOPICS_FILE = "engine-mvp-topics.json"
_RELATED_FILE = "engine-mvp-topic-related.json"
_TOPICS_HEADING = "## 主题"
_RELATED_HEADING = "## 相关主题"


def _safe_segment(value: str) -> bool:
    if not value or value in {".", ".."}:
        return False
    return "/" not in value and "\\" not in value


def load_topics() -> list[dict[str, Any]] | None:
    payload = load_seed_json(_TOPICS_FILE)
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        return None
    topics: list[dict[str, Any]] = []
    for item in payload["topics"]:
        if not isinstance(item, dict):
            continue
        topic_id = item.get("id")
        heading = item.get("heading_zh")
        paper_ids = item.get("paper_ids")
        if not isinstance(topic_id, str) or not _safe_segment(topic_id.strip()):
            continue
        if not isinstance(heading, str):
            continue
        ids: list[str] = []
        if isinstance(paper_ids, list):
            for paper_id in paper_ids:
                if isinstance(paper_id, str) and paper_id.strip():
                    ids.append(paper_id.strip())
        blurb = item.get("blurb_zh")
        if not isinstance(blurb, str):
            blurb = ""
        topics.append(
            {
                "id": topic_id.strip(),
                "heading_zh": heading,
                "paper_ids": ids,
                "blurb_zh": blurb,
            }
        )
    return topics


def load_topic_related() -> dict[str, list[str]] | None:
    payload = load_seed_json(_RELATED_FILE)
    if not isinstance(payload, dict) or not isinstance(payload.get("related"), dict):
        return None
    related: dict[str, list[str]] = {}
    for raw_id, raw_ids in payload["related"].items():
        if not isinstance(raw_id, str) or not _safe_segment(raw_id.strip()):
            continue
        ids: list[str] = []
        if isinstance(raw_ids, list):
            for item in raw_ids:
                if isinstance(item, str) and _safe_segment(item.strip()):
                    ids.append(item.strip())
        related[raw_id.strip()] = ids
    return related


def _paper_note_exists(root: Path, paper_id: str) -> bool:
    if not _safe_segment(paper_id):
        return False
    return (root / "papers" / f"{paper_id}.md").is_file()


def _related_section_lines(topic_id: str) -> list[str]:
    graph = load_topic_related()
    if not graph:
        return []
    wanted = graph.get(topic_id)
    if not wanted:
        return []
    topics = load_topics()
    if not topics:
        return []
    headings = {topic["id"]: topic["heading_zh"] for topic in topics}
    links: list[str] = []
    for related_id in sorted(dict.fromkeys(wanted)):
        if related_id == topic_id:
            continue
        heading = headings.get(related_id)
        if not heading:
            continue
        links.append(f"[{heading}](./{related_id}.md)")
    if not links:
        return []
    return [_RELATED_HEADING, *links]


def _topic_page_text(
    heading_zh: str,
    paper_ids: list[str],
    root: Path,
    blurb_zh: str = "",
    topic_id: str | None = None,
) -> str:
    # Lazy import: notes.index -> frontmatter -> links -> topics.
    from video_paper_wiki.notes.index import paper_index_year, sort_paper_ids

    lines = [f"# {heading_zh}", ""]
    if blurb_zh:
        lines.append(blurb_zh)
        lines.append("")

    renderable: list[str] = []
    for paper_id in paper_ids:
        title = catalog_title_for_paper_id(paper_id)
        if title is None:
            continue
        if not _paper_note_exists(root, paper_id):
            continue
        renderable.append(paper_id)

    for paper_id in sort_paper_ids(renderable):
        title = catalog_title_for_paper_id(paper_id)
        if title is None:
            continue
        line = f"[{title}](../papers/{paper_id}.md)"
        year = paper_index_year(paper_id)
        if year is not None:
            line = f"{line} ({year})"
        lines.append(line)
    if topic_id:
        related = _related_section_lines(topic_id)
        if related:
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend(related)
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _topic_index_block(topics: list[dict[str, Any]]) -> list[str]:
    lines = [_TOPICS_HEADING]
    for topic in topics:
        lines.append(f"[{topic['heading_zh']}](wiki/{topic['id']}.md)")
    return lines


def _is_topics_heading(line: str) -> bool:
    return line.strip() == _TOPICS_HEADING


def _replace_topics_section(index_text: str, topics: list[dict[str, Any]]) -> str:
    lines = index_text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if _is_topics_heading(line):
            start = i
            break
    block = _topic_index_block(topics)
    if start is None:
        result = list(lines)
        result.extend(block)
    else:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            stripped = lines[j].lstrip()
            if stripped.startswith("## "):
                end = j
                break
        result = lines[:start] + block + lines[end:]
    text = "\n".join(result)
    if not text.endswith("\n"):
        text += "\n"
    return text


def refresh_topic_pages(root: Path) -> None:
    """Write wiki/<id>.md pages and a root-index 主题 section.

    Does not create *root*. Missing topics file skips all wiki writes.
    Never writes wiki/index.md.
    """
    if not root.is_dir():
        return
    topics = load_topics()
    if topics is None:
        return
    wiki_dir = root / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    for topic in topics:
        page = wiki_dir / f"{topic['id']}.md"
        page.write_text(
            _topic_page_text(
                topic["heading_zh"],
                topic["paper_ids"],
                root,
                topic.get("blurb_zh", ""),
                topic["id"],
            ),
            encoding="utf-8",
        )
    index_path = root / "index.md"
    if not index_path.is_file():
        return
    updated = _replace_topics_section(read_utf8(index_path), topics)
    index_path.write_text(updated, encoding="utf-8")
