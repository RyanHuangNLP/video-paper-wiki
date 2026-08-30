"""Paper-note topic and related-paper trailers. Local only."""

from __future__ import annotations

from typing import Any

from video_paper_wiki.notes.topics import load_topics
from video_paper_wiki.parse.title import catalog_title_for_paper_id

_TOPICS_HEADING = "## 主题"
_RELATED_HEADING = "## 相关论文"


def topics_containing(paper_id: str) -> list[dict[str, Any]]:
    """Topics that list paper_id, in engine-mvp-topics.json order."""
    wanted = str(paper_id).strip()
    if not wanted:
        return []
    topics = load_topics()
    if not topics:
        return []
    return [topic for topic in topics if wanted in topic["paper_ids"]]


def related_catalog_papers(paper_id: str) -> list[tuple[str, str]]:
    """Catalog-titled siblings that share a topic, year-sorted, deduped, no self."""
    from video_paper_wiki.notes.index import sort_paper_ids

    wanted = str(paper_id).strip()
    related: list[tuple[str, str]] = []
    seen: set[str] = set()
    for topic in topics_containing(wanted):
        for sibling in topic["paper_ids"]:
            if sibling == wanted or sibling in seen:
                continue
            seen.add(sibling)
            title = catalog_title_for_paper_id(sibling)
            if title is None:
                continue
            related.append((sibling, title))
    titles = {sibling: title for sibling, title in related}
    return [(sibling, titles[sibling]) for sibling in sort_paper_ids(titles)]


def paper_note_link_suffix(paper_id: str) -> str:
    """Trailing ## 主题 / ## 相关论文 blocks, or empty if paper is in no topic.

    Intended only for the papers/<id>.md copy. Work notes stay the 10-section body.
    """
    from video_paper_wiki.notes.index import paper_index_year

    matching = topics_containing(paper_id)
    if not matching:
        return ""
    lines = ["", _TOPICS_HEADING, ""]
    for topic in matching:
        lines.append(f"[{topic['heading_zh']}](../wiki/{topic['id']}.md)")
    lines.append("")
    lines.append(_RELATED_HEADING)
    lines.append("")
    for sibling_id, title in related_catalog_papers(paper_id):
        line = f"[{title}](./{sibling_id}.md)"
        year = paper_index_year(sibling_id)
        if year is not None:
            line = f"{line} ({year})"
        lines.append(line)
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text
