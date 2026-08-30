"""Frozen paper-analysis-draft.v1 document helpers. Schema is read-only."""

from __future__ import annotations

from typing import Any

DRAFT_SCHEMA_NAME = "video-paper-wiki.paper-analysis-draft.v1"

SECTION_SPECS: tuple[tuple[str, str], ...] = (
    ("one_sentence_conclusion", "一句话结论"),
    ("research_question", "研究问题"),
    ("method", "方法"),
    ("representation_architecture", "表示与架构"),
    ("training_data", "训练与数据"),
    ("experiments_results", "实验与结果"),
    ("limitations", "局限"),
    ("code_resources", "代码与资源"),
    ("evidence_status", "证据状态"),
    ("related", "关联"),
)


def paper_id_from_sha256(sha256: str) -> str:
    return sha256.strip().lower()[:12]


def empty_sections() -> list[dict[str, str]]:
    return [{"id": section_id, "heading_zh": heading_zh} for section_id, heading_zh in SECTION_SPECS]


def build_draft(
    *,
    paper_id: str,
    title: str = "",
    title_zh: str = "",
    taxonomy: list[dict[str, Any]] | None = None,
    claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "paper_id": paper_id,
        "title": title,
        "title_zh": title_zh,
        "sections": empty_sections(),
        "taxonomy": [] if taxonomy is None else taxonomy,
        "claims": [] if claims is None else claims,
    }
