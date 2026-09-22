from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import subprocess
from pathlib import Path

import pytest

from tests.unit.test_article_revision import (
    _apply_staged_articles,
    _claim_and_value,
    _export,
    _import_outline,
    _provisional_section,
    _write_json,
)
from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.article_revision import (
    PROVISIONAL_LABEL,
    import_article_revision,
)
from video_paper_wiki.experiment_matrix import build_experiment_comparison_matrix
from video_paper_wiki.experiment_store import ExperimentStoreError, status_experiment_store
from video_paper_wiki.graph_projection import GraphProjectionError, build_domain_graph_projection
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.reading.view import (
    MANIFEST_KEYS,
    MAX_PAGE_BYTES,
    ReadingViewError,
    build_reading_views,
)
from video_paper_wiki.staging import StagingError


FORBIDDEN = {"ranked", "better", "winner", "score_delta", "official"}
BASIS_KEYS = (
    "domain_store_inventory_sha256",
    "claim_ledger_sha256",
    "assessment_heads_sha256",
    "experiment_store_inventory_sha256",
)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _expect(fn, code):
    with pytest.raises((ReadingViewError, GraphProjectionError, ExperimentStoreError, StagingError)) as err:
        fn()
    assert err.value.code == code
    return err.value


def _build(world, batch="r1", paper_id=None, articles_batch=None):
    return build_reading_views(
        vault_root=str(world["vault"]),
        batch_id=batch,
        paper_id=paper_id,
        articles_batch=articles_batch,
    )


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _import_full(world, batch="w1"):
    first = _import_outline(world, batch=batch)
    data = _export(world)
    rec = first["record"]
    claim, _value = _claim_and_value(data["context"])
    ctx = world["checkout"] / ("ctx-full-" + batch + ".json")
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    s1 = _provisional_section(rec["sections"][0], data["context"], [claim["evidence_id"]])
    doc = {
        "schema": "video-paper-wiki.article-document.v1",
        "title": rec["title"],
        "sections": [s1] + rec["sections"][1:],
    }
    path = world["checkout"] / ("doc-sec-" + batch + ".json")
    _write_json(path, doc)
    second = import_article_revision(
        vault_root=str(world["vault"]),
        batch_id=batch,
        context=str(ctx),
        document=str(path),
        recorded_by="t",
        recorded_at="2026-09-15T01:00:00Z",
        previous_revision_id=rec["revision_id"],
        target_section_id=rec["sections"][0]["section_id"],
    )
    rec2 = second["record"]
    filled = []
    for section in rec2["sections"]:
        if section["status"] == "provisional":
            filled.append(section)
        elif section["role"] == "unknowns":
            item = dict(section)
            item["status"] = "unknown"
            item["markdown"] = "证据不足"
            item["citations"] = []
            filled.append(item)
        else:
            filled.append(_provisional_section(section, data["context"], [claim["evidence_id"]]))
    doc3 = {"schema": "video-paper-wiki.article-document.v1", "title": rec2["title"], "sections": filled}
    path3 = world["checkout"] / ("doc-full-" + batch + ".json")
    _write_json(path3, doc3)
    return import_article_revision(
        vault_root=str(world["vault"]),
        batch_id=batch,
        context=str(ctx),
        document=str(path3),
        recorded_by="t",
        recorded_at="2026-09-15T02:00:00Z",
        previous_revision_id=rec2["revision_id"],
    )


def _reading_root(world, batch):
    return world["checkout"] / ".work" / batch / "reading"


def test_manifest_basis_counts_and_determinism(world, monkeypatch):
    _three_chain(world)
    vault_before = _snapshot(world["vault"])
    work = world["checkout"] / ".work"
    work_before = _snapshot(work) if work.exists() else {}
    sockets = []
    pops = []

    def boom_socket(*_args, **_kwargs):
        sockets.append(1)
        raise AssertionError("socket")

    def boom_popen(*_args, **_kwargs):
        pops.append(1)
        raise AssertionError("popen")

    monkeypatch.setattr(socket, "socket", boom_socket)
    monkeypatch.setattr(subprocess, "Popen", boom_popen)
    data = _build(world, "r1")
    assert set(data) - {"staging"} == set(MANIFEST_KEYS)
    graph = build_domain_graph_projection(vault_root=str(world["vault"]))
    status = status_experiment_store(vault_root=str(world["vault"]))
    matrix = build_experiment_comparison_matrix(vault_root=str(world["vault"]))
    assert {key: data["basis"][key] for key in BASIS_KEYS} == {key: graph["basis"][key] for key in BASIS_KEYS}
    assert {key: data["basis"][key] for key in BASIS_KEYS} == {key: status["basis"][key] for key in BASIS_KEYS}
    assert data["graph_sha256"] == graph["graph_sha256"]
    assert data["matrix_sha256"] == hashlib.sha256(canonicalize(matrix)).hexdigest()
    assert data["counts"]["papers"] == 2
    assert data["counts"]["conditions"] == 3
    assert data["counts"]["pairwise"] == len(matrix["pairwise"])
    assert data["counts"]["lineages"] == 1
    from video_paper_wiki.domain_structure import build_domain_structure_view
    from video_paper_wiki.domain_claims import build_domain_claim_coverage_view

    structure = build_domain_structure_view(vault_root=str(world["vault"]))
    coverage = build_domain_claim_coverage_view(vault_root=str(world["vault"]))
    assert data["counts"]["concepts"] == len(structure["concepts"])
    assert data["counts"]["claims"] == len(coverage["claims"])
    assert data["counts"]["articles"] == 0
    assert data["articles"] == []
    index = (_reading_root(world, "r1") / "articles" / "list.md").read_text(encoding="utf-8")
    assert "暂无" in index
    assert not (FORBIDDEN & set(_walk_keys(data)))
    assert sockets == []
    assert pops == []
    other = _build(world, "r2")
    left = _reading_root(world, "r1")
    right = _reading_root(world, "r2")
    left_files = {
        p.relative_to(left): p.read_bytes()
        for p in left.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    right_files = {
        p.relative_to(right): p.read_bytes()
        for p in right.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    assert left_files == right_files
    assert other["counts"] == data["counts"]
    assert _snapshot(world["vault"]) == vault_before
    after = _snapshot(work)
    for rel in after:
        if rel.startswith("r1/reading/") or rel.startswith("r2/reading/"):
            continue
        if rel.startswith("r1/articles/render/") or rel.startswith("r2/articles/render/"):
            continue
        assert after[rel] == work_before.get(rel)


def test_basis_changed_missing_key_limit_conflict_filter_reviews(world, monkeypatch):
    _three_chain(world)
    import video_paper_wiki.reading.view as view_mod
    import video_paper_wiki.domain_structure as structure_mod

    original = structure_mod.build_domain_structure_view

    def tampered(*, vault_root, paper_id=None):
        document = original(vault_root=vault_root, paper_id=paper_id)
        basis = dict(document["basis"])
        basis["experiment_store_inventory_sha256"] = "0" * 64
        document = dict(document)
        document["basis"] = basis
        return document

    monkeypatch.setattr(structure_mod, "build_domain_structure_view", tampered)
    monkeypatch.setattr(view_mod, "build_domain_structure_view", tampered)
    err = _expect(lambda: _build(world, "bad-basis"), "READING_BASIS_CHANGED")
    assert err.exit_code == 75
    assert not _reading_root(world, "bad-basis").exists()
    monkeypatch.setattr(structure_mod, "build_domain_structure_view", original)
    monkeypatch.setattr(view_mod, "build_domain_structure_view", original)

    def missing(*, vault_root, paper_id=None):
        return {"schema": "x"}

    monkeypatch.setattr(structure_mod, "build_domain_structure_view", missing)
    monkeypatch.setattr(view_mod, "build_domain_structure_view", missing)
    err = _expect(lambda: _build(world, "bad-shape"), "READING_INVALID")
    assert err.details.get("reason") == "upstream_shape"
    assert not _reading_root(world, "bad-shape").exists()
    monkeypatch.setattr(structure_mod, "build_domain_structure_view", original)
    monkeypatch.setattr(view_mod, "build_domain_structure_view", original)

    monkeypatch.setattr(view_mod, "MAX_PAGE_BYTES", 1024)
    err = _expect(lambda: _build(world, "tiny"), "READING_LIMIT")
    assert not _reading_root(world, "tiny").exists()
    monkeypatch.setattr(view_mod, "MAX_PAGE_BYTES", MAX_PAGE_BYTES)

    conflict = world["checkout"] / ".work" / "c1" / "reading" / "articles" / "list.md"
    conflict.parent.mkdir(parents=True, exist_ok=True)
    conflict.write_bytes(b"not-the-reading-page\n")
    os.chmod(conflict, 0o600)
    err = _expect(lambda: _build(world, "c1"), "STAGING_CONFLICT")
    assert err.code == "STAGING_CONFLICT"

    first = world["association"]["paper_id"]
    filtered = _build(world, "filt", paper_id=first)
    paper_pages = [row for row in filtered["pages"] if row["path"].startswith("papers/")]
    assert len(paper_pages) == 1
    assert filtered["counts"]["papers"] == 1
    matrix = (_reading_root(world, "filt") / "compare" / "matrix.md").read_text(encoding="utf-8")
    assert first in matrix
    assert "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" not in matrix

    reviews = world["vault"] / "wiki/meta/experiments/reviews"
    reviews.mkdir()
    (reviews / "x.json").write_bytes(b"{}\n")
    os.chmod(reviews / "x.json", 0o600)
    err = _expect(lambda: _build(world, "rev"), "EXPERIMENT_STORE_INVALID")
    assert not _reading_root(world, "rev").exists()


def test_article_paths_render_and_mismatch(world, monkeypatch):
    _three_chain(world)
    outline = _import_outline(world, batch="w2")
    sketched = _build(world, "r3", articles_batch="w2")
    assert sketched["articles"][0]["complete"] is False
    sketch_page = (
        _reading_root(world, "r3") / "articles" / (sketched["articles"][0]["article_id"] + ".md")
    ).read_text(encoding="utf-8")
    assert sketch_page.count("尚未撰写") == 7
    full = _import_full(world, "w1")
    data = _build(world, "r1", articles_batch="w1")
    assert data["articles"][0]["head_location"] == "staged"
    assert data["articles"][0]["render_path"].startswith(".work/w1/articles/render/")
    assert data["articles"][0]["check_status"] == "current"
    page = (_reading_root(world, "r1") / "articles" / (data["articles"][0]["article_id"] + ".md")).read_bytes()
    assert data["articles"][0]["render_sha256"][:16].encode("ascii") in page
    assert PROVISIONAL_LABEL.encode("utf-8") in page
    checkout = world["checkout"]
    render_path = checkout / data["articles"][0]["render_path"]
    assert render_path.read_bytes() in page
    index = (_reading_root(world, "r1") / "articles" / "list.md").read_text(encoding="utf-8")
    assert "staged" in index
    import video_paper_wiki.reading.view as view_mod

    real = view_mod.read_regular_file

    def other(*args, **kwargs):
        payload = real(*args, **kwargs)
        return payload + b"x"

    monkeypatch.setattr(view_mod, "read_regular_file", other)
    err = _expect(lambda: _build(world, "r4", articles_batch="w1"), "READING_RENDER_MISMATCH")
    assert err.code == "READING_RENDER_MISMATCH"
    monkeypatch.setattr(view_mod, "read_regular_file", real)
    _apply_staged_articles(world, "w1")
    vaulted = _build(world, "r2")
    assert vaulted["articles"][0]["head_location"] == "vault_store"
    assert vaulted["articles"][0]["render_path"].startswith(".work/r2/articles/render/")
    vault_index = (_reading_root(world, "r2") / "articles" / "list.md").read_text(encoding="utf-8")
    assert "../../meta/articles/records/" in vault_index
    assert full["record"]["article_id"] == data["articles"][0]["article_id"]
    assert outline["record"]["kind"] == "outline"
    assert stat.S_ISREG((_reading_root(world, "r1") / "manifest.json").stat().st_mode)
    raw = (_reading_root(world, "r1") / "manifest.json").read_bytes()
    assert raw == canonicalize(json.loads(raw.decode("utf-8")))
    assert not raw.endswith(b"\n\n")


def test_validate_document_hook_before_first_stage_bytes(world, monkeypatch):
    _three_chain(world)
    import video_paper_wiki.reading.view as view_mod

    calls = []
    real = view_mod.validate_document
    vault_before = _snapshot(world["vault"])

    def wrapper(document, expected_schema=None):
        calls.append((document, expected_schema))
        assert expected_schema == "video-paper-wiki.reading-manifest.v1"
        assert set(document) == set(MANIFEST_KEYS)
        assert "staging" not in document
        assert len(document["pages"]) == document["counts"]["pages"]
        assert not _reading_root(world, "hook").exists()
        return real(document, expected_schema)

    monkeypatch.setattr(view_mod, "validate_document", wrapper)
    data = _build(world, "hook")
    assert len(calls) == 1
    manifest = {key: value for key, value in data.items() if key != "staging"}
    raw = (_reading_root(world, "hook") / "manifest.json").read_bytes()
    assert canonicalize(manifest) == raw

    def boom(document, expected_schema=None):
        raise ContractError("SCHEMA_INVALID", "forced", {"instance_pointer": "/x"})

    monkeypatch.setattr(view_mod, "validate_document", boom)
    with pytest.raises(ContractError) as err:
        _build(world, "hook-fail")
    assert err.value.code == "SCHEMA_INVALID"
    assert err.value.message == "forced"
    assert err.value.details.get("instance_pointer") == "/x"
    assert not _reading_root(world, "hook-fail").exists()
    assert _snapshot(world["vault"]) == vault_before
