from __future__ import annotations

import errno
import json
import os
import socket
import stat

import pytest

from tests.apply_fs_helpers import install_portable_enospc
from tests.unit.test_article_publication import (
    _compile,
    _export_ctx,
    _import_doc,
    _stage_complete,
    _ts,
)
from tests.unit.test_article_revision import _apply_staged_articles
from tests.unit.test_domain_proposal import _snapshot, _write, make_world
from video_paper_wiki import article_apply as article_apply_mod
from video_paper_wiki.article_apply import ArticleApplyError, apply_article_publication
from video_paper_wiki.article_publication import ArticlePublicationError
from video_paper_wiki.article_revision import (
    article_history,
    check_article_revision,
    render_article_revision,
    status_article_store,
)
from video_paper_wiki.article_store import ArticleStoreError, _load_article_store
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import DomainStoreError, status_domain_store
from video_paper_wiki.experiment_matrix import build_experiment_comparison_matrix
from video_paper_wiki.experiment_store import ExperimentStoreError, status_experiment_store
from video_paper_wiki.graph_projection import build_domain_graph_projection
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import _Snapshot, _walk_inventory
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

RESULT_SCHEMA = "video-paper-wiki.article-publication-apply-result.v1"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _prepared(world, batch):
    return str(world["checkout"] / ".work" / batch / "article-publication" / "request.json")


def _apply_art(world, batch, *, confirm=None, _fault=None):
    if confirm is None:
        confirm = lambda _summary: True
    return apply_article_publication(
        prepared=_prepared(world, batch),
        vault_root=str(world["vault"]),
        confirm=confirm,
        _fault=_fault,
    )


def _expect(fn, code):
    with pytest.raises(
        (
            ArticleApplyError,
            ArticlePublicationError,
            ArticleStoreError,
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
    assert result["next_action"] == "articles_status"
    assert result["applied_inventory_sha256"] == result["prospective_inventory_sha256"]
    validate_document(result, RESULT_SCHEMA)


def test_apply_positive_create_and_idempotent(world):
    staged = _stage_complete(world, batch="p1")
    domain_before = status_domain_store(vault_root=str(world["vault"]))
    exp_before = status_experiment_store(vault_root=str(world["vault"]))
    matrix_before = build_experiment_comparison_matrix(vault_root=str(world["vault"]))
    graph_before = build_domain_graph_projection(vault_root=str(world["vault"]))
    compiled = _compile(world, "p1")
    outline = staged["outline"]["record"]
    rendered = render_article_revision(
        vault_root=str(world["vault"]),
        batch_id="p1",
        article_id=outline["article_id"],
        revision_id=outline["revision_id"],
    )
    staged_md = (world["checkout"] / rendered["markdown_path"]).read_text(encoding="utf-8")
    work_before_apply = _snapshot(world["checkout"] / ".work")
    audit_before = _audit_keys(world["vault"])
    md_before = {
        str(path.relative_to(world["vault"])): path.read_bytes()
        for path in world["vault"].rglob("*.md")
        if path.is_file()
    }
    captured = {}

    def confirm(summary):
        captured["summary"] = summary
        return True

    result = _apply_art(world, "p1", confirm=confirm)
    _consts(result)
    assert result["heads_mode"] == "create"
    assert result["heads_before_sha256"] is None
    assert result["payload_count"] == compiled["payload_count"]
    assert result["applied_paths"] == compiled["changed_paths"]
    assert len(result["applied_paths"]) == 4
    assert result["compiled_heads"] == compiled["compiled_heads"]
    art = outline["article_id"]
    heads = world["vault"] / "wiki/meta/articles/heads.json"
    content_root = world["checkout"] / ".work/p1/article-publication/content"
    for rec in (staged["outline"]["record"], staged["section"]["record"], staged["full"]["record"]):
        record_path = world["vault"] / "wiki/meta/articles/records" / rec["article_id"] / (rec["revision_id"] + ".json")
        assert record_path.is_file()
        assert record_path.read_bytes() == (content_root / sha(record_path.read_bytes())).read_bytes()
        assert _mode(record_path) == 0o600
    assert heads.is_file()
    assert heads.read_bytes() == (content_root / sha(heads.read_bytes())).read_bytes()
    assert _mode(heads) == 0o600
    assert _mode(world["vault"] / "wiki/meta/articles") == 0o700
    assert _mode(world["vault"] / "wiki/meta/articles/records") == 0o700
    assert _mode(world["vault"] / "wiki/meta/articles/records" / art) == 0o700
    assert not list((world["vault"] / "wiki/meta/articles").glob(".heads.json.*.tmp"))
    snap = _Snapshot(world["vault"])
    try:
        store = _load_article_store(snap)
    finally:
        snap.close()
    assert len(store.records) == 3
    status = status_article_store(vault_root=str(world["vault"]))
    row = next(item for item in status["articles"] if item["article_id"] == art)
    assert row["head_location"] == "vault_store"
    assert row["vault_revision_count"] == 3
    assert row["staged_revision_count"] == 0
    assert row["complete"] is True
    chk = check_article_revision(
        vault_root=str(world["vault"]),
        article_id=art,
        revision_id=staged["full"]["record"]["revision_id"],
    )
    assert chk["revision_location"] == "vault_store"
    assert chk["check_status"] == "current"
    rnd = render_article_revision(
        vault_root=str(world["vault"]),
        batch_id="rend1",
        article_id=art,
        revision_id=outline["revision_id"],
    )
    assert rnd["revision_location"] == "vault_store"
    vault_md = (world["checkout"] / rnd["markdown_path"]).read_text(encoding="utf-8")
    assert vault_md.replace("位置 vault_store", "位置 staged") == staged_md
    hist = article_history(vault_root=str(world["vault"]), article_id=art)
    assert [row["superseded"] for row in hist["revisions"]] == [True, True, False]
    assert canonicalize(domain_before) == canonicalize(status_domain_store(vault_root=str(world["vault"])))
    assert canonicalize(exp_before) == canonicalize(status_experiment_store(vault_root=str(world["vault"])))
    assert canonicalize(matrix_before) == canonicalize(
        build_experiment_comparison_matrix(vault_root=str(world["vault"]))
    )
    assert canonicalize(graph_before) == canonicalize(build_domain_graph_projection(vault_root=str(world["vault"])))
    assert _audit_keys(world["vault"]) == audit_before
    work_after = {
        key: value
        for key, value in _snapshot(world["checkout"] / ".work").items()
        if not key.startswith("rend1/")
    }
    assert work_after == work_before_apply
    md_after = {
        str(path.relative_to(world["vault"])): path.read_bytes()
        for path in world["vault"].rglob("*.md")
        if path.is_file()
    }
    assert md_after == md_before
    summary = captured["summary"]
    for key in (
        "batch_id",
        "request_sha256",
        "basis",
        "prospective_inventory_sha256",
        "heads_mode",
        "heads_before_sha256",
        "touched_articles",
        "compiled_heads",
        "changed_paths",
        "payload_count",
    ):
        assert key in summary
    assert set(summary["basis"]) == {
        "domain_store_inventory_sha256",
        "claim_ledger_sha256",
        "assessment_heads_sha256",
        "experiment_store_inventory_sha256",
        "article_store_inventory_sha256",
    }
    err = _expect(lambda: _apply_art(world, "p1"), "ARTICLE_APPLY_ALREADY_APPLIED")
    assert err.details["next_action"] == "discard_batch"
    head_doc = json.loads(
        (
            world["vault"]
            / "wiki/meta/articles/records"
            / art
            / (staged["full"]["record"]["revision_id"] + ".json")
        ).read_bytes()
    )
    cont = _import_doc(
        world,
        _export_ctx(world),
        {"schema": "video-paper-wiki.article-document.v1", "title": "after-apply", "sections": head_doc["sections"]},
        batch="p1b",
        recorded_at=_ts(20),
        previous=staged["full"]["record"]["revision_id"],
        tag="-n",
    )
    assert cont["revision_location"] == "staged"


def test_apply_successor_replace_and_second_chain(world):
    first = _stage_complete(world, batch="g1")
    _compile(world, "g1")
    _apply_art(world, "g1")
    old_heads = (world["vault"] / "wiki/meta/articles/heads.json").read_bytes()
    art = first["full"]["record"]["article_id"]
    old_record = (
        world["vault"]
        / "wiki/meta/articles/records"
        / art
        / (first["outline"]["record"]["revision_id"] + ".json")
    )
    old_bytes = old_record.read_bytes()
    old_stamp = old_record.stat()
    head_doc = json.loads(
        (
            world["vault"]
            / "wiki/meta/articles/records"
            / art
            / (first["full"]["record"]["revision_id"] + ".json")
        ).read_bytes()
    )
    cont1 = _import_doc(
        world,
        _export_ctx(world),
        {"schema": "video-paper-wiki.article-document.v1", "title": "succ-one", "sections": head_doc["sections"]},
        batch="g2",
        recorded_at=_ts(12),
        previous=first["full"]["record"]["revision_id"],
        tag="-s1",
    )
    _compile(world, "g2")
    result = _apply_art(world, "g2")
    _consts(result)
    assert result["heads_mode"] == "replace"
    assert result["heads_before_sha256"] == sha(old_heads)
    assert old_record.read_bytes() == old_bytes
    assert old_record.stat().st_mtime_ns == old_stamp.st_mtime_ns
    new_record = (
        world["vault"]
        / "wiki/meta/articles/records"
        / art
        / (cont1["record"]["revision_id"] + ".json")
    )
    assert new_record.is_file()
    new_heads = (world["vault"] / "wiki/meta/articles/heads.json").read_bytes()
    assert new_heads != old_heads
    status = status_article_store(vault_root=str(world["vault"]))
    row = next(item for item in status["articles"] if item["article_id"] == art)
    assert row["vault_revision_count"] == 4
    other = _stage_complete(world, batch="g3", question="alternate question text", hour=30)
    _compile(world, "g3")
    _apply_art(world, "g3")
    status = status_article_store(vault_root=str(world["vault"]))
    assert len(status["articles"]) == 2
    assert other["full"]["record"]["article_id"] != art


def test_apply_refusals_zero_writes(world):
    _stage_complete(world, batch="c1")
    _compile(world, "c1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    err = _expect(lambda: _apply_art(world, "c1", confirm=lambda _s: False), "HUMAN_APPROVAL_REQUIRED")
    assert err.details["next_action"] == "confirm_interactively"
    assert _snapshot(world["vault"]) == vault_before
    extra = world["vault"] / "wiki/meta/articles/extra.json"

    def tamper(_summary):
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_bytes(b"{}")
        os.chmod(extra, 0o600)
        return True

    err = _expect(lambda: _apply_art(world, "c1", confirm=tamper), "ARTICLE_APPLY_CHANGED")
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
    err = _expect(lambda: _apply_art(world, "c1"), "ARTICLE_PUBLICATION_STALE")
    assert err.exit_code == 75
    _write(ledger, original_ledger)
    request_path = world["checkout"] / ".work/c1/article-publication/request.json"
    request = json.loads(request_path.read_bytes())
    digest = request["payloads"][0]["after_sha256"]
    content_path = world["checkout"] / ".work/c1/article-publication/content" / digest
    original = content_path.read_bytes()
    content_path.write_bytes(original + b"x")
    os.chmod(content_path, 0o600)
    _expect(lambda: _apply_art(world, "c1"), "ARTICLE_PUBLICATION_CONTENT_MISMATCH")
    content_path.write_bytes(original)
    os.chmod(content_path, 0o600)
    rec_item = next(item for item in request["payloads"] if "/records/" in item["path"])
    target = world["vault"] / rec_item["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"not-json")
    os.chmod(target, 0o600)
    with pytest.raises(
        (
            ArticleApplyError,
            ArticlePublicationError,
            ArticleStoreError,
            ExperimentStoreError,
            DomainStoreError,
            StagingError,
            ContractError,
        )
    ) as planted:
        _apply_art(world, "c1")
    assert planted.value.code in {"ARTICLE_APPLY_VAULT_INVALID", "ARTICLE_STORE_INVALID"}
    target.unlink()
    records_dir = target.parent
    if records_dir.exists() and not any(records_dir.iterdir()):
        records_dir.rmdir()
    parent = records_dir.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
    art_root = world["vault"] / "wiki/meta/articles"
    if art_root.exists() and not any(art_root.iterdir()):
        art_root.rmdir()
    link = world["vault"] / "wiki/meta/articles"
    os.symlink(world["vault"] / "wiki/meta", link)
    _expect(lambda: _apply_art(world, "c1"), "ARTICLE_STORE_INVALID")
    link.unlink()
    empty_heads = {"schema": "video-paper-wiki.article-heads.v1", "heads": {}}
    _write(world["vault"] / "wiki/meta/articles/heads.json", canonicalize(empty_heads))
    with pytest.raises(
        (
            ArticleApplyError,
            ArticlePublicationError,
            ArticleStoreError,
            ExperimentStoreError,
            DomainStoreError,
            StagingError,
            ContractError,
        )
    ) as planted_heads:
        _apply_art(world, "c1")
    assert planted_heads.value.code in {
        "ARTICLE_APPLY_VAULT_INVALID",
        "ARTICLE_PUBLICATION_STALE",
        "ARTICLE_STORE_HEADS_MISMATCH",
    }
    (world["vault"] / "wiki/meta/articles/heads.json").unlink()
    if (world["vault"] / "wiki/meta/articles").exists() and not any(
        (world["vault"] / "wiki/meta/articles").iterdir()
    ):
        (world["vault"] / "wiki/meta/articles").rmdir()
    meta = world["vault"] / "wiki/meta"
    moved = world["vault"] / "wiki-meta-saved"
    meta.rename(moved)
    err = _expect(lambda: _apply_art(world, "c1"), "DOMAIN_STORE_INVALID")
    moved.rename(meta)
    err = _expect(
        lambda: apply_article_publication(
            prepared=str(world["checkout"] / ".work/c1/experiment-publication/request.json"),
            vault_root=str(world["vault"]),
            confirm=lambda _s: True,
        ),
        "WORK_PATH_UNSAFE",
    )
    assert err.details["next_action"] == "repair_input"
    reviews = world["vault"] / "wiki/meta/experiments/reviews"
    reviews.mkdir(parents=True)
    _expect(lambda: _apply_art(world, "c1"), "EXPERIMENT_STORE_INVALID")
    reviews.rmdir()
    if (world["vault"] / "wiki/meta/experiments").exists() and not any(
        (world["vault"] / "wiki/meta/experiments").iterdir()
    ):
        (world["vault"] / "wiki/meta/experiments").rmdir()
    work_after = _snapshot(world["checkout"] / ".work")
    assert {key: value[0] for key, value in work_after.items()} == {
        key: value[0] for key, value in work_before.items()
    }


def test_apply_replace_heads_mismatch_and_faults(world, monkeypatch):
    first = _stage_complete(world, batch="f1")
    _compile(world, "f1")
    vault_before = _snapshot(world["vault"])

    def boom(_phase):
        raise OSError("synthetic before-create")

    err = _expect(lambda: _apply_art(world, "f1", _fault=boom), "ARTICLE_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "before-create"
    assert err.details["rolled_back"] == []
    assert err.details["rollback_complete"] is True
    assert _snapshot(world["vault"]) == vault_before
    result = _apply_art(world, "f1")
    _consts(result)
    art = first["full"]["record"]["article_id"]
    head_doc = json.loads(
        (
            world["vault"]
            / "wiki/meta/articles/records"
            / art
            / (first["full"]["record"]["revision_id"] + ".json")
        ).read_bytes()
    )
    _import_doc(
        world,
        _export_ctx(world),
        {"schema": "video-paper-wiki.article-document.v1", "title": "succ-f2", "sections": head_doc["sections"]},
        batch="f2",
        recorded_at=_ts(12),
        previous=first["full"]["record"]["revision_id"],
        tag="-s",
    )
    _compile(world, "f2")
    heads_path = world["vault"] / "wiki/meta/articles/heads.json"
    original_heads = heads_path.read_bytes()
    _write(heads_path, canonicalize({"schema": "video-paper-wiki.article-heads.v1", "heads": {}}))
    err = _expect(lambda: _apply_art(world, "f2"), "ARTICLE_STORE_HEADS_MISMATCH")
    _write(heads_path, original_heads)
    vault_pre_write = _snapshot(world["vault"])
    injector = install_portable_enospc(
        monkeypatch,
        article_apply_mod,
        world["vault"],
        _prepared(world, "f2"),
        "wiki/meta/articles/records/",
        partial_bytes=1,
    )
    err = _expect(lambda: _apply_art(world, "f2"), "ARTICLE_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "write"
    assert err.details["errno"] == errno.ENOSPC
    assert err.details["rollback_complete"] is True
    injector.assert_hit(require_partial=True)
    injector.restore(monkeypatch)
    assert _snapshot(world["vault"]) == vault_pre_write

    def before_commit(phase):
        if phase != "before-commit":
            return
        raise OSError("synthetic before-commit")

    err = _expect(lambda: _apply_art(world, "f2", _fault=before_commit), "ARTICLE_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "before-commit"
    assert not list((world["vault"] / "wiki/meta/articles").glob(".heads.json.*.tmp"))
    assert _snapshot(world["vault"]) == vault_pre_write

    def after_commit(phase):
        if phase != "after-commit":
            return
        raise OSError("synthetic after-commit")

    err = _expect(lambda: _apply_art(world, "f2", _fault=after_commit), "ARTICLE_APPLY_VERIFY_FAILED")
    assert err.details["phase"] == "after-commit"
    snap = _Snapshot(world["vault"])
    try:
        _load_article_store(snap)
    finally:
        snap.close()
    _expect(lambda: _apply_art(world, "f2"), "ARTICLE_APPLY_ALREADY_APPLIED")
    other = _stage_complete(world, batch="f3", question="alternate question text", hour=40)
    _compile(world, "f3")

    def stamp_tamper(phase):
        if phase != "after-commit":
            return
        src = world["vault"] / world["association"]["raw"]["path"]
        src.write_bytes(src.read_bytes() + b"x")
        os.chmod(src, 0o600)

    err = _expect(lambda: _apply_art(world, "f3", _fault=stamp_tamper), "ARTICLE_APPLY_VERIFY_FAILED")
    assert err.details.get("reason") == "file_stamp"
    src = world["vault"] / world["association"]["raw"]["path"]
    src.write_bytes(src.read_bytes()[:-1])
    os.chmod(src, 0o600)
    _stage_complete(world, batch="f4", question="third question text here", hour=50)
    _compile(world, "f4")

    def domain_tamper(phase):
        if phase != "after-commit":
            return
        notes = world["vault"] / "wiki/meta/domain/notes.txt"
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_bytes(b"nope")
        os.chmod(notes, 0o600)

    err = _expect(lambda: _apply_art(world, "f4", _fault=domain_tamper), "ARTICLE_APPLY_VERIFY_FAILED")
    assert err.details.get("reason") in {"domain_store", None} or err.details.get("prior_code") == "DOMAIN_STORE_INVALID"
    if err.details.get("reason") != "domain_store":
        assert err.details.get("prior_code") == "DOMAIN_STORE_INVALID"
    notes = world["vault"] / "wiki/meta/domain/notes.txt"
    if notes.exists():
        notes.unlink()
    _stage_complete(world, batch="f5", question="fourth question text here", hour=60)
    _compile(world, "f5")

    def exp_tamper(phase):
        if phase != "after-commit":
            return
        extra_exp = world["vault"] / "wiki/meta/experiments/extra.json"
        extra_exp.parent.mkdir(parents=True, exist_ok=True)
        extra_exp.write_bytes(b"{}")
        os.chmod(extra_exp, 0o600)

    err = _expect(lambda: _apply_art(world, "f5", _fault=exp_tamper), "ARTICLE_APPLY_VERIFY_FAILED")
    assert err.details.get("reason") == "experiment_store" or err.details.get("prior_code") == "EXPERIMENT_STORE_INVALID"
    assert other["full"]["record"]["revision_id"]


def test_apply_genesis_write_rollback_removes_articles_dir(world, monkeypatch):
    _stage_complete(world, batch="r1")
    _compile(world, "r1")
    vault_before = _snapshot(world["vault"])
    injector = install_portable_enospc(
        monkeypatch,
        article_apply_mod,
        world["vault"],
        _prepared(world, "r1"),
        "wiki/meta/articles/records/",
    )
    err = _expect(lambda: _apply_art(world, "r1"), "ARTICLE_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "write"
    assert err.details["errno"] == errno.ENOSPC
    assert err.details["rollback_complete"] is True
    injector.assert_hit()
    injector.restore(monkeypatch)
    assert not (world["vault"] / "wiki/meta/articles").exists()
    assert _snapshot(world["vault"]) == vault_before


def test_apply_zero_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    _stage_complete(world, batch="net")
    _compile(world, "net")
    _apply_art(world, "net")
