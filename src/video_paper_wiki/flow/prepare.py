"""Prepare experiment-record and article-import inputs under .work/<batch>/flow/."""

from __future__ import annotations

import hashlib
import re

from video_paper_wiki.article_context import export_article_context
from video_paper_wiki.article_store import MAX_TITLE
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_versions import build_domain_source_version_view
from video_paper_wiki.experiment_store import CONDITION_KEYS, INPUT_KEYS
from video_paper_wiki.flow.actions import (
    PREPARE_SCHEMA,
    RECORD_DOMAIN_NEXT,
    ROLE_GOALS,
    assemble_next_actions,
    fail,
    invariants,
    missing_item,
    setting_key_schema,
    unique_sorted,
)
from video_paper_wiki.flow.status import build_flow_status
from video_paper_wiki.identity import is_canonical_paper_id
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staging import stage_bytes, validate_batch_id

EXPORT_COMMAND = "articles.export"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _relative(*parts):
    return "/".join(parts)


def _select_argv(vault_root, batch_id):
    return [
        "flow",
        "select",
        "--vault-root",
        vault_root,
        "--batch-id",
        batch_id,
        "--paper-id",
        "<paper_id>",
    ]


def _check_paper_ids(paper_ids):
    if type(paper_ids) is not list:
        fail("FLOW_INVALID", "/paper_ids", "repair_input")
    for index, item in enumerate(paper_ids):
        if type(item) is not str or not is_canonical_paper_id(item):
            fail("FLOW_INVALID", "/paper_ids/" + str(index), "repair_input")
    ordered = unique_sorted(paper_ids)
    if not ordered or len(ordered) > 8:
        fail("FLOW_INVALID", "/paper_ids", "repair_input")
    return ordered


def _unknown_slot(name, artifact_path):
    return {
        "status": "unknown",
        "value": None,
        "basis_note": None,
        "sources": [],
        "search_scope": {"artifact_paths": [artifact_path], "search_terms": [name]},
    }


def _stage_output(batch_id, relative, data, consumer):
    result = stage_bytes(batch_id=batch_id, relative=relative, data=data)
    path = _relative(".work", batch_id, *relative)
    return {
        "path": path,
        "sha256": _sha256(data),
        "size_bytes": len(data),
        "staging": "already_staged" if result.already_staged else "new",
        "consumer": consumer,
    }


def _lineages_for(vault_root, paper_id):
    versions = build_domain_source_version_view(vault_root=vault_root)
    rows = []
    for row in versions.get("lineages") or []:
        if type(row) is dict and row.get("paper_id") == paper_id:
            rows.append(row)
    return rows


def _prepare_experiment(*, vault_root, batch_id, status, paper_ids, setting_key, selection):
    if len(paper_ids) != 1:
        fail("FLOW_INVALID", "/paper_ids", "repair_input", {"reason": "single_paper_required"})
    paper_id = paper_ids[0]
    d1_rows = _lineages_for(vault_root, paper_id)
    if not d1_rows:
        fail(
            "FLOW_PREPARE_BLOCKED",
            "/paper_id",
            RECORD_DOMAIN_NEXT,
            {
                "reason": "no_lineage",
                "argv": [
                    "domain",
                    "record",
                    "--input",
                    "<input_json>",
                    "--vault-root",
                    vault_root,
                    "--code-batch-id",
                    "<code_batch_id>",
                    "--batch-id",
                    batch_id,
                    "--recorded-by",
                    "<recorded_by>",
                    "--recorded-at",
                    "<recorded_at>",
                ],
            },
        )
    assoc_ids = unique_sorted({row["source_association_id"] for row in d1_rows})
    chosen = None if selection is None else selection.get("association_id")
    if chosen is None:
        if len(assoc_ids) != 1:
            fail(
                "FLOW_PREPARE_BLOCKED",
                "/association_id",
                "select",
                {"reason": "association_ambiguous", "candidates": assoc_ids},
            )
        chosen = assoc_ids[0]
    matched = [row for row in d1_rows if row.get("source_association_id") == chosen]
    if not matched:
        fail(
            "FLOW_PREPARE_BLOCKED",
            "/association_id",
            "select",
            {"reason": "association_ambiguous", "candidates": assoc_ids},
        )
    if any(row.get("association_status") != "bound" for row in matched):
        fail(
            "FLOW_PREPARE_BLOCKED",
            "/association_id",
            RECORD_DOMAIN_NEXT,
            {"reason": "association_unbound", "association_status": matched[0].get("association_status")},
        )
    head = matched[0]
    for key in ("association_record_sha256", "source_digest", "head_annotation_id", "repository", "commit", "lineage_id"):
        if key not in head:
            fail("FLOW_INVALID", "/build_domain_source_version_view", "repair_input", {"reason": "upstream_shape"})
    digest = head["source_digest"]
    if type(digest) is not dict:
        fail("FLOW_INVALID", "/build_domain_source_version_view", "repair_input", {"reason": "upstream_shape"})
    code_binding = None
    missing = []
    if len(matched) == 1:
        code_binding = {
            "lineage_id": head["lineage_id"],
            "annotation_id": head["head_annotation_id"],
            "repository": head["repository"],
            "commit": head["commit"],
        }
    else:
        missing.append(
            missing_item(
                "code-binding",
                "compare",
                "code_binding",
                "multiple lineages share the selected association",
                [row["lineage_id"] for row in matched],
            )
        )
    conditions = {name: _unknown_slot(name, digest["path"]) for name in CONDITION_KEYS}
    draft = {
        "paper_id": paper_id,
        "source_association": {
            "association_id": chosen,
            "sha256": head["association_record_sha256"],
        },
        "source_digest": {
            "path": digest["path"],
            "sha256": digest["sha256"],
            "size_bytes": digest["size_bytes"],
        },
        "code_binding": code_binding,
        "setting_key": setting_key,
        "conditions": conditions,
        "claim_refs": [],
    }
    if set(draft) != INPUT_KEYS:
        fail("FLOW_INVALID", "/experiment", "repair_input", {"reason": "upstream_shape"})
    previous = None
    paper_row = next((row for row in status["papers"] if row["paper_id"] == paper_id), None)
    if paper_row is not None:
        for cond in paper_row["conditions"]:
            if cond.get("setting_key") == setting_key:
                previous = cond["head_record_id"]
                break
    relative = ("flow", "experiments", setting_key, "input.json")
    payload = canonicalize(draft)
    path = _relative(".work", batch_id, *relative)
    outputs = [
        {
            "path": path,
            "sha256": _sha256(payload),
            "size_bytes": len(payload),
            "staging": "new",
            "consumer": "experiments.record --input",
        }
    ]
    binding = {
        "paper_id": paper_id,
        "source_association_id": chosen,
        "association_record_sha256": head["association_record_sha256"],
        "source_digest": {
            "path": digest["path"],
            "sha256": digest["sha256"],
            "size_bytes": digest["size_bytes"],
        },
        "code_binding": code_binding,
        "setting_key": setting_key,
        "previous_record_id": previous,
    }
    document = _result_document(
        kind="experiment",
        batch_id=batch_id,
        paper_ids=paper_ids,
        outputs=outputs,
        experiment_binding=binding,
        article_binding=None,
        missing_inputs=missing,
        next_actions=[],
        basis=status["basis"],
    )
    validate_document(document, PREPARE_SCHEMA)
    staged = _stage_output(batch_id, relative, payload, "experiments.record --input")
    document["outputs"] = [staged]
    document["next_actions"] = assemble_next_actions(
        vault_root=vault_root,
        batch_id=batch_id,
        selection=selection,
        papers=status["papers"],
        universe_ids=[row["paper_id"] for row in status["papers"]],
        condition_count=status["counts"]["conditions"],
        experiment_next=None,
        articles=[item for row in status["papers"] for item in row["articles"]],
        kind="experiment",
        prepare_paths=[staged["path"]],
        previous_record_id=previous,
        setting_key=setting_key,
    )
    return document


def _reject_cite_mark_in_title(vault_root, batch_id, question):
    if "[@" not in question:
        return
    fail(
        "FLOW_INVALID",
        "/question",
        "repair_input",
        {
            "reason": "cite_mark_in_title",
            "argv": [
                "flow",
                "prepare",
                "--vault-root",
                vault_root,
                "--batch-id",
                batch_id,
                "--kind",
                "article",
                "--question",
                "<question>",
            ],
        },
    )


def _article_title(question):
    if len(question) <= MAX_TITLE:
        return question
    return question[:MAX_TITLE]


def _prepare_article(*, vault_root, batch_id, status, paper_ids, question, selection):
    if question is None:
        fail("FLOW_INVALID", "/question", "repair_input", {"reason": "question_required"})
    _reject_cite_mark_in_title(vault_root, batch_id, question)
    data = export_article_context(vault_root=vault_root, question=question, paper_ids=paper_ids)
    envelope = canonicalize({"ok": True, "command": EXPORT_COMMAND, "data": data})
    article_id = data["article_id"]
    roles = list(data["context"]["required_roles"])
    if len(paper_ids) >= 2 and "comparison" not in roles:
        roles.append("comparison")
    sections = []
    for index, role in enumerate(roles, 1):
        sections.append(
            {
                "section_id": "s" + str(index),
                "role": role,
                "title": role,
                "goal": ROLE_GOALS[role],
                "status": "unwritten",
                "markdown": "",
                "citations": [],
            }
        )
    body = {
        "schema": "video-paper-wiki.article-document.v1",
        "title": _article_title(question),
        "sections": sections,
    }
    document_bytes = canonicalize(body)
    ctx_rel = ("flow", "articles", article_id, "context.json")
    doc_rel = ("flow", "articles", article_id, "document.json")
    ctx_path = _relative(".work", batch_id, *ctx_rel)
    doc_path = _relative(".work", batch_id, *doc_rel)
    outputs = [
        {
            "path": ctx_path,
            "sha256": _sha256(envelope),
            "size_bytes": len(envelope),
            "staging": "new",
            "consumer": "articles.import --context",
        },
        {
            "path": doc_path,
            "sha256": _sha256(document_bytes),
            "size_bytes": len(document_bytes),
            "staging": "new",
            "consumer": "articles.import --document",
        },
    ]
    binding = {
        "article_id": article_id,
        "question": question,
        "paper_ids": list(paper_ids),
        "context_sha256": data["context_sha256"],
        "section_ids": [item["section_id"] for item in sections],
    }
    document = _result_document(
        kind="article",
        batch_id=batch_id,
        paper_ids=paper_ids,
        outputs=outputs,
        experiment_binding=None,
        article_binding=binding,
        missing_inputs=[],
        next_actions=[],
        basis=status["basis"],
    )
    validate_document(document, PREPARE_SCHEMA)
    staged_ctx = _stage_output(batch_id, ctx_rel, envelope, "articles.import --context")
    staged_doc = _stage_output(batch_id, doc_rel, document_bytes, "articles.import --document")
    document["outputs"] = [staged_ctx, staged_doc]
    document["next_actions"] = assemble_next_actions(
        vault_root=vault_root,
        batch_id=batch_id,
        selection=selection,
        papers=status["papers"],
        universe_ids=[row["paper_id"] for row in status["papers"]],
        condition_count=status["counts"]["conditions"],
        experiment_next=None,
        articles=[item for row in status["papers"] for item in row["articles"]],
        kind="article",
        prepare_paths=[staged_ctx["path"], staged_doc["path"]],
    )
    return document


def _result_document(
    *,
    kind,
    batch_id,
    paper_ids,
    outputs,
    experiment_binding,
    article_binding,
    missing_inputs,
    next_actions,
    basis,
):
    document = {
        "schema": PREPARE_SCHEMA,
        "state": "prepared",
        "kind": kind,
        "batch_id": batch_id,
        "paper_ids": list(paper_ids),
        "outputs": outputs,
        "experiment_binding": experiment_binding,
        "article_binding": article_binding,
        "missing_inputs": missing_inputs,
        "next_actions": next_actions,
        "basis": basis,
    }
    document.update(invariants("work_staging"))
    return document


def prepare_flow(*, vault_root, batch_id, kind, setting_key=None, paper_ids=None, question=None):
    validate_batch_id(batch_id)
    if kind not in {"experiment", "article"}:
        fail("FLOW_INVALID", "/kind", "repair_input")
    if kind == "article" and setting_key is not None:
        fail("FLOW_INVALID", "/setting_key", "repair_input", {"reason": "kind_argument"})
    if kind == "experiment" and question is not None:
        fail("FLOW_INVALID", "/question", "repair_input", {"reason": "kind_argument"})
    if kind == "experiment":
        if type(setting_key) is not str:
            fail("FLOW_INVALID", "/setting_key", "repair_input")
        spec = setting_key_schema()
        pattern = spec.get("pattern")
        if pattern is None or re.fullmatch(pattern, setting_key) is None:
            fail("FLOW_INVALID", "/setting_key", "repair_input")
        if spec.get("minLength") is not None and len(setting_key) < spec["minLength"]:
            fail("FLOW_INVALID", "/setting_key", "repair_input")
        if spec.get("maxLength") is not None and len(setting_key) > spec["maxLength"]:
            fail("FLOW_INVALID", "/setting_key", "repair_input")
    if paper_ids is not None:
        paper_ids = _check_paper_ids(paper_ids)
    status = build_flow_status(vault_root=vault_root, batch_id=batch_id)
    selection = None
    if status["selection"] is not None:
        selection = {
            "paper_ids": list(status["selection"]["paper_ids"]),
            "association_id": status["selection"]["association_id"],
            "question": status["selection"]["question"],
        }
    if paper_ids is None:
        if selection is None:
            fail(
                "FLOW_SELECTION_MISSING",
                "/batch_id",
                "select",
                {"argv": _select_argv(vault_root, batch_id)},
            )
        paper_ids = list(selection["paper_ids"])
    else:
        universe = {row["paper_id"] for row in status["papers"]}
        for index, item in enumerate(paper_ids):
            if item not in universe:
                fail(
                    "FLOW_INVALID",
                    "/paper_ids/" + str(index),
                    "repair_input",
                    {"reason": "unknown_paper", "known_paper_count": len(status["papers"])},
                )
        if selection is None:
            selection = {"paper_ids": paper_ids, "association_id": None, "question": question}
        else:
            selection = dict(selection)
            selection["paper_ids"] = paper_ids
    if question is not None:
        if selection is None:
            selection = {"paper_ids": paper_ids, "association_id": None, "question": question}
        else:
            selection = dict(selection)
            selection["question"] = question
    elif selection is not None:
        question = selection.get("question")
    if kind == "experiment":
        return _prepare_experiment(
            vault_root=vault_root,
            batch_id=batch_id,
            status=status,
            paper_ids=paper_ids,
            setting_key=setting_key,
            selection=selection,
        )
    return _prepare_article(
        vault_root=vault_root,
        batch_id=batch_id,
        status=status,
        paper_ids=paper_ids,
        question=question,
        selection=selection,
    )
