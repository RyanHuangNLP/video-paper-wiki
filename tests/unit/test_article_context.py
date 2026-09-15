from __future__ import annotations

import json
import socket
import subprocess
from fractions import Fraction

import pytest

from tests.unit.test_article_revision import _papers, _question
from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_domain_versions import _reseal_association
from tests.unit.test_experiment_store import _status
from tests.unit.test_graph_projection import _three_chain
from tests.unit.test_graph_query import _empirical_text, _two_words
from video_paper_wiki.article_context import (
    ArticleContextError,
    EXCERPT_BYTES_BUDGET,
    MAX_EVIDENCE,
    MAX_TABLE_ROWS,
    _filter_papers,
    export_article_context,
)
from video_paper_wiki.article_store import ArticleStoreError, article_id_from_question, evidence_id_for
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.graph_projection import build_domain_graph_projection, graph_sha256
from video_paper_wiki.graph_query import RANK_CONSTANT, _exact_route, _fuse, _graph_route
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha


CONTEXT_SCHEMA = "video-paper-wiki.article-context.v1"
FORBIDDEN_KEYS = {"ranked", "winner", "score_delta", "official"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _expect(fn, code):
    with pytest.raises((ArticleContextError, ArticleStoreError, DomainStoreError, ExperimentStoreError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    if code != "WORK_PATH_UNSAFE":
        assert details.get("instance_pointer") is not None
        assert details.get("next_action")
    return err.value


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _filter_independent(nodes, edges, paper_ids):
    wanted = set(paper_ids)
    kept = {node["node_id"] for node in nodes if node.get("paper_id") in wanted}
    changed = True
    by_id = {node["node_id"]: node for node in nodes}
    while changed:
        changed = False
        for edge in edges:
            for a, b in ((edge["from_node"], edge["to_node"]), (edge["to_node"], edge["from_node"])):
                if a in kept and b not in kept:
                    other = by_id.get(b)
                    if other is not None and other.get("paper_id") is None:
                        kept.add(b)
                        changed = True
    nodes_out = [node for node in nodes if node["node_id"] in kept]
    edges_out = [edge for edge in edges if edge["from_node"] in kept and edge["to_node"] in kept]
    return nodes_out, edges_out


def test_export_positive_example(world, monkeypatch):
    _three_chain(world)
    question = _question(world)
    papers = _papers(world)
    before_vault = _snapshot(world["vault"])
    before_work = _snapshot(world["checkout"] / ".work") if (world["checkout"] / ".work").exists() else {}
    sockets = []
    pops = []
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: sockets.append(1) or (_ for _ in ()).throw(AssertionError("socket")))
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pops.append(1) or (_ for _ in ()).throw(AssertionError("popen")))
    data = export_article_context(vault_root=str(world["vault"]), question=question, paper_ids=papers)
    context = data["context"]
    validate_document(context, CONTEXT_SCHEMA)
    status = _status(world)
    assert context["basis"] == status["basis"]
    projected = build_domain_graph_projection(vault_root=str(world["vault"]))
    nodes, edges = _filter_independent(projected["nodes"], projected["edges"], papers)
    assert context["graph_sha256"] == graph_sha256(nodes, edges)
    assert context["graph_sha256"] == projected["graph_sha256"]
    assert len(context["papers"]) == 2
    kinds = {}
    for item in context["evidence"]:
        kinds.setdefault(item["kind"], []).append(item)
    ledger = json.loads((world["vault"] / CLAIM_LEDGER).read_bytes())
    assert len(kinds["claim"]) == len(ledger["claims"])
    claim = kinds["claim"][0]
    text = ledger["claims"][next(iter(ledger["claims"]))]["text"]
    # identity for a ledger claim
    sample = next(item for item in kinds["claim"])
    cid = None
    for node in projected["nodes"]:
        if node["kind"] == "claim" and evidence_id_for("claim", {"claim_id": node["node_id"]}) == sample["evidence_id"]:
            cid = node["node_id"]
            break
    assert cid is not None
    assert sample["binding"]["text_sha256"] == sha(ledger["claims"][cid]["text"].encode("utf-8"))
    assert len(kinds["claim_span"]) >= 1
    span = next(item for item in kinds["claim_span"] if item["binding"]["quote_status"] == "bound")
    assert span["binding"]["relation"] == "supports"
    path = world["vault"] / span["binding"]["path"]
    raw = path.read_bytes()
    start, end = span["binding"]["charspan"]
    assert span["excerpt"] == raw.decode()[start:end]
    assert span["excerpt_status"] == "bound"
    assert len(kinds["condition"]) == 3
    assert len(kinds["condition_value"]) == 27
    assert {item["binding"]["column"] for item in kinds["condition_value"]} == {
        "model_checkpoint",
        "parameter_count",
        "dataset_split",
        "metrics",
        "resolution",
        "frames",
        "inference_steps",
        "sampling_guidance",
        "evaluation_setup",
    }
    assert len(kinds["metric_value"]) == 3
    lineage = kinds["code_lineage"][0]
    assert lineage["binding"]["reviewed_officiality"] == "official"
    assert lineage["binding"]["relation_status"] == "reviewed_accepted"
    assert len(kinds["comparability"]) == 3
    matrix = __import__("video_paper_wiki.experiment_matrix", fromlist=["build_experiment_comparison_matrix"])
    built = matrix.build_experiment_comparison_matrix(vault_root=str(world["vault"]))
    for index, pair in enumerate(context["matrix"]["pairwise_summary"]):
        assert pair["verdict"] == built["pairwise"][index]["verdict"]
        assert pair["ranking"] == built["pairwise"][index]["ranking"]
    assert len(kinds["source_version"]) >= 1
    ids = [item["evidence_id"] for item in context["evidence"]]
    assert len(ids) == len(set(ids))
    assert all(__import__("re").fullmatch(r"aev-[0-9a-f]{20}", eid) for eid in ids)
    assert context["matrix"]["row_count"] == 3
    assert context["matrix_sha256"] == sha(canonicalize(context["matrix"]))
    assert len(context["matrix"]["cells"]) == 27
    assert len(context["matrix"]["pairwise_summary"]) == 3
    assert context["relevance"]["supplied"] is True
    assert context["relevance"]["routes"][0]["candidate_count"] >= 1
    included0 = context["relevance"]["included"][0]
    claim_node = next(node for node in projected["nodes"] if node["kind"] == "claim" and node["node_id"] == included0["node_id"])
    claim_eid = evidence_id_for("claim", {"claim_id": claim_node["node_id"]})
    assert claim_eid in included0["evidence_ids"]
    span_ids = [item["evidence_id"] for item in kinds["claim_span"] if True]
    # at least the claim id is present
    score = Fraction(included0["fused_score"]["numerator"]) / Fraction(included0["fused_score"]["denominator"])
    exact = _exact_route(nodes, context["tokens"])
    graph_hits, _seed = _graph_route(nodes, edges, exact)
    fused = _fuse({"exact": exact, "graph": graph_hits})
    top = fused[0]
    assert str(top[0].numerator) == included0["fused_score"]["numerator"]
    assert str(top[0].denominator) == included0["fused_score"]["denominator"]
    claim_ev = next(item for item in context["evidence"] if item["evidence_id"] == claim_eid)
    assert claim_ev["relevance_rank"] == 1
    used = sum(len(item["excerpt"].encode("utf-8")) for item in context["evidence"] if item["excerpt_status"] == "bound" and item["excerpt"])
    assert context["budget"]["excerpt_bytes_used"] == used
    assert context["required_roles"] == [
        "question",
        "consensus",
        "differences",
        "controversies",
        "limits",
        "unknowns",
    ]
    assert context["next_action"] == "none"
    assert "[@aev-" in data["prompt"]
    assert "question" in data["prompt"] and "consensus" in data["prompt"]
    assert "证据不足" in data["prompt"]
    assert "video-paper-wiki.article-document.v1" in data["prompt"]
    assert data["article_id"] == article_id_from_question(question, papers)
    second = export_article_context(vault_root=str(world["vault"]), question=question, paper_ids=papers)
    assert canonicalize(data) == canonicalize(second)
    assert _snapshot(world["vault"]) == before_vault
    if (world["checkout"] / ".work").exists():
        assert _snapshot(world["checkout"] / ".work") == before_work
    assert sockets == [] and pops == []
    keys = set(_walk_keys(data))
    assert not keys.intersection(FORBIDDEN_KEYS)


def test_export_boundaries(world, monkeypatch):
    _three_chain(world)
    papers = _papers(world)
    question = _question(world)
    _expect(
        lambda: export_article_context(
            vault_root=str(world["vault"]),
            question=question,
            paper_ids=["sha256:" + "c" * 64],
        ),
        "ARTICLE_CONTEXT_PAPER_UNKNOWN",
    )
    _expect(
        lambda: export_article_context(
            vault_root=str(world["vault"]),
            question=question,
            paper_ids=papers + papers[:1] + ["sha256:" + "c" * 64] * 6,
        ),
        "ARTICLE_CONTEXT_INVALID",
    )
    called = []

    def boom(*_a, **_k):
        called.append(1)
        raise AssertionError("store")

    from video_paper_wiki.article_store import _with_store as original_with

    monkeypatch.setattr("video_paper_wiki.article_store._with_store", boom)
    _expect(
        lambda: export_article_context(vault_root=str(world["vault"]), question="!!!", paper_ids=papers),
        "ARTICLE_CONTEXT_INVALID",
    )
    assert not called
    _expect(
        lambda: export_article_context(vault_root=str(world["vault"]), question="x" * 513, paper_ids=papers),
        "ARTICLE_CONTEXT_INVALID",
    )
    monkeypatch.setattr("video_paper_wiki.article_store._with_store", original_with)
    empty = export_article_context(vault_root=str(world["vault"]), question="zzzz9999", paper_ids=_papers(world))
    assert empty["context"]["relevance"]["included"] == []
    assert empty["context"]["relevance"]["routes"][0]["candidate_count"] == 0
    assert empty["context"]["relevance"]["routes"][1]["candidate_count"] == 0
    assert empty["context"]["relevance"]["supplied"] is True
    monkeypatch.setattr("video_paper_wiki.article_context.EXCERPT_BYTES_BUDGET", 16)
    withheld = export_article_context(vault_root=str(world["vault"]), question=_question(world), paper_ids=_papers(world))
    spans = [item for item in withheld["context"]["evidence"] if item["kind"] == "claim_span"]
    assert all(item["excerpt"] is None for item in spans)
    assert all(item["excerpt_status"] == "withheld_budget" for item in spans)
    assert withheld["context"]["budget"]["excerpts_withheld"] >= 1
    assert withheld["context"]["budget"]["shortfall"] is True
    monkeypatch.setattr("video_paper_wiki.article_context.EXCERPT_BYTES_BUDGET", EXCERPT_BYTES_BUDGET)
    monkeypatch.setattr("video_paper_wiki.article_context.MAX_TABLE_ROWS", 2)
    _expect(
        lambda: export_article_context(vault_root=str(world["vault"]), question=_question(world), paper_ids=_papers(world)),
        "ARTICLE_CONTEXT_LIMIT",
    )
    one = export_article_context(
        vault_root=str(world["vault"]),
        question=_question(world),
        paper_ids=[_papers(world)[1]],
    )
    assert one["context"]["matrix"]["row_count"] == 1
    monkeypatch.setattr("video_paper_wiki.article_context.MAX_TABLE_ROWS", MAX_TABLE_ROWS)
    monkeypatch.setattr("video_paper_wiki.article_context.MAX_EVIDENCE", 3)
    _expect(
        lambda: export_article_context(vault_root=str(world["vault"]), question=_question(world), paper_ids=_papers(world)),
        "ARTICLE_CONTEXT_LIMIT",
    )
    monkeypatch.setattr("video_paper_wiki.article_context.MAX_EVIDENCE", MAX_EVIDENCE)
    assoc_path = world["vault"] / "wiki/meta/records/source-versions" / (world["association"]["association_id"] + ".json")
    original = assoc_path.read_bytes()
    mutated = json.loads(original)
    mutated["observation"]["title"] = "Rewritten"
    _resealed, raw = _reseal_association(mutated)
    from tests.unit.test_domain_proposal import _write

    _write(assoc_path, raw)
    stale = export_article_context(vault_root=str(world["vault"]), question=_question(world), paper_ids=_papers(world))
    assert any(row["status"] == "stale" for row in stale["context"]["papers"])
    assert stale["context"]["next_action"] == "re_record_annotation"
    _write(assoc_path, original)
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os_chmod = __import__("os").chmod
    os_chmod(src_path, 0o600)
    changed = export_article_context(vault_root=str(world["vault"]), question=_question(world), paper_ids=_papers(world))
    assert any(
        item["kind"] == "claim_span" and item["binding"]["quote_status"] == "source_changed" and item["excerpt"] is None
        for item in changed["context"]["evidence"]
    )
    src_path.write_bytes(src_original)
    os_chmod(src_path, 0o600)
    from tests.source_semantics_fixture import event_for

    _kind, claim, old_event = next(item for item in world["annotated"] if item[0] == "empirical_result")
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
    head_stale = export_article_context(vault_root=str(world["vault"]), question=_question(world), paper_ids=_papers(world))
    stale_claim = next(
        item
        for item in head_stale["context"]["evidence"]
        if item["kind"] == "claim" and evidence_id_for("claim", {"claim_id": claim["claim_id"]}) == item["evidence_id"]
    )
    assert stale_claim["binding"]["freshness"] == "stale"
    _expect(
        lambda: export_article_context(
            vault_root=str(world["vault"]),
            article_id="art-" + "0" * 20,
            revision_id="arv-" + "0" * 20,
        ),
        "ARTICLE_UNKNOWN",
    )
    _expect(
        lambda: export_article_context(
            vault_root="/nonexistent",
            question="a",
            paper_ids=["x"],
            article_id="art-" + "0" * 20,
        ),
        "ARTICLE_CONTEXT_INVALID",
    )
    reviews = world["vault"] / "wiki/meta/experiments" / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / "x.txt").write_bytes(b"x")
    _expect(
        lambda: export_article_context(vault_root=str(world["vault"]), question=_question(world), paper_ids=_papers(world)),
        "EXPERIMENT_STORE_INVALID",
    )
    (world["vault"] / CLAIM_LEDGER).unlink()
    reviews.rename(reviews.with_name("reviews.bak"))
    _expect(
        lambda: export_article_context(vault_root=str(world["vault"]), question=_question(world), paper_ids=_papers(world)),
        "DOMAIN_STORE_INVALID",
    )
