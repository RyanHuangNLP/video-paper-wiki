"""Original plus English lexical query fusion and strict query-plan traces."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_index import (
    INDEX_STALE,
    LIGHT_SELECTION_INVALID,
    NO_RESULTS,
    OK,
    _derived_chunks,
    _index_is_current,
    _load_index,
    _normalize_paper_ids,
    _search_same_snapshot,
    _sha256_text,
    _snapshot_id,
    _workspace_paper_ids,
)
from video_paper_wiki_research.light_qa import CONTEXT_SCHEMA, copy_evidence, export_qa_context
from video_paper_wiki_research.light_writing import export_writing_context

QUERY_REWRITE_INVALID = "QUERY_REWRITE_INVALID"
SOURCE_INVALID = "SOURCE_INVALID"
LIGHT_CONTEXT_INVALID = "LIGHT_CONTEXT_INVALID"
REWRITE_SCHEMA = "video-paper-wiki.light-query-rewrite.v1"
PLAN_SCHEMA = "video-paper-wiki.light-query-plan.v1"
FUSION = {"algorithm": "rrf-v1", "rank_constant": 60, "candidate_k": 24, "top_k": 8}
REWRITE_KEYS = ("schema", "original_query", "rewritten_query", "language")
PLAN_KEYS = (
    "schema",
    "original_query",
    "rewrite",
    "rewrite_sha256",
    "workspace_id",
    "index_id",
    "selected_paper_ids",
    "paper_snapshots",
    "fusion",
    "routes",
    "fused",
    "plan_sha256",
)
ROUTE_KEYS = ("name", "query", "status", "index_id", "candidates")
CANDIDATE_KEYS = ("chunk_id", "rank", "score")
FUSED_KEYS = ("chunk_id", "score", "route_names")
SNAPSHOT_KEYS = ("paper_id", "markdown_sha256", "source_json_sha256")
ROUTE_ORDER = ("original", "rewrite")
MAX_QUERY_CHARS = 2000
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_PAPER_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
EVIDENCE_IDENTITY_FIELDS = (
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
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_hex64(value: object) -> bool:
    return type(value) is str and _HEX64.fullmatch(value) is not None


def _is_finite_number(value: object) -> bool:
    return type(value) in (int, float) and type(value) is not bool and math.isfinite(value)


def _is_int(value: object) -> bool:
    return type(value) is int and type(value) is not bool


def _has_control(text: str) -> bool:
    return any(unicodedata.category(char) == "Cc" for char in text)


def _fail_payload(
    status: str,
    message: str,
    *,
    workspace: Path,
    kind: str,
    query: object,
    requirements: object,
    index_id: object,
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "message": message,
        "schema": CONTEXT_SCHEMA,
        "kind": kind,
        "query": query if type(query) is str else "",
        "requirements": requirements if type(requirements) is str else "",
        "paper_ids": [],
        "selected_paper_ids": [],
        "index_id": index_id,
        "workspace_root": str(workspace),
        "evidence": [],
        "prompt": "",
        "markdown": "",
        "citations": [],
    }


def _index_id_hint(workspace: Path) -> object:
    stored = _load_index(workspace)
    if type(stored) is not dict:
        return None
    return stored.get("index_id")


def _checked_rewrite(rewrite: object, query: str) -> tuple[dict[str, str] | None, str | None]:
    if type(rewrite) is not dict:
        return None, "rewrite must be an object"
    if set(rewrite) != set(REWRITE_KEYS):
        return None, "rewrite must have exactly schema, original_query, rewritten_query, language"
    if rewrite.get("schema") != REWRITE_SCHEMA:
        return None, "rewrite schema must be video-paper-wiki.light-query-rewrite.v1"
    original = rewrite.get("original_query")
    rewritten = rewrite.get("rewritten_query")
    language = rewrite.get("language")
    if type(original) is not str or type(rewritten) is not str or type(language) is not str:
        return None, "rewrite fields must be strings"
    if original != query:
        return None, "rewrite.original_query must equal query byte-for-byte"
    if language != "en":
        return None, "rewrite language must be exactly en"
    if not rewritten.strip() or len(rewritten) > MAX_QUERY_CHARS:
        return None, "rewritten_query must be a nonblank string of at most 2000 characters"
    if _has_control(rewritten):
        return None, "rewritten_query must not contain control characters"
    if _LATIN_LETTER.search(rewritten) is None:
        return None, "rewritten_query must contain a Latin letter"
    return {
        "schema": REWRITE_SCHEMA,
        "original_query": original,
        "rewritten_query": rewritten,
        "language": "en",
    }, None


def _paper_snapshots(papers: Sequence[Mapping[str, Any]], selected: Sequence[str]) -> list[dict[str, str]] | None:
    wanted = set(selected) if selected else {paper["paper_id"] for paper in papers}
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for paper in papers:
        paper_id = paper.get("paper_id")
        markdown_sha = paper.get("markdown_sha256")
        source_json_sha = paper.get("source_json_sha256")
        if paper_id not in wanted:
            continue
        if type(paper_id) is not str or not _is_hex64(markdown_sha) or not _is_hex64(source_json_sha):
            return None
        if paper_id in seen:
            return None
        seen.add(paper_id)
        rows.append(
            {
                "paper_id": paper_id,
                "markdown_sha256": markdown_sha,
                "source_json_sha256": source_json_sha,
            }
        )
    if seen != wanted:
        return None
    rows.sort(key=lambda item: item["paper_id"])
    return rows


def _route_candidates(result: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]] | None:
    status = result.get("status")
    evidence = result.get("evidence")
    if type(evidence) is not list:
        return None
    if status == NO_RESULTS:
        if evidence:
            return None
        return [], {}
    if status != OK or not evidence:
        return None
    if len(evidence) > FUSION["candidate_k"]:
        return None
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(evidence, start=1):
        if type(item) is not dict:
            return None
        chunk_id = item.get("chunk_id")
        score = item.get("score")
        if type(chunk_id) is not str or not chunk_id or chunk_id in by_id:
            return None
        if not _is_finite_number(score):
            return None
        rows.append({"chunk_id": chunk_id, "rank": index, "score": score})
        by_id[chunk_id] = dict(item)
    return rows, by_id


def _fuse_routes(routes: Sequence[Mapping[str, Any]], evidence_by_route: Mapping[str, Mapping[str, dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fused_map: dict[str, dict[str, Any]] = {}
    for route in routes:
        name = route["name"]
        for candidate in route["candidates"]:
            chunk_id = candidate["chunk_id"]
            addend = 1.0 / (FUSION["rank_constant"] + candidate["rank"])
            current = fused_map.get(chunk_id)
            if current is None:
                fused_map[chunk_id] = {
                    "chunk_id": chunk_id,
                    "score": addend,
                    "route_names": [name],
                    "evidence": dict(evidence_by_route[name][chunk_id]),
                }
            else:
                current["score"] += addend
                current["route_names"].append(name)
    ranked = sorted(fused_map.values(), key=lambda item: (-item["score"], item["chunk_id"]))
    kept = ranked[: FUSION["top_k"]]
    fused = [{"chunk_id": item["chunk_id"], "score": item["score"], "route_names": list(item["route_names"])} for item in kept]
    evidence: list[dict[str, Any]] = []
    for item in kept:
        row = dict(item["evidence"])
        row["score"] = item["score"]
        evidence.append(row)
    return fused, evidence


def _build_query_plan(
    *,
    workspace: Path,
    query: str,
    rewrite: Mapping[str, str],
    selected: Sequence[str],
    papers: Sequence[Mapping[str, Any]],
    index_id: str,
    routes: Sequence[Mapping[str, Any]],
    fused: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    snapshots = _paper_snapshots(papers, selected)
    if snapshots is None:
        return None
    plan = {
        "schema": PLAN_SCHEMA,
        "original_query": query,
        "rewrite": {
            "schema": rewrite["schema"],
            "original_query": rewrite["original_query"],
            "rewritten_query": rewrite["rewritten_query"],
            "language": rewrite["language"],
        },
        "rewrite_sha256": _sha256_canonical(rewrite),
        "workspace_id": _sha256_canonical({"workspace_root": str(workspace)}),
        "index_id": index_id,
        "selected_paper_ids": list(selected),
        "paper_snapshots": snapshots,
        "fusion": dict(FUSION),
        "routes": [dict(route) for route in routes],
        "fused": [dict(row) for row in fused],
    }
    plan["plan_sha256"] = _sha256_canonical({key: value for key, value in plan.items() if key != "plan_sha256"})
    return plan


def _derived_by_chunk(papers: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]] | None:
    derived = _derived_chunks(papers)
    by_id: dict[str, dict[str, Any]] = {}
    for chunk in derived:
        chunk_id = chunk["chunk_id"]
        if chunk_id in by_id:
            return None
        by_id[chunk_id] = chunk
    return by_id


def _evidence_matches_live(
    evidence: Sequence[Mapping[str, Any]],
    papers: Sequence[Mapping[str, Any]],
    selected: Sequence[str],
) -> bool:
    derived = _derived_by_chunk(papers)
    if derived is None:
        return False
    present = {paper["paper_id"] for paper in papers}
    allowed = set(selected) if selected else present
    papers_by_id = {paper["paper_id"]: paper for paper in papers}
    seen: set[str] = set()
    for row in evidence:
        chunk_id = row.get("chunk_id")
        if type(chunk_id) is not str or chunk_id in seen:
            return False
        seen.add(chunk_id)
        chunk = derived.get(chunk_id)
        if chunk is None:
            return False
        for field in EVIDENCE_IDENTITY_FIELDS:
            if row.get(field) != chunk.get(field):
                return False
        if row["paper_id"] not in allowed:
            return False
        paper = papers_by_id.get(chunk["paper_id"])
        if paper is None:
            return False
        slice_text = paper["markdown"][chunk["text_start"] : chunk["text_end"]]
        if row["text"] != chunk["text"] or chunk["text"] != slice_text:
            return False
        if _sha256_text(slice_text) != row["text_sha256"]:
            return False
    return True


def _retrieve_fused(
    workspace: Path,
    *,
    query: str,
    rewrite: Mapping[str, str],
    selected: Sequence[str],
) -> dict[str, Any]:
    """Raw fused retrieval and query_plan construction. Does not wrap a context."""
    allowed = set(selected) if selected else None
    original = query
    rewritten = rewrite["rewritten_query"]
    if original == rewritten:
        names = ["original"]
        texts = [original]
    else:
        names = ["original", "rewrite"]
        texts = [original, rewritten]
    try:
        batch = _search_same_snapshot(workspace, texts, top_k=FUSION["candidate_k"], allowed=allowed)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return {
            "ok": False,
            "status": INDEX_STALE,
            "message": "workspace Markdown or paper set disagrees with the stored index",
            "index_id": _index_id_hint(workspace),
        }
    if batch.get("ok") is not True or batch.get("status") not in {OK} or type(batch.get("routes")) is not list:
        status = batch.get("status") if type(batch.get("status")) is str else INDEX_STALE
        if status in {OK, NO_RESULTS}:
            status = INDEX_STALE
        return {
            "ok": False,
            "status": status,
            "message": batch.get("message") or "workspace Markdown or paper set disagrees with the stored index",
            "index_id": batch.get("index_id"),
        }
    index_id = batch.get("index_id")
    if type(index_id) is not str or not index_id:
        return {
            "ok": False,
            "status": INDEX_STALE,
            "message": "workspace Markdown or paper set disagrees with the stored index",
            "index_id": index_id,
        }
    routes: list[dict[str, Any]] = []
    evidence_by_route: dict[str, dict[str, dict[str, Any]]] = {}
    for name, text, result in zip(names, texts, batch["routes"]):
        if type(result) is not dict or result.get("query") != text:
            return {
                "ok": False,
                "status": INDEX_STALE,
                "message": "workspace Markdown or paper set disagrees with the stored index",
                "index_id": index_id,
            }
        if result.get("status") not in {OK, NO_RESULTS} or result.get("index_id") != index_id:
            status = result.get("status") if type(result.get("status")) is str else INDEX_STALE
            if status in {OK, NO_RESULTS}:
                status = INDEX_STALE
            return {
                "ok": False,
                "status": status,
                "message": result.get("message") or "workspace Markdown or paper set disagrees with the stored index",
                "index_id": result.get("index_id"),
            }
        parsed = _route_candidates(result)
        if parsed is None:
            return {
                "ok": False,
                "status": INDEX_STALE,
                "message": "workspace Markdown or paper set disagrees with the stored index",
                "index_id": index_id,
            }
        candidates, by_id = parsed
        routes.append(
            {
                "name": name,
                "query": text,
                "status": result["status"],
                "index_id": index_id,
                "candidates": candidates,
            }
        )
        evidence_by_route[name] = by_id
    fused, evidence = _fuse_routes(routes, evidence_by_route)
    return {
        "ok": True,
        "status": OK if evidence else NO_RESULTS,
        "index_id": index_id,
        "routes": routes,
        "fused": fused,
        "evidence": evidence,
        "rewrite": dict(rewrite),
        "selected": list(selected),
        "query": query,
    }


def _load_live_papers(workspace: Path) -> list[dict[str, Any]]:
    from video_paper_wiki_research.light_context import _load_live_papers

    return _load_live_papers(workspace)


def _recheck_live_snapshot(
    workspace: Path,
    *,
    index_id: str,
    selected: Sequence[str],
    evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        papers = _load_live_papers(workspace)
    except ResearchError as exc:
        if exc.code == SOURCE_INVALID:
            return {"ok": False, "status": SOURCE_INVALID, "message": exc.message, "index_id": index_id}
        raise
    except UnicodeError:
        return {"ok": False, "status": SOURCE_INVALID, "message": "source.md is not valid UTF-8", "index_id": index_id}
    except OSError as exc:
        return {"ok": False, "status": SOURCE_INVALID, "message": f"cannot read live paper source: {exc}", "index_id": index_id}
    stored = _load_index(workspace)
    try:
        current = stored is not None and _index_is_current(stored, papers)
    except (TypeError, ValueError, KeyError, AttributeError, IndexError):
        current = False
    if stored is None or not current or stored.get("index_id") != index_id:
        return {
            "ok": False,
            "status": INDEX_STALE,
            "message": "workspace Markdown or paper set disagrees with the stored index",
            "index_id": None if stored is None else stored.get("index_id") if type(stored) is dict else None,
        }
    if index_id != _snapshot_id(papers):
        return {
            "ok": False,
            "status": INDEX_STALE,
            "message": "workspace Markdown or paper set disagrees with the stored index",
            "index_id": index_id,
        }
    snapshots = _paper_snapshots(papers, selected)
    if snapshots is None:
        return {
            "ok": False,
            "status": INDEX_STALE,
            "message": "workspace Markdown or paper set disagrees with the stored index",
            "index_id": index_id,
        }
    if evidence and not _evidence_matches_live(evidence, papers, selected):
        return {
            "ok": False,
            "status": INDEX_STALE,
            "message": "workspace Markdown or paper set disagrees with the stored index",
            "index_id": index_id,
        }
    return {"ok": True, "status": OK, "papers": papers, "stored": stored, "snapshots": snapshots, "index_id": index_id}


def _validate_query_bounds(query: object) -> str | None:
    if type(query) is not str:
        return "query must be a string"
    if not query.strip() or len(query) > MAX_QUERY_CHARS:
        return "query must be a nonblank string of at most 2000 characters"
    return None


def _retrieve_fused_plan(
    workspace_root: Path,
    *,
    query: str,
    rewrite: Mapping[str, str],
    paper_ids: Sequence[str] | None,
) -> dict[str, Any]:
    """Build fused routes/plan from the live index. Public context wrapping stays outside."""
    from video_paper_wiki_research.light_context import _require_workspace

    workspace = _require_workspace(workspace_root)
    selected = list(paper_ids) if paper_ids is not None else []
    retrieved = _retrieve_fused(workspace, query=query, rewrite=rewrite, selected=selected)
    if retrieved.get("ok") is not True:
        return retrieved
    live = _recheck_live_snapshot(
        workspace,
        index_id=retrieved["index_id"],
        selected=selected,
        evidence=retrieved["evidence"],
    )
    if live.get("ok") is not True:
        return live
    plan = _build_query_plan(
        workspace=workspace,
        query=query,
        rewrite=rewrite,
        selected=selected,
        papers=live["papers"],
        index_id=retrieved["index_id"],
        routes=retrieved["routes"],
        fused=retrieved["fused"],
    )
    if plan is None:
        return {
            "ok": False,
            "status": INDEX_STALE,
            "message": "workspace Markdown or paper set disagrees with the stored index",
            "index_id": retrieved["index_id"],
        }
    retrieved["plan"] = plan
    retrieved["papers"] = live["papers"]
    retrieved["workspace"] = workspace
    return retrieved


def export_rewritten_context(
    workspace_root: Path,
    *,
    kind: str,
    query: str,
    rewrite: object,
    requirements: str = "",
    paper_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Search original plus rewritten English terms and export light-context.v1."""
    from video_paper_wiki_research.light_context import (
        KINDS,
        _attach_export_fields,
        _require_workspace,
        _selection_payload,
    )

    workspace = _require_workspace(workspace_root)
    if type(kind) is not str or kind not in KINDS:
        raise ResearchError(LIGHT_CONTEXT_INVALID, "kind must be exactly qa or writing")
    if type(query) is not str:
        raise ResearchError("QUERY_INVALID", "query must be a string")
    if type(requirements) is not str:
        raise ResearchError("QUERY_INVALID", "requirements must be a string")
    bound = _validate_query_bounds(query)
    if bound is not None:
        return _fail_payload(
            QUERY_REWRITE_INVALID,
            bound,
            workspace=workspace,
            kind=kind,
            query=query,
            requirements=requirements,
            index_id=_index_id_hint(workspace),
        )
    checked, rewrite_error = _checked_rewrite(rewrite, query)
    if checked is None or rewrite_error is not None:
        return _fail_payload(
            QUERY_REWRITE_INVALID,
            rewrite_error or "rewrite is invalid",
            workspace=workspace,
            kind=kind,
            query=query,
            requirements=requirements,
            index_id=_index_id_hint(workspace),
        )
    selected, selection_error = _normalize_paper_ids(paper_ids)
    stored = _load_index(workspace)
    index_id = stored.get("index_id") if type(stored) is dict else None
    if selection_error is not None or selected is None:
        return _selection_payload(
            kind=kind,
            query=query,
            requirements=requirements,
            workspace=workspace,
            index_id=index_id,
            message=selection_error or "paper_ids is invalid",
        )
    present = _workspace_paper_ids(workspace)
    if selected and any(item not in present for item in selected):
        return _selection_payload(
            kind=kind,
            query=query,
            requirements=requirements,
            workspace=workspace,
            index_id=index_id,
            message="selected paper_id is not present in the current workspace",
        )
    retrieved = _retrieve_fused_plan(workspace, query=query, rewrite=checked, paper_ids=selected)
    if retrieved.get("ok") is not True:
        status = retrieved.get("status") if type(retrieved.get("status")) is str else INDEX_STALE
        return _fail_payload(
            status,
            retrieved.get("message") or status,
            workspace=workspace,
            kind=kind,
            query=query,
            requirements=requirements,
            index_id=retrieved.get("index_id"),
        )
    retrieval = {
        "ok": retrieved["status"] == OK,
        "status": retrieved["status"],
        "query": query,
        "index_id": retrieved["index_id"],
        "evidence": retrieved["evidence"],
        "message": (
            "retrieved lexical evidence from the workspace index"
            if retrieved["status"] == OK
            else "query produced no lexical matches"
        ),
    }
    if kind == "qa":
        exported = export_qa_context(query, retrieval)
    else:
        exported = export_writing_context(query, requirements, list(selected), retrieval)
    payload = _attach_export_fields(exported, workspace=workspace, selected=list(selected))
    payload["query_plan"] = retrieved["plan"]
    return payload


def _route_shape_error(route: object, *, expected_name: str, expected_query: str, index_id: object) -> str | None:
    if type(route) is not dict or set(route) != set(ROUTE_KEYS):
        return "each route must have exactly name, query, status, index_id, candidates"
    if route.get("name") != expected_name:
        return "routes must be ordered original then rewrite"
    if route.get("query") != expected_query:
        return "route query must match the original or rewritten string"
    if route.get("index_id") != index_id:
        return "route index_id must equal the plan index_id"
    status = route.get("status")
    if status not in {OK, NO_RESULTS}:
        return "route status must be OK or NO_RESULTS"
    candidates = route.get("candidates")
    if type(candidates) is not list:
        return "route candidates must be a list"
    if status == NO_RESULTS:
        if candidates:
            return "NO_RESULTS candidates must be an empty list"
        return None
    if not candidates or len(candidates) > FUSION["candidate_k"]:
        return "OK candidates must contain 1 to 24 unique backend ranks"
    seen: set[str] = set()
    for index, item in enumerate(candidates, start=1):
        if type(item) is not dict or set(item) != set(CANDIDATE_KEYS):
            return "candidate rows must have exactly chunk_id, rank, score"
        chunk_id = item.get("chunk_id")
        rank = item.get("rank")
        score = item.get("score")
        if type(chunk_id) is not str or not chunk_id or chunk_id in seen:
            return "candidate chunk_id values must be unique nonempty strings"
        if not _is_int(rank) or rank != index:
            return "candidate rank must be a consecutive one-based integer"
        if not _is_finite_number(score):
            return "candidate score must be the finite original BM25 score"
        seen.add(chunk_id)
    return None


def query_plan_shape_error(plan: object) -> str | None:
    """Pure query_plan checks: exact keys, types, hashes, and internal RRF."""
    if type(plan) is not dict:
        return "query_plan must be an object"
    if set(plan) != set(PLAN_KEYS):
        return "query_plan has unknown or missing fields"
    if plan.get("schema") != PLAN_SCHEMA:
        return "query_plan schema must be video-paper-wiki.light-query-plan.v1"
    original = plan.get("original_query")
    if type(original) is not str:
        return "original_query must be a string"
    rewrite, rewrite_error = _checked_rewrite(plan.get("rewrite"), original)
    if rewrite is None or rewrite_error is not None:
        return rewrite_error or "rewrite is invalid"
    if plan.get("rewrite") != rewrite:
        return "rewrite must be the exact checked four-field object"
    if plan.get("rewrite_sha256") != _sha256_canonical(rewrite):
        return "rewrite_sha256 does not match the canonical rewrite"
    if not _is_hex64(plan.get("workspace_id")):
        return "workspace_id must be 64 lowercase hex characters"
    if type(plan.get("index_id")) is not str or not plan.get("index_id"):
        return "index_id must be a nonempty string"
    selected = plan.get("selected_paper_ids")
    if type(selected) is not list:
        return "selected_paper_ids must be a list"
    seen_ids: set[str] = set()
    for item in selected:
        if type(item) is not str or _PAPER_ID.fullmatch(item) is None:
            return "selected_paper_ids must be unique sha256 paper ids"
        if item in seen_ids:
            return "selected_paper_ids must not contain duplicates"
        seen_ids.add(item)
    snapshots = plan.get("paper_snapshots")
    if type(snapshots) is not list:
        return "paper_snapshots must be a list"
    snapshot_ids: list[str] = []
    for item in snapshots:
        if type(item) is not dict or set(item) != set(SNAPSHOT_KEYS):
            return "paper_snapshots rows must have exactly paper_id, markdown_sha256, source_json_sha256"
        paper_id = item.get("paper_id")
        if type(paper_id) is not str or _PAPER_ID.fullmatch(paper_id) is None:
            return "paper_snapshots paper_id is invalid"
        if not _is_hex64(item.get("markdown_sha256")) or not _is_hex64(item.get("source_json_sha256")):
            return "paper_snapshots digests must be lowercase SHA-256"
        snapshot_ids.append(paper_id)
    if snapshot_ids != sorted(snapshot_ids) or len(snapshot_ids) != len(set(snapshot_ids)):
        return "paper_snapshots must be unique and sorted by paper_id"
    if selected and set(snapshot_ids) != set(selected):
        return "paper_snapshots must cover the selected papers"
    fusion = plan.get("fusion")
    if fusion != FUSION:
        return "fusion must be the fixed rrf-v1 limits"
    routes = plan.get("routes")
    if type(routes) is not list or not routes or len(routes) > 2:
        return "routes must contain original, then rewrite when the query strings differ"
    rewritten = rewrite["rewritten_query"]
    if original == rewritten:
        if len(routes) != 1:
            return "identical query strings must produce only the original route"
        expected = [("original", original)]
    else:
        if len(routes) != 2:
            return "distinct query strings must produce original then rewrite routes"
        expected = [("original", original), ("rewrite", rewritten)]
    for route, (name, text) in zip(routes, expected):
        route_error = _route_shape_error(route, expected_name=name, expected_query=text, index_id=plan.get("index_id"))
        if route_error is not None:
            return route_error
    fused = plan.get("fused")
    if type(fused) is not list or len(fused) > FUSION["top_k"]:
        return "fused must contain at most eight rows"
    expected_fused, _evidence = _fuse_routes(routes, {route["name"]: {item["chunk_id"]: item for item in route["candidates"]} for route in routes})
    if len(fused) != len(expected_fused):
        return "fused rows do not match reciprocal-rank fusion"
    seen_fused: set[str] = set()
    for row, expected in zip(fused, expected_fused):
        if type(row) is not dict or set(row) != set(FUSED_KEYS):
            return "fused rows must have exactly chunk_id, score, route_names"
        chunk_id = row.get("chunk_id")
        if type(chunk_id) is not str or not chunk_id or chunk_id in seen_fused:
            return "fused chunk_id values must be unique"
        if row.get("route_names") != expected["route_names"]:
            return "fused route_names must list original then rewrite"
        if not _is_finite_number(row.get("score")) or row.get("score") != expected["score"]:
            return "fused score must be the prescribed reciprocal-rank sum"
        if chunk_id != expected["chunk_id"]:
            return "fused rows must sort by descending score then chunk_id"
        seen_fused.add(chunk_id)
    expected_hash = _sha256_canonical({key: value for key, value in plan.items() if key != "plan_sha256"})
    if plan.get("plan_sha256") != expected_hash:
        return "plan_sha256 does not match the canonical query_plan"
    return None


def validate_live_query_plan(
    workspace: Path,
    context: Mapping[str, Any],
    *,
    papers: Sequence[Mapping[str, Any]],
    stored: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Compare a successful context query_plan to live recomputed retrieval."""
    plan = context.get("query_plan")
    shaped = query_plan_shape_error(plan)
    if shaped is not None:
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": shaped,
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": stored.get("index_id") if type(stored) is dict else None,
        }
    assert type(plan) is dict
    if plan["original_query"] != context.get("query") or plan["rewrite"]["original_query"] != context.get("query"):
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "query_plan original_query must equal the context query",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": stored.get("index_id") if type(stored) is dict else None,
        }
    if "selected_paper_ids" in context and context.get("selected_paper_ids") != plan["selected_paper_ids"]:
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "query_plan selected_paper_ids must match the context selection",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": stored.get("index_id") if type(stored) is dict else None,
        }
    expected_workspace_id = _sha256_canonical({"workspace_root": str(workspace)})
    if plan["workspace_id"] != expected_workspace_id:
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "query_plan workspace_id does not match the explicit workspace",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": stored.get("index_id") if type(stored) is dict else None,
        }
    rewrite, rewrite_error = _checked_rewrite(plan["rewrite"], context["query"])
    if rewrite is None or rewrite_error is not None:
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": rewrite_error or "rewrite is invalid",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": stored.get("index_id") if type(stored) is dict else None,
        }
    retrieved = _retrieve_fused_plan(
        workspace,
        query=context["query"],
        rewrite=rewrite,
        paper_ids=plan["selected_paper_ids"],
    )
    if retrieved.get("ok") is not True:
        status = retrieved.get("status") if type(retrieved.get("status")) is str else INDEX_STALE
        if status == QUERY_REWRITE_INVALID:
            status = LIGHT_CONTEXT_INVALID
        return {
            "ok": False,
            "status": status,
            "message": retrieved.get("message") or status,
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": retrieved.get("index_id"),
        }
    live_plan = retrieved["plan"]
    try:
        if _canonical(plan) != _canonical(live_plan):
            return {
                "ok": False,
                "status": LIGHT_CONTEXT_INVALID,
                "message": "query_plan does not match live recomputed retrieval",
                "markdown": "",
                "citations": [],
                "workspace_root": str(workspace),
                "index_id": retrieved.get("index_id"),
            }
    except (TypeError, ValueError):
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "query_plan is not canonicalizable",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": retrieved.get("index_id"),
        }
    try:
        evidence = copy_evidence(context.get("evidence"))
    except ResearchError:
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "evidence rows are malformed",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": retrieved.get("index_id"),
        }
    live_evidence = retrieved["evidence"]
    if [row["chunk_id"] for row in evidence] != [row["chunk_id"] for row in live_plan["fused"]]:
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "evidence ids must match fused query_plan rows",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": retrieved.get("index_id"),
        }
    if [row["score"] for row in evidence] != [row["score"] for row in live_plan["fused"]]:
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "evidence scores must match fused query_plan rows",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": retrieved.get("index_id"),
        }
    if [row["chunk_id"] for row in evidence] != [row["chunk_id"] for row in live_evidence]:
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "evidence does not match live fused retrieval",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": retrieved.get("index_id"),
        }
    if not _evidence_matches_live(evidence, papers, plan["selected_paper_ids"]):
        return {
            "ok": False,
            "status": LIGHT_CONTEXT_INVALID,
            "message": "evidence row does not match a current derived source chunk",
            "markdown": "",
            "citations": [],
            "workspace_root": str(workspace),
            "index_id": retrieved.get("index_id"),
        }
    return None
