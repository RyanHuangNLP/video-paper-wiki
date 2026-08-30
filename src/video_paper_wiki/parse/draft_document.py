"""Frozen paper-analysis-draft.v1 document helpers. Schema is read-only."""

from __future__ import annotations

import hashlib
from typing import Any

DRAFT_SCHEMA_NAME = "video-paper-wiki.paper-analysis-draft.v1"
PROVISIONAL_CLAIM_SECTION = "one_sentence_conclusion"

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

SECTION_IDS: tuple[str, ...] = tuple(section_id for section_id, _heading in SECTION_SPECS)


def paper_id_from_sha256(sha256: str) -> str:
    return sha256.strip().lower()[:12]


class InvalidPaperId(ValueError):
    """Raised when an explicit paper_id is empty or not a safe path segment."""

    def __init__(self, paper_id: str) -> None:
        super().__init__("paper_id is empty or not a safe path segment")
        self.paper_id = paper_id


def validate_paper_id(paper_id: str) -> str:
    raw = str(paper_id)
    value = raw.strip()
    if not value or "/" in value or "\\" in value or ".." in value:
        raise InvalidPaperId(raw)
    return value


def resolve_paper_id(explicit: str | None, sha256: str) -> str:
    if explicit is None:
        return paper_id_from_sha256(sha256)
    return validate_paper_id(explicit)


def empty_sections() -> list[dict[str, str]]:
    return [{"id": section_id, "heading_zh": heading_zh} for section_id, heading_zh in SECTION_SPECS]


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def claims_from_body(
    *,
    body_text: str,
    artifact_sha256: str,
    artifact_path: str,
    page: int = 1,
) -> list[dict[str, Any]]:
    """Build provisional PDF claims when extractable body text exists."""

    first = ""
    for line in str(body_text).splitlines():
        stripped = line.strip()
        if stripped:
            first = stripped
            break
    if not first:
        first = str(body_text).strip()
    if not first:
        return []
    page_no = page if isinstance(page, int) and page >= 1 else 1
    digest = artifact_sha256.strip().lower()
    return [
        {
            "claim_text": first,
            "section": PROVISIONAL_CLAIM_SECTION,
            "core": True,
            "assessment": "provisional",
            "locators": [
                {
                    "kind": "pdf",
                    "source_id": paper_id_from_sha256(digest),
                    "page": page_no,
                    "ref": f"#/page/{page_no}",
                    "artifact_path": artifact_path,
                    "artifact_sha256": digest,
                    "text_sha256": text_sha256(first),
                }
            ],
        }
    ]


def claims_from_parse_fields(
    fields: dict[str, Any],
    *,
    artifact_sha256: str,
    artifact_path: str,
) -> list[dict[str, Any]]:
    existing = fields.get("claims")
    if isinstance(existing, list) and existing:
        return existing
    body = str(fields.get("body_text") or "")
    raw_page = fields.get("page", 1)
    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = 1
    return claims_from_body(
        body_text=body,
        artifact_sha256=artifact_sha256,
        artifact_path=artifact_path,
        page=page,
    )


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
