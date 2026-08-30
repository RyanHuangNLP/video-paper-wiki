"""Replacement YAML for papers/<id>.md copies. Work notes stay unchanged."""

from __future__ import annotations

from typing import Any, Mapping

from video_paper_wiki.notes.architectures import apply_frozen_architecture
from video_paper_wiki.notes.clear_draft import apply_empty_draft_sections
from video_paper_wiki.notes.conclusions import apply_frozen_conclusion
from video_paper_wiki.notes.experiments import apply_frozen_experiments
from video_paper_wiki.notes.links import (
    backlink_catalog_ids,
    related_catalog_papers,
    topics_containing,
)
from video_paper_wiki.notes.markdown import _yaml_scalar, render_paper_sections
from video_paper_wiki.notes.methods import apply_frozen_method
from video_paper_wiki.notes.questions import apply_frozen_question
from video_paper_wiki.notes.training import apply_frozen_training
from video_paper_wiki.parse.title import catalog_arxiv_id_for_paper_id, catalog_title_for_paper_id

_ARXIV_PREFIX = "arxiv-"


def year_from_arxiv_id(arxiv_id: str) -> int | None:
    """YYMM prefix → 2000+YY. Empty or non-digit start → None."""
    value = (arxiv_id or "").strip()
    if len(value) < 2 or not value[:2].isdigit():
        return None
    return 2000 + int(value[:2])


def resolve_arxiv_id(paper_id: str) -> str:
    catalog = catalog_arxiv_id_for_paper_id(paper_id)
    if catalog is not None:
        return catalog
    wanted = str(paper_id).strip()
    if wanted.startswith(_ARXIV_PREFIX):
        rest = wanted[len(_ARXIV_PREFIX) :]
        if rest:
            return rest
    return ""


def topic_ids_for_paper(paper_id: str) -> list[str]:
    return [topic["id"] for topic in topics_containing(paper_id)]


def _yaml_flow_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(values) + "]"


def render_paper_copy_frontmatter(paper_id: str, draft_title: str) -> str:
    catalog_title = catalog_title_for_paper_id(paper_id)
    title = catalog_title if catalog_title is not None else draft_title
    arxiv_id = resolve_arxiv_id(paper_id)
    year = year_from_arxiv_id(arxiv_id)
    lines = [
        "---",
        f"title: {_yaml_scalar(title)}",
        f"paper_id: {_yaml_scalar(paper_id)}",
        f"arxiv_id: {_yaml_scalar(arxiv_id)}",
    ]
    if year is not None:
        lines.append(f"year: {year}")
    lines.append(f"topics: {_yaml_flow_list(topic_ids_for_paper(paper_id))}")
    related_ids = [sibling for sibling, _title in related_catalog_papers(paper_id)]
    lines.append(f"related: {_yaml_flow_list(related_ids)}")
    lines.append(f"backlinks: {_yaml_flow_list(backlink_catalog_ids(paper_id))}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def render_paper_copy_markdown(document: Mapping[str, Any]) -> str:
    """papers/<id>.md YAML + the ten-section body. Caller appends the #30 suffix."""
    paper_id = str(document.get("paper_id", ""))
    raw_title = document.get("title", "")
    draft_title = raw_title if isinstance(raw_title, str) else ("" if raw_title is None else str(raw_title))
    header = render_paper_copy_frontmatter(paper_id, draft_title)
    body = apply_frozen_conclusion(header + "\n" + render_paper_sections(document), paper_id)
    body = apply_empty_draft_sections(body)
    body = apply_frozen_question(body, paper_id)
    body = apply_frozen_method(body, paper_id)
    body = apply_frozen_architecture(body, paper_id)
    body = apply_frozen_training(body, paper_id)
    return apply_frozen_experiments(body, paper_id)
