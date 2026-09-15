from __future__ import annotations

import copy

import pytest

from tests.contract.paths import VALID, load_json
from video_paper_wiki.contracts import ContractError, validate_document

TITLES = (
    "video-paper-wiki.domain-graph-projection.v1",
    "video-paper-wiki.domain-graph-query.v1",
)
PROJECTION = "video-paper-wiki.domain-graph-projection.v1"
QUERY = "video-paper-wiki.domain-graph-query.v1"


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


def test_projection_kind_endpoints_and_consts() -> None:
    document = _fixture(PROJECTION)
    validate_document(document, expected_schema=PROJECTION)
    bad_kind = copy.deepcopy(document)
    bad_kind["nodes"][0]["kind"] = "fact"
    _reject(bad_kind, PROJECTION)
    relation = next(edge for edge in document["edges"] if edge["kind"] == "code_relation")
    bad_from = copy.deepcopy(document)
    for edge in bad_from["edges"]:
        if edge["kind"] == "code_relation":
            edge["from_node"] = "dln-" + "a" * 20
            break
    else:
        raise AssertionError(relation)
    _reject(bad_from, PROJECTION)
    for key, value in (
        ("fact_source", "graph"),
        ("write_kind", "direct_store_write"),
        ("ranking", "ranked"),
        ("taxonomy_promotion", "candidate"),
    ):
        bad = copy.deepcopy(document)
        bad[key] = value
        _reject(bad, PROJECTION)
    official = copy.deepcopy(document)
    official["canonical_official"] = True
    _reject(official, PROJECTION)
    allowed = copy.deepcopy(document)
    allowed["next_action"] = "filter_paper_id"
    validate_document(allowed, expected_schema=PROJECTION)


def test_query_fusion_routes_score_and_currency() -> None:
    document = _fixture(QUERY)
    validate_document(document, expected_schema=QUERY)
    algo = copy.deepcopy(document)
    algo["fusion"]["algorithm"] = "rrf-v2"
    _reject(algo, QUERY)
    constant = copy.deepcopy(document)
    constant["fusion"]["rank_constant"] = 61
    _reject(constant, QUERY)
    arithmetic = copy.deepcopy(document)
    arithmetic["fusion"]["score_arithmetic"] = "float"
    _reject(arithmetic, QUERY)
    order = copy.deepcopy(document)
    order["routes"] = list(reversed(order["routes"]))
    _reject(order, QUERY)
    score = copy.deepcopy(document)
    score["included"][0]["fused_score"]["numerator"] = "0.5"
    _reject(score, QUERY)
    omitted = copy.deepcopy(document)
    omitted["omitted"][0]["reason"] = "stale"
    _reject(omitted, QUERY)
    catalog = copy.deepcopy(document)
    catalog["currency"]["source_catalog"] = "consulted"
    _reject(catalog, QUERY)
    bm25 = copy.deepcopy(document)
    bm25["currency"]["bm25"] = {"binding": "generation_verified"}
    _reject(bm25, QUERY)
    budget = copy.deepcopy(document)
    budget["budget"]["quote_bytes_budget"] = 16384
    _reject(budget, QUERY)
