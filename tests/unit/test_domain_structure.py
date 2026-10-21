from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from tests.source_semantics_fixture import event_for, source_fixture
from tests.unit.test_domain_apply import _apply, _compile
from tests.unit.test_domain_proposal import (
    CLAIM_KINDS,
    CONCEPT_KINDS,
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
from video_paper_wiki.domain_proposal import CAPABILITY_NAMES
from video_paper_wiki.domain_relations import build_domain_relation_view
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.domain_structure import (
    DomainStructureError,
    VIEW_SCHEMA,
    _capability_row,
    _concept_row,
    build_domain_structure_view,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = REPO_ROOT / "taxonomy" / "v1.json"
UNKNOWN_PAPER = "sha256:" + "f" * 64
THIRD_AT = "2026-09-14T03:00:00Z"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _view(world, paper_id=None):
    return build_domain_structure_view(vault_root=str(world["vault"]), paper_id=paper_id)


def _expect(fn, code):
    with pytest.raises((DomainStructureError, DomainStoreError)) as err:
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
    assert view["taxonomy_promotion"] == "none"
    assert view["canonical_official"] is False
    assert view["current_supported_typed_fact"] is False
    validate_document(view, VIEW_SCHEMA)


def _set_evaluation_present(proposal):
    training = next(item for item in proposal["capabilities"] if item["name"] == "training")
    evaluation = next(item for item in proposal["capabilities"] if item["name"] == "evaluation")
    evaluation["status"] = "present"
    evaluation["declaration_kind"] = "code"
    evaluation["locators"] = [dict(training["locators"][0])]
    evaluation["absence_scope"] = None
    return proposal


def _set_training_absent(proposal):
    evaluation = next(item for item in proposal["capabilities"] if item["name"] == "evaluation")
    training = next(item for item in proposal["capabilities"] if item["name"] == "training")
    training["status"] = "absent"
    training["declaration_kind"] = None
    training["locators"] = []
    training["absence_scope"] = dict(evaluation["absence_scope"])
    return proposal


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
    assert view["taxonomy_basis"]["resource"] == "taxonomy/v1.json"
    assert view["taxonomy_basis"]["sha256"] == sha(TAXONOMY.read_bytes())
    assert view["taxonomy_basis"]["pair_count"] == 20
    assert view["paper_filter"] is None
    assert view["lineage_count"] == 1
    row = view["lineages"][0]
    assert row["lineage_id"] == first["record"]["lineage_id"]
    assert [item["concept_kind"] for item in row["concepts"]] == list(CONCEPT_KINDS)
    by_key = {item["term_key"]: item for item in row["concepts"]}
    assert by_key["tax:backbone:dit"]["taxonomy_check"] == "known"
    assert by_key["tax:evaluation/dataset/benchmark:vbench"]["taxonomy_check"] == "known"
    tax_rows = [item for item in row["concepts"] if item["term_status"] == "taxonomy_v1"]
    prop_rows = [item for item in row["concepts"] if item["term_status"] == "normalization_proposal"]
    assert len(tax_rows) == 7
    assert all(item["taxonomy_check"] == "known" for item in tax_rows)
    assert len(prop_rows) == 1
    assert prop_rows[0]["term_key"] == "prop:custom-clip-score"
    assert prop_rows[0]["taxonomy_check"] == "not_applicable"
    caps = row["capabilities"]
    assert caps["training"]["status"] == "present"
    assert caps["training"]["declaration_kind"] == "code"
    assert caps["training"]["evidence_basis"] == "code_located"
    assert caps["training"]["locator_paths"] == ["src.py"]
    assert caps["inference"]["status"] == "partial"
    assert caps["inference"]["declaration_kind"] == "config"
    assert caps["inference"]["evidence_basis"] == "code_located"
    assert caps["inference"]["locator_paths"] == ["config.json"]
    assert caps["data"]["status"] == "unverified"
    assert caps["data"]["declaration_kind"] == "readme_only"
    assert caps["data"]["evidence_basis"] == "declared_only"
    assert caps["evaluation"]["status"] == "absent"
    assert caps["evaluation"]["declaration_kind"] is None
    assert caps["evaluation"]["evidence_basis"] == "absent_with_scope"
    assert caps["evaluation"]["search_scope"] == {
        "commit": row["commit"],
        "tree_prefix": "eval",
        "search_patterns": ["eval", "benchmark"],
        "observed_file_count": 3,
    }
    assert caps["checkpoints"]["status"] == "unverified"
    assert caps["checkpoints"]["declaration_kind"] is None
    assert caps["checkpoints"]["evidence_basis"] == "unverified"
    assert all(caps[name]["code_recheck"] == "not_checked" for name in CAPABILITY_NAMES)
    assert row["claims_by_kind"] == {kind: {"head_bound": 1, "stale": 0} for kind in CLAIM_KINDS}
    assert row["unannotated_count"] == 1
    assert row["structure_status"] == "proposal_only"
    assert row["reviewed_officiality"] is None
    assert len(row["history"]) == 1
    assert row["history"][0]["changes_from_previous"] == {
        "commit_changed": False,
        "concepts_changed": False,
        "claims_changed": False,
        "capabilities_changed": [],
    }
    assert len(view["concepts"]) == 8
    assert len(view["papers"]) == 1
    paper = view["papers"][0]
    assert paper["concept_kind_counts"] == {kind: 1 for kind in CONCEPT_KINDS}
    assert paper["capability_coverage"]["training"] == {"present": 1, "partial": 0, "absent": 0, "unverified": 0}
    assert paper["capability_coverage"]["inference"] == {"present": 0, "partial": 1, "absent": 0, "unverified": 0}
    assert paper["capability_coverage"]["data"] == {"present": 0, "partial": 0, "absent": 0, "unverified": 1}
    assert paper["capability_coverage"]["evaluation"] == {"present": 0, "partial": 0, "absent": 1, "unverified": 0}
    assert paper["capability_coverage"]["checkpoints"] == {"present": 0, "partial": 0, "absent": 0, "unverified": 1}
    assert view["findings"] == []
    assert view["next_action"] == "none"
    assert paper["finding_count"] == 0


def test_review_history_and_capability_change(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    review = _accept(world, first, batch="r1", officiality="official")
    viewed = _view(world)
    _consts(viewed)
    row = viewed["lineages"][0]
    assert row["structure_status"] == "reviewed_accepted"
    assert row["reviewed_officiality"] == "official"
    assert viewed["canonical_official"] is False
    assert viewed["current_supported_typed_fact"] is False
    succ = _successor_proposal(world)
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
    assert second_changes["concepts_changed"] is True
    assert second_changes["claims_changed"] is False
    assert second_changes["commit_changed"] is False
    assert second_changes["capabilities_changed"] == []
    assert row["structure_status"] == "proposal_only"
    assert row["reviewed_officiality"] is None
    registry = {item["term_key"]: item for item in after["concepts"]}
    assert registry["tax:backbone:dit"]["surface_forms"] == ["changed-surface"]
    review_path = (
        world["vault"]
        / "wiki/meta/domain/reviews"
        / first["record"]["lineage_id"]
        / (review["record"]["review_id"] + ".json")
    )
    assert review_path.is_file()
    third_proposal = _set_training_absent(_successor_proposal(world))
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
    assert row["history"][2]["changes_from_previous"]["capabilities_changed"] == ["training"]
    assert row["capabilities"]["training"]["evidence_basis"] == "absent_with_scope"


def test_contested_and_rejected(world):
    first = _publish(world, valid_proposal(world), name="g.json", batch="g1")
    _accept(world, first, batch="c1", decision="contested")
    contested = next(
        row for row in _view(world)["lineages"] if row["lineage_id"] == first["record"]["lineage_id"]
    )
    assert contested["structure_status"] == "reviewed_contested"
    other_code = _add_code_batch(world, "rej", repository="Reject/Repo")
    other_p = _proposal_from(world, other_code, repository="Reject/Repo")
    second = _publish(world, other_p, name="r.json", batch="rej1")
    _accept(world, second, batch="rej1r", decision="rejected")
    rejected = next(
        row for row in _view(world)["lineages"] if row["lineage_id"] == second["record"]["lineage_id"]
    )
    assert rejected["structure_status"] == "reviewed_rejected"


def test_cross_repo_capability_divergence(world):
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
    third = _publish(world, source_proposal, name="src.json", batch="src2")
    view = _view(world)
    _consts(view)
    assert view["lineage_count"] == 3
    assert len(view["papers"]) == 1
    paper = view["papers"][0]
    assert len(paper["repositories"]) == 2
    assert len(paper["source_association_ids"]) == 2
    assert paper["capability_coverage"]["training"]["present"] == 3
    assert view["findings"] == []
    changed = _set_evaluation_present(
        _proposal_from(world, source_code, association=association, assoc_raw=assoc_raw)
    )
    _publish(
        world,
        changed,
        name="src-eval.json",
        batch="src2b",
        previous=third["record"]["annotation_id"],
        recorded_at=LATER_AT,
    )
    later = _view(world)
    findings = later["findings"]
    assert len(findings) == 1
    row = findings[0]
    assert row["kind"] == "capability_divergence"
    paper_id = world["association"]["paper_id"]
    assert row["subject"] == paper_id + "|owner/name|evaluation"
    assert len(row["lineage_ids"]) == 2
    assert later["next_action"] == "review_findings"
    assert later["papers"][0]["finding_count"] == 1
    other_eval = next(
        item["capability_status"]["evaluation"]
        for repo in later["papers"][0]["repositories"]
        if repo["repository"] == "other/repo"
        for item in repo["lineages"]
    )
    owner_eval = {
        item["capability_status"]["evaluation"]
        for repo in later["papers"][0]["repositories"]
        if repo["repository"] == "owner/name"
        for item in repo["lineages"]
    }
    assert other_eval == "absent"
    assert owner_eval == {"absent", "present"}


def test_concept_kind_divergence(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    other_proposal["concepts"][-1]["concept_kind"] = "Benchmark"
    _publish(world, other_proposal, name="o.json", batch="o1")
    view = _view(world)
    findings = [row for row in view["findings"] if row["kind"] == "concept_kind_divergence"]
    assert len(findings) == 1
    assert findings[0]["subject"] == "prop:custom-clip-score"
    registry = {item["term_key"]: item for item in view["concepts"]}
    assert registry["prop:custom-clip-score"]["concept_kinds"] == ["Benchmark", "EvaluationMetric"]
    keys = [(row["kind"], row["subject"], row["lineage_ids"]) for row in view["findings"]]
    assert keys == sorted(
        keys,
        key=lambda item: (
            item[0].encode("utf-8"),
            item[1].encode("utf-8"),
            [lid.encode("utf-8") for lid in item[2]],
        ),
    )


def test_surface_form_divergence(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    other_proposal["concepts"][-1]["normalization_proposal"]["proposed_slug"] = "custom-clipscore"
    _publish(world, other_proposal, name="o.json", batch="o1")
    view = _view(world)
    findings = [row for row in view["findings"] if row["kind"] == "surface_form_divergence"]
    assert len(findings) == 1
    assert findings[0]["subject"] == "EvaluationMetric:CustomClipScore"
    prop_keys = [item["term_key"] for item in view["concepts"] if item["term_key"].startswith("prop:")]
    assert set(prop_keys) == {"prop:custom-clip-score", "prop:custom-clipscore"}
    assert view["taxonomy_promotion"] == "none"


def test_taxonomy_term_unknown(world, monkeypatch):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    import video_paper_wiki.domain_structure as domain_structure

    original = domain_structure._taxonomy_pairs

    def patched():
        return {pair for pair in original() if pair != ("backbone", "dit")}

    monkeypatch.setattr(domain_structure, "_taxonomy_pairs", patched)
    view = _view(world)
    by_key = {item["term_key"]: item for item in view["lineages"][0]["concepts"]}
    assert by_key["tax:backbone:dit"]["taxonomy_check"] == "unknown"
    findings = [row for row in view["findings"] if row["kind"] == "taxonomy_term_unknown"]
    assert len(findings) == 1
    assert findings[0]["subject"] == "tax:backbone:dit"
    keys = [(row["kind"], row["subject"], row["lineage_ids"]) for row in view["findings"]]
    assert keys == sorted(
        keys,
        key=lambda item: (
            item[0].encode("utf-8"),
            item[1].encode("utf-8"),
            [lid.encode("utf-8") for lid in item[2]],
        ),
    )


def test_taxonomy_unavailable_and_shape_failures(world, monkeypatch):
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    import video_paper_wiki.domain_proposal as domain_proposal

    monkeypatch.setattr(domain_proposal, "read_projection_resource_bytes", lambda *_a, **_k: None)
    err = _expect(lambda: _view(world), "DOMAIN_STRUCTURE_TAXONOMY_UNAVAILABLE")
    assert err.exit_code == 2
    assert err.details["instance_pointer"] == "/taxonomy_basis"
    assert err.details["next_action"] == "repair_install"
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    pairs = {("backbone", "dit")}
    both = _expect(
        lambda: _concept_row(
            {
                "concept_kind": "Method",
                "surface_form": "dit",
                "taxonomy_ref": {"axis": "backbone", "slug": "dit"},
                "normalization_proposal": {
                    "surface_form": "dit",
                    "proposed_slug": "dit",
                    "reason": "both sides filled",
                },
                "term_status": "taxonomy_v1",
            },
            pairs,
            "/lineages/0/concepts/0",
        ),
        "DOMAIN_STRUCTURE_VIEW_INVALID",
    )
    assert both.details["reason"] == "concept_shape"
    absent = _expect(
        lambda: _capability_row(
            {
                "name": "evaluation",
                "status": "absent",
                "declaration_kind": None,
                "locators": [],
                "absence_scope": None,
            },
            "/lineages/0/capabilities/evaluation",
        ),
        "DOMAIN_STRUCTURE_VIEW_INVALID",
    )
    assert absent.details["reason"] == "capability_shape"
    present = _expect(
        lambda: _capability_row(
            {
                "name": "training",
                "status": "present",
                "declaration_kind": "code",
                "locators": [],
                "absence_scope": None,
            },
            "/lineages/0/capabilities/training",
        ),
        "DOMAIN_STRUCTURE_VIEW_INVALID",
    )
    assert present.details["reason"] == "capability_shape"


def test_claim_stale(world):
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
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
    stale = _view(world)
    row = stale["lineages"][0]
    assert row["claim_freshness"]["stale"] == 1
    assert row["claims_by_kind"][kind]["stale"] == 1
    assert row["structure_status"] == "stale"
    assert stale["findings"] == []
    assert stale["next_action"] == "re_record_annotation"
    assert canonicalize(row["history"]) == history_before


def test_relations_orthogonal(world):
    proposal, _planted = _bound_proposal(world)
    _publish(world, proposal, name="g.json", batch="g1")
    before = canonicalize(_view(world))
    assert _view(world)["lineages"][0]["structure_status"] == "proposal_only"
    _write(world["vault"] / world["page_rel"], world["page_body"] + b"changed\n")
    related = build_domain_relation_view(vault_root=str(world["vault"]))
    assert related["lineages"][0]["evidence_freshness"] == "stale"
    after = _view(world)
    assert canonicalize(after) == before
    assert after["evidence_recheck"] == "not_performed"
    assert after["lineages"][0]["structure_status"] == "proposal_only"


def test_paper_filter_empty_store_and_invalid(world):
    empty = _view(world)
    _consts(empty)
    assert empty["lineage_count"] == 0
    assert empty["lineages"] == []
    assert empty["concepts"] == []
    assert empty["papers"] == []
    assert empty["findings"] == []
    assert empty["next_action"] == "none"
    assert set(empty["basis"]) == {
        "domain_store_inventory_sha256",
        "claim_ledger_sha256",
        "assessment_heads_sha256",
    }
    assert empty["taxonomy_basis"]["pair_count"] == 20
    _publish(world, valid_proposal(world), name="g.json", batch="g1")
    paper_id = world["association"]["paper_id"]
    filtered = _view(world, paper_id=paper_id)
    assert filtered["paper_filter"] == paper_id
    assert filtered["lineage_count"] == 1
    assert filtered["papers"][0]["paper_id"] == paper_id
    assert all(row["paper_id"] == paper_id for row in filtered["lineages"])
    err = _expect(lambda: _view(world, paper_id=UNKNOWN_PAPER), "DOMAIN_STRUCTURE_PAPER_UNKNOWN")
    assert err.details["next_action"] == "check_paper_id"
    assert err.details["known_paper_count"] == 1
    assert err.exit_code == 2
    invalid = _expect(lambda: _view(world, paper_id=""), "DOMAIN_STRUCTURE_INVALID")
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
    import video_paper_wiki.domain_structure as domain_structure

    original = domain_structure._claim_freshness

    def mutating(item, authority):
        path = world["vault"] / CLAIM_LEDGER
        path.write_bytes(path.read_bytes())
        os.chmod(path, 0o600)
        return original(item, authority)

    monkeypatch.setattr(domain_structure, "_claim_freshness", mutating)
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
