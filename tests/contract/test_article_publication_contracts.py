from __future__ import annotations

import copy

import pytest

from tests.contract.paths import VALID, load_json
from video_paper_wiki.contracts import ContractError, validate_document

TITLES = (
    "video-paper-wiki.article-publication-request.v1",
    "video-paper-wiki.article-publication-inspection.v1",
    "video-paper-wiki.article-publication-apply-result.v1",
)
CHECK_TITLE = "video-paper-wiki.article-check.v1"


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
    title = "video-paper-wiki.article-publication-request.v1"
    document = _fixture(title)
    bad_kind = copy.deepcopy(document)
    bad_kind["kind"] = "experiments"
    _reject(bad_kind, title)
    exp_heads = copy.deepcopy(document)
    exp_heads["payloads"][0]["path"] = "wiki/meta/experiments/heads.json"
    _reject(exp_heads, title)
    render_path = copy.deepcopy(document)
    render_path["payloads"][0]["path"] = (
        "wiki/meta/articles/render/art-" + "a" * 20 + "/arv-" + "b" * 20 + ".md"
    )
    _reject(render_path, title)
    reviews = copy.deepcopy(document)
    reviews["payloads"][0]["path"] = "wiki/meta/experiments/reviews/x.json"
    _reject(reviews, title)
    exp_content = copy.deepcopy(document)
    digest = exp_content["payloads"][0]["after_sha256"]
    exp_content["payloads"][0]["content_file"] = "experiment-publication/content/" + digest
    _reject(exp_content, title)
    missing_basis = copy.deepcopy(document)
    del missing_basis["basis"]["article_store_inventory_sha256"]
    _reject(missing_basis, title)
    touched = copy.deepcopy(document)
    touched["touched_articles"] = ["exc-" + "a" * 20]
    _reject(touched, title)
    unwritten = copy.deepcopy(document)
    unwritten["compiled_heads"][0]["progress"]["unwritten"] = 1
    _reject(unwritten, title)
    affected = copy.deepcopy(document)
    affected["compiled_heads"][0]["check_status"] = "affected"
    _reject(affected, title)
    inconsistent = copy.deepcopy(document)
    inconsistent["compiled_heads"][0]["check_status"] = "inconsistent"
    _reject(inconsistent, title)
    applied = copy.deepcopy(document)
    applied["applied"] = True
    _reject(applied, title)
    ranked = copy.deepcopy(document)
    ranked["ranking"] = "ranked"
    _reject(ranked, title)
    promotion = copy.deepcopy(document)
    promotion["typed_fact_promotion"] = "candidate"
    _reject(promotion, title)
    published = copy.deepcopy(document)
    published["publication"] = "published"
    _reject(published, title)


def test_inspection_verified_and_next_action() -> None:
    title = "video-paper-wiki.article-publication-inspection.v1"
    document = _fixture(title)
    gates = copy.deepcopy(document)
    gates["gates_verified"] = False
    _reject(gates, title)
    chains = copy.deepcopy(document)
    chains["chains_verified"] = False
    _reject(chains, title)
    later = copy.deepcopy(document)
    later["next_action"] = "apply_requires_later_slice"
    _reject(later, title)


def test_apply_result_write_kind_and_coverage() -> None:
    title = "video-paper-wiki.article-publication-apply-result.v1"
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
    publish = copy.deepcopy(document)
    publish["next_action"] = "publish"
    _reject(publish, title)


def test_article_check_recorded_binding_null_branch() -> None:
    document = _fixture(CHECK_TITLE)
    null_binding = copy.deepcopy(document)
    null_binding["items"][0]["recorded_binding"] = None
    validate_document(null_binding, expected_schema=CHECK_TITLE)
    as_string = copy.deepcopy(document)
    as_string["items"][0]["recorded_binding"] = "x"
    _reject(as_string, CHECK_TITLE)
    empty = copy.deepcopy(document)
    empty["items"][0]["recorded_binding"] = {}
    _reject(empty, CHECK_TITLE)
    missing_field = copy.deepcopy(document)
    recorded = dict(missing_field["items"][0]["recorded_binding"])
    recorded.pop(next(iter(recorded)))
    missing_field["items"][0]["recorded_binding"] = recorded
    _reject(missing_field, CHECK_TITLE)
