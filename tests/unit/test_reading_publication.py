from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
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
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.reading_publication import (
    INSPECTION_SCHEMA,
    MARKER_PREFIX,
    MAX_PAGES,
    REQUEST_SCHEMA,
    ReadingPublicationError,
    compile_reading_publication,
    inspect_reading_publication,
)
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

from video_paper_wiki import reading_publication as publication_mod


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _prepared(world, batch):
    return world["checkout"] / ".work" / batch / "reading-publication" / "request.json"


def _compile(world, batch):
    return compile_reading_publication(vault_root=str(world["vault"]), batch_id=batch)


def _inspect(world, batch):
    return inspect_reading_publication(prepared=str(_prepared(world, batch)), vault_root=str(world["vault"]))


def _manifest(world, batch):
    path = _reading_root(world, batch) / "manifest.json"
    return json.loads(path.read_bytes()), path


def _expect(fn, code):
    with pytest.raises(
        (
            ReadingPublicationError,
            ArticleStoreError,
            DomainStoreError,
            ExperimentStoreError,
            StagingError,
            ContractError,
        )
    ) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    if code not in {"WORK_PATH_UNSAFE", "STAGING_CONFLICT"}:
        assert details.get("instance_pointer") is not None
        assert details.get("next_action")
    return err.value


def _put(path: Path, data: bytes, mode=0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, mode)


def test_compile_positive_and_determinism(world, monkeypatch):
    _three_chain(world)
    vault_before = _snapshot(world["vault"])
    work = world["checkout"] / ".work"
    sockets = []
    pops = []

    def boom_socket(*_a, **_k):
        sockets.append(1)
        raise AssertionError("socket")

    def boom_popen(*_a, **_k):
        pops.append(1)
        raise AssertionError("popen")

    monkeypatch.setattr(socket, "socket", boom_socket)
    monkeypatch.setattr(subprocess, "Popen", boom_popen)
    reading_before = None
    _build(world, "r1")
    reading_before = _snapshot(_reading_root(world, "r1"))
    data = _compile(world, "r1")
    assert data["state"] == "reading_publication_prepared"
    raw = _prepared(world, "r1").read_bytes()
    request = json.loads(raw)
    validate_document(request, REQUEST_SCHEMA)
    assert sha(raw) == data["request_sha256"]
    manifest, manifest_path = _manifest(world, "r1")
    assert data["manifest_sha256"] == sha(manifest_path.read_bytes())
    status = status_article_store(vault_root=str(world["vault"]))
    assert data["basis"] == status["basis"]
    assert request["basis"] == status["basis"]
    assert {item["mode"] for item in request["payloads"]} == {"create"}
    staged = {item["staged_path"] for item in request["payloads"]}
    assert staged == {"reading/" + item["path"] for item in manifest["pages"]}
    paths = [item["path"] for item in request["payloads"]]
    assert paths == sorted(paths, key=lambda item: item.encode("utf-8"))
    assert request["foreign_paths"] == []
    n = len(manifest["pages"])
    assert request["write_plan_counts"] == {
        "create": n,
        "replace": 0,
        "keep": 0,
        "delete": 0,
        "foreign": 0,
    }
    assert data["write_plan_counts"] == request["write_plan_counts"]
    pub = world["checkout"] / ".work/r1/reading-publication"
    assert [p.name for p in pub.iterdir()] == ["request.json"]
    assert _snapshot(_reading_root(world, "r1")) == reading_before
    assert _snapshot(world["vault"]) == vault_before
    assert sockets == []
    assert pops == []
    _build(world, "r2")
    other = _compile(world, "r2")
    left = json.loads(_prepared(world, "r1").read_bytes())
    right = json.loads(_prepared(world, "r2").read_bytes())
    left["batch_id"] = "x"
    right["batch_id"] = "x"
    left["manifest_sha256"] = "x"
    right["manifest_sha256"] = "x"
    assert canonicalize(left) == canonicalize(right)
    assert other["write_plan_counts"] == data["write_plan_counts"]


def test_compile_refusals_and_passthrough(world, monkeypatch):
    _three_chain(world)
    _build(world, "r1")
    _build(world, "filt", paper_id=world["association"]["paper_id"])
    err = _expect(lambda: _compile(world, "filt"), "READING_COMPILE_INVALID")
    assert err.details["reason"] == "paper_filter"
    assert err.details["next_action"] == "rebuild_unfiltered"
    manifest = _reading_root(world, "r1") / "manifest.json"
    raw = manifest.read_bytes()
    manifest.unlink()
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_INVALID")
    assert err.details["reason"] == "manifest_missing"
    _put(manifest, raw)
    page = next(p for p in _reading_root(world, "r1").rglob("*.md") if p.is_file())
    original = page.read_bytes()
    _put(page, original + b"x")
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_INVALID")
    assert err.details["reason"] == "page_digest"
    _put(page, original)
    extra = _reading_root(world, "r1") / "extra.md"
    _put(extra, MARKER_PREFIX + b"x\n")
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_INVALID")
    assert err.details["reason"] == "unknown_entry"
    extra.unlink()
    page.unlink()
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_INVALID")
    assert err.details["reason"] == "page_missing"
    _put(page, original)
    page.unlink()
    page.symlink_to(manifest)
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_INVALID")
    assert err.details["reason"] == "symlink"
    page.unlink()
    _put(page, original)
    _put(manifest, raw + b" ")
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_INVALID")
    assert err.details["reason"] == "canonical_bytes"
    _put(manifest, raw)
    _import_full(world, "w1")
    _apply_staged_articles(world, "w1")
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_STALE")
    assert err.exit_code == 75
    assert err.details["next_action"] == "rebuild_reading"
    assert set(err.details["first"]) == set(err.details["observed"])
    monkeypatch.setattr(publication_mod, "MAX_PAGES", 3)
    _build(world, "lim")
    err = _expect(lambda: _compile(world, "lim"), "READING_COMPILE_LIMIT")
    assert MAX_PAGES == 8192
    monkeypatch.setattr(publication_mod, "MAX_PAGES", MAX_PAGES)
    _build(world, "chg")
    original_read = publication_mod._Snapshot.read
    seen = {}

    def flipped(self, relative, **kwargs):
        raw = original_read(self, relative, **kwargs)
        if relative.endswith(".md") or relative == "manifest.json":
            if relative in seen:
                return raw + b"x"
            seen[relative] = True
        return raw

    monkeypatch.setattr(publication_mod._Snapshot, "read", flipped)
    err = _expect(lambda: _compile(world, "chg"), "READING_COMPILE_CHANGED")
    assert err.exit_code == 75
    monkeypatch.setattr(publication_mod._Snapshot, "read", original_read)
    reviews = world["vault"] / "wiki/meta/experiments/reviews/x.json"
    _put(reviews, b"{}\n")
    err = _expect(lambda: _compile(world, "chg"), "EXPERIMENT_STORE_INVALID")
    assert err.details.get("reason") == "unknown_entry"
    reviews.unlink()
    ledger = world["vault"] / CLAIM_LEDGER
    kept = ledger.read_bytes()
    ledger.unlink()
    err = _expect(lambda: _compile(world, "r1"), "DOMAIN_STORE_INVALID")
    assert err.details.get("reason") == "authority"
    _put(ledger, kept)


def test_compile_target_classification(world):
    _three_chain(world)
    _build(world, "r1")
    manifest, _path = _manifest(world, "r1")
    install = world["vault"] / "wiki/reading"
    user = b"# user note\n"
    _put(install / "index.md", user)
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_UNMARKED_TARGET")
    assert err.details["next_action"] == "move_user_file"
    assert err.details["reason"] == "no_marker"
    assert not _prepared(world, "r1").exists()
    _put(install / "index.md", MARKER_PREFIX + b"old-marked\n")
    data = _compile(world, "r1")
    request = json.loads(_prepared(world, "r1").read_bytes())
    index = next(item for item in request["payloads"] if item["path"] == "wiki/reading/index.md")
    assert index["mode"] == "replace"
    assert index["before_sha256"] == sha(MARKER_PREFIX + b"old-marked\n")
    shutil.rmtree(install)
    shutil.copytree(_reading_root(world, "r1"), install)
    _prepared(world, "r1").unlink()
    (world["checkout"] / ".work/r1/reading-publication").rmdir()
    data = _compile(world, "r1")
    request = json.loads(_prepared(world, "r1").read_bytes())
    modes = {item["mode"] for item in request["payloads"]}
    assert modes == {"keep", "delete"}
    assert all(item["mode"] == "keep" for item in request["payloads"] if item["path"].endswith(".md"))
    deleted = [item for item in request["payloads"] if item["mode"] == "delete"]
    assert [item["path"] for item in deleted] == ["wiki/reading/manifest.json"]
    (install / "manifest.json").unlink()
    _prepared(world, "r1").unlink()
    (world["checkout"] / ".work/r1/reading-publication").rmdir()
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_ALREADY_APPLIED")
    assert err.details["next_action"] == "discard_batch"
    shutil.copy(_reading_root(world, "r1") / "manifest.json", install / "manifest.json")
    stale = install / ("papers/sha256-" + "f" * 64 + ".md")
    _put(stale, MARKER_PREFIX + b"stale\n")
    pub = world["checkout"] / ".work/r1/reading-publication"
    if pub.exists():
        shutil.rmtree(pub)
    data = _compile(world, "r1")
    request = json.loads(_prepared(world, "r1").read_bytes())
    stale_path = "wiki/reading/" + stale.relative_to(install).as_posix()
    assert any(item["path"] == stale_path and item["mode"] == "delete" for item in request["payloads"])
    shutil.rmtree(pub)
    _put(stale, b"user paper\n")
    data = _compile(world, "r1")
    request = json.loads(_prepared(world, "r1").read_bytes())
    assert stale_path in request["foreign_paths"]
    assert all(item["path"] != stale_path for item in request["payloads"])


def test_compile_foreign_unread_and_shape_refusals(world, monkeypatch):
    _three_chain(world)
    _build(world, "r1")
    install = world["vault"] / "wiki/reading"
    notes = install / "notes.txt"
    big = install / "attach/big.bin"
    hard = install / "papers/orphan.md"
    _put(notes, b"notes\n")
    _put(big, b"x" * (9 * 1024 * 1024))
    _put(hard, b"orphan\n")
    os.link(hard, install / "papers/orphan-link.md")
    reads = []
    real = publication_mod._read_child

    def wrapped(parent_fd, name, *, max_bytes=1048576):
        reads.append(name)
        return real(parent_fd, name, max_bytes=max_bytes)

    monkeypatch.setattr(publication_mod, "_read_child", wrapped)
    data = _compile(world, "r1")
    request = json.loads(_prepared(world, "r1").read_bytes())
    assert "wiki/reading/notes.txt" in request["foreign_paths"]
    assert "wiki/reading/attach/big.bin" in request["foreign_paths"]
    assert "wiki/reading/papers/orphan.md" in request["foreign_paths"]
    assert "notes.txt" not in reads
    assert "big.bin" not in reads
    assert "orphan.md" not in reads
    assert "orphan-link.md" not in reads
    if _prepared(world, "r1").exists():
        shutil.rmtree(world["checkout"] / ".work/r1/reading-publication")
    shutil.rmtree(install / "attach", ignore_errors=True)
    notes.unlink()
    hard.unlink()
    (install / "papers/orphan-link.md").unlink()
    _put(install / "x.md", MARKER_PREFIX + b"x\n")
    (install / "x.md").unlink()
    (install / "x.md").symlink_to(install.parent / "papers")
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_TARGET_INVALID")
    assert err.details["reason"] == "symlink"
    (install / "x.md").unlink()
    shutil.rmtree(install)
    install.symlink_to(world["vault"] / "wiki/reading-notes")
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_TARGET_INVALID")
    assert err.details["reason"] == "symlink"
    install.unlink()
    _put(install / "Index.md", b"case\n")
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_TARGET_INVALID")
    assert err.details["reason"] == "portable_collision"
    (install / "Index.md").unlink()
    marked = MARKER_PREFIX + b"hard\n"
    _put(install / "index.md", marked)
    os.link(install / "index.md", install / "index-link.md")
    (install / "index-link.md").unlink()
    sibling = install / "index-hard.md"
    os.link(install / "index.md", sibling)
    # keep hardlink on index.md itself
    sibling.unlink()
    other = install / "tmp-hard"
    os.link(install / "index.md", other)
    err = _expect(lambda: _compile(world, "r1"), "READING_COMPILE_TARGET_INVALID")
    assert err.details["reason"] == "hardlink"
    other.unlink()
    (install / "index.md").unlink()


def test_compile_does_not_open_reading_notes(world, monkeypatch):
    _three_chain(world)
    _build(world, "r1")
    notes = world["vault"] / "wiki/reading-notes"
    _put(notes / "index.md", b"user index\n")
    _put(notes / "papers/demo.md", b"user paper\n")
    before = _snapshot(notes)
    opened = []
    real = os.open

    def wrapped(path, flags, *args, **kwargs):
        opened.append(os.fspath(path))
        return real(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", wrapped)
    _compile(world, "r1")
    assert all("reading-notes" not in name for name in opened)
    assert _snapshot(notes) == before


def test_inspect_positive_and_refusals(world):
    _three_chain(world)
    _build(world, "r1")
    compiled = _compile(world, "r1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    first = _inspect(world, "r1")
    validate_document(first, INSPECTION_SCHEMA)
    raw = _prepared(world, "r1").read_bytes()
    assert first["request_sha256"] == sha(raw)
    assert first["request"] == json.loads(raw)
    assert first["next_action"] == "apply_via_vpwiki_admin"
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    second = _inspect(world, "r1")
    assert canonicalize(first) == canonicalize(second)
    page = _reading_root(world, "r1") / "index.md"
    original = page.read_bytes()
    _put(page, original + b"x")
    err = _expect(lambda: _inspect(world, "r1"), "READING_PUBLICATION_CONTENT_MISMATCH")
    _put(page, original)
    manifest = _reading_root(world, "r1") / "manifest.json"
    man_raw = manifest.read_bytes()
    _put(manifest, man_raw + b" ")
    err = _expect(lambda: _inspect(world, "r1"), "READING_PUBLICATION_CONTENT_MISMATCH")
    assert err.details["instance_pointer"] == "/manifest_sha256"
    _put(manifest, man_raw)
    request = json.loads(raw)
    request["unexpected"] = True
    _put(_prepared(world, "r1"), canonicalize(request))
    err = _expect(lambda: _inspect(world, "r1"), "READING_PUBLICATION_INVALID")
    _put(_prepared(world, "r1"), raw)
    request = json.loads(raw)
    request["batch_id"] = "other"
    _put(_prepared(world, "r1"), canonicalize(request))
    err = _expect(lambda: _inspect(world, "r1"), "READING_PUBLICATION_INVALID")
    assert err.details["reason"] == "batch_id"
    _put(_prepared(world, "r1"), raw)
    extra = _prepared(world, "r1").parent / "extra.json"
    _put(extra, b"{}\n")
    err = _expect(lambda: _inspect(world, "r1"), "READING_PUBLICATION_INVALID")
    assert err.details["reason"] == "unknown_entry"
    extra.unlink()
    install = world["vault"] / "wiki/reading"
    _put(install / "index.md", b"user\n")
    err = _expect(lambda: _inspect(world, "r1"), "READING_COMPILE_UNMARKED_TARGET")
    _put(install / "index.md", original)
    err = _expect(lambda: _inspect(world, "r1"), "READING_PUBLICATION_MISMATCH")
    (install / "index.md").unlink()
    _import_full(world, "w2")
    _apply_staged_articles(world, "w2")
    err = _expect(lambda: _inspect(world, "r1"), "READING_PUBLICATION_STALE")
    assert err.exit_code == 75
