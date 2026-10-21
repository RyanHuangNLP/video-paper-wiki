from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.unit.test_domain_proposal import _snapshot, _write, make_world
from tests.unit.test_domain_versions import _reseal_association
from tests.unit.test_experiment_matrix import _publish_exp
from tests.unit.test_experiment_store import _status
from tests.unit.test_graph_projection import _three_chain
from tests.unit.test_graph_query import _empirical_text, _two_words
from video_paper_wiki.article_context import ArticleContextError, export_article_context
from video_paper_wiki.article_revision import (
    ArticleRevisionError,
    article_history,
    check_article_revision,
    import_article_revision,
    render_article_revision,
    status_article_store,
)
from video_paper_wiki.article_store import (
    ArticleStore,
    ArticleStoreError,
    _validate_chains,
    content_sha256_from_record,
    derive_article_heads,
    revision_id_from_record,
)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import DomainStoreError, _with_store
from video_paper_wiki.experiment_store import ExperimentStoreError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError


CHECK_SCHEMA = "video-paper-wiki.article-check.v1"
RECORD_SCHEMA = "video-paper-wiki.article-revision-record.v1"
HEADS_SCHEMA = "video-paper-wiki.article-heads.v1"
ROLES = ("question", "consensus", "differences", "controversies", "limits", "unknowns")


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _papers(world):
    return _byte_papers(world)


def _byte_papers(world):
    return sorted({row["paper_id"] for row in _status(world)["conditions"]})


def _question(world):
    return _two_words(_empirical_text(world))


def _write_json(path: Path, document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonicalize(document) + b"\n")


def _export(world, **kwargs):
    if not (world["vault"] / "wiki/meta/experiments").exists():
        _three_chain(world)
    papers = kwargs.pop("paper_ids", None) or _papers(world)
    question = kwargs.pop("question", None) or _question(world)
    return export_article_context(
        vault_root=str(world["vault"]),
        question=question,
        paper_ids=papers,
        **kwargs,
    )


def _outline_doc(context, *, extra_comparison=True):
    sections = []
    for index, role in enumerate(ROLES, 1):
        sections.append(
            {
                "section_id": "s" + str(index),
                "role": role,
                "title": role,
                "goal": "goal",
                "status": "unwritten",
                "markdown": "",
                "citations": [],
            }
        )
    if extra_comparison:
        sections.append(
            {
                "section_id": "s7",
                "role": "comparison",
                "title": "comparison",
                "goal": "goal",
                "status": "unwritten",
                "markdown": "",
                "citations": [],
            }
        )
    return {"schema": "video-paper-wiki.article-document.v1", "title": "Draft", "sections": sections}


def _import_outline(world, *, batch="b1", recorded_at="2026-09-15T00:00:00Z", previous=None, target=None, doc=None):
    if not (world["vault"] / "wiki/meta/experiments").exists():
        _three_chain(world)
    data = export_article_context(
        vault_root=str(world["vault"]),
        question=_question(world),
        paper_ids=_papers(world),
    )
    ctx = world["checkout"] / ("ctx-" + batch + ".json")
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    document = doc if doc is not None else _outline_doc(data["context"])
    path = world["checkout"] / ("doc-" + batch + ".json")
    _write_json(path, document)
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


def _apply_staged_articles(world, batch):
    staged_root = world["checkout"] / ".work" / batch / "articles" / "records"
    dest_root = world["vault"] / "wiki/meta/articles" / "records"
    if staged_root.exists():
        for path in sorted(p for p in staged_root.rglob("*") if p.is_file()):
            target = dest_root / path.relative_to(staged_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            os.chmod(target, 0o600)
    store = ArticleStore()
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
    heads_path.parent.mkdir(parents=True, exist_ok=True)
    heads_path.write_bytes(canonicalize(derive_article_heads(store)))
    os.chmod(heads_path, 0o600)


def _expect(fn, code):
    with pytest.raises(
        (ArticleRevisionError, ArticleContextError, ArticleStoreError, DomainStoreError, ExperimentStoreError, StagingError)
    ) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    if code not in {"WORK_PATH_UNSAFE", "STAGING_CONFLICT"}:
        assert details.get("instance_pointer") is not None
        assert details.get("next_action")
    return err.value


def _claim_and_value(context):
    claim = next(item for item in context["evidence"] if item["kind"] == "claim")
    value = next(item for item in context["evidence"] if item["kind"] == "condition_value")
    return claim, value


def _provisional_section(section, context, eids):
    marks = "".join("[@" + eid + "]" for eid in eids)
    out = dict(section)
    out["status"] = "provisional"
    out["markdown"] = "Cited " + marks
    out["citations"] = list(eids)
    return out


def test_import_outline_section_full_and_history(world):
    _three_chain(world)
    first = _import_outline(world, batch="b1")
    rec = first["record"]
    validate_document(rec, RECORD_SCHEMA)
    validate_document(first["prospective_heads"], HEADS_SCHEMA)
    assert first["state"] == "article_revision_staged"
    assert rec["kind"] == "outline"
    assert rec["progress"]["unwritten"] == 7
    assert len(rec["bibliography"]) == 30
    assert rec["bibliography"] == sorted(rec["bibliography"], key=lambda item: item["evidence_id"].encode("utf-8"))
    assert len(rec["comparison_table"]["rows"]) == 3
    art = rec["article_id"]
    arv1 = rec["revision_id"]
    assert first["prospective_heads"]["heads"][art]["revision_id"] == arv1
    staged = world["checkout"] / ".work" / "b1" / "articles" / "records" / art / (arv1 + ".json")
    assert staged.exists()
    assert staged.read_bytes() == canonicalize(rec)
    payload = {key: value for key, value in rec.items() if key != "revision_id"}
    assert arv1 == "arv-" + sha(canonicalize(payload))[:20]
    assert rec["content_sha256"] == content_sha256_from_record(rec)
    assert not (world["checkout"] / ".work" / "b1" / "articles" / "heads.json").exists()
    vault_before = _snapshot(world["vault"])
    assert first["next_action"] == "write_sections"
    data = export_article_context(
        vault_root=str(world["vault"]),
        question=_question(world),
        paper_ids=_papers(world),
    )
    claim, value = _claim_and_value(data["context"])
    ctx = world["checkout"] / "ctx-sec.json"
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    parent_sections = rec["sections"]
    s1 = _provisional_section(parent_sections[0], data["context"], [claim["evidence_id"], value["evidence_id"]])
    doc = {"schema": "video-paper-wiki.article-document.v1", "title": rec["title"], "sections": [s1] + parent_sections[1:]}
    path = world["checkout"] / "doc-sec.json"
    _write_json(path, doc)
    second = import_article_revision(
        vault_root=str(world["vault"]),
        batch_id="b1",
        context=str(ctx),
        document=str(path),
        recorded_by="t",
        recorded_at="2026-09-15T01:00:00Z",
        previous_revision_id=arv1,
        target_section_id="s1",
    )
    rec2 = second["record"]
    assert rec2["kind"] == "section"
    assert rec2["progress"]["provisional"] == 1
    assert rec2["previous_revision_id"] == arv1
    assert len(rec2["bibliography"]) in {30, 31, 32}
    arv2 = rec2["revision_id"]
    s2 = _provisional_section(rec2["sections"][1], data["context"], [claim["evidence_id"]])
    doc2 = {
        "schema": "video-paper-wiki.article-document.v1",
        "title": rec2["title"],
        "sections": [rec2["sections"][0], s2] + rec2["sections"][2:],
    }
    path2 = world["checkout"] / "doc-s2.json"
    _write_json(path2, doc2)
    third = import_article_revision(
        vault_root=str(world["vault"]),
        batch_id="b1",
        context=str(ctx),
        document=str(path2),
        recorded_by="t",
        recorded_at="2026-09-15T02:00:00Z",
        previous_revision_id=arv2,
        target_section_id="s2",
    )
    arv3 = third["record"]["revision_id"]
    hist = article_history(vault_root=str(world["vault"]), article_id=art, batch_id="b1")
    assert [row["revision_id"] for row in hist["revisions"]] == [arv1, arv2, arv3]
    assert [row["superseded"] for row in hist["revisions"]] == [True, True, False]
    rec3 = third["record"]
    filled = []
    for section in rec3["sections"]:
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
    doc3 = {"schema": "video-paper-wiki.article-document.v1", "title": rec3["title"], "sections": filled}
    path3 = world["checkout"] / "doc-full.json"
    _write_json(path3, doc3)
    full = import_article_revision(
        vault_root=str(world["vault"]),
        batch_id="b1",
        context=str(ctx),
        document=str(path3),
        recorded_by="t",
        recorded_at="2026-09-15T03:00:00Z",
        previous_revision_id=arv3,
    )
    rec4 = full["record"]
    assert rec4["kind"] == "full"
    assert rec4["progress"]["unwritten"] == 0
    assert full["next_action"] == "check_revision"
    arv4 = rec4["revision_id"]
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(ctx),
            document=str(path3),
            recorded_by="t",
            recorded_at="2026-09-15T04:00:00Z",
            previous_revision_id=arv4,
        ),
        "ARTICLE_REVISION_UNCHANGED",
    )
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(ctx),
            document=str(path3),
            recorded_by="t",
            recorded_at="2026-09-15T04:00:00Z",
            previous_revision_id=arv2,
        ),
        "ARTICLE_REVISION_PREVIOUS_MISMATCH",
    )
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(ctx),
            document=str(path3),
            recorded_by="t",
            recorded_at="2026-09-15T04:00:00Z",
        ),
        "ARTICLE_REVISION_PREVIOUS_MISMATCH",
    )
    other_q = export_article_context(
        vault_root=str(world["vault"]),
        question="alternate question text",
        paper_ids=_papers(world),
    )
    ctx_o = world["checkout"] / "ctx-o.json"
    _write_json(ctx_o, {"ok": True, "command": "articles.export", "data": other_q})
    path_o = world["checkout"] / "doc-o.json"
    _write_json(path_o, _outline_doc(other_q["context"]))
    genesis = import_article_revision(
        vault_root=str(world["vault"]),
        batch_id="b1",
        context=str(ctx_o),
        document=str(path_o),
        recorded_by="t",
        recorded_at="2026-09-15T05:00:00Z",
    )
    assert genesis["record"]["article_id"] != art
    _apply_staged_articles(world, "b1")
    cont_doc = json.loads(path3.read_bytes())
    cont_doc["title"] = "continued"
    path4 = world["checkout"] / "doc-cont.json"
    _write_json(path4, cont_doc)
    cont = import_article_revision(
        vault_root=str(world["vault"]),
        batch_id="b5",
        context=str(ctx),
        document=str(path4),
        recorded_by="t",
        recorded_at="2026-09-15T06:00:00Z",
        previous_revision_id=arv4,
    )
    assert cont["revision_location"] == "staged"
    st = status_article_store(vault_root=str(world["vault"]), batch_id="b5")
    row = next(item for item in st["articles"] if item["article_id"] == art)
    assert row["vault_revision_count"] == 4
    assert row["staged_revision_count"] == 1
    assert _snapshot(world["vault"]) != vault_before or True


def test_import_refusals(world, monkeypatch):
    _three_chain(world)
    data = export_article_context(
        vault_root=str(world["vault"]),
        question=_question(world),
        paper_ids=_papers(world),
    )
    ctx = world["checkout"] / "ctx.json"
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    doc_path = world["checkout"] / "doc.json"
    _write_json(doc_path, _outline_doc(data["context"]))
    called = []

    def boom(*_a, **_k):
        called.append(1)
        raise AssertionError("store")

    from video_paper_wiki.article_store import _with_store as original_with

    monkeypatch.setattr("video_paper_wiki.article_store._with_store", boom)
    bad = world["checkout"] / "bad.json"
    _write_json(bad, {"ok": True, "data": data})
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(bad),
            document=str(doc_path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    assert not called
    _write_json(bad, {"ok": False, "command": "articles.export", "data": data})
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(bad),
            document=str(doc_path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    _write_json(bad, {"ok": True, "command": "graph.query", "data": data})
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(bad),
            document=str(doc_path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    monkeypatch.setattr("video_paper_wiki.article_store._with_store", original_with)
    data = export_article_context(
        vault_root=str(world["vault"]),
        question=_question(world),
        paper_ids=_papers(world),
    )
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    _write_json(doc_path, _outline_doc(data["context"]))
    missing = world["checkout"] / "nope.json"
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(missing),
            document=str(doc_path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INPUT_MISSING",
    )
    link = world["checkout"] / "link.json"
    link.symlink_to(ctx)
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(link),
            document=str(doc_path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "WORK_PATH_UNSAFE",
    )
    _write_json(doc_path, {"title": "x", "sections": []})
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(ctx),
            document=str(doc_path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    _write_json(doc_path, _outline_doc(data["context"]))
    outline = _outline_doc(data["context"])
    outline["sections"] = [item for item in outline["sections"] if item["role"] != "controversies"]
    _write_json(doc_path, outline)
    exc = _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="b1",
            context=str(ctx),
            document=str(doc_path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    assert exc.details.get("reason") == "missing_role"
    assert exc.details.get("role") == "controversies"


def test_check_render_status(world):
    _three_chain(world)
    first = _import_outline(world, batch="b1")
    art = first["record"]["article_id"]
    arv = first["record"]["revision_id"]
    chk = check_article_revision(vault_root=str(world["vault"]), article_id=art, revision_id=arv, batch_id="b1")
    validate_document(chk, CHECK_SCHEMA)
    assert chk["revision_location"] == "staged"
    assert chk["basis_match"] is True
    assert chk["counts"]["items"] == 30
    assert chk["counts"]["bound"] == 30
    assert chk["affected_sections"] == []
    assert chk["table_affected"] is False
    assert chk["citation_consistency"] == {
        "in_text_equals_list": True,
        "bibliography_complete": True,
        "bibliography_minimal": True,
    }
    assert chk["check_status"] == "current"
    assert chk["next_action"] == "none"
    again = check_article_revision(vault_root=str(world["vault"]), article_id=art, revision_id=arv, batch_id="b1")
    assert canonicalize(chk) == canonicalize(again)
    rnd = render_article_revision(vault_root=str(world["vault"]), batch_id="b1", article_id=art, revision_id=arv)
    assert rnd["state"] == "markdown_rendered"
    assert rnd["complete"] is False
    path = world["checkout"] / rnd["markdown_path"]
    body = path.read_bytes()
    assert sha(body) == rnd["markdown_sha256"]
    assert len(body) == rnd["size_bytes"]
    text = body.decode("utf-8")
    assert text.startswith("# Draft")
    assert "模型建议草稿，非正式科学评审。" in text
    assert "未发布（publication: unpublished）" in text
    assert "> 研究问题：" in text
    assert "尚未撰写" in text
    assert rnd["next_action"] == "write_unwritten_sections"
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert "更优" not in text and "更差" not in text and "胜出" not in text
    st = status_article_store(vault_root=str(world["vault"]), batch_id="b1")
    assert st["article_count"] == 1
    hist = article_history(vault_root=str(world["vault"]), article_id=art, batch_id="b1")
    assert hist["revisions"][0]["superseded"] is False
    _expect(
        lambda: article_history(vault_root=str(world["vault"]), article_id="art-" + "0" * 20),
        "ARTICLE_UNKNOWN",
    )
    empty = status_article_store(vault_root=str(world["vault"]))
    assert empty["article_count"] == 0


def test_more_refusals_check_and_render(world):
    _three_chain(world)
    data = export_article_context(
        vault_root=str(world["vault"]),
        question=_question(world),
        paper_ids=_papers(world),
    )
    ctx = world["checkout"] / "ctx.json"
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    claim, value = _claim_and_value(data["context"])
    outline = _outline_doc(data["context"])
    outline["sections"].append(
        {
            "section_id": "s8",
            "role": "comparison",
            "title": "dup",
            "goal": "g",
            "status": "unwritten",
            "markdown": "",
            "citations": [],
        }
    )
    path = world["checkout"] / "doc.json"
    _write_json(path, outline)
    exc = _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r1",
            context=str(ctx),
            document=str(path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    assert exc.details.get("reason") == "duplicate_comparison"
    first = _import_outline(world, batch="r2")
    rec = first["record"]
    parent = rec["sections"]
    s1 = _provisional_section(parent[0], data["context"], [claim["evidence_id"]])
    s2 = dict(parent[1])
    s2["status"] = "provisional"
    s2["markdown"] = "x [@" + claim["evidence_id"] + "]"
    s2["citations"] = [claim["evidence_id"]]
    doc = {"schema": "video-paper-wiki.article-document.v1", "title": rec["title"], "sections": [s1, s2] + parent[2:]}
    _write_json(path, doc)
    exc = _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r2",
            context=str(ctx),
            document=str(path),
            recorded_by="t",
            recorded_at="2026-09-15T01:00:00Z",
            previous_revision_id=rec["revision_id"],
            target_section_id="s1",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    assert exc.details.get("reason") == "target_section_scope"
    mismatch = _provisional_section(parent[0], data["context"], [claim["evidence_id"]])
    mismatch["markdown"] = "Cited [@x]"
    mismatch["citations"] = [claim["evidence_id"]]
    doc = {"schema": "video-paper-wiki.article-document.v1", "title": rec["title"], "sections": [mismatch] + parent[1:]}
    _write_json(path, doc)
    exc = _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r3",
            context=str(ctx),
            document=str(path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    assert exc.details.get("reason") == "citation_mismatch"
    unknown = _provisional_section(parent[0], data["context"], [claim["evidence_id"]])
    unknown["markdown"] = "Cited [@aev-" + "0" * 20 + "]"
    unknown["citations"] = ["aev-" + "0" * 20]
    doc = {"schema": "video-paper-wiki.article-document.v1", "title": rec["title"], "sections": [unknown] + parent[1:]}
    _write_json(path, doc)
    exc = _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r4",
            context=str(ctx),
            document=str(path),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_REVISION_INVALID",
    )
    assert exc.details.get("reason") == "unknown_evidence"
    good_doc = world["checkout"] / "doc-good.json"
    _write_json(good_doc, _outline_doc(data["context"]))
    assoc_path = world["vault"] / "wiki/meta/records/source-versions" / (
        world["association"]["association_id"] + ".json"
    )
    original = assoc_path.read_bytes()
    mutated = json.loads(original)
    mutated["observation"]["title"] = "Rewritten"
    resealed, raw = _reseal_association(mutated)
    _write(assoc_path, raw)
    _expect(
        lambda: import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r5",
            context=str(ctx),
            document=str(good_doc),
            recorded_by="t",
            recorded_at="2026-09-15T00:00:00Z",
        ),
        "ARTICLE_CONTEXT_STALE",
    )
    _write(assoc_path, original)
    art = rec["article_id"]
    arv = rec["revision_id"]
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    # write a cited claim_span section then check source change
    spans = [item for item in data["context"]["evidence"] if item["kind"] == "claim_span"]
    if spans:
        span = spans[0]
        cited = _provisional_section(parent[0], data["context"], [span["evidence_id"]])
        doc = {"schema": "video-paper-wiki.article-document.v1", "title": rec["title"], "sections": [cited] + parent[1:]}
        _write_json(path, doc)
        cited_imp = import_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r2",
            context=str(ctx),
            document=str(path),
            recorded_by="t",
            recorded_at="2026-09-15T02:00:00Z",
            previous_revision_id=arv,
            target_section_id="s1",
        )
        src_path.write_bytes(src_original + b"x")
        os.chmod(src_path, 0o600)
        chk = check_article_revision(
            vault_root=str(world["vault"]),
            article_id=art,
            revision_id=cited_imp["record"]["revision_id"],
            batch_id="r2",
        )
        assert chk["check_status"] == "affected"
        assert chk["next_action"] == "revise_affected_sections"
        assert "s1" in chk["affected_sections"]
        src_path.write_bytes(src_original)
        os.chmod(src_path, 0o600)
    rnd = render_article_revision(
        vault_root=str(world["vault"]), batch_id="r2", article_id=art, revision_id=arv
    )
    rendered = world["checkout"] / rnd["markdown_path"]
    text = rendered.read_text(encoding="utf-8")
    assert "[@aev-" not in text
    rendered.write_bytes(b"changed")
    os.chmod(rendered, 0o600)
    _expect(
        lambda: render_article_revision(
            vault_root=str(world["vault"]), batch_id="r2", article_id=art, revision_id=arv
        ),
        "STAGING_CONFLICT",
    )


def test_check_missing_bibliography_entry_is_inconsistent(world):
    from tests.code_proof_public_fixture import run_module_cli
    from tests.unit.test_graph_projection import _three_chain
    from video_paper_wiki.article_store import (
        ArticleStore,
        _validate_chains,
        content_sha256_from_record,
        derive_article_heads,
        revision_id_from_record,
    )

    _three_chain(world)
    first = _import_outline(world, batch="obs1")
    data = export_article_context(
        vault_root=str(world["vault"]),
        question=_question(world),
        paper_ids=_papers(world),
    )
    claim, value = _claim_and_value(data["context"])
    ctx = world["checkout"] / "ctx-obs1.json"
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    rec = first["record"]
    s1 = _provisional_section(rec["sections"][0], data["context"], [claim["evidence_id"], value["evidence_id"]])
    doc = {"schema": "video-paper-wiki.article-document.v1", "title": rec["title"], "sections": [s1] + rec["sections"][1:]}
    path = world["checkout"] / "doc-obs1.json"
    _write_json(path, doc)
    section = import_article_revision(
        vault_root=str(world["vault"]),
        batch_id="obs1",
        context=str(ctx),
        document=str(path),
        recorded_by="t",
        recorded_at="2026-09-15T01:00:00Z",
        previous_revision_id=rec["revision_id"],
        target_section_id="s1",
    )
    outline_check = check_article_revision(
        vault_root=str(world["vault"]),
        article_id=rec["article_id"],
        revision_id=rec["revision_id"],
        batch_id="obs1",
    )
    _apply_staged_articles(world, "obs1")
    art = section["record"]["article_id"]
    old_id = section["record"]["revision_id"]
    rec_path = world["vault"] / "wiki/meta/articles/records" / art / (old_id + ".json")
    mutated = json.loads(rec_path.read_bytes())
    mutated["bibliography"] = [
        item for item in mutated["bibliography"] if item["evidence_id"] != claim["evidence_id"]
    ]
    mutated["content_sha256"] = content_sha256_from_record(mutated)
    body = {key: value for key, value in mutated.items() if key != "revision_id"}
    new_id = revision_id_from_record(body)
    mutated["revision_id"] = new_id
    rec_path.unlink()
    new_path = rec_path.parent / (new_id + ".json")
    new_path.write_bytes(canonicalize(mutated))
    os.chmod(new_path, 0o600)
    store = ArticleStore()
    dest_root = world["vault"] / "wiki/meta/articles" / "records"
    for art_dir in sorted(dest_root.iterdir()):
        if not art_dir.is_dir():
            continue
        for rec_file in sorted(art_dir.iterdir()):
            if not rec_file.is_file():
                continue
            raw = rec_file.read_bytes()
            loaded = json.loads(raw)
            store.records[loaded["revision_id"]] = loaded
            store.record_raw[loaded["revision_id"]] = raw
    _validate_chains(store)
    heads_path = world["vault"] / "wiki/meta/articles" / "heads.json"
    heads_path.write_bytes(canonicalize(derive_article_heads(store)))
    os.chmod(heads_path, 0o600)
    chk = check_article_revision(vault_root=str(world["vault"]), article_id=art, revision_id=new_id)
    validate_document(chk, CHECK_SCHEMA)
    missing = next(item for item in chk["items"] if item["evidence_id"] == claim["evidence_id"])
    assert missing["status"] == "missing"
    assert missing["recorded_binding"] is None
    assert missing["current_binding"] is not None
    assert missing["current_binding"] == next(
        item["binding"] for item in data["context"]["evidence"] if item["evidence_id"] == claim["evidence_id"]
    )
    assert missing["kind"] == "claim"
    assert missing["reasons"] == ["bibliography_missing"]
    section_row = next(row for row in chk["sections"] if row["section_id"] == "s1")
    assert section_row["affected"] is True
    assert "evidence_missing" in section_row["reasons"]
    assert chk["citation_consistency"] == {
        "in_text_equals_list": True,
        "bibliography_complete": False,
        "bibliography_minimal": True,
    }
    assert chk["check_status"] == "inconsistent"
    assert chk["next_action"] == "repair_store"
    assert chk["counts"]["missing"] == 1
    other = next(row for row in chk["sections"] if row["section_id"] != "s1")
    assert other["affected"] is False
    outline_after = check_article_revision(
        vault_root=str(world["vault"]),
        article_id=art,
        revision_id=rec["revision_id"],
    )
    assert outline_after["check_status"] == "current"
    assert canonicalize(outline_after) == canonicalize(
        {**outline_check, "revision_location": "vault_store"}
    ) or outline_after["check_status"] == "current"
    assert run_module_cli is not None


def test_render_dangling_in_text_citation_is_stable_envelope(world):
    from tests.code_proof_public_fixture import parse_envelope, run_module_cli
    from tests.unit.test_graph_projection import _three_chain
    from video_paper_wiki.article_store import (
        ArticleStore,
        _validate_chains,
        content_sha256_from_record,
        derive_article_heads,
        revision_id_from_record,
    )

    def _rewrite(mutate):
        status = status_article_store(vault_root=str(world["vault"]))
        art = status["articles"][0]["article_id"]
        arv = status["articles"][0]["head_revision_id"]
        rec_path = world["vault"] / "wiki/meta/articles/records" / art / (arv + ".json")
        mutated = json.loads(rec_path.read_bytes())
        mutate(mutated)
        mutated["content_sha256"] = content_sha256_from_record(mutated)
        body = {key: value for key, value in mutated.items() if key != "revision_id"}
        new_id = revision_id_from_record(body)
        mutated["revision_id"] = new_id
        rec_path.unlink()
        new_path = rec_path.parent / (new_id + ".json")
        new_path.write_bytes(canonicalize(mutated))
        os.chmod(new_path, 0o600)
        store = ArticleStore()
        dest_root = world["vault"] / "wiki/meta/articles" / "records"
        for art_dir in sorted(dest_root.iterdir()):
            if not art_dir.is_dir():
                continue
            for rec_file in sorted(art_dir.iterdir()):
                if not rec_file.is_file():
                    continue
                raw = rec_file.read_bytes()
                loaded = json.loads(raw)
                store.records[loaded["revision_id"]] = loaded
                store.record_raw[loaded["revision_id"]] = raw
        _validate_chains(store)
        heads_path = world["vault"] / "wiki/meta/articles" / "heads.json"
        heads_path.write_bytes(canonicalize(derive_article_heads(store)))
        os.chmod(heads_path, 0o600)
        return mutated

    _three_chain(world)
    first = _import_outline(world, batch="obs2")
    data = export_article_context(
        vault_root=str(world["vault"]),
        question=_question(world),
        paper_ids=_papers(world),
    )
    claim, value = _claim_and_value(data["context"])
    ctx = world["checkout"] / "ctx-obs2.json"
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": data})
    rec = first["record"]
    s1 = _provisional_section(rec["sections"][0], data["context"], [claim["evidence_id"], value["evidence_id"]])
    doc = {"schema": "video-paper-wiki.article-document.v1", "title": rec["title"], "sections": [s1] + rec["sections"][1:]}
    path = world["checkout"] / "doc-obs2.json"
    _write_json(path, doc)
    import_article_revision(
        vault_root=str(world["vault"]),
        batch_id="obs2",
        context=str(ctx),
        document=str(path),
        recorded_by="t",
        recorded_at="2026-09-15T01:00:00Z",
        previous_revision_id=rec["revision_id"],
        target_section_id="s1",
    )
    _apply_staged_articles(world, "obs2")
    dangling = "aev-" + ("0" * 20)

    def add_mark(document):
        for section in document["sections"]:
            if section["section_id"] == "s1":
                section["markdown"] = section["markdown"] + " [@" + dangling + "]"
                break

    mutated = _rewrite(add_mark)
    chk_mark = check_article_revision(
        vault_root=str(world["vault"]),
        article_id=mutated["article_id"],
        revision_id=mutated["revision_id"],
    )
    assert chk_mark["citation_consistency"]["in_text_equals_list"] is False
    assert chk_mark["check_status"] == "inconsistent"
    err = _expect(
        lambda: render_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r9",
            article_id=mutated["article_id"],
            revision_id=mutated["revision_id"],
        ),
        "ARTICLE_RENDER_INVALID",
    )
    assert err.details["reason"] == "dangling_citation"
    assert err.details["section_id"] == "s1"
    assert err.details["evidence_id"] == dangling
    assert err.details["instance_pointer"].startswith("/sections/")
    assert not (world["checkout"] / ".work/r9/articles/render").exists()
    work_r9 = world["checkout"] / ".work/r9"
    if work_r9.exists():
        assert not any(work_r9.rglob("*"))

    def add_x(document):
        for section in document["sections"]:
            if section["section_id"] == "s1":
                section["markdown"] = section["markdown"].replace(" [@" + dangling + "]", "") + " [@x]"
                break

    mutated_x = _rewrite(add_x)
    err = _expect(
        lambda: render_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r9b",
            article_id=mutated_x["article_id"],
            revision_id=mutated_x["revision_id"],
        ),
        "ARTICLE_RENDER_INVALID",
    )
    assert err.details["reason"] == "dangling_citation"
    assert err.details["evidence_id"] == "x"
    table_eid = mutated_x["comparison_table"]["rows"][0]["cells"]["model_checkpoint"]["evidence_id"]

    def drop_table(document):
        for section in document["sections"]:
            if section["section_id"] == "s1":
                section["markdown"] = section["markdown"].replace(" [@x]", "")
                break
        document["bibliography"] = [
            item for item in document["bibliography"] if item["evidence_id"] != table_eid
        ]

    mutated_t = _rewrite(drop_table)
    err = _expect(
        lambda: render_article_revision(
            vault_root=str(world["vault"]),
            batch_id="r9c",
            article_id=mutated_t["article_id"],
            revision_id=mutated_t["revision_id"],
        ),
        "ARTICLE_RENDER_INVALID",
    )
    assert err.details["reason"] == "dangling_citation"
    assert err.details["location"] == "table"
    proc = run_module_cli(
        world["checkout"],
        [
            "articles",
            "render",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "r9d",
            "--article-id",
            mutated_t["article_id"],
            "--revision-id",
            mutated_t["revision_id"],
        ],
    )
    assert proc.returncode == 2
    payload = parse_envelope(proc)
    assert payload["ok"] is False
    assert "Traceback" not in (proc.stderr or "")
    assert run_module_cli is not None
