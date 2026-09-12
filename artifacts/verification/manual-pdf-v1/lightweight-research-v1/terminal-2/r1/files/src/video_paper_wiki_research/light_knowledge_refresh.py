"""Selective incremental knowledge refresh over complete or conservative inventories."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import validate_live_context
from video_paper_wiki_research.light_index import OK
from video_paper_wiki_research.light_knowledge import (
    EXTENDED_RECORD_SCHEMAS,
    KNOWLEDGE_DOCUMENT_SCHEMA,
    KNOWLEDGE_PAGE_NAME,
    KNOWLEDGE_REQUIREMENTS,
    KNOWLEDGE_STATE_DIR,
    LIGHT_KNOWLEDGE_CONFLICT,
    LIGHT_REFRESH_CONFLICT,
    LIGHT_REFRESH_INVALID,
    LIGHT_WORKSPACE_BUSY,
    REFRESH_RECORD_CONTEXT_SCHEMA,
    SECTION_KEYS,
    _closed,
    _evidence_from_chunks,
    _owned_record_bundle,
    _paper_snapshot,
    _record_bundle_ok,
    _records_root,
    _reject_irreplaceable_pointer,
    _set_head,
    _valid_chunk_inventory,
    _validate_document,
    _writing_context,
    canonical_bytes,
    current_head_record_id,
    require_hex64,
    require_paper_id,
    require_product_workspace,
    sha256_bytes,
    sha256_canonical,
    unknown_block,
    workspace_lock,
)
from video_paper_wiki_research.light_knowledge_batch import (
    FINAL_PROMPT,
    _cited_chunks,
    _coverage_for_record,
    _live_inputs,
    _paper_chunks,
    _publish_knowledge_record,
    _record_wrapper,
    create_batch_job,
)

REFRESH_PLAN_SCHEMA = "video-paper-wiki.light-knowledge-refresh-plan.v1"
DIFF_SCHEMA = "video-paper-wiki.light-knowledge-refresh-diff.v1"


def _closed_refresh(status: str, message: str, **extra: Any) -> dict[str, Any]:
    return _closed(status, message, **extra)


def _catch_locked(workspace: Path, fn: Any) -> dict[str, Any]:
    try:
        with workspace_lock(workspace):
            return fn()
    except ResearchError as exc:
        if exc.code in {
            LIGHT_WORKSPACE_BUSY,
            LIGHT_REFRESH_INVALID,
            LIGHT_REFRESH_CONFLICT,
            LIGHT_KNOWLEDGE_CONFLICT,
        }:
            return _closed_refresh(exc.code, exc.message)
        raise


def _base_inventory(bundle: Mapping[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    wrapper = bundle["identity"]["wrapper"]
    schema = wrapper.get("schema")
    if schema in EXTENDED_RECORD_SCHEMAS:
        coverage = wrapper.get("coverage")
        if type(coverage) is dict and _valid_chunk_inventory(coverage.get("inventory"), paper_id=bundle["paper_id"]):
            return [dict(row) for row in coverage["inventory"]], False
    return [dict(row) for row in bundle["chunks"]], True


def _stored_text_ok(old_row: Mapping[str, Any], live_chunk: Mapping[str, Any], evidence: list[dict[str, Any]]) -> bool:
    if live_chunk.get("page") != old_row.get("page") or live_chunk.get("text_sha256") != old_row.get("text_sha256"):
        return False
    for item in evidence:
        if item.get("chunk_id") != old_row.get("chunk_id"):
            continue
        if item.get("page") != old_row.get("page") or item.get("text_sha256") != old_row.get("text_sha256"):
            return False
        text = item.get("text")
        if type(text) is str:
            if sha256_bytes(text.encode("utf-8")) != old_row.get("text_sha256"):
                return False
            if text != live_chunk.get("text"):
                return False
    return True


def remap_live_chunks(
    old_inventory: list[dict[str, Any]],
    live_chunks: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str], list[str], list[str]]:
    old_groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for row in old_inventory:
        old_groups.setdefault((row["page"], row["text_sha256"]), []).append(row)
    live_groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for chunk in live_chunks:
        live_groups.setdefault((chunk["page"], chunk["text_sha256"]), []).append(chunk)
    mapping: dict[str, dict[str, Any]] = {}
    retained: list[str] = []
    changed_or_removed: list[str] = []
    retained_live: set[str] = set()
    for key, olds in old_groups.items():
        lives = live_groups.get(key, [])
        if len(olds) == 1 and len(lives) == 1 and _stored_text_ok(olds[0], lives[0], evidence):
            mapping[olds[0]["chunk_id"]] = lives[0]
            retained.append(olds[0]["chunk_id"])
            retained_live.add(lives[0]["chunk_id"])
        else:
            changed_or_removed.extend(item["chunk_id"] for item in olds)
    added = [chunk["chunk_id"] for chunk in live_chunks if chunk["chunk_id"] not in retained_live]
    return mapping, retained, added, changed_or_removed


def _remap_block(block: Mapping[str, Any], mapping: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    citations = block.get("citations")
    if type(citations) is not list:
        return unknown_block()
    remapped: list[str] = []
    for chunk_id in citations:
        live = mapping.get(chunk_id)
        if live is None:
            return unknown_block()
        remapped.append(live["chunk_id"])
    if block.get("status") == "unknown":
        return unknown_block()
    return {"citations": remapped, "status": block.get("status"), "text": block.get("text")}


def seed_document(document: Mapping[str, Any], mapping: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    sections = {key: _remap_block(document["sections"][key], mapping) for key in SECTION_KEYS}
    concepts: list[dict[str, Any]] = []
    for item in document.get("concepts") or []:
        if type(item) is not dict or type(item.get("citations")) is not list:
            continue
        remapped: list[str] = []
        valid = True
        for chunk_id in item["citations"]:
            live = mapping.get(chunk_id)
            if live is None:
                valid = False
                break
            remapped.append(live["chunk_id"])
        if valid and remapped:
            concepts.append({"citations": remapped, "name": item["name"]})
    return {
        "concepts": concepts,
        "paper_id": document["paper_id"],
        "schema": KNOWLEDGE_DOCUMENT_SCHEMA,
        "sections": sections,
    }


def _affected_sections(document: Mapping[str, Any], changed_or_removed: set[str]) -> list[str]:
    affected: list[str] = []
    sections = document.get("sections")
    if type(sections) is not dict:
        return affected
    for key in SECTION_KEYS:
        block = sections.get(key)
        if type(block) is not dict or type(block.get("citations")) is not list:
            continue
        if any(item in changed_or_removed for item in block["citations"]):
            affected.append(key)
    return affected


def _live_evidence(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    context = bundle["identity"]["wrapper"].get("context")
    if type(context) is dict and type(context.get("evidence")) is list:
        return [item for item in context["evidence"] if type(item) is dict]
    return []


def _plan_refresh_unlocked(workspace: Path, paper_id: str) -> dict[str, Any]:
    head = current_head_record_id(workspace, paper_id)
    if head is None:
        return _closed_refresh(
            LIGHT_REFRESH_INVALID,
            "refresh requires a validated current knowledge head for this paper",
            paper_id=paper_id,
        )
    bundle = _owned_record_bundle(workspace, record_id=head, paper_id=paper_id)
    if bundle is None:
        return _closed_refresh(LIGHT_REFRESH_CONFLICT, "current knowledge head is not a validated record", paper_id=paper_id)
    live = _live_inputs(workspace, paper_id)
    if type(live) is dict:
        return live
    stored, papers, paper = live
    live_chunks = _paper_chunks(papers, paper_id)
    if not live_chunks:
        return _closed_refresh(
            LIGHT_REFRESH_INVALID,
            "current paper has no derived chunks to refresh",
            paper_id=paper_id,
        )
    old_inventory, conservative = _base_inventory(bundle)
    mapping, retained, added, changed_or_removed = remap_live_chunks(
        old_inventory,
        live_chunks,
        _live_evidence(bundle),
    )
    seed = seed_document(bundle["document"], mapping)
    if conservative:
        partition_chunks = live_chunks
    else:
        by_id = {item["chunk_id"]: item for item in live_chunks}
        partition_chunks = [by_id[chunk_id] for chunk_id in added if chunk_id in by_id]
    created = create_batch_job(
        workspace,
        paper_id=paper_id,
        mode="refresh",
        stored=stored,
        paper=paper,
        inventory_chunks=live_chunks,
        batch_chunks=partition_chunks,
        expected_base_head=head,
        conservative_full_refresh=conservative,
        seed_document=seed,
    )
    if created.get("ok") is not True:
        return created
    created.update(
        {
            "schema": REFRESH_PLAN_SCHEMA,
            "base_record_id": head,
            "conservative_full_refresh": conservative,
            "retained": retained,
            "added": added if not conservative else [item["chunk_id"] for item in live_chunks],
            "changed_or_removed": changed_or_removed,
            "affected_sections": _affected_sections(bundle["document"], set(changed_or_removed)),
            "base_head_record_id": head,
        }
    )
    created["message"] = (
        "created conservative full refresh plan" if conservative else created["message"].replace("knowledge batch", "knowledge refresh")
    )
    return created


def plan_knowledge_refresh(workspace_root: Path, *, paper_id: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    ident = require_paper_id(paper_id, code=LIGHT_REFRESH_INVALID)
    return _catch_locked(workspace, lambda: _plan_refresh_unlocked(workspace, ident))


def _section_retain_allowed(block: Mapping[str, Any], mapping: Mapping[str, Mapping[str, Any]]) -> bool:
    citations = block.get("citations")
    if type(citations) is not list:
        return False
    return all(chunk_id in mapping for chunk_id in citations)


def _concept_retainable(concepts: list[Any], mapping: Mapping[str, Mapping[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    retainable: list[dict[str, Any]] = []
    all_ok = True
    for item in concepts:
        if type(item) is not dict or type(item.get("citations")) is not list:
            all_ok = False
            continue
        remapped: list[str] = []
        valid = True
        for chunk_id in item["citations"]:
            live = mapping.get(chunk_id)
            if live is None:
                valid = False
                all_ok = False
                break
            remapped.append(live["chunk_id"])
        if valid and remapped:
            retainable.append({"citations": remapped, "name": item["name"]})
        else:
            all_ok = False
    return all_ok, retainable


def _diff_body(
    workspace: Path,
    *,
    base_id: str,
    candidate_id: str,
) -> dict[str, Any]:
    base_dir = _records_root(workspace) / base_id
    cand_dir = _records_root(workspace) / candidate_id
    base = _record_bundle_ok(workspace, base_dir)
    candidate = _record_bundle_ok(workspace, cand_dir)
    if base is None or candidate is None:
        return _closed_refresh(LIGHT_REFRESH_INVALID, "base or candidate record is not a validated knowledge record")
    if base["paper_id"] != candidate["paper_id"]:
        return _closed_refresh(LIGHT_REFRESH_INVALID, "base and candidate records are not the same paper")
    cand_wrapper = candidate["identity"]["wrapper"]
    if cand_wrapper.get("schema") != REFRESH_RECORD_CONTEXT_SCHEMA:
        return _closed_refresh(LIGHT_REFRESH_INVALID, "candidate is not a refresh-mode knowledge record")
    provenance = cand_wrapper["coverage"]["provenance"]
    if provenance.get("base_record_id") != base_id or cand_wrapper["coverage"].get("mode") != "refresh":
        return _closed_refresh(LIGHT_REFRESH_INVALID, "candidate provenance does not bind this base record")
    live = _live_inputs(workspace, base["paper_id"])
    if type(live) is dict:
        return live
    stored, papers, paper = live
    live_chunks = _paper_chunks(papers, base["paper_id"])
    old_inventory, _conservative = _base_inventory(base)
    mapping, _retained, _added, _changed = remap_live_chunks(old_inventory, live_chunks, _live_evidence(base))
    sections: dict[str, Any] = {}
    for key in SECTION_KEYS:
        before = base["document"]["sections"][key]
        after = candidate["document"]["sections"][key]
        remapped = _remap_block(before, mapping)
        sections[key] = {
            "after": after,
            "before": before,
            "changed": canonical_bytes(remapped) != canonical_bytes(after),
            "retain_allowed": _section_retain_allowed(before, mapping),
        }
    before_concepts = base["document"]["concepts"]
    after_concepts = candidate["document"]["concepts"]
    concepts_ok, retainable = _concept_retainable(before_concepts, mapping)
    concepts = {
        "after": after_concepts,
        "before": before_concepts,
        "changed": canonical_bytes(before_concepts) != canonical_bytes(after_concepts)
        and canonical_bytes([{"citations": [mapping[c]["chunk_id"] for c in item["citations"] if c in mapping], "name": item["name"]} for item in before_concepts if type(item) is dict])
        != canonical_bytes(after_concepts),
        "retain_allowed": concepts_ok,
    }
    # keep changed true when remapped old concepts differ from candidate
    remapped_concepts = retainable if concepts_ok else retainable
    concepts["changed"] = canonical_bytes(remapped_concepts) != canonical_bytes(after_concepts)
    body = {
        "schema": DIFF_SCHEMA,
        "base_head_record_id": base_id,
        "candidate_record_id": candidate_id,
        "paper_id": base["paper_id"],
        "paper_snapshot": _paper_snapshot(paper),
        "index_id": stored["index_id"],
        "sections": sections,
        "concepts": concepts,
    }
    body["diff_sha256"] = sha256_canonical({key: body[key] for key in body if key != "diff_sha256"})
    return {
        "ok": True,
        "status": OK,
        "message": "exported deterministic knowledge refresh diff",
        **body,
    }


def export_knowledge_diff(workspace_root: Path, *, base_record_id: object, candidate_record_id: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    base_id = require_hex64(base_record_id, "base_record_id", code=LIGHT_REFRESH_INVALID)
    cand_id = require_hex64(candidate_record_id, "candidate_record_id", code=LIGHT_REFRESH_INVALID)
    return _catch_locked(workspace, lambda: _diff_body(workspace, base_id=base_id, candidate_id=cand_id))


def _require_accept_sections(value: object) -> list[str]:
    if type(value) is not list:
        raise ResearchError(LIGHT_REFRESH_INVALID, "accept_sections must be a list of section keys")
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if type(item) is not str or item not in SECTION_KEYS:
            raise ResearchError(LIGHT_REFRESH_INVALID, "accept_sections contains an unknown section key")
        if item in seen:
            raise ResearchError(LIGHT_REFRESH_INVALID, "accept_sections contains a duplicated section key")
        seen.add(item)
        result.append(item)
    return [key for key in SECTION_KEYS if key in seen]


def _same_diff(expected: Mapping[str, Any], supplied: Mapping[str, Any]) -> bool:
    skip = {"message"}
    for key in set(expected) | set(supplied):
        if key in skip:
            continue
        if key not in expected or key not in supplied:
            return False
        if canonical_bytes(expected[key]) != canonical_bytes(supplied[key]):
            return False
    return True


def _apply_unlocked(
    workspace: Path,
    diff: object,
    accept_sections: object,
    accept_concepts: object,
) -> dict[str, Any]:
    if type(diff) is not dict:
        return _closed_refresh(LIGHT_REFRESH_INVALID, "refresh diff must be an object")
    if type(accept_concepts) is not bool:
        return _closed_refresh(LIGHT_REFRESH_INVALID, "accept_concepts must be an explicit boolean")
    selected = _require_accept_sections(accept_sections)
    base_id = require_hex64(diff.get("base_head_record_id"), "base_head_record_id", code=LIGHT_REFRESH_INVALID)
    cand_id = require_hex64(diff.get("candidate_record_id"), "candidate_record_id", code=LIGHT_REFRESH_INVALID)
    expected = _diff_body(workspace, base_id=base_id, candidate_id=cand_id)
    if expected.get("ok") is not True:
        return expected
    if not _same_diff(expected, diff):
        return _closed_refresh(LIGHT_REFRESH_INVALID, "refresh diff does not match the recomputed current diff")
    paper_id = expected["paper_id"]
    head = current_head_record_id(workspace, paper_id)
    base = _owned_record_bundle(workspace, record_id=base_id, paper_id=paper_id)
    candidate = _record_bundle_ok(workspace, _records_root(workspace) / cand_id)
    if base is None or candidate is None:
        return _closed_refresh(LIGHT_REFRESH_CONFLICT, "base or candidate record is not usable")
    live = _live_inputs(workspace, paper_id)
    if type(live) is dict:
        return live
    stored, papers, paper = live
    live_chunks = _paper_chunks(papers, paper_id)
    old_inventory, _conservative = _base_inventory(base)
    mapping, _retained, _added, _changed = remap_live_chunks(old_inventory, live_chunks, _live_evidence(base))
    sections: dict[str, Any] = {}
    for key in SECTION_KEYS:
        if key in selected:
            sections[key] = candidate["document"]["sections"][key]
            continue
        before = base["document"]["sections"][key]
        if expected["sections"][key]["retain_allowed"]:
            sections[key] = _remap_block(before, mapping)
        else:
            sections[key] = unknown_block()
    if accept_concepts:
        concepts = candidate["document"]["concepts"]
    else:
        _ok, retainable = _concept_retainable(base["document"]["concepts"], mapping)
        concepts = retainable
    document = {
        "concepts": concepts,
        "paper_id": paper_id,
        "schema": KNOWLEDGE_DOCUMENT_SCHEMA,
        "sections": sections,
    }
    cited_ids = []
    for key in SECTION_KEYS:
        cited_ids.extend(sections[key].get("citations") or [])
    for item in concepts:
        cited_ids.extend(item.get("citations") or [])
    evidence = _cited_chunks(document, live_chunks)
    try:
        checked = _validate_document(
            document,
            paper_id=paper_id,
            evidence=_evidence_from_chunks(evidence),
            code=LIGHT_REFRESH_INVALID,
            max_chars=32_000,
        )
    except ResearchError as exc:
        if exc.code == LIGHT_REFRESH_INVALID:
            return _closed_refresh(exc.code, exc.message)
        raise
    if not checked:
        return _closed_refresh(LIGHT_REFRESH_INVALID, "selective refresh result is all unknown")
    cand_wrapper = candidate["identity"]["wrapper"]
    coverage = _coverage_for_record(
        {
            "batch_count": cand_wrapper["coverage"]["batch_count"],
            "inventory": cand_wrapper["coverage"]["inventory"],
            "plan_id": cand_wrapper["coverage"]["provenance"]["plan_id"],
            "plan_sha256": cand_wrapper["coverage"]["provenance"]["plan_sha256"],
            "planned_chunks": cand_wrapper["coverage"]["planned_chunks"],
        },
        mode="selection",
        merge_sha256=cand_wrapper["coverage"]["provenance"]["merge_sha256"],
        base_record_id=base_id,
        candidate_record_id=cand_id,
        accepted_sections=selected,
        accept_concepts=accept_concepts,
    )
    query = paper["title"] if type(paper.get("title")) is str and paper["title"].strip() else paper_id
    context = _writing_context(
        workspace=workspace,
        query=query,
        requirements=KNOWLEDGE_REQUIREMENTS,
        paper_ids=[paper_id],
        evidence=_evidence_from_chunks(evidence),
        index_id=str(stored["index_id"]),
        prompt=FINAL_PROMPT,
    )
    if context.get("ok") is not True:
        return context
    live_context = validate_live_context(workspace, context)
    if live_context.get("ok") is not True:
        return live_context
    wrapper = _record_wrapper(
        schema=REFRESH_RECORD_CONTEXT_SCHEMA,
        paper_id=paper_id,
        context=context,
        coverage=coverage,
        paper_snapshot=_paper_snapshot(paper),
        prompt=FINAL_PROMPT,
    )
    record_id = sha256_canonical({"document": checked, "wrapper": wrapper})
    if head == record_id:
        page = (_records_root(workspace) / record_id / KNOWLEDGE_PAGE_NAME).resolve()
        return {
            "ok": True,
            "status": OK,
            "message": "reused selective knowledge refresh record",
            "record_id": record_id,
            "paper_id": paper_id,
            "page_path": str(page),
            "source_status": "current",
            "reused": True,
            "accepted_sections": selected,
            "accept_concepts": accept_concepts,
        }
    if head != base_id:
        return _closed_refresh(
            LIGHT_REFRESH_CONFLICT,
            "expected base knowledge head changed before refresh adoption",
            paper_id=paper_id,
        )
    blocked = _reject_irreplaceable_pointer(workspace, kind="heads", relative_target=f"{KNOWLEDGE_STATE_DIR}/HEADS.json")
    if blocked is not None:
        return blocked
    published_id, reused = _publish_knowledge_record(
        workspace,
        paper=paper,
        document=checked,
        context=context,
        wrapper=wrapper,
    )
    if published_id != record_id:
        return _closed_refresh(LIGHT_REFRESH_CONFLICT, "refresh record identity drifted during publication")
    if current_head_record_id(workspace, paper_id) != base_id:
        return _closed_refresh(
            LIGHT_REFRESH_CONFLICT,
            "expected base knowledge head changed before refresh adoption",
            paper_id=paper_id,
        )
    _set_head(workspace, paper_id, record_id)
    page = (_records_root(workspace) / record_id / KNOWLEDGE_PAGE_NAME).resolve()
    return {
        "ok": True,
        "status": OK,
        "message": "reused selective knowledge refresh record" if reused else "published selective knowledge refresh record",
        "record_id": record_id,
        "paper_id": paper_id,
        "page_path": str(page),
        "source_status": "current",
        "reused": reused,
        "accepted_sections": selected,
        "accept_concepts": accept_concepts,
    }


def apply_knowledge_refresh(
    workspace_root: Path,
    diff: object,
    *,
    accept_sections: object,
    accept_concepts: object,
) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    return _catch_locked(
        workspace,
        lambda: _apply_unlocked(workspace, diff, accept_sections, accept_concepts),
    )
