from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki_research.source_conversion_model import METADATA, validate_metadata


def metadata():
    return json.loads((Path(__file__).parents[1] / "fixtures/contracts/valid" / (METADATA + ".json")).read_bytes())


@pytest.mark.parametrize("published", ["2024-02-29", "2024-02-29T23:59:59Z", "2024-02-29T23:59:59.123456789Z"])
def test_date_union_and_unknown_optional_bibliography_are_explicit(published):
    value = metadata()
    value["published_at"] = published
    value.update(authors=[], title_zh="", code_urls=[], taxonomy=[])
    assert validate_metadata(value, value["paper_id"]) == value


@pytest.mark.parametrize("key,value", [
    ("unexpected", True), ("title", " \n\t"), ("title", "x" * 16385),
    ("title_zh", "中" * 16385), ("authors", ["x"] * 257), ("authors", ["x" * 16385]),
    ("code_urls", ["http://example.com"]), ("aliases", ["duplicate", "duplicate"]),
    ("paper_id", "2401.01234"), ("published_at", "2023-02-29"),
    ("published_at", "2024-01-01T00:00:00+00:00"), ("taxonomy", [{"axis": "untyped"}]),
])
def test_metadata_is_closed_bounded_and_typed(key, value):
    material = metadata()
    material[key] = value
    with pytest.raises(ContractError):
        validate_metadata(material, material["paper_id"])


@pytest.mark.parametrize("key", ["paper_id", "title", "title_zh", "authors", "published_at", "aliases", "taxonomy", "code_urls"])
def test_required_bibliographic_decisions_are_not_guessed(key):
    value = metadata()
    del value[key]
    with pytest.raises(ContractError):
        validate_document(value, METADATA)


@pytest.mark.parametrize("key,value", [("arxiv_id", "2402.01234"), ("doi", "10.1234/unbound"), ("doi", "invalid")])
def test_explicit_identifiers_require_canonical_identity_binding(key, value):
    material = metadata()
    material[key] = value
    with pytest.raises(ContractError) as err:
        validate_metadata(material, material["paper_id"])
    assert err.value.code == "SOURCE_CONVERSION_INVALID"


def test_explicit_doi_alias_is_accepted_and_caller_object_is_not_mutated():
    material = metadata()
    material.update(doi="https://doi.org/10.1234/Exact", aliases=["doi:10.1234/exact"])
    before = copy.deepcopy(material)
    result = validate_metadata(material, material["paper_id"])
    assert result == before == material
    assert result is not material
