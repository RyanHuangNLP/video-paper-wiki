"""Simple writing handoff: export paper-bounded context, import a draft, render Markdown.

This is not graph retrieval, not a writing Skill, and not PDF `draft.export`
paper-analysis JSON. The current conversation model stays outside this module.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Sequence

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.catalog_store import query_catalog
from video_paper_wiki.retrieval import rank_hits

from video_paper_wiki_research.qa import (
    INSUFFICIENT_EVIDENCE,
    INVALID_CITATION,
    NO_RESULTS,
    OK,
    _bind_ranked_evidence,
    _collector,
    _enrich_evidence_item,
    _config_dict,
    _result,
    _stale,
    _STALE_CODES,
    _SUCCESS_MESSAGE,
    _title_map,
    check_citations,
    import_model_document,
    inspect_catalog,
    load_catalog_authority,
    provided_identities,
)


def _normalize_paper_ids(paper_ids: Sequence[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in paper_ids:
        if type(item) is not str:
            continue
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _units_for_papers(
    mapping: dict[str, Any],
    paper_ids: Sequence[str],
    titles: dict[str, str],
    *,
    claim_texts: dict[str, str] | None = None,
    vault_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    selected = set(paper_ids)
    chunk_by_unit: dict[str, dict[str, Any]] = {}
    for chunk in mapping.get("chunks") or []:
        if type(chunk) is not dict:
            continue
        for unit_id in chunk.get("default_evidence_unit_ids") or []:
            chunk_by_unit[unit_id] = chunk
    evidence: list[dict[str, Any]] = []
    for unit in mapping.get("inventory", {}).get("units") or []:
        if type(unit) is not dict or unit.get("paper_id") not in selected:
            continue
        if not unit.get("default_eligible"):
            continue
        chunk = chunk_by_unit.get(unit["evidence_unit_id"])
        item = {
            "paper_id": unit["paper_id"],
            "chunk_id": None if chunk is None else chunk.get("chunk_id"),
            "evidence_unit_id": unit["evidence_unit_id"],
            "claim_id": unit["claim_id"],
            "locator_fingerprint": unit["locator_fingerprint"],
        }
        locator = unit.get("locator")
        if type(locator) is dict:
            item["locator"] = copy.deepcopy(locator)
        title = titles.get(unit["paper_id"])
        if title is not None:
            item["title"] = title
        _enrich_evidence_item(item, claim_texts=claim_texts, vault_root=vault_root)
        evidence.append(item)
    return evidence


def _papers_payload(selected: Sequence[str], catalog_papers: list[dict[str, Any]], ranked_papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    titles = _title_map(catalog_papers)
    scores = {item["paper_id"]: item.get("score") for item in ranked_papers}
    payload = []
    for paper_id in selected:
        item: dict[str, Any] = {"paper_id": paper_id}
        if paper_id in titles:
            item["title"] = titles[paper_id]
        if paper_id in scores:
            item["score"] = scores[paper_id]
        payload.append(item)
    return payload


def collect_writing_evidence(
    *,
    topic: str,
    paper_ids: Sequence[object],
    vault_root: Path | str,
    upstream_root: Path | str,
    retrieval_config: object,
) -> dict[str, Any]:
    """Load selected-paper evidence from the current catalog, using query ranking when present."""
    inspected = inspect_catalog(vault_root, upstream_root, retrieval_config)
    if not inspected["ok"]:
        return inspected
    selected = _normalize_paper_ids(paper_ids)
    if not selected:
        return _result(ok=False, status=NO_RESULTS, message="no selected papers were provided", papers=[], evidence=[])
    if type(topic) is not str or not topic.strip():
        return _result(ok=False, status=NO_RESULTS, message="topic produced no catalog results", papers=[], evidence=[])
    try:
        cfg = _config_dict(retrieval_config)
        query = query_catalog(
            vault_root,
            upstream_root,
            retrieval_config,
            topic,
            _collector=_collector(),
        )
        authority = load_catalog_authority(vault_root)
        ranked = rank_hits(copy.deepcopy(query["raw_hits"]), authority["mapping"], cfg)
    except ContractError as exc:
        if exc.code in _STALE_CODES:
            return _stale("catalog index is stale and must be rebuilt", details={"code": exc.code})
        if exc.code == "QUERY_INVALID":
            return _result(ok=False, status=NO_RESULTS, message="topic produced no catalog results", papers=[], evidence=[])
        return _stale("catalog query inputs differ", details={"code": getattr(exc, "code", "")})
    known = {item["paper_id"] for item in authority["papers"]}
    missing = [paper_id for paper_id in selected if paper_id not in known]
    catalog_meta = {
        "join_generation_sha256": query.get("join_generation_sha256"),
        "mapping_sha256": query.get("mapping_sha256"),
        "retrieval_config_sha256": query.get("retrieval_config_sha256"),
        "catalog_generation_sha256": query.get("catalog_generation_sha256"),
    }
    if missing:
        return _result(
            ok=False,
            status=NO_RESULTS,
            message="selected papers are not present in the current catalog",
            papers=[],
            evidence=[],
            missing_paper_ids=missing,
            catalog=catalog_meta,
        )
    titles = _title_map(authority["papers"])
    claim_texts = authority.get("claim_texts") or {}
    ranked_papers, ranked_evidence = _bind_ranked_evidence(
        ranked,
        authority["mapping"],
        titles,
        claim_texts=claim_texts,
        vault_root=vault_root,
    )
    selected_ranked = [item for item in ranked_evidence if item["paper_id"] in set(selected)]
    evidence = selected_ranked or _units_for_papers(
        authority["mapping"],
        selected,
        titles,
        claim_texts=claim_texts,
        vault_root=vault_root,
    )
    papers = _papers_payload(selected, authority["papers"], ranked_papers)
    if not evidence:
        return _result(
            ok=False,
            status=INSUFFICIENT_EVIDENCE,
            message="selected papers do not provide usable evidence locators",
            papers=papers,
            evidence=[],
            catalog=catalog_meta,
        )
    return _result(
        ok=True,
        status=OK,
        message="collected writing evidence from the current catalog",
        papers=papers,
        evidence=evidence,
        catalog=catalog_meta,
        ranking={"top5": list(ranked.get("top5") or []), "top10": list(ranked.get("top10") or [])},
    )


def export_writing_context(
    *,
    topic: str,
    requirements: str,
    collected: dict[str, Any],
) -> dict[str, Any]:
    """Export a bounded writing context for the current conversation model."""
    if not collected.get("ok"):
        document = copy.deepcopy(collected)
        document["kind"] = "writing-context"
        document["topic"] = topic
        document["requirements"] = requirements
        return document
    return _result(
        ok=True,
        status=OK,
        message="exported writing context for the current conversation model",
        kind="writing-context",
        topic=topic,
        requirements=requirements,
        papers=copy.deepcopy(collected.get("papers") or []),
        evidence=copy.deepcopy(collected.get("evidence") or []),
        catalog=copy.deepcopy(collected.get("catalog") or {}),
        ranking=copy.deepcopy(collected.get("ranking") or {}),
        instructions=(
            "Write an editable Markdown draft for the topic using only the selected papers, "
            "claim_text, and source_excerpt values below. claim_text is a provisional proposal; "
            "source_excerpt is the original document slice bound to the locator. "
            "Cite paper_id and evidence_unit_id values from this context. "
            "Return Markdown plus citations bound to these identities. "
            "Do not emit paper-analysis-draft JSON and do not invent papers or locators."
        ),
        citation_policy="structural-subset-of-provided-evidence",
    )


def export_from_request(
    *,
    topic: str,
    requirements: str,
    paper_ids: Sequence[object],
    vault_root: Path | str,
    upstream_root: Path | str,
    retrieval_config: object,
) -> dict[str, Any]:
    """Shipped Flow B export: topic + requirements + selected papers → writing context."""
    collected = collect_writing_evidence(
        topic=topic,
        paper_ids=paper_ids,
        vault_root=vault_root,
        upstream_root=upstream_root,
        retrieval_config=retrieval_config,
    )
    return export_writing_context(topic=topic, requirements=requirements, collected=collected)


def _references(context: dict[str, Any]) -> list[dict[str, Any]]:
    provided = provided_identities(context)
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for item in provided["evidence"]:
        key = (item["paper_id"], item.get("evidence_unit_id"))
        if key in seen:
            continue
        seen.add(key)
        ref = {"paper_id": item["paper_id"]}
        for field in ("title", "evidence_unit_id", "locator_fingerprint", "claim_id", "chunk_id"):
            if item.get(field) is not None:
                ref[field] = item[field]
        refs.append(ref)
    for item in provided["papers"]:
        key = (item["paper_id"], None)
        if any(ref["paper_id"] == item["paper_id"] for ref in refs):
            continue
        ref = {"paper_id": item["paper_id"]}
        if item.get("title") is not None:
            ref["title"] = item["title"]
        refs.append(ref)
    return refs


def render_markdown(*, topic: str, requirements: str, draft_text: str, references: list[dict[str, Any]]) -> str:
    lines = [f"# {topic}", ""]
    if requirements.strip():
        lines.extend([f"> {requirements.strip()}", ""])
    body = draft_text.strip() or "_No draft text was imported._"
    lines.extend([body, "", "## 参考文献", ""])
    for index, ref in enumerate(references, start=1):
        line = f"{index}. `{ref['paper_id']}`"
        if ref.get("title"):
            line += f" — {ref['title']}"
        if ref.get("evidence_unit_id"):
            line += f" — `{ref['evidence_unit_id']}`"
        if ref.get("locator_fingerprint"):
            line += f" — `{ref['locator_fingerprint']}`"
        lines.append(line)
    if not references:
        lines.append("_No catalog evidence was bound._")
    lines.append("")
    return "\n".join(lines)


def import_and_render(*, context: object, draft: object) -> dict[str, Any]:
    """Shipped Flow B import: caller-supplied draft → editable Markdown and references."""
    document = context
    if isinstance(document, (str, Path)) and Path(str(document)).is_file():
        document = json.loads(Path(document).read_text(encoding="utf-8"))
    if isinstance(draft, (str, Path)):
        path = Path(str(draft))
        if path.is_file() and not (type(draft) is str and str(draft).lstrip().startswith("{")):
            draft = path.read_text(encoding="utf-8")
    if type(document) is not dict:
        return _result(
            ok=False,
            status=INVALID_CITATION,
            message="imported context is not a writing document",
            papers=[],
            evidence=[],
            markdown="",
            references=[],
        )
    if document.get("ok") is False:
        failed = copy.deepcopy(document)
        failed.setdefault("markdown", "")
        failed.setdefault("references", [])
        return failed
    imported = import_model_document(draft)
    checked = check_citations(context=document, imported=imported)
    if not checked["ok"]:
        checked.setdefault("markdown", "")
        checked.setdefault("references", [])
        return checked
    references = _references(document)
    markdown = render_markdown(
        topic=str(document.get("topic") or ""),
        requirements=str(document.get("requirements") or ""),
        draft_text=str(imported.get("text") or ""),
        references=references,
    )
    return _result(
        ok=True,
        status=OK,
        message=_SUCCESS_MESSAGE,
        kind="editable-markdown",
        topic=document.get("topic"),
        requirements=document.get("requirements"),
        markdown=markdown,
        references=references,
        citations=checked.get("citations") or [],
        papers=copy.deepcopy(document.get("papers") or []),
        evidence=copy.deepcopy(document.get("evidence") or []),
        citation_check={"kind": "structural-subset", "accepted": True},
    )
