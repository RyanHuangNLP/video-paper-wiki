from __future__ import annotations

import errno
import json
import os
import socket
import stat

import pytest

from tests.unit.test_domain_proposal import (
    _snapshot,
    _write,
    make_world,
    valid_proposal,
)
from tests.unit.test_domain_store import (
    BATCH,
    LATER_AT,
    RECORDED_AT,
    RECORDED_BY,
    REVIEW_AT,
    _add_code_batch,
    _authority_bytes,
    _decision_for,
    _proposal_from,
    _record,
    _relation_review,
    _review,
    _successor_proposal,
)
from video_paper_wiki import domain_apply
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_apply import DomainApplyError, apply_domain_publication
from video_paper_wiki.domain_publication import (
    DomainPublicationError,
    compile_domain_publication,
    inspect_domain_publication,
)
from video_paper_wiki.domain_store import (
    DomainStoreError,
    derive_domain_heads,
    load_domain_store,
    review_id_from_record,
    status_domain_store,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import _Snapshot, _walk_inventory
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

RESULT_SCHEMA = "video-paper-wiki.domain-publication-apply-result.v1"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _compile(world, batch=BATCH):
    return compile_domain_publication(vault_root=str(world["vault"]), batch_id=batch)


def _inspect(world, batch=BATCH):
    prepared = world["checkout"] / ".work" / batch / "domain-publication" / "request.json"
    return inspect_domain_publication(prepared=str(prepared), vault_root=str(world["vault"]))


def _request(world, batch=BATCH):
    path = world["checkout"] / ".work" / batch / "domain-publication" / "request.json"
    return json.loads(path.read_bytes())


def _prepared(world, batch=BATCH):
    return str(world["checkout"] / ".work" / batch / "domain-publication" / "request.json")


def _apply(world, batch=BATCH, *, confirm=None, _fault=None):
    if confirm is None:
        confirm = lambda _summary: True
    return apply_domain_publication(
        prepared=_prepared(world, batch),
        vault_root=str(world["vault"]),
        confirm=confirm,
        _fault=_fault,
    )


def _expect(fn, code):
    with pytest.raises((DomainApplyError, DomainPublicationError, DomainStoreError, StagingError, ContractError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    assert details.get("next_action")
    if code != "WORK_PATH_UNSAFE":
        assert details.get("instance_pointer") is not None
    return err.value


def _audit_keys(vault):
    snap = _Snapshot(vault)
    try:
        return set(_walk_inventory(snap, read_bytes=False))
    finally:
        snap.close()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _consts(result):
    assert result["write_kind"] == "direct_store_write"
    assert result["applied"] is True
    assert result["publication"] == "unpublished"
    assert result["receipt_backed"] is False
    assert result["audit_coverage"] == "not_wired"
    assert result["backup_coverage"] == "not_wired"
    assert result["transaction_authority"] == "not_wired"
    assert result["canonical_official"] is False
    assert result["current_supported_typed_fact"] is False
    assert result["next_action"] == "domain_status"
    assert result["applied_inventory_sha256"] == result["prospective_inventory_sha256"]
    validate_document(result, RESULT_SCHEMA)


def test_apply_record_review_successor_and_idempotent(world):
    vault_before = _snapshot(world["vault"])
    authority_before = _authority_bytes(world)
    work_before = _snapshot(world["checkout"] / ".work")
    audit_before = _audit_keys(world["vault"])
    first = _record(world, valid_proposal(world), name="g.json", batch="g1")
    _compile(world, "g1")
    work_after_compile = _snapshot(world["checkout"] / ".work")
    assert work_after_compile != work_before
    result = _apply(world, "g1")
    _consts(result)
    assert result["heads_mode"] == "create"
    assert result["heads_before_sha256"] is None
    lid = first["record"]["lineage_id"]
    aid = first["record"]["annotation_id"]
    annotation = world["vault"] / "wiki/meta/domain/annotations" / lid / (aid + ".json")
    heads = world["vault"] / "wiki/meta/domain/heads.json"
    assert annotation.is_file()
    assert heads.is_file()
    assert _mode(annotation) == 0o600
    assert _mode(heads) == 0o600
    assert _mode(world["vault"] / "wiki/meta/domain") == 0o700
    assert _mode(world["vault"] / "wiki/meta/domain/annotations") == 0o700
    assert _mode(world["vault"] / "wiki/meta/domain/annotations" / lid) == 0o700
    store, loaded_heads, _authority = load_domain_store(str(world["vault"]))
    assert aid in store.annotations
    status = status_domain_store(vault_root=str(world["vault"]))
    assert any(row["lineage_id"] == lid for row in status["lineages"])
    assert _authority_bytes(world)["ledger"] == authority_before["ledger"]
    assert _authority_bytes(world)["heads"] == authority_before["heads"]
    assert _authority_bytes(world)["reviews"] == authority_before["reviews"]
    assert _authority_bytes(world)["taxonomy"] == authority_before["taxonomy"]
    assert _snapshot(world["checkout"] / ".work") == work_after_compile
    assert _audit_keys(world["vault"]) == audit_before
    old_heads = heads.read_bytes()
    review = _review(world, _decision_for(world, first, officiality="official"), batch="r1")
    _compile(world, "r1")
    reviewed = _apply(world, "r1")
    _consts(reviewed)
    assert reviewed["heads_mode"] == "replace"
    assert reviewed["heads_before_sha256"] == sha(old_heads)
    review_path = (
        world["vault"]
        / "wiki/meta/domain/reviews"
        / review["record"]["lineage_id"]
        / (review["record"]["review_id"] + ".json")
    )
    assert review_path.is_file()
    assert _mode(review_path) == 0o600
    assert _mode(world["vault"] / "wiki/meta/domain/reviews") == 0o700
    successor = _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="s1",
    )
    _compile(world, "s1")
    successor_result = _apply(world, "s1")
    _consts(successor_result)
    assert successor_result["heads_mode"] == "replace"
    assert successor["record"]["annotation_id"] in load_domain_store(str(world["vault"]))[0].annotations
    vault_applied = _snapshot(world["vault"])
    err = _expect(lambda: _apply(world, "s1"), "DOMAIN_APPLY_ALREADY_APPLIED")
    assert err.details["next_action"] == "discard_batch"
    assert _snapshot(world["vault"]) == vault_applied
    domain = world["vault"] / "wiki/meta/domain"
    saved = {}
    for path in domain.rglob("*"):
        if path.is_file():
            saved[path.relative_to(domain).as_posix()] = path.read_bytes()
            path.unlink()
    for path in sorted((p for p in domain.rglob("*") if p.is_dir()), reverse=True):
        path.rmdir()
    domain.rmdir()
    restored = _apply(world, "g1")
    assert canonicalize(result) == canonicalize(restored)


def test_apply_refusals_from_valid_batch(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="c1")
    _compile(world, "c1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    err = _expect(lambda: _apply(world, "c1", confirm=lambda _s: False), "HUMAN_APPROVAL_REQUIRED")
    assert err.details["next_action"] == "confirm_interactively"
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    err = _expect(
        lambda: apply_domain_publication(
            prepared=str(world["checkout"] / "proposal.json"),
            vault_root=str(world["vault"]),
            confirm=lambda _s: True,
        ),
        "WORK_PATH_UNSAFE",
    )
    assert err.details["next_action"] == "repair_input"
    request_path = world["checkout"] / ".work/c1/domain-publication/request.json"
    request = json.loads(request_path.read_bytes())
    content_dir = world["checkout"] / ".work/c1/domain-publication/content"
    digest = request["payloads"][0]["after_sha256"]
    content_path = content_dir / digest
    original = content_path.read_bytes()
    content_path.write_bytes(original + b"x")
    os.chmod(content_path, 0o600)
    _expect(lambda: _apply(world, "c1"), "DOMAIN_PUBLICATION_CONTENT_MISMATCH")
    content_path.write_bytes(original)
    os.chmod(content_path, 0o600)
    extra = content_dir / ("c" * 64)
    extra.write_bytes(b"{}")
    os.chmod(extra, 0o600)
    _expect(lambda: _apply(world, "c1"), "DOMAIN_PUBLICATION_CONTENT_MISMATCH")
    extra.unlink()
    _write(request_path, json.dumps(request, indent=2).encode("utf-8"))
    _expect(lambda: _apply(world, "c1"), "DOMAIN_PUBLICATION_INVALID")
    _write(request_path, canonicalize(request))
    other = _add_code_batch(world, "aplo", repository="Apl/Other")
    other_proposal = _proposal_from(world, other, repository="Apl/Other")
    _record(world, other_proposal, name="o.json", batch="c2")
    _compile(world, "c2")
    _apply(world, "c2")
    err = _expect(lambda: _apply(world, "c1"), "DOMAIN_PUBLICATION_STALE")
    assert err.exit_code == 75
    assert err.details["next_action"] == "recompile"

    _record(world, valid_proposal(world), name="g2.json", batch="chg")
    _compile(world, "chg")
    request_chg = world["checkout"] / ".work/chg/domain-publication/request.json"
    original_request = request_chg.read_bytes()
    vault_mid = _snapshot(world["vault"])

    def replace_request(_summary):
        request_chg.write_bytes(b"{}\n")
        os.chmod(request_chg, 0o600)
        return True

    err = _expect(lambda: _apply(world, "chg", confirm=replace_request), "DOMAIN_APPLY_CHANGED")
    assert err.exit_code == 75
    assert _snapshot(world["vault"]) == vault_mid
    _write(request_chg, original_request)


def test_apply_changed_vault_and_faults(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="f1")
    _compile(world, "f1")
    request = _request(world, "f1")
    request_path = world["checkout"] / ".work/f1/domain-publication/request.json"
    _write(request_path, canonicalize(request))
    vault_before = _snapshot(world["vault"])

    def add_domain_file(_summary):
        target = world["vault"] / "wiki/meta/domain"
        target.mkdir(parents=True, exist_ok=True)
        extra = target / "extra.json"
        extra.write_bytes(b"{}")
        os.chmod(extra, 0o600)
        return True

    err = _expect(lambda: _apply(world, "f1", confirm=add_domain_file), "DOMAIN_APPLY_CHANGED")
    assert err.exit_code == 75
    lid = first["record"]["lineage_id"]
    aid = first["record"]["annotation_id"]
    assert not (world["vault"] / "wiki/meta/domain/annotations" / lid / (aid + ".json")).exists()
    extra = world["vault"] / "wiki/meta/domain/extra.json"
    extra.unlink()
    domain_dir = world["vault"] / "wiki/meta/domain"
    if domain_dir.exists() and not any(domain_dir.iterdir()):
        domain_dir.rmdir()
    assert not (world["vault"] / "wiki/meta/domain/annotations").exists()

    def boom(_phase):
        raise OSError("synthetic before-create")

    err = _expect(lambda: _apply(world, "f1", _fault=boom), "DOMAIN_APPLY_WRITE_FAILED")
    assert err.details["rollback_complete"] is True
    assert err.details["phase"] == "before-create"
    assert not (world["vault"] / "wiki/meta/domain/annotations").exists()
    result = _apply(world, "f1")
    _consts(result)
    old_heads = (world["vault"] / "wiki/meta/domain/heads.json").read_bytes()
    _review(world, _decision_for(world, first, officiality="official"), batch="f1r")
    _compile(world, "f1r")
    vault_pre_review = _snapshot(world["vault"])

    def replace_heads(phase):
        if phase != "before-commit":
            return
        path = world["vault"] / "wiki/meta/domain/heads.json"
        path.write_bytes(b'{"tampered":true}')
        os.chmod(path, 0o600)

    err = _expect(lambda: _apply(world, "f1r", _fault=replace_heads), "DOMAIN_APPLY_VAULT_INVALID")
    assert err.details.get("reason") == "heads_before"
    assert err.details["rollback_complete"] is True
    review_root = world["vault"] / "wiki/meta/domain/reviews"
    assert not review_root.exists() or not any(review_root.rglob("*.json"))
    (world["vault"] / "wiki/meta/domain/heads.json").write_bytes(old_heads)
    os.chmod(world["vault"] / "wiki/meta/domain/heads.json", 0o600)
    pre_files = {key: (value[0], value[1]) for key, value in vault_pre_review.items()}
    post_files = {key: (value[0], value[1]) for key, value in _snapshot(world["vault"]).items()}
    assert pre_files == post_files

    def after_commit(phase):
        if phase != "after-commit":
            return
        path = world["vault"] / "wiki/meta/domain" / "notes.txt"
        path.write_bytes(b"unknown")
        os.chmod(path, 0o600)

    err = _expect(lambda: _apply(world, "f1r", _fault=after_commit), "DOMAIN_APPLY_VERIFY_FAILED")
    assert err.details.get("phase") == "after-commit"
    assert (world["vault"] / "wiki/meta/domain" / "notes.txt").is_file()
    with pytest.raises(DomainStoreError) as status_err:
        status_domain_store(vault_root=str(world["vault"]))
    assert status_err.value.code == "DOMAIN_STORE_INVALID"


def test_apply_write_phase_oserror_unlinks_orphan(world, monkeypatch):
    first = _record(world, valid_proposal(world), name="g.json", batch="g1")
    _compile(world, "g1")
    _apply(world, "g1")
    successor = _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="s1",
    )
    _compile(world, "s1")
    lid = first["record"]["lineage_id"]
    aid = successor["record"]["annotation_id"]
    relative = "wiki/meta/domain/annotations/" + lid + "/" + aid + ".json"
    orphan = world["vault"] / relative
    assert (world["vault"] / "wiki/meta/domain/annotations" / lid).is_dir()
    vault_before = _snapshot(world["vault"])
    real_write = domain_apply.os.write

    def write_fail(fd, data):
        try:
            path = os.readlink("/proc/self/fd/" + str(int(fd)))
        except OSError:
            path = ""
        if "wiki/meta/domain/annotations/" in path.replace("\\", "/"):
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write(fd, data)

    monkeypatch.setattr(domain_apply.os, "write", write_fail)
    err = _expect(lambda: _apply(world, "s1"), "DOMAIN_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "write"
    assert err.details.get("errno") == errno.ENOSPC
    assert relative in err.details["rolled_back"]
    assert err.details["rollback_complete"] is True
    assert not orphan.exists()
    assert _snapshot(world["vault"]) == vault_before


def test_apply_head_stale_and_review_invalid(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="h1")
    _compile(world, "h1")
    _apply(world, "h1")
    _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="h2",
    )
    _compile(world, "h2")
    kind, claim, old_event = world["annotated"][0]
    from tests.source_semantics_fixture import event_for

    new_event = event_for(claim, previous=old_event, human=True, state="contested")
    event_path = (
        world["vault"] / "wiki/meta/reviews" / claim["claim_id"] / (old_event["event_id"] + ".json")
    )
    _write(event_path, canonicalize(new_event))
    err = _expect(lambda: _apply(world, "h2"), "DOMAIN_HEAD_STALE")
    assert err.details["next_action"] == "re_record_annotation"
    _write(event_path, canonicalize(old_event))

    planted_batch = "onlyc"
    record = first["record"]
    lid = record["lineage_id"]
    body = {
        "schema": "video-paper-wiki.domain-review-record.v1",
        "lineage_id": lid,
        "annotation_id": record["annotation_id"],
        "annotation_sha256": sha(canonicalize(record)),
        "previous_review_id": None,
        "actor_kind": "human",
        "decision": "accepted",
        "decided_by": RECORDED_BY,
        "decided_at": REVIEW_AT,
        "reason": "Synthetic planted review.",
        "relation_review": _relation_review(record["report"], "official", relied=["C"]),
    }
    review_id = review_id_from_record(body)
    review = {"review_id": review_id, **body}
    review_raw = canonicalize(review)
    store, _heads, _authority = load_domain_store(str(world["vault"]))
    store.reviews[review_id] = review
    store.review_raw[review_id] = review_raw
    chain = store.chains[lid]
    store.chains[lid] = {
        "annotation_order": list(chain["annotation_order"]),
        "review_order": list(chain["review_order"]) + [review_id],
    }
    heads_doc = derive_domain_heads(store)
    heads_raw = canonicalize(heads_doc)
    pub = world["checkout"] / ".work" / planted_batch / "domain-publication"
    content = pub / "content"
    content.mkdir(parents=True)
    review_digest = sha(review_raw)
    heads_digest = sha(heads_raw)
    _write(content / review_digest, review_raw)
    _write(content / heads_digest, heads_raw)
    snap = _Snapshot(world["vault"])
    try:
        from video_paper_wiki.domain_publication import _basis, _inventory_digest
        from video_paper_wiki.domain_store import _load_authority, _load_store

        live = _load_store(snap)
        auth = _load_authority(snap, required=True)
        basis = _basis(snap, live, auth)
    finally:
        snap.close()
    request = {
        "schema": "video-paper-wiki.domain-publication-request.v1",
        "batch_id": planted_batch,
        "kind": "domain",
        "basis": basis,
        "prospective_inventory_sha256": "a" * 64,
        "touched_lineages": [lid],
        "payloads": [
            {
                "path": "wiki/meta/domain/reviews/" + lid + "/" + review_id + ".json",
                "mode": "create",
                "before_sha256": None,
                "after_sha256": review_digest,
                "size_bytes": len(review_raw),
                "content_file": "domain-publication/content/" + review_digest,
            },
            {
                "path": "wiki/meta/domain/heads.json",
                "mode": "replace",
                "before_sha256": sha((world["vault"] / "wiki/meta/domain/heads.json").read_bytes()),
                "after_sha256": heads_digest,
                "size_bytes": len(heads_raw),
                "content_file": "domain-publication/content/" + heads_digest,
            },
        ],
        "publication": "unpublished",
        "applied": False,
        "receipt_backed": False,
        "audit_coverage": "not_wired",
        "transaction_authority": "not_wired",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": "inspect_domain_publication",
    }
    request["payloads"].sort(key=lambda item: item["path"].encode("utf-8"))
    _write(pub / "request.json", canonicalize(request))
    err = _expect(lambda: _apply(world, planted_batch), "DOMAIN_REVIEW_INVALID")
    assert err.details["next_action"] == "repair_review"


def test_apply_product_flow_and_stale_inspect(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="p1")
    compiled = _compile(world, "p1")
    inspection = _inspect(world, "p1")
    validate_document(inspection, "video-paper-wiki.domain-publication-inspection.v1")
    applied = _apply(world, "p1")
    _consts(applied)
    err = _expect(lambda: _inspect(world, "p1"), "DOMAIN_PUBLICATION_STALE")
    assert err.exit_code == 75
    review = _review(world, _decision_for(world, first, officiality="official"), batch="p1r")
    _compile(world, "p1r")
    _inspect(world, "p1r")
    reviewed = _apply(world, "p1r")
    _consts(reviewed)
    status = status_domain_store(vault_root=str(world["vault"]))
    assert status["canonical_official"] is False
    assert status["current_supported_typed_fact"] is False
    assert any(row["lineage_id"] == first["record"]["lineage_id"] for row in status["lineages"])
    err = _expect(lambda: _inspect(world, "p1r"), "DOMAIN_PUBLICATION_STALE")
    assert err.exit_code == 75
    assert compiled["applied"] is False
    assert review["publication"] == "unpublished"


def test_apply_zero_network_and_result_bytes(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    first = _record(world, valid_proposal(world), name="n.json", batch="net")
    _compile(world, "net")
    work_before = _snapshot(world["checkout"] / ".work")
    first_result = _apply(world, "net")
    second_denied = _expect(lambda: _apply(world, "net"), "DOMAIN_APPLY_ALREADY_APPLIED")
    assert second_denied.details["next_action"] == "discard_batch"
    assert _snapshot(world["checkout"] / ".work") == work_before
    domain = world["vault"] / "wiki/meta/domain"
    for path in sorted(domain.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()
    domain.rmdir()
    again = _apply(world, "net")
    assert canonicalize(first_result) == canonicalize(again)
    assert first["publication"] == "unpublished"
