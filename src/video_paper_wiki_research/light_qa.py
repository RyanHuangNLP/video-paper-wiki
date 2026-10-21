"""Local Q&A context export and citation-checked Markdown render.

The current conversation model stays outside this module. Callers export a
bounded context, obtain a model document themselves, then import it here.
Citation checks jointly match identity fields to one evidence item; they are
not a factual-correctness review. No model service, API key, or network
client is created.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any

from video_paper_wiki_research.contracts import ResearchError

OK = "OK"
NO_RESULTS = "NO_RESULTS"
INDEX_STALE = "INDEX_STALE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
INVALID_CITATION = "INVALID_CITATION"
CITATION_MISMATCH = "CITATION_MISMATCH"
CITATION_CROSS = "CITATION_CROSS"
CONTEXT_SCHEMA = "video-paper-wiki.light-context.v1"
EVIDENCE_FIELDS = (
    "chunk_id",
    "paper_id",
    "title",
    "source_sha256",
    "page",
    "markdown_path",
    "markdown_sha256",
    "text_start",
    "text_end",
    "text_sha256",
    "text",
    "score",
)
OPTIONAL_CITE_FIELDS = (
    "paper_id",
    "title",
    "source_sha256",
    "page",
    "markdown_path",
    "markdown_sha256",
    "text_start",
    "text_end",
    "text_sha256",
    "text",
    "score",
)
_CITE_MARK = re.compile(r"\[@([^\]\s]+)\]")
_SUCCESS_MESSAGE = (
    "Citations jointly match the provided evidence items. "
    "This is a structural citation check, not a factual-correctness review."
)
_QA_PROMPT = (
    "Answer the question using only the evidence chunks below. "
    "Cite a used chunk as [@chunk_id] and list the same chunk_id values in citations. "
    "Do not invent papers, pages, chunk ids, or sources. "
    "Do not add facts that are not in the evidence text."
)


def _fail(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "status": status,
        "message": message,
        "markdown": "",
        "citations": [],
    }
    payload.update(extra)
    return payload


def _require_dict(value: object, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ResearchError("LIGHT_QA_INVALID", f"{name} must be an object")
    return value


def _copy_evidence_item(item: object) -> dict[str, Any]:
    if type(item) is not dict:
        raise ResearchError("LIGHT_QA_INVALID", "evidence item must be an object")
    missing = [key for key in EVIDENCE_FIELDS if key not in item]
    if missing:
        raise ResearchError("LIGHT_QA_INVALID", "evidence item is missing frozen fields", {"missing": missing})
    row = {key: copy.deepcopy(item[key]) for key in EVIDENCE_FIELDS}
    if type(row["chunk_id"]) is not str or not row["chunk_id"]:
        raise ResearchError("LIGHT_QA_INVALID", "chunk_id must be a nonempty string")
    if type(row["paper_id"]) is not str or not row["paper_id"]:
        raise ResearchError("LIGHT_QA_INVALID", "paper_id must be a nonempty string")
    if type(row["title"]) is not str:
        raise ResearchError("LIGHT_QA_INVALID", "title must be a string")
    if type(row["page"]) is not int or type(row["page"]) is bool or row["page"] < 1:
        raise ResearchError("LIGHT_QA_INVALID", "page must be a 1-based integer")
    if type(row["text"]) is not str:
        raise ResearchError("LIGHT_QA_INVALID", "text must be a string")
    if type(row["score"]) not in (int, float) or type(row["score"]) is bool or not math.isfinite(row["score"]):
        raise ResearchError("LIGHT_QA_INVALID", "score must be a finite number")
    for key in ("source_sha256", "markdown_sha256", "text_sha256"):
        value = row[key]
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ResearchError("LIGHT_QA_INVALID", f"{key} must be lowercase SHA-256")
    if type(row["markdown_path"]) is not str or not row["markdown_path"]:
        raise ResearchError("LIGHT_QA_INVALID", "markdown_path must be a nonempty string")
    if type(row["text_start"]) is bool or type(row["text_end"]) is bool or type(row["text_start"]) is not int or type(row["text_end"]) is not int:
        raise ResearchError("LIGHT_QA_INVALID", "text offsets must be integers")
    if row["text_start"] < 0 or row["text_end"] < row["text_start"]:
        raise ResearchError("LIGHT_QA_INVALID", "text offsets must be a half-open range")
    return row


def copy_evidence(items: object) -> list[dict[str, Any]]:
    if type(items) is not list:
        raise ResearchError("LIGHT_QA_INVALID", "evidence must be a list")
    rows = [_copy_evidence_item(item) for item in items]
    seen: set[str] = set()
    for row in rows:
        if row["chunk_id"] in seen:
            raise ResearchError("LIGHT_QA_INVALID", "chunk_id is duplicated")
        seen.add(row["chunk_id"])
    return rows


def inspect_retrieval(retrieval: object) -> dict[str, Any]:
    doc = _require_dict(retrieval, "retrieval")
    status = doc.get("status")
    evidence = copy_evidence(doc.get("evidence") or [])
    index_id = doc.get("index_id")
    query = doc.get("query")
    message = doc.get("message") if type(doc.get("message")) is str else ""
    if doc.get("ok") is not True or status != OK:
        if status == INDEX_STALE:
            return _fail(INDEX_STALE, message or "index is stale", evidence=[], index_id=index_id, query=query)
        if status == NO_RESULTS or (doc.get("ok") is True and not evidence):
            return _fail(NO_RESULTS, message or "no matching evidence", evidence=[], index_id=index_id, query=query)
        if status in {NO_RESULTS, INDEX_STALE, INSUFFICIENT_EVIDENCE}:
            return _fail(str(status), message or str(status), evidence=evidence, index_id=index_id, query=query)
        return _fail(
            str(status or "QUERY_INVALID"),
            message or "retrieval is not usable",
            evidence=evidence,
            index_id=index_id,
            query=query,
        )
    return {
        "ok": True,
        "status": OK,
        "query": query,
        "index_id": index_id,
        "evidence": evidence,
        "message": message,
    }


def _context(
    *,
    kind: str,
    query: str,
    requirements: str,
    paper_ids: list[str],
    inspected: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    if not inspected.get("ok"):
        payload = copy.deepcopy(inspected)
        payload["schema"] = CONTEXT_SCHEMA
        payload["kind"] = kind
        payload["query"] = query
        payload["requirements"] = requirements
        payload["paper_ids"] = list(paper_ids)
        payload["prompt"] = ""
        payload.setdefault("evidence", [])
        return payload
    evidence = inspected["evidence"]
    if not evidence:
        return {
            "ok": False,
            "status": INSUFFICIENT_EVIDENCE,
            "schema": CONTEXT_SCHEMA,
            "kind": kind,
            "query": query,
            "requirements": requirements,
            "paper_ids": list(paper_ids),
            "index_id": inspected.get("index_id"),
            "evidence": [],
            "prompt": "",
            "markdown": "",
            "citations": [],
            "message": "no evidence is available for the current model",
        }
    return {
        "ok": True,
        "status": OK,
        "schema": CONTEXT_SCHEMA,
        "kind": kind,
        "query": query,
        "requirements": requirements,
        "paper_ids": list(paper_ids),
        "index_id": inspected.get("index_id"),
        "evidence": copy.deepcopy(evidence),
        "prompt": prompt,
        "message": "exported local context for the current conversation model",
    }


def export_qa_context(question: str, retrieval: dict) -> dict:
    if type(question) is not str:
        raise ResearchError("LIGHT_QA_INVALID", "question must be a string")
    inspected = inspect_retrieval(retrieval)
    paper_ids: list[str] = []
    if inspected.get("ok"):
        paper_ids = list(dict.fromkeys(item["paper_id"] for item in inspected["evidence"]))
    return _context(
        kind="qa",
        query=question,
        requirements="",
        paper_ids=paper_ids,
        inspected=inspected,
        prompt=_QA_PROMPT,
    )


def body_chunk_ids(text: str) -> list[str]:
    return _CITE_MARK.findall(text)


def _citation_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    raw = document.get("citations")
    if raw is None:
        return []
    if type(raw) is not list:
        raise ResearchError("LIGHT_QA_INVALID", "citations must be a list")
    rows: list[dict[str, Any]] = []
    for item in raw:
        if type(item) is not dict:
            raise ResearchError("LIGHT_QA_INVALID", "citation item must be an object")
        chunk_id = item.get("chunk_id")
        if type(chunk_id) is not str or not chunk_id:
            raise ResearchError("LIGHT_QA_INVALID", "citation chunk_id must be a nonempty string")
        rows.append(copy.deepcopy(item))
    return rows


def _joint_match(cite: dict[str, Any], by_chunk: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    chunk_id = cite["chunk_id"]
    item = by_chunk.get(chunk_id)
    if item is None:
        return INVALID_CITATION, None
    for key in OPTIONAL_CITE_FIELDS:
        if key not in cite:
            continue
        if cite[key] != item.get(key):
            return CITATION_CROSS, None
    return OK, item


def check_model_document(context: dict[str, Any], document: dict[str, Any], *, body_key: str) -> dict[str, Any]:
    if context.get("ok") is not True:
        payload = copy.deepcopy(context)
        payload.setdefault("markdown", "")
        payload.setdefault("citations", [])
        return payload
    evidence = copy_evidence(context.get("evidence") or [])
    if not evidence:
        return _fail(INSUFFICIENT_EVIDENCE, "no evidence is available for citation checks", evidence=[])
    body = document.get(body_key)
    if type(body) is not str:
        raise ResearchError("LIGHT_QA_INVALID", f"{body_key} must be a string")
    marks = body_chunk_ids(body)
    cites = _citation_rows(document)
    mark_set = list(dict.fromkeys(marks))
    cite_ids = [item["chunk_id"] for item in cites]
    cite_set = list(dict.fromkeys(cite_ids))
    if set(mark_set) != set(cite_set):
        return _fail(
            CITATION_MISMATCH,
            "body [@chunk_id] marks and citations list do not name the same chunks",
            evidence=evidence,
            body_chunk_ids=mark_set,
            citation_chunk_ids=cite_set,
        )
    if not cite_set:
        return _fail(INVALID_CITATION, "no citations point at the provided evidence", evidence=evidence)
    by_chunk = {item["chunk_id"]: item for item in evidence}
    bound: list[dict[str, Any]] = []
    for cite in cites:
        status, item = _joint_match(cite, by_chunk)
        if status == INVALID_CITATION:
            return _fail(
                INVALID_CITATION,
                "citation chunk_id is not in the provided evidence",
                evidence=evidence,
                invalid_chunk_id=cite["chunk_id"],
            )
        if status == CITATION_CROSS:
            return _fail(
                CITATION_CROSS,
                "citation identity fields do not jointly match one evidence item",
                evidence=evidence,
                invalid_citation=copy.deepcopy(cite),
            )
        assert item is not None
        bound.append(item)
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk_id in marks:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(by_chunk[chunk_id])
    return {
        "ok": True,
        "status": OK,
        "body": body,
        "evidence": evidence,
        "citations": copy.deepcopy(ordered),
        "message": _SUCCESS_MESSAGE,
    }


def _anchor(item: dict[str, Any]) -> str:
    return f"page-{item['page']}"


def _readable_mark(item: dict[str, Any]) -> str:
    title = item["title"] or item["paper_id"]
    return f"[{title}, p.{item['page']}]({item['markdown_path']}#{_anchor(item)})"


def render_markdown(body: str, citations: list[dict[str, Any]]) -> str:
    by_chunk = {item["chunk_id"]: item for item in citations}

    def replace(match: re.Match[str]) -> str:
        item = by_chunk.get(match.group(1))
        if item is None:
            return match.group(0)
        return _readable_mark(item)

    rendered = _CITE_MARK.sub(replace, body).rstrip()
    lines = [rendered, "", "## 参考文献", ""]
    for index, item in enumerate(citations, start=1):
        title = item["title"] or item["paper_id"]
        lines.append(
            f"{index}. {title} — PDF 第 {item['page']} 页 — `{item['markdown_path']}#{_anchor(item)}`"
        )
        quote = item["text"].replace("\n", " ").strip()
        if quote:
            lines.append(f"   > {quote}")
    lines.append("")
    return "\n".join(lines)


def render_checked(checked: dict[str, Any]) -> dict[str, Any]:
    if checked.get("ok") is not True:
        payload = copy.deepcopy(checked)
        payload.setdefault("markdown", "")
        payload.setdefault("citations", [])
        return payload
    citations = checked["citations"]
    markdown = render_markdown(checked["body"], citations)
    public_citations = [
        {
            "chunk_id": item["chunk_id"],
            "paper_id": item["paper_id"],
            "title": item["title"],
            "page": item["page"],
            "anchor": _anchor(item),
            "markdown_path": item["markdown_path"],
            "text_sha256": item["text_sha256"],
        }
        for item in citations
    ]
    return {
        "ok": True,
        "status": OK,
        "markdown": markdown,
        "citations": public_citations,
        "message": _SUCCESS_MESSAGE,
    }


def render_answer(context: dict, answer: dict) -> dict:
    document = _require_dict(answer, "answer")
    checked = check_model_document(_require_dict(context, "context"), document, body_key="text")
    return render_checked(checked)
