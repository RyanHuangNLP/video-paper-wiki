from __future__ import annotations

import errno
import json
import os
import socket
import stat

import pytest

from tests.unit.test_domain_proposal import _snapshot, _write, make_world
from tests.unit.test_domain_store import LATER_AT
from tests.unit.test_experiment_store import (
    _record_exp,
    _status,
    valid_condition_input,
)
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import DomainStoreError, status_domain_store
from video_paper_wiki.domain_versions import build_domain_source_version_view
from video_paper_wiki.experiment_apply import ExperimentApplyError, apply_experiment_publication
from video_paper_wiki import experiment_apply as experiment_apply_mod
from video_paper_wiki.experiment_publication import (
    ExperimentPublicationError,
    compile_experiment_publication,
)
from video_paper_wiki.experiment_store import ExperimentStoreError, load_experiment_store
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import _Snapshot, _walk_inventory
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

RESULT_SCHEMA = "video-paper-wiki.experiment-publication-apply-result.v1"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _compile(world, batch):
    return compile_experiment_publication(vault_root=str(world["vault"]), batch_id=batch)


def _prepared(world, batch):
    return str(world["checkout"] / ".work" / batch / "experiment-publication" / "request.json")


def _apply_exp(world, batch, *, confirm=None, _fault=None):
    if confirm is None:
        confirm = lambda _summary: True
    return apply_experiment_publication(
        prepared=_prepared(world, batch),
        vault_root=str(world["vault"]),
        confirm=confirm,
        _fault=_fault,
    )


def _expect(fn, code):
    with pytest.raises(
        (
            ExperimentApplyError,
            ExperimentPublicationError,
            ExperimentStoreError,
            DomainStoreError,
            StagingError,
            ContractError,
        )
    ) as err:
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


def _mode(path) -> int:
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
    assert result["typed_fact_promotion"] == "none"
    assert result["ranking"] == "not_ranked"
    assert result["next_action"] == "experiments_status"
    assert result["applied_inventory_sha256"] == result["prospective_inventory_sha256"]
    validate_document(result, RESULT_SCHEMA)


def test_apply_positive_create_and_idempotent(world):
    vault_before = _snapshot(world["vault"])
    domain_before = status_domain_store(vault_root=str(world["vault"]))
    view_before = build_domain_source_version_view(vault_root=str(world["vault"]))
    first = _record_exp(world, batch="p1")
    compiled = _compile(world, "p1")
    work_before_apply = _snapshot(world["checkout"] / ".work")
    audit_before = _audit_keys(world["vault"])
    captured = {}

    def confirm(summary):
        captured["summary"] = summary
        return True

    result = _apply_exp(world, "p1", confirm=confirm)
    _consts(result)
    assert result["heads_mode"] == "create"
    assert result["heads_before_sha256"] is None
    assert result["payload_count"] == 2
    cid = first["record"]["condition_id"]
    rid = first["record"]["record_id"]
    record_path = world["vault"] / "wiki/meta/experiments/records" / cid / (rid + ".json")
    heads = world["vault"] / "wiki/meta/experiments/heads.json"
    assert record_path.is_file()
    assert heads.is_file()
    assert result["applied_paths"] == compiled["changed_paths"]
    assert len(result["applied_paths"]) == 2
    content_root = world["checkout"] / ".work/p1/experiment-publication/content"
    assert record_path.read_bytes() == (content_root / sha(record_path.read_bytes())).read_bytes()
    assert heads.read_bytes() == (content_root / sha(heads.read_bytes())).read_bytes()
    assert _mode(record_path) == 0o600
    assert _mode(heads) == 0o600
    assert _mode(world["vault"] / "wiki/meta/experiments") == 0o700
    assert _mode(world["vault"] / "wiki/meta/experiments/records") == 0o700
    assert _mode(world["vault"] / "wiki/meta/experiments/records" / cid) == 0o700
    assert not list((world["vault"] / "wiki/meta/experiments").glob(".heads.json.*.tmp"))
    store, loaded_heads, _authority = load_experiment_store(str(world["vault"]))
    assert rid in store.records
    assert len(loaded_heads["heads"]) == 1
    status = _status(world)
    assert status["conditions"][0]["record_count"] == 1
    assert status["conditions"][0]["record_status"] == "current"
    assert status["next_action"] == "none"
    domain_after = status_domain_store(vault_root=str(world["vault"]))
    view_after = build_domain_source_version_view(vault_root=str(world["vault"]))
    assert canonicalize(domain_before) == canonicalize(domain_after)
    assert canonicalize(view_before) == canonicalize(view_after)
    assert _audit_keys(world["vault"]) == audit_before
    assert _snapshot(world["checkout"] / ".work") == work_before_apply
    summary = captured["summary"]
    for key in (
        "batch_id",
        "request_sha256",
        "basis",
        "prospective_inventory_sha256",
        "heads_mode",
        "heads_before_sha256",
        "touched_conditions",
        "changed_paths",
        "payload_count",
    ):
        assert key in summary
    assert set(summary["basis"]) == {
        "domain_store_inventory_sha256",
        "claim_ledger_sha256",
        "assessment_heads_sha256",
        "experiment_store_inventory_sha256",
    }
    assert _snapshot(world["vault"]) != vault_before
    err = _expect(lambda: _apply_exp(world, "p1"), "EXPERIMENT_APPLY_ALREADY_APPLIED")
    assert err.details["next_action"] == "discard_batch"


def test_apply_successor_replace_and_second_chain(world):
    first = _record_exp(world, batch="g1")
    _compile(world, "g1")
    _apply_exp(world, "g1")
    old_heads = (world["vault"] / "wiki/meta/experiments/heads.json").read_bytes()
    old_record = (
        world["vault"]
        / "wiki/meta/experiments/records"
        / first["record"]["condition_id"]
        / (first["record"]["record_id"] + ".json")
    )
    old_bytes = old_record.read_bytes()
    old_stamp = old_record.stat()
    changed = valid_condition_input(
        world,
        conditions={
            "resolution": valid_condition_input(world)["conditions"]["resolution"],
        },
    )
    changed["conditions"]["resolution"] = {
        **changed["conditions"]["resolution"],
        "value": {"width": 256, "height": 256},
    }
    second = _record_exp(
        world,
        changed,
        name="succ.json",
        previous=first["record"]["record_id"],
        recorded_at=LATER_AT,
        batch="g2",
    )
    _compile(world, "g2")
    result = _apply_exp(world, "g2")
    _consts(result)
    assert result["heads_mode"] == "replace"
    assert result["heads_before_sha256"] == sha(old_heads)
    assert old_record.read_bytes() == old_bytes
    assert old_record.stat().st_mtime_ns == old_stamp.st_mtime_ns
    new_record = (
        world["vault"]
        / "wiki/meta/experiments/records"
        / second["record"]["condition_id"]
        / (second["record"]["record_id"] + ".json")
    )
    assert new_record.is_file()
    new_heads = (world["vault"] / "wiki/meta/experiments/heads.json").read_bytes()
    assert new_heads != old_heads
    status = _status(world)
    row = next(item for item in status["conditions"] if item["condition_id"] == first["record"]["condition_id"])
    assert row["record_count"] == 2
    other = _record_exp(world, valid_condition_input(world, setting_key="table3-row1-vbench-256"), name="other.json", batch="g3")
    _compile(world, "g3")
    _apply_exp(world, "g3")
    store, heads, _authority = load_experiment_store(str(world["vault"]))
    assert len(heads["heads"]) == 2
    assert other["record"]["record_id"] in store.records


def test_apply_refusals_zero_writes(world):
    first = _record_exp(world, batch="c1")
    _compile(world, "c1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    err = _expect(lambda: _apply_exp(world, "c1", confirm=lambda _s: False), "HUMAN_APPROVAL_REQUIRED")
    assert err.details["next_action"] == "confirm_interactively"
    assert _snapshot(world["vault"]) == vault_before
    extra = world["vault"] / "wiki/meta/experiments/extra.json"

    def tamper(_summary):
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_bytes(b"{}")
        os.chmod(extra, 0o600)
        return True

    err = _expect(lambda: _apply_exp(world, "c1", confirm=tamper), "EXPERIMENT_APPLY_CHANGED")
    assert err.exit_code == 75
    assert err.details["next_action"] == "repeat_apply"
    if extra.exists():
        extra.unlink()
        parent = extra.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    ledger = world["vault"] / CLAIM_LEDGER
    original_ledger = ledger.read_bytes()
    mutated = json.loads(original_ledger)
    mutated["generated_at"] = "2026-09-14T12:00:00Z"
    _write(ledger, canonicalize(mutated))
    err = _expect(lambda: _apply_exp(world, "c1"), "EXPERIMENT_PUBLICATION_STALE")
    assert err.exit_code == 75
    _write(ledger, original_ledger)
    request_path = world["checkout"] / ".work/c1/experiment-publication/request.json"
    request = json.loads(request_path.read_bytes())
    digest = request["payloads"][0]["after_sha256"]
    content_path = world["checkout"] / ".work/c1/experiment-publication/content" / digest
    original = content_path.read_bytes()
    content_path.write_bytes(original + b"x")
    os.chmod(content_path, 0o600)
    _expect(lambda: _apply_exp(world, "c1"), "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH")
    content_path.write_bytes(original)
    os.chmod(content_path, 0o600)
    cid = first["record"]["condition_id"]
    rid = first["record"]["record_id"]
    target = world["vault"] / "wiki/meta/experiments/records" / cid / (rid + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"not-json")
    os.chmod(target, 0o600)
    planted = _expect(lambda: _apply_exp(world, "c1"), "EXPERIMENT_STORE_INVALID")
    assert planted.details.get("next_action")
    target.unlink()
    records_dir = target.parent
    if records_dir.exists() and not any(records_dir.iterdir()):
        records_dir.rmdir()
    parent = records_dir.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
    exp_root = world["vault"] / "wiki/meta/experiments"
    if exp_root.exists() and not any(exp_root.iterdir()):
        exp_root.rmdir()
    link = world["vault"] / "wiki/meta/experiments"
    os.symlink(world["vault"] / "wiki/meta", link)
    _expect(lambda: _apply_exp(world, "c1"), "EXPERIMENT_STORE_INVALID")
    link.unlink()
    empty_heads = {"schema": "video-paper-wiki.experiment-heads.v1", "heads": {}}
    _write(world["vault"] / "wiki/meta/experiments/heads.json", canonicalize(empty_heads))
    err = _expect(lambda: _apply_exp(world, "c1"), "EXPERIMENT_PUBLICATION_STALE")
    assert err.exit_code == 75
    (world["vault"] / "wiki/meta/experiments/heads.json").unlink()
    if (world["vault"] / "wiki/meta/experiments").exists() and not any((world["vault"] / "wiki/meta/experiments").iterdir()):
        (world["vault"] / "wiki/meta/experiments").rmdir()
    meta = world["vault"] / "wiki/meta"
    saved = []
    for path in sorted(meta.rglob("*"), reverse=True):
        saved.append(path)
    # missing parent: rename wiki/meta out of the way
    moved = world["vault"] / "wiki-meta-saved"
    meta.rename(moved)
    err = _expect(lambda: _apply_exp(world, "c1"), "DOMAIN_STORE_INVALID")
    moved.rename(meta)
    err = _expect(
        lambda: apply_experiment_publication(
            prepared=str(world["checkout"] / ".work/c1/domain-publication/request.json"),
            vault_root=str(world["vault"]),
            confirm=lambda _s: True,
        ),
        "WORK_PATH_UNSAFE",
    )
    assert err.details["next_action"] == "repair_input"
    reviews = world["vault"] / "wiki/meta/experiments/reviews"
    reviews.mkdir(parents=True)
    _expect(lambda: _apply_exp(world, "c1"), "EXPERIMENT_STORE_INVALID")
    reviews.rmdir()
    if (world["vault"] / "wiki/meta/experiments").exists() and not any((world["vault"] / "wiki/meta/experiments").iterdir()):
        (world["vault"] / "wiki/meta/experiments").rmdir()
    work_after = _snapshot(world["checkout"] / ".work")
    assert {key: value[0] for key, value in work_after.items()} == {key: value[0] for key, value in work_before.items()}


def test_apply_replace_heads_mismatch_and_faults(world, monkeypatch):
    first = _record_exp(world, batch="f1")
    _compile(world, "f1")
    vault_before = _snapshot(world["vault"])

    def boom(_phase):
        raise OSError("synthetic before-create")

    err = _expect(lambda: _apply_exp(world, "f1", _fault=boom), "EXPERIMENT_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "before-create"
    assert err.details["rolled_back"] == []
    assert err.details["rollback_complete"] is True
    assert _snapshot(world["vault"]) == vault_before
    result = _apply_exp(world, "f1")
    _consts(result)
    changed = valid_condition_input(world)
    changed["conditions"]["resolution"] = {
        **changed["conditions"]["resolution"],
        "value": {"width": 256, "height": 256},
    }
    _record_exp(
        world,
        changed,
        name="succ.json",
        previous=first["record"]["record_id"],
        recorded_at=LATER_AT,
        batch="f2",
    )
    _compile(world, "f2")
    heads_path = world["vault"] / "wiki/meta/experiments/heads.json"
    original_heads = heads_path.read_bytes()
    _write(heads_path, canonicalize({"schema": "video-paper-wiki.experiment-heads.v1", "heads": {}}))
    err = _expect(lambda: _apply_exp(world, "f2"), "EXPERIMENT_STORE_HEADS_MISMATCH")
    _write(heads_path, original_heads)
    vault_pre_write = _snapshot(world["vault"])
    real_write = experiment_apply_mod.os.write

    def write_fail(fd, data):
        try:
            path = os.readlink("/proc/self/fd/" + str(int(fd)))
        except OSError:
            path = ""
        if "wiki/meta/experiments/records/" in path.replace("\\", "/"):
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write(fd, data)

    monkeypatch.setattr(experiment_apply_mod.os, "write", write_fail)
    err = _expect(lambda: _apply_exp(world, "f2"), "EXPERIMENT_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "write"
    assert err.details["rollback_complete"] is True
    monkeypatch.setattr(experiment_apply_mod.os, "write", real_write)
    assert _snapshot(world["vault"]) == vault_pre_write

    def before_commit(phase):
        if phase != "before-commit":
            return
        raise OSError("synthetic before-commit")

    err = _expect(lambda: _apply_exp(world, "f2", _fault=before_commit), "EXPERIMENT_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "before-commit"
    assert not list((world["vault"] / "wiki/meta/experiments").glob(".heads.json.*.tmp"))
    assert _snapshot(world["vault"]) == vault_pre_write

    def after_commit(phase):
        if phase != "after-commit":
            return
        raise OSError("synthetic after-commit")

    err = _expect(lambda: _apply_exp(world, "f2", _fault=after_commit), "EXPERIMENT_APPLY_VERIFY_FAILED")
    assert err.details["phase"] == "after-commit"
    new_rid = json.loads((world["checkout"] / ".work/f2/experiment-publication/request.json").read_bytes())
    load_experiment_store(str(world["vault"]))
    _expect(lambda: _apply_exp(world, "f2"), "EXPERIMENT_APPLY_ALREADY_APPLIED")

    other = _record_exp(world, valid_condition_input(world, setting_key="table3-row1-vbench-256"), name="o.json", batch="f3")
    _compile(world, "f3")

    def stamp_tamper(phase):
        if phase != "after-commit":
            return
        src = world["vault"] / world["association"]["raw"]["path"]
        src.write_bytes(src.read_bytes() + b"x")
        os.chmod(src, 0o600)

    err = _expect(lambda: _apply_exp(world, "f3", _fault=stamp_tamper), "EXPERIMENT_APPLY_VERIFY_FAILED")
    assert err.details.get("reason") == "file_stamp"
    src = world["vault"] / world["association"]["raw"]["path"]
    src.write_bytes(src.read_bytes()[:-1])
    os.chmod(src, 0o600)
    # restore f3 not applied? after-commit already wrote. Clean by not reusing f3.
    other_key = valid_condition_input(world, setting_key="table4-row1-vbench-128")
    _record_exp(world, other_key, name="o4.json", batch="f4")
    _compile(world, "f4")

    def domain_tamper(phase):
        if phase != "after-commit":
            return
        notes = world["vault"] / "wiki/meta/domain/notes.txt"
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_bytes(b"nope")
        os.chmod(notes, 0o600)

    err = _expect(lambda: _apply_exp(world, "f4", _fault=domain_tamper), "EXPERIMENT_APPLY_VERIFY_FAILED")
    assert err.details.get("reason") in {"domain_store", None} or err.details.get("prior_code") == "DOMAIN_STORE_INVALID"
    if err.details.get("reason") != "domain_store":
        assert err.details.get("prior_code") == "DOMAIN_STORE_INVALID"


def test_apply_genesis_write_rollback_removes_experiments_dir(world, monkeypatch):
    _record_exp(world, batch="r1")
    _compile(world, "r1")
    vault_before = _snapshot(world["vault"])
    real_write = experiment_apply_mod.os.write

    def write_fail(fd, data):
        try:
            path = os.readlink("/proc/self/fd/" + str(int(fd)))
        except OSError:
            path = ""
        if "wiki/meta/experiments/records/" in path.replace("\\", "/"):
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write(fd, data)

    monkeypatch.setattr(experiment_apply_mod.os, "write", write_fail)
    err = _expect(lambda: _apply_exp(world, "r1"), "EXPERIMENT_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "write"
    assert err.details["rollback_complete"] is True
    assert not (world["vault"] / "wiki/meta/experiments").exists()
    assert _snapshot(world["vault"]) == vault_before


def test_apply_zero_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    _record_exp(world, batch="net")
    _compile(world, "net")
    _apply_exp(world, "net")
