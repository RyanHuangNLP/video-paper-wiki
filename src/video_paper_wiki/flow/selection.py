"""Write a session selection document under .work/<batch>/flow/."""

from __future__ import annotations

import hashlib
import re

from video_paper_wiki.contracts import validate_document
from video_paper_wiki.flow.actions import (
    CONTROL_RE,
    OUTPUT_BASIS_KEYS,
    SELECTION_SCHEMA,
    association_id_pattern,
    fail,
    invariants,
    question_max_length,
    unique_sorted,
)
from video_paper_wiki.flow.status import build_flow_status
from video_paper_wiki.identity import is_canonical_paper_id
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staging import stage_bytes, validate_batch_id


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _check_question(question):
    if type(question) is not str or question == "":
        fail("FLOW_SELECTION_INVALID", "/question", "repair_input")
    if len(question) > question_max_length():
        fail("FLOW_SELECTION_INVALID", "/question", "repair_input")
    if CONTROL_RE.search(question):
        fail("FLOW_SELECTION_INVALID", "/question", "repair_input")


def _check_association(association_id):
    if type(association_id) is not str or re.fullmatch(association_id_pattern(), association_id) is None:
        fail("FLOW_SELECTION_INVALID", "/association_id", "repair_input")


def select_flow(*, vault_root, batch_id, paper_ids, association_id=None, question=None):
    validate_batch_id(batch_id)
    if type(paper_ids) is not list:
        fail("FLOW_SELECTION_INVALID", "/paper_ids", "repair_input")
    for index, item in enumerate(paper_ids):
        if type(item) is not str or not is_canonical_paper_id(item):
            fail("FLOW_SELECTION_INVALID", "/paper_ids/" + str(index), "repair_input")
    ordered = unique_sorted(paper_ids)
    if not ordered or len(ordered) > 8:
        fail("FLOW_SELECTION_INVALID", "/paper_ids", "repair_input")
    if question is not None:
        _check_question(question)
    if association_id is not None:
        _check_association(association_id)
    status = build_flow_status(vault_root=vault_root, batch_id=None)
    universe = {row["paper_id"] for row in status["papers"]}
    by_id = {row["paper_id"]: row for row in status["papers"]}
    for index, item in enumerate(paper_ids):
        if item not in universe:
            fail(
                "FLOW_SELECTION_INVALID",
                "/paper_ids/" + str(index),
                "repair_input",
                {"reason": "unknown_paper", "known_paper_count": len(status["papers"])},
            )
    first = by_id[ordered[0]]
    assoc_ids = unique_sorted({row["source_association_id"] for row in first["lineages"]})
    derived = []
    chosen = association_id
    if chosen is not None:
        if chosen not in assoc_ids:
            fail(
                "FLOW_SELECTION_INVALID",
                "/association_id",
                "repair_input",
                {"reason": "association_not_of_paper"},
            )
    elif len(assoc_ids) == 1:
        chosen = assoc_ids[0]
        derived.append("association_id")
    basis = {}
    for key in OUTPUT_BASIS_KEYS:
        basis[key] = status["basis"][key]
    document = {
        "schema": SELECTION_SCHEMA,
        "batch_id": batch_id,
        "paper_ids": ordered,
        "association_id": chosen,
        "question": question,
        "basis": basis,
        "publication": "unpublished",
        "write_kind": "work_staging",
    }
    validate_document(document, SELECTION_SCHEMA)
    payload = canonicalize(document)
    result = stage_bytes(batch_id=batch_id, relative=("flow", "selection.json"), data=payload)
    live = build_flow_status(vault_root=vault_root, batch_id=batch_id)
    data = {
        "state": "already_selected" if result.already_staged else "selected",
        "selection": document,
        "selection_path": ".work/" + batch_id + "/flow/selection.json",
        "selection_sha256": _sha256(payload),
        "derived": derived,
        "missing_inputs": live["missing_inputs"],
        "next_actions": live["next_actions"],
    }
    data.update(invariants("work_staging"))
    return data
