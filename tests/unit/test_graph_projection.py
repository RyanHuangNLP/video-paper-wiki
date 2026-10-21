from __future__ import annotations

import json
import os
import socket
import subprocess

import pytest

from tests.source_semantics_fixture import event_for
from tests.unit.test_domain_apply import _apply, _compile
from tests.unit.test_domain_proposal import _snapshot, _write, make_world, valid_proposal
from tests.unit.test_domain_relations import _accept, _bind_a, _bound_proposal, _publish
from tests.unit.test_domain_store import _add_code_batch, _decision_for, _proposal_from, _record, _review
from tests.unit.test_domain_versions import _reseal_association
from tests.unit.test_experiment_matrix import _publish_exp, _second_paper_payload
from tests.unit.test_experiment_store import _status, valid_condition_input
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.graph_projection import (
    ENDPOINT_TYPES,
    MAX_NODES,
    MAX_PAIRWISE_ROWS,
    PROJECTION_SCHEMA,
    GraphProjectionError,
    _assemble_graph,
    build_domain_graph_projection,
    graph_sha256,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_catalog_projection import _pointer
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha

FORBIDDEN_KEYS = {"ranked", "better", "winner", "score_delta", "official"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _project(world, paper_id=None):
    return build_domain_graph_projection(vault_root=str(world["vault"]), paper_id=paper_id)


def _expect(fn, code):
    with pytest.raises((GraphProjectionError, DomainStoreError, ExperimentStoreError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    assert details.get("next_action")
    if code != "WORK_PATH_UNSAFE":
        assert details.get("instance_pointer") is not None
    return err.value


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _three_chain(world):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    _accept(world, first, batch="r1", officiality="official")
    a = _publish_exp(world, batch="ea")
    other = valid_condition_input(world, setting_key="table3-row1-vbench-256")
    b = _publish_exp(world, other, name="b.json", batch="eb")
    second_payload, association = _second_paper_payload(world)
    c = _publish_exp(world, second_payload, name="c.json", batch="ec")
    return first, a, b, c, association, planted


def _by_kind(document, kind):
    return [node for node in document["nodes"] if node["kind"] == kind]


def test_projection_positive_example(world, monkeypatch):
    first, _a, _b, _c, _association, _planted = _three_chain(world)
    before_vault = _snapshot(world["vault"])
    before_work = _snapshot(world["checkout"] / ".work") if (world["checkout"] / ".work").exists() else {}
    sockets = []
    pops = []

    def boom_socket(*_args, **_kwargs):
        sockets.append(1)
        raise AssertionError("socket")

    def boom_popen(*_args, **_kwargs):
        pops.append(1)
        raise AssertionError("popen")

    monkeypatch.setattr(socket, "socket", boom_socket)
    monkeypatch.setattr(subprocess, "Popen", boom_popen)
    document = _project(world)
    validate_document(document, PROJECTION_SCHEMA)
    status = _status(world)
    assert document["basis"] == status["basis"]
    assert document["known_paper_count"] == 2
    assert document["node_counts"]["paper"] == 2
    assert document["node_counts"]["source_version"] >= 1
    ledger = json.loads((world["vault"] / CLAIM_LEDGER).read_bytes())
    assert document["node_counts"]["claim"] == len(ledger["claims"])
    proposal = valid_proposal(world)
    keys = set()
    for item in proposal["concepts"]:
        if item["taxonomy_ref"] is not None:
            keys.add((item["concept_kind"], item["taxonomy_ref"]["axis"] + "/" + item["taxonomy_ref"]["slug"]))
        else:
            keys.add((item["concept_kind"], "proposal:" + item["surface_form"].casefold()))
    assert document["node_counts"]["concept"] == len(keys)
    assert document["node_counts"]["code_lineage"] == 1
    assert document["node_counts"]["capability"] == 5
    handoffs = first["record"]["report"]["code_refs"]["handoffs"]
    assert document["node_counts"]["code_ref"] == len(handoffs)
    assert document["node_counts"]["experiment_condition"] == 3
    assert document["edge_counts"]["comparability"] == 1
    kinds = {node["node_id"]: node["kind"] for node in document["nodes"]}
    for edge in document["edges"]:
        assert kinds[edge["from_node"]] == ENDPOINT_TYPES[edge["kind"]][0]
        assert kinds[edge["to_node"]] == ENDPOINT_TYPES[edge["kind"]][1]
    records = set(json.loads((world["vault"] / CLAIM_LEDGER).read_bytes())["claims"])
    store_ids = set()
    domain = world["vault"] / "wiki/meta/domain"
    if domain.exists():
        for path in domain.rglob("*.json"):
            if path.name == "heads.json":
                continue
            store_ids.add(path.stem)
    experiments = world["vault"] / "wiki/meta/experiments/records"
    if experiments.exists():
        for path in experiments.rglob("*.json"):
            store_ids.add(path.stem)
    assoc_ids = {
        path.stem
        for path in (world["vault"] / "wiki/meta/records/source-versions").glob("*.json")
    }
    for node in document["nodes"]:
        for source in node["sources"]:
            rid = source["record_id"]
            assert rid in store_ids or rid in records or rid in assoc_ids or rid.startswith("sva-")
    unannotated = [
        node
        for node in _by_kind(document, "claim")
        if node["attributes"]["freshness"] == "unannotated"
    ]
    assert unannotated
    for node in unannotated:
        assert node["paper_id"] is None
    evidence = [edge for edge in document["edges"] if edge["kind"] == "claim_evidence"]
    assert evidence
    assert any(
        edge["attributes"]["quote_status"] == "bound" and edge["attributes"]["relation"] == "supports"
        for edge in evidence
    )
    lineage = _by_kind(document, "code_lineage")[0]
    assert lineage["attributes"]["reviewed_officiality"] == "official"
    assert lineage["attributes"]["relation_status"] == "reviewed_accepted"
    names = {node["attributes"]["name"] for node in _by_kind(document, "capability")}
    assert names == {"training", "inference", "data", "evaluation", "checkpoints"}
    for node in _by_kind(document, "code_ref"):
        assert node["attributes"]["verification"] == "recorded_only"
    conditions = {row["condition_id"]: row for row in status["conditions"]}
    for node in _by_kind(document, "experiment_condition"):
        row = conditions[node["node_id"]]
        for key, value in node["attributes"].items():
            if key in row:
                assert value == row[key]
    assert document["graph_sha256"] == graph_sha256(document["nodes"], document["edges"])
    again = _project(world)
    assert canonicalize(document) == canonicalize(again)
    assert _snapshot(world["vault"]) == before_vault
    if (world["checkout"] / ".work").exists():
        assert _snapshot(world["checkout"] / ".work") == before_work
    assert sockets == []
    assert pops == []
    assert not (FORBIDDEN_KEYS & set(_walk_keys(document)))
    assert document["next_action"] != "filter_paper_id"


def test_projection_filter_and_limits(world, monkeypatch):
    _three_chain(world)
    first_paper = world["association"]["paper_id"]
    filtered = _project(world, paper_id=first_paper)
    assert filtered["node_counts"]["paper"] == 1
    assert filtered["node_counts"]["experiment_condition"] == 2
    assert filtered["node_counts"]["concept"] >= 1
    assert filtered["edge_counts"]["comparability"] == 1
    papers = {node["node_id"] for node in _by_kind(filtered, "paper")}
    assert papers == {first_paper}
    err = _expect(lambda: _project(world, paper_id="sha256:" + "f" * 64), "GRAPH_PROJECTION_PAPER_UNKNOWN")
    assert err.details["known_paper_count"] == 2
    _expect(lambda: _project(world, paper_id=""), "GRAPH_PROJECTION_INVALID")
    import video_paper_wiki.graph_projection as graph_projection

    monkeypatch.setattr(graph_projection, "MAX_PAIRWISE_ROWS", 1)
    err = _expect(lambda: _project(world), "GRAPH_PROJECTION_LIMIT")
    assert err.details["reason"] == "pairwise_rows"
    assert err.details["paper_id"] == first_paper
    assert err.details["row_count"] == 2
    assert err.details["limit"] == 1
    assert err.details["next_action"] == "filter_paper_id"
    second = _project(world, paper_id="sha256:" + "b" * 64)
    assert second["node_counts"]["paper"] == 1
    assert second["node_counts"]["experiment_condition"] == 1
    assert MAX_PAIRWISE_ROWS == 64
    monkeypatch.setattr(graph_projection, "MAX_PAIRWISE_ROWS", 64)
    full = _project(world)
    monkeypatch.setattr(graph_projection, "MAX_NODES", len(full["nodes"]) - 1)
    err = _expect(lambda: _project(world), "GRAPH_PROJECTION_LIMIT")
    assert err.details["reason"] == "nodes"
    assert MAX_NODES == 65536


def test_projection_endpoint_and_source_reachability(world, monkeypatch):
    _three_chain(world)
    import video_paper_wiki.graph_projection as graph_projection

    monkeypatch.setitem(graph_projection.ENDPOINT_TYPES, "code_relation", ("paper", "claim"))
    err = _expect(lambda: _project(world), "GRAPH_PROJECTION_INVALID")
    assert err.details["reason"] == "endpoint_type"
    monkeypatch.setitem(graph_projection.ENDPOINT_TYPES, "code_relation", ("paper", "code_lineage"))
    original = graph_projection._assemble_graph

    def missing(*args, **kwargs):
        graph = original(*args, **kwargs)
        graph.edges[0]["to_node"] = "clm-" + "f" * 20
        return graph

    monkeypatch.setattr(graph_projection, "_assemble_graph", missing)
    err = _expect(lambda: _project(world), "GRAPH_PROJECTION_INVALID")
    assert err.details["reason"] == "endpoint_missing"
    monkeypatch.setattr(graph_projection, "_assemble_graph", original)

    def unresolvable(*args, **kwargs):
        graph = original(*args, **kwargs)
        node = next(iter(graph.nodes.values()))
        node["sources"][0]["record_id"] = "dan-" + "0" * 20
        return graph

    monkeypatch.setattr(graph_projection, "_assemble_graph", unresolvable)
    err = _expect(lambda: _project(world), "GRAPH_PROJECTION_INVALID")
    assert err.details["reason"] == "source_unresolvable"


def test_projection_staleness_and_passthrough(world, monkeypatch):
    _three_chain(world)
    assoc_path = world["vault"] / "wiki/meta/records/source-versions" / (
        world["association"]["association_id"] + ".json"
    )
    original = assoc_path.read_bytes()
    mutated = json.loads(original)
    mutated["observation"]["title"] = "Rewritten"
    _resealed, mismatch_raw = _reseal_association(mutated)
    _write(assoc_path, mismatch_raw)
    stale = _project(world)
    changed = [
        node
        for node in _by_kind(stale, "source_version")
        if node["node_id"] == world["association"]["association_id"]
    ]
    assert changed
    assert changed[0]["attributes"]["association_status"] == "changed"
    assert any(node["status"] == "stale" for node in _by_kind(stale, "code_lineage"))
    assert any(node["status"] == "stale" for node in _by_kind(stale, "experiment_condition"))
    assert any(node["status"] == "stale" for node in _by_kind(stale, "paper"))
    assert stale["next_action"] == "re_record_annotation"
    _write(assoc_path, original)
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os.chmod(src_path, 0o600)
    source_changed = _project(world)
    assert any(
        node["attributes"]["source_status"] == "changed" for node in _by_kind(source_changed, "source_version")
    )
    assert any(
        edge["attributes"].get("quote_status") == "source_changed"
        for edge in source_changed["edges"]
        if edge["kind"] == "claim_evidence"
    )
    src_path.write_bytes(src_original)
    os.chmod(src_path, 0o600)
    from video_paper_wiki.markdown_locator import decode_evidence, encode_evidence

    ledger_path = world["vault"] / CLAIM_LEDGER
    ledger = json.loads(ledger_path.read_bytes())
    cid = next(iter(ledger["claims"]))
    row = ledger["claims"][cid]
    if row["evidence"]:
        locator = decode_evidence(row["evidence"][0])
        digest = locator["excerpt_sha256"]
        locator["excerpt_sha256"] = ("0" if digest[0] != "0" else "1") + digest[1:]
        row["evidence"][0] = encode_evidence(locator)
        _write(ledger_path, canonicalize(ledger))
        excerpt = _project(world)
        assert any(
            edge["attributes"].get("quote_status") == "excerpt_changed"
            for edge in excerpt["edges"]
            if edge["kind"] == "claim_evidence"
        )
        assert any(
            node["attributes"]["freshness"] == "stale"
            for node in _by_kind(excerpt, "claim")
            if node["node_id"] == cid
        )
    _kind, claim, old_event = next(
        item for item in world["annotated"] if item[0] == "empirical_result"
    )
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
    head_stale = _project(world)
    stale_claim = next(node for node in _by_kind(head_stale, "claim") if node["node_id"] == claim["claim_id"])
    assert stale_claim["attributes"]["freshness"] == "stale"
    assert any(
        edge["freshness"] == "stale"
        for edge in head_stale["edges"]
        if edge["kind"] == "claim_about" and edge["from_node"] == claim["claim_id"]
    )
    assert head_stale["next_action"] == "re_record_annotation"


def test_projection_lineage_missing_conflicts_and_empty(world, monkeypatch):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    _accept(world, first, batch="r1", officiality="official")
    binding = {
        "lineage_id": first["record"]["lineage_id"],
        "annotation_id": first["record"]["annotation_id"],
        "repository": first["record"]["report"]["repository"],
        "commit": first["record"]["report"]["commit"],
    }
    payload = valid_condition_input(world, code_binding=binding)
    _publish_exp(world, payload, batch="bind")
    import shutil

    domain = world["vault"] / "wiki/meta/domain"
    if domain.exists():
        shutil.rmtree(domain)
    missing = _project(world)
    conds = _by_kind(missing, "experiment_condition")
    assert conds
    assert all(node["attributes"]["binding_status"] == "lineage_missing" for node in conds)
    assert missing["edge_counts"]["condition_code_binding"] == 0
    assert missing["next_action"] == "re_record_condition"
    empty = make_world(world["checkout"] / "empty-root", monkeypatch)
    vacant = build_domain_graph_projection(vault_root=str(empty["vault"]))
    validate_document(vacant, PROJECTION_SCHEMA)
    assert vacant["known_paper_count"] == 0
    assert vacant["node_counts"]["paper"] == 0
    assert vacant["node_counts"]["claim"] >= 1
    assert vacant["next_action"] == "none"
    kinds = {node["kind"] for node in vacant["nodes"]}
    assert kinds <= {"claim", "source_version"}
    notes = world["vault"] / "wiki/meta/domain/notes.txt"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("nope", encoding="utf-8")
    os.chmod(notes, 0o600)
    _expect(lambda: _project(world), "DOMAIN_STORE_INVALID")
    notes.unlink()
    reviews = world["vault"] / "wiki/meta/experiments/reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    _expect(lambda: _project(world), "EXPERIMENT_STORE_INVALID")
    reviews.rmdir()
    ledger = world["vault"] / CLAIM_LEDGER
    saved = ledger.read_bytes()
    ledger.unlink()
    _expect(lambda: _project(world), "DOMAIN_STORE_INVALID")
    _write(ledger, saved)
    from video_paper_wiki.receipt_audit import _Snapshot

    def boom(*_args, **_kwargs):
        raise OSError("changed")

    monkeypatch.setattr(_Snapshot, "read_optional", boom)
    err = _expect(lambda: _project(world), "DOMAIN_STORE_CHANGED")
    assert err.exit_code == 75


def test_projection_resolve_conflicts(world):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    _accept(world, first, batch="r1", officiality="official")
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    _bind_a(other_proposal, planted)
    other = _publish(world, other_proposal, name="o.json", batch="o1")
    _accept(world, other, batch="o1r", officiality="official")
    document = _project(world)
    assert document["next_action"] == "resolve_conflicts"
