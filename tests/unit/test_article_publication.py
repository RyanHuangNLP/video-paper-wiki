from __future__ import annotations

import json
import os
import socket

import pytest

from tests.unit.test_article_revision import (
    _apply_staged_articles,
    _claim_and_value,
    _outline_doc,
    _papers,
    _provisional_section,
    _question,
    _write_json,
)
from tests.unit.test_domain_proposal import _snapshot, _write, make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.article_context import export_article_context
from video_paper_wiki.article_publication import (
    ArticlePublicationError,
    MAX_STAGED_RECORDS,
    compile_article_publication,
    inspect_article_publication,
)
from video_paper_wiki.article_revision import (
    import_article_revision,
    status_article_store,
)
from video_paper_wiki.article_store import (
    ArticleStore,
    ArticleStoreError,
    _validate_chains,
    article_inventory_digest,
    content_sha256_from_record,
    derive_article_heads,
    revision_id_from_record,
)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

REQUEST_SCHEMA = "video-paper-wiki.article-publication-request.v1"
INSPECTION_SCHEMA = "video-paper-wiki.article-publication-inspection.v1"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _compile(world, batch):
    return compile_article_publication(vault_root=str(world["vault"]), batch_id=batch)


def _inspect(world, batch):
    prepared = world["checkout"] / ".work" / batch / "article-publication" / "request.json"
    return inspect_article_publication(prepared=str(prepared), vault_root=str(world["vault"]))


def _request(world, batch):
    path = world["checkout"] / ".work" / batch / "article-publication" / "request.json"
    return json.loads(path.read_bytes())


def _expect(fn, code):
    with pytest.raises(
        (ArticlePublicationError, ArticleStoreError, DomainStoreError, ExperimentStoreError, StagingError)
    ) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    if code not in {"WORK_PATH_UNSAFE", "STAGING_CONFLICT"}:
        assert details.get("instance_pointer") is not None
        assert details.get("next_action")
    return err.value


def _ts(step):
    hour = step % 24
    minute = min((step // 24) * 3, 59)
    return "2026-09-15T%02d:%02d:00Z" % (hour, minute)


def _export_ctx(world, question=None):
    if not (world["vault"] / "wiki/meta/experiments").exists():
        _three_chain(world)
    return export_article_context(
        vault_root=str(world["vault"]),
        question=question or _question(world),
        paper_ids=_papers(world),
    )


def _import_doc(world, data, doc, *, batch, recorded_at, previous=None, target=None, tag=""):
    ctx = world["checkout"] / ("ctx-" + batch + tag + ".json")
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    path = world["checkout"] / ("doc-" + batch + tag + ".json")
    _write_json(path, doc)
    return import_article_revision(
        vault_root=str(world["vault"]),
        batch_id=batch,
        context=str(ctx),
        document=str(path),
        recorded_by="t",
        recorded_at=recorded_at,
        previous_revision_id=previous,
        target_section_id=target,
    )


def _fill_full(record, context, eids):
    filled = []
    for section in record["sections"]:
        if section["status"] == "provisional":
            filled.append(section)
        elif section["role"] == "unknowns":
            item = dict(section)
            item["status"] = "unknown"
            item["markdown"] = "证据不足"
            item["citations"] = []
            filled.append(item)
        else:
            filled.append(_provisional_section(section, context, eids))
    return {"schema": "video-paper-wiki.article-document.v1", "title": record["title"], "sections": filled}


def _stage_complete(world, *, batch, question=None, hour=0):
    data = _export_ctx(world, question)
    claim, value = _claim_and_value(data["context"])
    eids = [claim["evidence_id"], value["evidence_id"]]
    spans = [item for item in data["context"]["evidence"] if item["kind"] == "claim_span"]
    if spans:
        eids.append(spans[0]["evidence_id"])
    outline = _import_doc(
        world, data, _outline_doc(data["context"]), batch=batch, recorded_at=_ts(hour), tag="-o"
    )
    rec = outline["record"]
    s1 = _provisional_section(rec["sections"][0], data["context"], eids)
    sec_doc = {
        "schema": "video-paper-wiki.article-document.v1",
        "title": rec["title"],
        "sections": [s1] + rec["sections"][1:],
    }
    section = _import_doc(
        world,
        data,
        sec_doc,
        batch=batch,
        recorded_at=_ts(hour + 1),
        previous=rec["revision_id"],
        target="s1",
        tag="-s",
    )
    rec2 = section["record"]
    full = _import_doc(
        world,
        data,
        _fill_full(rec2, data["context"], eids),
        batch=batch,
        recorded_at=_ts(hour + 2),
        previous=rec2["revision_id"],
        tag="-f",
    )
    assert full["record"]["progress"]["unwritten"] == 0
    return {
        "outline": outline,
        "section": section,
        "full": full,
        "data": data,
        "claim": claim,
        "value": value,
    }


def _copy_staged_articles(world, src, dst):
    src_root = world["checkout"] / ".work" / src / "articles"
    dst_root = world["checkout"] / ".work" / dst / "articles"
    for path in src_root.rglob("*"):
        if path.is_file():
            _write(dst_root / path.relative_to(src_root), path.read_bytes())


def _articles_snapshot(world, batch):
    root = world["checkout"] / ".work" / batch / "articles"
    if not root.exists():
        return {}
    return _snapshot(root)


def _remove_articles_store(world):
    art_root = world["vault"] / "wiki/meta/articles"
    if not art_root.exists():
        return
    for path in sorted(art_root.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()


def _load_applied_store(world):
    store = ArticleStore()
    dest_root = world["vault"] / "wiki/meta/articles" / "records"
    if dest_root.exists():
        for art_dir in sorted(dest_root.iterdir()):
            if not art_dir.is_dir():
                continue
            for rec in sorted(art_dir.iterdir()):
                if not rec.is_file():
                    continue
                raw = rec.read_bytes()
                doc = json.loads(raw)
                store.records[doc["revision_id"]] = doc
                store.record_raw[doc["revision_id"]] = raw
    _validate_chains(store)
    heads_path = world["vault"] / "wiki/meta/articles" / "heads.json"
    if heads_path.exists():
        store.heads_raw = heads_path.read_bytes()
    store.empty = not store.records and store.heads_raw is None
    return store


def test_compile_positive_example(world):
    staged = _stage_complete(world, batch="p1")
    vault_before = _snapshot(world["vault"])
    articles_before = _articles_snapshot(world, "p1")
    work_root = world["checkout"] / ".work"
    outside_before = {
        str(path.relative_to(work_root)): path.read_bytes()
        for path in work_root.rglob("*")
        if path.is_file() and path.relative_to(work_root).parts[:2] != ("p1", "article-publication")
    }
    data = _compile(world, "p1")
    assert data["state"] == "article_publication_prepared"
    rec = staged["full"]["record"]
    art = rec["article_id"]
    chain_len = 3
    assert data["payload_count"] == chain_len + 1
    assert data["changed_paths"] == sorted(data["changed_paths"], key=lambda item: item.encode("utf-8"))
    assert "wiki/meta/articles/heads.json" in data["changed_paths"]
    assert data["touched_articles"] == [art]
    status = status_article_store(vault_root=str(world["vault"]), batch_id="p1")
    assert data["basis"] == status["basis"]
    head = data["compiled_heads"]
    assert len(head) == 1
    assert head[0]["revision_id"] == status["articles"][0]["head_revision_id"]
    staged_path = (
        world["checkout"]
        / ".work/p1/articles/records"
        / art
        / (head[0]["revision_id"] + ".json")
    )
    assert head[0]["record_sha256"] == sha(staged_path.read_bytes())
    assert head[0]["previous_vault_revision_id"] is None
    assert head[0]["staged_revision_count"] == chain_len
    assert head[0]["progress"]["unwritten"] == 0
    assert head[0]["check_status"] == "current"
    request_path = world["checkout"] / ".work/p1/article-publication/request.json"
    assert request_path.is_file()
    request = json.loads(request_path.read_bytes())
    validate_document(request, REQUEST_SCHEMA)
    assert sha(request_path.read_bytes()) == data["request_sha256"]
    content = world["checkout"] / ".work/p1/article-publication/content"
    files = sorted(p.name for p in content.iterdir() if p.is_file())
    after = {item["after_sha256"] for item in request["payloads"]}
    assert set(files) == after
    for name in files:
        raw = (content / name).read_bytes()
        assert sha(raw) == name
    by_path = {item["path"]: item for item in request["payloads"]}
    assert by_path["wiki/meta/articles/heads.json"]["mode"] == "create"
    assert by_path["wiki/meta/articles/heads.json"]["before_sha256"] is None
    _copy_staged_articles(world, "p1", "applied-check")
    _apply_staged_articles(world, "applied-check")
    store = _load_applied_store(world)
    assert data["prospective_inventory_sha256"] == article_inventory_digest(store)
    heads_raw = (world["vault"] / "wiki/meta/articles/heads.json").read_bytes()
    assert heads_raw == canonicalize(derive_article_heads(store))
    _remove_articles_store(world)
    assert _snapshot(world["vault"]) == vault_before
    assert _articles_snapshot(world, "p1") == articles_before
    pub_root = world["checkout"] / ".work/p1/article-publication"
    assert pub_root.is_dir()
    work_after_compile = {
        str(path.relative_to(work_root)): path.read_bytes()
        for path in work_root.rglob("*")
        if path.is_file()
        and path.relative_to(work_root).parts[:2] != ("p1", "article-publication")
        and path.relative_to(work_root).parts[:1] != ("applied-check",)
    }
    assert work_after_compile == outside_before
    _expect(lambda: _compile(world, "p1"), "STAGING_CONFLICT")
    _copy_staged_articles(world, "p1", "p1b")
    other = _compile(world, "p1b")
    left = dict(_request(world, "p1"))
    right = dict(_request(world, "p1b"))
    left.pop("batch_id")
    right.pop("batch_id")
    assert left == right
    assert other["batch_id"] == "p1b"


def test_compile_gates(world):
    data = _export_ctx(world)
    _import_doc(world, data, _outline_doc(data["context"]), batch="g0", recorded_at=_ts(0), tag="-o")
    err = _expect(lambda: _compile(world, "g0"), "ARTICLE_COMPILE_INCOMPLETE")
    assert err.details["next_action"] == "write_unwritten_sections"
    assert err.details["unwritten"] == 7
    assert not (world["checkout"] / ".work/g0/article-publication").exists()
    complete = _stage_complete(world, batch="g1")
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os.chmod(src_path, 0o600)
    err = _expect(lambda: _compile(world, "g1"), "ARTICLE_COMPILE_NOT_CURRENT")
    assert err.details["check_status"] == "affected"
    assert err.details["next_action"] == "revise_affected_sections"
    assert err.details["affected_sections"]
    src_path.write_bytes(src_original)
    os.chmod(src_path, 0o600)
    _compile(world, "g1")
    _apply_staged_articles(world, "g1")
    head = complete["full"]["record"]
    art = head["article_id"]
    path = world["vault"] / "wiki/meta/articles/records" / art / (head["revision_id"] + ".json")
    doc = json.loads(path.read_bytes())
    claim_id = complete["claim"]["evidence_id"]
    doc["bibliography"] = [item for item in doc["bibliography"] if item["evidence_id"] != claim_id]
    doc["content_sha256"] = content_sha256_from_record(doc)
    body = {key: value for key, value in doc.items() if key != "revision_id"}
    new_id = revision_id_from_record(body)
    doc["revision_id"] = new_id
    raw = canonicalize(doc)
    path.unlink()
    new_path = path.parent / (new_id + ".json")
    new_path.write_bytes(raw)
    os.chmod(new_path, 0o600)
    store = _load_applied_store(world)
    heads_path = world["vault"] / "wiki/meta/articles/heads.json"
    heads_path.write_bytes(canonicalize(derive_article_heads(store)))
    os.chmod(heads_path, 0o600)
    child_doc = _fill_full(doc, complete["data"]["context"], [complete["claim"]["evidence_id"]])
    child_doc["title"] = "after tamper"
    child = _import_doc(
        world,
        complete["data"],
        child_doc,
        batch="g2",
        recorded_at=_ts(8),
        previous=new_id,
        tag="-c",
    )
    compiled = _compile(world, "g2")
    assert compiled["compiled_heads"][0]["check_status"] == "current"
    assert compiled["compiled_heads"][0]["revision_id"] == child["record"]["revision_id"]
    planted = dict(json.loads(new_path.read_bytes()))
    planted["previous_revision_id"] = new_id
    planted["recorded_at"] = _ts(9)
    planted["content_sha256"] = content_sha256_from_record(planted)
    body = {key: value for key, value in planted.items() if key != "revision_id"}
    planted["revision_id"] = revision_id_from_record(body)
    planted_raw = canonicalize(planted)
    dest = (
        world["checkout"]
        / ".work/g3/articles/records"
        / planted["article_id"]
        / (planted["revision_id"] + ".json")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(planted_raw)
    os.chmod(dest, 0o600)
    err = _expect(lambda: _compile(world, "g3"), "ARTICLE_COMPILE_NOT_CURRENT")
    assert err.details["check_status"] == "inconsistent"
    assert err.details["next_action"] == "repair_store"
    _remove_articles_store(world)
    first = _stage_complete(world, batch="g4")
    data_b = _export_ctx(world, "alternate question text")
    _import_doc(world, data_b, _outline_doc(data_b["context"]), batch="g4", recorded_at=_ts(10), tag="-b")
    err = _expect(lambda: _compile(world, "g4"), "ARTICLE_COMPILE_INCOMPLETE")
    complete_art = first["full"]["record"]["article_id"]
    arts = sorted(
        (path.name for path in (world["checkout"] / ".work/g4/articles/records").iterdir() if path.is_dir()),
        key=lambda item: item.encode("utf-8"),
    )
    outline_only = [item for item in arts if item != complete_art][0]
    assert err.details.get("article_id") == outline_only
    genesis = _stage_complete(world, batch="g5")
    _apply_staged_articles(world, "g5")
    old_heads = (world["vault"] / "wiki/meta/articles/heads.json").read_bytes()
    status = status_article_store(vault_root=str(world["vault"]))
    old_head = status["articles"][0]["head_revision_id"]
    art = status["articles"][0]["article_id"]
    head_doc = json.loads(
        (world["vault"] / "wiki/meta/articles/records" / art / (old_head + ".json")).read_bytes()
    )
    cont_data = _export_ctx(world)
    cont1 = _import_doc(
        world,
        cont_data,
        {"schema": "video-paper-wiki.article-document.v1", "title": "continued-one", "sections": head_doc["sections"]},
        batch="g6",
        recorded_at=_ts(12),
        previous=old_head,
        tag="-c1",
    )
    _import_doc(
        world,
        cont_data,
        {"schema": "video-paper-wiki.article-document.v1", "title": "continued-two", "sections": head_doc["sections"]},
        batch="g6",
        recorded_at=_ts(13),
        previous=cont1["record"]["revision_id"],
        tag="-c2",
    )
    compiled = _compile(world, "g6")
    request = _request(world, "g6")
    heads = next(item for item in request["payloads"] if item["path"].endswith("heads.json"))
    assert heads["mode"] == "replace"
    assert heads["before_sha256"] == sha(old_heads)
    assert compiled["compiled_heads"][0]["previous_vault_revision_id"] == old_head
    assert compiled["compiled_heads"][0]["staged_revision_count"] == 2
    assert compiled["payload_count"] == 3
    assert genesis["full"]["record"]["article_id"] == art


def test_compile_input_failures(world):
    _expect(lambda: _compile(world, "missing"), "ARTICLE_COMPILE_EMPTY")
    render_only = world["checkout"] / ".work/r0/articles/render"
    render_only.mkdir(parents=True)
    (render_only / "note.md").write_text("x", encoding="utf-8")
    os.chmod(render_only / "note.md", 0o600)
    _expect(lambda: _compile(world, "r0"), "ARTICLE_COMPILE_EMPTY")
    staged = _stage_complete(world, batch="c1")
    extra = world["checkout"] / ".work/c1/articles/extra"
    extra.mkdir()
    err = _expect(lambda: _compile(world, "c1"), "ARTICLE_STORE_INVALID")
    assert err.details["reason"] == "unknown_entry"
    extra.rmdir()
    rec_path = next((world["checkout"] / ".work/c1/articles/records").rglob("*.json"))
    rec_bytes = rec_path.read_bytes()
    renamed = rec_path.parent / ("arv-" + "a" * 20 + ".json")
    rec_path.rename(renamed)
    err = _expect(lambda: _compile(world, "c1"), "ARTICLE_STORE_INVALID")
    assert err.details["reason"] == "path_identity"
    renamed.rename(rec_path)
    rec_path.write_bytes(json.dumps(json.loads(rec_bytes), indent=2).encode("utf-8"))
    os.chmod(rec_path, 0o600)
    err = _expect(lambda: _compile(world, "c1"), "ARTICLE_STORE_INVALID")
    assert err.details["reason"] == "canonical_bytes"
    rec_path.write_bytes(rec_bytes)
    os.chmod(rec_path, 0o600)
    link = rec_path.parent / ("arv-" + "c" * 20 + ".json")
    os.symlink(rec_path, link)
    err = _expect(lambda: _compile(world, "c1"), "ARTICLE_STORE_INVALID")
    assert err.details.get("reason") == "symlink"
    link.unlink()
    _compile(world, "c1")
    _apply_staged_articles(world, "c1")
    _copy_staged_articles(world, "c1", "c2")
    err = _expect(lambda: _compile(world, "c2"), "ARTICLE_COMPILE_ALREADY_PUBLISHED")
    assert err.details["next_action"] == "discard_batch"
    vault_head = status_article_store(vault_root=str(world["vault"]))["articles"][0]
    head_id = vault_head["head_revision_id"]
    art = vault_head["article_id"]
    cont_data = _export_ctx(world)
    head_doc = json.loads(
        (world["vault"] / "wiki/meta/articles/records" / art / (head_id + ".json")).read_bytes()
    )
    cont1 = _import_doc(
        world,
        cont_data,
        {"schema": "video-paper-wiki.article-document.v1", "title": "move-head", "sections": head_doc["sections"]},
        batch="c3",
        recorded_at=_ts(20),
        previous=head_id,
        tag="-m",
    )
    _apply_staged_articles(world, "c3")
    planted = dict(head_doc)
    planted["title"] = "stale-previous"
    planted["previous_revision_id"] = head_id
    planted["recorded_at"] = _ts(21)
    planted["content_sha256"] = content_sha256_from_record(planted)
    body = {key: value for key, value in planted.items() if key != "revision_id"}
    planted["revision_id"] = revision_id_from_record(body)
    dest = (
        world["checkout"]
        / ".work/c4/articles/records"
        / art
        / (planted["revision_id"] + ".json")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(canonicalize(planted))
    os.chmod(dest, 0o600)
    err = _expect(lambda: _compile(world, "c4"), "ARTICLE_STORE_CHAIN_INVALID")
    assert err.details.get("reason") == "staged_previous"
    import video_paper_wiki.article_publication as publication

    assert publication.MAX_STAGED_RECORDS == 512
    _copy_staged_articles(world, "c1", "c5")
    original = publication.MAX_STAGED_RECORDS
    publication.MAX_STAGED_RECORDS = 2
    try:
        _expect(lambda: _compile(world, "c5"), "ARTICLE_COMPILE_LIMIT")
    finally:
        publication.MAX_STAGED_RECORDS = original
    assert MAX_STAGED_RECORDS == 512
    real_read = publication._Snapshot.read
    seen_reads = {}

    def changed_read(self, relative, *, max_bytes=64 * 1024 * 1024):
        raw = real_read(self, relative, max_bytes=max_bytes)
        if relative.startswith("records/") and not relative.startswith("wiki/"):
            seen_reads[relative] = seen_reads.get(relative, 0) + 1
            if seen_reads[relative] >= 2:
                return raw + b" "
        return raw

    _copy_staged_articles(world, "c1", "c6")
    publication._Snapshot.read = changed_read
    try:
        err = _expect(lambda: _compile(world, "c6"), "ARTICLE_COMPILE_CHANGED")
        assert err.exit_code == 75
    finally:
        publication._Snapshot.read = real_read
    ledger = world["vault"] / CLAIM_LEDGER
    saved = ledger.read_bytes()
    ledger.unlink()
    err = _expect(lambda: _compile(world, "c6"), "DOMAIN_STORE_INVALID")
    assert err.details.get("reason") == "authority"
    _write(ledger, saved)
    reviews = world["vault"] / "wiki/meta/experiments/reviews"
    reviews.mkdir(parents=True)
    _expect(lambda: _compile(world, "c6"), "EXPERIMENT_STORE_INVALID")
    reviews.rmdir()
    notes = world["vault"] / "wiki/meta/articles/notes.txt"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("nope", encoding="utf-8")
    os.chmod(notes, 0o600)
    _expect(lambda: _compile(world, "c6"), "ARTICLE_STORE_INVALID")
    notes.unlink()
    heads = world["vault"] / "wiki/meta/articles/heads.json"
    if heads.exists():
        saved_heads = heads.read_bytes()
        heads.unlink()
        _expect(lambda: _compile(world, "c6"), "ARTICLE_STORE_HEADS_MISSING")
        _write(heads, saved_heads)
    assert staged["full"]["record"]["revision_id"]
    assert cont1["record"]["revision_id"]


def test_publish_inspect_positive_and_refusals(world):
    staged = _stage_complete(world, batch="p1")
    compiled = _compile(world, "p1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    inspection = _inspect(world, "p1")
    validate_document(inspection, INSPECTION_SCHEMA)
    request_path = world["checkout"] / ".work/p1/article-publication/request.json"
    assert inspection["request_sha256"] == sha(request_path.read_bytes())
    assert inspection["request"] == json.loads(request_path.read_bytes())
    assert inspection["gates_verified"] is True
    assert inspection["next_action"] == "apply_via_vpwiki_admin"
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    again = _inspect(world, "p1")
    assert canonicalize(again) == canonicalize(inspection)
    _expect(
        lambda: inspect_article_publication(
            prepared=str(world["checkout"] / ".work/p1/experiment-publication/request.json"),
            vault_root=str(world["vault"]),
        ),
        "WORK_PATH_UNSAFE",
    )
    _expect(
        lambda: inspect_article_publication(
            prepared=str(world["checkout"] / ".work/p1/domain-publication/request.json"),
            vault_root=str(world["vault"]),
        ),
        "WORK_PATH_UNSAFE",
    )
    rec_prepared = next((world["checkout"] / ".work/p1/articles/records").rglob("*.json"))
    _expect(
        lambda: inspect_article_publication(prepared=str(rec_prepared), vault_root=str(world["vault"])),
        "WORK_PATH_UNSAFE",
    )
    _expect(
        lambda: inspect_article_publication(prepared="/etc/passwd", vault_root=str(world["vault"])),
        "WORK_PATH_UNSAFE",
    )
    request = _request(world, "p1")
    content_dir = world["checkout"] / ".work/p1/article-publication/content"
    digest = request["payloads"][0]["after_sha256"]
    content_path = content_dir / digest
    original = content_path.read_bytes()
    content_path.unlink()
    _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_CONTENT_MISMATCH")
    _write(content_path, original)
    content_path.write_bytes(original + b"x")
    os.chmod(content_path, 0o600)
    _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_CONTENT_MISMATCH")
    content_path.write_bytes(original)
    os.chmod(content_path, 0o600)
    extra = content_dir / ("c" * 64)
    extra.write_bytes(b"{}")
    os.chmod(extra, 0o600)
    _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_CONTENT_MISMATCH")
    extra.unlink()
    request_path.write_bytes(json.dumps({**request, "extra": True}, separators=(",", ":")).encode("utf-8"))
    os.chmod(request_path, 0o600)
    _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_INVALID")
    _write(request_path, canonicalize(request))
    bad_batch = dict(request)
    bad_batch["batch_id"] = "other"
    _write(request_path, canonicalize(bad_batch))
    err = _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_INVALID")
    assert err.details["reason"] == "batch_id"
    _write(request_path, canonicalize(request))
    rec_item = next(item for item in request["payloads"] if item["path"].endswith(".json") and "/records/" in item["path"])
    mutated_item = dict(rec_item)
    new_arv = "arv-" + "d" * 20
    prefix, _sep, filename = mutated_item["path"].rpartition("/")
    mutated_item["path"] = prefix + "/" + new_arv + ".json"
    payloads = []
    for item in request["payloads"]:
        if item is rec_item or item == rec_item:
            payloads.append(mutated_item)
        else:
            payloads.append(item)
    mutated = dict(request)
    mutated["payloads"] = payloads
    _write(request_path, canonicalize(mutated))
    _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_MISMATCH")
    _write(request_path, canonicalize(request))
    ledger = world["vault"] / CLAIM_LEDGER
    original_ledger = ledger.read_bytes()
    mutated_ledger = json.loads(original_ledger)
    mutated_ledger["generated_at"] = "2026-09-14T12:00:00Z"
    _write(ledger, canonicalize(mutated_ledger))
    err = _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_STALE")
    assert err.exit_code == 75
    _write(ledger, original_ledger)
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os.chmod(src_path, 0o600)
    with pytest.raises(
        (ArticlePublicationError, ArticleStoreError, DomainStoreError, ExperimentStoreError, StagingError)
    ) as caught:
        _inspect(world, "p1")
    err = caught.value
    if err.code == "ARTICLE_PUBLICATION_STALE":
        assert err.exit_code == 75
    else:
        assert err.code == "ARTICLE_COMPILE_NOT_CURRENT"
        assert err.details["check_status"] == "affected"
    src_path.write_bytes(src_original)
    os.chmod(src_path, 0o600)
    extra_entry = world["checkout"] / ".work/p1/article-publication/notes.txt"
    extra_entry.write_text("nope", encoding="utf-8")
    os.chmod(extra_entry, 0o600)
    err = _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_INVALID")
    assert err.details["reason"] == "unknown_entry"
    extra_entry.unlink()
    from tests.unit.test_article_apply import _apply_art

    _apply_art(world, "p1")
    err = _expect(lambda: _inspect(world, "p1"), "ARTICLE_PUBLICATION_STALE")
    assert err.exit_code == 75
    assert compiled["request_sha256"]
    assert staged["full"]["record"]["revision_id"]


def test_compile_inspect_zero_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "socketpair", blocked)
    _stage_complete(world, batch="n1")
    _compile(world, "n1")
    _inspect(world, "n1")
