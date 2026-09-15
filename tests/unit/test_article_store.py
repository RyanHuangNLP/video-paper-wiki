from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.unit.test_article_revision import (
    _apply_staged_articles,
    _export,
    _import_outline,
    _papers,
    _question,
)
from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.article_revision import status_article_store
from video_paper_wiki.article_store import (
    EXCERPT_BYTES_BUDGET,
    MAX_ARTICLES,
    MAX_EVIDENCE,
    MAX_REVISIONS_PER_ARTICLE,
    MAX_TABLE_ROWS,
    RELEVANCE_LIMIT,
    ArticleStoreError,
    _load_article_store,
    _load_staged_articles,
    _merge,
    _read_optional,
    article_inventory_digest,
    derive_article_heads,
)
from video_paper_wiki.domain_store import DomainStoreError, _with_store
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import _Snapshot
from video_paper_wiki.source_semantics_contracts import sha


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _load(world):
    def apply(snapshot, store, authority):
        return _load_article_store(snapshot)

    return _with_store(str(world["vault"]), apply, authority_required=True)


def _expect(fn, code):
    with pytest.raises((ArticleStoreError, DomainStoreError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    assert details.get("next_action")
    if code != "WORK_PATH_UNSAFE":
        assert details.get("instance_pointer") is not None
    return err.value


def test_empty_store_and_constants(world):
    store = _load(world)
    assert store.records == {}
    assert derive_article_heads(store) == {"schema": "video-paper-wiki.article-heads.v1", "heads": {}}
    status = status_article_store(vault_root=str(world["vault"]))
    assert status["article_count"] == 0
    assert status["next_action"] == "none"
    assert status["basis"]["article_store_inventory_sha256"] == sha(canonicalize([]))
    assert MAX_REVISIONS_PER_ARTICLE == 128
    assert MAX_ARTICLES == 4096
    assert MAX_TABLE_ROWS == 64
    assert MAX_EVIDENCE == 1024
    assert EXCERPT_BYTES_BUDGET == 65536
    assert RELEVANCE_LIMIT == 48


def test_apply_staged_and_digest(world):
    _three_chain(world)
    imported = _import_outline(world, batch="b1")
    _apply_staged_articles(world, "b1")
    store = _load(world)
    assert imported["record"]["revision_id"] in store.records
    status = status_article_store(vault_root=str(world["vault"]))
    assert article_inventory_digest(store) == status["basis"]["article_store_inventory_sha256"]


def test_unknown_entry_and_heads(world):
    _three_chain(world)
    _import_outline(world, batch="b1")
    _apply_staged_articles(world, "b1")
    notes = world["vault"] / "wiki/meta/articles" / "notes.txt"
    notes.write_bytes(b"x")
    os.chmod(notes, 0o600)
    _expect(lambda: _load(world), "ARTICLE_STORE_INVALID")
    notes.unlink()
    heads = world["vault"] / "wiki/meta/articles" / "heads.json"
    heads.unlink()
    _expect(lambda: _load(world), "ARTICLE_STORE_HEADS_MISSING")
    _apply_staged_articles(world, "b1")
    doc = json.loads(heads.read_bytes())
    art = next(iter(doc["heads"]))
    digest = doc["heads"][art]["record_sha256"]
    doc["heads"][art]["record_sha256"] = ("0" if digest[0] != "0" else "1") + digest[1:]
    heads.write_bytes(canonicalize(doc))
    os.chmod(heads, 0o600)
    _expect(lambda: _load(world), "ARTICLE_STORE_HEADS_MISMATCH")


def test_path_identity_canonical_and_identity(world):
    _three_chain(world)
    imported = _import_outline(world, batch="b1")
    _apply_staged_articles(world, "b1")
    rec = imported["record"]
    path = (
        world["vault"]
        / "wiki/meta/articles"
        / "records"
        / rec["article_id"]
        / (rec["revision_id"] + ".json")
    )
    renamed = path.with_name("arv-" + "0" * 20 + ".json")
    path.rename(renamed)
    _expect(lambda: _load(world), "ARTICLE_STORE_INVALID")
    renamed.rename(path)
    path.write_bytes(path.read_bytes() + b" ")
    os.chmod(path, 0o600)
    exc = _expect(lambda: _load(world), "ARTICLE_STORE_INVALID")
    assert exc.details.get("reason") == "canonical_bytes"
    doc = json.loads(canonicalize(rec).decode())
    doc["content_sha256"] = "b" * 64
    path.write_bytes(canonicalize(doc))
    os.chmod(path, 0o600)
    exc = _expect(lambda: _load(world), "ARTICLE_STORE_INVALID")
    assert exc.details.get("reason") == "identity"
    _apply_staged_articles(world, "b1")
    doc = json.loads(path.read_bytes())
    doc["question"] = doc["question"] + " x"
    path.write_bytes(canonicalize(doc))
    os.chmod(path, 0o600)
    exc = _expect(lambda: _load(world), "ARTICLE_STORE_INVALID")
    assert exc.details.get("reason") == "identity"


def test_symlink_chain_and_staged(world, monkeypatch):
    _three_chain(world)
    imported = _import_outline(world, batch="b1")
    _apply_staged_articles(world, "b1")
    rec = imported["record"]
    path = (
        world["vault"]
        / "wiki/meta/articles"
        / "records"
        / rec["article_id"]
        / (rec["revision_id"] + ".json")
    )
    backup = path.read_bytes()
    path.unlink()
    path.symlink_to("/etc/passwd")
    exc = _expect(lambda: _load(world), "ARTICLE_STORE_INVALID")
    assert exc.details.get("reason") == "symlink"
    path.unlink()
    path.write_bytes(backup)
    os.chmod(path, 0o600)
    second = json.loads(backup)
    second["previous_revision_id"] = None
    second["recorded_at"] = "2026-09-15T01:00:00Z"
    from video_paper_wiki.article_store import content_sha256_from_record, revision_id_from_record

    second["content_sha256"] = content_sha256_from_record(second)
    rid = revision_id_from_record(second)
    second["revision_id"] = rid
    other = path.parent / (rid + ".json")
    other.write_bytes(canonicalize(second))
    os.chmod(other, 0o600)
    from video_paper_wiki.article_store import derive_article_heads

    def apply(snapshot, store, authority):
        return _load_article_store(snapshot)

    exc = _expect(lambda: _with_store(str(world["vault"]), apply, authority_required=True), "ARTICLE_STORE_CHAIN_INVALID")
    assert exc.details.get("reason") == "genesis"
    other.unlink()
    foreign = json.loads(backup)
    foreign["previous_revision_id"] = "arv-" + "f" * 20
    foreign["content_sha256"] = content_sha256_from_record(foreign)
    rid = revision_id_from_record(foreign)
    foreign["revision_id"] = rid
    other = path.parent / (rid + ".json")
    other.write_bytes(canonicalize(foreign))
    os.chmod(other, 0o600)
    exc = _expect(lambda: _load(world), "ARTICLE_STORE_CHAIN_INVALID")
    assert exc.details.get("reason") == "previous"
    other.unlink()
    early = json.loads(backup)
    early["previous_revision_id"] = rec["revision_id"]
    early["recorded_at"] = "2026-09-14T00:00:00Z"
    early["title"] = "later"
    early["content_sha256"] = content_sha256_from_record(early)
    rid = revision_id_from_record(early)
    early["revision_id"] = rid
    other = path.parent / (rid + ".json")
    other.write_bytes(canonicalize(early))
    os.chmod(other, 0o600)
    exc = _expect(lambda: _load(world), "ARTICLE_STORE_CHAIN_INVALID")
    assert exc.details.get("reason") == "timestamp_order"
    other.unlink()
    extra = world["checkout"] / ".work" / "b2" / "articles" / "extra"
    extra.mkdir(parents=True)
    (extra / "x.txt").write_bytes(b"x")

    def load_staged():
        return _load_staged_articles("b2")

    exc = _expect(load_staged, "ARTICLE_STORE_INVALID")
    assert exc.details.get("reason") == "unknown_entry"


def test_staged_previous_limit_and_changed(world, monkeypatch):
    _three_chain(world)
    first = _import_outline(world, batch="b1")
    _apply_staged_articles(world, "b1")
    planted = json.loads(canonicalize(first["record"]).decode())
    planted["previous_revision_id"] = "arv-" + "0" * 20
    planted["recorded_at"] = "2026-09-15T03:00:00Z"
    planted["title"] = "changed-title"
    from video_paper_wiki.article_store import content_sha256_from_record, revision_id_from_record

    planted["content_sha256"] = content_sha256_from_record(planted)
    rid = revision_id_from_record(planted)
    planted["revision_id"] = rid
    staged_dir = (
        world["checkout"] / ".work" / "b3" / "articles" / "records" / planted["article_id"]
    )
    staged_dir.mkdir(parents=True, exist_ok=True)
    (staged_dir / (rid + ".json")).write_bytes(canonicalize(planted))

    def merge_bad():
        def apply(snapshot, store, authority):
            vault = _load_article_store(snapshot)
            staged = _load_staged_articles("b3")
            return _merge(vault, staged)

        return _with_store(str(world["vault"]), apply, authority_required=True)

    exc = _expect(merge_bad, "ARTICLE_STORE_CHAIN_INVALID")
    assert exc.details.get("reason") == "staged_previous"
    monkeypatch.setattr("video_paper_wiki.article_store.MAX_REVISIONS_PER_ARTICLE", 1)
    monkeypatch.setattr("video_paper_wiki.article_revision.MAX_REVISIONS_PER_ARTICLE", 1)
    from tests.unit.test_article_revision import _outline_doc, _write_json
    from video_paper_wiki.article_revision import ArticleRevisionError, import_article_revision

    data = _export(world)
    ctx = world["checkout"] / "ctx2.json"
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    doc = world["checkout"] / "doc2.json"
    changed_doc = _outline_doc(data["context"])
    changed_doc["title"] = "limit-title"
    _write_json(doc, changed_doc)
    with pytest.raises((ArticleStoreError, ArticleRevisionError, DomainStoreError)) as err:
        import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b4",
            context=str(ctx),
            document=str(doc),
            recorded_by="t",
            recorded_at="2026-09-15T04:00:00Z",
            previous_revision_id=first["record"]["revision_id"],
        )
    assert err.value.code == "ARTICLE_STORE_LIMIT"
    def apply_boom(snapshot, store, authority):
        original = snapshot.read

        def boom(relative, **kwargs):
            if "articles" in relative:
                raise OSError("changed")
            return original(relative, **kwargs)

        snapshot.read = boom
        return _load_article_store(snapshot)

    exc = _expect(
        lambda: _with_store(str(world["vault"]), apply_boom, authority_required=True),
        "ARTICLE_STORE_CHANGED",
    )
    assert exc.exit_code == 75

    def boom_optional(*_a, **_k):
        raise OSError("x")

    class Boom:
        def read_optional(self, *_a, **_k):
            raise OSError("x")

    with pytest.raises(ArticleStoreError) as err:
        _read_optional(Boom(), "wiki/meta/articles/heads.json", "/wiki/meta/articles/heads.json")
    assert err.value.code == "ARTICLE_STORE_CHANGED"
    assert err.value.exit_code == 75
