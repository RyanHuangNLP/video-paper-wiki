from __future__ import annotations

import copy

import pytest

from tests.contract.paths import VALID, load_json
from video_paper_wiki.contracts import ContractError, validate_document

TITLES = (
    "video-paper-wiki.experiment-publication-request.v1",
    "video-paper-wiki.experiment-publication-inspection.v1",
    "video-paper-wiki.experiment-publication-apply-result.v1",
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


def test_request_kind_path_content_and_consts() -> None:
    title = "video-paper-wiki.experiment-publication-request.v1"
    document = _fixture(title)
    bad_kind = copy.deepcopy(document)
    bad_kind["kind"] = "domain"
    _reject(bad_kind, title)
    domain_heads = copy.deepcopy(document)
    domain_heads["payloads"][0]["path"] = "wiki/meta/domain/heads.json"
    _reject(domain_heads, title)
    reviews = copy.deepcopy(document)
    reviews["payloads"][0]["path"] = (
        "wiki/meta/experiments/reviews/exc-" + "a" * 20 + "/x.json"
    )
    _reject(reviews, title)
    domain_content = copy.deepcopy(document)
    digest = domain_content["payloads"][0]["after_sha256"]
    domain_content["payloads"][0]["content_file"] = "domain-publication/content/" + digest
    _reject(domain_content, title)
    missing_basis = copy.deepcopy(document)
    del missing_basis["basis"]["experiment_store_inventory_sha256"]
    _reject(missing_basis, title)
    dln = copy.deepcopy(document)
    dln["touched_conditions"] = ["dln-" + "a" * 20]
    _reject(dln, title)
    applied = copy.deepcopy(document)
    applied["applied"] = True
    _reject(applied, title)
    ranked = copy.deepcopy(document)
    ranked["ranking"] = "ranked"
    _reject(ranked, title)
    promotion = copy.deepcopy(document)
    promotion["typed_fact_promotion"] = "candidate"
    _reject(promotion, title)


def test_inspection_verified_and_next_action() -> None:
    title = "video-paper-wiki.experiment-publication-inspection.v1"
    document = _fixture(title)
    basis = copy.deepcopy(document)
    basis["basis_verified"] = False
    _reject(basis, title)
    bindings = copy.deepcopy(document)
    bindings["bindings_verified"] = False
    _reject(bindings, title)
    later = copy.deepcopy(document)
    later["next_action"] = "apply_requires_later_slice"
    _reject(later, title)


def test_apply_result_write_kind_and_coverage() -> None:
    title = "video-paper-wiki.experiment-publication-apply-result.v1"
    document = _fixture(title)
    transaction = copy.deepcopy(document)
    transaction["write_kind"] = "transaction"
    _reject(transaction, title)
    not_applied = copy.deepcopy(document)
    not_applied["applied"] = False
    _reject(not_applied, title)
    receipt = copy.deepcopy(document)
    receipt["receipt_backed"] = True
    _reject(receipt, title)
    wired = copy.deepcopy(document)
    wired["audit_coverage"] = "wired"
    _reject(wired, title)
