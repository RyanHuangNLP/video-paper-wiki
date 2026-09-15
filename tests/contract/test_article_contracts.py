from __future__ import annotations

import copy

import pytest

from tests.contract.paths import VALID, load_json
from video_paper_wiki.contracts import ContractError, validate_document

TITLES = (
    "video-paper-wiki.article-context.v1",
    "video-paper-wiki.article-revision-record.v1",
    "video-paper-wiki.article-heads.v1",
    "video-paper-wiki.article-check.v1",
)
CONTEXT = "video-paper-wiki.article-context.v1"
RECORD = "video-paper-wiki.article-revision-record.v1"
HEADS = "video-paper-wiki.article-heads.v1"
CHECK = "video-paper-wiki.article-check.v1"


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


def test_record_fixture_refusals() -> None:
    document = _fixture(RECORD)
    validate_document(document, expected_schema=RECORD)
    bad_role = copy.deepcopy(document)
    bad_role["sections"][0]["role"] = "summary"
    _reject(bad_role, RECORD)
    for sid in ("s0", "s100"):
        bad = copy.deepcopy(document)
        bad["sections"][0]["section_id"] = sid
        _reject(bad, RECORD)
    if document["bibliography"]:
        bad_kind = copy.deepcopy(document)
        bad_kind["bibliography"][0]["kind"] = "chunk"
        _reject(bad_kind, RECORD)
        missing = copy.deepcopy(document)
        binding = missing["bibliography"][0]["binding"]
        key = next(iter(binding))
        del binding[key]
        _reject(missing, RECORD)
        extra = copy.deepcopy(document)
        extra["bibliography"][0]["binding"]["unexpected_field"] = True
        _reject(extra, RECORD)
    bad_kind = copy.deepcopy(document)
    bad_kind["kind"] = "draft"
    _reject(bad_kind, RECORD)
    for key, value in (
        ("publication", "published"),
        ("ranking", "ranked"),
        ("canonical_official", True),
        ("scientific_conclusion_contradiction", True),
    ):
        bad = copy.deepcopy(document)
        bad[key] = value
        _reject(bad, RECORD)
    if document["comparison_table"]["rows"]:
        bad_cells = copy.deepcopy(document)
        cells = bad_cells["comparison_table"]["rows"][0]["cells"]
        del cells[next(iter(cells))]
        _reject(bad_cells, RECORD)


def test_context_fixture_refusals() -> None:
    document = _fixture(CONTEXT)
    validate_document(document, expected_schema=CONTEXT)
    bad_alg = copy.deepcopy(document)
    bad_alg["relevance"]["fusion"]["algorithm"] = "rrf-v2"
    _reject(bad_alg, CONTEXT)
    bad_k = copy.deepcopy(document)
    bad_k["relevance"]["fusion"]["rank_constant"] = 61
    _reject(bad_k, CONTEXT)
    bad_third = copy.deepcopy(document)
    bad_third["relevance"]["third_route"] = "supplied"
    _reject(bad_third, CONTEXT)
    swapped = copy.deepcopy(document)
    swapped["relevance"]["routes"] = list(reversed(swapped["relevance"]["routes"]))
    _reject(swapped, CONTEXT)
    bad_budget = copy.deepcopy(document)
    bad_budget["budget"]["excerpt_bytes_budget"] = 8192
    _reject(bad_budget, CONTEXT)
    bad_roles = copy.deepcopy(document)
    bad_roles["required_roles"] = list(document["required_roles"])[:-1]
    _reject(bad_roles, CONTEXT)
    if document["evidence"]:
        bad_ex = copy.deepcopy(document)
        bad_ex["evidence"][0]["excerpt_status"] = "quoted"
        _reject(bad_ex, CONTEXT)


def test_check_and_heads_fixture_refusals() -> None:
    document = _fixture(CHECK)
    validate_document(document, expected_schema=CHECK)
    if document["items"]:
        bad_status = copy.deepcopy(document)
        bad_status["items"][0]["status"] = "ok"
        _reject(bad_status, CHECK)
    bad_check = copy.deepcopy(document)
    bad_check["check_status"] = "passed"
    _reject(bad_check, CHECK)
    applied = copy.deepcopy(document)
    applied["applied"] = True
    _reject(applied, CHECK)
    nxt = copy.deepcopy(document)
    nxt["next_action"] = "publish"
    _reject(nxt, CHECK)
    heads = _fixture(HEADS)
    validate_document(heads, expected_schema=HEADS)
    bad_heads = copy.deepcopy(heads)
    bad_heads["heads"]["exc-" + "0" * 20] = {
        "revision_id": "arv-" + "0" * 20,
        "record_sha256": "a" * 64,
    }
    _reject(bad_heads, HEADS)
