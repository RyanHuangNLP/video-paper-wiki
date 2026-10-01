from __future__ import annotations

import copy
import json

import pytest

from tests.contract.paths import VALID, load_json
from tests.unit.test_article_revision import _papers, _question
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.article_store import MAX_TITLE
from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document
from video_paper_wiki.flow.actions import PREPARE_SCHEMA, SELECTION_SCHEMA, STATUS_SCHEMA
from video_paper_wiki.flow.prepare import prepare_flow
from video_paper_wiki.flow.selection import select_flow
from video_paper_wiki.flow.status import build_flow_status
from video_paper_wiki.jcs import canonicalize

TITLES = (STATUS_SCHEMA, SELECTION_SCHEMA, PREPARE_SCHEMA)


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


def test_shared_refusals() -> None:
    status = _fixture(STATUS_SCHEMA)
    validate_document(status, expected_schema=STATUS_SCHEMA)
    for key, value in (
        ("publication", "published"),
        ("applied", True),
        ("ranking", "ranked"),
    ):
        bad = copy.deepcopy(status)
        bad[key] = value
        _reject(bad, STATUS_SCHEMA)
    bad = copy.deepcopy(status)
    bad["stages"]["publish"]["agent_apply"] = "available"
    _reject(bad, STATUS_SCHEMA)
    bad = copy.deepcopy(status)
    bad["next_actions"][0]["leaf_check"] = "shell"
    _reject(bad, STATUS_SCHEMA)
    bad = copy.deepcopy(status)
    bad["next_actions"][0]["writes"] = "vault"
    _reject(bad, STATUS_SCHEMA)
    bad = copy.deepcopy(status)
    bad["selection"] = {
        "paper_ids": ["sha256:" + "b" * 64],
        "association_id": None,
        "question": None,
        "basis_state": "stale",
    }
    _reject(bad, STATUS_SCHEMA)
    status_paper = copy.deepcopy(status)
    status_paper["counts"]["papers"] = 1
    status_paper["stages"]["discover"] = {"state": "papers_known", "paper_count": 1}
    status_paper["papers"] = [
        {
            "paper_id": "sha256:" + "b" * 64,
            "selected": False,
            "lineages": [
                {
                    "lineage_id": "dln-" + "f" * 20,
                    "head_annotation_id": "dan-" + "1" * 20,
                    "current_review_id": None,
                    "review_decision": None,
                    "reviewed_officiality": None,
                    "typed_fact_status": 42,
                    "source_association_id": "sva-" + "c" * 64,
                    "association_status": "bound",
                    "version_status": "proposal_only",
                    "source_id": None,
                    "version": None,
                    "repository": "owner/name",
                    "commit": "a" * 40,
                }
            ],
            "conditions": [],
            "articles": [],
        }
    ]
    _reject(status_paper, STATUS_SCHEMA)
    bad = copy.deepcopy(status)
    bad["counts"]["papers"] = -1
    _reject(bad, STATUS_SCHEMA)
    selection = _fixture(SELECTION_SCHEMA)
    for papers in (
        ["sha256:" + format(index, "064x") for index in range(9)],
        [],
        ["sha256:" + "b" * 64, "sha256:" + "b" * 64],
    ):
        bad = copy.deepcopy(selection)
        bad["paper_ids"] = papers
        _reject(bad, SELECTION_SCHEMA)
    prepare = _fixture(PREPARE_SCHEMA)
    bad = copy.deepcopy(prepare)
    bad["kind"] = "domain"
    _reject(bad, PREPARE_SCHEMA)


def test_schema_titles() -> None:
    for title in TITLES:
        assert schema_by_title(title)["title"] == title


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def test_real_world_documents(world) -> None:
    _three_chain(world)
    vault = str(world["vault"])
    papers = _papers(world)
    status = build_flow_status(vault_root=vault)
    validate_document(status, STATUS_SCHEMA)
    selected = select_flow(vault_root=vault, batch_id="sess1", paper_ids=[papers[0]], question=_question(world))
    validate_document(selected["selection"], SELECTION_SCHEMA)
    raw = (world["checkout"] / ".work" / "sess1" / "flow" / "selection.json").read_bytes()
    assert canonicalize(json.loads(raw.decode("utf-8"))) == raw
    prepared = prepare_flow(vault_root=vault, batch_id="sess1", kind="article")
    validate_document(prepared, PREPARE_SCHEMA)
    live = build_flow_status(vault_root=vault, batch_id="sess1")
    validate_document(live, STATUS_SCHEMA)
    long_q = _question(world) + " " + ("测" * (301 - len(_question(world)) - 1))
    assert len(long_q) == 301
    long_prepared = prepare_flow(
        vault_root=vault,
        batch_id="sess1",
        kind="article",
        paper_ids=[papers[0]],
        question=long_q,
    )
    validate_document(long_prepared, PREPARE_SCHEMA)
    body = json.loads(
        (world["checkout"] / long_prepared["outputs"][1]["path"]).read_bytes().decode("utf-8")
    )
    assert len(body["title"]) == MAX_TITLE
    assert body["title"] == long_q[:MAX_TITLE]
    assert long_prepared["article_binding"]["question"] == long_q
    multi = select_flow(vault_root=vault, batch_id="sess-multi", paper_ids=papers)
    validate_document(multi["selection"], SELECTION_SCHEMA)
    live_multi = build_flow_status(vault_root=vault, batch_id="sess-multi")
    validate_document(live_multi, STATUS_SCHEMA)
    action = next(
        item for item in live_multi["next_actions"] if item["id"].startswith("compare-prepare-experiment-")
    )
    assert action["argv"].count("--paper-id") == 1


def test_pairwise_state_legacy_computed_and_limit_refusals() -> None:
    status = _fixture(STATUS_SCHEMA)
    validate_document(status, expected_schema=STATUS_SCHEMA)
    assert "pairwise_state" not in status["stages"]["compare"]
    computed = copy.deepcopy(status)
    computed["stages"]["compare"]["pairwise_state"] = "computed"
    validate_document(computed, expected_schema=STATUS_SCHEMA)
    limited = copy.deepcopy(status)
    limited["stages"]["compare"]["pairwise_state"] = "not_computed_limit"
    limited["counts"]["pairwise"] = None
    limited["stages"]["compare"]["pairwise_count"] = None
    limited["stages"]["compare"]["by_verdict"] = {}
    validate_document(limited, expected_schema=STATUS_SCHEMA)
    null_without_state = copy.deepcopy(status)
    null_without_state["counts"]["pairwise"] = None
    null_without_state["stages"]["compare"]["pairwise_count"] = None
    _reject(null_without_state, STATUS_SCHEMA)
    computed_null = copy.deepcopy(computed)
    computed_null["counts"]["pairwise"] = None
    computed_null["stages"]["compare"]["pairwise_count"] = None
    _reject(computed_null, STATUS_SCHEMA)
    limited_zero = copy.deepcopy(limited)
    limited_zero["counts"]["pairwise"] = 0
    limited_zero["stages"]["compare"]["pairwise_count"] = 0
    _reject(limited_zero, STATUS_SCHEMA)
    limited_verdict = copy.deepcopy(limited)
    limited_verdict["stages"]["compare"]["by_verdict"] = {"comparable": 1}
    _reject(limited_verdict, STATUS_SCHEMA)
    mixed = copy.deepcopy(limited)
    mixed["counts"]["pairwise"] = 3
    _reject(mixed, STATUS_SCHEMA)
    unknown_state = copy.deepcopy(status)
    unknown_state["stages"]["compare"]["pairwise_state"] = "skipped"
    _reject(unknown_state, STATUS_SCHEMA)
