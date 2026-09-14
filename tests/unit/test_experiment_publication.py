from __future__ import annotations

import json
import os
import socket

import pytest

from tests.source_semantics_fixture import event_for
from tests.unit.test_domain_proposal import _snapshot, _write, make_world
from tests.unit.test_domain_store import LATER_AT
from tests.unit.test_domain_versions import _reseal_association
from tests.unit.test_experiment_apply import _apply_exp
from tests.unit.test_experiment_store import (
    _empirical,
    _publish_lineage,
    _record_exp,
    _status,
    valid_condition_input,
)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.experiment_publication import (
    ExperimentPublicationError,
    compile_experiment_publication,
    inspect_experiment_publication,
)
from video_paper_wiki.experiment_store import (
    ExperimentStoreError,
    experiment_inventory_digest,
    load_experiment_store,
    record_id_from_record,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

REQUEST_SCHEMA = "video-paper-wiki.experiment-publication-request.v1"
INSPECTION_SCHEMA = "video-paper-wiki.experiment-publication-inspection.v1"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _compile(world, batch):
    return compile_experiment_publication(vault_root=str(world["vault"]), batch_id=batch)


def _inspect(world, batch):
    prepared = world["checkout"] / ".work" / batch / "experiment-publication" / "request.json"
    return inspect_experiment_publication(prepared=str(prepared), vault_root=str(world["vault"]))


def _request(world, batch):
    path = world["checkout"] / ".work" / batch / "experiment-publication" / "request.json"
    return json.loads(path.read_bytes())


def _expect(fn, code):
    with pytest.raises((ExperimentPublicationError, ExperimentStoreError, DomainStoreError, StagingError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    if code not in {"WORK_PATH_UNSAFE", "STAGING_CONFLICT"}:
        assert details.get("instance_pointer") is not None
        assert details.get("next_action")
    return err.value


def _copy_staged_experiments(world, src, dst):
    src_root = world["checkout"] / ".work" / src / "experiments"
    dst_root = world["checkout"] / ".work" / dst / "experiments"
    for path in src_root.rglob("*"):
        if path.is_file():
            _write(dst_root / path.relative_to(src_root), path.read_bytes())


def _experiments_snapshot(world, batch):
    root = world["checkout"] / ".work" / batch / "experiments"
    if not root.exists():
        return {}
    return _snapshot(root)


def test_compile_positive_example(world):
    first = _record_exp(world, batch="p1")
    vault_before = _snapshot(world["vault"])
    experiments_before = _experiments_snapshot(world, "p1")
    work_root = world["checkout"] / ".work"
    outside_before = {
        str(path.relative_to(work_root)): path.read_bytes()
        for path in work_root.rglob("*")
        if path.is_file() and path.relative_to(work_root).parts[:2] != ("p1", "experiment-publication")
    }
    data = _compile(world, "p1")
    assert data["state"] == "experiment_publication_prepared"
    assert data["payload_count"] == 2
    cid = first["record"]["condition_id"]
    rid = first["record"]["record_id"]
    rec_path = "wiki/meta/experiments/records/" + cid + "/" + rid + ".json"
    assert data["changed_paths"] == sorted([rec_path, "wiki/meta/experiments/heads.json"], key=lambda item: item.encode("utf-8"))
    assert data["touched_conditions"] == [cid]
    status = _status(world)
    assert data["basis"] == status["basis"]
    request_path = world["checkout"] / ".work/p1/experiment-publication/request.json"
    assert request_path.is_file()
    request = json.loads(request_path.read_bytes())
    validate_document(request, REQUEST_SCHEMA)
    assert sha(request_path.read_bytes()) == data["request_sha256"]
    content = world["checkout"] / ".work/p1/experiment-publication/content"
    files = sorted(p.name for p in content.iterdir() if p.is_file())
    assert len(files) == 2
    for name in files:
        raw = (content / name).read_bytes()
        assert sha(raw) == name
    by_path = {item["path"]: item for item in request["payloads"]}
    assert by_path["wiki/meta/experiments/heads.json"]["mode"] == "create"
    assert by_path["wiki/meta/experiments/heads.json"]["before_sha256"] is None
    _copy_staged_experiments(world, "p1", "applied-check")
    from tests.unit.test_experiment_store import _apply_staged_experiments

    _apply_staged_experiments(world, "applied-check")
    store, _heads, _authority = load_experiment_store(str(world["vault"]))
    assert data["prospective_inventory_sha256"] == experiment_inventory_digest(store)
    # restore empty experiments store
    exp_root = world["vault"] / "wiki/meta/experiments"
    for path in sorted(exp_root.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()
    assert _snapshot(world["vault"]) == vault_before
    assert _experiments_snapshot(world, "p1") == experiments_before
    pub_root = world["checkout"] / ".work/p1/experiment-publication"
    assert pub_root.is_dir()
    work_after_compile = {
        str(path.relative_to(work_root)): path.read_bytes()
        for path in work_root.rglob("*")
        if path.is_file() and path.relative_to(work_root).parts[:2] != ("p1", "experiment-publication")
        and path.relative_to(work_root).parts[:1] != ("applied-check",)
    }
    assert work_after_compile == outside_before
    _expect(lambda: _compile(world, "p1"), "STAGING_CONFLICT")
    _copy_staged_experiments(world, "p1", "p1b")
    other = _compile(world, "p1b")
    left = dict(_request(world, "p1"))
    right = dict(_request(world, "p1b"))
    left.pop("batch_id")
    right.pop("batch_id")
    assert left == right
    assert other["batch_id"] == "p1b"


def test_compile_successor_replace_already_published_genesis_and_stale(world):
    first = _record_exp(world, batch="p1")
    _compile(world, "p1")
    _apply_exp(world, "p1")
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
        batch="p2",
    )
    compiled = _compile(world, "p2")
    request = _request(world, "p2")
    heads = next(item for item in request["payloads"] if item["path"].endswith("heads.json"))
    assert heads["mode"] == "replace"
    assert heads["before_sha256"] == sha((world["vault"] / "wiki/meta/experiments/heads.json").read_bytes())
    _apply_exp(world, "p2")
    store, _heads, _authority = load_experiment_store(str(world["vault"]))
    assert compiled["prospective_inventory_sha256"] == experiment_inventory_digest(store)
    _copy_staged_experiments(world, "p1", "p3")
    err = _expect(lambda: _compile(world, "p3"), "EXPERIMENT_COMPILE_ALREADY_PUBLISHED")
    assert err.details["next_action"] == "discard_batch"
    planted_batch = "p4"
    src = world["checkout"] / ".work/p1/experiments"
    dst = world["checkout"] / ".work" / planted_batch / "experiments"
    for path in src.rglob("*"):
        if path.is_file():
            _write(dst / path.relative_to(src), path.read_bytes())
    record_file = next((dst / "records").rglob("*.json"))
    doc = json.loads(record_file.read_bytes())
    doc["recorded_at"] = "2026-09-14T02:00:00Z"
    from video_paper_wiki.experiment_store import content_sha256_from_record, record_id_from_record

    body = {key: value for key, value in doc.items() if key != "record_id"}
    new_id = record_id_from_record(body)
    body["record_id"] = new_id
    body["content_sha256"] = content_sha256_from_record(body)
    raw = canonicalize(body)
    record_file.unlink()
    _write(record_file.parent / (new_id + ".json"), raw)
    heads_doc = {
        "schema": "video-paper-wiki.experiment-heads.v1",
        "heads": {doc["condition_id"]: {"record_id": new_id, "record_sha256": sha(raw)}},
    }
    _write(dst / "heads.json", canonicalize(heads_doc))
    err = _expect(lambda: _compile(world, planted_batch), "EXPERIMENT_STORE_CHAIN_INVALID")
    assert err.details.get("reason") == "genesis"
    pending = valid_condition_input(world, setting_key="table5-row1-vbench-64")
    _record_exp(world, pending, name="pending.json", batch="p6")
    other = _record_exp(world, valid_condition_input(world, setting_key="table3-row1-vbench-256"), name="other.json", batch="p5")
    _compile(world, "p5")
    _apply_exp(world, "p5")
    err = _expect(lambda: _compile(world, "p6"), "EXPERIMENT_COMPILE_STALE")
    assert err.exit_code == 75


def test_compile_input_failures(world):
    _expect(lambda: _compile(world, "missing"), "EXPERIMENT_COMPILE_INVALID")
    first = _record_exp(world, batch="c1")
    domain = world["checkout"] / ".work/c1/experiments"
    reviews = domain / "reviews"
    reviews.mkdir()
    err = _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_INVALID")
    assert err.details["reason"] == "unknown_entry"
    reviews.rmdir()
    notes = domain / "notes.txt"
    notes.write_text("nope", encoding="utf-8")
    os.chmod(notes, 0o600)
    err = _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_INVALID")
    assert err.details["reason"] == "unknown_entry"
    notes.unlink()
    heads = domain / "heads.json"
    heads_bytes = heads.read_bytes()
    heads.unlink()
    err = _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_INVALID")
    assert err.details["reason"] == "missing"
    _write(heads, heads_bytes)
    record = next(domain.joinpath("records").rglob("*.json"))
    record_bytes = record.read_bytes()
    lineage = record.parent
    record.unlink()
    lineage.rmdir()
    _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_EMPTY")
    _write(record, record_bytes)
    renamed = record.parent / ("exr-" + "a" * 20 + ".json")
    record.rename(renamed)
    err = _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_INVALID")
    assert err.details["reason"] == "path_identity"
    renamed.rename(record)
    _write(record, json.dumps(json.loads(record_bytes), indent=2).encode("utf-8"))
    err = _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_INVALID")
    assert err.details["reason"] == "canonical_bytes"
    _write(record, record_bytes)
    mutated = json.loads(record_bytes)
    mutated["content_sha256"] = "d" * 64
    new_id = record_id_from_record(mutated)
    mutated["record_id"] = new_id
    new_record = record.parent / (new_id + ".json")
    record.unlink()
    _write(new_record, canonicalize(mutated))
    err = _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_INVALID")
    assert err.details["reason"] == "content_sha256"
    new_record.unlink()
    _write(record, record_bytes)
    link = record.parent / ("exr-" + "c" * 20 + ".json")
    os.symlink(record, link)
    err = _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_INVALID")
    assert err.details["reason"] == "symlink"
    link.unlink()
    _write(heads, canonicalize({"schema": "video-paper-wiki.experiment-heads.v1", "heads": {}}))
    _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_STALE")
    _write(heads, heads_bytes)
    huge = record.parent / ("exr-" + "e" * 20 + ".json")
    huge.write_bytes(b"x" * (1048576 + 1))
    os.chmod(huge, 0o600)
    _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_LIMIT")
    huge.unlink()
    import video_paper_wiki.experiment_publication as publication

    original = publication.MAX_STAGED_RECORDS
    publication.MAX_STAGED_RECORDS = 1
    try:
        extra = record.parent / ("exr-" + "f" * 20 + ".json")
        extra.write_bytes(record_bytes)
        os.chmod(extra, 0o600)
        _expect(lambda: _compile(world, "c1"), "EXPERIMENT_COMPILE_LIMIT")
        extra.unlink()
    finally:
        publication.MAX_STAGED_RECORDS = original
    assert first["record"]["record_id"]


def test_compile_rebind_after_vault_change(world):
    first = _record_exp(world, batch="b1")
    assoc_path = world["vault"] / "wiki/meta/records/source-versions" / (world["association"]["association_id"] + ".json")
    original = assoc_path.read_bytes()
    mutated = json.loads(original)
    mutated["observation"]["title"] = "Rewritten"
    _resealed, mismatch_raw = _reseal_association(mutated)
    _write(assoc_path, mismatch_raw)
    err = _expect(lambda: _compile(world, "b1"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "source_association"
    assert err.details["reason"] == "sha256"
    assert err.details["record_id"] == first["record"]["record_id"]
    _write(assoc_path, original)
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os.chmod(src_path, 0o600)
    err = _expect(lambda: _compile(world, "b1"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "source_digest"
    src_path.write_bytes(src_original)
    os.chmod(src_path, 0o600)
    art_rel = first["record"]["conditions"]["model_checkpoint"]["sources"][0]["locator"]["artifact_path"]
    art_path = world["vault"] / art_rel
    art_bytes = art_path.read_bytes()
    art_path.unlink()
    err = _expect(lambda: _compile(world, "b1"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "paper_direct"
    assert err.details["reason"] == "missing"
    _write(art_path, art_bytes)
    _kind, claim, old_event = _empirical(world)
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
    err = _expect(lambda: _compile(world, "b1"), "EXPERIMENT_HEAD_STALE")
    assert err.details["stale_reason"] == "assessment_head_changed"
    heads["heads"][claim["claim_id"]] = {
        "event_id": old_event["event_id"],
        "event_sha256": sha(canonicalize(old_event)),
        "evidence_profile": old_event.get("evidence_profile", "legacy-v1"),
    }
    _write(heads_path, canonicalize(heads))
    published = _publish_lineage(world, "cb1")
    report = published["record"]["report"]
    binding = {
        "lineage_id": published["record"]["lineage_id"],
        "annotation_id": published["record"]["annotation_id"],
        "repository": report["repository"],
        "commit": report["commit"],
    }
    bound = _record_exp(world, valid_condition_input(world, code_binding=binding), name="bound.json", batch="eb1")
    domain_root = world["vault"] / "wiki/meta/domain"
    moved_domain = world["vault"] / "wiki/meta/domain-saved"
    domain_root.rename(moved_domain)
    err = _expect(lambda: _compile(world, "eb1"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "code_binding"
    moved_domain.rename(domain_root)
    ledger = world["vault"] / CLAIM_LEDGER
    saved = ledger.read_bytes()
    ledger.unlink()
    err = _expect(lambda: _compile(world, "b1"), "DOMAIN_STORE_INVALID")
    assert err.details.get("reason") == "authority"
    _write(ledger, saved)
    notes = world["vault"] / "wiki/meta/domain/notes.txt"
    notes.write_text("nope", encoding="utf-8")
    os.chmod(notes, 0o600)
    _expect(lambda: _compile(world, "b1"), "DOMAIN_STORE_INVALID")
    notes.unlink()
    reviews = world["vault"] / "wiki/meta/experiments/reviews"
    reviews.mkdir(parents=True)
    _expect(lambda: _compile(world, "b1"), "EXPERIMENT_STORE_INVALID")
    reviews.rmdir()
    if (world["vault"] / "wiki/meta/experiments").exists() and not any((world["vault"] / "wiki/meta/experiments").iterdir()):
        (world["vault"] / "wiki/meta/experiments").rmdir()
    assert bound["record"]["code_binding"]["lineage_id"] == binding["lineage_id"]


def test_publish_inspect_positive_and_refusals(world):
    first = _record_exp(world, batch="p1")
    compiled = _compile(world, "p1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    inspection = _inspect(world, "p1")
    validate_document(inspection, INSPECTION_SCHEMA)
    request_path = world["checkout"] / ".work/p1/experiment-publication/request.json"
    assert inspection["request_sha256"] == sha(request_path.read_bytes())
    assert inspection["request"] == json.loads(request_path.read_bytes())
    assert inspection["bindings_verified"] is True
    assert inspection["next_action"] == "apply_via_vpwiki_admin"
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    again = _inspect(world, "p1")
    assert canonicalize(again) == canonicalize(inspection)
    domain_prepared = str(world["checkout"] / ".work/p1/domain-publication/request.json")
    _expect(
        lambda: inspect_experiment_publication(prepared=domain_prepared, vault_root=str(world["vault"])),
        "WORK_PATH_UNSAFE",
    )
    heads_prepared = str(world["checkout"] / ".work/p1/experiments/heads.json")
    _expect(
        lambda: inspect_experiment_publication(prepared=heads_prepared, vault_root=str(world["vault"])),
        "WORK_PATH_UNSAFE",
    )
    _expect(
        lambda: inspect_experiment_publication(prepared="/etc/passwd", vault_root=str(world["vault"])),
        "WORK_PATH_UNSAFE",
    )
    request = _request(world, "p1")
    content_dir = world["checkout"] / ".work/p1/experiment-publication/content"
    digest = request["payloads"][0]["after_sha256"]
    content_path = content_dir / digest
    original = content_path.read_bytes()
    content_path.unlink()
    _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH")
    _write(content_path, original)
    content_path.write_bytes(original + b"x")
    os.chmod(content_path, 0o600)
    _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH")
    content_path.write_bytes(original)
    os.chmod(content_path, 0o600)
    extra = content_dir / ("c" * 64)
    extra.write_bytes(b"{}")
    os.chmod(extra, 0o600)
    _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH")
    extra.unlink()
    request_path.write_bytes(json.dumps({**request, "extra": True}, separators=(",", ":")).encode("utf-8"))
    os.chmod(request_path, 0o600)
    _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_INVALID")
    _write(request_path, canonicalize(request))
    bad_batch = dict(request)
    bad_batch["batch_id"] = "other"
    _write(request_path, canonicalize(bad_batch))
    err = _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_INVALID")
    assert err.details["reason"] == "batch_id"
    _write(request_path, canonicalize(request))
    mismatched = dict(request)
    mismatched["prospective_inventory_sha256"] = "b" * 64
    _write(request_path, canonicalize(mismatched))
    _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_MISMATCH")
    _write(request_path, canonicalize(request))
    item = dict(request["payloads"][0])
    new_digest = "b" * 64
    item["after_sha256"] = new_digest
    item["content_file"] = "experiment-publication/content/" + new_digest
    payloads = list(request["payloads"])
    payloads[0] = item
    mutated = dict(request)
    mutated["payloads"] = payloads
    _write(request_path, canonicalize(mutated))
    content_path.rename(content_dir / new_digest)
    _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH")
    (content_dir / new_digest).rename(content_path)
    _write(request_path, canonicalize(request))
    ledger = world["vault"] / CLAIM_LEDGER
    original_ledger = ledger.read_bytes()
    mutated_ledger = json.loads(original_ledger)
    mutated_ledger["generated_at"] = "2026-09-14T12:00:00Z"
    _write(ledger, canonicalize(mutated_ledger))
    err = _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_STALE")
    assert err.exit_code == 75
    _write(ledger, original_ledger)
    _apply_exp(world, "p1")
    err = _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_STALE")
    assert err.exit_code == 75
    extra_entry = world["checkout"] / ".work/p1/experiment-publication/notes.txt"
    extra_entry.write_text("nope", encoding="utf-8")
    os.chmod(extra_entry, 0o600)
    err = _expect(lambda: _inspect(world, "p1"), "EXPERIMENT_PUBLICATION_INVALID")
    assert err.details["reason"] == "unknown_entry"
    extra_entry.unlink()
    assert compiled["request_sha256"]
    assert first["record"]["record_id"]


def test_compile_inspect_zero_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    _record_exp(world, batch="n1")
    _compile(world, "n1")
    _inspect(world, "n1")
