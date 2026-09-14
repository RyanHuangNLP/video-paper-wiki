from __future__ import annotations

import json
import os
import socket

import pytest

from tests.source_semantics_fixture import event_for, source_fixture
from tests.unit.test_domain_apply import _apply, _compile
from tests.unit.test_domain_proposal import (
    CLAIM_KINDS,
    CLAIM_TEXTS,
    _snapshot,
    _write,
    make_world,
    valid_proposal,
)
from tests.unit.test_domain_relations import _bound_proposal
from tests.unit.test_domain_store import (
    LATER_AT,
    RECORDED_AT,
    _add_code_batch,
    _decision_for,
    _proposal_from,
    _record,
    _review,
    _successor_proposal,
)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_claims import (
    DomainClaimsError,
    VIEW_SCHEMA,
    _typed_row,
    _typed_rows,
    _untyped_row,
    _untyped_rows,
    build_domain_claim_coverage_view,
)
from video_paper_wiki.domain_relations import build_domain_relation_view
from video_paper_wiki.domain_store import DomainStoreError, status_domain_store
from video_paper_wiki.domain_structure import DomainStructureError, build_domain_structure_view
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha

UNKNOWN_PAPER = "sha256:" + "f" * 64
THIRD_AT = "2026-09-14T03:00:00Z"
SHAPE_HEAD = {
    "event_id": "ase-" + "a" * 20,
    "event_sha256": "0" * 64,
    "evidence_profile": "legacy-v1",
}
SHAPE_TYPED = {
    "claim_id": "clm-" + "a" * 20,
    "claim_kind": "architecture",
    "assessment": "provisional",
    "claim_text": "text",
    "evidence_fingerprint": "0" * 64,
    "assessment_head": dict(SHAPE_HEAD),
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _view(world, paper_id=None):
    return build_domain_claim_coverage_view(vault_root=str(world["vault"]), paper_id=paper_id)


def _expect(fn, code):
    with pytest.raises((DomainClaimsError, DomainStoreError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    assert details.get("instance_pointer") is not None
    assert details.get("next_action")
    return err.value


def _publish(world, proposal, *, name, batch, previous=None, recorded_at=RECORDED_AT):
    data = _record(
        world,
        proposal,
        name=name,
        previous=previous,
        recorded_at=recorded_at,
        batch=batch,
    )
    _compile(world, batch)
    _apply(world, batch)
    return data


def _accept(world, data, *, batch, officiality="official", decision="accepted"):
    review = _review(
        world,
        _decision_for(world, data, officiality=officiality, decision=decision),
        name=batch + ".json",
        batch=batch,
    )
    _compile(world, batch)
    _apply(world, batch)
    return review


def _request_basis(world, batch):
    path = world["checkout"] / ".work" / batch / "domain-publication" / "request.json"
    return json.loads(path.read_bytes())["basis"]


def _consts(view):
    assert view["schema"] == VIEW_SCHEMA
    assert view["publication"] == "unpublished"
    assert view["write_kind"] == "read_only"
    assert view["audit_coverage"] == "not_wired"
    assert view["code_freshness"] == "not_checked"
    assert view["evidence_recheck"] == "not_performed"
    assert view["typed_fact_promotion"] == "none"
    assert view["experiment_conditions"] == "not_modeled"
    assert view["canonical_official"] is False
    assert view["current_supported_typed_fact"] is False
    validate_document(view, VIEW_SCHEMA)


def _claim_of(world, kind):
    for item_kind, claim, event in world["annotated"]:
        if item_kind == kind:
            return claim, event
    raise AssertionError(kind)


def _rewrite_ledger(world, mutate):
    path = world["vault"] / CLAIM_LEDGER
    document = json.loads(path.read_bytes())
    mutate(document)
    _write(path, canonicalize(document))


def _drop_kind(proposal, kind):
    proposal["claim_annotations"] = [
        item for item in proposal["claim_annotations"] if item["claim_kind"] != kind
    ]
    return proposal


def _set_kind(proposal, claim_id, kind):
    for item in proposal["claim_annotations"]:
        if item["claim_id"] == claim_id:
            item["claim_kind"] = kind
            return proposal
    raise AssertionError(claim_id)


def test_happy_path_proposal_only(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    succ = _successor_proposal(world)
    _record(
        world,
        succ,
        name="basis.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="basis",
    )
    _compile(world, "basis")
    view = _view(world)
    _consts(view)
    assert view["basis"] == _request_basis(world, "basis")
    assert view["paper_filter"] is None
    assert view["ledger_claim_count"] == 10
    assert view["lineage_count"] == 1
    row = view["lineages"][0]
    assert row["lineage_id"] == first["record"]["lineage_id"]
    assert row["typed_claim_count"] == 9
    assert row["untyped_claim_count"] == 1
    assert row["coverage_status"] == "proposal_only"
    assert row["reviewed_officiality"] is None
    report_by_id = {
        item["claim_id"]: item for item in first["record"]["report"]["claim_annotations"]
    }
    by_id = {item["claim_id"]: item for item in row["claims"]}
    assert list(by_id) == _byte_ids(by_id)
    assert len(row["claims"]) == 9
    for kind, claim, event in world["annotated"]:
        item = by_id[claim["claim_id"]]
        assert item["claim_kind"] == kind
        assert item["freshness"] == "head_bound"
        assert item["stale_reason"] is None
        assert item["recorded_assessment"] == "provisional"
        assert item["current_assessment"] == "provisional"
        assert item["assessment_drift"] is False
        assert item["ledger_status"] == "present"
        assert item["claim_text_sha256"] == sha(CLAIM_TEXTS[kind].encode("utf-8"))
        reported = report_by_id[claim["claim_id"]]
        assert item["evidence_fingerprint"] == reported["evidence_fingerprint"]
        assert item["assessment_head"] == reported["assessment_head"]
        assert item["first_annotation_id"] == row["head_annotation_id"]
        assert item["binding_revisions"] == 1
        _ = event
        cell = row["kinds"][kind]
        assert cell["claim_ids"] == [claim["claim_id"]]
        assert cell["head_bound"] == 1
        assert cell["stale"] == 0
    extra_id = world["extra"]["claim_id"]
    assert row["untyped"][0]["claim_id"] == extra_id
    assert row["untyped"][0]["ledger_status"] == "present"
    assert row["untyped"][0]["current_assessment"] == "provisional"
    assert len(row["history"]) == 1
    assert row["history"][0]["changes_from_previous"] == {
        "claims_added": [],
        "claims_removed": [],
        "claims_retyped": [],
        "claims_rebound": [],
        "untyped_changed": False,
    }
    assert len(view["claims"]) == 9
    assert [item["claim_id"] for item in view["claims"]] == _byte_ids(
        {item["claim_id"]: item for item in view["claims"]}
    )
    for item in view["claims"]:
        assert len(item["claim_kinds"]) == 1
        assert len(item["lineage_ids"]) == 1
    assert len(view["papers"]) == 1
    paper = view["papers"][0]
    assert len(paper["source_versions"]) == 1
    assert paper["source_versions"][0]["source_digest_sha256s"] == [
        world["association"]["raw"]["sha256"]
    ]
    assert len(paper["repositories"]) == 1
    for kind in CLAIM_KINDS:
        cell = paper["kind_coverage"][kind]
        assert cell == {
            "typed_claim_count": 1,
            "lineage_count": 1,
            "head_bound": 1,
            "stale": 0,
            "coverage": "covered",
        }
    assert paper["uncovered_kinds"] == []
    assert len(paper["untyped_claims"]) == 1
    assert paper["untyped_claims"][0]["claim_id"] == extra_id
    assert paper["search_scope"]["lineage_ids"] == [row["lineage_id"]]
    assert paper["search_scope"]["head_annotation_ids"] == [row["head_annotation_id"]]
    assert paper["search_scope"]["claim_ledger_sha256"] == view["basis"]["claim_ledger_sha256"]
    assert paper["search_scope"]["ledger_claim_count"] == 10
    assert view["findings"] == []
    assert view["next_action"] == "none"
    assert paper["finding_count"] == 0


def _byte_ids(mapping):
    return sorted(mapping, key=lambda item: item.encode("utf-8"))


def test_uncovered_kind_carries_search_scope(world):
    proposal = _drop_kind(valid_proposal(world), "license")
    _publish(world, proposal, name="g.json", batch="g1")
    view = _view(world)
    _consts(view)
    row = view["lineages"][0]
    assert row["kinds"]["license"] == {"claim_ids": [], "head_bound": 0, "stale": 0}
    paper = view["papers"][0]
    assert paper["kind_coverage"]["license"]["coverage"] == "uncovered"
    assert paper["uncovered_kinds"] == ["license"]
    untyped_ids = {item["claim_id"] for item in paper["untyped_claims"]}
    license_claim, _event = _claim_of(world, "license")
    assert untyped_ids == {license_claim["claim_id"], world["extra"]["claim_id"]}
    assert paper["search_scope"]["lineage_ids"]
    assert paper["search_scope"]["head_annotation_ids"]
    assert view["findings"] == []
    assert view["next_action"] == "none"


def test_review_history_retype_and_remove(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    review = _accept(world, first, batch="r1", officiality="official")
    viewed = _view(world)
    _consts(viewed)
    row = viewed["lineages"][0]
    assert row["coverage_status"] == "reviewed_accepted"
    assert row["reviewed_officiality"] == "official"
    assert viewed["canonical_official"] is False
    assert viewed["current_supported_typed_fact"] is False
    assert b'"typed_fact_candidate"' not in canonicalize(viewed)
    architecture, _event = _claim_of(world, "architecture")
    succ = _set_kind(_successor_proposal(world), architecture["claim_id"], "implementation")
    second = _publish(
        world,
        succ,
        name="s.json",
        batch="s1",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
    )
    after = _view(world)
    row = after["lineages"][0]
    assert len(row["history"]) == 2
    second_changes = row["history"][1]["changes_from_previous"]
    assert second_changes["claims_retyped"] == [architecture["claim_id"]]
    assert second_changes["claims_added"] == []
    assert second_changes["claims_removed"] == []
    assert second_changes["claims_rebound"] == []
    assert second_changes["untyped_changed"] is False
    assert row["kinds"]["architecture"]["claim_ids"] == []
    assert len(row["kinds"]["implementation"]["claim_ids"]) == 2
    typed = next(item for item in row["claims"] if item["claim_id"] == architecture["claim_id"])
    assert typed["first_annotation_id"] == first["record"]["annotation_id"]
    assert typed["binding_revisions"] == 2
    assert after["papers"][0]["uncovered_kinds"] == ["architecture"]
    registry = next(item for item in after["claims"] if item["claim_id"] == architecture["claim_id"])
    assert registry["claim_kinds"] == ["implementation"]
    assert after["findings"] == []
    assert row["coverage_status"] == "proposal_only"
    assert row["reviewed_officiality"] is None
    review_path = (
        world["vault"]
        / "wiki/meta/domain/reviews"
        / first["record"]["lineage_id"]
        / (review["record"]["review_id"] + ".json")
    )
    assert review_path.is_file()
    ablation, _ablation_event = _claim_of(world, "ablation")
    third_proposal = _drop_kind(_successor_proposal(world), "ablation")
    _set_kind(third_proposal, architecture["claim_id"], "implementation")
    _publish(
        world,
        third_proposal,
        name="t.json",
        batch="t1",
        previous=second["record"]["annotation_id"],
        recorded_at=THIRD_AT,
    )
    third = _view(world)
    row = third["lineages"][0]
    assert len(row["history"]) == 3
    third_changes = row["history"][2]["changes_from_previous"]
    assert third_changes["claims_removed"] == [ablation["claim_id"]]
    assert third_changes["untyped_changed"] is True


def test_contested_and_rejected(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    _accept(world, first, batch="c1", decision="contested")
    contested = next(
        row for row in _view(world)["lineages"] if row["lineage_id"] == first["record"]["lineage_id"]
    )
    assert contested["coverage_status"] == "reviewed_contested"
    other_code = _add_code_batch(world, "rej", repository="Reject/Repo")
    other_p = _proposal_from(world, other_code, repository="Reject/Repo")
    second = _publish(world, other_p, name="r.json", batch="rej1")
    _accept(world, second, batch="rej1r", decision="rejected")
    rejected = next(
        row for row in _view(world)["lineages"] if row["lineage_id"] == second["record"]["lineage_id"]
    )
    assert rejected["coverage_status"] == "reviewed_rejected"


def test_cross_repo_and_source_versions(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    _publish(world, other_proposal, name="o.json", batch="o1")
    association, raw, _authority = source_fixture(label="v2")
    assoc_raw = canonicalize(association)
    _write(
        world["vault"] / "wiki/meta/records/source-versions" / (association["association_id"] + ".json"),
        assoc_raw,
    )
    raw_path = world["vault"] / association["raw"]["path"]
    if not raw_path.exists():
        _write(raw_path, raw)
    source_code = _add_code_batch(world, "src2", association=association, assoc_raw=assoc_raw)
    source_proposal = _proposal_from(world, source_code, association=association, assoc_raw=assoc_raw)
    _publish(world, source_proposal, name="src.json", batch="src2")
    view = _view(world)
    _consts(view)
    assert view["lineage_count"] == 3
    assert len(view["papers"]) == 1
    paper = view["papers"][0]
    assert len(paper["source_versions"]) == 2
    versions = {item["source_association_id"]: item for item in paper["source_versions"]}
    original = versions[world["association"]["association_id"]]
    later = versions[association["association_id"]]
    assert original["repositories"] == ["other/repo", "owner/name"]
    assert later["repositories"] == ["owner/name"]
    assert len(original["lineage_ids"]) == 2
    assert len(later["lineage_ids"]) == 1
    assert len(paper["repositories"]) == 2
    for kind in CLAIM_KINDS:
        assert paper["kind_coverage"][kind]["lineage_count"] == 3
        assert paper["kind_coverage"][kind]["typed_claim_count"] == 1
    for item in view["claims"]:
        assert len(item["lineage_ids"]) == 3
        assert len(item["claim_kinds"]) == 1
    assert view["findings"] == []


def test_claim_kind_divergence(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    training, _event = _claim_of(world, "training")
    _set_kind(other_proposal, training["claim_id"], "reproducibility")
    _publish(world, other_proposal, name="o.json", batch="o1")
    view = _view(world)
    findings = [row for row in view["findings"] if row["kind"] == "claim_kind_divergence"]
    assert len(findings) == 1
    assert findings[0]["subject"] == training["claim_id"]
    assert len(findings[0]["lineage_ids"]) == 2
    registry = next(item for item in view["claims"] if item["claim_id"] == training["claim_id"])
    assert registry["claim_kinds"] == ["reproducibility", "training"]
    training_count = view["papers"][0]["kind_coverage"]["training"]["lineage_count"]
    other_counts = {
        view["papers"][0]["kind_coverage"][kind]["lineage_count"]
        for kind in CLAIM_KINDS
        if kind != "training"
    }
    assert training_count == 1
    assert other_counts == {2}
    assert view["next_action"] == "review_findings"
    assert view["papers"][0]["finding_count"] == 1


def test_claim_binding_divergence(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    before = _view(world)
    history_before = canonicalize(before["lineages"][0]["history"])
    kind, claim, old_event = world["annotated"][0]
    _ = kind
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
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    for item in other_proposal["claim_annotations"]:
        if item["claim_id"] == claim["claim_id"]:
            item["assessment_head"] = {
                "event_id": new_event["event_id"],
                "event_sha256": sha(canonicalize(new_event)),
                "evidence_profile": new_event.get("evidence_profile", "legacy-v1"),
            }
    _publish(world, other_proposal, name="o.json", batch="o1")
    view = _view(world)
    first_row = next(
        row for row in view["lineages"] if row["lineage_id"] == first["record"]["lineage_id"]
    )
    second_row = next(
        row for row in view["lineages"] if row["lineage_id"] != first["record"]["lineage_id"]
    )
    stale_item = next(item for item in first_row["claims"] if item["claim_id"] == claim["claim_id"])
    bound_item = next(item for item in second_row["claims"] if item["claim_id"] == claim["claim_id"])
    assert stale_item["freshness"] == "stale"
    assert stale_item["stale_reason"] == "assessment_head_changed"
    assert first_row["coverage_status"] == "stale"
    assert bound_item["freshness"] == "head_bound"
    registry = next(item for item in view["claims"] if item["claim_id"] == claim["claim_id"])
    assert len(registry["event_sha256s"]) == 2
    assert registry["head_bound"] == 1
    assert registry["stale"] == 1
    findings = [row for row in view["findings"] if row["kind"] == "claim_binding_divergence"]
    assert len(findings) == 1
    assert view["next_action"] == "review_findings"
    assert canonicalize(first_row["history"]) == history_before


def test_assessment_drift(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    kind, claim, _event = world["annotated"][0]
    _ = kind

    def mutate(document):
        document["claims"][claim["claim_id"]]["assessment"] = "unsupported"

    _rewrite_ledger(world, mutate)
    view = _view(world)
    item = next(row for row in view["lineages"][0]["claims"] if row["claim_id"] == claim["claim_id"])
    assert item["freshness"] == "head_bound"
    assert item["current_assessment"] == "unsupported"
    assert item["assessment_drift"] is True
    assert view["lineages"][0]["coverage_status"] == "proposal_only"
    findings = [row for row in view["findings"] if row["kind"] == "claim_assessment_drift"]
    assert len(findings) == 1
    assert findings[0]["subject"] == claim["claim_id"]
    assert view["next_action"] == "review_findings"
    status = status_domain_store(vault_root=str(world["vault"]))
    status_item = next(
        row for row in status["lineages"][0]["claims"] if row["claim_id"] == claim["claim_id"]
    )
    assert status_item["freshness"] == "head_bound"


def test_untyped_claim_missing(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    extra_id = world["extra"]["claim_id"]

    def mutate(document):
        del document["claims"][extra_id]

    _rewrite_ledger(world, mutate)
    view = _view(world)
    assert view["lineages"][0]["untyped"][0]["ledger_status"] == "missing"
    assert view["lineages"][0]["untyped"][0]["current_assessment"] is None
    assert view["papers"][0]["untyped_claims"][0]["ledger_status"] == "missing"
    findings = [row for row in view["findings"] if row["kind"] == "untyped_claim_missing"]
    assert len(findings) == 1
    assert findings[0]["subject"] == world["association"]["paper_id"] + "|" + extra_id
    assert view["lineages"][0]["typed_claim_count"] == 9
    assert all(item["ledger_status"] == "present" for item in view["lineages"][0]["claims"])


def test_claim_stale(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    before = _view(world)
    history_before = canonicalize(before["lineages"][0]["history"])
    kind, claim, old_event = world["annotated"][0]
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
    stale = _view(world)
    row = stale["lineages"][0]
    assert row["claim_freshness"]["stale"] == 1
    assert row["kinds"][kind]["stale"] == 1
    assert stale["papers"][0]["kind_coverage"][kind]["stale"] == 1
    assert row["coverage_status"] == "stale"
    assert stale["findings"] == []
    assert stale["next_action"] == "re_record_annotation"
    assert canonicalize(row["history"]) == history_before


def test_relations_and_structure_orthogonal(world, monkeypatch):
    proposal, _planted = _bound_proposal(world)
    _publish(world, proposal, name="g.json", batch="g1")
    before = canonicalize(_view(world))
    _write(world["vault"] / world["page_rel"], world["page_body"] + b"changed\n")
    related = build_domain_relation_view(vault_root=str(world["vault"]))
    assert related["lineages"][0]["evidence_freshness"] == "stale"
    after = _view(world)
    assert canonicalize(after) == before
    assert after["evidence_recheck"] == "not_performed"
    import video_paper_wiki.domain_proposal as domain_proposal

    monkeypatch.setattr(domain_proposal, "read_projection_resource_bytes", lambda *_a, **_k: None)
    with pytest.raises(DomainStructureError) as err:
        build_domain_structure_view(vault_root=str(world["vault"]))
    assert err.value.code == "DOMAIN_STRUCTURE_TAXONOMY_UNAVAILABLE"
    unchanged = _view(world)
    assert canonicalize(unchanged) == before


def test_shape_failures():
    unknown = dict(SHAPE_TYPED)
    unknown["claim_kind"] = "unknown_kind"
    err = _expect(
        lambda: _typed_row(unknown, {}, "/lineages/0/claims/0"),
        "DOMAIN_CLAIMS_VIEW_INVALID",
    )
    assert err.details["reason"] == "claim_shape"
    maybe = dict(SHAPE_TYPED)
    maybe["assessment"] = "maybe"
    err = _expect(
        lambda: _typed_row(maybe, {}, "/lineages/0/claims/0"),
        "DOMAIN_CLAIMS_VIEW_INVALID",
    )
    assert err.details["reason"] == "claim_shape"
    missing_head = dict(SHAPE_TYPED)
    del missing_head["assessment_head"]
    err = _expect(
        lambda: _typed_row(missing_head, {}, "/lineages/0/claims/0"),
        "DOMAIN_CLAIMS_VIEW_INVALID",
    )
    assert err.details["reason"] == "claim_shape"
    err = _expect(
        lambda: _typed_rows([dict(SHAPE_TYPED), dict(SHAPE_TYPED)], {}, "/lineages/0/claims"),
        "DOMAIN_CLAIMS_VIEW_INVALID",
    )
    assert err.details["reason"] == "claim_shape"
    untyped = {
        "claim_id": SHAPE_TYPED["claim_id"],
        "claim_text": "text",
        "assessment": "provisional",
    }
    err = _expect(
        lambda: _untyped_rows([untyped], {SHAPE_TYPED["claim_id"]}, {}, "/lineages/0/untyped"),
        "DOMAIN_CLAIMS_VIEW_INVALID",
    )
    assert err.details["reason"] == "untyped_shape"
    err = _expect(
        lambda: _untyped_row({"claim_id": SHAPE_TYPED["claim_id"]}, {}, "/lineages/0/untyped/0"),
        "DOMAIN_CLAIMS_VIEW_INVALID",
    )
    assert err.details["reason"] == "untyped_shape"


def test_paper_filter_empty_store_and_invalid(world):
    empty = _view(world)
    _consts(empty)
    assert empty["lineage_count"] == 0
    assert empty["lineages"] == []
    assert empty["claims"] == []
    assert empty["papers"] == []
    assert empty["findings"] == []
    assert empty["ledger_claim_count"] == 10
    assert empty["next_action"] == "none"
    assert set(empty["basis"]) == {
        "domain_store_inventory_sha256",
        "claim_ledger_sha256",
        "assessment_heads_sha256",
    }
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    paper_id = world["association"]["paper_id"]
    filtered = _view(world, paper_id=paper_id)
    assert filtered["paper_filter"] == paper_id
    assert filtered["lineage_count"] == 1
    assert filtered["papers"][0]["paper_id"] == paper_id
    assert all(row["paper_id"] == paper_id for row in filtered["lineages"])
    assert all(paper_id in item["paper_ids"] for item in filtered["claims"])
    assert filtered["ledger_claim_count"] == 10
    err = _expect(lambda: _view(world, paper_id=UNKNOWN_PAPER), "DOMAIN_CLAIMS_PAPER_UNKNOWN")
    assert err.details["next_action"] == "check_paper_id"
    assert err.details["known_paper_count"] == 1
    assert err.exit_code == 2
    invalid = _expect(lambda: _view(world, paper_id=""), "DOMAIN_CLAIMS_INVALID")
    assert invalid.details["instance_pointer"] == "/paper_id"
    assert invalid.details["next_action"] == "repair_input"
    (world["vault"] / CLAIM_LEDGER).unlink()
    missing = _expect(lambda: _view(world), "DOMAIN_STORE_INVALID")
    assert missing.details.get("reason") == "authority"


def test_store_structure_errors(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    extra = world["vault"] / "wiki/meta/domain" / "extra.json"
    _write(extra, b"{}\n")
    _expect(lambda: _view(world), "DOMAIN_STORE_INVALID")
    extra.unlink()
    heads = world["vault"] / "wiki/meta/domain/heads.json"
    _write(heads, canonicalize({"schema": "video-paper-wiki.domain-heads.v1", "heads": {}}))
    _expect(lambda: _view(world), "DOMAIN_STORE_HEADS_MISMATCH")
    _write(heads, canonicalize(first["heads"]))
    link = (
        world["vault"]
        / "wiki/meta/domain/annotations"
        / first["record"]["lineage_id"]
        / ("dan-" + "c" * 20 + ".json")
    )
    os.symlink(first["record"]["annotation_id"] + ".json", link)
    _expect(lambda: _view(world), "DOMAIN_STORE_INVALID")


def test_changed_during_claim_freshness(world, monkeypatch):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    import video_paper_wiki.domain_claims as domain_claims

    original = domain_claims._claim_freshness

    def mutating(item, authority):
        path = world["vault"] / CLAIM_LEDGER
        path.write_bytes(path.read_bytes())
        os.chmod(path, 0o600)
        return original(item, authority)

    monkeypatch.setattr(domain_claims, "_claim_freshness", mutating)
    err = _expect(lambda: _view(world), "DOMAIN_STORE_CHANGED")
    assert err.exit_code == 75


def test_readonly_determinism_and_zero_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    first = _view(world)
    second = _view(world)
    assert canonicalize(first) == canonicalize(second)
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
