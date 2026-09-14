"""Read-only experiment comparison matrix. Vault writes are forbidden."""

from __future__ import annotations

import json

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import _claim_freshness
from video_paper_wiki.experiment_comparability import ExperimentComparabilityError, _summary, compare_experiment_records
from video_paper_wiki.experiment_publication import _experiment_basis
from video_paper_wiki.experiment_store import (
    CRITICAL_CONDITIONS,
    KNOWN_STATUSES,
    STALE_BINDINGS,
    _association_lookup,
    _association_status,
    _byte_sort,
    _check_source_digest,
    _code_binding_status,
    _load_experiment_store,
    _run_with_store,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.source_semantics_contracts import sha

MATRIX_SCHEMA = "video-paper-wiki.experiment-comparison-matrix.v1"
MATRIX_COMMAND = "experiments.matrix"
MAX_PAIRWISE_ROWS = 64
PAPER_ID_LIMIT = 256
COLUMNS = (
    "model_checkpoint",
    "parameter_count",
    "dataset_split",
    "metrics",
    "resolution",
    "frames",
    "inference_steps",
    "sampling_guidance",
    "evaluation_setup",
)
MESSAGES = {
    "EXPERIMENT_MATRIX_INVALID": "experiment matrix input is invalid",
    "EXPERIMENT_MATRIX_PAPER_UNKNOWN": "experiment matrix paper_id is unknown",
    "EXPERIMENT_MATRIX_LIMIT": "experiment matrix exceeds a closed bound",
}


class ExperimentMatrixError(Exception):
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
    raise ExperimentMatrixError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _check_paper_id(paper_id):
    if paper_id is None:
        return
    if type(paper_id) is not str or not paper_id or len(paper_id.encode("utf-8")) > PAPER_ID_LIMIT:
        _fail("EXPERIMENT_MATRIX_INVALID", "/paper_id", "repair_input")


def _row_version(snapshot, record, association_status):
    if association_status != "bound":
        return None
    _state, _reason, doc = _association_lookup(snapshot, record)
    if doc is None:
        return None
    return doc["version"]


def _code_binding_view(domain_store, record):
    binding = record["code_binding"]
    if binding is None:
        return None
    return {
        "lineage_id": binding["lineage_id"],
        "annotation_id": binding["annotation_id"],
        "repository": binding["repository"],
        "commit": binding["commit"],
        "binding_status": _code_binding_status(domain_store, record),
    }


def _matrix_row(snapshot, domain_store, authority, exp, cid, row_index):
    chain = exp.chains[cid]
    head_id = chain["record_order"][-1]
    record = exp.records[head_id]
    association_status = _association_status(snapshot, record)
    source_status = _check_source_digest(snapshot, record["source_digest"], error=False)
    binding_status = _code_binding_status(domain_store, record)
    stale_claims = 0
    bound_claims = 0
    for item in record["claim_refs"]:
        freshness, _reason = _claim_freshness(item, authority)
        if freshness == "stale":
            stale_claims += 1
        else:
            bound_claims += 1
    stale = (
        association_status != "bound"
        or source_status != "bound"
        or stale_claims > 0
        or (binding_status in STALE_BINDINGS)
    )
    return {
        "row_index": row_index,
        "condition_id": cid,
        "record_id": head_id,
        "record_sha256": sha(exp.record_raw[head_id]),
        "paper_id": record["paper_id"],
        "source_association_id": record["source_association"]["association_id"],
        "version": _row_version(snapshot, record, association_status),
        "association_status": association_status,
        "source_status": source_status,
        "setting_key": record["setting_key"],
        "code_binding": _code_binding_view(domain_store, record),
        "claim_freshness": {"head_bound": bound_claims, "stale": stale_claims},
        "row_status": "stale" if stale else "current",
    }, record


def _cells_for_row(row_index, record):
    cells = []
    for key in COLUMNS:
        cond = record["conditions"][key]
        status = cond["status"]
        value_summary = _summary(cond["value"]) if status in KNOWN_STATUSES else None
        sources = cond.get("sources") or []
        source_pointers = [
            {"record_id": record["record_id"], "json_pointer": "/conditions/" + key + "/sources/" + str(index)}
            for index in range(len(sources))
        ]
        search_scope_pointer = "/conditions/" + key + "/search_scope" if status == "unknown" else None
        cells.append(
            {
                "row_index": row_index,
                "column": key,
                "status": status,
                "value_summary": value_summary,
                "source_count": len(sources),
                "source_pointers": source_pointers,
                "search_scope_pointer": search_scope_pointer,
            }
        )
    return cells


def _metric_parts(records_by_index):
    columns = []
    seen = set()
    cells = []
    for row_index, record in records_by_index:
        cond = record["conditions"]["metrics"]
        if cond["status"] not in KNOWN_STATUSES:
            continue
        for index, metric in enumerate(cond["value"]):
            pair = (metric["name"], metric["unit"])
            if pair not in seen:
                seen.add(pair)
                columns.append({"name": metric["name"], "unit": metric["unit"]})
            definition = metric.get("definition_source")
            pointer = None
            if definition is not None:
                pointer = "/conditions/metrics/value/" + str(index) + "/definition_source"
            cells.append(
                {
                    "row_index": row_index,
                    "name": metric["name"],
                    "unit": metric["unit"],
                    "value": metric["value"],
                    "higher_is_better": metric["higher_is_better"],
                    "definition_source_pointer": pointer,
                }
            )
    columns.sort(key=lambda item: (item["name"].encode("utf-8"), item["unit"].encode("utf-8")))
    if len(columns) > 128:
        _fail(
            "EXPERIMENT_MATRIX_LIMIT",
            "/metric_columns",
            "filter_paper_id",
            {"reason": "metric_columns"},
        )
    if len(cells) > 4096:
        _fail(
            "EXPERIMENT_MATRIX_LIMIT",
            "/metric_cells",
            "filter_paper_id",
            {"reason": "metric_cells"},
        )
    return columns, cells


def _pairwise(records_by_index):
    row_count = len(records_by_index)
    if row_count > MAX_PAIRWISE_ROWS:
        _fail(
            "EXPERIMENT_MATRIX_LIMIT",
            "/rows",
            "filter_paper_id",
            {"reason": "pairwise_rows", "row_count": row_count, "limit": MAX_PAIRWISE_ROWS},
        )
    pairs = []
    for i in range(row_count):
        for j in range(i + 1, row_count):
            left = records_by_index[i][1]
            right = records_by_index[j][1]
            try:
                pairs.append(compare_experiment_records(left, right))
            except ExperimentComparabilityError as exc:
                _fail(
                    "EXPERIMENT_MATRIX_INVALID",
                    "/pairwise",
                    "repair_input",
                    {
                        "reason": "compare",
                        "left_record_id": left["record_id"],
                        "right_record_id": right["record_id"],
                        **dict(exc.details or {}),
                    },
                )
    return pairs


def _next_action(rows, records_by_index, pairwise):
    if any(row["row_status"] == "stale" for row in rows):
        return "re_record_condition"
    for _index, record in records_by_index:
        conditions = record["conditions"]
        if any(conditions[key]["status"] == "unknown" for key in CRITICAL_CONDITIONS):
            return "supply_missing_conditions"
    if any(item.get("contradiction_candidates") for item in pairwise):
        return "review_findings"
    return "none"


def build_experiment_comparison_matrix(*, vault_root, paper_id=None):
    _check_paper_id(paper_id)

    def apply(snapshot, domain_store, authority):
        exp = _load_experiment_store(snapshot)
        basis = _experiment_basis(snapshot, domain_store, authority, exp)
        ordered = _byte_sort(list(exp.chains))
        built = []
        for cid in ordered:
            built.append(_matrix_row(snapshot, domain_store, authority, exp, cid, 0))
        if paper_id is not None:
            known = {row["paper_id"] for row, _record in built}
            if paper_id not in known:
                _fail(
                    "EXPERIMENT_MATRIX_PAPER_UNKNOWN",
                    "/paper_id",
                    "check_paper_id",
                    {"known_paper_count": len(known)},
                )
            built = [(row, record) for row, record in built if row["paper_id"] == paper_id]
        rows = []
        records_by_index = []
        cells = []
        for index, (row, record) in enumerate(built):
            row = dict(row)
            row["row_index"] = index
            rows.append(row)
            records_by_index.append((index, record))
            cells.extend(_cells_for_row(index, record))
        metric_columns, metric_cells = _metric_parts(records_by_index)
        pairwise = _pairwise(records_by_index)
        document = {
            "schema": MATRIX_SCHEMA,
            "basis": basis,
            "paper_filter": paper_id,
            "row_count": len(rows),
            "rows": rows,
            "columns": list(COLUMNS),
            "metric_columns": metric_columns,
            "cells": cells,
            "metric_cells": metric_cells,
            "pairwise": pairwise,
            "ranking": "not_ranked",
            "publication": "unpublished",
            "write_kind": "read_only",
            "audit_coverage": "not_wired",
            "code_freshness": "not_checked",
            "code_source_verification": "not_checked",
            "scientific_conclusion_contradiction": False,
            "typed_fact_promotion": "none",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": _next_action(rows, records_by_index, pairwise),
        }
        try:
            raw = canonicalize(document)
            sealed = json.loads(raw.decode("utf-8"))
        except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            _fail("EXPERIMENT_MATRIX_INVALID", "", "repair_input", {"reason": "schema"})
        try:
            validate_document(sealed, MATRIX_SCHEMA)
        except ContractError as exc:
            pointer = exc.details.get("instance_pointer") or ""
            raise ExperimentMatrixError(
                "EXPERIMENT_MATRIX_INVALID",
                MESSAGES["EXPERIMENT_MATRIX_INVALID"],
                {"instance_pointer": pointer, "next_action": "repair_input", "reason": "schema", **exc.details},
                exit_code=getattr(exc, "exit_code", 2),
            ) from exc
        return sealed

    return _run_with_store(vault_root, apply, authority_required=True)
