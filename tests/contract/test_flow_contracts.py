from __future__ import annotations

import copy
import json

import pytest

from tests.contract.paths import VALID, load_json
from tests.unit.test_article_revision import _papers, _question
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
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
