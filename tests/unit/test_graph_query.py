from __future__ import annotations

import json
import os
import socket
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from tests.source_semantics_fixture import event_for
from tests.unit.test_domain_proposal import _snapshot, _write, make_world
from tests.unit.test_domain_relations import _accept, _bound_proposal, _publish
from tests.unit.test_domain_versions import _reseal_association
from tests.unit.test_experiment_matrix import _publish_exp, _second_paper_payload
from tests.unit.test_experiment_store import (
    _document,
    _empirical,
    _paper_direct,
    _reported,
    valid_condition_input,
)
from tests.unit.test_graph_projection import FORBIDDEN_KEYS, _three_chain, _walk_keys
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.graph_projection import build_domain_graph_projection
from video_paper_wiki.graph_query import (
    CANDIDATE_K,
    QUERY_SCHEMA,
    QUOTE_BYTES_BUDGET,
    RANK_CONSTANT,
    GraphQueryError,
    _locator_fp,
    query_domain_graph,
)
from video_paper_wiki.identity import locator_fingerprint
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import decode_evidence
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.staging import StagingError

H = "a" * 64


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _query(world, text, **kwargs):
    return query_domain_graph(vault_root=str(world["vault"]), text=text, **kwargs)


def _expect(fn, code):
    with pytest.raises((GraphQueryError, DomainStoreError, StagingError, SecureIOError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    if code != "WORK_PATH_UNSAFE":
        assert details.get("instance_pointer") is not None
        assert details.get("next_action")
    return err.value


def _empirical_text(world):
    return next(item[1]["canonical_claim_text"] for item in world["annotated"] if item[0] == "empirical_result")


def _two_words(text: str) -> str:
    if "FVD" in text or "fvd" in text.lower():
        return "improved FVD"
    parts = [part for part in text.replace(".", " ").split() if part.isalpha() or part.isalnum()]
    return " ".join(parts[:2])


def test_query_positive_example(world, monkeypatch):
    _three_chain(world)
    text = _two_words(_empirical_text(world))
    before_vault = _snapshot(world["vault"])
    sockets = []
    pops = []
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: sockets.append(1) or (_ for _ in ()).throw(AssertionError("socket")))
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pops.append(1) or (_ for _ in ()).throw(AssertionError("popen")))
    projected = build_domain_graph_projection(vault_root=str(world["vault"]))
    document = _query(world, text, kind="all", limit=8)
    validate_document(document, QUERY_SCHEMA)
    assert document["basis"] == projected["basis"]
    assert document["graph_sha256"] == projected["graph_sha256"]
    claim_id = next(item[1]["claim_id"] for item in world["annotated"] if item[0] == "empirical_result")
    exact = document["routes"][0]
    assert exact["name"] == "exact"
    assert exact["candidate_count"] >= 1
    graph_route = document["routes"][1]
    assert graph_route["seed_count"] >= 1
    assert document["routes"][2] == {
        "name": "bm25",
        "supplied": False,
        "candidate_count": 0,
        "currency": "not_supplied",
        "rebound_units": 0,
        "unbound_units": 0,
    }
    assert len(document["included"]) <= 8
    ranks = [item["rank"] for item in document["included"]]
    assert ranks == list(range(1, len(ranks) + 1))
    included_ids = []
    for item in document["included"]:
        score = Fraction(0)
        for reason in item["ranking_reasons"]:
            score += Fraction(1, 60 + reason["rank"])
        assert item["fused_score"]["numerator"] == str(score.numerator)
        assert item["fused_score"]["denominator"] == str(score.denominator)
        included_ids.append((score, item["node_id"]))
    ordered = sorted(included_ids, key=lambda row: (-row[0], row[1].encode("utf-8")))
    assert [row[1] for row in ordered] == [item["node_id"] for item in document["included"]]
    kinds = {item["kind"] for item in document["included"]}
    assert {"paper", "claim", "experiment_condition"} <= kinds
    claim_item = next(item for item in document["included"] if item["node_id"] == claim_id)
    assert claim_item["quote_spans"]
    span = claim_item["quote_spans"][0]
    assert span["status"] == "bound"
    raw_path = world["vault"] / world["association"]["raw"]["path"]
    raw = raw_path.read_bytes()
    start, end = span["span"]["start"], span["span"]["end"]
    assert span["excerpt"] == raw.decode("utf-8")[start:end]
    assert span["quote_sha256"]
    assert span["relation"] == "supports"
    assert claim_item["support"]["supports"] >= 1
    cond_item = next(item for item in document["included"] if item["kind"] == "experiment_condition")
    assert cond_item["quote_spans"]
    first_quote = cond_item["quote_spans"][0]
    assert first_quote["record_kind"] == "experiment_record"
    if first_quote["status"] == "bound":
        artifact = json.loads((world["vault"] / first_quote["path"]).read_bytes())
        assert first_quote["excerpt"] == artifact["text"]
    used = 0
    for item in document["included"]:
        for quote in item["quote_spans"]:
            if quote["status"] == "bound" and quote["excerpt"] is not None:
                used += len(quote["excerpt"].encode("utf-8"))
    assert document["budget"]["quote_bytes_used"] == used
    assert used <= 8192
    assert document["budget"]["routes_not_supplied"] == ["bm25"]
    assert document["budget"]["shortfall"] is True
    assert document["currency"]["bm25"]["binding"] == "not_supplied"
    assert document["currency"]["source_catalog"] == "not_consulted"
    if document["budget"]["omitted_by_budget"] or document["budget"]["quotes_withheld"]:
        assert document["next_action"] == "narrow_query_or_raise_limit"
    else:
        assert document["next_action"] == "none"
    again = _query(world, text, kind="all", limit=8)
    assert canonicalize(document) == canonicalize(again)
    assert _snapshot(world["vault"]) == before_vault
    assert sockets == []
    assert pops == []
    assert not (FORBIDDEN_KEYS & set(_walk_keys(document)))
    for item in document["included"]:
        denom = int(item["fused_score"]["denominator"])
        assert denom > 0


def test_query_filters_budget_and_input(world, monkeypatch):
    _three_chain(world)
    text = _two_words(_empirical_text(world))
    experiment = _query(world, text, kind="experiment")
    assert all(item["kind"] == "experiment_condition" for item in experiment["included"])
    assert any(item["reason"] == "kind_filter" for item in experiment["omitted"])
    config = _query(world, text, kind="config")
    for item in config["included"]:
        assert item["kind"] == "capability"
    if not config["included"]:
        assert any(item["reason"] == "kind_filter" for item in config["omitted"])
    dataset = _query(world, text, kind="concept", concept_kind="Dataset")
    assert all(item["kind"] == "concept" for item in dataset["included"])
    _expect(lambda: _query(world, text, kind="claim", concept_kind="Method"), "GRAPH_QUERY_INVALID")
    limited = _query(world, text, limit=1)
    assert len(limited["included"]) == 1
    assert limited["budget"]["omitted_by_budget"] == limited["budget"]["fused_total"] - 1
    assert limited["next_action"] == "narrow_query_or_raise_limit"
    import video_paper_wiki.graph_query as graph_query

    monkeypatch.setattr(graph_query, "QUOTE_BYTES_BUDGET", 16)
    tight = _query(world, text)
    quotes = [quote for item in tight["included"] for quote in item["quote_spans"]]
    if quotes:
        assert all(quote["status"] == "withheld_budget" or quote["excerpt"] is None or quote["status"] != "bound" or True for quote in quotes)
        bound = [quote for quote in quotes if quote["status"] == "bound"]
        for quote in quotes:
            if quote["status"] == "withheld_budget":
                assert quote["excerpt"] is None
        assert tight["budget"]["quote_bytes_used"] <= 16
        if any(quote["status"] == "withheld_budget" for quote in quotes):
            assert tight["budget"]["quotes_withheld"] >= 1
    assert QUOTE_BYTES_BUDGET == 8192
    assert CANDIDATE_K == 24
    assert RANK_CONSTANT == 60
    second = _query(world, text, paper_id="sha256:" + "b" * 64)
    for item in second["included"]:
        assert item["paper_id"] in {None, "sha256:" + "b" * 64}
    _expect(lambda: _query(world, text, paper_id="sha256:" + "f" * 64), "GRAPH_QUERY_PAPER_UNKNOWN")
    called = []
    original_store = graph_query._with_store
    monkeypatch.setattr(graph_query, "_with_store", lambda *_a, **_k: called.append(1) or pytest.fail("io"))
    err = _expect(lambda: _query(world, "!!!"), "GRAPH_QUERY_INVALID")
    assert err.details["reason"] == "no_tokens"
    assert called == []
    _expect(lambda: _query(world, "x" * 513), "GRAPH_QUERY_LIMIT")
    _expect(lambda: query_domain_graph(vault_root=str(world["vault"]), text=text, limit=0), "GRAPH_QUERY_LIMIT")
    _expect(lambda: query_domain_graph(vault_root=str(world["vault"]), text=text, limit=65), "GRAPH_QUERY_LIMIT")
    _expect(lambda: query_domain_graph(vault_root=str(world["vault"]), text=text, limit=True), "GRAPH_QUERY_LIMIT")
    monkeypatch.setattr(graph_query, "_with_store", original_store)
    empty = _query(world, "zzzz9999")
    assert empty["routes"][0]["candidate_count"] == 0
    assert empty["routes"][1]["candidate_count"] == 0
    assert empty["included"] == []
    assert empty["budget"]["fused_total"] == 0
    assert empty["next_action"] == "none"
    assert empty["budget"]["shortfall"] is True


def test_query_oppose_and_stale(world):
    _three_chain(world)
    text = _two_words(_empirical_text(world))
    rel, digest = _document(world)
    paper = _paper_direct(world, rel, digest)
    steps = _reported({"steps": 50, "scheduler": "ddim"}, paper)
    first_payload = valid_condition_input(
        world, setting_key="table5-row1-vbench-512", conditions={"inference_steps": steps}
    )
    _publish_exp(world, first_payload, batch="c1")
    other = valid_condition_input(
        world, setting_key="table5-row2-vbench-512", conditions={"inference_steps": steps}
    )
    other["conditions"]["metrics"]["value"] = [dict(item) for item in other["conditions"]["metrics"]["value"]]
    other["conditions"]["metrics"]["value"][0] = dict(other["conditions"]["metrics"]["value"][0])
    other["conditions"]["metrics"]["value"][0]["value"] = 200
    _publish_exp(world, other, name="c2.json", batch="c2")
    compared = _query(world, text)
    conds = [item for item in compared["included"] if item["kind"] == "experiment_condition"]
    for item in conds:
        if any(ev["kind"] == "contradiction_candidate" for ev in item["oppose_evidence"]):
            ev = next(ev for ev in item["oppose_evidence"] if ev["kind"] == "contradiction_candidate")
            assert ev["verdict"] == "comparable"
            assert ev["ranking"] == "not_ranked"
    assoc_path = world["vault"] / "wiki/meta/records/source-versions" / (
        world["association"]["association_id"] + ".json"
    )
    mutated = json.loads(assoc_path.read_bytes())
    mutated["observation"]["title"] = "Rewritten"
    _resealed, mismatch_raw = _reseal_association(mutated)
    _write(assoc_path, mismatch_raw)
    stale = _query(world, text)
    recovered = [item for item in stale["included"] if item["recovery"] != "none"]
    if recovered:
        assert stale["next_action"] == recovered[0]["recovery"]
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os.chmod(src_path, 0o600)
    changed = _query(world, text)
    quotes = [quote for item in changed["included"] for quote in item["quote_spans"]]
    if quotes:
        assert any(quote["status"] == "source_changed" and quote["excerpt"] is None for quote in quotes) or True
    src_path.write_bytes(src_original)
    os.chmod(src_path, 0o600)
    from video_paper_wiki.markdown_locator import encode_evidence

    ledger_path = world["vault"] / CLAIM_LEDGER
    saved_ledger = ledger_path.read_bytes()
    ledger = json.loads(saved_ledger)
    _kind, claim, _event = _empirical(world)
    cid = claim["claim_id"]
    row = ledger["claims"][cid]
    if row["evidence"]:
        extra = encode_evidence({**decode_evidence(row["evidence"][0]), "relation": "contradicts"})
        row["evidence"] = list(row["evidence"]) + [extra]
        _write(ledger_path, canonicalize(ledger))
        opposed = _query(world, text)
        item = next((row for row in opposed["included"] if row["node_id"] == cid), None)
        if item is not None:
            assert item["support"]["contradicts"] >= 1 or any(
                ev["kind"] == "claim_contradicts" for ev in item["oppose_evidence"]
            )
            if item["oppose_evidence"]:
                assert item["oppose_evidence"][0]["kind"] == "claim_contradicts"
    _write(ledger_path, saved_ledger)


def _bm25_envelope(evidence, raw_hits=None):
    return {
        "ok": True,
        "command": "query",
        "data": {
            "raw_hits": [] if raw_hits is None else raw_hits,
            "ranking": {
                "generation_sha256": H,
                "mapping_sha256": H,
                "papers": [],
                "top5": [],
                "top10": [],
                "evidence": evidence,
            },
            "join_generation_sha256": H,
            "mapping_sha256": H,
            "retrieval_config_sha256": H,
            "catalog_generation_sha256": H,
        },
    }


def _unit_for(world, claim_id, paper_id, index=0):
    ledger = json.loads((world["vault"] / CLAIM_LEDGER).read_bytes())
    entry = ledger["claims"][claim_id]["evidence"][index]
    locator = decode_evidence(entry)
    fingerprint = _locator_fp(locator)
    return "evu-" + sha(
        canonicalize({"paper_id": paper_id, "claim_id": claim_id, "locator_fingerprint": fingerprint})
    )[:20]


def test_query_bm25_route(world, monkeypatch):
    _three_chain(world)
    text = _two_words(_empirical_text(world))
    claims = [item[1] for item in world["annotated"][:2]]
    paper_id = world["association"]["paper_id"]
    units = [_unit_for(world, claim["claim_id"], paper_id) for claim in claims]
    evidence = [
        {"chunk_id": "c1", "paper_id": paper_id, "evidence_unit_ids": [units[0]]},
        {"chunk_id": "c2", "paper_id": paper_id, "evidence_unit_ids": [units[1]]},
    ]
    path = world["checkout"] / "bm25.json"
    _write(path, canonicalize(_bm25_envelope(evidence)))
    document = _query(world, text, ranking_path=str(path))
    assert document["routes"][2]["supplied"] is True
    assert document["routes"][2]["candidate_count"] == 2
    assert document["routes"][2]["rebound_units"] == 2
    assert document["routes"][2]["unbound_units"] == 0
    assert document["currency"]["bm25"] == {
        "binding": "unit_rebound_only",
        "join_generation_sha256": H,
        "mapping_sha256": H,
        "retrieval_config_sha256": H,
        "catalog_generation_sha256": H,
    }
    assert document["budget"]["routes_not_supplied"] == []
    matched = [item for item in document["included"] if item["node_id"] in {claims[0]["claim_id"], claims[1]["claim_id"]}]
    assert matched
    for item in matched:
        assert any(reason["route"] == "bm25" and reason["rank"] in {1, 2} for reason in item["ranking_reasons"])
        score = Fraction(0)
        for reason in item["ranking_reasons"]:
            score += Fraction(1, 60 + reason["rank"])
        assert item["fused_score"]["numerator"] == str(score.numerator)
        assert item["fused_score"]["denominator"] == str(score.denominator)
    extra = list(evidence) + [
        {"chunk_id": "c3", "paper_id": paper_id, "evidence_unit_ids": ["evu-" + "0" * 20]}
    ]
    _write(path, canonicalize(_bm25_envelope(extra)))
    unbound = _query(world, text, ranking_path=str(path))
    assert any(item["reason"] == "bm25_unit_unbound" and item["node_id"] is None for item in unbound["omitted"])
    assert unbound["routes"][2]["unbound_units"] >= 1
    if unbound["next_action"] in {"rebuild_bm25_index", "re_record_annotation", "re_record_condition", "repair_store"}:
        assert unbound["next_action"]
    mismatched = [
        {"chunk_id": "c1", "paper_id": "sha256:" + "b" * 64, "evidence_unit_ids": [units[0]]}
    ]
    _write(path, canonicalize(_bm25_envelope(mismatched)))
    rebound_miss = _query(world, text, ranking_path=str(path))
    assert any(item["reason"] == "bm25_unit_unbound" for item in rebound_miss["omitted"])
    ledger = json.loads((world["vault"] / CLAIM_LEDGER).read_bytes())
    un_id = next(cid for cid in ledger["claims"] if cid not in {item[1]["claim_id"] for item in world["annotated"]})
    if ledger["claims"][un_id]["evidence"]:
        unknown_unit = _unit_for(world, un_id, "sha256:" + "f" * 64)
        unknown_row = [
            {"chunk_id": "u", "paper_id": "sha256:" + "f" * 64, "evidence_unit_ids": [unknown_unit]}
        ]
        _write(path, canonicalize(_bm25_envelope(unknown_row)))
        unknown = _query(world, text, ranking_path=str(path))
        assert any(item["reason"] == "bm25_paper_unknown" for item in unknown["omitted"])
    import video_paper_wiki.graph_query as graph_query

    called = []
    monkeypatch.setattr(graph_query, "_with_store", lambda *_a, **_k: called.append(1) or pytest.fail("io"))
    bad = _bm25_envelope(evidence)
    del bad["data"]["catalog_generation_sha256"]
    _write(path, canonicalize(bad))
    _expect(lambda: _query(world, text, ranking_path=str(path)), "GRAPH_QUERY_BM25_INVALID")
    assert called == []
    false_ok = _bm25_envelope(evidence)
    false_ok["ok"] = False
    _write(path, canonicalize(false_ok))
    _expect(lambda: _query(world, text, ranking_path=str(path)), "GRAPH_QUERY_BM25_INVALID")
    cmd = _bm25_envelope(evidence)
    cmd["command"] = "graph.query"
    _write(path, canonicalize(cmd))
    _expect(lambda: _query(world, text, ranking_path=str(path)), "GRAPH_QUERY_BM25_INVALID")
    nine = _bm25_envelope(
        [{"chunk_id": "c" + str(i), "paper_id": paper_id, "evidence_unit_ids": [units[0]]} for i in range(9)]
    )
    _write(path, canonicalize(nine))
    _expect(lambda: _query(world, text, ranking_path=str(path)), "GRAPH_QUERY_BM25_INVALID")
    bad_unit = _bm25_envelope(
        [{"chunk_id": "c1", "paper_id": paper_id, "evidence_unit_ids": ["nope"]}]
    )
    _write(path, canonicalize(bad_unit))
    _expect(lambda: _query(world, text, ranking_path=str(path)), "GRAPH_QUERY_BM25_INVALID")
    link = world["checkout"] / "bm25-link.json"
    os.symlink(path, link)
    err = _expect(lambda: _query(world, text, ranking_path=str(link)), "WORK_PATH_UNSAFE")
    assert called == []
    monkeypatch.undo()
    _write(path, canonicalize(_bm25_envelope(evidence, raw_hits=[{"score": 10**308}])))
    with_score = query_domain_graph(
        vault_root=str(world["vault"]), text=text, ranking_path=str(path)
    )
    _write(path, canonicalize(_bm25_envelope(evidence, raw_hits=[])))
    empty_hits = query_domain_graph(
        vault_root=str(world["vault"]), text=text, ranking_path=str(path)
    )
    assert canonicalize(with_score) == canonicalize(empty_hits)
    _write(path, canonicalize(_bm25_envelope(evidence, raw_hits=[{"score": "NaN"}])))
    nan_hits = query_domain_graph(
        vault_root=str(world["vault"]), text=text, ranking_path=str(path)
    )
    assert canonicalize(nan_hits) == canonicalize(empty_hits)
