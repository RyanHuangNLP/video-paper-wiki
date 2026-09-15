"""Article revision import, check, render, status, and history. Vault writes are forbidden."""

from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.article_context import ArticleContextError, build_article_context
from video_paper_wiki.article_store import (
    ARTICLE_RE,
    ARTICLE_ROOT,
    CHECK_SCHEMA,
    CITE_ANY,
    CITE_MARK,
    CONTROL_RE,
    EVIDENCE_RE,
    HEADS_SCHEMA,
    MAX_ARTICLES,
    MAX_BIBLIOGRAPHY,
    MAX_CITATIONS,
    MAX_GOAL,
    MAX_INSTRUCTIONS,
    MAX_RECORD_BYTES,
    MAX_REVISIONS_PER_ARTICLE,
    MAX_SECTION_MARKDOWN,
    MAX_SECTIONS,
    MAX_TITLE,
    PROVISIONAL_LABEL,
    RECORD_SCHEMA,
    REQUIRED_ROLES,
    REVISION_RE,
    ROLES,
    SECTION_RE,
    UNKNOWN_TEXT,
    UNWRITTEN_TEXT,
    ArticleStoreError,
    _byte_sort,
    _copy_article_store,
    _fail as _store_fail,
    _load_article_store,
    _load_staged_articles,
    _lookup_revision,
    _merge,
    _pointer,
    _run_with_store,
    article_id_from_question,
    article_inventory_digest,
    content_sha256_from_record,
    derive_article_heads,
    revision_id_from_record,
)
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import DomainStoreError, _batch, _stage_items, derive_domain_heads
from video_paper_wiki.experiment_matrix import COLUMNS
from video_paper_wiki.experiment_publication import _experiment_basis
from video_paper_wiki.experiment_store import ExperimentStoreError, _load_experiment_store, _recorded_at, _recorded_by
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.secure_io import JSON_MAX_BYTES, SecureIOError, load_strict_json
from video_paper_wiki.source_semantics_contracts import calendar, sha
from video_paper_wiki.staging import StagingError, stage_bytes

_HIB = "higher_is_b" + "etter"
ROLE_ZH = {
    "question": "问题",
    "background": "背景",
    "consensus": "共识",
    "differences": "差异",
    "controversies": "争议",
    "comparison": "比较",
    "limits": "局限",
    "unknowns": "未知",
}
STATUS_ZH = {
    "unwritten": "未撰写",
    "unknown": "未知",
    "provisional": "暂定",
}
STALE_STATUS = frozenset(
    {
        "stale",
        "source_missing",
        "source_changed",
        "excerpt_changed",
        "changed",
        "missing",
        "identity_mismatch",
    }
)
SECTION_REASON = {
    "changed": "evidence_changed",
    "stale": "evidence_stale",
    "missing": "evidence_missing",
}
MESSAGES = {
    "ARTICLE_REVISION_INVALID": "article revision input is invalid",
    "ARTICLE_REVISION_INPUT_MISSING": "required article revision input is missing",
    "ARTICLE_REVISION_PREVIOUS_MISMATCH": "article revision previous revision does not match the chain head",
    "ARTICLE_REVISION_UNCHANGED": "article revision content is unchanged from the chain head",
    "ARTICLE_CHECK_INVALID": "article check input is invalid",
    "ARTICLE_RENDER_INVALID": "article render input is invalid",
    "ARTICLE_CONTEXT_STALE": "article context is stale relative to the current store",
    "ARTICLE_STORE_CHAIN_INVALID": "article store chain is invalid",
    "ARTICLE_STORE_LIMIT": "article store exceeds a closed bound",
    "ARTICLE_STORE_CHANGED": "article store changed during read",
}


class ArticleRevisionError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


def _fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise ArticleRevisionError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _check_instructions(value):
    if value is None:
        return ""
    if type(value) is not str or len(value) > MAX_INSTRUCTIONS or CONTROL_RE.search(value) is not None:
        _fail("ARTICLE_REVISION_INVALID", "/instructions", "repair_input")
    return value


def _load_json_file(path, *, pointer):
    try:
        parsed = load_strict_json(
            Path(path),
            missing_code="ARTICLE_REVISION_INPUT_MISSING",
            unsafe_code="WORK_PATH_UNSAFE",
            invalid_code="ARTICLE_REVISION_INVALID",
            changed_code="ARTICLE_STORE_CHANGED",
            max_bytes=JSON_MAX_BYTES,
        )
    except SecureIOError as exc:
        code = exc.code
        if code == "WORK_PATH_UNSAFE":
            raise ArticleRevisionError(
                code,
                exc.message,
                {"instance_pointer": pointer, "next_action": "repair_input", **dict(exc.details or {})},
                exit_code=getattr(exc, "exit_code", 2),
            ) from exc
        next_action = "repeat_read" if code == "ARTICLE_STORE_CHANGED" else "repair_input"
        raise ArticleRevisionError(
            code,
            MESSAGES.get(code, exc.message),
            {"instance_pointer": pointer, "next_action": next_action, **dict(exc.details or {})},
            exit_code=75 if code == "ARTICLE_STORE_CHANGED" else getattr(exc, "exit_code", 2),
        ) from exc
    except OSError:
        _store_fail("ARTICLE_STORE_CHANGED", pointer, "repeat_read", exit_code=75)
    return parsed


def _load_export_envelope(path):
    parsed = _load_json_file(path, pointer="/context")
    if type(parsed) is not dict or set(parsed) != {"ok", "command", "data"}:
        _fail("ARTICLE_REVISION_INVALID", "/context", "repair_input", {"reason": "context_shape"})
    if parsed.get("ok") is not True or parsed.get("command") != "articles.export":
        _fail("ARTICLE_REVISION_INVALID", "/context", "repair_input", {"reason": "context_shape"})
    data = parsed.get("data")
    if type(data) is not dict or "context" not in data or "context_sha256" not in data:
        _fail("ARTICLE_REVISION_INVALID", "/context", "repair_input", {"reason": "context_shape"})
    context = data["context"]
    digest = data["context_sha256"]
    try:
        validate_document(context, "video-paper-wiki.article-context.v1")
        if sha(canonicalize(context)) != digest:
            _fail("ARTICLE_REVISION_INVALID", "/context", "repair_input", {"reason": "context_shape"})
    except ContractError:
        _fail("ARTICLE_REVISION_INVALID", "/context", "repair_input", {"reason": "context_shape"})
    except CanonicalJsonError:
        _fail("ARTICLE_REVISION_INVALID", "/context", "repair_input", {"reason": "context_shape"})
    return context, digest


def _load_document_file(path):
    parsed = _load_json_file(path, pointer="/document")
    if type(parsed) is not dict or set(parsed) != {"schema", "title", "sections"}:
        _fail("ARTICLE_REVISION_INVALID", "/document", "repair_input", {"reason": "document_shape"})
    if parsed.get("schema") != "video-paper-wiki.article-document.v1":
        _fail("ARTICLE_REVISION_INVALID", "/document", "repair_input", {"reason": "document_shape"})
    return parsed


def _section_pointer(index, field):
    return "/document/sections/" + str(index) + "/" + field


def _validate_document_body(document, context, *, parent, target_section_id):
    title = document.get("title")
    if type(title) is not str or not title or len(title) > MAX_TITLE or CONTROL_RE.search(title) is not None:
        _fail("ARTICLE_REVISION_INVALID", "/document/title", "repair_document")
    if "[@" in title:
        _fail("ARTICLE_REVISION_INVALID", "/document/title", "repair_document", {"reason": "cite_mark_in_title"})
    sections = document.get("sections")
    if type(sections) is not list or not sections or len(sections) > MAX_SECTIONS:
        _fail("ARTICLE_REVISION_INVALID", "/document/sections", "repair_document")
    keys = {"section_id", "role", "title", "goal", "status", "markdown", "citations"}
    seen_ids = set()
    roles_seen = []
    comparison_count = 0
    evidence_ids = {item["evidence_id"] for item in context.get("evidence") or []}
    out = []
    for index, section in enumerate(sections):
        base = "/document/sections/" + str(index)
        if type(section) is not dict or set(section) != keys:
            _fail("ARTICLE_REVISION_INVALID", base, "repair_document")
        sid = section["section_id"]
        if type(sid) is not str or SECTION_RE.fullmatch(sid) is None:
            _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "section_id"), "repair_document")
        if sid in seen_ids:
            _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "section_id"), "repair_document")
        seen_ids.add(sid)
        role = section["role"]
        if role not in ROLES:
            _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "role"), "repair_document")
        roles_seen.append(role)
        if role == "comparison":
            comparison_count += 1
        stitle = section["title"]
        if type(stitle) is not str or not stitle or len(stitle) > MAX_TITLE or CONTROL_RE.search(stitle) is not None:
            _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "title"), "repair_document")
        if "[@" in stitle:
            _fail(
                "ARTICLE_REVISION_INVALID",
                _section_pointer(index, "title"),
                "repair_document",
                {"reason": "cite_mark_in_title"},
            )
        goal = section["goal"]
        if type(goal) is not str or not goal or len(goal) > MAX_GOAL or CONTROL_RE.search(goal) is not None:
            _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "goal"), "repair_document")
        if "[@" in goal:
            _fail(
                "ARTICLE_REVISION_INVALID",
                _section_pointer(index, "goal"),
                "repair_document",
                {"reason": "cite_mark_in_title"},
            )
        status = section["status"]
        if status not in {"unwritten", "unknown", "provisional"}:
            _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "status"), "repair_document")
        markdown = section["markdown"]
        citations = section["citations"]
        if type(markdown) is not str or type(citations) is not list:
            _fail("ARTICLE_REVISION_INVALID", base, "repair_document")
        if status == "unwritten":
            if markdown != "" or citations != []:
                _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "markdown"), "repair_document")
        elif status == "unknown":
            if markdown != UNKNOWN_TEXT or citations != []:
                _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "markdown"), "repair_document")
        else:
            stripped = markdown.strip()
            if not stripped or len(markdown) > MAX_SECTION_MARKDOWN:
                _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "markdown"), "repair_document")
            cleaned = markdown.replace("\n", "").replace("\r", "").replace("\t", "")
            if CONTROL_RE.search(cleaned) is not None:
                _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "markdown"), "repair_document")
            if not (1 <= len(citations) <= MAX_CITATIONS):
                _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "citations"), "repair_document")
            seen_c = set()
            for item in citations:
                if type(item) is not str or EVIDENCE_RE.fullmatch(item) is None:
                    _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "citations"), "repair_document")
                if item in seen_c:
                    _fail("ARTICLE_REVISION_INVALID", _section_pointer(index, "citations"), "repair_document")
                seen_c.add(item)
                if item not in evidence_ids:
                    _fail(
                        "ARTICLE_REVISION_INVALID",
                        _section_pointer(index, "citations"),
                        "repair_document",
                        {"reason": "unknown_evidence"},
                    )
            in_text = set(CITE_ANY.findall(markdown))
            listed = set(citations)
            if in_text != listed:
                _fail(
                    "ARTICLE_REVISION_INVALID",
                    _section_pointer(index, "citations"),
                    "repair_document",
                    {
                        "reason": "citation_mismatch",
                        "missing_in_text": _byte_sort(list(listed - in_text)),
                        "missing_in_list": _byte_sort(list(in_text - listed)),
                    },
                )
        out.append(
            {
                "section_id": sid,
                "role": role,
                "title": stitle,
                "goal": goal,
                "status": status,
                "markdown": markdown,
                "citations": list(citations),
            }
        )
    present = set(roles_seen)
    for role in REQUIRED_ROLES:
        if role not in present:
            _fail(
                "ARTICLE_REVISION_INVALID",
                "/document/sections",
                "repair_document",
                {"reason": "missing_role", "role": role},
            )
    if comparison_count > 1:
        _fail(
            "ARTICLE_REVISION_INVALID",
            "/document/sections",
            "repair_document",
            {"reason": "duplicate_comparison"},
        )
    if target_section_id is not None:
        if parent is None:
            _fail(
                "ARTICLE_REVISION_INVALID",
                "/target_section_id",
                "repair_document",
                {"reason": "requires_previous"},
            )
        if parent["title"] != title:
            _fail(
                "ARTICLE_REVISION_INVALID",
                "/document/title",
                "repair_document",
                {"reason": "target_section_scope"},
            )
        parent_sections = parent["sections"]
        if len(parent_sections) != len(out):
            _fail(
                "ARTICLE_REVISION_INVALID",
                "/document/sections",
                "repair_document",
                {"reason": "target_section_scope"},
            )
        found_target = False
        for index, (cur, prev) in enumerate(zip(out, parent_sections)):
            if (cur["section_id"], cur["role"], cur["title"], cur["goal"]) != (
                prev["section_id"],
                prev["role"],
                prev["title"],
                prev["goal"],
            ):
                _fail(
                    "ARTICLE_REVISION_INVALID",
                    _section_pointer(index, "title"),
                    "repair_document",
                    {"reason": "target_section_scope", "section_id": cur["section_id"]},
                )
            if cur["section_id"] == target_section_id:
                found_target = True
                continue
            if (cur["status"], cur["markdown"], cur["citations"]) != (
                prev["status"],
                prev["markdown"],
                prev["citations"],
            ):
                _fail(
                    "ARTICLE_REVISION_INVALID",
                    _section_pointer(index, "markdown"),
                    "repair_document",
                    {"reason": "target_section_scope", "section_id": cur["section_id"]},
                )
        if not found_target:
            _fail(
                "ARTICLE_REVISION_INVALID",
                "/target_section_id",
                "repair_document",
                {"reason": "target_section_scope", "section_id": target_section_id},
            )
    return title, out


def _derive_kind(parent, target_section_id, sections):
    if parent is None:
        if all(item["status"] in {"unwritten", "unknown"} for item in sections):
            return "outline"
        return "full"
    if target_section_id is not None:
        return "section"
    return "full"


def _progress(sections):
    counts = {"provisional": 0, "unknown": 0, "unwritten": 0}
    for item in sections:
        counts[item["status"]] += 1
    return counts


def _comparison_table(context):
    matrix = context["matrix"]
    rows = []
    for row in matrix["rows"]:
        cells = {}
        for cell in matrix["cells"]:
            if cell["row_index"] != row["row_index"]:
                continue
            cells[cell["column"]] = {
                "status": cell["status"],
                "value_summary": cell["value_summary"],
                "evidence_id": cell["evidence_id"],
            }
        rows.append(
            {
                "row_index": row["row_index"],
                "condition_id": row["condition_id"],
                "paper_id": row["paper_id"],
                "setting_key": row["setting_key"],
                "version": row["version"],
                "head_record_id": row["record_id"],
                "head_record_sha256": row["record_sha256"],
                "row_status": row["row_status"],
                "cells": cells,
            }
        )
    metric_cells = []
    for cell in matrix["metric_cells"]:
        metric_cells.append(
            {
                "row_index": cell["row_index"],
                "name": cell["name"],
                "unit": cell["unit"],
                "value": cell["value"],
                _HIB: cell.get(_HIB),
                "evidence_id": cell["evidence_id"],
            }
        )
    return {
        "rows": rows,
        "metric_columns": list(matrix["metric_columns"]),
        "metric_cells": metric_cells,
    }


def _bibliography(context, sections, table):
    ids = set()
    for section in sections:
        ids.update(section["citations"])
    for row in table["rows"]:
        for key in COLUMNS:
            ids.add(row["cells"][key]["evidence_id"])
    for cell in table["metric_cells"]:
        ids.add(cell["evidence_id"])
    if len(ids) > MAX_BIBLIOGRAPHY:
        _fail("ARTICLE_REVISION_INVALID", "/bibliography", "repair_document", {"reason": "bibliography_limit"})
    by_id = {item["evidence_id"]: item for item in context["evidence"]}
    out = []
    for eid in _byte_sort(list(ids)):
        src = by_id[eid]
        out.append(
            {
                "evidence_id": eid,
                "kind": src["kind"],
                "paper_id": src["paper_id"],
                "label": src["label"],
                "source": src["source"],
                "binding": src["binding"],
                "status_at_export": src["status"],
            }
        )
    return out


def _seal_record(document):
    try:
        raw = canonicalize(document)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("ARTICLE_REVISION_INVALID", "/record", "repair_document", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, RECORD_SCHEMA)
    except ContractError as exc:
        details = dict(exc.details or {})
        raise ArticleRevisionError(
            "ARTICLE_REVISION_INVALID",
            MESSAGES["ARTICLE_REVISION_INVALID"],
            {
                "instance_pointer": details.get("instance_pointer", ""),
                "next_action": "repair_document",
                "reason": "schema",
                **details,
            },
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    if len(raw) > MAX_RECORD_BYTES:
        _fail("ARTICLE_REVISION_INVALID", "/record", "repair_document", {"reason": "bytes"})
    return sealed, raw


def import_article_revision(
    *,
    vault_root,
    batch_id,
    context,
    document,
    recorded_by,
    recorded_at,
    previous_revision_id=None,
    target_section_id=None,
    instructions="",
):
    batch = _batch(batch_id, "/batch_id")
    try:
        recorded_by = _recorded_by(recorded_by)
    except ExperimentStoreError as exc:
        details = dict(exc.details or {})
        raise ArticleRevisionError(
            "ARTICLE_REVISION_INVALID",
            MESSAGES["ARTICLE_REVISION_INVALID"],
            details,
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    try:
        recorded_at = _recorded_at(recorded_at)
    except ExperimentStoreError as exc:
        details = dict(exc.details or {})
        raise ArticleRevisionError(
            "ARTICLE_REVISION_INVALID",
            MESSAGES["ARTICLE_REVISION_INVALID"],
            details,
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    if previous_revision_id is not None and (
        type(previous_revision_id) is not str or REVISION_RE.fullmatch(previous_revision_id) is None
    ):
        _fail("ARTICLE_REVISION_INVALID", "/previous_revision_id", "repair_input")
    if target_section_id is not None and previous_revision_id is None:
        _fail(
            "ARTICLE_REVISION_INVALID",
            "/target_section_id",
            "repair_document",
            {"reason": "requires_previous"},
        )
    if target_section_id is not None and (
        type(target_section_id) is not str or SECTION_RE.fullmatch(target_section_id) is None
    ):
        _fail("ARTICLE_REVISION_INVALID", "/target_section_id", "repair_input")
    instructions = _check_instructions(instructions)
    ctx, context_sha = _load_export_envelope(context)
    doc = _load_document_file(document)

    def apply(snapshot, domain_store, authority):
        exp = _load_experiment_store(snapshot)
        heads = derive_domain_heads(domain_store)
        art_store = _load_article_store(snapshot)
        staged = _load_staged_articles(batch)
        merged = _merge(art_store, staged)
        current = build_article_context(
            snapshot,
            domain_store,
            authority,
            exp,
            heads,
            question=ctx["question"],
            paper_ids=list(ctx["paper_ids"]),
        )
        current_sha = current.pop("_sha256")
        if current_sha != context_sha:
            raise ArticleContextError(
                "ARTICLE_CONTEXT_STALE",
                MESSAGES["ARTICLE_CONTEXT_STALE"],
                {
                    "instance_pointer": "/context_sha256",
                    "next_action": "re_export",
                },
                exit_code=75,
            )
        art = article_id_from_question(ctx["question"], ctx["paper_ids"])
        chain = merged.chains.get(art)
        parent = None
        if chain is not None:
            head = chain["record_order"][-1]
            if previous_revision_id != head:
                _fail(
                    "ARTICLE_REVISION_PREVIOUS_MISMATCH",
                    "/previous_revision_id",
                    "supply_previous",
                    {"expected": head},
                )
            if len(chain["record_order"]) >= MAX_REVISIONS_PER_ARTICLE:
                _fail("ARTICLE_STORE_LIMIT", "/records", "reduce_store")
            parent = merged.records[head]
        else:
            if previous_revision_id is not None:
                _fail(
                    "ARTICLE_REVISION_PREVIOUS_MISMATCH",
                    "/previous_revision_id",
                    "omit_previous",
                )
            if len(merged.chains) >= MAX_ARTICLES:
                _fail("ARTICLE_STORE_LIMIT", "/heads", "reduce_store")
        title, sections = _validate_document_body(
            doc, current, parent=parent, target_section_id=target_section_id
        )
        kind = _derive_kind(parent, target_section_id, sections)
        table = _comparison_table(current)
        bibliography = _bibliography(current, sections, table)
        progress = _progress(sections)
        body = {
            "schema": RECORD_SCHEMA,
            "article_id": art,
            "previous_revision_id": previous_revision_id,
            "content_sha256": "",
            "recorded_by": recorded_by,
            "recorded_at": recorded_at,
            "question": current["question"],
            "paper_ids": list(current["paper_ids"]),
            "context_sha256": context_sha,
            "basis": {
                **current["basis"],
                "graph_sha256": current["graph_sha256"],
                "matrix_sha256": current["matrix_sha256"],
            },
            "kind": kind,
            "target_section_id": target_section_id,
            "instructions": instructions,
            "title": title,
            "sections": sections,
            "bibliography": bibliography,
            "comparison_table": table,
            "progress": progress,
            "publication": "unpublished",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "typed_fact_promotion": "none",
            "ranking": "not_ranked",
            "scientific_conclusion_contradiction": False,
        }
        body["content_sha256"] = content_sha256_from_record(body)
        if parent is not None and body["content_sha256"] == parent["content_sha256"]:
            _fail("ARTICLE_REVISION_UNCHANGED", "/document", "revise_document")
        if parent is not None and calendar(recorded_at) < calendar(parent["recorded_at"]):
            _fail(
                "ARTICLE_STORE_CHAIN_INVALID",
                "/recorded_at",
                "repair_store",
                {"reason": "timestamp_order"},
            )
        rid = revision_id_from_record(body)
        body["revision_id"] = rid
        sealed, raw = _seal_record(body)
        staged_info = _stage_items(
            batch,
            [
                (
                    ("articles", "records", art, rid + ".json"),
                    ARTICLE_ROOT + "/records/" + art + "/" + rid + ".json",
                    raw,
                )
            ],
        )
        tmp = _copy_article_store(merged)
        tmp.records[rid] = sealed
        tmp.record_raw[rid] = raw
        if art in tmp.chains:
            tmp.chains[art] = {"record_order": list(tmp.chains[art]["record_order"]) + [rid]}
        else:
            tmp.chains[art] = {"record_order": [rid]}
        prospective = derive_article_heads(tmp)
        try:
            validate_document(prospective, HEADS_SCHEMA)
        except ContractError as exc:
            details = dict(exc.details or {})
            raise ArticleRevisionError(
                "ARTICLE_REVISION_INVALID",
                MESSAGES["ARTICLE_REVISION_INVALID"],
                {"reason": "schema", **details},
                exit_code=getattr(exc, "exit_code", 2),
            ) from exc
        next_action = "write_sections" if progress["unwritten"] > 0 else "check_revision"
        return {
            "state": "article_revision_staged",
            "record": sealed,
            "prospective_heads": prospective,
            "staged": staged_info,
            "revision_location": "staged",
            "progress": progress,
            "publication": "unpublished",
            "applied": False,
            "write_kind": "work_staging",
            "audit_coverage": "not_wired",
            "backup_coverage": "not_wired",
            "ranking": "not_ranked",
            "typed_fact_promotion": "none",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": next_action,
        }

    try:
        return _run_with_store(vault_root, apply, authority_required=True)
    except OSError:
        _store_fail("ARTICLE_STORE_CHANGED", "/wiki/meta/articles", "repeat_read", exit_code=75)


def _binding_status(recorded, current_ev):
    if current_ev is None:
        return "missing", None, None, ["evidence_missing"]
    current_binding = current_ev["binding"]
    reasons = []
    keys = list(recorded)
    for key in current_binding:
        if key not in keys:
            keys.append(key)
    for key in keys:
        if recorded.get(key) != current_binding.get(key):
            reasons.append(key)
            if len(reasons) >= 8:
                break
    current_status = current_ev["status"]
    if reasons:
        return "changed", current_binding, current_status, reasons
    rec_status = current_binding.get("record_status")
    if current_status in STALE_STATUS:
        return "stale", current_binding, current_status, [current_status]
    if rec_status is not None and rec_status != "current":
        return "stale", current_binding, current_status, [rec_status]
    return "bound", current_binding, current_status, []


def _used_ids(record):
    ids = set()
    for section in record["sections"]:
        ids.update(section["citations"])
    for row in record["comparison_table"]["rows"]:
        for key in COLUMNS:
            ids.add(row["cells"][key]["evidence_id"])
    for cell in record["comparison_table"]["metric_cells"]:
        ids.add(cell["evidence_id"])
    return ids


def _missing_bibliography_item(eid, current_by_id, default_kind):
    current_ev = current_by_id.get(eid)
    return (
        "missing",
        current_ev["binding"] if current_ev is not None else None,
        current_ev["status"] if current_ev is not None else None,
        ["bibliography_missing"],
        current_ev["kind"] if current_ev is not None else default_kind,
        None,
    )


def check_revision_view(snapshot, domain_store, authority, exp, heads, record, location):
    current = None
    paper_unknown = False
    try:
        current = build_article_context(
            snapshot,
            domain_store,
            authority,
            exp,
            heads,
            question=record["question"],
            paper_ids=list(record["paper_ids"]),
        )
        current.pop("_sha256", None)
    except ArticleContextError as exc:
        if exc.code != "ARTICLE_CONTEXT_PAPER_UNKNOWN":
            raise
        paper_unknown = True
    basis_recorded = dict(record["basis"])
    if current is None:
        basis_current = dict(_experiment_basis(snapshot, domain_store, authority, exp))
        basis_current["graph_sha256"] = "0" * 64
        basis_current["matrix_sha256"] = "0" * 64
    else:
        basis_current = dict(current["basis"])
        basis_current["graph_sha256"] = current["graph_sha256"]
        basis_current["matrix_sha256"] = current["matrix_sha256"]
    basis_match = canonicalize(basis_recorded) == canonicalize(basis_current) and not paper_unknown
    current_by_id = {}
    if current is not None:
        current_by_id = {item["evidence_id"]: item for item in current["evidence"]}
    biblio = {item["evidence_id"]: item for item in record["bibliography"]}
    items = []
    section_rows = []
    affected_sections = []
    in_text_ok = True
    for section in record["sections"]:
        sid = section["section_id"]
        marks = set(CITE_ANY.findall(section["markdown"])) if section["status"] == "provisional" else set()
        listed = set(section["citations"])
        if section["status"] == "provisional" and marks != listed:
            in_text_ok = False
        reasons = []
        affected = False
        for eid in section["citations"]:
            if eid in biblio:
                recorded_binding = biblio[eid]["binding"]
                kind = biblio[eid]["kind"]
                status, cur_b, cur_status, item_reasons = _binding_status(
                    recorded_binding, current_by_id.get(eid)
                )
            else:
                status, cur_b, cur_status, item_reasons, kind, recorded_binding = _missing_bibliography_item(
                    eid, current_by_id, "claim"
                )
            if status != "bound":
                affected = True
                mapped = SECTION_REASON.get(status)
                if mapped and mapped not in reasons:
                    reasons.append(mapped)
            items.append(
                {
                    "location": "section",
                    "section_id": sid,
                    "evidence_id": eid,
                    "kind": kind,
                    "status": status,
                    "recorded_binding": recorded_binding,
                    "current_binding": cur_b,
                    "current_status": cur_status,
                    "reasons": item_reasons,
                }
            )
        if section["status"] == "provisional" and marks != listed:
            if "citation_mismatch" not in reasons:
                reasons.append("citation_mismatch")
            affected = True
        if affected:
            affected_sections.append(sid)
        section_rows.append(
            {
                "section_id": sid,
                "role": section["role"],
                "status": section["status"],
                "citation_count": len(section["citations"]),
                "affected": affected,
                "reasons": reasons[:4],
            }
        )
    table_affected = False
    for row in record["comparison_table"]["rows"]:
        for key in COLUMNS:
            cell = row["cells"][key]
            eid = cell["evidence_id"]
            if eid in biblio:
                recorded_binding = biblio[eid]["binding"]
                kind = biblio[eid]["kind"]
                status, cur_b, cur_status, item_reasons = _binding_status(
                    recorded_binding, current_by_id.get(eid)
                )
            else:
                status, cur_b, cur_status, item_reasons, kind, recorded_binding = _missing_bibliography_item(
                    eid, current_by_id, "condition_value"
                )
            if status != "bound":
                table_affected = True
            items.append(
                {
                    "location": "table",
                    "section_id": None,
                    "evidence_id": eid,
                    "kind": kind,
                    "status": status,
                    "recorded_binding": recorded_binding,
                    "current_binding": cur_b,
                    "current_status": cur_status,
                    "reasons": item_reasons,
                }
            )
    for cell in record["comparison_table"]["metric_cells"]:
        eid = cell["evidence_id"]
        if eid in biblio:
            recorded_binding = biblio[eid]["binding"]
            kind = biblio[eid]["kind"]
            status, cur_b, cur_status, item_reasons = _binding_status(
                recorded_binding, current_by_id.get(eid)
            )
        else:
            status, cur_b, cur_status, item_reasons, kind, recorded_binding = _missing_bibliography_item(
                eid, current_by_id, "metric_value"
            )
        if status != "bound":
            table_affected = True
        items.append(
            {
                "location": "metric",
                "section_id": None,
                "evidence_id": eid,
                "kind": kind,
                "status": status,
                "recorded_binding": recorded_binding,
                "current_binding": cur_b,
                "current_status": cur_status,
                "reasons": item_reasons,
            }
        )
    used = _used_ids(record)
    biblio_ids = set(biblio)
    citation_consistency = {
        "in_text_equals_list": in_text_ok,
        "bibliography_complete": used <= biblio_ids,
        "bibliography_minimal": biblio_ids <= used,
    }
    counts = {"bound": 0, "changed": 0, "stale": 0, "missing": 0, "items": len(items)}
    for item in items:
        counts[item["status"]] += 1
    consistent = all(citation_consistency.values())
    if not consistent:
        check_status = "inconsistent"
    elif any(item["status"] != "bound" for item in items) or not basis_match:
        check_status = "affected"
    else:
        check_status = "current"
    if not consistent or counts["missing"] > 0:
        next_action = "repair_store"
    elif counts["changed"] > 0:
        next_action = "revise_affected_sections"
    elif counts["stale"] > 0:
        stale_item = next(item for item in items if item["status"] == "stale")
        kind = stale_item["kind"]
        if kind in {"claim", "claim_span", "code_lineage", "source_version"}:
            next_action = "re_record_annotation"
        else:
            next_action = "re_record_condition"
    elif not basis_match:
        next_action = "re_export"
    else:
        next_action = "none"
    view = {
        "schema": CHECK_SCHEMA,
        "article_id": record["article_id"],
        "revision_id": record["revision_id"],
        "revision_location": location,
        "basis_recorded": basis_recorded,
        "basis_current": basis_current,
        "basis_match": basis_match,
        "items": items,
        "sections": section_rows,
        "affected_sections": affected_sections,
        "table_affected": table_affected,
        "citation_consistency": citation_consistency,
        "counts": counts,
        "check_status": check_status,
        "fact_source": "formal_records",
        "write_kind": "read_only",
        "publication": "unpublished",
        "applied": False,
        "audit_coverage": "not_wired",
        "ranking": "not_ranked",
        "typed_fact_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "scientific_conclusion_contradiction": False,
        "next_action": next_action,
    }
    try:
        raw = canonicalize(view)
        sealed = json.loads(raw.decode("utf-8"))
        validate_document(sealed, CHECK_SCHEMA)
    except (CanonicalJsonError, ContractError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        details = dict(getattr(exc, "details", {}) or {})
        raise ArticleRevisionError(
            "ARTICLE_CHECK_INVALID",
            MESSAGES["ARTICLE_CHECK_INVALID"],
            {"reason": "schema", "instance_pointer": details.get("instance_pointer", ""), **details},
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    return sealed


def check_article_revision(*, vault_root, article_id, revision_id, batch_id=None):
    if type(article_id) is not str or ARTICLE_RE.fullmatch(article_id) is None:
        _fail("ARTICLE_CHECK_INVALID", "/article_id", "repair_input")
    if type(revision_id) is not str or REVISION_RE.fullmatch(revision_id) is None:
        _fail("ARTICLE_CHECK_INVALID", "/revision_id", "repair_input")
    if batch_id is not None:
        _batch(batch_id, "/batch_id")

    def apply(snapshot, domain_store, authority):
        vault = _load_article_store(snapshot)
        staged = _load_staged_articles(batch_id)
        merged = _merge(vault, staged)
        record, location, _chain = _lookup_revision(merged, article_id, revision_id)
        exp = _load_experiment_store(snapshot)
        heads = derive_domain_heads(domain_store)
        return check_revision_view(snapshot, domain_store, authority, exp, heads, record, location)

    return _run_with_store(vault_root, apply, authority_required=True)


def _escape_md(text):
    if type(text) is not str:
        text = "" if text is None else str(text)
    escaped = (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("`", "\\`")
        .replace("#", "\\#")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )
    return escaped.replace("\r\n", "\n").replace("\r", "\n")


def _version_label(version):
    if version is None:
        return "未知"
    if type(version) is dict:
        label = version.get("label")
        if type(label) is str and label:
            return label
        kind = version.get("kind")
        if kind == "unknown" or label is None:
            return "未知"
        if type(kind) is str:
            return kind
    return "未知"


def _main_sha(kind, binding):
    if kind == "claim":
        return binding.get("text_sha256")
    if kind == "claim_span":
        return binding.get("excerpt_sha256") or binding.get("sha256")
    if kind in {"condition", "condition_value", "metric_value"}:
        return binding.get("head_record_sha256")
    if kind == "code_lineage":
        return binding.get("head_report_sha256")
    if kind == "comparability":
        return binding.get("left_record_sha256")
    if kind == "source_version":
        return binding.get("raw_sha256")
    return None


def _assign_numbers(record):
    order = []
    seen = set()

    def add(eid):
        if eid not in seen:
            seen.add(eid)
            order.append(eid)

    for section in record["sections"]:
        if section["status"] != "provisional":
            continue
        for eid in CITE_MARK.findall(section["markdown"]):
            add(eid)
    for row in record["comparison_table"]["rows"]:
        for key in COLUMNS:
            add(row["cells"][key]["evidence_id"])
    for cell in record["comparison_table"]["metric_cells"]:
        add(cell["evidence_id"])
    for item in record["bibliography"]:
        add(item["evidence_id"])
    return {eid: index for index, eid in enumerate(order, 1)}, order


def _render_markdown(record, location):
    biblio = {item["evidence_id"]: item for item in record["bibliography"]}
    for index, section in enumerate(record["sections"]):
        marks = set(CITE_ANY.findall(section["markdown"])) if section["status"] == "provisional" else set()
        listed = set(section["citations"])
        for eid in marks | listed:
            if eid in biblio:
                continue
            pointer = "/sections/" + str(index) + (
                "/markdown" if eid in marks and eid not in listed else "/citations"
            )
            _fail(
                "ARTICLE_RENDER_INVALID",
                pointer,
                "repair_store",
                {
                    "reason": "dangling_citation",
                    "section_id": section["section_id"],
                    "evidence_id": eid,
                },
            )
    for row_index, row in enumerate(record["comparison_table"]["rows"]):
        for key in COLUMNS:
            eid = row["cells"][key]["evidence_id"]
            if eid in biblio:
                continue
            _fail(
                "ARTICLE_RENDER_INVALID",
                "/comparison_table/rows/" + str(row_index) + "/cells/" + key,
                "repair_store",
                {"reason": "dangling_citation", "location": "table", "evidence_id": eid},
            )
    for cell_index, cell in enumerate(record["comparison_table"]["metric_cells"]):
        eid = cell["evidence_id"]
        if eid in biblio:
            continue
        _fail(
            "ARTICLE_RENDER_INVALID",
            "/comparison_table/metric_cells/" + str(cell_index),
            "repair_store",
            {"reason": "dangling_citation", "location": "metric", "evidence_id": eid},
        )
    numbers, order = _assign_numbers(record)
    previous = record["previous_revision_id"] or "无"
    lines = [
        "# " + _escape_md(record["title"]),
        "",
        PROVISIONAL_LABEL + "未发布（publication: unpublished）。",
        "",
        "> 研究问题：" + _escape_md(record["question"]),
        "> 论文：" + _escape_md("、".join(record["paper_ids"])),
        "> 修订："
        + record["revision_id"]
        + "（前一版："
        + previous
        + "）· 记录时间 "
        + record["recorded_at"]
        + " · 位置 "
        + location,
        "",
    ]
    has_comparison = any(item["role"] == "comparison" for item in record["sections"])

    def cite_replace(markdown):
        def repl(match):
            eid = match.group(1)
            return "[" + str(numbers[eid]) + "]"

        return CITE_MARK.sub(repl, markdown)

    def render_tables():
        table = record["comparison_table"]
        out = []
        if not table["rows"]:
            out.append("暂无实验条件记录。")
            out.append("")
            return out
        header = ["论文", "设置", "版本"] + list(COLUMNS)
        out.append("| " + " | ".join(_escape_md(col) for col in header) + " |")
        out.append("| " + " | ".join("---" for _ in header) + " |")
        for row in table["rows"]:
            cells = [_escape_md(row["paper_id"]), _escape_md(row["setting_key"]), _escape_md(_version_label(row["version"]))]
            for key in COLUMNS:
                cell = row["cells"][key]
                n = numbers[cell["evidence_id"]]
                status = cell["status"]
                if status == "unknown":
                    text = "未知 [" + str(n) + "]"
                elif status == "not_applicable":
                    text = "不适用 [" + str(n) + "]"
                else:
                    summary = cell["value_summary"] or "未知"
                    text = _escape_md(summary) + " [" + str(n) + "]"
                cells.append(text)
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
        if table["metric_columns"]:
            mheader = ["论文", "设置"] + [item["name"] + " (" + item["unit"] + ")" for item in table["metric_columns"]]
            out.append("| " + " | ".join(_escape_md(col) for col in mheader) + " |")
            out.append("| " + " | ".join("---" for _ in mheader) + " |")
            by_row = {}
            for cell in table["metric_cells"]:
                by_row.setdefault(cell["row_index"], {})[(cell["name"], cell["unit"])] = cell
            for row in table["rows"]:
                cells = [_escape_md(row["paper_id"]), _escape_md(row["setting_key"])]
                found = by_row.get(row["row_index"], {})
                for col in table["metric_columns"]:
                    cell = found.get((col["name"], col["unit"]))
                    if cell is None:
                        cells.append("")
                        continue
                    n = numbers[cell["evidence_id"]]
                    mark = ""
                    hib = cell.get(_HIB)
                    if hib is True:
                        mark = "↑"
                    elif hib is False:
                        mark = "↓"
                    cells.append(_escape_md(str(cell["value"])) + mark + " [" + str(n) + "]")
                out.append("| " + " | ".join(cells) + " |")
            out.append("")
        return out

    for section in record["sections"]:
        lines.append("## " + _escape_md(section["title"]))
        lines.append(
            "（角色：" + ROLE_ZH.get(section["role"], section["role"]) + "；状态：" + STATUS_ZH.get(section["status"], section["status"]) + "）"
        )
        if section["status"] == "unwritten":
            lines.append(UNWRITTEN_TEXT)
        elif section["status"] == "unknown":
            lines.append(UNKNOWN_TEXT)
        else:
            lines.append(cite_replace(section["markdown"]).rstrip())
        lines.append("")
        if section["role"] == "comparison":
            lines.extend(render_tables())
    if not has_comparison:
        lines.append("## 比较表")
        lines.extend(render_tables())
    lines.append("## 参考文献")
    for index, eid in enumerate(order, 1):
        item = biblio[eid]
        binding = item["binding"]
        digest = _main_sha(item["kind"], binding)
        sha_part = digest[:16] if type(digest) is str and digest else "—"
        version = _version_label(binding.get("version"))
        src = item["source"]
        lines.append(
            "["
            + str(index)
            + "] "
            + _escape_md(item["label"])
            + " — "
            + item["kind"]
            + " — 记录 "
            + src["record_kind"]
            + ":"
            + src["record_id"]
            + src["json_pointer"]
            + " — 版本 "
            + _escape_md(version)
            + " — sha256 "
            + sha_part
            + " — 导出时状态 "
            + item["status_at_export"]
        )
        if item["kind"] == "claim_span":
            span = binding.get("charspan") or [0, 0]
            lines.append(
                "   > 定位 "
                + _escape_md(binding.get("path") or "")
                + "#"
                + str(span[0])
                + "-"
                + str(span[1])
                + " · "
                + str(binding.get("relation") or "")
            )
    text = "\n".join(lines).rstrip("\n") + "\n"
    return text.encode("utf-8")


def render_article_revision(*, vault_root, batch_id, article_id, revision_id):
    batch = _batch(batch_id, "/batch_id")
    if type(article_id) is not str or ARTICLE_RE.fullmatch(article_id) is None:
        _fail("ARTICLE_RENDER_INVALID", "/article_id", "repair_input")
    if type(revision_id) is not str or REVISION_RE.fullmatch(revision_id) is None:
        _fail("ARTICLE_RENDER_INVALID", "/revision_id", "repair_input")

    def apply(snapshot, domain_store, authority):
        vault = _load_article_store(snapshot)
        staged = _load_staged_articles(batch)
        merged = _merge(vault, staged)
        record, location, _chain = _lookup_revision(merged, article_id, revision_id)
        md = _render_markdown(record, location)
        stage_bytes(batch_id=batch, relative=("articles", "render", record["article_id"], record["revision_id"] + ".md"), data=md)
        progress = record["progress"]
        complete = progress["unwritten"] == 0
        relative = ".work/" + batch + "/articles/render/" + record["article_id"] + "/" + record["revision_id"] + ".md"
        return {
            "state": "markdown_rendered",
            "article_id": record["article_id"],
            "revision_id": record["revision_id"],
            "revision_location": location,
            "markdown_path": relative,
            "markdown_sha256": sha(md),
            "size_bytes": len(md),
            "complete": complete,
            "progress": progress,
            "bibliography_count": len(record["bibliography"]),
            "table_rows": len(record["comparison_table"]["rows"]),
            "metric_columns": len(record["comparison_table"]["metric_columns"]),
            "publication": "unpublished",
            "applied": False,
            "write_kind": "work_staging",
            "audit_coverage": "not_wired",
            "ranking": "not_ranked",
            "typed_fact_promotion": "none",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": "check_revision" if complete else "write_unwritten_sections",
        }

    try:
        return _run_with_store(vault_root, apply, authority_required=True)
    except OSError:
        _store_fail("ARTICLE_STORE_CHANGED", "/wiki/meta/articles", "repeat_read", exit_code=75)


def status_article_store(*, vault_root, batch_id=None):
    if batch_id is not None:
        _batch(batch_id, "/batch_id")

    def apply(snapshot, domain_store, authority):
        vault = _load_article_store(snapshot)
        staged = _load_staged_articles(batch_id)
        merged = _merge(vault, staged)
        exp = _load_experiment_store(snapshot)
        basis = dict(_experiment_basis(snapshot, domain_store, authority, exp))
        basis["article_store_inventory_sha256"] = article_inventory_digest(vault)
        articles = []
        for art in _byte_sort(list(merged.chains)):
            chain = merged.chains[art]
            head_id = chain["record_order"][-1]
            head = merged.records[head_id]
            vault_count = 0
            staged_count = 0
            for rid in chain["record_order"]:
                if merged.locations.get(rid) == "staged":
                    staged_count += 1
                else:
                    vault_count += 1
            articles.append(
                {
                    "article_id": art,
                    "question": head["question"],
                    "paper_ids": list(head["paper_ids"]),
                    "head_revision_id": head_id,
                    "head_record_sha256": sha(merged.record_raw[head_id]),
                    "head_location": merged.locations.get(head_id, "vault_store"),
                    "revision_count": len(chain["record_order"]),
                    "staged_revision_count": staged_count,
                    "vault_revision_count": vault_count,
                    "kind": head["kind"],
                    "progress": head["progress"],
                    "recorded_at": head["recorded_at"],
                    "complete": head["progress"]["unwritten"] == 0,
                }
            )
        return {
            "basis": basis,
            "staged_batch": batch_id,
            "article_count": len(articles),
            "articles": articles,
            "publication": "unpublished",
            "write_kind": "read_only",
            "audit_coverage": "not_wired",
            "backup_coverage": "not_wired",
            "ranking": "not_ranked",
            "typed_fact_promotion": "none",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": "none" if not articles else "check_revisions",
        }

    return _run_with_store(vault_root, apply, authority_required=True)


def article_history(*, vault_root, article_id, batch_id=None):
    if type(article_id) is not str or ARTICLE_RE.fullmatch(article_id) is None:
        raise ArticleStoreError(
            "ARTICLE_UNKNOWN",
            "article_id is unknown",
            {"instance_pointer": "/article_id", "next_action": "check_article_id"},
        )
    if batch_id is not None:
        _batch(batch_id, "/batch_id")

    def apply(snapshot, domain_store, authority):
        vault = _load_article_store(snapshot)
        staged = _load_staged_articles(batch_id)
        merged = _merge(vault, staged)
        chain = merged.chains.get(article_id)
        if chain is None:
            raise ArticleStoreError(
                "ARTICLE_UNKNOWN",
                "article_id is unknown",
                {"instance_pointer": "/article_id", "next_action": "check_article_id"},
            )
        head_id = chain["record_order"][-1]
        head = merged.records[head_id]
        revisions = []
        last = len(chain["record_order"]) - 1
        for index, rid in enumerate(chain["record_order"]):
            rec = merged.records[rid]
            revisions.append(
                {
                    "revision_id": rid,
                    "previous_revision_id": rec["previous_revision_id"],
                    "kind": rec["kind"],
                    "target_section_id": rec["target_section_id"],
                    "recorded_at": rec["recorded_at"],
                    "recorded_by": rec["recorded_by"],
                    "content_sha256": rec["content_sha256"],
                    "record_sha256": sha(merged.record_raw[rid]),
                    "location": merged.locations.get(rid, "vault_store"),
                    "superseded": index != last,
                    "progress": rec["progress"],
                    "basis": rec["basis"],
                }
            )
        return {
            "article_id": article_id,
            "question": head["question"],
            "paper_ids": list(head["paper_ids"]),
            "head_revision_id": head_id,
            "revisions": revisions,
            "publication": "unpublished",
            "write_kind": "read_only",
            "audit_coverage": "not_wired",
            "backup_coverage": "not_wired",
            "ranking": "not_ranked",
            "typed_fact_promotion": "none",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": "none",
        }

    return _run_with_store(vault_root, apply, authority_required=True)
