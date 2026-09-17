from __future__ import annotations

import errno
import json
import os
import shutil
import stat
from pathlib import Path

import pytest

from tests.unit.test_article_revision import _apply_staged_articles
from tests.unit.test_domain_proposal import _snapshot, _write, make_world
from tests.unit.test_graph_projection import _three_chain
from tests.unit.test_reading_view import _build, _import_full, _reading_root
from video_paper_wiki.article_revision import status_article_store
from video_paper_wiki.article_store import ArticleStoreError
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.experiment_matrix import build_experiment_comparison_matrix
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.graph_projection import build_domain_graph_projection
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.reading_apply import ReadingApplyError, apply_reading_publication
from video_paper_wiki.reading_publication import (
    MARKER_PREFIX,
    REQUEST_SCHEMA,
    ReadingPublicationError,
    compile_reading_publication,
    inspect_reading_publication,
)
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

from video_paper_wiki import reading_apply as apply_mod

RESULT_SCHEMA = "video-paper-wiki.reading-publication-apply-result.v1"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _prepared(world, batch):
    return str(world["checkout"] / ".work" / batch / "reading-publication" / "request.json")


def _compile(world, batch):
    return compile_reading_publication(vault_root=str(world["vault"]), batch_id=batch)


def _apply_reading(world, batch, confirm=None, _fault=None):
    if confirm is None:
        confirm = lambda _summary: True
    return apply_reading_publication(
        prepared=_prepared(world, batch),
        vault_root=str(world["vault"]),
        confirm=confirm,
        _fault=_fault,
    )


def _expect(fn, code):
    with pytest.raises(
        (
            ReadingApplyError,
            ReadingPublicationError,
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


def _put(path: Path, data: bytes, mode=0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, mode)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _audit_state(vault):
    try:
        result = audit_integrity(vault)
        return ("ok", result["classification"], tuple(result.get("current_paths") or []))
    except ContractError as exc:
        return ("error", exc.code, ())


def _drop_publication(world, batch):
    root = world["checkout"] / ".work" / batch / "reading-publication"
    if root.exists():
        shutil.rmtree(root)


def test_apply_positive_create_and_idempotent(world):
    _three_chain(world)
    _build(world, "r1")
    compiled = _compile(world, "r1")
    request = json.loads(Path(_prepared(world, "r1")).read_bytes())
    validate_document(request, REQUEST_SCHEMA)
    work_before = _snapshot(world["checkout"] / ".work")
    meta_before = _snapshot(world["vault"] / "wiki/meta")
    papers_before = _snapshot(world["vault"] / "wiki/papers") if (world["vault"] / "wiki/papers").exists() else {}
    graph_before = canonicalize(build_domain_graph_projection(vault_root=str(world["vault"])))
    matrix_before = canonicalize(build_experiment_comparison_matrix(vault_root=str(world["vault"])))
    basis_before = status_article_store(vault_root=str(world["vault"]))["basis"]
    audit_before = _audit_state(world["vault"])
    captured = {}

    def confirm(summary):
        captured["summary"] = summary
        return True

    result = _apply_reading(world, "r1", confirm=confirm)
    validate_document(result, RESULT_SCHEMA)
    pages = [item["path"] for item in json.loads((_reading_root(world, "r1") / "manifest.json").read_bytes())["pages"]]
    expected = ["wiki/reading/" + path for path in pages]
    expected.sort(key=lambda item: item.encode("utf-8"))
    assert result["applied_paths"] == expected
    assert result["kept_paths"] == []
    assert result["deleted_paths"] == []
    assert result["foreign_paths"] == []
    assert result["removed_dirs"] == []
    assert "wiki/reading" in result["created_dirs"]
    for relative in result["created_dirs"]:
        assert _mode(world["vault"] / relative) == 0o700
    for path in expected:
        dest = world["vault"] / path
        staged = _reading_root(world, "r1") / path[len("wiki/reading/") :]
        assert dest.read_bytes() == staged.read_bytes()
        assert _mode(dest) == 0o600
    assert not (world["vault"] / "wiki/reading/manifest.json").exists()
    assert not list((world["vault"] / "wiki/reading").rglob(".*.tmp"))
    assert _snapshot(world["checkout"] / ".work") == work_before
    assert _snapshot(world["vault"] / "wiki/meta") == meta_before
    if papers_before:
        assert _snapshot(world["vault"] / "wiki/papers") == papers_before
    assert _audit_state(world["vault"]) == audit_before
    assert status_article_store(vault_root=str(world["vault"]))["basis"] == basis_before
    assert canonicalize(build_domain_graph_projection(vault_root=str(world["vault"]))) == graph_before
    assert canonicalize(build_experiment_comparison_matrix(vault_root=str(world["vault"]))) == matrix_before
    summary = captured["summary"]
    for key in (
        "batch_id",
        "request_sha256",
        "manifest_sha256",
        "basis",
        "install_path",
        "write_plan_counts",
        "create_paths",
        "replace_paths",
        "delete_paths",
    ):
        assert key in summary
    err = _expect(lambda: _apply_reading(world, "r1"), "READING_APPLY_ALREADY_APPLIED")
    assert err.details["next_action"] == "discard_batch"
    _build(world, "r2")
    err = _expect(lambda: _compile(world, "r2"), "READING_COMPILE_ALREADY_APPLIED")
    inspect_err = _expect(
        lambda: inspect_reading_publication(prepared=_prepared(world, "r1"), vault_root=str(world["vault"])),
        "READING_PUBLICATION_MISMATCH",
    )
    assert inspect_err.code == "READING_PUBLICATION_MISMATCH"


def test_apply_regenerate_and_delete(world):
    _three_chain(world)
    _build(world, "r1")
    _compile(world, "r1")
    _apply_reading(world, "r1")
    _import_full(world, "w1")
    _apply_staged_articles(world, "w1")
    _build(world, "r3")
    compiled = _compile(world, "r3")
    request = json.loads(Path(_prepared(world, "r3")).read_bytes())
    modes = {item["mode"] for item in request["payloads"]}
    assert "replace" in modes
    assert "create" in modes
    keep_items = [item for item in request["payloads"] if item["mode"] == "keep"]
    keep_stamps = {}
    for item in keep_items:
        path = world["vault"] / item["path"]
        keep_stamps[item["path"]] = path.stat()
    result = _apply_reading(world, "r3")
    validate_document(result, RESULT_SCHEMA)
    create_replace = [item["path"] for item in request["payloads"] if item["mode"] in {"create", "replace"}]
    create_replace.sort(key=lambda item: item.encode("utf-8"))
    assert result["applied_paths"] == create_replace
    assert result["kept_paths"]
    assert result["removed_dirs"] == []
    for path in result["applied_paths"]:
        dest = world["vault"] / path
        staged = _reading_root(world, "r3") / path[len("wiki/reading/") :]
        assert dest.read_bytes() == staged.read_bytes()
    for path, first in keep_stamps.items():
        current = (world["vault"] / path).stat()
        assert (current.st_mtime_ns, current.st_size, current.st_ino) == (
            first.st_mtime_ns,
            first.st_size,
            first.st_ino,
        )
    stale = world["vault"] / "wiki/reading/papers" / ("sha256-" + "d" * 64 + ".md")
    old = world["vault"] / "wiki/reading/stale/old.md"
    _put(stale, MARKER_PREFIX + b"stale-paper\n")
    _put(old, MARKER_PREFIX + b"old-page\n")
    _drop_publication(world, "r4")
    _build(world, "r4")
    _compile(world, "r4")
    result = _apply_reading(world, "r4")
    deleted = set(result["deleted_paths"])
    assert "wiki/reading/stale/old.md" in deleted
    assert any(path.endswith("sha256-" + "d" * 64 + ".md") for path in deleted)
    assert not stale.exists()
    assert not old.exists()
    assert result["removed_dirs"] == ["wiki/reading/stale"]
    assert (world["vault"] / "wiki/reading/papers").is_dir()


def test_apply_ownership(world):
    _three_chain(world)
    _build(world, "r1")
    notes = world["vault"] / "wiki/reading-notes"
    _put(notes / "index.md", b"note-index\n")
    _put(notes / "papers/demo.md", b"note-paper\n")
    _put(notes / "compare/matrix.md", b"note-matrix\n")
    note_snap = _snapshot(notes)
    note_dir = notes.stat()
    install = world["vault"] / "wiki/reading"
    _put(install / "notes.txt", b"foreign-notes\n")
    _put(install / "attach/big.bin", b"bin\n")
    _put(install / "papers/README.md", b"readme\n")
    foreign_snap = {
        "notes": (install / "notes.txt").stat(),
        "bin": (install / "attach/big.bin").stat(),
        "readme": (install / "papers/README.md").stat(),
    }
    _compile(world, "r1")
    result = _apply_reading(world, "r1")
    assert result["reading_notes_written"] is False
    assert _snapshot(notes) == note_snap
    assert notes.stat().st_mtime_ns == note_dir.st_mtime_ns
    assert set(result["foreign_paths"]) == {
        "wiki/reading/notes.txt",
        "wiki/reading/attach/big.bin",
        "wiki/reading/papers/README.md",
    }
    assert (install / "notes.txt").stat().st_mtime_ns == foreign_snap["notes"].st_mtime_ns
    assert (install / "attach/big.bin").stat().st_mtime_ns == foreign_snap["bin"].st_mtime_ns
    assert (install / "papers/README.md").stat().st_mtime_ns == foreign_snap["readme"].st_mtime_ns
    assert (install / "attach").is_dir()
    _build(world, "r5")
    _put(install / "index.md", b"user-replaced\n")
    vault_before = _snapshot(world["vault"])
    err = _expect(lambda: _compile(world, "r5"), "READING_COMPILE_UNMARKED_TARGET")
    assert _snapshot(world["vault"]) == vault_before
    err = _expect(lambda: _apply_reading(world, "r1"), "READING_COMPILE_UNMARKED_TARGET")
    assert _snapshot(world["vault"]) == vault_before
    _drop_publication(world, "r1")
    _put(install / "index.md", (_reading_root(world, "r1") / "index.md").read_bytes())
    _put(install / "stale/old.md", MARKER_PREFIX + b"pending-delete\n")
    _drop_publication(world, "r5")
    _build(world, "r6")
    _compile(world, "r6")

    def swap(_summary):
        _put(install / "index.md", b"tamper\n")
        return True

    vault_before = _snapshot(world["vault"])
    err = _expect(lambda: _apply_reading(world, "r6", confirm=swap), "READING_APPLY_CHANGED")
    assert err.exit_code == 75 or err.details.get("reason") == "before"
    if err.code == "READING_APPLY_CHANGED":
        assert err.exit_code == 75
    if (install / "index.md").exists() and (install / "index.md").is_file():
        (install / "index.md").unlink()
    _drop_publication(world, "r6")
    _build(world, "r7")
    _compile(world, "r7")

    ledger = world["vault"] / CLAIM_LEDGER
    ledger_raw = ledger.read_bytes()

    def touch_ledger(_summary):
        _put(ledger, ledger_raw + b" ")
        return True

    err = _expect(lambda: _apply_reading(world, "r7", confirm=touch_ledger), "READING_APPLY_CHANGED")
    assert err.exit_code == 75
    _put(ledger, ledger_raw)
    install_link = world["vault"] / "wiki/reading"
    if install_link.exists():
        shutil.rmtree(install_link)
    install_link.symlink_to(notes)
    _drop_publication(world, "r7")
    _build(world, "r8")
    err = _expect(lambda: _compile(world, "r8"), "READING_COMPILE_TARGET_INVALID")
    assert err.details["reason"] == "symlink"
    install_link.unlink()
    wiki = world["vault"] / "wiki"
    moved = world["vault"] / "wiki.bak"
    _drop_publication(world, "r8")
    _build(world, "r9")
    _compile(world, "r9")
    wiki.rename(moved)
    with pytest.raises(
        (ReadingApplyError, ReadingPublicationError, DomainStoreError, ContractError)
    ) as missing:
        _apply_reading(world, "r9")
    assert missing.value.code in {
        "READING_APPLY_VAULT_INVALID",
        "READING_COMPILE_TARGET_INVALID",
        "DOMAIN_STORE_INVALID",
        "DOMAIN_STORE_CHANGED",
        "WORK_PATH_UNSAFE",
    }
    moved.rename(wiki)
    _put(install / "index.md" / "nested.txt", b"dir\n")
    _drop_publication(world, "r9")
    _build(world, "r10")
    err = _expect(lambda: _compile(world, "r10"), "READING_COMPILE_TARGET_INVALID")
    assert err.details["reason"] == "entry_kind"
    shutil.rmtree(install / "index.md")
    article_slot = world["checkout"] / ".work/r10/article-publication/request.json"
    article_slot.parent.mkdir(parents=True, exist_ok=True)
    article_slot.write_bytes(b"{}\n")
    err = _expect(
        lambda: apply_reading_publication(
            prepared=str(article_slot),
            vault_root=str(world["vault"]),
            confirm=lambda _s: True,
        ),
        "WORK_PATH_UNSAFE",
    )
    _build(world, "r11")
    _compile(world, "r11")
    reviews = world["vault"] / "wiki/meta/experiments/reviews/x.json"
    _put(reviews, b"{}\n")
    err = _expect(lambda: _apply_reading(world, "r11"), "EXPERIMENT_STORE_INVALID")
    assert err.details.get("reason") == "unknown_entry"


def test_apply_faults(world, monkeypatch):
    _three_chain(world)
    _build(world, "r1")
    _compile(world, "r1")
    vault_before = _snapshot(world["vault"])

    def boom_create(phase):
        if phase == "before-create":
            raise OSError(errno.EIO, "injected")

    err = _expect(lambda: _apply_reading(world, "r1", _fault=boom_create), "READING_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "before-create"
    assert err.details["rolled_back"] == []
    assert err.details["rollback_complete"] is True
    assert _snapshot(world["vault"]) == vault_before
    assert not (world["vault"] / "wiki/reading").exists()
    calls = {"n": 0}
    real = apply_mod._write_excl

    def second(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(errno.EIO, "injected-write")
        return real(*args, **kwargs)

    monkeypatch.setattr(apply_mod, "_write_excl", second)
    vault_before = _snapshot(world["vault"])
    err = _expect(lambda: _apply_reading(world, "r1"), "READING_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "write"
    assert err.details["rollback_complete"] is True
    assert err.details["rolled_back"]
    assert _snapshot(world["vault"]) == vault_before
    assert not list((world["vault"] / "wiki").rglob(".*.tmp"))
    monkeypatch.setattr(apply_mod, "_write_excl", real)
    _apply_reading(world, "r1")
    stale = world["vault"] / "wiki/reading/stale/old.md"
    _put(stale, MARKER_PREFIX + b"old\n")
    _import_full(world, "w1")
    _apply_staged_articles(world, "w1")
    _build(world, "r2")
    _compile(world, "r2")
    vault_mid = _snapshot(world["vault"])

    def boom_commit(phase):
        if phase == "before-commit":
            raise OSError(errno.EIO, "injected-commit")

    err = _expect(lambda: _apply_reading(world, "r2", _fault=boom_commit), "READING_APPLY_WRITE_FAILED")
    assert err.details["phase"] == "before-commit"
    assert err.details["rollback_complete"] is True
    assert stale.exists()
    assert not list((world["vault"] / "wiki/reading").rglob(".*.tmp"))
    assert _snapshot(world["vault"]) == vault_mid
    request = json.loads(Path(_prepared(world, "r2")).read_bytes())
    replace = next(item for item in request["payloads"] if item["mode"] == "replace")

    def boom_before(phase):
        if phase == "before-commit":
            _put(world["vault"] / replace["path"], MARKER_PREFIX + b"changed\n")

    err = _expect(lambda: _apply_reading(world, "r2", _fault=boom_before), "READING_APPLY_VAULT_INVALID")
    assert err.details["reason"] == "before"
    assert err.details["rollback_complete"] is True
    _put(world["vault"] / replace["path"], _reading_root(world, "r1") / replace["path"][len("wiki/reading/") :] if False else (world["vault"] / replace["path"]).read_bytes())
    # restore replace target from r1 installed bytes then rebuild request consistency by copying original staged r1 page if needed
    staged_old = None
    r1_page = _reading_root(world, "r1") / replace["path"][len("wiki/reading/") :]
    if r1_page.exists():
        _put(world["vault"] / replace["path"], r1_page.read_bytes())
    _drop_publication(world, "r2")
    _build(world, "r2b")
    _compile(world, "r2b")

    def boom_after(phase):
        if phase == "after-commit":
            raise OSError(errno.EIO, "injected-after")

    err = _expect(lambda: _apply_reading(world, "r2b", _fault=boom_after), "READING_APPLY_VERIFY_FAILED")
    assert err.details["phase"] == "after-commit"
    assert err.details["committed_paths"]
    assert err.details["next_action"] == "repair_store"
    assert not list((world["vault"] / "wiki/reading").rglob(".*.tmp"))
    err = _expect(lambda: _apply_reading(world, "r2b"), "READING_APPLY_ALREADY_APPLIED")
    _drop_publication(world, "r3")
    _build(world, "r3")
    _put(world["vault"] / "wiki/reading/notes.txt", b"keep-me\n")
    _compile(world, "r3")

    def tamper_foreign(phase):
        if phase == "after-commit":
            _put(world["vault"] / "wiki/reading/notes.txt", b"changed\n")

    err = _expect(lambda: _apply_reading(world, "r3", _fault=tamper_foreign), "READING_APPLY_VERIFY_FAILED")
    assert err.details["reason"] == "foreign"
    _put(world["vault"] / "wiki/reading-notes/index.md", b"note\n")
    _drop_publication(world, "r3")
    _build(world, "r3b")
    _compile(world, "r3b")

    def tamper_notes(phase):
        if phase == "after-commit":
            _put(world["vault"] / "wiki/reading-notes/extra.md", b"new\n")

    err = _expect(lambda: _apply_reading(world, "r3b", _fault=tamper_notes), "READING_APPLY_VERIFY_FAILED")
    assert err.details["reason"] == "reading_notes"
    _drop_publication(world, "r3b")
    _build(world, "r3c")
    _compile(world, "r3c")

    def tamper_store(phase):
        if phase == "after-commit":
            path = world["vault"] / CLAIM_LEDGER
            _put(path, path.read_bytes() + b" ")

    err = _expect(lambda: _apply_reading(world, "r3c", _fault=tamper_store), "READING_APPLY_VERIFY_FAILED")
    assert err.details.get("reason") in {"basis"} or str(err.details.get("prior_code", "")).startswith("DOMAIN_STORE")
    assert err.details["next_action"] == "repair_store"
    assert "committed_paths" in err.details


def test_apply_refuses_patched_basis_after_article_store_change(world):
    _three_chain(world)
    _build(world, "r1")
    _compile(world, "r1")
    raw = Path(_prepared(world, "r1")).read_bytes()
    _import_full(world, "w4")
    _apply_staged_articles(world, "w4")
    request = json.loads(raw)
    request["basis"] = status_article_store(vault_root=str(world["vault"]))["basis"]
    Path(_prepared(world, "r1")).write_bytes(canonicalize(request))
    vault_before = _snapshot(world["vault"])
    err = _expect(lambda: _apply_reading(world, "r1"), "READING_PUBLICATION_CONTENT_MISMATCH")
    assert err.details["instance_pointer"] == "/basis"
    assert err.details["next_action"] == "recompile"
    assert _snapshot(world["vault"]) == vault_before


def test_apply_rejects_parent_directory_case_collision_before_write(world):
    _three_chain(world)
    _build(world, "r1")
    _compile(world, "r1")
    _put(world["vault"] / "wiki/reading/PAPERS/private.txt", b"private\n")
    vault_before = _snapshot(world["vault"])
    err = _expect(lambda: _apply_reading(world, "r1"), "READING_COMPILE_TARGET_INVALID")
    assert err.details["reason"] == "portable_collision"
    assert _snapshot(world["vault"]) == vault_before
    assert not (world["vault"] / "wiki/reading/papers").exists()


def test_apply_keep_plus_delete_only_chain(world):
    _three_chain(world)
    _build(world, "r1")
    install = world["vault"] / "wiki/reading"
    shutil.copytree(_reading_root(world, "r1"), install)
    compiled = _compile(world, "r1")
    request = json.loads(Path(_prepared(world, "r1")).read_bytes())
    modes = {item["mode"] for item in request["payloads"]}
    assert modes == {"keep", "delete"}
    assert compiled["write_plan_counts"]["create"] == 0
    assert compiled["write_plan_counts"]["replace"] == 0
    assert compiled["write_plan_counts"]["keep"] >= 1
    assert compiled["write_plan_counts"]["delete"] == 1
    inspection = inspect_reading_publication(prepared=_prepared(world, "r1"), vault_root=str(world["vault"]))
    validate_document(inspection, "video-paper-wiki.reading-publication-inspection.v1")
    result = _apply_reading(world, "r1")
    validate_document(result, RESULT_SCHEMA)
    assert result["applied_paths"] == []
    assert result["deleted_paths"] == ["wiki/reading/manifest.json"]
    assert result["kept_paths"]
    assert not (install / "manifest.json").exists()
    for path in result["kept_paths"]:
        dest = install / path[len("wiki/reading/") :]
        staged = _reading_root(world, "r1") / path[len("wiki/reading/") :]
        assert dest.read_bytes() == staged.read_bytes()


def test_apply_post_commit_collision_keeps_committed_paths_and_repair_store(world):
    _three_chain(world)
    _build(world, "r1")
    install = world["vault"] / "wiki/reading"
    shutil.copytree(_reading_root(world, "r1"), install)
    _compile(world, "r1")

    def collide(phase):
        if phase == "after-commit":
            _put(install / "PAPERS/private.txt", b"private\n")

    err = _expect(lambda: _apply_reading(world, "r1", _fault=collide), "READING_APPLY_VERIFY_FAILED")
    assert err.details["next_action"] == "repair_store"
    assert "committed_paths" in err.details
    assert "wiki/reading/manifest.json" in err.details["committed_paths"]
    assert err.details.get("prior_code") == "READING_COMPILE_TARGET_INVALID"
    assert err.details.get("reason") == "portable_collision"
    assert not (install / "manifest.json").exists()


def _committed_write_paths(request):
    paths = [item["path"] for item in request["payloads"] if item["mode"] in {"create", "replace", "delete"}]
    paths.sort(key=lambda item: item.encode("utf-8"))
    return paths


def test_apply_after_commit_oserror_records_create_paths(world):
    _three_chain(world)
    _build(world, "r1")
    _compile(world, "r1")
    request = json.loads(Path(_prepared(world, "r1")).read_bytes())
    modes = {item["mode"] for item in request["payloads"]}
    assert modes == {"create"}
    expected = _committed_write_paths(request)
    assert expected

    def boom_after(phase):
        if phase == "after-commit":
            raise OSError(errno.EIO, "injected-after-create")

    err = _expect(lambda: _apply_reading(world, "r1", _fault=boom_after), "READING_APPLY_VERIFY_FAILED")
    assert err.details["phase"] == "after-commit"
    assert err.details["next_action"] == "repair_store"
    assert set(err.details["committed_paths"]) == set(expected)
    for item in request["payloads"]:
        dest = world["vault"] / item["path"]
        staged = _reading_root(world, "r1") / item["path"][len("wiki/reading/") :]
        raw = dest.read_bytes()
        assert raw == staged.read_bytes()
        assert sha(raw) == item["after_sha256"]


def test_apply_after_commit_oserror_records_mixed_committed_paths(world):
    _three_chain(world)
    _build(world, "r1")
    _compile(world, "r1")
    _apply_reading(world, "r1")
    _put(world["vault"] / "wiki/reading/stale/old.md", MARKER_PREFIX + b"old\n")
    _import_full(world, "w1")
    _apply_staged_articles(world, "w1")
    _build(world, "r2")
    _compile(world, "r2")
    request = json.loads(Path(_prepared(world, "r2")).read_bytes())
    modes = {item["mode"] for item in request["payloads"]}
    assert "create" in modes
    assert {"replace", "delete"} & modes
    expected = _committed_write_paths(request)
    keep_paths = {item["path"] for item in request["payloads"] if item["mode"] == "keep"}

    def boom_after(phase):
        if phase == "after-commit":
            raise OSError(errno.EIO, "injected-after-mixed")

    err = _expect(lambda: _apply_reading(world, "r2", _fault=boom_after), "READING_APPLY_VERIFY_FAILED")
    assert err.details["phase"] == "after-commit"
    assert err.details["next_action"] == "repair_store"
    assert set(err.details["committed_paths"]) == set(expected)
    assert keep_paths.isdisjoint(err.details["committed_paths"])
    for item in request["payloads"]:
        dest = world["vault"] / item["path"]
        if item["mode"] in {"create", "replace"}:
            staged = _reading_root(world, "r2") / item["path"][len("wiki/reading/") :]
            raw = dest.read_bytes()
            assert raw == staged.read_bytes()
            assert sha(raw) == item["after_sha256"]
        elif item["mode"] == "delete":
            assert not dest.exists()
