"""Local writing-context export and citation-checked editable Markdown render.

This is not graph retrieval, not a writing Skill, and not PDF draft.export
paper-analysis JSON. The current conversation model stays outside this module.
"""
from __future__ import annotations

from typing import Any

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_qa import (
    INSUFFICIENT_EVIDENCE,
    _context,
    _require_dict,
    check_model_document,
    inspect_retrieval,
    render_checked,
)

_WRITING_PROMPT = (
    "Write an editable Markdown draft for the topic using only the evidence chunks below. "
    "Cite a used chunk as [@chunk_id] and list the same chunk_id values in citations. "
    "Do not invent papers, pages, chunk ids, or sources. "
    "Do not emit paper-analysis-draft JSON."
)


def _normalize_paper_ids(paper_ids: object) -> list[str]:
    if paper_ids is None:
        return []
    if type(paper_ids) is not list:
        raise ResearchError("LIGHT_WRITING_INVALID", "paper_ids must be a list")
    result: list[str] = []
    seen: set[str] = set()
    for item in paper_ids:
        if type(item) is not str:
            raise ResearchError("LIGHT_WRITING_INVALID", "paper_id must be a string")
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def export_writing_context(topic: str, requirements: str, paper_ids: list[str], retrieval: dict) -> dict:
    if type(topic) is not str:
        raise ResearchError("LIGHT_WRITING_INVALID", "topic must be a string")
    if type(requirements) is not str:
        raise ResearchError("LIGHT_WRITING_INVALID", "requirements must be a string")
    selected = _normalize_paper_ids(paper_ids)
    inspected = inspect_retrieval(retrieval)
    if inspected.get("ok") and selected:
        filtered = [item for item in inspected["evidence"] if item["paper_id"] in set(selected)]
        inspected = dict(inspected)
        inspected["evidence"] = filtered
        if not filtered:
            inspected = {
                "ok": False,
                "status": INSUFFICIENT_EVIDENCE,
                "index_id": inspected.get("index_id"),
                "query": inspected.get("query"),
                "evidence": [],
                "message": "selected papers are not present in this retrieval evidence",
                "markdown": "",
                "citations": [],
            }
    used_ids = selected
    if inspected.get("ok") and not used_ids:
        used_ids = list(dict.fromkeys(item["paper_id"] for item in inspected["evidence"]))
    return _context(
        kind="writing",
        query=topic,
        requirements=requirements,
        paper_ids=used_ids,
        inspected=inspected,
        prompt=_WRITING_PROMPT,
    )


def render_draft(context: dict, draft: dict) -> dict:
    document = _require_dict(draft, "draft")
    if "markdown" not in document and type(document.get("text")) is str:
        document = dict(document)
        document["markdown"] = document["text"]
    checked = check_model_document(_require_dict(context, "context"), document, body_key="markdown")
    rendered = render_checked(checked)
    if rendered.get("ok") is True:
        rendered["kind"] = "editable-markdown"
    return rendered
