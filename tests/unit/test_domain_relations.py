from __future__ import annotations

import json
import os
import socket

import pytest

from tests.code_proof_public_fixture import README_BODY
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
from video_paper_wiki.domain_relations import DomainRelationError, VIEW_SCHEMA, build_domain_relation_view
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha

A_TEXT = "our implementation is available at"
UNKNOWN_PAPER = "sha256:" + "f" * 64


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _view(world, paper_id=None):
    return build_domain_relation_view(vault_root=str(world["vault"]), paper_id=paper_id)


def _expect(fn, code):
    with pytest.raises((DomainRelationError, DomainStoreError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    assert details.get("instance_pointer") is not None
    assert details.get("next_action")
    return err.value


def _plant_document(world, *, text=A_TEXT, page=1):
    document = {
        "texts": [
            {"text": "padding", "prov": [{"page_no": 1}]},
            {"text": text, "prov": [{"page_no": page}]},
        ]
    }
    raw = canonicalize(document)
    digest = sha(raw)
    rel = ".raw/derived/" + digest + "/document.json"
    _write(world["vault"] / rel, raw)
    return {
        "rel": rel,
        "raw": raw,
        "artifact_sha256": digest,
        "text_sha256": sha(text.encode("utf-8")),
        "ref": "#/texts/1",
        "page": page,
        "text": text,
    }


def _bind_a(proposal, planted, **overrides):
    locator = proposal["relation"]["evidence_classes"]["A"]["locators"][0]
    locator["artifact_path"] = planted["rel"]
    locator["artifact_sha256"] = planted["artifact_sha256"]
    locator["text_sha256"] = planted["text_sha256"]
    locator["ref"] = planted["ref"]
    locator["page"] = planted["page"]
    locator.update(overrides)
    return proposal


def _with_c(proposal):
    proposal["relation"]["evidence_classes"]["C"] = {
        "present": True,
        "locators": [
            {
                "kind": "repository_text",
                "path": "README.md",
                "commit": proposal["commit"],
                "local_digest": {"sha256": sha(README_BODY), "size_bytes": len(README_BODY)},
                "fragment": {"start": 0, "end": len(README_BODY), "text_sha256": sha(README_BODY)},
            }
        ],
    }
    return proposal


def _bound_proposal(world, planted=None):
    planted = _plant_document(world) if planted is None else planted
    proposal = valid_proposal(world)
    _bind_a(proposal, planted)
    _with_c(proposal)
    return proposal, planted


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


def _consts(view):
    assert view["schema"] == VIEW_SCHEMA
    assert view["publication"] == "unpublished"
    assert view["write_kind"] == "read_only"
    assert view["audit_coverage"] == "not_wired"
    assert view["code_freshness"] == "not_checked"
    assert view["canonical_official"] is False
    assert view["current_supported_typed_fact"] is False
    validate_document(view, VIEW_SCHEMA)


def _request_basis(world, batch):
    path = world["checkout"] / ".work" / batch / "domain-publication" / "request.json"
    return json.loads(path.read_bytes())["basis"]


def test_bound_view_proposal_only(world):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    succ = _successor_proposal(world)
    _bind_a(succ, planted)
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
    assert view["lineage_count"] == 1
    row = view["lineages"][0]
    assert row["lineage_id"] == first["record"]["lineage_id"]
    assert row["evidence"]["A"]["present"] is True
    assert row["evidence"]["A"]["status"] == "bound"
    assert row["evidence"]["A"]["locators"][0]["status"] == "bound"
    assert row["evidence"]["B"]["present"] is True
    assert row["evidence"]["B"]["status"] == "bound"
    assert row["evidence"]["C"]["status"] == "not_checked"
    assert row["evidence"]["D"]["status"] == "absent"
    assert row["evidence_freshness"] == "bound"
    assert row["relation_status"] == "proposal_only"
    assert row["role_basis"] == "proposal"
    assert row["reviewed_officiality"] is None
    assert row["current_review_id"] is None
    assert len(row["history"]) == 1
    assert row["reviews"] == []
    assert view["next_action"] == "none"
    assert view["conflicts"] == []
    assert view["papers"][0]["conflict_count"] == 0


def test_review_history_and_successor(world):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    review = _accept(world, first, batch="r1", officiality="official")
    viewed = _view(world)
    _consts(viewed)
    row = viewed["lineages"][0]
    assert row["relation_status"] == "reviewed_accepted"
    assert row["role_basis"] == "reviewed"
    assert row["reviewed_officiality"] == "official"
    assert row["reviews"][0]["current"] is True
    assert row["reviews"][0]["review_id"] == review["record"]["review_id"]
    assert viewed["canonical_official"] is False
    assert viewed["current_supported_typed_fact"] is False
    succ = _successor_proposal(world)
    _bind_a(succ, planted)
    _publish(
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
    assert row["reviews"][0]["current"] is False
    assert row["relation_status"] == "proposal_only"
    assert row["reviewed_officiality"] is None
    review_path = (
        world["vault"]
        / "wiki/meta/domain/reviews"
        / first["record"]["lineage_id"]
        / (review["record"]["review_id"] + ".json")
    )
    assert review_path.is_file()


def test_contested_and_rejected_role_basis(world):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    _accept(world, first, batch="c1", decision="contested")
    contested = next(
        row for row in _view(world)["lineages"] if row["lineage_id"] == first["record"]["lineage_id"]
    )
    assert contested["relation_status"] == "reviewed_contested"
    assert contested["role_basis"] == "proposal"
    other_code = _add_code_batch(world, "rej", repository="Reject/Repo")
    other_p = _proposal_from(world, other_code, repository="Reject/Repo")
    _bind_a(other_p, planted)
    second = _publish(world, other_p, name="r.json", batch="rej1")
    _accept(world, second, batch="rej1r", decision="rejected")
    rejected = next(
        row for row in _view(world)["lineages"] if row["lineage_id"] == second["record"]["lineage_id"]
    )
    assert rejected["relation_status"] == "reviewed_rejected"
    assert rejected["role_basis"] == "proposal"


def test_cross_repo_and_version_conflicts(world):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    _accept(world, first, batch="r1")
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    _bind_a(other_proposal, planted)
    other = _publish(world, other_proposal, name="o.json", batch="o1")
    _accept(world, other, batch="o1r")
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
    source_proposal["relation"]["kind"] = "baseline"
    _bind_a(source_proposal, planted)
    _publish(world, source_proposal, name="src.json", batch="src2")
    view = _view(world)
    _consts(view)
    assert view["lineage_count"] == 3
    assert len(view["papers"]) == 1
    paper = view["papers"][0]
    assert len(paper["repositories"]) == 2
    assert len(paper["source_association_ids"]) == 2
    kinds = {row["kind"] for row in view["conflicts"]}
    assert kinds == {"multiple_official_implementations", "repository_role_divergence"}
    multi = next(row for row in view["conflicts"] if row["kind"] == "multiple_official_implementations")
    assert set(multi["repositories"]) == {"owner/name", "other/repo"}
    assert view["next_action"] == "resolve_conflicts"
    assert paper["conflict_count"] == len(view["conflicts"])


def test_partial_or_unverified_review_has_no_multiple_official(world):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    _accept(world, first, batch="r1")
    other_code = _add_code_batch(world, "repo2", repository="Other/Repo")
    other_proposal = _proposal_from(world, other_code, repository="Other/Repo")
    _bind_a(other_proposal, planted)
    _publish(world, other_proposal, name="o.json", batch="o1")
    view = _view(world)
    assert all(row["kind"] != "multiple_official_implementations" for row in view["conflicts"])
    unverified_code = _add_code_batch(world, "repo3", repository="Third/Repo")
    unverified_proposal = _proposal_from(world, unverified_code, repository="Third/Repo")
    _bind_a(unverified_proposal, planted)
    third = _publish(world, unverified_proposal, name="t.json", batch="t1")
    _accept(world, third, batch="t1r", officiality="unverified_candidate")
    later = _view(world)
    assert all(row["kind"] != "multiple_official_implementations" for row in later["conflicts"])


def test_b_and_a_raw_mutations_make_stale(world):
    proposal, planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
    page = world["vault"] / world["page_rel"]
    original_page = world["page_body"]
    _write(page, original_page + b"changed\n")
    changed = _view(world)
    assert changed["lineages"][0]["evidence"]["B"]["status"] == "artifact_changed"
    assert changed["lineages"][0]["evidence_freshness"] == "stale"
    assert changed["lineages"][0]["relation_status"] == "stale"
    assert changed["next_action"] == "re_record_annotation"
    _write(page, original_page)
    page.unlink()
    missing = _view(world)
    assert missing["lineages"][0]["evidence"]["B"]["status"] == "artifact_missing"
    _write(page, original_page)
    _write(world["vault"] / planted["rel"], canonicalize({"texts": [{"text": "x"}, {"text": "changed", "prov": [{"page_no": 1}]}]}))
    a_changed = _view(world)
    assert a_changed["lineages"][0]["evidence"]["A"]["locators"][0]["status"] == "artifact_changed"
    _write(world["vault"] / planted["rel"], planted["raw"])
    _accept(world, first, batch="r1")
    _write(page, original_page + b"stale-official\n")
    official_stale = _view(world)
    row = official_stale["lineages"][0]
    assert row["reviewed_officiality"] == "official"
    assert row["relation_status"] == "stale"
    assert [item["kind"] for item in official_stale["conflicts"]] == ["official_with_stale_evidence"]
    assert official_stale["next_action"] == "resolve_conflicts"


def test_b_fragment_changed_with_same_size_bytes(world, monkeypatch):
    proposal, _planted = _bound_proposal(world)
    original = world["page_body"]
    proposal["relation"]["evidence_classes"]["B"]["project_page"]["fragment"] = {
        "start": 0,
        "end": 8,
        "text_sha256": sha(original[:8]),
    }
    _publish(world, proposal, name="g.json", batch="g1")
    page = world["vault"] / world["page_rel"]
    replacement = b"X" * len(original)
    _write(page, replacement)
    import video_paper_wiki.domain_relations as domain_relations

    real_sha = domain_relations.sha

    def patched(data):
        if data == replacement:
            return sha(original)
        return real_sha(data)

    monkeypatch.setattr(domain_relations, "sha", patched)
    view = _view(world)
    assert view["lineages"][0]["evidence"]["B"]["status"] == "fragment_changed"
    assert view["lineages"][0]["evidence_freshness"] == "stale"


def test_default_pdf_locator_artifact_missing(world):
    _publish(world, valid_proposal(world), name="m.json", batch="m1")
    row = _view(world)["lineages"][0]
    assert row["evidence"]["A"]["locators"][0]["status"] == "artifact_missing"
    assert row["evidence"]["A"]["status"] == "stale"
    assert row["evidence_freshness"] == "stale"
    assert row["relation_status"] == "stale"
    assert _view(world)["next_action"] == "re_record_annotation"


def test_a_text_ref_page_statuses(world):
    planted = _plant_document(world)
    other = _add_code_batch(world, "ta", repository="Text/Repo")
    text_p = _proposal_from(world, other, repository="Text/Repo")
    _bind_a(text_p, planted, text_sha256="b" * 64)
    _publish(world, text_p, name="t.json", batch="t1")
    assert _view(world)["lineages"][0]["evidence"]["A"]["locators"][0]["status"] == "text_mismatch"
    ref_code = _add_code_batch(world, "ra", repository="Ref/Repo")
    ref_p = _proposal_from(world, ref_code, repository="Ref/Repo")
    _bind_a(ref_p, planted, ref="#/texts/9")
    _publish(world, ref_p, name="r.json", batch="r1")
    statuses = {
        row["repository"]: row["evidence"]["A"]["locators"][0]["status"] for row in _view(world)["lineages"]
    }
    assert statuses["ref/repo"] == "ref_unresolvable"
    page_doc = _plant_document(world, page=2)
    page_code = _add_code_batch(world, "pa", repository="Page/Repo")
    page_p = _proposal_from(world, page_code, repository="Page/Repo")
    _bind_a(page_p, page_doc, page=1)
    _publish(world, page_p, name="p.json", batch="p1")
    statuses = {
        row["repository"]: row["evidence"]["A"]["locators"][0]["status"] for row in _view(world)["lineages"]
    }
    assert statuses["page/repo"] == "page_mismatch"
    assert all(row["evidence_freshness"] == "stale" for row in _view(world)["lineages"])
    assert _view(world)["next_action"] == "re_record_annotation"


def test_claim_stale_with_bound_evidence(world):
    proposal, _planted = _bound_proposal(world)
    _publish(world, proposal, name="g.json", batch="g1")
    bound = _view(world)
    assert bound["lineages"][0]["evidence_freshness"] == "bound"
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
    assert stale["lineages"][0]["claim_freshness"]["stale"] >= 1
    assert stale["lineages"][0]["evidence"]["A"]["status"] == "bound"
    assert stale["lineages"][0]["evidence"]["B"]["status"] == "bound"
    assert stale["lineages"][0]["relation_status"] == "stale"
    assert stale["next_action"] == "re_record_annotation"


def test_paper_filter_empty_store_and_invalid(world):
    empty = _view(world)
    _consts(empty)
    assert empty["lineage_count"] == 0
    assert empty["lineages"] == []
    assert empty["papers"] == []
    assert empty["conflicts"] == []
    assert empty["next_action"] == "none"
    assert set(empty["basis"]) == {
        "domain_store_inventory_sha256",
        "claim_ledger_sha256",
        "assessment_heads_sha256",
    }
    proposal, _planted = _bound_proposal(world)
    _publish(world, proposal, name="g.json", batch="g1")
    paper_id = world["association"]["paper_id"]
    filtered = _view(world, paper_id=paper_id)
    assert filtered["paper_filter"] == paper_id
    assert filtered["lineage_count"] == 1
    assert filtered["papers"][0]["paper_id"] == paper_id
    err = _expect(lambda: _view(world, paper_id=UNKNOWN_PAPER), "DOMAIN_RELATION_PAPER_UNKNOWN")
    assert err.details["next_action"] == "check_paper_id"
    assert err.details["known_paper_count"] == 1
    assert err.exit_code == 2
    invalid = _expect(lambda: _view(world, paper_id=""), "DOMAIN_RELATION_INVALID")
    assert invalid.details["instance_pointer"] == "/paper_id"
    assert invalid.details["next_action"] == "repair_input"
    (world["vault"] / CLAIM_LEDGER).unlink()
    missing = _expect(lambda: _view(world), "DOMAIN_STORE_INVALID")
    assert missing.details.get("reason") == "authority"


def test_store_structure_errors(world):
    proposal, _planted = _bound_proposal(world)
    first = _publish(world, proposal, name="g.json", batch="g1")
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
    os.symlink(
        first["record"]["annotation_id"] + ".json",
        link,
    )
    _expect(lambda: _view(world), "DOMAIN_STORE_INVALID")


def test_changed_during_claim_freshness_and_a_read(world, monkeypatch):
    proposal, planted = _bound_proposal(world)
    _publish(world, proposal, name="g.json", batch="g1")
    import video_paper_wiki.domain_relations as domain_relations

    original = domain_relations._claim_freshness

    def mutating(item, authority):
        path = world["vault"] / CLAIM_LEDGER
        path.write_bytes(path.read_bytes())
        os.chmod(path, 0o600)
        return original(item, authority)

    monkeypatch.setattr(domain_relations, "_claim_freshness", mutating)
    err = _expect(lambda: _view(world), "DOMAIN_STORE_CHANGED")
    assert err.exit_code == 75
    monkeypatch.setattr(domain_relations, "_claim_freshness", original)
    from video_paper_wiki.receipt_audit import _Snapshot

    read_optional = _Snapshot.read_optional

    def mutating_read(self, relative, **kwargs):
        result = read_optional(self, relative, **kwargs)
        if relative == planted["rel"]:
            path = self.root / relative
            path.write_bytes(path.read_bytes())
            os.chmod(path, 0o600)
        return result

    monkeypatch.setattr(_Snapshot, "read_optional", mutating_read)
    err = _expect(lambda: _view(world), "DOMAIN_STORE_CHANGED")
    assert err.exit_code == 75


def test_readonly_determinism_and_zero_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    proposal, _planted = _bound_proposal(world)
    _publish(world, proposal, name="g.json", batch="g1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    first = _view(world)
    second = _view(world)
    assert canonicalize(first) == canonicalize(second)
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before


def test_c_not_checked_and_d_declared_only(world):
    proposal, planted = _bound_proposal(world)
    proposal["relation"]["evidence_classes"]["C"] = {
        "present": True,
        "locators": [
            {
                "kind": "repository_text",
                "path": "README.md",
                "commit": proposal["commit"],
                "local_digest": {"sha256": sha(README_BODY), "size_bytes": len(README_BODY)},
                "fragment": {"start": 0, "end": len(README_BODY), "text_sha256": sha(README_BODY)},
            }
        ],
    }
    proposal["relation"]["evidence_classes"]["D"] = {
        "present": True,
        "author_control": {
            "kind": "author_control",
            "account": "owner",
            "organization": None,
            "control_evidence": "verified public control of the repository",
            "context": "repository README states this is the official implementation",
        },
    }
    _bind_a(proposal, planted)
    _publish(world, proposal, name="cd.json", batch="cd1")
    row = _view(world)["lineages"][0]
    assert row["evidence"]["C"]["present"] is True
    assert row["evidence"]["C"]["status"] == "not_checked"
    assert row["evidence"]["D"]["present"] is True
    assert row["evidence"]["D"]["status"] == "declared_only"


def test_unchecked_when_a_and_b_absent(world):
    proposal = valid_proposal(world)
    proposal["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
    proposal["relation"]["evidence_classes"]["B"] = {"present": False, "project_page": None}
    proposal["relation"]["officiality_candidate"] = "unverified_candidate"
    proposal["relation"]["missing_evidence"] = ["A", "B"]
    _publish(world, proposal, name="u.json", batch="u1")
    row = _view(world)["lineages"][0]
    assert row["evidence"]["A"]["status"] == "absent"
    assert row["evidence"]["B"]["status"] == "absent"
    assert row["evidence_freshness"] == "unchecked"
    assert row["relation_status"] == "proposal_only"
