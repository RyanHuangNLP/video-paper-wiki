from __future__ import annotations

import json
import os
import socket

import pytest

from tests.source_semantics_fixture import event_for, source_fixture
from tests.unit.test_domain_proposal import _snapshot, _write, make_world
from tests.unit.test_domain_store import LATER_AT
from tests.unit.test_domain_versions import _reseal_association
from tests.unit.test_experiment_apply import _apply_exp, _compile
from tests.unit.test_experiment_store import (
    _document,
    _empirical,
    _paper_direct,
    _record_exp,
    _reported,
    _status,
    _unknown,
    valid_condition_input,
)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.experiment_comparability import compare_experiment_records
from video_paper_wiki.experiment_matrix import (
    MAX_PAIRWISE_ROWS,
    MATRIX_SCHEMA,
    ExperimentMatrixError,
    build_experiment_comparison_matrix,
)
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha

FORBIDDEN_KEYS = {"ranked", "better", "winner", "score_delta"}
FIXTURE = json.loads(
    (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "fixtures/contracts/valid/video-paper-wiki.experiment-comparison-matrix.v1.json"
    ).read_bytes()
)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _matrix(world, paper_id=None):
    return build_experiment_comparison_matrix(vault_root=str(world["vault"]), paper_id=paper_id)


def _expect(fn, code):
    with pytest.raises((ExperimentMatrixError, ExperimentStoreError, DomainStoreError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    assert details.get("next_action")
    if code != "WORK_PATH_UNSAFE":
        assert details.get("instance_pointer") is not None
    return err.value


def _publish_exp(world, payload=None, *, batch, name="condition.json", previous=None, recorded_at=None, **overrides):
    data = _record_exp(
        world,
        payload,
        name=name,
        previous=previous,
        recorded_at=recorded_at or "2026-09-14T00:00:00Z",
        batch=batch,
        **overrides,
    )
    _compile(world, batch)
    _apply_exp(world, batch)
    return data


def _second_paper_payload(world):
    association, raw, _authority = source_fixture(paper_id="sha256:" + "b" * 64, text="second paper body")
    assoc_raw = canonicalize(association)
    _write(world["vault"] / "wiki/meta/records/source-versions" / (association["association_id"] + ".json"), assoc_raw)
    _write(world["vault"] / association["raw"]["path"], raw)
    payload = valid_condition_input(world, paper_id=association["paper_id"], claim_refs=[])
    payload["source_association"] = {"association_id": association["association_id"], "sha256": sha(assoc_raw)}
    payload["source_digest"] = {
        "path": association["raw"]["path"],
        "sha256": association["raw"]["sha256"],
        "size_bytes": association["raw"]["size_bytes"],
    }
    rel, digest = _document(world)
    for cond in payload["conditions"].values():
        for source in cond["sources"]:
            if source["kind"] == "paper_direct":
                source["locator"]["source_id"] = association["source_id"]
                source["locator"]["artifact_path"] = rel
                source["locator"]["artifact_sha256"] = digest
        value = cond.get("value")
        if isinstance(value, list):
            for metric in value:
                ds = metric.get("definition_source")
                if ds and ds["kind"] == "paper_direct":
                    ds["locator"]["source_id"] = association["source_id"]
                    ds["locator"]["artifact_path"] = rel
                    ds["locator"]["artifact_sha256"] = digest
    return payload, association


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_empty_store_matches_fixture_shape(world):
    document = _matrix(world)
    validate_document(document, MATRIX_SCHEMA)
    assert document["row_count"] == 0
    assert document["rows"] == []
    assert document["cells"] == []
    assert document["metric_columns"] == []
    assert document["metric_cells"] == []
    assert document["pairwise"] == []
    assert document["next_action"] == "none"
    expected = dict(FIXTURE)
    expected["basis"] = document["basis"]
    assert document == expected


def test_three_chains_cells_pairwise_and_filter(world):
    a = _publish_exp(world, batch="ea")
    other_key = valid_condition_input(world, setting_key="table3-row1-vbench-256")
    b = _publish_exp(world, other_key, name="b.json", batch="eb")
    second_payload, association = _second_paper_payload(world)
    c = _publish_exp(world, second_payload, name="c.json", batch="ec")
    document = _matrix(world)
    validate_document(document, MATRIX_SCHEMA)
    ids = [row["condition_id"] for row in document["rows"]]
    assert ids == sorted(ids, key=lambda item: item.encode("utf-8"))
    assert [row["row_index"] for row in document["rows"]] == [0, 1, 2]
    assert document["row_count"] == 3
    for row in document["rows"]:
        assert row["version"] is not None
        if row["paper_id"] == world["association"]["paper_id"]:
            assert row["version"] == world["association"]["version"]
        else:
            assert row["version"] == association["version"]
    assert len(document["cells"]) == 27
    by_index = {row["row_index"]: row for row in document["rows"]}
    for cell in document["cells"]:
        assert all(item["record_id"] == by_index[cell["row_index"]]["record_id"] for item in cell["source_pointers"])
    inference = [cell for cell in document["cells"] if cell["column"] == "inference_steps"]
    assert inference
    for cell in inference:
        assert cell["status"] == "not_applicable"
        assert cell["value_summary"] is None
    assert document["metric_columns"] == [{"name": "fvd", "unit": "fvd"}]
    assert len(document["metric_cells"]) == 3
    assert len(document["pairwise"]) == 3
    heads = []
    store, _heads, _authority = __import__("video_paper_wiki.experiment_store", fromlist=["load_experiment_store"]).load_experiment_store(str(world["vault"]))
    for row in document["rows"]:
        heads.append(store.records[row["record_id"]])
    for pair, (i, j) in zip(document["pairwise"], ((0, 1), (0, 2), (1, 2))):
        assert pair["left"]["record_id"] == document["rows"][i]["record_id"]
        assert canonicalize(pair) == canonicalize(compare_experiment_records(heads[i], heads[j]))
    cross = [item for item in document["pairwise"] if item["same_paper"] is False]
    assert cross
    status = _status(world)
    assert document["basis"] == status["basis"]
    filtered = _matrix(world, paper_id=world["association"]["paper_id"])
    assert filtered["paper_filter"] == world["association"]["paper_id"]
    assert filtered["row_count"] == 2
    assert len(filtered["pairwise"]) == 1
    err = _expect(lambda: _matrix(world, paper_id="sha256:" + "f" * 64), "EXPERIMENT_MATRIX_PAPER_UNKNOWN")
    assert err.details["known_paper_count"] == 2
    _expect(lambda: _matrix(world, paper_id=""), "EXPERIMENT_MATRIX_INVALID")
    assert a["record"]["record_id"]
    assert b["record"]["record_id"]
    assert c["record"]["record_id"]


def test_unknown_resolution_and_stale_rows(world):
    _publish_exp(world, batch="u0")
    unknown = valid_condition_input(world, setting_key="table4-unknown-res", conditions={"resolution": _unknown()})
    _publish_exp(world, unknown, name="u.json", batch="eu")
    document = _matrix(world)
    cell = next(
        item
        for item in document["cells"]
        if item["column"] == "resolution" and item["status"] == "unknown"
    )
    assert cell["search_scope_pointer"] == "/conditions/resolution/search_scope"
    assert cell["source_count"] == 0
    related = [item for item in document["pairwise"] if True]
    assert any(item["verdict"] == "insufficient_conditions" for item in related)
    assert any(item["ranking"] == "refused_insufficient_conditions" for item in related)
    assert document["next_action"] == "supply_missing_conditions"
    assoc_path = world["vault"] / "wiki/meta/records/source-versions" / (world["association"]["association_id"] + ".json")
    original = assoc_path.read_bytes()
    mutated = json.loads(original)
    mutated["observation"]["title"] = "Rewritten"
    _resealed, mismatch_raw = _reseal_association(mutated)
    _write(assoc_path, mismatch_raw)
    stale = _matrix(world)
    changed_rows = [row for row in stale["rows"] if row["association_status"] == "changed"]
    assert changed_rows
    for row in changed_rows:
        assert row["version"] is None
        assert row["row_status"] == "stale"
    assert stale["next_action"] == "re_record_condition"
    _write(assoc_path, original)
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os.chmod(src_path, 0o600)
    changed = _matrix(world)
    assert any(row["source_status"] == "changed" for row in changed["rows"])
    src_path.write_bytes(src_original)
    os.chmod(src_path, 0o600)
    _kind, claim, old_event = _empirical(world)
    new_event = event_for(claim, previous=old_event, human=True, state="contested")
    _write(
        world["vault"] / "wiki/meta/reviews" / claim["claim_id"] / (new_event["event_id"] + ".json"),
        canonicalize(new_event),
    )
    heads_path = world["vault"] / ASSESSMENT_HEADS
    heads = json.loads(heads_path.read_bytes())
    heads["heads"][claim["claim_id"]] = {
        "event_id": new_event["event_id"],
        "event_sha256": sha(canonicalize(new_event)),
        "evidence_profile": new_event.get("evidence_profile", "legacy-v1"),
    }
    _write(heads_path, canonicalize(heads))
    claims = _matrix(world)
    assert any(row["claim_freshness"]["stale"] == 1 for row in claims["rows"])
    assert any(row["row_status"] == "stale" for row in claims["rows"])


def test_comparable_contradiction_candidate(world):
    rel, digest = _document(world)
    paper = _paper_direct(world, rel, digest)
    steps = _reported({"steps": 50, "scheduler": "ddim"}, paper)
    first_payload = valid_condition_input(world, conditions={"inference_steps": steps})
    first = _publish_exp(world, first_payload, batch="c1")
    other = valid_condition_input(world, setting_key="table3-row1-vbench-256", conditions={"inference_steps": steps})
    other["conditions"]["metrics"]["value"] = [
        dict(item) for item in other["conditions"]["metrics"]["value"]
    ]
    other["conditions"]["metrics"]["value"][0] = dict(other["conditions"]["metrics"]["value"][0])
    other["conditions"]["metrics"]["value"][0]["value"] = 200
    _publish_exp(world, other, name="c2.json", batch="c2")
    document = _matrix(world)
    pair = document["pairwise"][0]
    assert pair["verdict"] == "comparable"
    assert len(pair["contradiction_candidates"]) == 1
    assert document["next_action"] == "review_findings"
    assert document["scientific_conclusion_contradiction"] is False
    assert first["record"]["record_id"]


def test_pairwise_row_limit(world, monkeypatch):
    _publish_exp(world, batch="l1")
    _publish_exp(world, valid_condition_input(world, setting_key="table3-row1-vbench-256"), name="l2.json", batch="l2")
    second_payload, _association = _second_paper_payload(world)
    _publish_exp(world, second_payload, name="l3.json", batch="l3")
    import video_paper_wiki.experiment_matrix as experiment_matrix

    monkeypatch.setattr(experiment_matrix, "MAX_PAIRWISE_ROWS", 2)
    err = _expect(lambda: _matrix(world), "EXPERIMENT_MATRIX_LIMIT")
    assert err.details["reason"] == "pairwise_rows"
    assert err.details["row_count"] == 3
    assert err.details["limit"] == 2
    assert err.details["next_action"] == "filter_paper_id"
    filtered = build_experiment_comparison_matrix(
        vault_root=str(world["vault"]),
        paper_id=world["association"]["paper_id"],
    )
    assert filtered["row_count"] == 2
    assert MAX_PAIRWISE_ROWS == 64


def test_matrix_readonly_determinism_and_passthrough(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    _publish_exp(world, batch="n1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    first = _matrix(world)
    second = _matrix(world)
    assert canonicalize(first) == canonicalize(second)
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    for key in _walk_keys(first):
        assert key not in FORBIDDEN_KEYS
    reviews = world["vault"] / "wiki/meta/experiments/reviews"
    reviews.mkdir()
    _expect(lambda: _matrix(world), "EXPERIMENT_STORE_INVALID")
    reviews.rmdir()
    ledger = world["vault"] / CLAIM_LEDGER
    saved = ledger.read_bytes()
    ledger.unlink()
    err = _expect(lambda: _matrix(world), "DOMAIN_STORE_INVALID")
    assert err.details.get("reason") == "authority"
    _write(ledger, saved)
