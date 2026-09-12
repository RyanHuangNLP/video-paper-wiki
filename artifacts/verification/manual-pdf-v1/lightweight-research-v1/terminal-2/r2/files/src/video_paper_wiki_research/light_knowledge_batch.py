"""Complete long-paper batch knowledge, rolling merge, and job backup recognition."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import validate_live_context
from video_paper_wiki_research.light_index import (
    INDEX_STALE,
    LIGHT_SELECTION_INVALID,
    OK,
    PAPER_ID_PATTERN,
    _derived_chunks,
    _workspace_paper_ids,
)
from video_paper_wiki_research.light_knowledge import (
    BATCH_JOBS_DIRNAME,
    BATCH_RECORD_CONTEXT_SCHEMA,
    HEX64,
    INSUFFICIENT_EVIDENCE,
    KNOWLEDGE_DOCUMENT_SCHEMA,
    KNOWLEDGE_PAGE_NAME,
    KNOWLEDGE_REQUIREMENTS,
    KNOWLEDGE_STATE_DIR,
    LIGHT_BATCH_CONFLICT,
    LIGHT_BATCH_INCOMPLETE,
    LIGHT_BATCH_INVALID,
    LIGHT_KNOWLEDGE_CONFLICT,
    LIGHT_KNOWLEDGE_INVALID,
    LIGHT_WORKSPACE_BUSY,
    MAX_BATCHES,
    MAX_DOCUMENT_CHARS,
    MAX_EXPORT_CHARS,
    MAX_EXPORT_CHUNKS,
    MAX_MERGE_CONTEXT_CHARS,
    REFRESH_RECORD_CONTEXT_SCHEMA,
    SECTION_KEYS,
    _closed,
    _evidence_from_chunks,
    _expected_parent_dirs,
    _inspect_tree,
    _load_persisted_object,
    _paper_by_id,
    _paper_snapshot,
    _publish_record,
    _raise,
    _record_bundle_ok,
    _record_files,
    _records_root,
    _reject_irreplaceable_pointer,
    _require_current_index,
    _set_head,
    _validate_document,
    _writing_context,
    canonical_bytes,
    canonical_char_count,
    current_head_record_id,
    inventory_row,
    persisted_bytes,
    pointer_head_record_id,
    publish_managed_file,
    require_hex64,
    require_nonneg_int,
    require_paper_id,
    require_product_workspace,
    sha256_canonical,
    sort_inventory,
    unknown_block,
    workspace_identity,
    workspace_lock,
)
PLAN_SCHEMA = "video-paper-wiki.light-knowledge-batch-plan.v1"
PLAN_IDENTITY_SCHEMA = "video-paper-wiki.light-knowledge-batch-plan-identity.v1"
BATCH_CONTEXT_SCHEMA = "video-paper-wiki.light-knowledge-batch-context.v1"
BATCH_ACCEPTED_SCHEMA = "video-paper-wiki.light-knowledge-batch-accepted.v1"
MERGE_CONTEXT_SCHEMA = "video-paper-wiki.light-knowledge-merge-context.v1"
MERGE_STEP_SCHEMA = "video-paper-wiki.light-knowledge-merge-step.v1"
COMPLETION_SCHEMA = "video-paper-wiki.light-knowledge-batch-completion.v1"
STATUS_SCHEMA = "video-paper-wiki.light-knowledge-batch-status.v1"

BATCH_PROMPT = (
    "Using only this batch's evidence chunks, author one "
    "video-paper-wiki.light-knowledge-document.v1 object. "
    "Do not use facts from other batches. All-unknown is allowed when this batch "
    "does not support a claim. Do not invent papers, pages, chunk ids, or facts."
)
MERGE_PROMPT = (
    "Merge the prior accumulator and the next batch document into one "
    "video-paper-wiki.light-knowledge-document.v1 object. "
    "Cite only chunk ids already cited by the accumulator or the next batch document. "
    "Do not resurrect discarded citations. Do not invent sources."
)
FINAL_PROMPT = (
    "Final merged structured knowledge document produced from complete batch coverage."
)
PLAN_FILE = "plan.json"
COMPLETION_FILE = "completion.json"
BATCHES_DIRNAME = "batches"
MERGES_DIRNAME = "merges"


def _jobs_root(workspace: Path) -> Path:
    return workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME


def _job_dir(workspace: Path, plan_id: str) -> Path:
    return _jobs_root(workspace) / plan_id


def _job_relative(plan_id: str, *parts: str) -> str:
    return "/".join((KNOWLEDGE_STATE_DIR, BATCH_JOBS_DIRNAME, plan_id, *parts))


def _file_target_id(plan_id: str, relative: str) -> str:
    return sha256_canonical({"plan_id": plan_id, "relative": relative})


def _empty_document(paper_id: str) -> dict[str, Any]:
    return {
        "concepts": [],
        "paper_id": paper_id,
        "schema": KNOWLEDGE_DOCUMENT_SCHEMA,
        "sections": {key: unknown_block() for key in SECTION_KEYS},
    }


def _plan_without_hash(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {key: plan[key] for key in plan if key != "plan_sha256"}


def _plan_content_hash(plan: Mapping[str, Any]) -> str:
    return sha256_canonical(_plan_without_hash(plan))


def _document_citation_set(document: Mapping[str, Any] | None) -> set[str]:
    if document is None:
        return set()
    used: set[str] = set()
    sections = document.get("sections")
    if type(sections) is dict:
        for key in SECTION_KEYS:
            block = sections.get(key)
            if type(block) is dict and type(block.get("citations")) is list:
                used.update(item for item in block["citations"] if type(item) is str)
    concepts = document.get("concepts")
    if type(concepts) is list:
        for item in concepts:
            if type(item) is dict and type(item.get("citations")) is list:
                used.update(value for value in item["citations"] if type(value) is str)
    return used


def _seed_document_shape_ok(seed: object, paper_id: str) -> bool:
    if type(seed) is not dict:
        return False
    if set(seed) != {"concepts", "paper_id", "schema", "sections"}:
        return False
    if seed.get("schema") != KNOWLEDGE_DOCUMENT_SCHEMA or seed.get("paper_id") != paper_id:
        return False
    sections = seed.get("sections")
    if type(sections) is not dict or set(sections) != set(SECTION_KEYS):
        return False
    if type(seed.get("concepts")) is not list:
        return False
    try:
        if canonical_char_count(seed) > MAX_DOCUMENT_CHARS:
            return False
    except ResearchError:
        return False
    return True


def _try_validate_document(
    document: object,
    *,
    paper_id: str,
    evidence: list[dict[str, Any]],
    allowed_citation_ids: set[str],
    allow_all_unknown: bool = True,
    code: str = LIGHT_BATCH_INVALID,
) -> dict[str, Any] | None:
    try:
        checked = _validate_document(
            document,
            paper_id=paper_id,
            evidence=evidence,
            allow_all_unknown=allow_all_unknown,
            allowed_citation_ids=allowed_citation_ids,
            code=code,
            max_chars=MAX_DOCUMENT_CHARS,
        )
    except (ResearchError, KeyError, TypeError, ValueError):
        return None
    if not checked:
        return None
    if canonical_bytes(checked) != canonical_bytes(document):
        return None
    return checked


def _partition_allowed_ids(plan: Mapping[str, Any], index: int) -> set[str] | None:
    partition = plan.get("partition")
    if type(partition) is not list or index < 0 or index >= len(partition):
        return None
    row = partition[index]
    if type(row) is not dict or type(row.get("chunk_ids")) is not list:
        return None
    ids = row["chunk_ids"]
    if any(type(item) is not str or not item for item in ids):
        return None
    return set(ids)


def _synthetic_partition_evidence(paper_id: str, chunk_ids: set[str]) -> list[dict[str, Any]]:
    return [{"chunk_id": chunk_id, "paper_id": paper_id} for chunk_id in sorted(chunk_ids)]


def _is_all_unknown(document: Mapping[str, Any]) -> bool:
    sections = document.get("sections")
    if type(sections) is not dict:
        return False
    return all(
        type(sections.get(key)) is dict and sections[key].get("status") == "unknown" for key in SECTION_KEYS
    )


def _closed_batch(status: str, message: str, **extra: Any) -> dict[str, Any]:
    return _closed(status, message, **extra)


def _catch_locked(workspace: Path, fn: Any) -> dict[str, Any]:
    try:
        with workspace_lock(workspace):
            return fn()
    except ResearchError as exc:
        if exc.code in {
            LIGHT_WORKSPACE_BUSY,
            LIGHT_BATCH_INVALID,
            LIGHT_BATCH_CONFLICT,
            LIGHT_BATCH_INCOMPLETE,
            LIGHT_KNOWLEDGE_CONFLICT,
            LIGHT_KNOWLEDGE_INVALID,
        }:
            return _closed_batch(exc.code, exc.message)
        raise


def _paper_chunks(papers: list[dict[str, Any]], paper_id: str) -> list[dict[str, Any]]:
    derived = [item for item in _derived_chunks(papers) if item["paper_id"] == paper_id]
    return sorted(derived, key=lambda item: (item["page"], item["text_start"], item["text_end"], item["chunk_id"]))


def partition_chunks(chunks: list[dict[str, Any]]) -> tuple[list[list[dict[str, Any]]], list[str]]:
    oversized = [item["chunk_id"] for item in chunks if len(item["text"]) > MAX_EXPORT_CHARS]
    if oversized:
        return [], oversized
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0
    for chunk in chunks:
        length = len(chunk["text"])
        if current and (len(current) >= MAX_EXPORT_CHUNKS or used + length > MAX_EXPORT_CHARS):
            batches.append(current)
            current = []
            used = 0
        current.append(chunk)
        used += length
    if current:
        batches.append(current)
    if len(batches) > MAX_BATCHES:
        return [], [item["chunk_id"] for item in chunks]
    return batches, []


def _partition_rows(batches: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, batch in enumerate(batches):
        rows.append(
            {
                "batch_index": index,
                "chunk_count": len(batch),
                "chunk_ids": [item["chunk_id"] for item in batch],
                "text_chars": sum(len(item["text"]) for item in batch),
            }
        )
    return rows


def _plan_identity(
    *,
    mode: str,
    workspace_id: str,
    index_id: str,
    paper_id: str,
    paper_snapshot: Mapping[str, Any],
    expected_base_head: str | None,
    inventory: list[dict[str, Any]],
    partition: list[dict[str, Any]],
    conservative_full_refresh: bool,
    seed_document: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "conservative_full_refresh": conservative_full_refresh,
        "expected_base_head": expected_base_head,
        "index_id": index_id,
        "inventory": inventory,
        "mode": mode,
        "paper_id": paper_id,
        "paper_snapshot": dict(paper_snapshot),
        "partition": partition,
        "schema": PLAN_IDENTITY_SCHEMA,
        "seed_document": seed_document,
        "workspace_id": workspace_id,
    }


def _plan_object(identity: Mapping[str, Any], plan_id: str) -> dict[str, Any]:
    body = {
        "batch_count": len(identity["partition"]),
        "conservative_full_refresh": identity["conservative_full_refresh"],
        "expected_base_head": identity["expected_base_head"],
        "index_id": identity["index_id"],
        "inventory": identity["inventory"],
        "mode": identity["mode"],
        "paper_id": identity["paper_id"],
        "paper_snapshot": identity["paper_snapshot"],
        "partition": identity["partition"],
        "plan_id": plan_id,
        "planned_chunks": len(identity["inventory"]),
        "schema": PLAN_SCHEMA,
        "seed_document": identity["seed_document"],
        "workspace_id": identity["workspace_id"],
    }
    body["plan_sha256"] = sha256_canonical(body)
    return body


def _valid_partition(value: object, *, inventory_ids: set[str]) -> bool:
    if type(value) is not list:
        return False
    seen: set[str] = set()
    for index, row in enumerate(value):
        if type(row) is not dict:
            return False
        if set(row) != {"batch_index", "chunk_count", "chunk_ids", "text_chars"}:
            return False
        if row.get("batch_index") != index or type(row["batch_index"]) is not int or type(row["batch_index"]) is bool:
            return False
        ids = row.get("chunk_ids")
        if type(ids) is not list or not ids:
            return False
        if type(row.get("chunk_count")) is not int or type(row["chunk_count"]) is bool or row["chunk_count"] != len(ids):
            return False
        if type(row.get("text_chars")) is not int or type(row["text_chars"]) is bool or row["text_chars"] < 0:
            return False
        for chunk_id in ids:
            if type(chunk_id) is not str or not chunk_id or chunk_id in seen or chunk_id not in inventory_ids:
                return False
            seen.add(chunk_id)
    return True


def _valid_plan_object(plan: object) -> bool:
    required = {
        "batch_count",
        "conservative_full_refresh",
        "expected_base_head",
        "index_id",
        "inventory",
        "mode",
        "paper_id",
        "paper_snapshot",
        "partition",
        "plan_id",
        "plan_sha256",
        "planned_chunks",
        "schema",
        "seed_document",
        "workspace_id",
    }
    if type(plan) is not dict or set(plan) != required:
        return False
    if plan.get("schema") != PLAN_SCHEMA:
        return False
    if type(plan.get("plan_id")) is not str or not HEX64.fullmatch(plan["plan_id"]):
        return False
    if type(plan.get("plan_sha256")) is not str or plan["plan_sha256"] != _plan_content_hash(plan):
        return False
    if type(plan.get("workspace_id")) is not str or not HEX64.fullmatch(plan["workspace_id"]):
        return False
    if type(plan.get("index_id")) is not str or not plan["index_id"]:
        return False
    if type(plan.get("paper_id")) is not str or not PAPER_ID_PATTERN.fullmatch(plan["paper_id"]):
        return False
    if plan.get("mode") not in {"full", "refresh"}:
        return False
    if type(plan.get("conservative_full_refresh")) is not bool:
        return False
    if plan["expected_base_head"] is not None:
        if type(plan["expected_base_head"]) is not str or not HEX64.fullmatch(plan["expected_base_head"]):
            return False
    from video_paper_wiki_research.light_knowledge import _valid_chunk_inventory, _valid_paper_snapshot

    if not _valid_paper_snapshot(plan.get("paper_snapshot")):
        return False
    if not _valid_chunk_inventory(plan.get("inventory"), paper_id=plan["paper_id"]):
        return False
    inventory = plan["inventory"]
    if type(plan.get("planned_chunks")) is not int or type(plan["planned_chunks"]) is bool:
        return False
    if plan["planned_chunks"] != len(inventory):
        return False
    if type(plan.get("batch_count")) is not int or type(plan["batch_count"]) is bool:
        return False
    if plan["batch_count"] != len(plan["partition"]):
        return False
    inventory_ids = {row["chunk_id"] for row in inventory}
    if not _valid_partition(plan.get("partition"), inventory_ids=inventory_ids):
        return False
    assigned = [chunk_id for row in plan["partition"] for chunk_id in row["chunk_ids"]]
    if plan["mode"] == "full":
        if set(assigned) != inventory_ids or len(assigned) != len(inventory_ids):
            return False
        if plan["seed_document"] is not None:
            return False
        if plan["conservative_full_refresh"] is not False:
            return False
    else:
        seed = plan.get("seed_document")
        if seed is not None:
            if not _seed_document_shape_ok(seed, plan["paper_id"]):
                return False
            if _document_citation_set(seed) - inventory_ids:
                return False
            if _try_validate_document(
                seed,
                paper_id=plan["paper_id"],
                evidence=_synthetic_partition_evidence(plan["paper_id"], inventory_ids),
                allowed_citation_ids=inventory_ids,
            ) is None:
                return False
        if len(assigned) != len(set(assigned)) or not set(assigned) <= inventory_ids:
            return False
        if plan["batch_count"] == 0 and assigned:
            return False
    identity = _plan_identity(
        mode=plan["mode"],
        workspace_id=plan["workspace_id"],
        index_id=plan["index_id"],
        paper_id=plan["paper_id"],
        paper_snapshot=plan["paper_snapshot"],
        expected_base_head=plan["expected_base_head"],
        inventory=plan["inventory"],
        partition=plan["partition"],
        conservative_full_refresh=plan["conservative_full_refresh"],
        seed_document=plan["seed_document"],
    )
    return sha256_canonical(identity) == plan["plan_id"]


def load_plan(workspace: Path, plan_id: str) -> dict[str, Any] | None:
    path = _job_dir(workspace, plan_id) / PLAN_FILE
    loaded = _load_persisted_object(path)
    if not _valid_plan_object(loaded):
        return None
    assert loaded is not None
    if loaded["plan_id"] != plan_id:
        return None
    return loaded


def _valid_accepted_batch(value: object, *, plan: Mapping[str, Any]) -> bool:
    required = {
        "batch_index",
        "context_sha256",
        "document",
        "document_sha256",
        "parent_sha256",
        "plan_id",
        "plan_sha256",
        "schema",
        "source",
    }
    if type(value) is not dict or set(value) != required:
        return False
    if value.get("schema") != BATCH_ACCEPTED_SCHEMA:
        return False
    if value.get("plan_id") != plan["plan_id"] or value.get("plan_sha256") != plan["plan_sha256"]:
        return False
    if value.get("parent_sha256") != plan["plan_sha256"]:
        return False
    index = value.get("batch_index")
    if type(index) is not int or type(index) is bool or index < 0 or index >= plan["batch_count"]:
        return False
    source = value.get("source")
    if type(source) is not dict or set(source) != {"index_id", "paper_snapshot"}:
        return False
    if source.get("index_id") != plan["index_id"]:
        return False
    if canonical_bytes(source.get("paper_snapshot")) != canonical_bytes(plan["paper_snapshot"]):
        return False
    document = value.get("document")
    if type(document) is not dict:
        return False
    if type(value.get("document_sha256")) is not str or value["document_sha256"] != sha256_canonical(document):
        return False
    if type(value.get("context_sha256")) is not str or not HEX64.fullmatch(value["context_sha256"]):
        return False
    allowed = _partition_allowed_ids(plan, index)
    if allowed is None:
        return False
    if _document_citation_set(document) - allowed:
        return False
    if _try_validate_document(
        document,
        paper_id=plan["paper_id"],
        evidence=_synthetic_partition_evidence(plan["paper_id"], allowed),
        allowed_citation_ids=allowed,
    ) is None:
        return False
    return True


def _valid_merge_step(value: object, *, plan: Mapping[str, Any]) -> bool:
    required = {
        "document",
        "document_sha256",
        "next_batch_document_hash",
        "parent_step_hash",
        "plan_id",
        "plan_sha256",
        "schema",
        "step",
    }
    if type(value) is not dict or set(value) != required:
        return False
    if value.get("schema") != MERGE_STEP_SCHEMA:
        return False
    if value.get("plan_id") != plan["plan_id"] or value.get("plan_sha256") != plan["plan_sha256"]:
        return False
    step = value.get("step")
    if type(step) is not int or type(step) is bool or step < 0 or step >= plan["batch_count"]:
        return False
    if not (
        value.get("parent_step_hash") is None
        or (type(value.get("parent_step_hash")) is str and HEX64.fullmatch(value["parent_step_hash"]))
    ):
        return False
    if type(value.get("next_batch_document_hash")) is not str or not HEX64.fullmatch(value["next_batch_document_hash"]):
        return False
    document = value.get("document")
    if type(document) is not dict:
        return False
    if type(value.get("document_sha256")) is not str or value["document_sha256"] != sha256_canonical(document):
        return False
    if not _seed_document_shape_ok(document, plan["paper_id"]):
        return False
    return True


def _valid_completion(value: object, *, plan: Mapping[str, Any]) -> bool:
    required = {
        "index_id",
        "merge_sha256",
        "paper_snapshot",
        "plan_id",
        "plan_sha256",
        "record_id",
        "schema",
        "status",
    }
    if type(value) is not dict or set(value) != required:
        return False
    if value.get("schema") != COMPLETION_SCHEMA:
        return False
    if value.get("plan_id") != plan["plan_id"] or value.get("plan_sha256") != plan["plan_sha256"]:
        return False
    if value.get("index_id") != plan["index_id"]:
        return False
    if canonical_bytes(value.get("paper_snapshot")) != canonical_bytes(plan["paper_snapshot"]):
        return False
    if value.get("status") not in {OK, INSUFFICIENT_EVIDENCE}:
        return False
    if not (
        value.get("merge_sha256") is None
        or (type(value.get("merge_sha256")) is str and HEX64.fullmatch(value["merge_sha256"]))
    ):
        return False
    if not (
        value.get("record_id") is None or (type(value.get("record_id")) is str and HEX64.fullmatch(value["record_id"]))
    ):
        return False
    if value["status"] == OK and value["record_id"] is None:
        return False
    if value["status"] == INSUFFICIENT_EVIDENCE and value["record_id"] is not None:
        return False
    if plan["batch_count"] == 0:
        return value["merge_sha256"] is None
    return type(value["merge_sha256"]) is str


def _job_tree(workspace: Path, plan_id: str) -> tuple[dict[str, bytes], set[str]] | None:
    directory = _job_dir(workspace, plan_id)
    if not directory.exists() and not directory.is_symlink():
        return None
    return _inspect_tree(directory)


def _accepted_batch(workspace: Path, plan: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    loaded = _load_persisted_object(_job_dir(workspace, plan["plan_id"]) / BATCHES_DIRNAME / f"{index}.json")
    if not _valid_accepted_batch(loaded, plan=plan):
        return None
    return loaded


def _merge_step(workspace: Path, plan: Mapping[str, Any], step: int) -> dict[str, Any] | None:
    loaded = _load_persisted_object(_job_dir(workspace, plan["plan_id"]) / MERGES_DIRNAME / f"{step}.json")
    if not _valid_merge_step(loaded, plan=plan):
        return None
    return loaded


def _completion(workspace: Path, plan: Mapping[str, Any]) -> dict[str, Any] | None:
    loaded = _load_persisted_object(_job_dir(workspace, plan["plan_id"]) / COMPLETION_FILE)
    if not _valid_completion(loaded, plan=plan):
        return None
    return loaded


def _merge_parent_state(plan: Mapping[str, Any], workspace: Path, step: int) -> tuple[dict[str, Any] | None, str | None] | None:
    if step == 0:
        seed = plan.get("seed_document")
        if seed is None:
            return None, None
        if not _seed_document_shape_ok(seed, plan["paper_id"]):
            return None
        return seed, sha256_canonical(seed)
    previous = _merge_step(workspace, plan, step - 1)
    if previous is None:
        return None
    return previous["document"], sha256_canonical(previous)


def _merge_step_binds(workspace: Path, plan: Mapping[str, Any], step: int, loaded: Mapping[str, Any]) -> bool:
    if loaded.get("step") != step:
        return False
    accepted = _accepted_batch(workspace, plan, step)
    if accepted is None:
        return False
    if loaded.get("next_batch_document_hash") != accepted.get("document_sha256"):
        return False
    parent = _merge_parent_state(plan, workspace, step)
    if parent is None:
        return False
    accumulator, parent_hash = parent
    if loaded.get("parent_step_hash") != parent_hash:
        return False
    permitted = _document_citation_set(accumulator) | _document_citation_set(accepted.get("document"))
    if _document_citation_set(loaded.get("document")) - permitted:
        return False
    if _try_validate_document(
        loaded.get("document"),
        paper_id=plan["paper_id"],
        evidence=_synthetic_partition_evidence(plan["paper_id"], permitted),
        allowed_citation_ids=permitted,
    ) is None:
        return False
    return True


def _accepted_merge_chain_ok(workspace: Path, plan: Mapping[str, Any], merges: set[int]) -> bool:
    if merges != set(range(len(merges))):
        return False
    for step in sorted(merges):
        loaded = _merge_step(workspace, plan, step)
        if loaded is None or not _merge_step_binds(workspace, plan, step, loaded):
            return False
    return True


def _final_merge_from_files(workspace: Path, plan: Mapping[str, Any]) -> dict[str, Any] | None:
    if plan["batch_count"] == 0:
        return None
    last = _merge_step(workspace, plan, plan["batch_count"] - 1)
    if last is None:
        return None
    return last


def _completion_binds_record(workspace: Path, plan: Mapping[str, Any], completion: Mapping[str, Any]) -> bool:
    expected_merge = None
    if plan["batch_count"] == 0:
        if completion.get("merge_sha256") is not None:
            return False
    else:
        last = _final_merge_from_files(workspace, plan)
        if last is None:
            return False
        expected_merge = sha256_canonical(last)
        if completion.get("merge_sha256") != expected_merge:
            return False
    if completion.get("status") == INSUFFICIENT_EVIDENCE:
        return completion.get("record_id") is None
    record_id = completion.get("record_id")
    if type(record_id) is not str or not HEX64.fullmatch(record_id):
        return False
    dest = _records_root(workspace) / record_id
    bundle = _record_bundle_ok(
        workspace,
        dest,
        check_ancestry=False,
        require_completed_job=False,
        bind_job_result=True,
    )
    if bundle is None or bundle["paper_id"] != plan["paper_id"]:
        return False
    wrapper = bundle["identity"]["wrapper"]
    if type(wrapper) is not dict:
        return False
    coverage = wrapper.get("coverage")
    if type(coverage) is not dict:
        return False
    provenance = coverage.get("provenance")
    if type(provenance) is not dict:
        return False
    if provenance.get("plan_id") != plan["plan_id"] or provenance.get("plan_sha256") != plan["plan_sha256"]:
        return False
    if provenance.get("merge_sha256") != completion.get("merge_sha256"):
        return False
    page = dest / KNOWLEDGE_PAGE_NAME
    if not page.is_file() or page.is_symlink():
        return False
    return True


def _expected_job_files(plan: Mapping[str, Any], *, complete: bool, accepted: set[int], merges: set[int]) -> set[str]:
    names = {PLAN_FILE}
    for index in accepted:
        names.add(f"{BATCHES_DIRNAME}/{index}.json")
    for step in merges:
        names.add(f"{MERGES_DIRNAME}/{step}.json")
    if complete:
        names.add(COMPLETION_FILE)
        for index in range(plan["batch_count"]):
            names.add(f"{BATCHES_DIRNAME}/{index}.json")
            names.add(f"{MERGES_DIRNAME}/{index}.json")
        if plan["batch_count"] == 0:
            names.discard(f"{BATCHES_DIRNAME}/0.json")
            names.discard(f"{MERGES_DIRNAME}/0.json")
            names = {PLAN_FILE, COMPLETION_FILE}
    return names


def classify_batch_job(workspace: Path, plan_id: str) -> dict[str, Any]:
    rel = f"{KNOWLEDGE_STATE_DIR}/{BATCH_JOBS_DIRNAME}/{plan_id}"
    directory = _job_dir(workspace, plan_id)
    if directory.is_symlink() or not directory.is_dir():
        return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"batch job {plan_id} is not a regular directory"}
    inspected = _inspect_tree(directory)
    if inspected is None:
        return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"batch job {plan_id} contains unsafe files"}
    files, dirs = inspected
    expected_dirs = _expected_parent_dirs(files)
    if dirs != expected_dirs:
        extra_dirs = sorted(dirs - expected_dirs)
        label = extra_dirs[0] if extra_dirs else "layout"
        return {
            "kind": "conflict",
            "path": rel + "/" + label,
            "plan_id": plan_id,
            "message": f"batch job {plan_id} contains unknown or extra directory {label}",
        }
    plan = load_plan(workspace, plan_id)
    if plan is None:
        return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"batch job {plan_id} plan is missing or tampered"}
    accepted: set[int] = set()
    merges: set[int] = set()
    extra = set(files) - {PLAN_FILE, COMPLETION_FILE}
    for name in list(extra):
        if name.startswith(f"{BATCHES_DIRNAME}/") and name.endswith(".json"):
            token = name[len(BATCHES_DIRNAME) + 1 : -5]
            if token.isdigit() and type(int(token)) is int:
                index = int(token)
                if _accepted_batch(workspace, plan, index) is not None and f"{index}.json" == Path(name).name:
                    accepted.add(index)
                    continue
        if name.startswith(f"{MERGES_DIRNAME}/") and name.endswith(".json"):
            token = name[len(MERGES_DIRNAME) + 1 : -5]
            if token.isdigit():
                step = int(token)
                if _merge_step(workspace, plan, step) is not None and f"{step}.json" == Path(name).name:
                    merges.add(step)
                    continue
        return {
            "kind": "conflict",
            "path": rel + "/" + name,
            "plan_id": plan_id,
            "message": f"batch job {plan_id} contains unknown or tampered file {name}",
        }
    if not _accepted_merge_chain_ok(workspace, plan, merges):
        return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"batch job {plan_id} merge chain is not contiguous"}
    if COMPLETION_FILE in files:
        completion = _completion(workspace, plan)
        if completion is None:
            return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"batch job {plan_id} completion is tampered"}
        expected = _expected_job_files(plan, complete=True, accepted=accepted, merges=merges)
        if set(files) != expected:
            return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"completed batch job {plan_id} file set is incomplete or extra"}
        if plan["batch_count"]:
            if accepted != set(range(plan["batch_count"])) or merges != set(range(plan["batch_count"])):
                return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"completed batch job {plan_id} is missing accepted steps"}
        elif accepted or merges:
            return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"zero-batch job {plan_id} has unexpected step files"}
        if not _completion_binds_record(workspace, plan, completion):
            return {
                "kind": "conflict",
                "path": rel,
                "plan_id": plan_id,
                "message": f"completed batch job {plan_id} completion does not bind the actual final record",
            }
        return {
            "kind": "completed",
            "path": rel,
            "plan_id": plan_id,
            "plan": plan,
            "completion": completion,
            "accepted_batches": sorted(accepted),
            "accepted_merges": sorted(merges),
            "missing_batches": [],
            "next_merge_step": None,
            "message": f"completed batch job {plan_id} is includable history",
        }
    missing = [index for index in range(plan["batch_count"]) if index not in accepted]
    next_merge = 0
    while next_merge in merges:
        next_merge += 1
    if next_merge > plan["batch_count"]:
        next_merge = plan["batch_count"]
    if merges != set(range(next_merge)):
        return {"kind": "conflict", "path": rel, "plan_id": plan_id, "message": f"batch job {plan_id} merge chain is not contiguous"}
    return {
        "kind": "pending",
        "path": rel,
        "plan_id": plan_id,
        "plan": plan,
        "accepted_batches": sorted(accepted),
        "accepted_merges": sorted(merges),
        "missing_batches": missing,
        "next_merge_step": next_merge if plan["batch_count"] else None,
        "message": (
            f"pending batch job {plan_id} must be finished or retried "
            f"(missing batches {missing}; next merge step {next_merge if plan['batch_count'] else 'none'})"
        ),
    }


def validate_job_provenance(
    workspace: Path,
    *,
    plan_id: str,
    plan_sha256: str,
    merge_sha256: object,
) -> bool:
    if type(plan_id) is not str or not HEX64.fullmatch(plan_id):
        return False
    if type(plan_sha256) is not str or not HEX64.fullmatch(plan_sha256):
        return False
    plan = load_plan(workspace, plan_id)
    if plan is None or plan["plan_sha256"] != plan_sha256:
        return False
    classified = classify_batch_job(workspace, plan_id)
    if classified["kind"] != "completed":
        return False
    if merge_sha256 is None:
        return plan["batch_count"] == 0
    if plan["batch_count"] == 0:
        return False
    if type(merge_sha256) is not str or not HEX64.fullmatch(merge_sha256):
        return False
    last = _final_merge_from_files(workspace, plan)
    if last is None or sha256_canonical(last) != merge_sha256:
        return False
    return _accepted_merge_chain_ok(workspace, plan, set(classified.get("accepted_merges") or []))


def knowledge_batch_backup_blockers(workspace: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    root = _jobs_root(workspace)
    if not root.exists() and not root.is_symlink():
        return rows
    if root.is_symlink() or not root.is_dir():
        return [
            {
                "path": f"{KNOWLEDGE_STATE_DIR}/{BATCH_JOBS_DIRNAME}",
                "status": LIGHT_BATCH_CONFLICT,
                "message": "batch-jobs path is not a regular directory",
            }
        ]
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        rel = f"{KNOWLEDGE_STATE_DIR}/{BATCH_JOBS_DIRNAME}/{item.name}"
        if item.is_symlink() or not item.is_dir() or not HEX64.fullmatch(item.name):
            rows.append(
                {
                    "path": rel,
                    "status": LIGHT_BATCH_CONFLICT,
                    "message": f"unknown or unsafe batch job entry {item.name}",
                }
            )
            continue
        classified = classify_batch_job(workspace, item.name)
        if classified["kind"] == "completed":
            continue
        status = LIGHT_BATCH_CONFLICT if classified["kind"] == "conflict" else LIGHT_BATCH_INCOMPLETE
        rows.append({"path": classified["path"], "status": status, "message": classified["message"]})
    return rows


def _live_inputs(workspace: Path, paper_id: str) -> dict[str, Any] | tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    loaded = _require_current_index(workspace)
    if type(loaded) is dict:
        loaded.setdefault("paper_id", paper_id)
        return loaded
    stored, papers = loaded
    present = {paper["paper_id"] for paper in papers}
    if paper_id not in present or paper_id not in _workspace_paper_ids(workspace):
        return _closed_batch(
            LIGHT_SELECTION_INVALID,
            "selected paper_id is not present in the current workspace",
            paper_id=paper_id,
        )
    paper = _paper_by_id(papers, paper_id)
    assert paper is not None
    return stored, papers, paper


def _current_plan_binding(workspace: Path, plan: Mapping[str, Any]) -> dict[str, Any] | None:
    live = _live_inputs(workspace, plan["paper_id"])
    if type(live) is dict:
        return live
    stored, papers, paper = live
    if stored.get("index_id") != plan["index_id"]:
        return _closed_batch(INDEX_STALE, "batch plan index_id is not the current index", plan_id=plan["plan_id"])
    if _paper_snapshot(paper) != plan["paper_snapshot"]:
        return _closed_batch(INDEX_STALE, "batch plan paper snapshot is not current", plan_id=plan["plan_id"], paper_id=plan["paper_id"])
    live_chunks = _paper_chunks(papers, plan["paper_id"])
    expected_inventory = sort_inventory(inventory_row(item) for item in live_chunks)
    if canonical_bytes(expected_inventory) != canonical_bytes(plan["inventory"]):
        return _closed_batch(
            LIGHT_BATCH_INVALID,
            "batch plan is not bound to the current complete derived inventory",
            plan_id=plan["plan_id"],
            paper_id=plan["paper_id"],
        )
    if plan["mode"] == "full":
        batches, gaps = partition_chunks(live_chunks)
        if gaps or canonical_bytes(_partition_rows(batches)) != canonical_bytes(plan["partition"]):
            return _closed_batch(
                LIGHT_BATCH_INVALID,
                "batch plan partition is not the current complete derived partition",
                plan_id=plan["plan_id"],
                paper_id=plan["paper_id"],
            )
        if plan.get("seed_document") is not None:
            return _closed_batch(LIGHT_BATCH_INVALID, "full batch plan cannot carry a refresh seed", plan_id=plan["plan_id"])
        return None
    from video_paper_wiki_research.light_knowledge_refresh import expected_refresh_plan_parts

    parts = expected_refresh_plan_parts(workspace, plan, papers)
    if parts.get("ok") is not True:
        return parts
    if canonical_bytes(parts["partition"]) != canonical_bytes(plan["partition"]):
        return _closed_batch(
            LIGHT_BATCH_INVALID,
            "refresh plan partition is not the current same-paper delta partition",
            plan_id=plan["plan_id"],
            paper_id=plan["paper_id"],
        )
    if canonical_bytes(parts["seed_document"]) != canonical_bytes(plan.get("seed_document")):
        return _closed_batch(
            LIGHT_BATCH_INVALID,
            "refresh plan seed is not the recomputed same-paper base summary",
            plan_id=plan["plan_id"],
            paper_id=plan["paper_id"],
        )
    if parts["conservative_full_refresh"] != plan["conservative_full_refresh"]:
        return _closed_batch(
            LIGHT_BATCH_INVALID,
            "refresh plan conservative flag does not match the validated base inventory",
            plan_id=plan["plan_id"],
        )
    return None


def _require_resumable_plan(workspace: Path, plan: Mapping[str, Any]) -> dict[str, Any] | None:
    if plan["workspace_id"] != workspace_identity(workspace):
        return _closed_batch(
            LIGHT_BATCH_INVALID,
            "batch job belongs to a different workspace identity and cannot be resumed",
            plan_id=plan["plan_id"],
        )
    return _current_plan_binding(workspace, plan)


def _publish_job_file(workspace: Path, plan_id: str, relative: str, payload: Mapping[str, Any]) -> bool:
    return publish_managed_file(
        workspace,
        kind="batch-file",
        target_id=_file_target_id(plan_id, relative),
        relative_target=_job_relative(plan_id, *relative.split("/")),
        payload=payload,
    )


def create_batch_job(
    workspace: Path,
    *,
    paper_id: str,
    mode: str,
    stored: Mapping[str, Any],
    paper: Mapping[str, Any],
    inventory_chunks: list[dict[str, Any]],
    batch_chunks: list[dict[str, Any]],
    expected_base_head: str | None,
    conservative_full_refresh: bool = False,
    seed_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    batches, gaps = partition_chunks(batch_chunks)
    if gaps:
        return _closed_batch(
            LIGHT_BATCH_INVALID,
            "paper exceeds the supported batch count or contains an oversized chunk",
            paper_id=paper_id,
            schema=PLAN_SCHEMA,
            processing_complete=False,
            planned_chunks=len(inventory_chunks),
            processed_chunks=0,
            batch_count=0,
            gap_chunk_ids=gaps,
        )
    inventory = sort_inventory(inventory_row(item) for item in inventory_chunks)
    partition = _partition_rows(batches)
    identity = _plan_identity(
        mode=mode,
        workspace_id=workspace_identity(workspace),
        index_id=str(stored["index_id"]),
        paper_id=paper_id,
        paper_snapshot=_paper_snapshot(paper),
        expected_base_head=expected_base_head,
        inventory=inventory,
        partition=partition,
        conservative_full_refresh=conservative_full_refresh,
        seed_document=seed_document,
    )
    plan_id = sha256_canonical(identity)
    plan = _plan_object(identity, plan_id)
    reused = _publish_job_file(workspace, plan_id, PLAN_FILE, plan)
    return {
        "ok": True,
        "status": OK,
        "message": "reused knowledge batch plan" if reused else "created knowledge batch plan",
        "schema": PLAN_SCHEMA,
        "plan_id": plan_id,
        "plan_sha256": plan["plan_sha256"],
        "paper_id": paper_id,
        "mode": mode,
        "batch_count": plan["batch_count"],
        "planned_chunks": plan["planned_chunks"],
        "processed_chunks": 0,
        "processing_complete": False,
        "gap_chunk_ids": [],
        "conservative_full_refresh": conservative_full_refresh,
        "reused": reused,
        "expected_base_head": expected_base_head,
    }


def _plan_unlocked(workspace: Path, paper_id: str) -> dict[str, Any]:
    live = _live_inputs(workspace, paper_id)
    if type(live) is dict:
        return live
    stored, papers, paper = live
    chunks = _paper_chunks(papers, paper_id)
    if not chunks:
        return _closed_batch(
            INSUFFICIENT_EVIDENCE,
            "no derived evidence is available for complete batch knowledge",
            paper_id=paper_id,
            schema=PLAN_SCHEMA,
            processing_complete=False,
            planned_chunks=0,
            processed_chunks=0,
            batch_count=0,
            gap_chunk_ids=[],
        )
    head = current_head_record_id(workspace, paper_id)
    return create_batch_job(
        workspace,
        paper_id=paper_id,
        mode="full",
        stored=stored,
        paper=paper,
        inventory_chunks=chunks,
        batch_chunks=chunks,
        expected_base_head=head,
    )


def plan_knowledge_batches(workspace_root: Path, *, paper_id: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    try:
        ident = require_paper_id(paper_id, code=LIGHT_BATCH_INVALID)
    except ResearchError as exc:
        if exc.code == LIGHT_BATCH_INVALID:
            return _closed_batch(exc.code, exc.message)
        raise
    return _catch_locked(workspace, lambda: _plan_unlocked(workspace, ident))


def _batch_chunks(plan: Mapping[str, Any], papers: list[dict[str, Any]], batch_index: int) -> list[dict[str, Any]]:
    wanted = list(plan["partition"][batch_index]["chunk_ids"])
    by_id = {item["chunk_id"]: item for item in _paper_chunks(papers, plan["paper_id"])}
    return [by_id[chunk_id] for chunk_id in wanted if chunk_id in by_id]


def _batch_export_unlocked(workspace: Path, plan_id: str, batch_index: int) -> dict[str, Any]:
    plan = load_plan(workspace, plan_id)
    if plan is None:
        classified = classify_batch_job(workspace, plan_id) if (_job_dir(workspace, plan_id).exists() or _job_dir(workspace, plan_id).is_symlink()) else None
        if classified is not None and classified["kind"] == "conflict":
            return _closed_batch(LIGHT_BATCH_CONFLICT, classified["message"], plan_id=plan_id)
        return _closed_batch(LIGHT_BATCH_INVALID, "batch plan_id is not a validated job", plan_id=plan_id)
    blocked = _require_resumable_plan(workspace, plan)
    if blocked is not None:
        return blocked
    if batch_index < 0 or batch_index >= plan["batch_count"]:
        return _closed_batch(LIGHT_BATCH_INVALID, "batch_index is outside the planned partition", plan_id=plan_id, batch_index=batch_index)
    live = _live_inputs(workspace, plan["paper_id"])
    if type(live) is dict:
        return live
    stored, papers, paper = live
    chunks = _batch_chunks(plan, papers, batch_index)
    if [item["chunk_id"] for item in chunks] != plan["partition"][batch_index]["chunk_ids"]:
        return _closed_batch(INDEX_STALE, "planned batch chunks are not present in the current source", plan_id=plan_id)
    query = paper["title"] if type(paper.get("title")) is str and paper["title"].strip() else plan["paper_id"]
    context = _writing_context(
        workspace=workspace,
        query=query,
        requirements=KNOWLEDGE_REQUIREMENTS,
        paper_ids=[plan["paper_id"]],
        evidence=_evidence_from_chunks(chunks),
        index_id=str(stored["index_id"]),
        prompt=BATCH_PROMPT,
    )
    if context.get("ok") is not True:
        payload = dict(context)
        payload["schema"] = BATCH_CONTEXT_SCHEMA
        payload["plan_id"] = plan_id
        return payload
    live_context = validate_live_context(workspace, context)
    if live_context.get("ok") is not True:
        return live_context
    accepted = [index for index in range(plan["batch_count"]) if _accepted_batch(workspace, plan, index) is not None]
    processed = 0
    for index in accepted:
        processed += plan["partition"][index]["chunk_count"]
    wrapper = {
        "ok": True,
        "status": OK,
        "message": "exported knowledge batch context for the current conversation model",
        "schema": BATCH_CONTEXT_SCHEMA,
        "plan_id": plan_id,
        "plan_sha256": plan["plan_sha256"],
        "batch_index": batch_index,
        "batch_count": plan["batch_count"],
        "coverage": {
            "batch_chunk_ids": list(plan["partition"][batch_index]["chunk_ids"]),
            "batch_index": batch_index,
            "gap_chunk_ids": [],
            "inventory": [inventory_row(item) for item in chunks],
            "mode": plan["mode"],
            "planned_chunks": plan["planned_chunks"],
            "processed_chunks": processed,
            "processing_complete": False,
        },
        "paper_snapshot": dict(plan["paper_snapshot"]),
        "context": context,
        "prompt": BATCH_PROMPT,
    }
    wrapper["context_sha256"] = sha256_canonical(context)
    wrapper["wrapper_sha256"] = sha256_canonical({key: wrapper[key] for key in wrapper if key != "wrapper_sha256"})
    return wrapper


def export_knowledge_batch(workspace_root: Path, *, plan_id: object, batch_index: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    try:
        ident = require_hex64(plan_id, "plan_id", code=LIGHT_BATCH_INVALID)
        index = require_nonneg_int(batch_index, "batch_index", code=LIGHT_BATCH_INVALID)
    except ResearchError as exc:
        if exc.code == LIGHT_BATCH_INVALID:
            return _closed_batch(exc.code, exc.message)
        raise
    return _catch_locked(workspace, lambda: _batch_export_unlocked(workspace, ident, index))


def _export_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    body = {key: payload[key] for key in payload if key not in {"message", "wrapper_sha256"}}
    coverage = body.get("coverage")
    if type(coverage) is dict:
        coverage = {key: coverage[key] for key in coverage if key != "processed_chunks"}
        body["coverage"] = coverage
    return body


def _same_export(expected: Mapping[str, Any], wrapper: Mapping[str, Any]) -> bool:
    return canonical_bytes(_export_identity(expected)) == canonical_bytes(_export_identity(wrapper))


def _import_batch_unlocked(workspace: Path, wrapper: object, document: object) -> dict[str, Any]:
    if type(wrapper) is not dict:
        return _closed_batch(LIGHT_BATCH_INVALID, "batch context must be an object")
    required = {
        "ok",
        "status",
        "message",
        "schema",
        "plan_id",
        "plan_sha256",
        "batch_index",
        "batch_count",
        "coverage",
        "paper_snapshot",
        "context",
        "prompt",
        "context_sha256",
        "wrapper_sha256",
    }
    if set(wrapper) != required:
        return _closed_batch(LIGHT_BATCH_INVALID, "batch context wrapper keys are invalid")
    if wrapper.get("schema") != BATCH_CONTEXT_SCHEMA:
        return _closed_batch(LIGHT_BATCH_INVALID, "batch context schema is invalid")
    plan_id = require_hex64(wrapper.get("plan_id"), "plan_id", code=LIGHT_BATCH_INVALID)
    batch_index = require_nonneg_int(wrapper.get("batch_index"), "batch_index", code=LIGHT_BATCH_INVALID)
    expected = _batch_export_unlocked(workspace, plan_id, batch_index)
    if expected.get("ok") is not True:
        return expected
    if not _same_export(expected, wrapper):
        return _closed_batch(LIGHT_BATCH_INVALID, "batch context does not match a current export", plan_id=plan_id)
    plan = load_plan(workspace, plan_id)
    assert plan is not None
    live = _live_inputs(workspace, plan["paper_id"])
    if type(live) is dict:
        return live
    _stored, papers, _paper = live
    chunks = _batch_chunks(plan, papers, batch_index)
    try:
        checked = _validate_document(
            document,
            paper_id=plan["paper_id"],
            evidence=_evidence_from_chunks(chunks),
            allow_all_unknown=True,
            code=LIGHT_BATCH_INVALID,
            max_chars=MAX_DOCUMENT_CHARS,
        )
    except ResearchError as exc:
        if exc.code == LIGHT_BATCH_INVALID:
            return _closed_batch(exc.code, exc.message, plan_id=plan_id)
        raise
    accepted = {
        "batch_index": batch_index,
        "context_sha256": expected["context_sha256"],
        "document": checked,
        "document_sha256": sha256_canonical(checked),
        "parent_sha256": plan["plan_sha256"],
        "plan_id": plan_id,
        "plan_sha256": plan["plan_sha256"],
        "schema": BATCH_ACCEPTED_SCHEMA,
        "source": {"index_id": plan["index_id"], "paper_snapshot": dict(plan["paper_snapshot"])},
    }
    existing = _accepted_batch(workspace, plan, batch_index)
    if existing is not None and canonical_bytes(existing) != canonical_bytes(accepted):
        return _closed_batch(
            LIGHT_BATCH_CONFLICT,
            "accepted batch slot already holds a different document",
            plan_id=plan_id,
            batch_index=batch_index,
        )
    reused = _publish_job_file(workspace, plan_id, f"{BATCHES_DIRNAME}/{batch_index}.json", accepted)
    processed = 0
    accepted_count = 0
    for index in range(plan["batch_count"]):
        if _accepted_batch(workspace, plan, index) is not None:
            accepted_count += 1
            processed += plan["partition"][index]["chunk_count"]
    return {
        "ok": True,
        "status": OK,
        "message": "reused accepted knowledge batch" if reused else "accepted knowledge batch",
        "plan_id": plan_id,
        "batch_index": batch_index,
        "reused": reused,
        "accepted_batches": accepted_count,
        "total_batches": plan["batch_count"],
        "planned_chunks": plan["planned_chunks"],
        "processed_chunks": processed,
    }


def import_knowledge_batch(workspace_root: Path, context: object, document: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    return _catch_locked(workspace, lambda: _import_batch_unlocked(workspace, context, document))


def _job_status_payload(workspace: Path, classified: Mapping[str, Any]) -> dict[str, Any]:
    plan = classified.get("plan")
    accepted = list(classified.get("accepted_batches") or [])
    processed = 0
    planned = 0
    total = 0
    if type(plan) is dict:
        planned = plan["planned_chunks"]
        total = plan["batch_count"]
        for index in accepted:
            processed += plan["partition"][index]["chunk_count"]
        if plan["mode"] == "refresh":
            delta = sum(row["chunk_count"] for row in plan["partition"])
            processed = (planned - delta) + sum(plan["partition"][index]["chunk_count"] for index in accepted)
    workspace_status = "conflict"
    if type(plan) is dict:
        if plan["workspace_id"] != workspace_identity(workspace):
            workspace_status = "historical"
        else:
            binding = _current_plan_binding(workspace, plan)
            workspace_status = "stale" if binding is not None else "current"
    status = OK
    ok = True
    if classified["kind"] == "pending":
        status = LIGHT_BATCH_INCOMPLETE
        ok = True
    elif classified["kind"] == "conflict":
        status = LIGHT_BATCH_CONFLICT
        ok = False
    elif classified["kind"] == "completed":
        status = OK
    return {
        "ok": ok,
        "status": status,
        "message": classified["message"],
        "schema": STATUS_SCHEMA,
        "plan_id": classified["plan_id"],
        "paper_id": plan["paper_id"] if type(plan) is dict else "",
        "mode": plan["mode"] if type(plan) is dict else "",
        "total_batches": total,
        "accepted_batches": len(accepted),
        "missing_batches": list(classified.get("missing_batches") or []),
        "planned_chunks": planned,
        "processed_chunks": processed,
        "accepted_merges": len(classified.get("accepted_merges") or []),
        "next_merge_step": classified.get("next_merge_step"),
        "processing_complete": classified["kind"] == "completed",
        "workspace_status": workspace_status,
    }


def knowledge_batch_status(workspace_root: Path, *, plan_id: object = None) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    root = _jobs_root(workspace)
    if plan_id is not None:
        try:
            ident = require_hex64(plan_id, "plan_id", code=LIGHT_BATCH_INVALID)
        except ResearchError as exc:
            if exc.code == LIGHT_BATCH_INVALID:
                return _closed_batch(exc.code, exc.message, schema=STATUS_SCHEMA)
            raise
        if not _job_dir(workspace, ident).exists() and not _job_dir(workspace, ident).is_symlink():
            return _closed_batch(LIGHT_BATCH_INVALID, "batch plan_id is not present", plan_id=ident, schema=STATUS_SCHEMA)
        return _job_status_payload(workspace, classify_batch_job(workspace, ident))
    jobs: list[dict[str, Any]] = []
    if root.exists() or root.is_symlink():
        if root.is_symlink() or not root.is_dir():
            return _closed_batch(LIGHT_BATCH_CONFLICT, "batch-jobs path is not a regular directory", schema=STATUS_SCHEMA)
        for item in sorted(root.iterdir(), key=lambda path: path.name):
            if item.is_symlink() or not item.is_dir() or not HEX64.fullmatch(item.name):
                jobs.append(
                    {
                        "ok": False,
                        "status": LIGHT_BATCH_CONFLICT,
                        "message": f"unknown or unsafe batch job entry {item.name}",
                        "plan_id": item.name,
                        "schema": STATUS_SCHEMA,
                    }
                )
                continue
            jobs.append(_job_status_payload(workspace, classify_batch_job(workspace, item.name)))
    return {
        "ok": True,
        "status": OK,
        "message": "listed knowledge batch jobs",
        "schema": STATUS_SCHEMA,
        "jobs": jobs,
    }


def _first_missing_merge(workspace: Path, plan: Mapping[str, Any]) -> int | dict[str, Any]:
    classified = classify_batch_job(workspace, plan["plan_id"])
    if classified["kind"] == "conflict":
        return _closed_batch(LIGHT_BATCH_CONFLICT, classified["message"], plan_id=plan["plan_id"])
    if classified["kind"] == "completed":
        return _closed_batch(LIGHT_BATCH_INVALID, "batch job is already complete", plan_id=plan["plan_id"])
    if plan["batch_count"] == 0:
        return _closed_batch(LIGHT_BATCH_INVALID, "refresh plan has no merge steps", plan_id=plan["plan_id"])
    step = classified["next_merge_step"]
    assert type(step) is int
    if step >= plan["batch_count"]:
        return _closed_batch(LIGHT_BATCH_INVALID, "all merge steps are already accepted", plan_id=plan["plan_id"])
    if _accepted_batch(workspace, plan, step) is None:
        return _closed_batch(
            LIGHT_BATCH_INCOMPLETE,
            f"batch {step} must be imported before merge step {step}",
            plan_id=plan["plan_id"],
            missing_batches=classified["missing_batches"],
            next_merge_step=step,
        )
    return step


def _parent_merge_state(workspace: Path, plan: Mapping[str, Any], step: int) -> tuple[dict[str, Any] | None, str | None]:
    if step == 0:
        seed = plan.get("seed_document")
        if seed is not None:
            return seed, sha256_canonical(seed)
        return None, None
    previous = _merge_step(workspace, plan, step - 1)
    if previous is None:
        return None, None
    return previous["document"], sha256_canonical(previous)


def _merge_export_unlocked(workspace: Path, plan_id: str) -> dict[str, Any]:
    plan = load_plan(workspace, plan_id)
    if plan is None:
        return _closed_batch(LIGHT_BATCH_INVALID, "batch plan_id is not a validated job", plan_id=plan_id)
    blocked = _require_resumable_plan(workspace, plan)
    if blocked is not None:
        return blocked
    step_or_error = _first_missing_merge(workspace, plan)
    if type(step_or_error) is dict:
        return step_or_error
    step = step_or_error
    accepted = _accepted_batch(workspace, plan, step)
    assert accepted is not None
    accumulator, parent_hash = _parent_merge_state(workspace, plan, step)
    if step > 0 and accumulator is None:
        return _closed_batch(LIGHT_BATCH_INCOMPLETE, "merge chain is missing the previous step", plan_id=plan_id)
    wrapper = {
        "ok": True,
        "status": OK,
        "message": "exported knowledge merge context for the current conversation model",
        "schema": MERGE_CONTEXT_SCHEMA,
        "plan_id": plan_id,
        "plan_sha256": plan["plan_sha256"],
        "step": step,
        "parent_step_hash": parent_hash,
        "next_batch_document_hash": accepted["document_sha256"],
        "accumulator": accumulator,
        "next_batch_document": accepted["document"],
        "coverage": {
            "batch_count": plan["batch_count"],
            "gap_chunk_ids": [],
            "mode": plan["mode"],
            "next_batch_chunk_ids": list(plan["partition"][step]["chunk_ids"]),
            "next_batch_index": step,
            "planned_chunks": plan["planned_chunks"],
            "processed_chunks": sum(plan["partition"][index]["chunk_count"] for index in range(step + 1)),
            "processing_complete": False,
        },
        "prompt": MERGE_PROMPT,
    }
    if canonical_char_count(wrapper) > MAX_MERGE_CONTEXT_CHARS:
        return _closed_batch(LIGHT_BATCH_INVALID, "merge context exceeds the 80000-character canonical JSON cap", plan_id=plan_id)
    wrapper["wrapper_sha256"] = sha256_canonical({key: wrapper[key] for key in wrapper if key != "wrapper_sha256"})
    return wrapper


def export_knowledge_merge_context(workspace_root: Path, *, plan_id: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    try:
        ident = require_hex64(plan_id, "plan_id", code=LIGHT_BATCH_INVALID)
    except ResearchError as exc:
        if exc.code == LIGHT_BATCH_INVALID:
            return _closed_batch(exc.code, exc.message)
        raise
    return _catch_locked(workspace, lambda: _merge_export_unlocked(workspace, ident))


def _live_chunks_by_id(papers: list[dict[str, Any]], paper_id: str) -> dict[str, dict[str, Any]]:
    return {item["chunk_id"]: item for item in _paper_chunks(papers, paper_id)}


def _batch_evidence_by_id(workspace: Path, plan: Mapping[str, Any], papers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    live = _live_chunks_by_id(papers, plan["paper_id"])
    for index in range(plan["batch_count"]):
        accepted = _accepted_batch(workspace, plan, index)
        if accepted is None:
            continue
        owned = _document_citation_set(accepted.get("document"))
        allowed = _partition_allowed_ids(plan, index) or set()
        for chunk_id in owned & allowed:
            live_chunk = live.get(chunk_id)
            if live_chunk is not None:
                by_id[chunk_id] = live_chunk
    return by_id


def _import_merge_unlocked(workspace: Path, wrapper: object, document: object) -> dict[str, Any]:
    if type(wrapper) is not dict:
        return _closed_batch(LIGHT_BATCH_INVALID, "merge context must be an object")
    required = {
        "ok",
        "status",
        "message",
        "schema",
        "plan_id",
        "plan_sha256",
        "step",
        "parent_step_hash",
        "next_batch_document_hash",
        "accumulator",
        "next_batch_document",
        "coverage",
        "prompt",
        "wrapper_sha256",
    }
    if set(wrapper) != required:
        return _closed_batch(LIGHT_BATCH_INVALID, "merge context wrapper keys are invalid")
    if wrapper.get("schema") != MERGE_CONTEXT_SCHEMA:
        return _closed_batch(LIGHT_BATCH_INVALID, "merge context schema is invalid")
    plan_id = require_hex64(wrapper.get("plan_id"), "plan_id", code=LIGHT_BATCH_INVALID)
    expected = _merge_export_unlocked(workspace, plan_id)
    if expected.get("ok") is not True:
        return expected
    if not _same_export(expected, wrapper):
        return _closed_batch(LIGHT_BATCH_INVALID, "merge context does not match the next missing step", plan_id=plan_id)
    plan = load_plan(workspace, plan_id)
    assert plan is not None
    step = expected["step"]
    permitted = _document_citation_set(expected.get("accumulator")) | _document_citation_set(expected["next_batch_document"])
    live = _live_inputs(workspace, plan["paper_id"])
    if type(live) is dict:
        return live
    _stored, papers, _paper = live
    owned = _batch_evidence_by_id(workspace, plan, papers)
    live = _live_chunks_by_id(papers, plan["paper_id"])
    by_id = {chunk_id: live[chunk_id] for chunk_id in permitted if chunk_id in live and chunk_id in owned}
    if plan.get("seed_document") is not None:
        seed_ids = _document_citation_set(plan.get("seed_document"))
        for chunk_id in permitted & seed_ids:
            if chunk_id in live:
                by_id[chunk_id] = live[chunk_id]
    evidence = [_evidence_from_chunks([by_id[chunk_id]])[0] for chunk_id in sorted(permitted) if chunk_id in by_id]
    if set(permitted) - set(by_id):
        return _closed_batch(LIGHT_BATCH_INVALID, "merge citations are not present in accepted batch evidence", plan_id=plan_id)
    try:
        checked = _validate_document(
            document,
            paper_id=plan["paper_id"],
            evidence=evidence,
            allow_all_unknown=True,
            allowed_citation_ids=permitted,
            code=LIGHT_BATCH_INVALID,
            max_chars=MAX_DOCUMENT_CHARS,
        )
    except ResearchError as exc:
        if exc.code == LIGHT_BATCH_INVALID:
            return _closed_batch(exc.code, exc.message, plan_id=plan_id)
        raise
    extra = _document_citation_set(checked) - permitted
    if extra:
        return _closed_batch(LIGHT_BATCH_INVALID, "merge document resurrects a discarded citation", plan_id=plan_id)
    step_payload = {
        "document": checked,
        "document_sha256": sha256_canonical(checked),
        "next_batch_document_hash": expected["next_batch_document_hash"],
        "parent_step_hash": expected["parent_step_hash"],
        "plan_id": plan_id,
        "plan_sha256": plan["plan_sha256"],
        "schema": MERGE_STEP_SCHEMA,
        "step": step,
    }
    existing = _merge_step(workspace, plan, step)
    if existing is not None and canonical_bytes(existing) != canonical_bytes(step_payload):
        return _closed_batch(
            LIGHT_BATCH_CONFLICT,
            "merge step already holds a different document",
            plan_id=plan_id,
            step=step,
        )
    reused = _publish_job_file(workspace, plan_id, f"{MERGES_DIRNAME}/{step}.json", step_payload)
    return {
        "ok": True,
        "status": OK,
        "message": "reused knowledge merge step" if reused else "accepted knowledge merge step",
        "plan_id": plan_id,
        "step": step,
        "reused": reused,
        "next_merge_step": step + 1 if step + 1 < plan["batch_count"] else None,
    }


def import_knowledge_merge(workspace_root: Path, context: object, document: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    return _catch_locked(workspace, lambda: _import_merge_unlocked(workspace, context, document))


def _validated_final_document(
    workspace: Path,
    plan: Mapping[str, Any],
    papers: list[dict[str, Any]],
) -> dict[str, Any] | dict[str, Any]:
    live = _paper_chunks(papers, plan["paper_id"])
    inventory_ids = {row["chunk_id"] for row in plan["inventory"]}
    if plan["batch_count"] == 0:
        seed = plan.get("seed_document")
        if type(seed) is not dict:
            seed = _empty_document(plan["paper_id"])
        checked = _try_validate_document(
            seed,
            paper_id=plan["paper_id"],
            evidence=_evidence_from_chunks([item for item in live if item["chunk_id"] in inventory_ids]),
            allowed_citation_ids=inventory_ids,
        )
        if checked is None:
            return _closed_batch(
                LIGHT_BATCH_INVALID,
                "zero-batch refresh seed is not a validated same-paper document",
                plan_id=plan["plan_id"],
            )
        return checked
    if not _accepted_merge_chain_ok(workspace, plan, set(range(plan["batch_count"]))):
        return _closed_batch(
            LIGHT_BATCH_INCOMPLETE,
            "batch job merge chain is not complete or not contiguous",
            plan_id=plan["plan_id"],
        )
    last = _final_merge_from_files(workspace, plan)
    if last is None:
        return _closed_batch(LIGHT_BATCH_INCOMPLETE, "final merge step is missing", plan_id=plan["plan_id"])
    document = last["document"]
    checked = _try_validate_document(
        document,
        paper_id=plan["paper_id"],
        evidence=_evidence_from_chunks([item for item in live if item["chunk_id"] in _document_citation_set(document)]),
        allowed_citation_ids=_document_citation_set(document) | inventory_ids,
    )
    if checked is None:
        return _closed_batch(
            LIGHT_BATCH_INVALID,
            "final merge document is not a validated cited knowledge document",
            plan_id=plan["plan_id"],
        )
    return checked


def _final_document(workspace: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan["batch_count"] == 0:
        seed = plan.get("seed_document")
        if type(seed) is dict:
            return seed
        return _empty_document(plan["paper_id"])
    last = _merge_step(workspace, plan, plan["batch_count"] - 1)
    if last is None:
        return _empty_document(plan["paper_id"])
    return last["document"]


def _final_merge_hash(workspace: Path, plan: Mapping[str, Any]) -> str | None:
    if plan["batch_count"] == 0:
        return None
    last = _final_merge_from_files(workspace, plan)
    if last is None:
        return None
    return sha256_canonical(last)


def _cited_chunks(document: Mapping[str, Any], live_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["chunk_id"]: item for item in live_chunks}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    sections = document.get("sections")
    order: list[str] = []
    if type(sections) is dict:
        for key in SECTION_KEYS:
            block = sections.get(key)
            if type(block) is dict and type(block.get("citations")) is list:
                order.extend(item for item in block["citations"] if type(item) is str)
    concepts = document.get("concepts")
    if type(concepts) is list:
        for item in concepts:
            if type(item) is dict and type(item.get("citations")) is list:
                order.extend(value for value in item["citations"] if type(value) is str)
    for chunk_id in order:
        if chunk_id in seen or chunk_id not in by_id:
            continue
        seen.add(chunk_id)
        rows.append(by_id[chunk_id])
    return rows


def _record_wrapper(
    *,
    schema: str,
    paper_id: str,
    context: Mapping[str, Any],
    coverage: Mapping[str, Any],
    paper_snapshot: Mapping[str, Any],
    prompt: str,
) -> dict[str, Any]:
    return {
        "context": dict(context),
        "coverage": dict(coverage),
        "paper_id": paper_id,
        "paper_snapshot": dict(paper_snapshot),
        "prompt": prompt,
        "schema": schema,
    }


def _coverage_for_record(
    plan: Mapping[str, Any],
    *,
    mode: str,
    merge_sha256: str | None,
    base_record_id: str | None,
    candidate_record_id: str | None,
    accepted_sections: list[str] | None,
    accept_concepts: bool | None,
) -> dict[str, Any]:
    return {
        "batch_count": plan["batch_count"],
        "gap_chunk_ids": [],
        "inventory": list(plan["inventory"]),
        "mode": mode,
        "planned_chunks": plan["planned_chunks"],
        "processed_chunks": len(plan["inventory"]),
        "processing_complete": True,
        "provenance": {
            "accept_concepts": accept_concepts,
            "accepted_sections": accepted_sections,
            "base_record_id": base_record_id,
            "candidate_record_id": candidate_record_id,
            "merge_sha256": merge_sha256,
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
        },
    }


def _publish_knowledge_record(
    workspace: Path,
    *,
    paper: Mapping[str, Any],
    document: dict[str, Any],
    context: dict[str, Any],
    wrapper: Mapping[str, Any],
) -> tuple[str, bool]:
    publish_wrapper = dict(wrapper)
    publish_wrapper["context_sha256"] = sha256_canonical(context)
    record_id = sha256_canonical({"document": document, "wrapper": _record_wrapper(
        schema=str(wrapper["schema"]),
        paper_id=str(wrapper["paper_id"]),
        context=context,
        coverage=wrapper["coverage"],
        paper_snapshot=wrapper["paper_snapshot"],
        prompt=str(wrapper["prompt"]),
    )})
    files = _record_files(
        workspace=workspace,
        record_id=record_id,
        document=document,
        context=context,
        paper=paper,
        wrapper=publish_wrapper,
    )
    reused = _publish_record(workspace, record_id, files)
    return record_id, reused


def _finalize_result(
    *,
    plan: Mapping[str, Any],
    plan_id: str,
    record_id: str,
    page: Path,
    reused: bool,
    advanced_head: bool,
    message: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "status": OK,
        "message": message,
        "plan_id": plan_id,
        "record_id": record_id,
        "paper_id": plan["paper_id"],
        "page_path": str(page),
        "source_status": "current",
        "reused": reused,
        "advanced_head": advanced_head,
        "processing_complete": True,
        "planned_chunks": plan["planned_chunks"],
        "processed_chunks": len(plan["inventory"]),
        "batch_count": plan["batch_count"],
        "gap_chunk_ids": [],
    }


def _finalize_unlocked(workspace: Path, plan_id: str) -> dict[str, Any]:
    plan = load_plan(workspace, plan_id)
    if plan is None:
        return _closed_batch(LIGHT_BATCH_INVALID, "batch plan_id is not a validated job", plan_id=plan_id)
    blocked = _require_resumable_plan(workspace, plan)
    if blocked is not None:
        return blocked
    classified = classify_batch_job(workspace, plan_id)
    if classified["kind"] == "conflict":
        return _closed_batch(LIGHT_BATCH_CONFLICT, classified["message"], plan_id=plan_id)
    existing = _completion(workspace, plan)
    if existing is not None and classified["kind"] == "completed":
        if existing["status"] == INSUFFICIENT_EVIDENCE:
            return _closed_batch(
                INSUFFICIENT_EVIDENCE,
                "final merged knowledge document is all unknown",
                plan_id=plan_id,
                processing_complete=True,
                planned_chunks=plan["planned_chunks"],
                processed_chunks=len(plan["inventory"]),
                batch_count=plan["batch_count"],
                gap_chunk_ids=[],
            )
        record_id = existing["record_id"]
        page = (_records_root(workspace) / str(record_id) / KNOWLEDGE_PAGE_NAME).resolve()
        if not page.is_file():
            return _closed_batch(
                LIGHT_BATCH_CONFLICT,
                "completed job record_id does not resolve to a published knowledge page",
                plan_id=plan_id,
            )
        advanced = plan["mode"] == "full" and pointer_head_record_id(workspace, plan["paper_id"]) == record_id
        return _finalize_result(
            plan=plan,
            plan_id=plan_id,
            record_id=str(record_id),
            page=page,
            reused=True,
            advanced_head=advanced,
            message="reused finalized knowledge record",
        )
    if classified["kind"] == "pending":
        if classified["missing_batches"] or (
            plan["batch_count"] and len(classified.get("accepted_merges") or []) != plan["batch_count"]
        ):
            return _closed_batch(
                LIGHT_BATCH_INCOMPLETE,
                classified["message"],
                plan_id=plan_id,
                missing_batches=classified["missing_batches"],
                next_merge_step=classified.get("next_merge_step"),
            )
    live = _live_inputs(workspace, plan["paper_id"])
    if type(live) is dict:
        return live
    stored, papers, paper = live
    document = _validated_final_document(workspace, plan, papers)
    if document.get("schema") != KNOWLEDGE_DOCUMENT_SCHEMA:
        return document
    merge_sha256 = _final_merge_hash(workspace, plan)
    pointer = pointer_head_record_id(workspace, plan["paper_id"])
    if _is_all_unknown(document):
        if pointer != plan["expected_base_head"]:
            return _closed_batch(
                LIGHT_BATCH_CONFLICT,
                "expected base knowledge head changed before finalization",
                plan_id=plan_id,
            )
        completion = {
            "index_id": plan["index_id"],
            "merge_sha256": merge_sha256,
            "paper_snapshot": dict(plan["paper_snapshot"]),
            "plan_id": plan_id,
            "plan_sha256": plan["plan_sha256"],
            "record_id": None,
            "schema": COMPLETION_SCHEMA,
            "status": INSUFFICIENT_EVIDENCE,
        }
        if existing is not None and canonical_bytes(existing) != canonical_bytes(completion):
            return _closed_batch(LIGHT_BATCH_CONFLICT, "completion already exists with different bytes", plan_id=plan_id)
        _publish_job_file(workspace, plan_id, COMPLETION_FILE, completion)
        return _closed_batch(
            INSUFFICIENT_EVIDENCE,
            "final merged knowledge document is all unknown",
            plan_id=plan_id,
            processing_complete=True,
            planned_chunks=plan["planned_chunks"],
            processed_chunks=len(plan["inventory"]),
            batch_count=plan["batch_count"],
            gap_chunk_ids=[],
        )
    live_chunks = _paper_chunks(papers, plan["paper_id"])
    cited = _cited_chunks(document, live_chunks)
    query = paper["title"] if type(paper.get("title")) is str and paper["title"].strip() else plan["paper_id"]
    context = _writing_context(
        workspace=workspace,
        query=query,
        requirements=KNOWLEDGE_REQUIREMENTS,
        paper_ids=[plan["paper_id"]],
        evidence=_evidence_from_chunks(cited),
        index_id=str(stored["index_id"]),
        prompt=FINAL_PROMPT,
    )
    if context.get("ok") is not True:
        return context
    live_context = validate_live_context(workspace, context)
    if live_context.get("ok") is not True:
        return live_context
    after = _current_plan_binding(workspace, plan)
    if after is not None:
        return after
    if plan["mode"] == "full":
        schema = BATCH_RECORD_CONTEXT_SCHEMA
        coverage = _coverage_for_record(
            plan,
            mode="full",
            merge_sha256=merge_sha256,
            base_record_id=None,
            candidate_record_id=None,
            accepted_sections=None,
            accept_concepts=None,
        )
    else:
        schema = REFRESH_RECORD_CONTEXT_SCHEMA
        coverage = _coverage_for_record(
            plan,
            mode="refresh",
            merge_sha256=merge_sha256,
            base_record_id=plan["expected_base_head"],
            candidate_record_id=None,
            accepted_sections=None,
            accept_concepts=None,
        )
    wrapper = _record_wrapper(
        schema=schema,
        paper_id=plan["paper_id"],
        context=context,
        coverage=coverage,
        paper_snapshot=plan["paper_snapshot"],
        prompt=FINAL_PROMPT,
    )
    expected_id = sha256_canonical({"document": document, "wrapper": wrapper})
    if pointer != plan["expected_base_head"] and pointer != expected_id:
        return _closed_batch(
            LIGHT_BATCH_CONFLICT,
            "expected base knowledge head changed before finalization",
            plan_id=plan_id,
        )
    blocked_heads = _reject_irreplaceable_pointer(
        workspace, kind="heads", relative_target=f"{KNOWLEDGE_STATE_DIR}/HEADS.json"
    )
    if blocked_heads is not None and plan["mode"] == "full" and pointer != expected_id:
        return blocked_heads
    record_id, reused = _publish_knowledge_record(
        workspace,
        paper=paper,
        document=document,
        context=context,
        wrapper=wrapper,
    )
    if record_id != expected_id:
        return _closed_batch(LIGHT_BATCH_CONFLICT, "knowledge record identity drifted during publication", plan_id=plan_id)
    after_record = _current_plan_binding(workspace, plan)
    if after_record is not None:
        return after_record
    page = (_records_root(workspace) / record_id / KNOWLEDGE_PAGE_NAME).resolve()
    if not page.is_file():
        return _closed_batch(
            LIGHT_BATCH_CONFLICT,
            "published knowledge record does not contain a knowledge page",
            plan_id=plan_id,
        )
    pointer_after = pointer_head_record_id(workspace, plan["paper_id"])
    if pointer_after != plan["expected_base_head"] and pointer_after != record_id:
        return _closed_batch(LIGHT_BATCH_CONFLICT, "expected base knowledge head changed before finalization", plan_id=plan_id)
    advanced = False
    if plan["mode"] == "full":
        if pointer_after == plan["expected_base_head"]:
            _set_head(workspace, plan["paper_id"], record_id)
        elif pointer_after != record_id:
            return _closed_batch(
                LIGHT_BATCH_CONFLICT,
                "expected base knowledge head changed before finalization",
                plan_id=plan_id,
            )
        if pointer_head_record_id(workspace, plan["paper_id"]) != record_id:
            return _closed_batch(
                LIGHT_BATCH_CONFLICT,
                "full finalization did not adopt the published knowledge record",
                plan_id=plan_id,
            )
        advanced = True
    completion = {
        "index_id": plan["index_id"],
        "merge_sha256": merge_sha256,
        "paper_snapshot": dict(plan["paper_snapshot"]),
        "plan_id": plan_id,
        "plan_sha256": plan["plan_sha256"],
        "record_id": record_id,
        "schema": COMPLETION_SCHEMA,
        "status": OK,
    }
    if existing is not None and canonical_bytes(existing) != canonical_bytes(completion):
        return _closed_batch(LIGHT_BATCH_CONFLICT, "completion already exists with different bytes", plan_id=plan_id)
    _publish_job_file(workspace, plan_id, COMPLETION_FILE, completion)
    return _finalize_result(
        plan=plan,
        plan_id=plan_id,
        record_id=record_id,
        page=page,
        reused=reused,
        advanced_head=advanced,
        message=(
            "reused finalized knowledge record"
            if reused
            else ("published refresh candidate record" if plan["mode"] == "refresh" else "published batch knowledge record")
        ),
    )


def finalize_knowledge_batches(workspace_root: Path, *, plan_id: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    try:
        ident = require_hex64(plan_id, "plan_id", code=LIGHT_BATCH_INVALID)
    except ResearchError as exc:
        if exc.code == LIGHT_BATCH_INVALID:
            return _closed_batch(exc.code, exc.message)
        raise
    return _catch_locked(workspace, lambda: _finalize_unlocked(workspace, ident))
