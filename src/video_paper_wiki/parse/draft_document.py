"""Frozen paper-analysis-draft.v1 document helpers. Schema is read-only."""

from __future__ import annotations

import hashlib
import re
from typing import Any

DRAFT_SCHEMA_NAME = "video-paper-wiki.paper-analysis-draft.v1"
PROVISIONAL_CLAIM_SECTION = "one_sentence_conclusion"
EVIDENCE_STATUS_TEXT = "provisional; local pypdf extract"
CLAIM_TEXT_MAX = 500
HEADING_MAX_LEN = 80

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

_NUMBERING_RE = re.compile(r"^\d+(?:\.\d+)*[.)\:]?\s+")
_SENTENCE_CUES_RE = re.compile(
    r"\b(is|are|was|were|been|being|we|this|these|those|that|which|"
    r"have|has|had|using|used|uses)\b",
    re.I,
)
_CODE_LINE_RE = re.compile(
    r"github\.com|huggingface\.co|project\s+page",
    re.I,
)
_OPTIONAL_PREFIX_RE = r"(?:(?:our|proposed)\s+)?"
_HEADING_SMALL_WORDS = frozenset({"and", "or", "of", "the", "a", "an", "for", "in", "on", "with", "to"})
# Related is listed before training/data so "Related Work" is never stolen into data.
_EXACT_HEADINGS: dict[str, str] = {
    "abstract": "one_sentence_conclusion",
    "summary": "one_sentence_conclusion",
    "introduction": "research_question",
    "research question": "research_question",
    "research questions": "research_question",
    "related": "related",
    "related work": "related",
    "method": "method",
    "methods": "method",
    "approach": "method",
    "model": "method",
    "architecture": "representation_architecture",
    "representation": "representation_architecture",
    "tokenizer": "representation_architecture",
    "unet": "representation_architecture",
    "dit": "representation_architecture",
    "training": "training_data",
    "training data": "training_data",
    "dataset": "training_data",
    "datasets": "training_data",
    "data": "training_data",
    "experiment": "experiments_results",
    "experiments": "experiments_results",
    "experimental results": "experiments_results",
    "experimental setup": "experiments_results",
    "results": "experiments_results",
    "evaluation": "experiments_results",
    "benchmark": "experiments_results",
    "benchmarks": "experiments_results",
    "limitation": "limitations",
    "limitations": "limitations",
    "conclusion": "limitations",
    "conclusions": "limitations",
    "局限": "limitations",
    "code": "code_resources",
    "resources": "code_resources",
    "github": "code_resources",
    "project page": "code_resources",
    "code and resources": "code_resources",
}
_HEADING_RULES: tuple[tuple[str, str], ...] = (
    (rf"^{_OPTIONAL_PREFIX_RE}(abstract|summary)\b", "one_sentence_conclusion"),
    (rf"^{_OPTIONAL_PREFIX_RE}(introduction|research\s+questions?)\b", "research_question"),
    (rf"^{_OPTIONAL_PREFIX_RE}related(\s+work)?\b", "related"),
    (rf"^{_OPTIONAL_PREFIX_RE}(methods?|approach|model)\b", "method"),
    (
        rf"^{_OPTIONAL_PREFIX_RE}(architecture|representation|tokenizer|unet|dit)\b",
        "representation_architecture",
    ),
    (rf"^{_OPTIONAL_PREFIX_RE}(training|datasets?|data)\b", "training_data"),
    (
        rf"^{_OPTIONAL_PREFIX_RE}(experiments?|experimental|results?|evaluation|benchmarks?)\b",
        "experiments_results",
    ),
    (rf"^{_OPTIONAL_PREFIX_RE}(limitations?|conclusions?|局限)", "limitations"),
    (rf"^{_OPTIONAL_PREFIX_RE}(code|resources?|github)\b", "code_resources"),
    (rf"^project\s+page\b", "code_resources"),
)
_HEADING_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.I), section) for pattern, section in _HEADING_RULES
)


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


def _clip_claim_text(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= CLAIM_TEXT_MAX:
        return stripped
    return stripped[:CLAIM_TEXT_MAX].rstrip()


def _first_sentence(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    for index, char in enumerate(stripped):
        if char in ".!?" and (index + 1 == len(stripped) or stripped[index + 1].isspace()):
            return stripped[: index + 1].strip()
    return stripped.splitlines()[0].strip()


def _heading_shape(rest: str) -> bool:
    words = rest.split()
    if not words:
        return False
    letters = [char for char in rest if char.isalpha()]
    if letters and all(char.isupper() for char in letters):
        return True
    for word in words:
        bare = word.strip(".:")
        if not bare:
            continue
        if bare.lower() in _HEADING_SMALL_WORDS:
            continue
        if not bare[:1].isupper():
            return False
    return True


def _heading_section(line: str) -> str | None:
    raw = line.strip()
    if not raw or len(raw) > HEADING_MAX_LEN:
        return None
    if "://" in raw:
        return None
    rest = _NUMBERING_RE.sub("", raw, count=1).strip()
    if not rest or len(rest) > HEADING_MAX_LEN:
        return None
    if "." in rest.rstrip("."):
        return None
    words = rest.split()
    if len(words) > 8:
        return None
    key = rest.rstrip(".:").strip().lower()
    exact = _EXACT_HEADINGS.get(key)
    if exact is not None:
        return exact
    shaped = rest.rstrip(".:").strip()
    if not _heading_shape(shaped):
        return None
    if _SENTENCE_CUES_RE.search(shaped):
        return None
    for pattern, section in _HEADING_COMPILED:
        if pattern.search(shaped):
            return section
    return None


def _normalize_pages(
    *,
    body_text: str,
    page: int,
    pages: list[dict[str, Any]] | None,
) -> list[tuple[int, str]]:
    normalized: list[tuple[int, str]] = []
    if isinstance(pages, list):
        for item in pages:
            if not isinstance(item, dict):
                continue
            raw_page = item.get("page", 1)
            try:
                page_no = int(raw_page)
            except (TypeError, ValueError):
                page_no = 1
            if page_no < 1:
                page_no = 1
            text = str(item.get("text") or "")
            if text.strip():
                normalized.append((page_no, text))
    if normalized:
        return normalized
    fallback_page = page if isinstance(page, int) and page >= 1 else 1
    body = str(body_text or "")
    if body.strip():
        return [(fallback_page, body)]
    return []


def _iter_lines(page_texts: list[tuple[int, str]]) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for page_no, text in page_texts:
        for line in str(text).splitlines():
            stripped = line.strip()
            if stripped:
                lines.append((page_no, stripped))
    return lines


def _join_lines(lines: list[tuple[int, str]]) -> str:
    return "\n".join(text for _page, text in lines)


def _make_claim(
    *,
    claim_text: str,
    section: str,
    core: bool,
    page: int,
    artifact_sha256: str,
    artifact_path: str,
) -> dict[str, Any]:
    digest = artifact_sha256.strip().lower()
    page_no = page if isinstance(page, int) and page >= 1 else 1
    return {
        "claim_text": claim_text,
        "section": section,
        "core": core,
        "assessment": "provisional",
        "locators": [
            {
                "kind": "pdf",
                "source_id": paper_id_from_sha256(digest),
                "page": page_no,
                "ref": f"#/page/{page_no}",
                "artifact_path": artifact_path,
                "artifact_sha256": digest,
                "text_sha256": text_sha256(claim_text),
            }
        ],
    }


def claims_from_body(
    *,
    body_text: str,
    artifact_sha256: str,
    artifact_path: str,
    page: int = 1,
    pages: list[dict[str, Any]] | None = None,
    title: str = "",
) -> list[dict[str, Any]]:
    """Build provisional PDF claims from extracted text and optional page map."""

    page_texts = _normalize_pages(body_text=body_text, page=page, pages=pages)
    lines = _iter_lines(page_texts)
    if not lines:
        return []

    segments: list[tuple[str | None, list[tuple[int, str]], int]] = []
    current_section: str | None = None
    current_lines: list[tuple[int, str]] = []
    current_page = lines[0][0]
    for page_no, line in lines:
        mapped = _heading_section(line)
        if mapped is not None:
            segments.append((current_section, current_lines, current_page))
            current_section = mapped
            current_lines = []
            current_page = page_no
            continue
        if not current_lines:
            current_page = page_no
        current_lines.append((page_no, line))
    segments.append((current_section, current_lines, current_page))

    filled: dict[str, tuple[str, int]] = {}
    for section, seglines, start_page in segments:
        if section is None:
            continue
        if section in filled:
            continue
        chunk = _clip_claim_text(_join_lines(seglines))
        if not chunk:
            continue
        if section == "one_sentence_conclusion":
            chunk = _clip_claim_text(_first_sentence(chunk))
            if not chunk:
                continue
        loc_page = seglines[0][0] if seglines else start_page
        filled[section] = (chunk, loc_page)

    if "code_resources" not in filled:
        for page_no, line in lines:
            if _heading_section(line) is not None:
                continue
            if _CODE_LINE_RE.search(line):
                filled["code_resources"] = (_clip_claim_text(line), page_no)
                break

    if "one_sentence_conclusion" not in filled:
        title_norm = str(title or "").strip()
        candidates: list[tuple[int, str]] = []
        for page_no, line in lines:
            if _heading_section(line) is not None:
                continue
            if title_norm and line == title_norm:
                continue
            candidates.append((page_no, line))
        source_lines = candidates if candidates else lines
        sentence = _first_sentence(_join_lines(source_lines))
        if not sentence:
            sentence = _first_sentence(_join_lines(lines))
        if sentence:
            filled["one_sentence_conclusion"] = (
                _clip_claim_text(sentence),
                source_lines[0][0],
            )

    first_extracted_page = page_texts[0][0]
    filled["evidence_status"] = (EVIDENCE_STATUS_TEXT, first_extracted_page)

    claims: list[dict[str, Any]] = []
    for section_id, _heading in SECTION_SPECS:
        if section_id not in filled:
            continue
        claim_text, loc_page = filled[section_id]
        claims.append(
            _make_claim(
                claim_text=claim_text,
                section=section_id,
                core=section_id == "one_sentence_conclusion",
                page=loc_page,
                artifact_sha256=artifact_sha256,
                artifact_path=artifact_path,
            )
        )
    return claims


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
    raw_pages = fields.get("pages")
    pages = raw_pages if isinstance(raw_pages, list) else None
    return claims_from_body(
        body_text=body,
        artifact_sha256=artifact_sha256,
        artifact_path=artifact_path,
        page=page,
        pages=pages,
        title=str(fields.get("title") or ""),
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
