"""Evidence Q&A handoff: retrieve, export context, import an answer, check citations.

The current conversation model stays outside this module. Callers export a
bounded context, obtain a model document themselves, then import that document
here. Citation checks only test whether references point at provided evidence
identities; they are not a factual-correctness review. No model service, API
key, or network client is created.
"""
from __future__ import annotations

import copy
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from video_paper_wiki.catalog_store import DB_RELATIVE, catalog_status, mapping_from_database, query_catalog
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.retrieval import rank_hits, validate_retrieval_config

INDEX_STALE = "INDEX_STALE"
NO_RESULTS = "NO_RESULTS"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
INVALID_CITATION = "INVALID_CITATION"
OK = "OK"

LABELS = {
    INDEX_STALE: "旧索引",
    NO_RESULTS: "无结果",
    INSUFFICIENT_EVIDENCE: "证据不足",
    INVALID_CITATION: "无效引用",
    OK: "ok",
}

_STALE_CODES = frozenset({"CATALOG_STALE", "RETRIEVAL_GENERATION_MISMATCH"})
_PAPER_CITE = re.compile(r"\[@((?:arxiv|doi|openalex|sha256):[^\]\s]+)\]")
_EVU_CITE = re.compile(r"\[?(evu-[0-9a-f]{20})\]?")
_PAPER_ID = re.compile(r"^(?:arxiv|doi|openalex|sha256):.+$")
_SUCCESS_MESSAGE = (
    "Citations are a subset of the provided evidence identities. "
    "This is a structural citation check, not a factual-correctness review."
)


def _result(*, ok: bool, status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "status": status,
        "label": LABELS.get(status, status),
        "message": message,
    }
    payload.update(extra)
    return payload


def _stale(message: str, *, reasons: list[str] | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    extra: dict[str, Any] = {"papers": [], "evidence": []}
    if reasons is not None:
        extra["reasons"] = list(reasons)
    if details:
        extra["details"] = dict(details)
    return _result(ok=False, status=INDEX_STALE, message=message, **extra)


def _config_dict(retrieval_config: object) -> dict[str, Any]:
    if isinstance(retrieval_config, (str, Path)):
        raw = json.loads(Path(retrieval_config).read_text(encoding="utf-8"))
        return validate_retrieval_config(raw)
    return validate_retrieval_config(copy.deepcopy(retrieval_config))


def inspect_catalog(vault_root: Path | str, upstream_root: Path | str, retrieval_config: object) -> dict[str, Any]:
    """Return current catalog status or a distinct 旧索引 refusal."""
    try:
        status = catalog_status(vault_root, upstream_root, retrieval_config)
    except ContractError as exc:
        if exc.code in _STALE_CODES:
            return _stale("catalog index is stale and must be rebuilt", details={"code": exc.code})
        return _stale("catalog index is unavailable", details={"code": getattr(exc, "code", "")})
    if status.get("state") != "current":
        return _stale(
            "catalog index is stale and must be rebuilt",
            reasons=list(status.get("reasons") or []),
        )
    return _result(ok=True, status=OK, message="catalog is current", catalog=status)


def load_catalog_authority(vault_root: Path | str) -> dict[str, Any]:
    """Load mapping, locators, and paper rows from the disposable catalog."""
    path = Path(vault_root) / DB_RELATIVE
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        cols = [item[1] for item in con.execute("PRAGMA table_info(search_catalog_meta)")]
        rows = con.execute("SELECT * FROM search_catalog_meta").fetchall()
        if len(rows) != 1:
            raise ContractError("CATALOG_STALE", "catalog metadata is missing or duplicated", {})
        meta = dict(zip(cols, rows[0]))
        mapping = mapping_from_database(con, meta)
        papers = [
            {"paper_id": paper_id, "title": title}
            for paper_id, title in con.execute("SELECT paper_id, title FROM papers ORDER BY paper_id")
        ]
        return {"mapping": mapping, "papers": papers, "meta": meta}
    finally:
        con.close()


def _title_map(papers: list[dict[str, Any]]) -> dict[str, str]:
    return {item["paper_id"]: item["title"] for item in papers if type(item.get("paper_id")) is str}


def _locator_public(locator: object) -> dict[str, Any] | None:
    if type(locator) is not dict:
        return None
    return copy.deepcopy(locator)


def _bind_ranked_evidence(ranked: dict[str, Any], mapping: dict[str, Any], titles: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    units = {unit["evidence_unit_id"]: unit for unit in mapping["inventory"]["units"]}
    papers = []
    for row in ranked.get("papers") or []:
        if type(row) is not dict or type(row.get("paper_id")) is not str:
            continue
        item = {"paper_id": row["paper_id"], "score": row.get("score")}
        title = titles.get(row["paper_id"])
        if title is not None:
            item["title"] = title
        papers.append(item)
    evidence = []
    for row in ranked.get("evidence") or []:
        if type(row) is not dict or type(row.get("paper_id")) is not str:
            continue
        chunk_id = row.get("chunk_id")
        for unit_id in row.get("evidence_unit_ids") or []:
            unit = units.get(unit_id)
            if unit is None or unit.get("paper_id") != row["paper_id"]:
                continue
            item = {
                "paper_id": unit["paper_id"],
                "chunk_id": chunk_id,
                "evidence_unit_id": unit["evidence_unit_id"],
                "claim_id": unit["claim_id"],
                "locator_fingerprint": unit["locator_fingerprint"],
            }
            locator = _locator_public(unit.get("locator"))
            if locator is not None:
                item["locator"] = locator
            title = titles.get(unit["paper_id"])
            if title is not None:
                item["title"] = title
            evidence.append(item)
    return papers, evidence


def retrieve_evidence(
    *,
    question: str,
    vault_root: Path | str,
    upstream_root: Path | str,
    retrieval_config: object,
) -> dict[str, Any]:
    """Retrieve ranked papers and joined locators for one question."""
    inspected = inspect_catalog(vault_root, upstream_root, retrieval_config)
    if not inspected["ok"]:
        return inspected
    if type(question) is not str or not question.strip():
        return _result(
            ok=False,
            status=NO_RESULTS,
            message="question produced no catalog results",
            papers=[],
            evidence=[],
        )
    try:
        cfg = _config_dict(retrieval_config)
        query = query_catalog(vault_root, upstream_root, retrieval_config, question)
        authority = load_catalog_authority(vault_root)
        ranked = rank_hits(copy.deepcopy(query["raw_hits"]), authority["mapping"], cfg)
    except ContractError as exc:
        if exc.code in _STALE_CODES:
            return _stale("catalog index is stale and must be rebuilt", details={"code": exc.code})
        if exc.code == "QUERY_INVALID":
            return _result(ok=False, status=NO_RESULTS, message="question produced no catalog results", papers=[], evidence=[])
        return _stale("catalog query inputs differ", details={"code": getattr(exc, "code", "")})
    titles = _title_map(authority["papers"])
    papers, evidence = _bind_ranked_evidence(ranked, authority["mapping"], titles)
    catalog_meta = {
        "join_generation_sha256": query.get("join_generation_sha256"),
        "mapping_sha256": query.get("mapping_sha256"),
        "retrieval_config_sha256": query.get("retrieval_config_sha256"),
        "catalog_generation_sha256": query.get("catalog_generation_sha256"),
    }
    if not papers:
        return _result(
            ok=False,
            status=NO_RESULTS,
            message="question produced no catalog results",
            papers=[],
            evidence=[],
            catalog=catalog_meta,
        )
    if not evidence:
        return _result(
            ok=False,
            status=INSUFFICIENT_EVIDENCE,
            message="retrieved papers do not provide usable evidence locators",
            papers=papers,
            evidence=[],
            catalog=catalog_meta,
        )
    return _result(
        ok=True,
        status=OK,
        message="retrieved evidence from the current catalog",
        papers=papers,
        evidence=evidence,
        catalog=catalog_meta,
        ranking={"top5": list(ranked.get("top5") or []), "top10": list(ranked.get("top10") or [])},
    )


def export_qa_context(*, question: str, retrieved: dict[str, Any]) -> dict[str, Any]:
    """Export a bounded context document for the current conversation model."""
    if not retrieved.get("ok"):
        document = copy.deepcopy(retrieved)
        document["kind"] = "qa-context"
        document["question"] = question
        return document
    evidence = copy.deepcopy(retrieved.get("evidence") or [])
    papers = copy.deepcopy(retrieved.get("papers") or [])
    return _result(
        ok=True,
        status=OK,
        message="exported retrieval context for the current conversation model",
        kind="qa-context",
        question=question,
        papers=papers,
        evidence=evidence,
        catalog=copy.deepcopy(retrieved.get("catalog") or {}),
        ranking=copy.deepcopy(retrieved.get("ranking") or {}),
        instructions=(
            "Answer the question using only the papers and evidence identities below. "
            "Cite paper_id and evidence_unit_id values from this context. "
            "Do not invent papers, locators, or model calls. "
            "Later citation checks only test whether references point at these identities."
        ),
        citation_policy="structural-subset-of-provided-evidence",
    )


def export_from_question(
    *,
    question: str,
    vault_root: Path | str,
    upstream_root: Path | str,
    retrieval_config: object,
) -> dict[str, Any]:
    """Shipped Flow A export: question → retrieve → context document."""
    retrieved = retrieve_evidence(
        question=question,
        vault_root=vault_root,
        upstream_root=upstream_root,
        retrieval_config=retrieval_config,
    )
    return export_qa_context(question=question, retrieved=retrieved)


def _coerce_citation(item: object) -> dict[str, Any] | None:
    if type(item) is str:
        text = item.strip()
        if _EVU_CITE.fullmatch(text):
            return {"evidence_unit_id": text}
        if _PAPER_ID.match(text):
            return {"paper_id": text}
        return None
    if type(item) is not dict:
        return None
    cite: dict[str, Any] = {}
    for key in ("paper_id", "evidence_unit_id", "locator_fingerprint", "chunk_id", "claim_id"):
        value = item.get(key)
        if type(value) is str and value:
            cite[key] = value
    return cite or None


def _citations_from_text(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for match in _PAPER_CITE.finditer(text):
        found.append({"paper_id": match.group(1)})
    for match in re.finditer(r"\[(evu-[0-9a-f]{20})\]", text):
        found.append({"evidence_unit_id": match.group(1)})
    return found


def _dedupe_citations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = tuple(sorted((k, item[k]) for k in ("paper_id", "evidence_unit_id", "locator_fingerprint") if k in item))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def import_model_document(payload: object) -> dict[str, Any]:
    """Parse a caller-supplied model document. Never contacts a model."""
    value: object = payload
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if type(value) is str:
        text = value.strip()
        if not text:
            return {"text": "", "citations": []}
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return {"text": value, "citations": _dedupe_citations(_citations_from_text(value))}
    if type(value) is not dict:
        return {"text": "", "citations": []}
    text = ""
    for key in ("text", "answer", "markdown", "draft", "body"):
        candidate = value.get(key)
        if type(candidate) is str and candidate:
            text = candidate
            break
    parsed: list[dict[str, Any]] = []
    raw_citations = value.get("citations")
    if type(raw_citations) is list:
        for item in raw_citations:
            cite = _coerce_citation(item)
            if cite is not None:
                parsed.append(cite)
    parsed.extend(_citations_from_text(text))
    return {"text": text, "citations": _dedupe_citations(parsed)}


def provided_identities(context: dict[str, Any]) -> dict[str, Any]:
    evidence = [item for item in (context.get("evidence") or []) if type(item) is dict]
    papers = [item for item in (context.get("papers") or []) if type(item) is dict]
    by_unit = {item["evidence_unit_id"]: item for item in evidence if type(item.get("evidence_unit_id")) is str}
    paper_ids = {item["paper_id"] for item in papers if type(item.get("paper_id")) is str}
    paper_ids.update(item["paper_id"] for item in evidence if type(item.get("paper_id")) is str)
    fingerprints = {item["locator_fingerprint"] for item in evidence if type(item.get("locator_fingerprint")) is str}
    chunk_ids = {item["chunk_id"] for item in evidence if type(item.get("chunk_id")) is str}
    return {
        "evidence": evidence,
        "papers": papers,
        "by_unit": by_unit,
        "paper_ids": paper_ids,
        "fingerprints": fingerprints,
        "chunk_ids": chunk_ids,
    }


def _match_citation(cite: dict[str, Any], provided: dict[str, Any]) -> dict[str, Any] | None:
    unit = None
    unit_id = cite.get("evidence_unit_id")
    if type(unit_id) is str:
        unit = provided["by_unit"].get(unit_id)
        if unit is None:
            return None
    paper_id = cite.get("paper_id")
    if type(paper_id) is str:
        if paper_id not in provided["paper_ids"]:
            return None
        if unit is not None and unit["paper_id"] != paper_id:
            return None
    elif unit is not None:
        paper_id = unit["paper_id"]
    else:
        return None
    fingerprint = cite.get("locator_fingerprint")
    if type(fingerprint) is str:
        if unit is not None:
            if unit.get("locator_fingerprint") != fingerprint:
                return None
        elif fingerprint not in provided["fingerprints"]:
            return None
    chunk_id = cite.get("chunk_id")
    if type(chunk_id) is str:
        if unit is not None:
            if unit.get("chunk_id") != chunk_id:
                return None
        elif chunk_id not in provided["chunk_ids"]:
            return None
    bound = {"paper_id": paper_id}
    if unit is not None:
        bound["evidence_unit_id"] = unit["evidence_unit_id"]
        bound["locator_fingerprint"] = unit.get("locator_fingerprint")
        bound["claim_id"] = unit.get("claim_id")
        bound["chunk_id"] = unit.get("chunk_id")
        if unit.get("title") is not None:
            bound["title"] = unit["title"]
    elif type(fingerprint) is str:
        bound["locator_fingerprint"] = fingerprint
    return bound


def check_citations(*, context: dict[str, Any], imported: dict[str, Any]) -> dict[str, Any]:
    """Accept citations that are a subset of provided evidence identities."""
    if type(context) is dict and context.get("ok") is False:
        return copy.deepcopy(context)
    provided = provided_identities(context if type(context) is dict else {})
    if not provided["evidence"] and not provided["paper_ids"]:
        return _result(
            ok=False,
            status=INSUFFICIENT_EVIDENCE,
            message="no provided evidence is available for citation checks",
            papers=[],
            evidence=[],
            citations=[],
        )
    accepted: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for cite in imported.get("citations") or []:
        bound = _match_citation(cite, provided)
        if bound is None:
            invalid.append(copy.deepcopy(cite))
        else:
            accepted.append(bound)
    if invalid or not accepted:
        return _result(
            ok=False,
            status=INVALID_CITATION,
            message="citations do not point at the provided evidence identities",
            papers=copy.deepcopy(context.get("papers") or []),
            evidence=copy.deepcopy(context.get("evidence") or []),
            citations=accepted,
            invalid_citations=invalid,
            citation_check={"kind": "structural-subset", "accepted": False},
        )
    return _result(
        ok=True,
        status=OK,
        message=_SUCCESS_MESSAGE,
        kind="qa-answer",
        question=context.get("question"),
        text=imported.get("text") or "",
        papers=copy.deepcopy(context.get("papers") or []),
        evidence=copy.deepcopy(context.get("evidence") or []),
        citations=accepted,
        citation_check={"kind": "structural-subset", "accepted": True},
    )


def import_and_check(*, context: object, answer: object) -> dict[str, Any]:
    """Shipped Flow A import: caller-supplied model answer → citation check."""
    document = context
    if isinstance(document, (str, Path)) and Path(str(document)).is_file():
        document = json.loads(Path(document).read_text(encoding="utf-8"))
    if isinstance(answer, (str, Path)) and Path(str(answer)).is_file() and not (type(answer) is str and answer.lstrip().startswith("{")):
        answer = Path(answer).read_text(encoding="utf-8")
    imported = import_model_document(answer)
    if type(document) is not dict:
        return _result(ok=False, status=INVALID_CITATION, message="imported context is not a retrieval document", papers=[], evidence=[], citations=[])
    return check_citations(context=document, imported=imported)
