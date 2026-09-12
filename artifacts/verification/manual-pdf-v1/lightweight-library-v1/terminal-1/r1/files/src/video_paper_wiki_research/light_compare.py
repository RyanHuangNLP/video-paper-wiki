"""Cited multi-paper comparison contexts and create-only Markdown tables."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import (
    LIGHT_OUTPUT_CONFLICT,
    _commit_staged_output,
    _prepare_output_path,
    _stage_output_bytes,
    rewrite_markdown_links,
    validate_live_context,
)
from video_paper_wiki_research.light_index import (
    INDEX_STALE,
    LIGHT_SELECTION_INVALID,
    OK,
    PAPER_ID_PATTERN,
    _load_paper,
    _normalize_paper_ids,
    _paper_dirs,
    _sha256_bytes,
    _workspace_paper_ids,
    search,
)
from video_paper_wiki_research.light_knowledge import (
    LIGHT_WORKSPACE_BUSY,
    MAX_CONCEPT_NAME,
    STATUS_PROVISIONAL,
    STATUS_UNKNOWN,
    WORKSPACE_INVALID,
    _append_marks,
    _citation_rows,
    _closed,
    _control_in,
    _raise,
    _require_current_index,
    _writing_context,
    canonical_bytes,
    escape_md,
    escape_table_cell,
    require_paper_id,
    require_product_workspace,
    require_work_output,
    sha256_canonical,
    validate_cited_block,
    workspace_lock,
)
from video_paper_wiki_research.light_qa import INSUFFICIENT_EVIDENCE, copy_evidence, render_markdown

LIGHT_COMPARISON_INVALID = "LIGHT_COMPARISON_INVALID"
COMPARISON_CONTEXT_SCHEMA = "video-paper-wiki.light-comparison-context.v1"
COMPARISON_DOCUMENT_SCHEMA = "video-paper-wiki.light-comparison-document.v1"
DEFAULT_DIMENSIONS = (
    "method",
    "architecture",
    "training_data",
    "experiments",
    "limitations",
)
COMPARABLE = "comparable"
NOT_COMPARABLE = "not_comparable"
UNKNOWN = "unknown"
MAX_PAPERS = 8
MIN_PAPERS = 2
MAX_DIMENSIONS = 12
MAX_CHUNKS_PER_PAPER = 6
COMPARISON_PROMPT = (
    "Using only the provided evidence, author one "
    "video-paper-wiki.light-comparison-document.v1 object. "
    "rows must follow the frozen dimensions in order. Each row has dimension, cells, "
    "comparability, and a nonblank reason. cells cover every selected paper exactly once "
    "in selection order and use paper_id, status, text, citations, and conditions. "
    "Provisional cell rules match knowledge sections, except citations must belong to that "
    "cell's paper. Unknown cells use text 证据不足, no citations, and conditions unknown. "
    "conditions is a nonblank string or the literal unknown. "
    "comparability is comparable, not_comparable, or unknown. A comparable row requires "
    "every cell to be provisional, cited, and not conditions=unknown. "
    "This is a model-proposed comparison, not deterministic scientific verification. "
    "Do not rank numbers or equate scores across different datasets, resolutions, "
    "frame counts, or evaluation protocols. Do not put [@chunk_id] marks in text."
)
COMPARISON_REQUIREMENTS = (
    "Return video-paper-wiki.light-comparison-document.v1 using only provided evidence."
)


def _normalize_query(query: object) -> str:
    if type(query) is not str:
        _raise(LIGHT_COMPARISON_INVALID, "query must be a nonempty string")
    if not query.strip():
        _raise(LIGHT_COMPARISON_INVALID, "query must be a nonempty string")
    return query


def _normalize_dimensions(dimensions: object) -> list[str]:
    if dimensions is None:
        return list(DEFAULT_DIMENSIONS)
    if type(dimensions) is not list:
        _raise(LIGHT_COMPARISON_INVALID, "dimensions must be a list of distinct nonempty labels")
    if not 1 <= len(dimensions) <= MAX_DIMENSIONS:
        _raise(LIGHT_COMPARISON_INVALID, "dimensions must contain 1 to 12 distinct nonempty labels")
    result: list[str] = []
    seen: set[str] = set()
    for item in dimensions:
        if type(item) is not str:
            _raise(LIGHT_COMPARISON_INVALID, "each dimension must be a nonempty string")
        label = item.strip()
        if not label or len(label) > MAX_CONCEPT_NAME:
            _raise(LIGHT_COMPARISON_INVALID, "each dimension must be 1 to 120 characters")
        if _control_in(label):
            _raise(LIGHT_COMPARISON_INVALID, "dimension labels must not contain control characters")
        if label in seen:
            _raise(LIGHT_COMPARISON_INVALID, "dimensions must be distinct")
        seen.add(label)
        result.append(label)
    return result


def _normalize_selected_papers(paper_ids: object) -> list[str]:
    if type(paper_ids) is not list:
        _raise(LIGHT_COMPARISON_INVALID, "paper_ids must be a list of sha256:<64 lowercase hex> strings")
    selected, error = _normalize_paper_ids(paper_ids)
    if error is not None or selected is None:
        _raise(LIGHT_SELECTION_INVALID, error or "paper_ids is invalid")
    if any(type(item) is not str or not PAPER_ID_PATTERN.fullmatch(item) for item in paper_ids):
        _raise(LIGHT_SELECTION_INVALID, "each paper_id must be sha256:<64 lowercase hex>")
    return selected


def _wrapper_identity(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "context": payload["context"],
        "coverage": payload["coverage"],
        "dimensions": payload["dimensions"],
        "paper_ids": payload["paper_ids"],
        "prompt": payload["prompt"],
        "query": payload["query"],
        "schema": payload["schema"],
    }


def _export_comparison_unlocked(
    workspace: Path,
    *,
    query: str,
    paper_ids: list[str],
    dimensions: list[str],
) -> dict[str, Any]:
    if not MIN_PAPERS <= len(paper_ids) <= MAX_PAPERS:
        return _closed(
            LIGHT_SELECTION_INVALID,
            "comparison requires 2 to 8 distinct present papers",
            schema=COMPARISON_CONTEXT_SCHEMA,
            query=query,
            paper_ids=list(paper_ids),
            dimensions=list(dimensions),
        )
    loaded = _require_current_index(workspace)
    if type(loaded) is dict:
        loaded.setdefault("schema", COMPARISON_CONTEXT_SCHEMA)
        loaded.setdefault("query", query)
        loaded.setdefault("paper_ids", list(paper_ids))
        loaded.setdefault("dimensions", list(dimensions))
        return loaded
    stored, _papers = loaded
    present = _workspace_paper_ids(workspace)
    if any(item not in present for item in paper_ids):
        return _closed(
            LIGHT_SELECTION_INVALID,
            "selected paper_id is not present in the current workspace",
            schema=COMPARISON_CONTEXT_SCHEMA,
            query=query,
            paper_ids=list(paper_ids),
            dimensions=list(dimensions),
        )
    evidence: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for paper_id in paper_ids:
        retrieved = search(workspace, query, top_k=MAX_CHUNKS_PER_PAPER, paper_ids=[paper_id])
        if retrieved.get("status") == INDEX_STALE:
            return _closed(
                INDEX_STALE,
                str(retrieved.get("message") or "index is stale"),
                schema=COMPARISON_CONTEXT_SCHEMA,
                query=query,
                paper_ids=list(paper_ids),
                dimensions=list(dimensions),
                index_id=retrieved.get("index_id"),
            )
        if retrieved.get("status") == LIGHT_SELECTION_INVALID:
            return _closed(
                LIGHT_SELECTION_INVALID,
                str(retrieved.get("message") or "paper selection is invalid"),
                schema=COMPARISON_CONTEXT_SCHEMA,
                query=query,
                paper_ids=list(paper_ids),
                dimensions=list(dimensions),
            )
        hits = list(retrieved.get("evidence") or []) if retrieved.get("ok") is True else []
        hits = hits[:MAX_CHUNKS_PER_PAPER]
        evidence.extend(hits)
        coverage.append({"exported_chunks": len(hits), "paper_id": paper_id})
    if not evidence:
        return _closed(
            INSUFFICIENT_EVIDENCE,
            "no evidence is available for the current model",
            schema=COMPARISON_CONTEXT_SCHEMA,
            query=query,
            paper_ids=list(paper_ids),
            dimensions=list(dimensions),
            coverage=coverage,
        )
    context = _writing_context(
        workspace=workspace,
        query=query,
        requirements=COMPARISON_REQUIREMENTS,
        paper_ids=paper_ids,
        evidence=evidence,
        index_id=str(stored["index_id"]),
        prompt=COMPARISON_PROMPT,
    )
    if context.get("ok") is not True:
        payload = dict(context)
        payload["schema"] = COMPARISON_CONTEXT_SCHEMA
        payload["query"] = query
        payload["paper_ids"] = list(paper_ids)
        payload["dimensions"] = list(dimensions)
        payload["coverage"] = coverage
        return payload
    live = validate_live_context(workspace, context)
    if live.get("ok") is not True:
        return live
    wrapper = {
        "ok": True,
        "status": OK,
        "message": "exported structured comparison context for the current conversation model",
        "schema": COMPARISON_CONTEXT_SCHEMA,
        "query": query,
        "paper_ids": list(paper_ids),
        "dimensions": list(dimensions),
        "context": context,
        "coverage": coverage,
        "prompt": COMPARISON_PROMPT,
    }
    wrapper["context_sha256"] = sha256_canonical(context)
    return wrapper


def export_comparison_context(
    workspace_root: Path,
    *,
    query: object,
    paper_ids: object,
    dimensions: object = None,
) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    normalized_query = _normalize_query(query)
    selected = _normalize_selected_papers(paper_ids)
    labels = _normalize_dimensions(dimensions)
    return _export_comparison_unlocked(
        workspace, query=normalized_query, paper_ids=selected, dimensions=labels
    )


def _validate_conditions(status: str, conditions: object) -> str:
    if type(conditions) is not str or not conditions.strip():
        _raise(LIGHT_COMPARISON_INVALID, "conditions must be a nonempty string or the literal unknown")
    if status == STATUS_UNKNOWN and conditions != UNKNOWN:
        _raise(LIGHT_COMPARISON_INVALID, "unknown cells must have conditions unknown")
    return conditions


def _validate_cell(
    cell: object,
    *,
    paper_id: str,
    evidence_ids: set[str],
    by_chunk: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if type(cell) is not dict:
        _raise(LIGHT_COMPARISON_INVALID, "comparison cell must be an object")
    if set(cell) != {"paper_id", "status", "text", "citations", "conditions"}:
        _raise(LIGHT_COMPARISON_INVALID, "comparison cell must have exactly paper_id, status, text, citations, and conditions")
    if cell.get("paper_id") != paper_id:
        _raise(LIGHT_COMPARISON_INVALID, "comparison cells must follow the selected paper order")
    require_paper_id(cell.get("paper_id"), code=LIGHT_COMPARISON_INVALID)
    checked = validate_cited_block(
        {key: cell[key] for key in ("status", "text", "citations")},
        evidence_ids=evidence_ids,
        paper_id=paper_id,
        by_chunk=by_chunk,
        code=LIGHT_COMPARISON_INVALID,
    )
    conditions = _validate_conditions(checked["status"], cell.get("conditions"))
    checked["conditions"] = conditions
    checked["paper_id"] = paper_id
    return checked


def _validate_document(
    document: object,
    *,
    paper_ids: list[str],
    dimensions: list[str],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    if type(document) is not dict:
        _raise(LIGHT_COMPARISON_INVALID, "document must be an object")
    if document.get("schema") != COMPARISON_DOCUMENT_SCHEMA:
        _raise(LIGHT_COMPARISON_INVALID, "document schema must be light-comparison-document.v1")
    if set(document) != {"schema", "rows"}:
        _raise(LIGHT_COMPARISON_INVALID, "document must have exactly schema and rows")
    rows = document.get("rows")
    if type(rows) is not list or len(rows) != len(dimensions):
        _raise(LIGHT_COMPARISON_INVALID, "rows must contain one entry per frozen dimension in order")
    by_chunk = {item["chunk_id"]: item for item in evidence}
    evidence_ids = set(by_chunk)
    checked_rows: list[dict[str, Any]] = []
    for dimension, row in zip(dimensions, rows):
        if type(row) is not dict:
            _raise(LIGHT_COMPARISON_INVALID, "comparison row must be an object")
        if set(row) != {"dimension", "cells", "comparability", "reason"}:
            _raise(LIGHT_COMPARISON_INVALID, "comparison row must have exactly dimension, cells, comparability, and reason")
        if row.get("dimension") != dimension:
            _raise(LIGHT_COMPARISON_INVALID, "comparison rows must follow the frozen dimension order")
        reason = row.get("reason")
        if type(reason) is not str or not reason.strip():
            _raise(LIGHT_COMPARISON_INVALID, "comparison reason must be a nonempty string")
        comparability = row.get("comparability")
        if comparability not in {COMPARABLE, NOT_COMPARABLE, UNKNOWN}:
            _raise(LIGHT_COMPARISON_INVALID, "comparability must be comparable, not_comparable, or unknown")
        cells_raw = row.get("cells")
        if type(cells_raw) is not list or len(cells_raw) != len(paper_ids):
            _raise(LIGHT_COMPARISON_INVALID, "cells must cover every selected paper exactly once in order")
        cells = [
            _validate_cell(
                cell,
                paper_id=paper_id,
                evidence_ids=evidence_ids,
                by_chunk=by_chunk,
            )
            for cell, paper_id in zip(cells_raw, paper_ids)
        ]
        if comparability == COMPARABLE:
            for cell in cells:
                if (
                    cell["status"] != STATUS_PROVISIONAL
                    or not cell["citations"]
                    or cell["conditions"] == UNKNOWN
                ):
                    _raise(
                        LIGHT_COMPARISON_INVALID,
                        "comparable rows require every cell to be provisional, cited, and not conditions=unknown",
                    )
        checked_rows.append(
            {
                "cells": cells,
                "comparability": comparability,
                "dimension": dimension,
                "reason": reason,
            }
        )
    return {"rows": checked_rows, "schema": COMPARISON_DOCUMENT_SCHEMA}


def _cell_markdown(cell: dict[str, Any]) -> str:
    body = _append_marks(cell["text"], cell["citations"])
    return f"{body}<br>条件: {escape_table_cell(cell['conditions'])}"


def _render_comparison_markdown(
    *,
    workspace: Path,
    output: Path,
    wrapper: dict[str, Any],
    document: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> str:
    by_chunk = {item["chunk_id"]: item for item in evidence}
    titles: dict[str, str] = {}
    for directory in _paper_dirs(workspace):
        paper = _load_paper(directory)
        titles[paper["paper_id"]] = str(paper.get("title") or paper["paper_id"])
    for item in evidence:
        titles.setdefault(item["paper_id"], str(item.get("title") or item["paper_id"]))
    for paper_id in wrapper["paper_ids"]:
        titles.setdefault(paper_id, paper_id)
    headers = (
        ["维度"]
        + [escape_table_cell(titles[paper_id]) for paper_id in wrapper["paper_ids"]]
        + ["可比性", "理由"]
    )
    lines = [
        "# 论文对比",
        "",
        "本表是模型建议的条件感知对比，不是确定性科学核验。不要把不同数据集、分辨率、帧数或评测协议上的数字直接排序或等同。",
        "",
        f"- 查询: {escape_md(wrapper['query'])}",
        f"- 维度: {escape_md(', '.join(wrapper['dimensions']))}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    used: list[str] = []
    for row in document["rows"]:
        cells = [_cell_markdown(cell) for cell in row["cells"]]
        for cell in row["cells"]:
            used.extend(cell["citations"])
        rendered = [escape_table_cell(row["dimension"]), *[escape_table_cell(item) for item in cells]]
        rendered.append(escape_table_cell(row["comparability"]))
        rendered.append(escape_table_cell(row["reason"]))
        lines.append("| " + " | ".join(rendered) + " |")
    lines.append("")
    body = "\n".join(lines).rstrip()
    citations = _citation_rows(used, by_chunk)
    markdown = render_markdown(body, citations) if citations else body + "\n"
    return rewrite_markdown_links(markdown, workspace=workspace, output=output)


def _default_output(workspace: Path, document_id: str) -> Path:
    return workspace / "reports" / f"comparison-{document_id}.md"


def _import_comparison_locked(
    workspace: Path,
    wrapper: object,
    document: object,
    output: Path,
) -> dict[str, Any]:
    if type(wrapper) is not dict:
        _raise(LIGHT_COMPARISON_INVALID, "context must be an object")
    query = _normalize_query(wrapper.get("query"))
    paper_ids = _normalize_selected_papers(wrapper.get("paper_ids"))
    dimensions = _normalize_dimensions(wrapper.get("dimensions"))
    fresh = _export_comparison_unlocked(
        workspace, query=query, paper_ids=paper_ids, dimensions=dimensions
    )
    if fresh.get("ok") is not True:
        return fresh
    if wrapper.get("schema") != COMPARISON_CONTEXT_SCHEMA:
        return _closed(LIGHT_COMPARISON_INVALID, "context schema must be light-comparison-context.v1")
    if type(wrapper.get("context")) is not dict:
        return _closed(LIGHT_COMPARISON_INVALID, "context wrapper is missing the inner light-context")
    if sha256_canonical(wrapper["context"]) != fresh["context_sha256"]:
        return _closed(LIGHT_COMPARISON_INVALID, "context wrapper does not match a current comparison export")
    if wrapper.get("context_sha256") != fresh["context_sha256"]:
        return _closed(LIGHT_COMPARISON_INVALID, "context_sha256 does not match the inner context bytes")
    if canonical_bytes(_wrapper_identity(wrapper)) != canonical_bytes(_wrapper_identity(fresh)):
        return _closed(LIGHT_COMPARISON_INVALID, "context wrapper does not match a current comparison export")
    live = validate_live_context(workspace, fresh["context"])
    if live.get("ok") is not True:
        return live
    try:
        checked = _validate_document(
            document,
            paper_ids=paper_ids,
            dimensions=dimensions,
            evidence=copy_evidence(fresh["context"]["evidence"]),
        )
    except ResearchError as exc:
        if exc.code == LIGHT_COMPARISON_INVALID:
            return _closed(LIGHT_COMPARISON_INVALID, exc.message)
        raise
    resolved, conflict = _prepare_output_path(output, workspace, overwrite=False)
    if conflict is not None:
        return conflict
    markdown = _render_comparison_markdown(
        workspace=workspace,
        output=resolved,
        wrapper=fresh,
        document=checked,
        evidence=fresh["context"]["evidence"],
    )
    if not markdown.endswith("\n"):
        markdown += "\n"
    encoded = markdown.encode("utf-8")
    live = validate_live_context(workspace, fresh["context"])
    if live.get("ok") is not True:
        return live
    tmp, created_parent, staged_fail = _stage_output_bytes(resolved, encoded)
    if staged_fail is not None:
        return staged_fail
    assert tmp is not None
    committed = False
    try:
        live = validate_live_context(workspace, fresh["context"])
        if live.get("ok") is not True:
            return live
        failed = _commit_staged_output(tmp, resolved, overwrite=False)
        if failed is not None:
            return failed
        committed = True
        citations = []
        by_chunk = {item["chunk_id"]: item for item in fresh["context"]["evidence"]}
        used: list[str] = []
        for row in checked["rows"]:
            for cell in row["cells"]:
                used.extend(cell["citations"])
        for item in _citation_rows(used, by_chunk):
            citations.append(
                {
                    "anchor": f"page-{item['page']}",
                    "chunk_id": item["chunk_id"],
                    "markdown_path": item["markdown_path"],
                    "page": item["page"],
                    "paper_id": item["paper_id"],
                    "text_sha256": item["text_sha256"],
                    "title": item["title"],
                }
            )
        return {
            "ok": True,
            "status": OK,
            "message": "published structured comparison Markdown",
            "path": str(resolved),
            "output_sha256": _sha256_bytes(encoded),
            "citations": citations,
            "workspace_root": str(workspace),
            "index_id": live.get("index_id"),
        }
    finally:
        if not committed:
            from video_paper_wiki_research.light_context import _abandon_stage

            _abandon_stage(tmp, resolved.parent, created_parent)


def import_comparison(workspace_root: Path, context: object, document: object, *, output: Path | None = None) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    try:
        with workspace_lock(workspace):
            if output is None:
                if type(context) is not dict or type(document) is not dict:
                    _raise(LIGHT_COMPARISON_INVALID, "context and document must be objects")
                document_id = sha256_canonical({"context": context, "document": document})
                target = require_work_output(
                    _default_output(workspace, document_id), code=LIGHT_COMPARISON_INVALID
                )
            else:
                target = require_work_output(output, code=LIGHT_COMPARISON_INVALID)
            return _import_comparison_locked(workspace, context, document, target)
    except ResearchError as exc:
        if exc.code == LIGHT_WORKSPACE_BUSY:
            return _closed(LIGHT_WORKSPACE_BUSY, exc.message)
        if exc.code == LIGHT_OUTPUT_CONFLICT:
            return _closed(LIGHT_OUTPUT_CONFLICT, exc.message)
        if exc.code == LIGHT_COMPARISON_INVALID:
            return _closed(LIGHT_COMPARISON_INVALID, exc.message)
        if exc.code == WORKSPACE_INVALID:
            raise
        raise
