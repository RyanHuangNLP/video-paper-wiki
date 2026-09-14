from __future__ import annotations

import copy
import json

import pytest

from video_paper_wiki.contracts import validate_document
from video_paper_wiki.experiment_comparability import (
    ExperimentComparabilityError,
    compare_experiment_records,
)
from video_paper_wiki.experiment_store import (
    condition_id_from_record,
    content_sha256_from_record,
    record_id_from_record,
)
from video_paper_wiki.jcs import canonicalize

H = "a" * 64
COMMIT = "b" * 40
PAPER = "sha256:" + "a" * 64
ASSOC = "sva-" + "c" * 64
CLAIM = "clm-" + "d" * 20
EVENT = "ase-" + "e" * 20
FORBIDDEN_KEYS = {"ranked", "better", "winner", "score_delta"}
RULE_ORDER = (
    ("same_benchmark_and_split", True),
    ("same_metric_definition", True),
    ("same_metric_unit", True),
    ("same_resolution", True),
    ("same_frame_count", True),
    ("same_evaluation_protocol", True),
    ("checkpoint_identified", False),
    ("parameter_basis_declared", False),
    ("inference_steps_declared", False),
    ("guidance_declared", False),
    ("same_source_version_within_paper", False),
)

PAPER_DIRECT = {
    "kind": "paper_direct",
    "locator": {
        "kind": "pdf",
        "source_id": "src-fixture-1",
        "page": 1,
        "ref": "#/texts/1",
        "artifact_path": ".raw/derived/" + "a" * 64 + "/document.json",
        "artifact_sha256": H,
        "text_sha256": H,
        "context": "synthetic experiment table",
    },
    "quote_sha256": H,
}


def _reported(value):
    return {
        "status": "reported",
        "value": value,
        "basis_note": None,
        "sources": [PAPER_DIRECT],
        "search_scope": None,
    }


def _unknown():
    return {
        "status": "unknown",
        "value": None,
        "basis_note": None,
        "sources": [],
        "search_scope": {
            "artifact_paths": ["wiki/papers/paper.md"],
            "search_terms": ["missing"],
        },
    }


def _n_a():
    return {
        "status": "not_applicable",
        "value": None,
        "basis_note": None,
        "sources": [],
        "search_scope": None,
    }


def _metric(name="fvd", unit="fvd", value=100, hib=False, defined=True):
    return {
        "name": name,
        "unit": unit,
        "value": value,
        "higher_is_better": hib,
        "definition_source": PAPER_DIRECT if defined else None,
    }


def _seal(overrides=None, *, recorded_by="left-reviewer"):
    payload = {
        "schema": "video-paper-wiki.experiment-condition-record.v1",
        "previous_record_id": None,
        "recorded_by": recorded_by,
        "recorded_at": "2026-09-14T00:00:00Z",
        "paper_id": PAPER,
        "source_association": {"association_id": ASSOC, "sha256": H},
        "source_digest": {"path": ".raw/captured/" + "a" * 64 + ".md", "sha256": H, "size_bytes": 64},
        "code_binding": None,
        "setting_key": "table2-row3-vbench-512",
        "conditions": {
            "model_checkpoint": _reported(
                {"name": "demo-a", "checkpoint_ref": "ckpt-a", "checkpoint_sha256": "1" * 64}
            ),
            "parameter_count": _reported({"count": 1000, "basis": "total"}),
            "dataset_split": _reported({"dataset": "vbench", "split": "test", "subset": None}),
            "metrics": _reported([_metric()]),
            "resolution": _reported({"width": 512, "height": 512}),
            "frames": _reported({"count": 16, "fps": 8}),
            "inference_steps": _reported({"steps": 50, "scheduler": "ddim"}),
            "sampling_guidance": _reported({"guidance_scale": 7, "sampler": "ddim", "seed": 1}),
            "evaluation_setup": _reported(
                {"protocol": "vbench-official", "num_samples": 100, "evaluator": "vbench"}
            ),
        },
        "claim_refs": [
            {
                "claim_id": CLAIM,
                "claim_kind": "empirical_result",
                "claim_text": "The method reports improved FVD on the benchmark.",
                "evidence_fingerprint": H,
                "assessment_head": {
                    "event_id": EVENT,
                    "event_sha256": H,
                    "evidence_profile": "legacy-v1",
                },
            }
        ],
        "publication": "unpublished",
        "typed_fact_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
    }
    if overrides:
        payload = copy.deepcopy(payload)
        for key, value in overrides.items():
            if key == "conditions":
                payload["conditions"].update(copy.deepcopy(value))
            else:
                payload[key] = copy.deepcopy(value)
    payload["condition_id"] = condition_id_from_record(payload)
    payload["content_sha256"] = content_sha256_from_record(payload)
    record = {"record_id": record_id_from_record(payload), **payload}
    raw = canonicalize(record)
    return json.loads(raw.decode("utf-8"))


def _compare(left, right):
    result = compare_experiment_records(left, right)
    validate_document(result, "video-paper-wiki.experiment-comparability.v1")
    assert [(row["rule"], row["critical"]) for row in result["rules"]] == list(RULE_ORDER)
    assert FORBIDDEN_KEYS.isdisjoint(result)
    assert result["scientific_conclusion_contradiction"] is False
    return result


def _rule(result, name):
    return next(row for row in result["rules"] if row["rule"] == name)


def test_comparable_different_checkpoint_is_not_contradiction():
    left = _seal(recorded_by="left")
    right = _seal(
        {
            "conditions": {
                "model_checkpoint": _reported(
                    {"name": "demo-b", "checkpoint_ref": "ckpt-b", "checkpoint_sha256": "2" * 64}
                )
            }
        },
        recorded_by="right",
    )
    result = _compare(left, right)
    assert result["verdict"] == "comparable"
    assert result["ranking"] == "not_ranked"
    assert result["incomparable_reasons"] == []
    assert result["contradiction_candidates"] == []
    assert any(row["field_pointer"] == "/conditions/model_checkpoint" for row in result["condition_differences"])
    again = compare_experiment_records(left, right)
    assert canonicalize(again) == canonicalize(result)


def test_same_checkpoint_value_delta_is_candidate_not_contradiction():
    left = _seal(recorded_by="left")
    right = _seal(
        {"conditions": {"metrics": _reported([_metric(value=140)])}},
        recorded_by="right",
    )
    result = _compare(left, right)
    assert result["verdict"] == "comparable"
    assert len(result["contradiction_candidates"]) == 1
    row = result["contradiction_candidates"][0]
    assert row["comparability_verdict"] == "comparable"
    assert row["left_claim_ids"] == [CLAIM]
    assert result["scientific_conclusion_contradiction"] is False


def test_resolution_mismatch_is_incomparable():
    left = _seal(recorded_by="left")
    right = _seal(
        {"conditions": {"resolution": _reported({"width": 256, "height": 256})}},
        recorded_by="right",
    )
    result = _compare(left, right)
    assert result["verdict"] == "incomparable"
    assert result["ranking"] == "refused_incomparable"
    assert len(result["incomparable_reasons"]) == 1
    assert result["incomparable_reasons"][0]["rule"] == "same_resolution"
    assert result["incomparable_reasons"][0]["kind"] == "condition_differs"
    assert result["contradiction_candidates"] == []


def test_unknown_frames_is_insufficient_and_swaps():
    left = _seal(recorded_by="left")
    right = _seal({"conditions": {"frames": _unknown()}}, recorded_by="right")
    result = _compare(left, right)
    assert result["verdict"] == "insufficient_conditions"
    assert result["ranking"] == "refused_insufficient_conditions"
    assert _rule(result, "same_frame_count")["outcome"] == "unknown_right"
    assert any("/conditions/frames" in item for item in result["incomparable_reasons"][0]["evidence_needed"])
    swapped = _compare(right, left)
    assert _rule(swapped, "same_frame_count")["outcome"] == "unknown_left"
    both = _compare(
        _seal({"conditions": {"frames": _unknown()}}, recorded_by="left-u"),
        _seal({"conditions": {"frames": _unknown()}}, recorded_by="right-u"),
    )
    assert _rule(both, "same_frame_count")["outcome"] == "unknown_both"


def test_unit_mismatch_and_no_shared_metric():
    left = _seal(recorded_by="left")
    unit = _compare(
        left,
        _seal({"conditions": {"metrics": _reported([_metric(unit="score")])}}, recorded_by="right-unit"),
    )
    assert unit["verdict"] == "incomparable"
    assert unit["incomparable_reasons"][0]["kind"] == "unit_mismatch"
    none = _compare(
        left,
        _seal({"conditions": {"metrics": _reported([_metric(name="fid", unit="fid")])}}, recorded_by="right-name"),
    )
    assert none["verdict"] == "incomparable"
    assert none["incomparable_reasons"][0]["kind"] == "no_shared_metric"
    assert _rule(none, "same_metric_unit")["outcome"] == "not_applicable"


def test_missing_definition_source_is_insufficient():
    left = _seal(recorded_by="left")
    right = _seal(
        {"conditions": {"metrics": _reported([_metric(defined=False)])}},
        recorded_by="right",
    )
    result = _compare(left, right)
    assert result["verdict"] == "insufficient_conditions"
    assert _rule(result, "same_metric_definition")["outcome"] in {"unknown_right", "unknown_left", "unknown_both"}


def test_guidance_caveat_does_not_emit_candidates():
    left = _seal(recorded_by="left")
    right = _seal(
        {
            "conditions": {
                "sampling_guidance": _reported({"guidance_scale": None, "sampler": "ddim", "seed": 1}),
                "metrics": _reported([_metric(value=140)]),
            }
        },
        recorded_by="right",
    )
    result = _compare(left, right)
    assert result["verdict"] == "comparable_with_caveats"
    assert result["ranking"] == "not_ranked"
    assert result["contradiction_candidates"] == []


def test_source_version_and_paper_split():
    other_assoc = "sva-" + "d" * 64
    same_paper = _compare(
        _seal(recorded_by="left"),
        _seal(
            {"source_association": {"association_id": other_assoc, "sha256": H}},
            recorded_by="right",
        ),
    )
    assert _rule(same_paper, "same_source_version_within_paper")["outcome"] == "violated"
    assert same_paper["verdict"] == "comparable_with_caveats"
    other_paper = _compare(
        _seal(recorded_by="left"),
        _seal({"paper_id": "sha256:" + "b" * 64}, recorded_by="right"),
    )
    assert other_paper["same_paper"] is False
    assert _rule(other_paper, "same_source_version_within_paper")["outcome"] == "not_applicable"


def test_not_applicable_dataset_split():
    left = _seal(recorded_by="left")
    one = _compare(left, _seal({"conditions": {"dataset_split": _n_a()}}, recorded_by="right"))
    assert _rule(one, "same_benchmark_and_split")["outcome"] == "violated"
    both = _compare(
        _seal({"conditions": {"dataset_split": _n_a()}}, recorded_by="left-n"),
        _seal({"conditions": {"dataset_split": _n_a()}}, recorded_by="right-n"),
    )
    assert _rule(both, "same_benchmark_and_split")["outcome"] == "not_applicable"
    assert both["verdict"] in {"comparable", "comparable_with_caveats"}


def test_same_record_and_schema_failures():
    left = _seal(recorded_by="left")
    with pytest.raises(ExperimentComparabilityError) as exc:
        compare_experiment_records(left, left)
    assert exc.value.code == "EXPERIMENT_COMPARE_INVALID"
    assert exc.value.details["reason"] == "same_record"
    with pytest.raises(ExperimentComparabilityError) as missing:
        compare_experiment_records({"schema": "video-paper-wiki.experiment-condition-record.v1"}, left)
    assert missing.value.details["reason"] == "schema"
    assert missing.value.details["next_action"] == "repair_input"
