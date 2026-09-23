from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.test_article_revision import _apply_staged_articles, _import_outline
from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_experiment_matrix import _publish_exp, _second_paper_payload
from tests.unit.test_experiment_store import valid_condition_input
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import status_domain_store
from video_paper_wiki.domain_versions import build_domain_source_version_view
from video_paper_wiki.experiment_matrix import build_experiment_comparison_matrix
from video_paper_wiki.flow.actions import (
    FORBIDDEN_TOKENS,
    STATUS_SCHEMA,
    assemble_next_actions,
    eligible_experiment_paper_id,
    make_action,
)
from video_paper_wiki.flow import status as status_mod
from video_paper_wiki.flow.actions import FlowError
from video_paper_wiki.flow.selection import select_flow
from video_paper_wiki.flow.status import build_flow_status
from video_paper_wiki.jcs import canonicalize

TREE = Path("tests/fixtures/contracts/agent-safe-command-tree.v1.json")
LEAVES = {tuple(item) for item in json.loads(TREE.read_text(encoding="utf-8"))["leaves"]}
VERDICTS = {
    "comparable",
    "comparable_with_caveats",
    "incomparable",
    "insufficient_conditions",
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _vault(world):
    return str(world["vault"])


def _expect(function, code):
    with pytest.raises(FlowError) as exc:
        function()
    assert exc.value.code == code
    return exc.value


def _articles(document):
    return [item for row in document["papers"] for item in row["articles"]]


def _assert_actions(document):
    validate_document(document, STATUS_SCHEMA)
    module_entries = []
    for item in document["next_actions"]:
        placeholders = {token for token in item["argv"] if token.startswith("<")}
        assert placeholders == set(item["placeholders"])
        for token in item["argv"]:
            assert token not in {"apply", "vpwiki-admin"}
        if item["leaf_check"] == "module_entry":
            module_entries.append(item)
            assert item["argv"][:4] == ["python", "-m", "video_paper_wiki.reading", "build"]
            continue
        if not item["argv"]:
            continue
        head = (item["argv"][0],)
        if head in LEAVES:
            continue
        assert tuple(item["argv"][:2]) in LEAVES
    return module_entries


def test_bare_world_is_empty_not_an_error(world):
    before_vault = _snapshot(world["vault"])
    work = world["checkout"] / ".work"
    before_work = _snapshot(work) if work.exists() else {}
    document = build_flow_status(vault_root=_vault(world), batch_id="sess1")
    validate_document(document, STATUS_SCHEMA)
    assert document["counts"]["papers"] == 0
    assert document["stages"]["discover"]["state"] == "empty"
    assert document["stages"]["annotate"]["lineage_count"] == 0
    ids = {item["id"] for item in document["next_actions"]}
    assert "discover-ingest-plan" in ids
    assert "discover-source-catalog-build" in ids
    assert "session-select" in ids
    select_paper = next(item for item in document["missing_inputs"] if item["id"] == "select-paper")
    assert select_paper["candidates"] == []
    again = build_flow_status(vault_root=_vault(world), batch_id="sess1")
    assert canonicalize(document) == canonicalize(again)
    assert _snapshot(world["vault"]) == before_vault
    assert ( _snapshot(work) if work.exists() else {} ) == before_work
    _assert_actions(document)


def test_three_chain_counts_filter_and_lineage_keys(world):
    _three_chain(world)
    versions = build_domain_source_version_view(vault_root=_vault(world))
    matrix = build_experiment_comparison_matrix(vault_root=_vault(world))
    domain = status_domain_store(vault_root=_vault(world))
    document = build_flow_status(vault_root=_vault(world))
    validate_document(document, STATUS_SCHEMA)
    assert document["counts"]["papers"] == 2
    assert document["counts"]["lineages"] == 1
    assert document["counts"]["conditions"] == 3
    assert document["counts"]["pairwise"] == len(matrix["pairwise"])
    assert document["stages"]["compare"]["pairwise_state"] == "computed"
    assert document["stages"]["annotate"]["by_typed_fact_status"] == {"reviewed_accepted": 1}
    verdicts = document["stages"]["compare"]["by_verdict"]
    assert set(verdicts) <= VERDICTS
    assert sum(verdicts.values()) == document["counts"]["pairwise"]
    assert document["stages"]["publish"] == {"state": "unpublished", "agent_apply": "not_available"}
    lined = next(row for row in document["papers"] if row["lineages"])
    d1 = next(row for row in versions["lineages"] if row["paper_id"] == lined["paper_id"])
    flow_row = lined["lineages"][0]
    assert set(flow_row) == {
        "lineage_id",
        "head_annotation_id",
        "current_review_id",
        "review_decision",
        "reviewed_officiality",
        "typed_fact_status",
        "source_association_id",
        "association_status",
        "version_status",
        "source_id",
        "version",
        "repository",
        "commit",
    }
    for key in flow_row:
        if key == "typed_fact_status":
            typed = next(item["typed_fact_status"] for item in domain["lineages"] if item["lineage_id"] == flow_row["lineage_id"])
            assert flow_row[key] == typed
        else:
            assert flow_row[key] == d1[key]
    bare = next(row for row in document["papers"] if not row["lineages"])
    ids = {item["id"] for item in document["next_actions"]}
    assert "annotate-domain-record-" + bare["paper_id"] in ids
    record = next(item for item in document["next_actions"] if item["id"].startswith("annotate-domain-record-"))
    assert "<code_batch_id>" in record["placeholders"]
    known = lined["paper_id"]
    filtered = build_flow_status(vault_root=_vault(world), paper_id=known)
    assert [row["paper_id"] for row in filtered["papers"]] == [known]
    assert filtered["counts"] == document["counts"]
    err = _expect(
        lambda: build_flow_status(vault_root=_vault(world), paper_id="sha256:" + "f" * 64),
        "FLOW_INVALID",
    )
    assert err.details["reason"] == "unknown_paper"
    assert err.details["instance_pointer"] == "/paper_id"
    _assert_actions(document)


def test_basis_gate_and_upstream_shape(world, monkeypatch):
    _three_chain(world)
    real = status_mod.status_article_store(vault_root=_vault(world), batch_id=None)

    def flipped(**_kwargs):
        document = copy.deepcopy(real)
        sha = document["basis"]["experiment_store_inventory_sha256"]
        document["basis"]["experiment_store_inventory_sha256"] = ("0" if sha[0] != "0" else "1") + sha[1:]
        return document

    monkeypatch.setattr(status_mod, "status_article_store", flipped)
    err = _expect(lambda: build_flow_status(vault_root=_vault(world)), "FLOW_BASIS_CHANGED")
    assert err.exit_code == 75
    assert err.details["instance_pointer"] == "/basis/experiment_store_inventory_sha256"
    monkeypatch.setattr(status_mod, "status_experiment_store", lambda **_kwargs: {})
    missing = _expect(lambda: build_flow_status(vault_root=_vault(world)), "FLOW_INVALID")
    assert missing.details["reason"] == "upstream_shape"


def test_selection_current_changed_and_shape(world):
    _three_chain(world)
    paper = world["association"]["paper_id"]
    selected = select_flow(vault_root=_vault(world), batch_id="sess1", paper_ids=[paper])
    assert selected["state"] == "selected"
    document = build_flow_status(vault_root=_vault(world), batch_id="sess1")
    assert document["selection"]["paper_ids"] == [paper]
    assert document["selection"]["basis_state"] == "current"
    assert sum(1 for row in document["papers"] if row["selected"]) == 1
    _publish_exp(
        world,
        valid_condition_input(world, setting_key="table9-extra-flow"),
        batch="e-extra",
        name="extra.json",
    )
    changed = build_flow_status(vault_root=_vault(world), batch_id="sess1")
    assert changed["selection"]["basis_state"] == "changed"
    path = world["checkout"] / ".work" / "sess1" / "flow" / "selection.json"
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"unpublished"', b'"published!"', 1))
    err = _expect(lambda: build_flow_status(vault_root=_vault(world), batch_id="sess1"), "FLOW_INVALID")
    assert err.details["reason"] == "selection_shape"


def test_article_staged_then_vault(world):
    _three_chain(world)
    imported = _import_outline(world, batch="art1")
    document = build_flow_status(vault_root=_vault(world), batch_id="art1")
    articles = _articles(document)
    assert articles[0]["head_location"] == "staged"
    assert articles[0]["next_section_id"] == "s1"
    assert document["stages"]["survey"]["in_progress_count"] == 1
    export = next(item for item in document["next_actions"] if item["id"].startswith("survey-export-"))
    assert "--section-id" in export["argv"]
    assert export["argv"][export["argv"].index("--section-id") + 1] == "s1"
    assert "--batch-id" in export["argv"]
    assert export["argv"][export["argv"].index("--batch-id") + 1] == "art1"
    module_entries = _assert_actions(document)
    assert len(module_entries) == 1
    _apply_staged_articles(world, "art1")
    vaulted = build_flow_status(vault_root=_vault(world))
    vault_articles = _articles(vaulted)
    assert vault_articles[0]["article_id"] == imported["record"]["article_id"]
    export_vault = next(item for item in vaulted["next_actions"] if item["id"].startswith("survey-export-"))
    assert "--batch-id" not in export_vault["argv"]
    _assert_actions(vaulted)


def test_forbidden_token_and_invalid_paper_before_io(world):
    err = _expect(lambda: make_action("x", "session", "r", ["apply"], "none", "command_tree"), "FLOW_INVALID")
    assert err.details["reason"] == "forbidden_token"
    assert FORBIDDEN_TOKENS[0] == "apply"
    missing = _expect(
        lambda: build_flow_status(vault_root="/nonexistent", paper_id="not-a-paper"),
        "FLOW_INVALID",
    )
    assert missing.details["instance_pointer"] == "/paper_id"


def test_multiselect_experiment_primary_and_incompatible_association(world):
    _three_chain(world)
    p1 = world["association"]["paper_id"]
    p2 = next(row["paper_id"] for row in build_flow_status(vault_root=_vault(world))["papers"] if row["paper_id"] != p1)
    selected = select_flow(vault_root=_vault(world), batch_id="st-multi", paper_ids=[p2, p1])
    document = build_flow_status(vault_root=_vault(world), batch_id="st-multi")
    _assert_actions(document)
    action = next(item for item in document["next_actions"] if item["id"].startswith("compare-prepare-experiment-"))
    assert action["argv"].count("--paper-id") == 1
    primary = action["argv"][action["argv"].index("--paper-id") + 1]
    assert primary == p1
    assert action["id"] == "compare-prepare-experiment-" + p1
    assert p1 in action["reason"]
    assert document["selection"]["paper_ids"] == selected["selection"]["paper_ids"]
    assert all(item["id"] != "experiment-paper-id" for item in document["missing_inputs"])
    assoc1 = "sva-" + "1" * 64
    assoc2 = "sva-" + "2" * 64
    left = "sha256:" + "c" * 64
    right = "sha256:" + "d" * 64
    papers = [
        {
            "paper_id": left,
            "lineages": [
                {
                    "lineage_id": "dln-" + "1" * 20,
                    "typed_fact_status": "reviewed_accepted",
                    "source_association_id": assoc1,
                    "association_status": "changed",
                    "head_annotation_id": "dan-" + "1" * 20,
                    "current_review_id": None,
                }
            ],
            "conditions": [],
            "articles": [],
        },
        {
            "paper_id": right,
            "lineages": [
                {
                    "lineage_id": "dln-" + "2" * 20,
                    "typed_fact_status": "reviewed_accepted",
                    "source_association_id": assoc2,
                    "association_status": "bound",
                    "head_annotation_id": "dan-" + "2" * 20,
                    "current_review_id": None,
                }
            ],
            "conditions": [],
            "articles": [],
        },
    ]
    selection = {"paper_ids": [right, left], "association_id": assoc1, "question": None}
    assert eligible_experiment_paper_id(selection, papers) is None
    assert eligible_experiment_paper_id({"paper_ids": [right, left], "association_id": None}, papers) == right
    actions = assemble_next_actions(
        vault_root=_vault(world),
        batch_id="st-incompat",
        selection=selection,
        papers=papers,
        universe_ids=[left, right],
        condition_count=0,
        experiment_next=None,
        articles=[],
    )
    ids = [item["id"] for item in actions]
    assert not any(item.startswith("compare-prepare-experiment-") for item in ids)
    reselect = next(item for item in actions if item["id"] == "session-select-new-batch")
    assert reselect["argv"][reselect["argv"].index("--batch-id") + 1] == "<batch_id>"
    assert reselect["argv"][reselect["argv"].index("--batch-id") + 1] != "st-incompat"
    assert "<batch_id>" in reselect["placeholders"]
    assert "<paper_id>" in reselect["placeholders"]


def _grow_conditions(world, payload, *, count, key_prefix, batch_prefix):
    for index in range(count):
        extra = copy.deepcopy(payload)
        extra["setting_key"] = key_prefix + format(index, "03d")
        extra["claim_refs"] = []
        _publish_exp(
            world,
            extra,
            name=batch_prefix + str(index) + ".json",
            batch=batch_prefix + str(index),
        )


def _paper_rows_by_id(document):
    return {row["paper_id"]: row for row in document["papers"]}


def _action_ids(document):
    return {item["id"] for item in document["next_actions"]}


def test_scale_64_computed_then_a2_b63_continues_small_scope(world):
    from tests.code_proof_public_fixture import parse_envelope, run_module_cli
    from tests.unit.test_article_revision import _question
    from video_paper_wiki.article_context import ArticleContextError
    from video_paper_wiki.experiment_matrix import ExperimentMatrixError, MAX_PAIRWISE_ROWS
    from video_paper_wiki.flow.prepare import prepare_flow

    _three_chain(world)
    paper_a = world["association"]["paper_id"]
    paper_b = "sha256:" + "b" * 64
    payload, _association = _second_paper_payload(world)
    _grow_conditions(world, payload, count=61, key_prefix="grow-b-", batch_prefix="gb")
    vault = _vault(world)
    at_64 = build_flow_status(vault_root=vault)
    validate_document(at_64, STATUS_SCHEMA)
    matrix_64 = build_experiment_comparison_matrix(vault_root=vault)
    assert at_64["counts"]["conditions"] == 64
    assert at_64["stages"]["compare"]["pairwise_state"] == "computed"
    assert at_64["counts"]["pairwise"] == len(matrix_64["pairwise"])
    assert at_64["stages"]["compare"]["pairwise_count"] == len(matrix_64["pairwise"])
    assert sum(at_64["stages"]["compare"]["by_verdict"].values()) == at_64["counts"]["pairwise"]
    assert "compare-matrix" in _action_ids(at_64)
    _grow_conditions(world, payload, count=1, key_prefix="grow-b-x-", batch_prefix="gbx")
    before_vault = _snapshot(world["vault"])
    default = build_flow_status(vault_root=vault)
    filtered = build_flow_status(vault_root=vault, paper_id=paper_a)
    saved = select_flow(vault_root=vault, batch_id="saved-small", paper_ids=[paper_a])
    session = build_flow_status(vault_root=vault, batch_id="saved-small")
    assert _snapshot(world["vault"]) == before_vault
    for document in (default, filtered, session):
        validate_document(document, STATUS_SCHEMA)
        _assert_actions(document)
        assert document["counts"]["conditions"] == 65
        rows = _paper_rows_by_id(document) if document is default else {row["paper_id"]: row for row in document["papers"]}
        if document is default:
            assert len(rows[paper_a]["conditions"]) == 2
            assert len(rows[paper_b]["conditions"]) == 63
        assert document["stages"]["compare"]["pairwise_state"] == "not_computed_limit"
        assert document["counts"]["pairwise"] is None
        assert document["stages"]["compare"]["pairwise_count"] is None
        assert document["stages"]["compare"]["by_verdict"] == {}
        assert document["counts"] == default["counts"]
        assert any(item["id"] == "compare-pairwise-limit" for item in document["missing_inputs"])
        matrix_action = next(item for item in document["next_actions"] if item["id"].startswith("compare-matrix-"))
        assert matrix_action["id"] == "compare-matrix-" + paper_a
        assert matrix_action["argv"].count("--paper-id") == 1
        assert matrix_action["argv"][matrix_action["argv"].index("--paper-id") + 1] == paper_a
        assert "单篇" in matrix_action["reason"]
        assert paper_a in matrix_action["reason"]
        assert "compare-matrix" not in _action_ids(document)
    assert [row["paper_id"] for row in filtered["papers"]] == [paper_a]
    assert session["selection"]["paper_ids"] == [paper_a]
    assert saved["selection"]["paper_ids"] == [paper_a]
    matrix_proc = run_module_cli(
        world["checkout"],
        next(item["argv"] for item in default["next_actions"] if item["id"] == "compare-matrix-" + paper_a),
    )
    assert matrix_proc.returncode == 0, matrix_proc.stdout + matrix_proc.stderr
    matrix_env = parse_envelope(matrix_proc)
    assert matrix_env["ok"] is True
    assert matrix_env["data"]["paper_filter"] == paper_a
    assert matrix_env["data"]["row_count"] == 2
    prepared_exp = prepare_flow(
        vault_root=vault,
        batch_id="saved-small",
        kind="experiment",
        setting_key="table9-row1-flow",
    )
    assert prepared_exp["paper_ids"] == [paper_a]
    question = _question(world)
    prepared_art = prepare_flow(
        vault_root=vault,
        batch_id="saved-small",
        kind="article",
        question=question,
    )
    import_action = next(item for item in prepared_art["next_actions"] if item["id"] == "survey-import-article")
    imported = run_module_cli(
        world["checkout"],
        [
            token
            if token not in {"<recorded_by>", "<recorded_at>"}
            else {"<recorded_by>": "fixture", "<recorded_at>": "2026-09-15T00:00:00Z"}[token]
            for token in import_action["argv"]
        ],
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr
    live = build_flow_status(vault_root=vault, batch_id="saved-small")
    assert live["selection"]["paper_ids"] == [paper_a]
    reading = next(item for item in live["next_actions"] if item["id"].startswith("survey-reading-build-"))
    assert reading["id"] == "survey-reading-build-" + paper_a
    assert reading["argv"].count("--paper-id") == 1
    assert reading["argv"][reading["argv"].index("--paper-id") + 1] == paper_a
    assert "单篇" in reading["reason"]
    env = os.environ.copy()
    previous = env.get("PYTHONPATH")
    src = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src if not previous else src + os.pathsep + previous
    filled = [
        token if token != "<reading_batch>" else "read-a"
        for token in reading["argv"]
    ]
    assert filled[:3] == ["python", "-m", "video_paper_wiki.reading"]
    reading_proc = subprocess.run(
        [sys.executable, "-m", "video_paper_wiki.reading", *filled[3:]],
        cwd=world["checkout"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert reading_proc.returncode == 0, reading_proc.stdout + reading_proc.stderr
    reading_env = parse_envelope(reading_proc)
    assert reading_env["ok"] is True
    assert reading_env["data"]["paper_filter"] == paper_a
    both = select_flow(vault_root=vault, batch_id="saved-both", paper_ids=[paper_a, paper_b], question=question)
    both_status = build_flow_status(vault_root=vault, batch_id="saved-both")
    assert both_status["selection"]["paper_ids"] == both["selection"]["paper_ids"]
    assert "survey-prepare-article" not in _action_ids(both_status)
    assert any(item["id"] == "article-narrow-selection" for item in both_status["missing_inputs"])
    with pytest.raises(ArticleContextError) as art_err:
        prepare_flow(vault_root=vault, batch_id="over-art", kind="article", paper_ids=[paper_a, paper_b], question=question)
    assert art_err.value.code == "ARTICLE_CONTEXT_LIMIT"
    with pytest.raises(ExperimentMatrixError) as matrix_err:
        build_experiment_comparison_matrix(vault_root=vault)
    assert matrix_err.value.code == "EXPERIMENT_MATRIX_LIMIT"
    assert matrix_err.value.details["row_count"] == 65
    assert matrix_err.value.details["limit"] == MAX_PAIRWISE_ROWS
    assert _snapshot(world["vault"]) == before_vault


def test_single_paper_65_keeps_experiment_and_omits_doomed_actions(world):
    from tests.unit.test_article_revision import _question
    from tests.unit.test_domain_relations import _accept, _bound_proposal, _publish
    from video_paper_wiki.article_context import ArticleContextError
    from video_paper_wiki.experiment_matrix import ExperimentMatrixError, MAX_PAIRWISE_ROWS
    from video_paper_wiki.flow.prepare import prepare_flow

    proposal, _planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    _accept(world, first, batch="r1", officiality="official")
    base = valid_condition_input(world, claim_refs=[])
    _grow_conditions(world, base, count=65, key_prefix="solo-", batch_prefix="solo")
    paper = world["association"]["paper_id"]
    vault = _vault(world)
    before_vault = _snapshot(world["vault"])
    document = build_flow_status(vault_root=vault)
    validate_document(document, STATUS_SCHEMA)
    _assert_actions(document)
    assert document["counts"]["conditions"] == 65
    assert document["stages"]["compare"]["pairwise_state"] == "not_computed_limit"
    assert document["counts"]["pairwise"] is None
    ids = _action_ids(document)
    assert not any(item.startswith("compare-matrix") for item in ids)
    assert not any(item.startswith("survey-reading-build") for item in ids)
    assert "survey-prepare-article" not in ids
    assert any(item["id"] == "compare-pairwise-limit" for item in document["missing_inputs"])
    assert any(item["id"] == "compare-paper-id" for item in document["missing_inputs"])
    selected = select_flow(
        vault_root=vault,
        batch_id="solo-sel",
        paper_ids=[paper],
        question=_question(world),
    )
    live = build_flow_status(vault_root=vault, batch_id="solo-sel")
    assert live["selection"]["paper_ids"] == selected["selection"]["paper_ids"]
    assert "survey-prepare-article" not in _action_ids(live)
    assert any(item["id"].startswith("compare-prepare-experiment-") for item in live["next_actions"])
    prepared = prepare_flow(
        vault_root=vault,
        batch_id="solo-sel",
        kind="experiment",
        setting_key="table9-row1-flow",
    )
    assert prepared["paper_ids"] == [paper]
    with pytest.raises(ArticleContextError) as art_err:
        prepare_flow(vault_root=vault, batch_id="solo-sel", kind="article")
    assert art_err.value.code == "ARTICLE_CONTEXT_LIMIT"
    with pytest.raises(ExperimentMatrixError) as matrix_err:
        build_experiment_comparison_matrix(vault_root=vault, paper_id=paper)
    assert matrix_err.value.code == "EXPERIMENT_MATRIX_LIMIT"
    assert matrix_err.value.details["row_count"] == 65
    assert matrix_err.value.details["limit"] == MAX_PAIRWISE_ROWS
    reselect = next(item for item in live["missing_inputs"] if item["id"] == "compare-paper-id")
    assert "new batch" in reselect["reason"]
    assert _snapshot(world["vault"]) == before_vault
