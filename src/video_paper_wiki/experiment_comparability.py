"""Pure-function comparability of two sealed experiment-condition records."""

from __future__ import annotations

import json

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.source_semantics_contracts import sha

COMPARABILITY_SCHEMA = "video-paper-wiki.experiment-comparability.v1"
RECORD_SCHEMA = "video-paper-wiki.experiment-condition-record.v1"
KNOWN = frozenset({"reported", "derived"})
CRITICAL_RULES = (
    "same_benchmark_and_split",
    "same_metric_definition",
    "same_metric_unit",
    "same_resolution",
    "same_frame_count",
    "same_evaluation_protocol",
)
RULES = (
    ("same_benchmark_and_split", True, "dataset_split"),
    ("same_metric_definition", True, "metrics"),
    ("same_metric_unit", True, "metrics"),
    ("same_resolution", True, "resolution"),
    ("same_frame_count", True, "frames"),
    ("same_evaluation_protocol", True, "evaluation_setup"),
    ("checkpoint_identified", False, "model_checkpoint"),
    ("parameter_basis_declared", False, "parameter_count"),
    ("inference_steps_declared", False, "inference_steps"),
    ("guidance_declared", False, "sampling_guidance"),
    ("same_source_version_within_paper", False, "source_association"),
)
CONDITION_KEYS = (
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
UNKNOWN_OUTCOMES = frozenset({"unknown_left", "unknown_right", "unknown_both"})
MESSAGES = {
    "EXPERIMENT_COMPARE_INVALID": "experiment comparability input is invalid",
}


class ExperimentComparabilityError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


def _fail(reason, pointer):
    raise ExperimentComparabilityError(
        "EXPERIMENT_COMPARE_INVALID",
        MESSAGES["EXPERIMENT_COMPARE_INVALID"],
        {"instance_pointer": pointer, "next_action": "repair_input", "reason": reason},
    )


def _load_record(record, pointer):
    if type(record) is not dict:
        _fail("schema", pointer)
    try:
        sealed = validate_document(record, RECORD_SCHEMA)
    except ContractError:
        _fail("schema", pointer)
    return sealed


def _status(record, key):
    return record["conditions"][key]["status"]


def _value(record, key):
    return record["conditions"][key]["value"]


def _unknown_outcome(left_unknown, right_unknown):
    if left_unknown and right_unknown:
        return "unknown_both"
    if left_unknown:
        return "unknown_left"
    return "unknown_right"


def _status_outcome(left, right, key):
    ls = _status(left, key)
    rs = _status(right, key)
    left_unknown = ls == "unknown"
    right_unknown = rs == "unknown"
    if left_unknown or right_unknown:
        return _unknown_outcome(left_unknown, right_unknown), "condition_unknown"
    if ls == "not_applicable" and rs == "not_applicable":
        return "not_applicable", None
    if ls == "not_applicable" or rs == "not_applicable":
        return "violated", "condition_differs"
    return None, None


def _summary(value):
    if value is None:
        return None
    try:
        text = canonicalize(value).decode("utf-8")
    except CanonicalJsonError:
        return None
    if len(text) > 512:
        return text[:509] + "..."
    return text


def _equal_jcs(left, right):
    try:
        return canonicalize(left) == canonicalize(right)
    except CanonicalJsonError:
        return False


def _metric_map(record):
    cond = record["conditions"]["metrics"]
    if cond["status"] not in KNOWN:
        return None
    return {item["name"]: item for item in cond["value"]}


def _byte_sort(values):
    return sorted(values, key=lambda item: item.encode("utf-8"))


def _side(record):
    raw = canonicalize(record)
    return {
        "record_id": record["record_id"],
        "record_sha256": sha(raw),
        "condition_id": record["condition_id"],
        "paper_id": record["paper_id"],
        "source_association_id": record["source_association"]["association_id"],
        "setting_key": record["setting_key"],
    }


def _pointers(key):
    if key == "source_association":
        pointer = "/source_association/association_id"
        return pointer, pointer
    pointer = "/conditions/" + key
    return pointer, pointer


def _evidence(kind, key, outcome, metric_name=None):
    if kind == "condition_unknown" or outcome in UNKNOWN_OUTCOMES:
        sides = []
        if outcome in {"unknown_left", "unknown_both"}:
            sides.append("left")
        if outcome in {"unknown_right", "unknown_both"}:
            sides.append("right")
        if not sides:
            sides = ["left", "right"]
        return [
            "supply /conditions/" + key + " for the " + side + " record within its search_scope"
            for side in sides
        ]
    if kind == "no_shared_metric":
        return ["record at least one shared metric name with unit and definition_source on both records"]
    if kind in {"unit_mismatch", "metric_definition_differs"}:
        name = metric_name or "metric"
        return ["re-report metric " + name + " in one unit with its definition_source on both records"]
    return ["re-evaluate under a matching " + key + " or record a setting with an equal " + key]


def _rule_row(name, critical, outcome, key, kind, left, right, detail, metric_name=None):
    left_pointer, right_pointer = _pointers(key)
    left_value = None
    right_value = None
    if key != "source_association" and _status(left, key) in KNOWN:
        left_value = _value(left, key)
    if key != "source_association" and _status(right, key) in KNOWN:
        right_value = _value(right, key)
    return {
        "rule": name,
        "critical": critical,
        "outcome": outcome,
        "left_pointer": left_pointer,
        "right_pointer": right_pointer,
        "detail": detail,
        "_kind": kind,
        "_key": key,
        "_metric_name": metric_name,
        "_left_summary": _summary(left_value) if key != "source_association" else left["source_association"]["association_id"],
        "_right_summary": _summary(right_value) if key != "source_association" else right["source_association"]["association_id"],
    }


def _eval_dataset(left, right):
    outcome, kind = _status_outcome(left, right, "dataset_split")
    if outcome is not None:
        return outcome, kind, "dataset_split statuses compared"
    lv = _value(left, "dataset_split")
    rv = _value(right, "dataset_split")
    same = lv["dataset"] == rv["dataset"] and lv["split"] == rv["split"] and lv["subset"] == rv["subset"]
    if same:
        return "satisfied", None, "dataset, split, and subset match"
    return "violated", "condition_differs", "dataset, split, or subset differs"


def _shared_metrics(left, right):
    lmap = _metric_map(left)
    rmap = _metric_map(right)
    if lmap is None or rmap is None:
        return [], lmap, rmap
    names = _byte_sort(set(lmap) & set(rmap))
    return names, lmap, rmap


def _eval_metric_definition(left, right, shared, lmap, rmap):
    outcome, kind = _status_outcome(left, right, "metrics")
    if outcome is not None:
        return outcome, kind, None, "metrics statuses compared"
    if not shared:
        return "violated", "no_shared_metric", None, "no shared metric name"
    left_unknown = False
    right_unknown = False
    mismatch = None
    for name in shared:
        lm = lmap[name]
        rm = rmap[name]
        if lm["higher_is_better"] is not None and rm["higher_is_better"] is not None:
            if lm["higher_is_better"] != rm["higher_is_better"]:
                mismatch = name
                break
        if lm["definition_source"] is None or lm["higher_is_better"] is None:
            left_unknown = True
        if rm["definition_source"] is None or rm["higher_is_better"] is None:
            right_unknown = True
    if mismatch is not None:
        return "violated", "metric_definition_differs", mismatch, "shared metric higher_is_better differs"
    if left_unknown or right_unknown:
        return _unknown_outcome(left_unknown, right_unknown), "condition_unknown", None, "metric definition is incomplete"
    return "satisfied", None, None, "shared metrics have matching definitions"


def _eval_metric_unit(left, right, shared, lmap, rmap):
    outcome, kind = _status_outcome(left, right, "metrics")
    if outcome is not None:
        if outcome == "violated":
            return outcome, kind, None, "metrics statuses compared"
        if kind == "condition_unknown":
            return "not_applicable" if False else (outcome, kind, None, "metrics statuses compared")
        return outcome, kind, None, "metrics statuses compared"
    if not shared:
        return "not_applicable", None, None, "no shared metric name"
    for name in shared:
        if lmap[name]["unit"] != rmap[name]["unit"]:
            return "violated", "unit_mismatch", name, "shared metric unit differs"
    return "satisfied", None, None, "shared metric units match"


def _eval_resolution(left, right):
    outcome, kind = _status_outcome(left, right, "resolution")
    if outcome is not None:
        return outcome, kind, "resolution statuses compared"
    lv = _value(left, "resolution")
    rv = _value(right, "resolution")
    if lv["width"] == rv["width"] and lv["height"] == rv["height"]:
        return "satisfied", None, "width and height match"
    return "violated", "condition_differs", "width or height differs"


def _eval_frames(left, right):
    outcome, kind = _status_outcome(left, right, "frames")
    if outcome is not None:
        return outcome, kind, "frames statuses compared"
    if _value(left, "frames")["count"] == _value(right, "frames")["count"]:
        return "satisfied", None, "frame counts match"
    return "violated", "condition_differs", "frame counts differ"


def _eval_protocol(left, right):
    outcome, kind = _status_outcome(left, right, "evaluation_setup")
    if outcome is not None:
        return outcome, kind, "evaluation_setup statuses compared"
    lv = _value(left, "evaluation_setup")
    rv = _value(right, "evaluation_setup")
    if lv["protocol"] != rv["protocol"]:
        return "violated", "condition_differs", "evaluation protocols differ"
    for field in ("num_samples", "evaluator"):
        if lv[field] is not None and rv[field] is not None and lv[field] != rv[field]:
            return "violated", "condition_differs", field + " differs"
    return "satisfied", None, "evaluation protocols match"


def _eval_checkpoint(left, right):
    ls = _status(left, "model_checkpoint")
    rs = _status(right, "model_checkpoint")
    left_unknown = ls not in KNOWN or (
        _value(left, "model_checkpoint")["checkpoint_ref"] is None
        and _value(left, "model_checkpoint")["checkpoint_sha256"] is None
    )
    right_unknown = rs not in KNOWN or (
        _value(right, "model_checkpoint")["checkpoint_ref"] is None
        and _value(right, "model_checkpoint")["checkpoint_sha256"] is None
    )
    if ls == "unknown":
        left_unknown = True
    if rs == "unknown":
        right_unknown = True
    if ls == "not_applicable":
        left_unknown = True
    if rs == "not_applicable":
        right_unknown = True
    if left_unknown or right_unknown:
        return _unknown_outcome(left_unknown, right_unknown), "condition_unknown", "checkpoint is not identified"
    return "satisfied", None, "both checkpoints are identified"


def _eval_parameter(left, right):
    ls = _status(left, "parameter_count")
    rs = _status(right, "parameter_count")
    left_unknown = ls not in KNOWN or _value(left, "parameter_count")["basis"] == "unspecified"
    right_unknown = rs not in KNOWN or _value(right, "parameter_count")["basis"] == "unspecified"
    if left_unknown or right_unknown:
        return _unknown_outcome(left_unknown, right_unknown), "condition_unknown", "parameter basis is not declared"
    return "satisfied", None, "parameter bases are declared"


def _eval_steps(left, right):
    ls = _status(left, "inference_steps")
    rs = _status(right, "inference_steps")
    left_unknown = ls not in KNOWN
    right_unknown = rs not in KNOWN
    if left_unknown or right_unknown:
        return _unknown_outcome(left_unknown, right_unknown), "condition_unknown", "inference steps are not declared"
    return "satisfied", None, "inference steps are declared"


def _eval_guidance(left, right):
    ls = _status(left, "sampling_guidance")
    rs = _status(right, "sampling_guidance")
    left_unknown = ls not in KNOWN or _value(left, "sampling_guidance")["guidance_scale"] is None
    right_unknown = rs not in KNOWN or _value(right, "sampling_guidance")["guidance_scale"] is None
    if left_unknown or right_unknown:
        return _unknown_outcome(left_unknown, right_unknown), "condition_unknown", "guidance scale is not declared"
    return "satisfied", None, "guidance scales are declared"


def _eval_source_version(left, right, same_paper):
    if not same_paper:
        return "not_applicable", None, "records are from different papers"
    if left["source_association"]["association_id"] == right["source_association"]["association_id"]:
        return "satisfied", None, "records share a source-version association"
    return "violated", "condition_differs", "records use different source versions of the same paper"


def _same_checkpoint(left, right):
    if _status(left, "model_checkpoint") not in KNOWN or _status(right, "model_checkpoint") not in KNOWN:
        return False
    lv = _value(left, "model_checkpoint")
    rv = _value(right, "model_checkpoint")
    if lv["name"] != rv["name"]:
        return False
    sha_ok = (
        lv["checkpoint_sha256"] is not None
        and rv["checkpoint_sha256"] is not None
        and lv["checkpoint_sha256"] == rv["checkpoint_sha256"]
    )
    ref_ok = (
        lv["checkpoint_ref"] is not None
        and rv["checkpoint_ref"] is not None
        and lv["checkpoint_ref"] == rv["checkpoint_ref"]
    )
    return sha_ok or ref_ok


def _claim_ids(record):
    return _byte_sort([item["claim_id"] for item in record["claim_refs"]])


def _condition_differences(left, right, shared, lmap, rmap):
    rows = []
    for key in CONDITION_KEYS:
        if _status(left, key) not in KNOWN or _status(right, key) not in KNOWN:
            continue
        lv = _value(left, key)
        rv = _value(right, key)
        if key != "metrics":
            if not _equal_jcs(lv, rv):
                rows.append(
                    {
                        "field_pointer": "/conditions/" + key,
                        "left_summary": _summary(lv),
                        "right_summary": _summary(rv),
                    }
                )
            continue
        if not _equal_jcs(lv, rv):
            rows.append(
                {
                    "field_pointer": "/conditions/metrics",
                    "left_summary": _summary(lv),
                    "right_summary": _summary(rv),
                }
            )
        if lmap is not None and rmap is not None:
            if set(lmap) != set(rmap):
                rows.append(
                    {
                        "field_pointer": "/conditions/metrics",
                        "left_summary": _summary(sorted(lmap)),
                        "right_summary": _summary(sorted(rmap)),
                    }
                )
            for name in shared:
                lm = lmap[name]
                rm = rmap[name]
                if lm["unit"] != rm["unit"] or lm["higher_is_better"] != rm["higher_is_better"]:
                    rows.append(
                        {
                            "field_pointer": "/conditions/metrics/" + name,
                            "left_summary": _summary({"unit": lm["unit"], "higher_is_better": lm["higher_is_better"]}),
                            "right_summary": _summary({"unit": rm["unit"], "higher_is_better": rm["higher_is_better"]}),
                        }
                    )
    return rows


def compare_experiment_records(left, right):
    left = _load_record(left, "/left")
    right = _load_record(right, "/right")
    if left["record_id"] == right["record_id"]:
        _fail("same_record", "/left/record_id")
    same_paper = left["paper_id"] == right["paper_id"]
    shared, lmap, rmap = _shared_metrics(left, right)
    rules = []

    outcome, kind, detail = _eval_dataset(left, right)
    rules.append(_rule_row("same_benchmark_and_split", True, outcome, "dataset_split", kind, left, right, detail))

    outcome, kind, metric_name, detail = _eval_metric_definition(left, right, shared, lmap, rmap)
    rules.append(
        _rule_row("same_metric_definition", True, outcome, "metrics", kind, left, right, detail, metric_name)
    )

    outcome, kind, metric_name, detail = _eval_metric_unit(left, right, shared, lmap, rmap)
    rules.append(_rule_row("same_metric_unit", True, outcome, "metrics", kind, left, right, detail, metric_name))

    outcome, kind, detail = _eval_resolution(left, right)
    rules.append(_rule_row("same_resolution", True, outcome, "resolution", kind, left, right, detail))

    outcome, kind, detail = _eval_frames(left, right)
    rules.append(_rule_row("same_frame_count", True, outcome, "frames", kind, left, right, detail))

    outcome, kind, detail = _eval_protocol(left, right)
    rules.append(_rule_row("same_evaluation_protocol", True, outcome, "evaluation_setup", kind, left, right, detail))

    outcome, kind, detail = _eval_checkpoint(left, right)
    rules.append(_rule_row("checkpoint_identified", False, outcome, "model_checkpoint", kind, left, right, detail))

    outcome, kind, detail = _eval_parameter(left, right)
    rules.append(_rule_row("parameter_basis_declared", False, outcome, "parameter_count", kind, left, right, detail))

    outcome, kind, detail = _eval_steps(left, right)
    rules.append(_rule_row("inference_steps_declared", False, outcome, "inference_steps", kind, left, right, detail))

    outcome, kind, detail = _eval_guidance(left, right)
    rules.append(_rule_row("guidance_declared", False, outcome, "sampling_guidance", kind, left, right, detail))

    outcome, kind, detail = _eval_source_version(left, right, same_paper)
    rules.append(
        _rule_row("same_source_version_within_paper", False, outcome, "source_association", kind, left, right, detail)
    )

    critical_violated = any(row["critical"] and row["outcome"] == "violated" for row in rules)
    critical_unknown = any(row["critical"] and row["outcome"] in UNKNOWN_OUTCOMES for row in rules)
    other_open = any(
        (not row["critical"]) and row["outcome"] in UNKNOWN_OUTCOMES | {"violated"} for row in rules
    )
    if critical_violated:
        verdict = "incomparable"
        ranking = "refused_incomparable"
    elif critical_unknown:
        verdict = "insufficient_conditions"
        ranking = "refused_insufficient_conditions"
    elif other_open:
        verdict = "comparable_with_caveats"
        ranking = "not_ranked"
    else:
        verdict = "comparable"
        ranking = "not_ranked"

    reasons = []
    for row in rules:
        if not row["critical"]:
            continue
        if row["outcome"] != "violated" and row["outcome"] not in UNKNOWN_OUTCOMES:
            continue
        kind = "condition_unknown" if row["outcome"] in UNKNOWN_OUTCOMES else row["_kind"]
        reasons.append(
            {
                "rule": row["rule"],
                "kind": kind,
                "field_pointer": row["left_pointer"],
                "left_summary": row["_left_summary"],
                "right_summary": row["_right_summary"],
                "evidence_needed": _evidence(kind, row["_key"], row["outcome"], row["_metric_name"]),
            }
        )

    candidates = []
    if verdict == "comparable" and _same_checkpoint(left, right) and lmap is not None and rmap is not None:
        for name in shared:
            lm = lmap[name]
            rm = rmap[name]
            if lm["value"] != rm["value"]:
                candidates.append(
                    {
                        "metric_name": name,
                        "unit": lm["unit"],
                        "left_value": lm["value"],
                        "right_value": rm["value"],
                        "higher_is_better": lm["higher_is_better"],
                        "comparability_verdict": "comparable",
                        "left_claim_ids": _claim_ids(left),
                        "right_claim_ids": _claim_ids(right),
                        "detail": (
                            "same identified checkpoint reports different "
                            + name
                            + " under comparable conditions; verify both sources before treating this as a contradiction"
                        ),
                    }
                )

    public_rules = []
    for row in rules:
        public_rules.append(
            {
                "rule": row["rule"],
                "critical": row["critical"],
                "outcome": row["outcome"],
                "left_pointer": row["left_pointer"],
                "right_pointer": row["right_pointer"],
                "detail": row["detail"],
            }
        )

    result = {
        "schema": COMPARABILITY_SCHEMA,
        "left": _side(left),
        "right": _side(right),
        "same_paper": same_paper,
        "rules": public_rules,
        "verdict": verdict,
        "ranking": ranking,
        "incomparable_reasons": reasons,
        "condition_differences": _condition_differences(left, right, shared, lmap, rmap),
        "shared_metrics": shared,
        "contradiction_candidates": candidates,
        "scientific_conclusion_contradiction": False,
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "typed_fact_promotion": "none",
    }
    try:
        raw = canonicalize(result)
        sealed = json.loads(raw.decode("utf-8"))
        validate_document(sealed, COMPARABILITY_SCHEMA)
    except (CanonicalJsonError, ContractError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ExperimentComparabilityError(
            "EXPERIMENT_COMPARE_INVALID",
            MESSAGES["EXPERIMENT_COMPARE_INVALID"],
            {"instance_pointer": "", "next_action": "repair_input", "reason": "schema"},
        ) from exc
    return sealed
