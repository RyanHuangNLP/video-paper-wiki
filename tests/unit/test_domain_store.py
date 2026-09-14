from __future__ import annotations

import copy
import json
import os
import socket
import stat
from pathlib import Path

import pytest

from tests.code_proof_public_fixture import (
    dump_json,
    make_repo,
    observe_raw_doc,
    request_doc,
    seal,
    write_bytes,
)
from video_paper_wiki.code_proof_public import (
    handoff_code_proof,
    observe_code_proof,
    request_code_proof,
    status_code_proof,
)
from tests.source_semantics_fixture import event_for, source_fixture
from tests.unit.test_domain_proposal import (
    _snapshot,
    _write,
    inspect_file,
    make_world,
    valid_proposal,
    write_proposal,
)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import (
    DomainStoreError,
    derive_domain_heads,
    lineage_id_from_report,
    load_domain_store,
    record_domain_annotation,
    review_domain_annotation,
    status_domain_store,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = REPO_ROOT / "taxonomy" / "v1.json"
BATCH = "d2"
RECORDED_BY = "synthetic-fixture-reviewer"
RECORDED_AT = "2026-09-14T00:00:00Z"
LATER_AT = "2026-09-14T01:00:00Z"
REVIEW_AT = "2026-09-14T02:00:00Z"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _apply_staged(world, batch=BATCH):
    staged_root = world["checkout"] / ".work" / batch / "domain"
    dest_root = world["vault"] / "wiki/meta/domain"
    for path in sorted(p for p in staged_root.rglob("*") if p.is_file()):
        target = dest_root / path.relative_to(staged_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        os.chmod(target, 0o600)


def _record(world, proposal, *, name="proposal.json", previous=None, recorded_at=RECORDED_AT, batch=BATCH):
    path = write_proposal(world["checkout"], proposal, name)
    return record_domain_annotation(
        input_path=str(path),
        vault_root=str(world["vault"]),
        code_batch_id="d1" if proposal["code_batch_id"] == "d1" else proposal["code_batch_id"],
        batch_id=batch,
        recorded_by=RECORDED_BY,
        recorded_at=recorded_at,
        previous_annotation_id=previous,
    )


def _review(world, decision, *, name="decision.json", batch=BATCH):
    path = world["checkout"] / name
    write_bytes(path, canonicalize(decision) + b"\n")
    return review_domain_annotation(
        decision_path=str(path),
        vault_root=str(world["vault"]),
        batch_id=batch,
    )


def _status(world):
    return status_domain_store(vault_root=str(world["vault"]))


def _load(world):
    return load_domain_store(str(world["vault"]))


def _expect(fn, code):
    with pytest.raises(DomainStoreError) as err:
        fn()
    assert err.value.code == code
    assert err.value.details.get("instance_pointer") is not None
    assert err.value.details.get("next_action")
    return err.value


def _relation_review(report, officiality="official", relied=None, missing=None):
    return {
        "reviewed_officiality": officiality,
        "evidence_classes_relied_on": list(relied if relied is not None else ["A"]),
        "missing_evidence": list(report["relation"]["gaps"] if missing is None else missing),
        "reason": "Synthetic relation review.",
    }


def _decision_for(world, data, *, officiality="official", decision="accepted", **overrides):
    record = data["record"]
    lid = record["lineage_id"]
    aid = record["annotation_id"]
    payload = {
        "schema": "video-paper-wiki.domain-review-decision.v1",
        "lineage_id": lid,
        "annotation_id": aid,
        "annotation_sha256": sha(canonicalize(record)),
        "expected_previous_review_id": None,
        "decision": decision,
        "decided_by": RECORDED_BY,
        "decided_at": REVIEW_AT,
        "reason": "Synthetic human review.",
    }
    if decision == "accepted":
        payload["relation_review"] = _relation_review(record["report"], officiality)
    payload.update(overrides)
    return payload


def _authority_bytes(world):
    vault = world["vault"]
    reviews = {}
    root = vault / "wiki/meta/reviews"
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file():
                reviews[str(path.relative_to(vault))] = path.read_bytes()
    return {
        "ledger": (vault / CLAIM_LEDGER).read_bytes(),
        "heads": (vault / ASSESSMENT_HEADS).read_bytes(),
        "reviews": reviews,
        "taxonomy": TAXONOMY.read_bytes(),
    }


def _rewrite_json(path: Path, mutate):
    doc = json.loads(path.read_bytes())
    mutate(doc)
    _write(path, canonicalize(doc))


def _plant_annotation(world, record, raw=None):
    raw = canonicalize(record) if raw is None else raw
    path = (
        world["vault"]
        / "wiki/meta/domain/annotations"
        / record["lineage_id"]
        / (record["annotation_id"] + ".json")
    )
    _write(path, raw)
    return path


def _plant_heads(world, heads):
    _write(world["vault"] / "wiki/meta/domain/heads.json", canonicalize(heads))


def _write_bundle(checkout: Path, relative: str, repo: dict, request_ref: dict, repository: str) -> None:
    root = checkout / relative
    objects = root / "objects"
    objects.mkdir(parents=True)
    data = {
        "request": request_ref,
        "object_format": repo["object_format"],
        "repository": repository.lower(),
        "commit_oid": repo["commit_oid"],
        "root_tree_oid": repo["root_tree_oid"],
        "objects": repo["objects"],
    }
    payload = seal("code-git-bundle", data)
    (root / "manifest.json").write_bytes(payload)
    for record in repo["objects"]:
        dest = objects / (record["oid"] + ".body")
        dest.write_bytes(repo["bodies"][record["oid"]])
        os.chmod(dest, 0o600)
    os.chmod(root / "manifest.json", 0o600)


def _add_code_batch(world, batch_id, *, repository="Owner/Name", files=None, association=None, assoc_raw=None):
    files = files or world["files"]
    association = world["association"] if association is None else association
    assoc_raw = world["assoc_raw"] if assoc_raw is None else assoc_raw
    repo = make_repo("sha1", files)
    targets = [
        {"path": "README.md", "roles": ["readme"], "allow_executable_source": False},
        {"path": "config.json", "roles": ["configuration"], "allow_executable_source": False},
        {"path": "src.py", "roles": ["implementation"], "allow_executable_source": False},
    ]
    request = request_doc(repo, targets, repository=repository)
    request["paper_id"] = association["paper_id"]
    request["source_association"] = {
        "association_id": association["association_id"],
        "sha256": sha(assoc_raw),
    }
    checkout = world["checkout"]
    write_bytes(checkout / f"request-{batch_id}.json", dump_json(request))
    req = request_code_proof(input_path=f"request-{batch_id}.json", batch_id=batch_id)
    _write_bundle(checkout, f".work/raw-{batch_id}", repo, req["request"], repository)
    write_bytes(checkout / f"observe-{batch_id}.json", dump_json(observe_raw_doc(repo)))
    observe_code_proof(
        input_path=f"observe-{batch_id}.json",
        batch_id=batch_id,
        bundle_dir=f".work/raw-{batch_id}",
    )
    handoff_code_proof(batch_id=batch_id)
    return {"repo": repo, "status": status_code_proof(batch_id=batch_id), "batch_id": batch_id}


def _proposal_from(world, code, *, association=None, assoc_raw=None, repository="Owner/Name"):
    alt = dict(world)
    alt["repo"] = code["repo"]
    alt["status"] = code["status"]
    if association is not None:
        alt["association"] = association
        alt["assoc_raw"] = assoc_raw
    proposal = valid_proposal(alt)
    proposal["repository"] = repository
    proposal["code_batch_id"] = code["batch_id"]
    proposal["commit"] = code["repo"]["commit_oid"]
    for capability in proposal["capabilities"]:
        for locator in capability["locators"]:
            locator["repository"] = repository
            locator["commit"] = code["repo"]["commit_oid"]
        absence = capability.get("absence_scope")
        if absence is not None:
            absence["commit"] = code["repo"]["commit_oid"]
    return proposal


def _successor_proposal(world):
    proposal = valid_proposal(world)
    proposal["concepts"][0]["surface_form"] = "changed-surface"
    return proposal


def test_genesis_successor_and_commit_change(world):
    before = _authority_bytes(world)
    first = _record(world, valid_proposal(world), name="g.json", batch="g1")
    validate_document(first["record"], "video-paper-wiki.domain-annotation-record.v1")
    validate_document(first["heads"], "video-paper-wiki.domain-heads.v1")
    report = first["record"]["report"]
    for key, value in (
        ("status", "proposal_only"),
        ("publication", "unpublished"),
        ("review", "pending_semantic_review"),
        ("successor_only", True),
        ("source_association_verified", False),
        ("canonical_official", False),
        ("current_supported_typed_fact", False),
    ):
        assert report[key] is value or report[key] == value
    assert first["publication"] == "unpublished"
    assert first["next_action"] == "semantic_review_required"
    lid = first["record"]["lineage_id"]
    assert lid == lineage_id_from_report(report)
    assert first["record"]["previous_annotation_id"] is None
    rel = first["staged"][0]["relative"]
    assert rel.startswith("domain/annotations/")
    assert (world["checkout"] / ".work" / "g1" / rel).is_file()
    assert first["staged"][0]["destination"].startswith("wiki/meta/domain/")
    _apply_staged(world, "g1")
    second = _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="g2",
    )
    assert second["record"]["lineage_id"] == lid
    assert second["record"]["previous_annotation_id"] == first["record"]["annotation_id"]
    assert second["record"]["report_sha256"] != first["record"]["report_sha256"]
    _apply_staged(world, "g2")
    files = {
        "config.json": world["files"]["config.json"],
        "src.py": world["files"]["src.py"],
        "README.md": (b"# demo changed\n", False),
    }
    code = _add_code_batch(world, "d1c", files=files)
    commit_proposal = _proposal_from(world, code)
    commit_proposal["concepts"][1]["surface_form"] = "commit-change"
    third = _record(
        world,
        commit_proposal,
        name="c.json",
        previous=second["record"]["annotation_id"],
        recorded_at="2026-09-14T03:00:00Z",
        batch="g3",
    )
    assert third["record"]["lineage_id"] == lid
    assert third["record"]["report"]["commit"] != first["record"]["report"]["commit"]
    after = _authority_bytes(world)
    assert after["ledger"] == before["ledger"]
    assert after["heads"] == before["heads"]
    assert after["reviews"] == before["reviews"]
    assert after["taxonomy"] == before["taxonomy"]


def test_different_source_and_repo_lineages(world):
    first = _record(world, valid_proposal(world), name="a.json")
    association, raw, _authority = source_fixture(label="v2")
    assoc_raw = canonicalize(association)
    _write(
        world["vault"] / "wiki/meta/records/source-versions" / (association["association_id"] + ".json"),
        assoc_raw,
    )
    raw_path = world["vault"] / association["raw"]["path"]
    if not raw_path.exists():
        _write(raw_path, raw)
    source_code = _add_code_batch(
        world, "src2", association=association, assoc_raw=assoc_raw
    )
    source_proposal = _proposal_from(
        world, source_code, association=association, assoc_raw=assoc_raw
    )
    source_data = _record(world, source_proposal, name="src.json", batch="d2s")
    assert source_data["record"]["lineage_id"] != first["record"]["lineage_id"]
    repo_code = _add_code_batch(world, "repo2", repository="Other/Name")
    repo_proposal = _proposal_from(world, repo_code, repository="Other/Name")
    repo_data = _record(world, repo_proposal, name="repo.json", batch="d2r")
    assert repo_data["record"]["lineage_id"] != first["record"]["lineage_id"]
    assert repo_data["record"]["lineage_id"] != source_data["record"]["lineage_id"]
    _apply_staged(world)
    _apply_staged(world, "d2s")
    from video_paper_wiki.domain_store import annotation_id_from_record

    src_path = (
        world["vault"]
        / "wiki/meta/domain/annotations"
        / source_data["record"]["lineage_id"]
        / (source_data["record"]["annotation_id"] + ".json")
    )
    crossed = json.loads(src_path.read_bytes())
    crossed["previous_annotation_id"] = first["record"]["annotation_id"]
    crossed.pop("annotation_id")
    crossed["annotation_id"] = annotation_id_from_record(crossed)
    src_path.unlink()
    _write(src_path.parent / (crossed["annotation_id"] + ".json"), canonicalize(crossed))
    err = _expect(lambda: _load(world), "DOMAIN_STORE_CHAIN_INVALID")
    assert err.details.get("reason") == "cross_lineage"


def test_record_const_guards_and_empty_status(world):
    empty = _status(world)
    assert empty["heads"]["heads"] == {}
    assert empty["lineages"] == []
    assert empty["canonical_official"] is False
    assert empty["current_supported_typed_fact"] is False
    assert empty["code_freshness"] == "not_checked"
    assert empty["audit_coverage"] == "not_wired"
    data = _record(world, valid_proposal(world))
    assert data["record"]["report"]["canonical_official"] is False
    assert data["record"]["report"]["current_supported_typed_fact"] is False


def test_record_previous_and_unchanged_refusals(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="p1")
    _apply_staged(world, "p1")
    _expect(lambda: _record(world, valid_proposal(world), name="again.json", batch="p2"), "DOMAIN_RECORD_PREVIOUS_MISMATCH")
    _expect(
        lambda: _record(
            world,
            valid_proposal(world),
            name="wrong.json",
            previous="dan-" + "0" * 20,
        ),
        "DOMAIN_RECORD_PREVIOUS_MISMATCH",
    )
    _expect(
        lambda: _record(
            world,
            valid_proposal(world),
            name="same.json",
            previous=first["record"]["annotation_id"],
            recorded_at=LATER_AT,
        ),
        "DOMAIN_RECORD_UNCHANGED",
    )
    repo_code = _add_code_batch(world, "omit", repository="Omit/Repo")
    omit_proposal = _proposal_from(world, repo_code, repository="Omit/Repo")
    _expect(
        lambda: _record(
            world,
            omit_proposal,
            name="omit.json",
            previous=first["record"]["annotation_id"],
            batch="d2o",
        ),
        "DOMAIN_RECORD_PREVIOUS_MISMATCH",
    )


def test_store_mutation_refusals(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="m1")
    _apply_staged(world, "m1")
    second = _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="m2",
    )
    _apply_staged(world, "m2")
    vault = world["vault"]
    lid = first["record"]["lineage_id"]
    first_path = vault / "wiki/meta/domain/annotations" / lid / (first["record"]["annotation_id"] + ".json")
    second_path = vault / "wiki/meta/domain/annotations" / lid / (second["record"]["annotation_id"] + ".json")
    heads_path = vault / "wiki/meta/domain/heads.json"

    renamed = first_path.parent / ("dan-" + "a" * 20 + ".json")
    first_path.rename(renamed)
    _expect(lambda: _load(world), "DOMAIN_STORE_INVALID")
    renamed.rename(first_path)

    fake_id = "dan-" + "b" * 20
    fake = json.loads(first_path.read_bytes())
    fake["annotation_id"] = fake_id
    fake_path = first_path.parent / (fake_id + ".json")
    _write(fake_path, canonicalize(fake))
    first_path.unlink()
    _expect(lambda: _load(world), "DOMAIN_STORE_INVALID")
    fake_path.unlink()
    _write(first_path, canonicalize(first["record"]))

    _write(first_path, json.dumps(json.loads(first_path.read_bytes()), indent=2).encode("utf-8"))
    _expect(lambda: _load(world), "DOMAIN_STORE_INVALID")
    _write(first_path, canonicalize(first["record"]))

    from video_paper_wiki.domain_store import annotation_id_from_record

    missing_prev = json.loads(second_path.read_bytes())
    missing_prev["previous_annotation_id"] = "dan-" + "c" * 20
    missing_prev.pop("annotation_id")
    missing_prev["annotation_id"] = annotation_id_from_record(missing_prev)
    second_path.unlink()
    _write(second_path.parent / (missing_prev["annotation_id"] + ".json"), canonicalize(missing_prev))
    _expect(lambda: _load(world), "DOMAIN_STORE_CHAIN_INVALID")
    for leftover in second_path.parent.glob("dan-*.json"):
        leftover.unlink()
    _write(first_path, canonicalize(first["record"]))
    _write(second_path, canonicalize(second["record"]))
    _plant_heads(world, second["heads"])

    fork = json.loads(second_path.read_bytes())
    fork["recorded_by"] = "other-reviewer"
    fork.pop("annotation_id")
    fork["annotation_id"] = annotation_id_from_record(fork)
    _write(second_path.parent / (fork["annotation_id"] + ".json"), canonicalize(fork))
    _expect(lambda: _load(world), "DOMAIN_STORE_CHAIN_INVALID")
    (second_path.parent / (fork["annotation_id"] + ".json")).unlink()

    genesis2 = json.loads(second_path.read_bytes())
    genesis2["previous_annotation_id"] = None
    genesis2["recorded_by"] = "second-genesis"
    genesis2.pop("annotation_id")
    genesis2["annotation_id"] = annotation_id_from_record(genesis2)
    _write(second_path.parent / (genesis2["annotation_id"] + ".json"), canonicalize(genesis2))
    _expect(lambda: _load(world), "DOMAIN_STORE_CHAIN_INVALID")
    (second_path.parent / (genesis2["annotation_id"] + ".json")).unlink()

    earlier = json.loads(second_path.read_bytes())
    earlier["recorded_at"] = "2026-09-13T00:00:00Z"
    earlier.pop("annotation_id")
    earlier["annotation_id"] = annotation_id_from_record(earlier)
    second_path.unlink()
    _write(second_path.parent / (earlier["annotation_id"] + ".json"), canonicalize(earlier))
    _expect(lambda: _load(world), "DOMAIN_STORE_CHAIN_INVALID")
    for leftover in second_path.parent.glob("dan-*.json"):
        if leftover.name != first["record"]["annotation_id"] + ".json":
            leftover.unlink()
    _write(second_path, canonicalize(second["record"]))
    _plant_heads(world, second["heads"])

    foreign_lid = "dln-" + "d" * 20
    mixed = json.loads(first_path.read_bytes())
    mixed["lineage_id"] = foreign_lid
    mixed.pop("annotation_id")
    mixed["annotation_id"] = annotation_id_from_record(mixed)
    mixed_dir = vault / "wiki/meta/domain/annotations" / foreign_lid
    _write(mixed_dir / (mixed["annotation_id"] + ".json"), canonicalize(mixed))
    original_dir = first_path.parent
    for leftover in original_dir.glob("*.json"):
        leftover.unlink()
    original_dir.rmdir()
    _plant_heads(world, {"schema": "video-paper-wiki.domain-heads.v1", "heads": {}})
    _expect(lambda: _load(world), "DOMAIN_STORE_INVALID")
    for leftover in mixed_dir.glob("*.json"):
        leftover.unlink()
    mixed_dir.rmdir()
    _write(first_path, canonicalize(first["record"]))
    _write(second_path, canonicalize(second["record"]))
    _plant_heads(world, second["heads"])

    notes = vault / "wiki/meta/domain/notes.txt"
    notes.write_text("nope", encoding="utf-8")
    os.chmod(notes, 0o600)
    _expect(lambda: _load(world), "DOMAIN_STORE_INVALID")
    notes.unlink()

    empty_dir = vault / "wiki/meta/domain/annotations" / ("dln-" + "e" * 20)
    empty_dir.mkdir(parents=True)
    _expect(lambda: _load(world), "DOMAIN_STORE_INVALID")
    empty_dir.rmdir()

    link = vault / "wiki/meta/domain" / "link.json"
    os.symlink(first_path, link)
    _expect(lambda: _load(world), "DOMAIN_STORE_INVALID")
    link.unlink()

    extra = world["checkout"] / "hardlink-extra"
    os.link(first_path, extra)
    _expect(lambda: _load(world), "DOMAIN_STORE_INVALID")
    extra.unlink()

    heads_path.unlink()
    _expect(lambda: _load(world), "DOMAIN_STORE_HEADS_MISSING")
    _plant_heads(world, first["heads"])
    _expect(lambda: _load(world), "DOMAIN_STORE_HEADS_MISMATCH")
    _plant_heads(world, second["heads"])

    import video_paper_wiki.domain_store as domain_store

    original = domain_store.MAX_PER_LINEAGE
    domain_store.MAX_PER_LINEAGE = 1
    try:
        _expect(
            lambda: _record(
                world,
                _successor_proposal(world),
                name="limit.json",
                previous=second["record"]["annotation_id"],
                recorded_at="2026-09-14T04:00:00Z",
                batch="m3",
            ),
            "DOMAIN_STORE_LIMIT",
        )
    finally:
        domain_store.MAX_PER_LINEAGE = original


def test_read_during_change_exit_75(world, monkeypatch):
    data = _record(world, valid_proposal(world), batch="chg1")
    _apply_staged(world, "chg1")
    from video_paper_wiki.receipt_audit import _Snapshot

    original = _Snapshot.read

    def mutating(self, relative, **kwargs):
        raw = original(self, relative, **kwargs)
        if relative.endswith("heads.json") and "domain" in relative:
            path = self.root / relative
            path.write_bytes(raw)
            os.chmod(path, 0o600)
        return raw

    monkeypatch.setattr(_Snapshot, "read", mutating)
    err = _expect(lambda: _status(world), "DOMAIN_STORE_CHANGED")
    assert err.exit_code == 75
    assert err.details["next_action"] == "repeat_read"


def test_review_official_unverified_and_unofficial(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="o1")
    _apply_staged(world, "o1")
    official = _review(world, _decision_for(world, first, officiality="official"), batch="o1r")
    assert official["record"]["decision"] == "accepted"
    assert official["record"]["actor_kind"] == "human"
    assert official["record"]["relation_review"]["reviewed_officiality"] == "official"
    assert official["next_action"] == "publication_pending_later_slice"
    assert official["canonical_official"] is False
    assert official["current_supported_typed_fact"] is False
    _apply_staged(world, "o1r")
    status = _status(world)
    assert status["canonical_official"] is False
    assert status["current_supported_typed_fact"] is False
    assert status["lineages"][0]["reviewed_officiality"] == "official"
    assert status["heads"]["heads"][first["record"]["lineage_id"]]["review_decision"] == "accepted"

    unverified_world_proposal = valid_proposal(world)
    unverified_world_proposal["concepts"][2]["surface_form"] = "unverified-branch"
    # new lineage by recording without apply? use a distinct batch after resetting store
    # instead, review unverified against a fresh vault copy is heavy; record a new lineage via different repo
    repo_code = _add_code_batch(world, "unv", repository="Unver/Repo")
    unverified_proposal = _proposal_from(world, repo_code, repository="Unver/Repo")
    unverified_data = _record(world, unverified_proposal, name="unv.json", batch="d2u")
    _apply_staged(world, batch="d2u")
    unverified = _review(
        world,
        _decision_for(world, unverified_data, officiality="unverified_candidate"),
        name="unv-dec.json",
        batch="d2ur",
    )
    assert unverified["record"]["relation_review"]["reviewed_officiality"] == "unverified_candidate"

    third_code = _add_code_batch(world, "tp", repository="Third/Party")
    third = _proposal_from(world, third_code, repository="Third/Party")
    third["relation"]["kind"] = "third_party_reproduction"
    third["relation"]["third_party_statement"] = True
    third["relation"]["officiality_candidate"] = "third_party"
    third["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
    third["concepts"][3]["surface_form"] = "third-party-branch"
    third_data = _record(world, third, name="third.json", batch="d2t")
    _apply_staged(world, batch="d2t")
    unofficial = _review(
        world,
        _decision_for(world, third_data, officiality="unofficial"),
        name="third-dec.json",
        batch="d2tr",
    )
    assert unofficial["record"]["relation_review"]["reviewed_officiality"] == "unofficial"


def test_review_refusals(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="rf1")
    _apply_staged(world, "rf1")
    only_c = _decision_for(world, first)
    only_c["relation_review"] = _relation_review(first["record"]["report"], "official", relied=["C"])
    _expect(lambda: _review(world, only_c, name="only-c.json"), "DOMAIN_REVIEW_INVALID")

    unknown_class = _decision_for(world, first)
    unknown_class["relation_review"] = _relation_review(
        first["record"]["report"], "official", relied=["A", "C"]
    )
    _expect(lambda: _review(world, unknown_class, name="bad-class.json"), "DOMAIN_REVIEW_INVALID")

    bad_gaps = _decision_for(world, first)
    bad_gaps["relation_review"] = _relation_review(
        first["record"]["report"], "official", missing=["A"]
    )
    _expect(lambda: _review(world, bad_gaps, name="bad-gaps.json"), "DOMAIN_REVIEW_INVALID")

    contested = _decision_for(world, first, decision="contested")
    contested["relation_review"] = _relation_review(first["record"]["report"])
    _expect(lambda: _review(world, contested, name="contested.json"), "DOMAIN_REVIEW_INVALID")

    shortcuts = valid_proposal(world)
    shortcuts["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
    shortcuts["relation"]["evidence_classes"]["B"] = {"present": False, "project_page": None}
    shortcuts["relation"]["officiality_candidate"] = "unverified_candidate"
    shortcuts["concepts"][4]["surface_form"] = "shortcut-branch"
    shortcut_data = _record(
        world,
        shortcuts,
        name="short.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="d2k",
    )
    _apply_staged(world, batch="d2k")
    shortcut_official = _decision_for(world, shortcut_data, officiality="official")
    _expect(
        lambda: _review(world, shortcut_official, name="short-dec.json", batch="d2k"),
        "DOMAIN_REVIEW_INVALID",
    )
    missing_unofficial = _decision_for(world, shortcut_data, officiality="unofficial")
    _expect(
        lambda: _review(world, missing_unofficial, name="false-unoff.json", batch="d2k"),
        "DOMAIN_REVIEW_INVALID",
    )

    second = _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=shortcut_data["record"]["annotation_id"],
        recorded_at="2026-09-14T03:00:00Z",
        batch="rf2",
    )
    _apply_staged(world, "rf2")
    not_head = _decision_for(world, first)
    not_head["annotation_id"] = first["record"]["annotation_id"]
    not_head["annotation_sha256"] = sha(canonicalize(first["record"]))
    _expect(lambda: _review(world, not_head, name="old-head.json"), "DOMAIN_REVIEW_TARGET_NOT_HEAD")

    stale_prev = _decision_for(world, second)
    stale_prev["expected_previous_review_id"] = "drv-" + "0" * 20
    _expect(lambda: _review(world, stale_prev, name="stale-prev.json"), "DOMAIN_REVIEW_STALE")

    bad_sha = _decision_for(world, second)
    bad_sha["annotation_sha256"] = "0" * 64
    _expect(lambda: _review(world, bad_sha, name="bad-sha.json"), "DOMAIN_REVIEW_BINDING_MISMATCH")


def test_freshness_and_typed_fact_candidates(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="f1")
    _apply_staged(world, "f1")
    accepted = _review(world, _decision_for(world, first, officiality="official"), batch="f1r")
    _apply_staged(world, "f1r")
    status = _status(world)
    assert status["lineages"][0]["typed_fact_status"] == "reviewed_accepted"
    assert {row["typed_fact_candidate"] for row in status["lineages"][0]["claims"]} == {"not_supported"}
    assert all(row["freshness"] == "head_bound" for row in status["lineages"][0]["claims"])
    assert status["current_supported_typed_fact"] is False

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
    stale_status = _status(world)
    assert stale_status["lineages"][0]["typed_fact_status"] == "stale"
    stale_row = next(
        row for row in stale_status["lineages"][0]["claims"] if row["claim_id"] == claim["claim_id"]
    )
    assert stale_row["freshness"] == "stale"
    assert stale_row["stale_reason"] == "assessment_head_changed"
    stale_decision = _decision_for(world, first)
    stale_decision["expected_previous_review_id"] = accepted["record"]["review_id"]
    _expect(lambda: _review(world, stale_decision, name="stale-head.json"), "DOMAIN_HEAD_STALE")

    heads["heads"][claim["claim_id"]] = {
        "event_id": old_event["event_id"],
        "event_sha256": sha(canonicalize(old_event)),
        "evidence_profile": old_event.get("evidence_profile", "legacy-v1"),
    }
    _write(heads_path, canonicalize(heads))
    historical = _record(
        world,
        _successor_proposal(world),
        name="hist.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="f2",
    )
    _apply_staged(world, "f2")
    review_path = (
        world["vault"]
        / "wiki/meta/domain/reviews"
        / first["record"]["lineage_id"]
        / (accepted["record"]["review_id"] + ".json")
    )
    assert review_path.is_file()
    hist_status = _status(world)
    head_entry = hist_status["heads"]["heads"][first["record"]["lineage_id"]]
    assert head_entry["annotation_id"] == historical["record"]["annotation_id"]
    assert head_entry["review_id"] is None
    assert hist_status["lineages"][0]["review_count"] == 1
    assert hist_status["lineages"][0]["typed_fact_status"] == "proposal_only"


def test_supported_candidate_from_accepted_claim(world):
    kind, claim, old_event = world["annotated"][0]
    new_event = event_for(claim, previous=old_event, human=True, state="accepted")
    _write(
        world["vault"] / "wiki/meta/reviews" / claim["claim_id"] / (new_event["event_id"] + ".json"),
        canonicalize(new_event),
    )
    heads = json.loads((world["vault"] / ASSESSMENT_HEADS).read_bytes())
    heads["heads"][claim["claim_id"]] = {
        "event_id": new_event["event_id"],
        "event_sha256": sha(canonicalize(new_event)),
        "evidence_profile": new_event.get("evidence_profile", "legacy-v1"),
    }
    _write(world["vault"] / ASSESSMENT_HEADS, canonicalize(heads))
    ledger = json.loads((world["vault"] / CLAIM_LEDGER).read_bytes())
    ledger["claims"][claim["claim_id"]]["assessment"] = "accepted"
    ledger["claims"][claim["claim_id"]]["reviewed_at"] = new_event["decided_at"][:10]
    _write(world["vault"] / CLAIM_LEDGER, canonicalize(ledger))
    world["annotated"][0] = (kind, claim, new_event)
    data = _record(world, valid_proposal(world), name="acc.json", batch="sc1")
    _apply_staged(world, "sc1")
    _review(world, _decision_for(world, data, officiality="official"), batch="sc1r")
    _apply_staged(world, "sc1r")
    status = _status(world)
    by_id = {row["claim_id"]: row for row in status["lineages"][0]["claims"]}
    assert by_id[claim["claim_id"]]["assessment"] == "accepted"
    assert by_id[claim["claim_id"]]["typed_fact_candidate"] == "supported_candidate"
    assert status["current_supported_typed_fact"] is False
    assert status["canonical_official"] is False
    others = [row for cid, row in by_id.items() if cid != claim["claim_id"]]
    assert all(row["typed_fact_candidate"] == "not_supported" for row in others)


def test_record_stale_window(world, monkeypatch):
    proposal = valid_proposal(world)
    path = write_proposal(world["checkout"], proposal, "window.json")
    report = inspect_file(world, proposal, name="window-inspect.json")
    monkeypatch.setattr(
        "video_paper_wiki.domain_store.inspect_domain_proposal",
        lambda **_k: report,
    )
    kind, claim, old_event = world["annotated"][0]
    new_event = event_for(claim, previous=old_event, human=True, state="contested")
    _write(
        world["vault"] / "wiki/meta/reviews" / claim["claim_id"] / (new_event["event_id"] + ".json"),
        canonicalize(new_event),
    )
    heads = json.loads((world["vault"] / ASSESSMENT_HEADS).read_bytes())
    heads["heads"][claim["claim_id"]] = {
        "event_id": new_event["event_id"],
        "event_sha256": sha(canonicalize(new_event)),
        "evidence_profile": new_event.get("evidence_profile", "legacy-v1"),
    }
    _write(world["vault"] / ASSESSMENT_HEADS, canonicalize(heads))
    _expect(
        lambda: record_domain_annotation(
            input_path=str(path),
            vault_root=str(world["vault"]),
            code_batch_id="d1",
            batch_id=BATCH,
            recorded_by=RECORDED_BY,
            recorded_at=RECORDED_AT,
        ),
        "DOMAIN_HEAD_STALE",
    )


def test_determinism_and_zero_vault_writes(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    proposal = valid_proposal(world)
    vault_before = _snapshot(world["vault"])
    first = _record(world, proposal, name="a.json")
    second = _record(world, proposal, name="b.json")
    assert canonicalize(first) == canonicalize(second)
    assert _snapshot(world["vault"]) == vault_before
    staged = world["checkout"] / ".work" / BATCH / first["staged"][0]["relative"]
    assert staged.read_bytes() == canonicalize(first["record"])
