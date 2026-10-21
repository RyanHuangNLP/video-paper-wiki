from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.contract.paths import VALID, load_json
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.experiment_store import (
    condition_id_from_record,
    content_sha256_from_record,
    record_id_from_record,
)

TITLES = (
    "video-paper-wiki.experiment-condition-record.v1",
    "video-paper-wiki.experiment-heads.v1",
    "video-paper-wiki.experiment-comparability.v1",
    "video-paper-wiki.experiment-comparison-matrix.v1",
)
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


def _fixture(title: str) -> dict:
    return load_json(VALID / f"{title}.json")


def _first_nested_object(document: dict) -> dict | None:
    for value in document.values():
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    return item
    return None


def _reject(document: dict, title: str) -> None:
    with pytest.raises(ContractError) as exc:
        validate_document(document, expected_schema=title)
    assert exc.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("title", TITLES)
def test_valid_fixtures_and_closed_objects(title: str) -> None:
    document = _fixture(title)
    validate_document(document, expected_schema=title)
    top = copy.deepcopy(document)
    top["unexpected_field"] = True
    _reject(top, title)
    nested_doc = copy.deepcopy(document)
    nested = _first_nested_object(nested_doc)
    assert nested is not None
    nested["unexpected_field"] = True
    _reject(nested_doc, title)


def test_record_identities_and_condition_coverage() -> None:
    record = _fixture("video-paper-wiki.experiment-condition-record.v1")
    assert record["record_id"] == record_id_from_record(record)
    assert record["condition_id"] == condition_id_from_record(record)
    assert record["content_sha256"] == content_sha256_from_record(record)
    statuses = {item["status"] for item in record["conditions"].values()}
    assert statuses == {"reported", "derived", "unknown", "not_applicable"}
    kinds = set()
    for cond in record["conditions"].values():
        for source in cond["sources"]:
            kinds.add(source["kind"])
        if cond["status"] in {"reported", "derived"} and cond["value"] and isinstance(cond["value"], list):
            for metric in cond["value"]:
                source = metric.get("definition_source")
                if source:
                    kinds.add(source["kind"])
    assert kinds == {"paper_direct", "project_page", "repository_text"}


def test_unknown_and_reported_shapes_rejected() -> None:
    title = "video-paper-wiki.experiment-condition-record.v1"
    record = _fixture(title)
    bad = copy.deepcopy(record)
    bad["conditions"]["resolution"]["value"] = {"width": 512, "height": 512}
    _reject(bad, title)
    bad = copy.deepcopy(record)
    bad["conditions"]["resolution"]["sources"] = [record["conditions"]["model_checkpoint"]["sources"][0]]
    _reject(bad, title)
    bad = copy.deepcopy(record)
    bad["conditions"]["resolution"]["search_scope"] = None
    _reject(bad, title)
    bad = copy.deepcopy(record)
    bad["conditions"]["model_checkpoint"]["sources"] = []
    _reject(bad, title)
    bad = copy.deepcopy(record)
    bad["conditions"]["model_checkpoint"]["search_scope"] = {
        "artifact_paths": ["wiki/papers/paper.md"],
        "search_terms": ["checkpoint"],
    }
    _reject(bad, title)


def test_search_scope_artifact_path_branches() -> None:
    title = "video-paper-wiki.experiment-condition-record.v1"
    record = _fixture(title)
    captured = ".raw/captured/" + "a" * 64 + ".md"
    derived = ".raw/derived/" + "a" * 64 + "/document.json"
    portable_paths = ("wiki/papers/paper.md", "wiki/code/page.md", "a")
    for path in (captured, derived, *portable_paths):
        good = copy.deepcopy(record)
        good["conditions"]["resolution"]["search_scope"]["artifact_paths"] = [path]
        validate_document(good, title)
    rejected = (
        "/tmp/x.md",
        "wiki/papers/../code/x.md",
        "wiki\\papers\\paper.md",
        "wiki/papers/paper.md\n",
        "wiki/papers/paper.md\r",
        "wiki/papers/paper.md\r\n",
        "wiki/papers/paper.md\x00",
        "wiki/papers/paper.md\x01",
        "wiki/papers/paper.md\x7f",
        "wiki/code/page.md\n",
        "a\n",
        "https://example.invalid/x",
        ".work/batch/x.json",
        ".git/config",
        ".raw/tmp/x.md",
        ".raw/captured/" + "a" * 64 + ".md\n",
        ".raw/captured/" + "a" * 64 + ".md\r",
        ".raw/derived/" + "a" * 64 + "/document.json\n",
        ".raw/derived/" + "a" * 64 + "/document.json\r",
        ".raw/captured",
        ".raw/**/x.md",
    )
    for path in rejected:
        bad = copy.deepcopy(record)
        bad["conditions"]["resolution"]["search_scope"]["artifact_paths"] = [path]
        _reject(bad, title)


def test_comparability_rule_order_and_consts() -> None:
    title = "video-paper-wiki.experiment-comparability.v1"
    document = _fixture(title)
    assert [(row["rule"], row["critical"]) for row in document["rules"]] == list(RULE_ORDER)
    bad = copy.deepcopy(document)
    bad["rules"][0]["critical"] = False
    _reject(bad, title)
    swapped = copy.deepcopy(document)
    swapped["rules"][0], swapped["rules"][1] = swapped["rules"][1], swapped["rules"][0]
    _reject(swapped, title)
    ranked = copy.deepcopy(document)
    ranked["ranking"] = "ranked"
    _reject(ranked, title)
    fourth = copy.deepcopy(document)
    fourth["ranking"] = "winner"
    _reject(fourth, title)
    caveats = copy.deepcopy(document)
    caveats["contradiction_candidates"][0]["comparability_verdict"] = "comparable_with_caveats"
    _reject(caveats, title)
    contradiction = copy.deepcopy(document)
    contradiction["scientific_conclusion_contradiction"] = True
    _reject(contradiction, title)


def test_matrix_consts_and_heads_keys() -> None:
    matrix_title = "video-paper-wiki.experiment-comparison-matrix.v1"
    matrix = _fixture(matrix_title)
    for field, value in (("ranking", "ranked"), ("write_kind", "direct_store_write"), ("audit_coverage", "wired")):
        bad = copy.deepcopy(matrix)
        bad[field] = value
        _reject(bad, matrix_title)
    heads_title = "video-paper-wiki.experiment-heads.v1"
    heads = _fixture(heads_title)
    bad_heads = copy.deepcopy(heads)
    entry = next(iter(bad_heads["heads"].values()))
    bad_heads["heads"] = {"not-an-exc-id": entry}
    _reject(bad_heads, heads_title)
