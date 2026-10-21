from __future__ import annotations

import copy
import json
import os
import socket

import pytest

from tests.source_semantics_fixture import event_for, source_fixture
from tests.unit.test_domain_apply import _apply, _compile
from tests.unit.test_domain_proposal import (
    _snapshot,
    _write,
    make_world,
    valid_proposal,
)
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
from video_paper_wiki.domain_claims import build_domain_claim_coverage_view
from video_paper_wiki.domain_relations import build_domain_relation_view
from video_paper_wiki.domain_store import DomainStoreError, status_domain_store
from video_paper_wiki.domain_structure import DomainStructureError, build_domain_structure_view
from video_paper_wiki.domain_versions import (
    DomainVersionsError,
    VIEW_SCHEMA,
    _association_state,
    build_domain_source_version_view,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import association_id, extraction_descriptor, sha

UNKNOWN_PAPER = "sha256:" + "f" * 64


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _view(world, paper_id=None):
    return build_domain_source_version_view(vault_root=str(world["vault"]), paper_id=paper_id)


def _expect(fn, code):
    with pytest.raises((DomainVersionsError, DomainStoreError)) as err:
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
    assert view["source_recheck"] == "captured_markdown_digest"
    assert view["source_association_verified"] is False
    assert view["typed_fact_promotion"] == "none"
    assert view["experiment_conditions"] == "not_modeled"
    assert view["canonical_official"] is False
    assert view["current_supported_typed_fact"] is False
    assert "typed_fact_candidate" not in view
    validate_document(view, VIEW_SCHEMA)


def _assoc_path(world, association_id=None):
    aid = world["association"]["association_id"] if association_id is None else association_id
    return world["vault"] / "wiki/meta/records/source-versions" / (aid + ".json")


def _rewrite_association(world, *, title="Rewritten"):
    doc = copy.deepcopy(world["association"])
    doc["observation"]["title"] = title
    raw = canonicalize(doc)
    _write(_assoc_path(world), raw)
    return doc, raw


def _uncanonical(raw):
    payload = json.dumps(json.loads(raw), ensure_ascii=False, indent=2).encode("utf-8")
    assert payload != raw
    return payload


def _reseal_association(document):
    doc = copy.deepcopy(document)
    doc["extraction"] = extraction_descriptor(doc["observation"])
    doc["association_id"] = association_id(doc)
    return doc, canonicalize(doc)


def _plant_source_version(world, association, raw, assoc_raw):
    _write(_assoc_path(world, association["association_id"]), assoc_raw)
    raw_path = world["vault"] / association["raw"]["path"]
    if not raw_path.exists():
        _write(raw_path, raw)


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
    claims = build_domain_claim_coverage_view(vault_root=str(world["vault"]))
    assert view["basis"] == claims["basis"]
    assert view["paper_filter"] is None
    assert view["lineage_count"] == 1
    row = view["lineages"][0]
    report = first["record"]["report"]
    assoc_id = world["association"]["association_id"]
    assert row["source_association_id"] == assoc_id
    assert row["recorded_association_sha256"] == sha(world["assoc_raw"])
    assert row["association_status"] == "bound"
    assert row["association_record_sha256"] == row["recorded_association_sha256"]
    assert row["source_id"] == world["association"]["source_id"]
    assert row["version"] == {"kind": "unknown", "label": None}
    assert row["source_digest"] == report["source_digest"]
    assert row["source_status"] == "bound"
    assert row["claim_freshness"] == {"head_bound": 9, "stale": 0}
    assert row["version_status"] == "proposal_only"
    assert row["reviewed_officiality"] is None
    assert row["binding_revisions"] == 1
    assert len(row["history"]) == 1
    assert row["history"][0]["changes_from_previous"]["association_rebound"] is False
    assert len(view["versions"]) == 1
    registry = view["versions"][0]
    assert registry["record_status"] == "present"
    assert registry["status_counts"] == {
        "bound": 1,
        "changed": 0,
        "missing": 0,
        "identity_mismatch": 0,
    }
    assert registry["source_id"] == world["association"]["source_id"]
    assert registry["version"] == {"kind": "unknown", "label": None}
    assert len(view["papers"]) == 1
    paper = view["papers"][0]
    assert len(paper["versions"]) == 1
    assert len(paper["repositories"]) == 1
    assert paper["declared_version_count"] == 0
    assert paper["unlabeled_versions"] == [assoc_id]
    assert paper["search_scope"]["association_record_paths"] == [
        "wiki/meta/records/source-versions/" + assoc_id + ".json"
    ]
    assert paper["search_scope"]["claim_ledger_sha256"] == view["basis"]["claim_ledger_sha256"]
    assert view["findings"] == []
    assert view["next_action"] == "none"


def test_labeled_versions_and_cross_repo(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    _publish(world, other_proposal, name="o.json", batch="o1")
    association, raw, _authority = source_fixture(label="v2")
    assoc_raw = canonicalize(association)
    _plant_source_version(world, association, raw, assoc_raw)
    source_code = _add_code_batch(world, "src2", association=association, assoc_raw=assoc_raw)
    source_proposal = _proposal_from(world, source_code, association=association, assoc_raw=assoc_raw)
    _publish(world, source_proposal, name="src.json", batch="src2")
    view = _view(world)
    _consts(view)
    assert view["lineage_count"] == 3
    assert len(view["versions"]) == 2
    versions = {item["source_association_id"]: item for item in view["versions"]}
    later = versions[association["association_id"]]
    assert later["version"] == {"kind": "declared", "label": "v2"}
    assert later["source_id"] == association["source_id"]
    paper = view["papers"][0]
    assert paper["declared_version_count"] == 1
    original_id = world["association"]["association_id"]
    assert paper["unlabeled_versions"] == [original_id]
    original = {item["source_association_id"]: item for item in paper["versions"]}[original_id]
    assert len(original["lineage_ids"]) == 2
    assert original["repositories"] == ["other/repo", "owner/name"]
    assert view["findings"] == []


def test_association_record_rewritten(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    before_claims = canonicalize(build_domain_claim_coverage_view(vault_root=str(world["vault"])))
    _doc, new_raw = _rewrite_association(world)
    view = _view(world)
    _consts(view)
    row = view["lineages"][0]
    assert row["association_status"] == "changed"
    assert row["association_record_sha256"] == sha(new_raw)
    assert row["source_id"] is None
    assert row["version"] is None
    assert row["version_status"] == "stale"
    assert row["source_status"] == "bound"
    assert view["versions"][0]["status_counts"]["changed"] == 1
    assert view["versions"][0]["source_id"] is None
    assert view["versions"][0]["version"] is None
    assert view["papers"][0]["versions"][0]["association_counts"]["changed"] == 1
    changed = [item for item in view["findings"] if item["kind"] == "association_changed"]
    assert len(changed) == 1
    assert changed[0]["subject"] == world["association"]["association_id"]
    assert view["next_action"] == "review_findings"
    after_claims = canonicalize(build_domain_claim_coverage_view(vault_root=str(world["vault"])))
    assert after_claims == before_claims
    status = status_domain_store(vault_root=str(world["vault"]))
    assert all(item["freshness"] == "head_bound" for item in status["lineages"][0]["claims"])


def test_rebind_divergence_and_history(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    new_raw = _uncanonical(world["assoc_raw"])
    _write(_assoc_path(world), new_raw)
    doc = world["association"]
    other_code = _add_code_batch(
        world, "repo2", repository="Other/Repo", association=doc, assoc_raw=new_raw
    )
    other_proposal = _proposal_from(
        world, other_code, association=doc, assoc_raw=new_raw, repository="Other/Repo"
    )
    second = _publish(world, other_proposal, name="o.json", batch="o1")
    mixed = _view(world)
    first_row = next(
        row for row in mixed["lineages"] if row["lineage_id"] == first["record"]["lineage_id"]
    )
    second_row = next(
        row for row in mixed["lineages"] if row["lineage_id"] == second["record"]["lineage_id"]
    )
    assert first_row["association_status"] == "changed"
    assert second_row["association_status"] == "bound"
    assert second_row["recorded_association_sha256"] == sha(new_raw)
    assert second_row["source_id"] is not None
    assert second_row["version"] is not None
    registry = mixed["versions"][0]
    assert len(registry["recorded_association_sha256s"]) == 2
    assert registry["status_counts"] == {
        "bound": 1,
        "changed": 1,
        "missing": 0,
        "identity_mismatch": 0,
    }
    assert registry["source_id"] is None
    assert registry["version"] is None
    kinds = {item["kind"]: item for item in mixed["findings"]}
    assert set(kinds) == {"association_changed", "association_binding_divergence"}
    assert kinds["association_changed"]["lineage_ids"] == [first["record"]["lineage_id"]]
    assert set(kinds["association_binding_divergence"]["lineage_ids"]) == {
        first["record"]["lineage_id"],
        second["record"]["lineage_id"],
    }
    history_before = canonicalize(first_row["history"][0])
    rebind_code = _add_code_batch(world, "rebind", association=doc, assoc_raw=new_raw)
    successor = _proposal_from(world, rebind_code, association=doc, assoc_raw=new_raw)
    _publish(
        world,
        successor,
        name="succ.json",
        batch="succ",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
    )
    later = _view(world)
    rebound = next(
        row for row in later["lineages"] if row["lineage_id"] == first["record"]["lineage_id"]
    )
    assert len(rebound["history"]) == 2
    assert rebound["history"][1]["changes_from_previous"]["association_rebound"] is True
    assert rebound["binding_revisions"] == 2
    assert rebound["association_status"] == "bound"
    assert len(later["versions"][0]["recorded_association_sha256s"]) == 1
    assert later["findings"] == []
    assert later["next_action"] == "none"
    assert canonicalize(rebound["history"][0]) == history_before


def test_association_missing(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    assoc_id = world["association"]["association_id"]
    record_rel = "wiki/meta/records/source-versions/" + assoc_id + ".json"
    _assoc_path(world).unlink()
    view = _view(world)
    row = view["lineages"][0]
    assert row["association_status"] == "missing"
    assert row["association_record_sha256"] is None
    assert row["source_id"] is None
    assert row["version"] is None
    assert row["version_status"] == "stale"
    assert view["versions"][0]["record_status"] == "missing"
    assert record_rel in view["papers"][0]["search_scope"]["association_record_paths"]
    missing = [item for item in view["findings"] if item["kind"] == "association_missing"]
    assert len(missing) == 1
    assert missing[0]["subject"] == assoc_id
    assert view["next_action"] == "review_findings"


def test_identity_mismatch(world):
    mutated = copy.deepcopy(world["association"])
    mutated["observation"]["title"] = "Rewritten"
    resealed, mismatch_raw = _reseal_association(mutated)
    assert resealed["association_id"] != world["association"]["association_id"]
    binder = copy.deepcopy(world["association"])
    binder_id = binder["association_id"]
    _write(_assoc_path(world, binder_id), mismatch_raw)
    code = _add_code_batch(world, "mis", association=binder, assoc_raw=mismatch_raw)
    proposal = _proposal_from(world, code, association=binder, assoc_raw=mismatch_raw)
    _publish(world, proposal, name="m.json", batch="mis1")
    view = _view(world)
    row = view["lineages"][0]
    assert row["association_status"] == "identity_mismatch"
    assert row["source_id"] is None
    assert row["version"] is None
    assert row["version_status"] == "stale"
    mismatch = [item for item in view["findings"] if item["kind"] == "association_identity_mismatch"]
    assert len(mismatch) == 1
    assert mismatch[0]["subject"] == binder_id


def test_source_changed_and_missing(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    before_r5 = build_domain_relation_view(vault_root=str(world["vault"]))["lineages"][0][
        "evidence_freshness"
    ]
    before_r7 = canonicalize(build_domain_claim_coverage_view(vault_root=str(world["vault"])))
    source_path = world["vault"] / world["association"]["raw"]["path"]
    original = source_path.read_bytes()
    flipped = bytearray(original)
    flipped[-1] ^= 1
    _write(source_path, bytes(flipped))
    changed = _view(world)
    row = changed["lineages"][0]
    assert row["source_status"] == "changed"
    assert row["association_status"] == "bound"
    assert row["version_status"] == "stale"
    findings = [item for item in changed["findings"] if item["kind"] == "source_changed"]
    assert len(findings) == 1
    assert (
        build_domain_relation_view(vault_root=str(world["vault"]))["lineages"][0]["evidence_freshness"]
        == before_r5
    )
    assert canonicalize(build_domain_claim_coverage_view(vault_root=str(world["vault"]))) == before_r7
    source_path.unlink()
    missing = _view(world)
    assert missing["lineages"][0]["source_status"] == "missing"
    missing_findings = [item for item in missing["findings"] if item["kind"] == "source_missing"]
    assert len(missing_findings) == 1
    assert (
        build_domain_relation_view(vault_root=str(world["vault"]))["lineages"][0]["evidence_freshness"]
        == before_r5
    )
    assert canonicalize(build_domain_claim_coverage_view(vault_root=str(world["vault"]))) == before_r7


def test_version_label_collision(world):
    first_assoc, first_raw, _authority = source_fixture(label="v2")
    first_assoc_raw = canonicalize(first_assoc)
    _plant_source_version(world, first_assoc, first_raw, first_assoc_raw)
    first_code = _add_code_batch(world, "v2a", association=first_assoc, assoc_raw=first_assoc_raw)
    first_proposal = _proposal_from(
        world, first_code, association=first_assoc, assoc_raw=first_assoc_raw
    )
    _publish(world, first_proposal, name="v2a.json", batch="v2a")
    one = _view(world)
    assert [item for item in one["findings"] if item["kind"] == "version_label_collision"] == []
    second_assoc, second_raw, _ignored = source_fixture(
        label="v2", text="Different synthetic evidence."
    )
    second_assoc_raw = canonicalize(second_assoc)
    _plant_source_version(world, second_assoc, second_raw, second_assoc_raw)
    second_code = _add_code_batch(
        world, "v2b", repository="Other/Repo", association=second_assoc, assoc_raw=second_assoc_raw
    )
    second_proposal = _proposal_from(
        world,
        second_code,
        association=second_assoc,
        assoc_raw=second_assoc_raw,
        repository="Other/Repo",
    )
    _publish(world, second_proposal, name="v2b.json", batch="v2b")
    view = _view(world)
    assert view["papers"][0]["declared_version_count"] == 2
    collision = [item for item in view["findings"] if item["kind"] == "version_label_collision"]
    assert len(collision) == 1
    assert collision[0]["subject"] == world["association"]["paper_id"] + "|v2"
    assert len(collision[0]["lineage_ids"]) == 2
    assert view["next_action"] == "review_findings"


def test_review_echo(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    _accept(world, first, batch="acc")
    accepted = _view(world)
    row = accepted["lineages"][0]
    assert row["version_status"] == "reviewed_accepted"
    assert row["reviewed_officiality"] == "official"
    assert accepted["canonical_official"] is False
    assert accepted["current_supported_typed_fact"] is False
    assert accepted["source_association_verified"] is False
    assert "typed_fact_candidate" not in accepted
    contest_code = _add_code_batch(world, "c2", repository="Contest/Repo")
    contest_proposal = _proposal_from(world, contest_code, repository="Contest/Repo")
    contested_data = _publish(world, contest_proposal, name="c.json", batch="c2")
    _accept(world, contested_data, batch="c2r", decision="contested")
    contested = next(
        item
        for item in _view(world)["lineages"]
        if item["lineage_id"] == contested_data["record"]["lineage_id"]
    )
    assert contested["version_status"] == "reviewed_contested"
    reject_code = _add_code_batch(world, "r2", repository="Reject/Repo")
    reject_proposal = _proposal_from(world, reject_code, repository="Reject/Repo")
    rejected_data = _publish(world, reject_proposal, name="r.json", batch="r2")
    _accept(world, rejected_data, batch="r2r", decision="rejected")
    rejected = next(
        item
        for item in _view(world)["lineages"]
        if item["lineage_id"] == rejected_data["record"]["lineage_id"]
    )
    assert rejected["version_status"] == "reviewed_rejected"


def test_claim_stale_without_findings(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
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
    stale = _view(world)
    row = stale["lineages"][0]
    assert row["claim_freshness"]["stale"] == 1
    assert row["version_status"] == "stale"
    assert row["association_status"] == "bound"
    assert row["source_status"] == "bound"
    assert stale["findings"] == []
    assert stale["next_action"] == "re_record_annotation"


def test_structure_orthogonal(world, monkeypatch):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    before = canonicalize(_view(world))
    import video_paper_wiki.domain_proposal as domain_proposal

    monkeypatch.setattr(domain_proposal, "read_projection_resource_bytes", lambda *_a, **_k: None)
    with pytest.raises(DomainStructureError) as err:
        build_domain_structure_view(vault_root=str(world["vault"]))
    assert err.value.code == "DOMAIN_STRUCTURE_TAXONOMY_UNAVAILABLE"
    unchanged = _view(world)
    assert canonicalize(unchanged) == before


def test_shape_failures(world):
    raw = world["assoc_raw"]
    association = world["association"]
    report = {
        "paper_id": association["paper_id"],
        "source_association": {
            "association_id": association["association_id"],
            "sha256": sha(raw),
        },
        "source_digest": {
            "path": association["raw"]["path"],
            "sha256": association["raw"]["sha256"],
            "size_bytes": association["raw"]["size_bytes"],
        },
    }
    broken = b"{"
    shape_report = {
        "paper_id": association["paper_id"],
        "source_association": {
            "association_id": association["association_id"],
            "sha256": sha(broken),
        },
        "source_digest": dict(report["source_digest"]),
    }
    err = _expect(
        lambda: _association_state(broken, shape_report, association["association_id"]),
        "DOMAIN_VERSIONS_VIEW_INVALID",
    )
    assert err.details["reason"] == "association_shape"
    binding_report = {
        "paper_id": report["paper_id"],
        "source_association": dict(report["source_association"]),
        "source_digest": dict(report["source_digest"]),
    }
    binding_report["source_digest"]["sha256"] = "0" * 64
    err = _expect(
        lambda: _association_state(raw, binding_report, association["association_id"]),
        "DOMAIN_VERSIONS_VIEW_INVALID",
    )
    assert err.details["reason"] == "association_binding"
    assert _association_state(None, report, association["association_id"]) == (
        "missing",
        None,
        None,
    )
    changed_doc = copy.deepcopy(association)
    changed_doc["observation"]["title"] = "Rewritten"
    changed_raw = canonicalize(changed_doc)
    status, doc, record_sha = _association_state(
        changed_raw, report, association["association_id"]
    )
    assert status == "changed"
    assert doc is None
    assert record_sha == sha(changed_raw)


def test_paper_filter_empty_store_and_invalid(world):
    empty = _view(world)
    _consts(empty)
    assert empty["lineage_count"] == 0
    assert empty["lineages"] == []
    assert empty["versions"] == []
    assert empty["papers"] == []
    assert empty["findings"] == []
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
    assert all(paper_id in item["paper_ids"] for item in filtered["versions"])
    err = _expect(lambda: _view(world, paper_id=UNKNOWN_PAPER), "DOMAIN_VERSIONS_PAPER_UNKNOWN")
    assert err.details["next_action"] == "check_paper_id"
    assert err.details["known_paper_count"] == 1
    assert err.exit_code == 2
    invalid = _expect(lambda: _view(world, paper_id=""), "DOMAIN_VERSIONS_INVALID")
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
    assoc_path = _assoc_path(world)
    payload = assoc_path.read_bytes()
    assoc_path.unlink()
    os.symlink("other.json", assoc_path)
    linked = _expect(lambda: _view(world), "DOMAIN_STORE_CHANGED")
    assert linked.code.startswith("DOMAIN_STORE_")
    assoc_path.unlink()
    _write(assoc_path, payload)
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
    import video_paper_wiki.domain_versions as domain_versions

    original = domain_versions._claim_freshness

    def mutating(item, authority):
        path = _assoc_path(world)
        path.write_bytes(path.read_bytes())
        os.chmod(path, 0o600)
        return original(item, authority)

    monkeypatch.setattr(domain_versions, "_claim_freshness", mutating)
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
