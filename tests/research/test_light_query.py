from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import (
    LIGHT_CONTEXT_INVALID,
    LIGHT_SELECTION_INVALID,
    SOURCE_INVALID,
    WORKSPACE_INVALID,
    export_context,
    import_document,
    render_document,
    validate_live_context,
)
from video_paper_wiki_research.light_index import INDEX_STALE, NO_RESULTS, OK, build_index, search
from video_paper_wiki_research.light_library_state import try_workspace_lock
from video_paper_wiki_research.light_query import (
    FUSION,
    LIGHT_WORKSPACE_BUSY,
    PLAN_SCHEMA,
    QUERY_REWRITE_INVALID,
    REWRITE_SCHEMA,
    export_rewritten_context,
    query_plan_shape_error,
)

PAPER_A = "sha256:" + SHA_A
PAPER_B = "sha256:" + SHA_B


def _rewrite(query: str, rewritten: str) -> dict[str, str]:
    return {
        "schema": REWRITE_SCHEMA,
        "original_query": query,
        "rewritten_query": rewritten,
        "language": "en",
    }


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / ".work" / "ws"
    workspace.mkdir(parents=True)
    _write_paper(workspace, SHA_A, "Alpha paper", ["Synthetic quasar method evidence 类星体方法。"])
    _write_paper(workspace, SHA_B, "Beta paper", ["Nebula writing token evidence 星云写作。"])
    build_index(workspace)
    return workspace


def _rrf(*ranks: int) -> float:
    return sum(1.0 / (FUSION["rank_constant"] + rank) for rank in ranks)


def test_rewrite_only_original_only_both_and_no_hits(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    rewrite_only = export_rewritten_context(
        workspace,
        kind="qa",
        query="时间注意力机制问题",
        rewrite=_rewrite("时间注意力机制问题", "quasar method"),
    )
    assert rewrite_only["ok"] is True
    assert rewrite_only["status"] == OK
    assert rewrite_only["query"] == "时间注意力机制问题"
    assert rewrite_only["schema"] == "video-paper-wiki.light-context.v1"
    plan = rewrite_only["query_plan"]
    assert plan["schema"] == PLAN_SCHEMA
    assert [route["name"] for route in plan["routes"]] == ["original", "rewrite"]
    assert plan["routes"][0]["status"] == NO_RESULTS
    assert plan["routes"][0]["candidates"] == []
    assert plan["routes"][1]["status"] == OK
    assert 1 <= len(plan["routes"][1]["candidates"]) <= 24
    assert [row["chunk_id"] for row in plan["fused"]] == [item["chunk_id"] for item in rewrite_only["evidence"]]
    assert [row["score"] for row in plan["fused"]] == [item["score"] for item in rewrite_only["evidence"]]
    assert plan["fused"][0]["route_names"] == ["rewrite"]
    assert plan["fused"][0]["score"] == _rrf(plan["routes"][1]["candidates"][0]["rank"])
    assert query_plan_shape_error(plan) is None
    live = validate_live_context(workspace, rewrite_only)
    assert live["ok"] is True

    original_only = export_rewritten_context(
        workspace,
        kind="qa",
        query="类星体方法",
        rewrite=_rewrite("类星体方法", "AbsentLatinTokenXYZ"),
    )
    assert original_only["ok"] is True
    plan = original_only["query_plan"]
    assert plan["routes"][0]["status"] == OK
    assert plan["routes"][1]["status"] == NO_RESULTS
    assert plan["fused"][0]["route_names"] == ["original"]
    assert validate_live_context(workspace, original_only)["ok"] is True

    both = export_rewritten_context(
        workspace,
        kind="writing",
        query="quasar",
        rewrite=_rewrite("quasar", "method"),
        requirements="one paragraph",
    )
    assert both["ok"] is True
    assert both["kind"] == "writing"
    plan = both["query_plan"]
    assert plan["routes"][0]["status"] == OK
    assert plan["routes"][1]["status"] == OK
    first = plan["fused"][0]
    assert first["route_names"] == ["original", "rewrite"]
    orig_rank = next(item["rank"] for item in plan["routes"][0]["candidates"] if item["chunk_id"] == first["chunk_id"])
    rew_rank = next(item["rank"] for item in plan["routes"][1]["candidates"] if item["chunk_id"] == first["chunk_id"])
    assert first["score"] == _rrf(orig_rank, rew_rank)
    assert both["evidence"][0]["text"] == "Synthetic quasar method evidence 类星体方法。"

    empty = export_rewritten_context(
        workspace,
        kind="qa",
        query="完全不存在的中文检索词组",
        rewrite=_rewrite("完全不存在的中文检索词组", "AbsentLatinTokenXYZ"),
    )
    assert empty["ok"] is False
    assert empty["status"] == NO_RESULTS
    assert empty["evidence"] == []
    assert empty["query_plan"]["fused"] == []
    assert [route["status"] for route in empty["query_plan"]["routes"]] == [NO_RESULTS, NO_RESULTS]
    assert query_plan_shape_error(empty["query_plan"]) is None
    assert validate_live_context(workspace, empty)["status"] == LIGHT_CONTEXT_INVALID


def test_equal_query_deduplicates_to_original_route(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    query = "quasar method"
    exported = export_rewritten_context(workspace, kind="qa", query=query, rewrite=_rewrite(query, query))
    assert exported["ok"] is True
    plan = exported["query_plan"]
    assert [route["name"] for route in plan["routes"]] == ["original"]
    assert plan["routes"][0]["query"] == query
    assert all(row["route_names"] == ["original"] for row in plan["fused"])
    single = search(workspace, query, top_k=24)
    assert [item["chunk_id"] for item in single["evidence"][:8]] == [item["chunk_id"] for item in exported["evidence"]]
    assert query_plan_shape_error(plan) is None


def test_selection_happens_before_search(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    selected = export_rewritten_context(
        workspace,
        kind="qa",
        query="quasar",
        rewrite=_rewrite("quasar", "nebula writing"),
        paper_ids=[PAPER_B],
    )
    assert selected["ok"] is True
    assert selected["selected_paper_ids"] == [PAPER_B]
    assert selected["query_plan"]["selected_paper_ids"] == [PAPER_B]
    assert [item["paper_id"] for item in selected["query_plan"]["paper_snapshots"]] == [PAPER_B]
    assert {item["paper_id"] for item in selected["evidence"]} == {PAPER_B}
    assert selected["query_plan"]["routes"][0]["status"] == NO_RESULTS
    assert selected["query_plan"]["routes"][1]["status"] == OK
    unknown = export_rewritten_context(
        workspace,
        kind="qa",
        query="quasar",
        rewrite=_rewrite("quasar", "nebula writing"),
        paper_ids=[PAPER_A, "sha256:" + "f" * 64],
    )
    assert unknown["ok"] is False
    assert unknown["status"] == LIGHT_SELECTION_INVALID
    assert "query_plan" not in unknown
    duplicate = export_rewritten_context(
        workspace,
        kind="qa",
        query="quasar",
        rewrite=_rewrite("quasar", "nebula writing"),
        paper_ids=[PAPER_B, PAPER_B],
    )
    assert duplicate["ok"] is False
    assert duplicate["status"] == LIGHT_SELECTION_INVALID
    assert "query_plan" not in duplicate


def test_rrf_order_limits_and_identity(tmp_path: Path) -> None:
    workspace = tmp_path / ".work" / "many"
    workspace.mkdir(parents=True)
    pages = [f"sharedterm page{index:02d} unique{index:02d} " + ("block " * 40) for index in range(30)]
    _write_paper(workspace, SHA_A, "Long paper", pages)
    build_index(workspace)
    exported = export_rewritten_context(
        workspace,
        kind="qa",
        query="sharedterm",
        rewrite=_rewrite("sharedterm", "unique00 unique29"),
    )
    assert exported["ok"] is True
    plan = exported["query_plan"]
    assert plan["fusion"] == FUSION
    assert len(plan["routes"][0]["candidates"]) <= 24
    assert len(plan["routes"][1]["candidates"]) <= 24
    assert len(plan["fused"]) <= 8
    assert len(exported["evidence"]) == len(plan["fused"])
    ordered = sorted(plan["fused"], key=lambda item: (-item["score"], item["chunk_id"]))
    assert [item["chunk_id"] for item in ordered] == [item["chunk_id"] for item in plan["fused"]]
    source = (workspace / "papers" / SHA_A / "source.md").read_text(encoding="utf-8")
    for item in exported["evidence"]:
        assert item["text"] == source[item["text_start"] : item["text_end"]]
        assert item["text_sha256"] == hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
        assert item["score"] == next(row["score"] for row in plan["fused"] if row["chunk_id"] == item["chunk_id"])


def test_malformed_rewrite_is_query_rewrite_invalid(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    query = "quasar method"
    cases = [
        {"schema": REWRITE_SCHEMA, "original_query": query, "rewritten_query": "method", "language": "zh"},
        {"schema": REWRITE_SCHEMA, "original_query": "other", "rewritten_query": "method", "language": "en"},
        {"schema": REWRITE_SCHEMA, "original_query": query, "rewritten_query": "123456", "language": "en"},
        {"schema": REWRITE_SCHEMA, "original_query": query, "rewritten_query": "method\nterms", "language": "en"},
        {"schema": REWRITE_SCHEMA, "original_query": query, "rewritten_query": "", "language": "en"},
        {"schema": REWRITE_SCHEMA, "original_query": query, "rewritten_query": "method", "language": "en", "extra": True},
        {"schema": "other", "original_query": query, "rewritten_query": "method", "language": "en"},
        "not-an-object",
    ]
    for rewrite in cases:
        result = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
        assert result["ok"] is False
        assert result["status"] == QUERY_REWRITE_INVALID
        assert "query_plan" not in result
    too_long = export_rewritten_context(workspace, kind="qa", query="q" * 2001, rewrite=_rewrite("q" * 2001, "method"))
    assert too_long["status"] == QUERY_REWRITE_INVALID
    blank = export_rewritten_context(workspace, kind="qa", query="   ", rewrite=_rewrite("   ", "method"))
    assert blank["status"] == QUERY_REWRITE_INVALID
    with pytest.raises(ResearchError) as exc:
        export_rewritten_context(workspace, kind="draft", query=query, rewrite=_rewrite(query, "method"))
    assert exc.value.code == LIGHT_CONTEXT_INVALID


def test_source_change_between_routes_is_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    source = workspace / "papers" / SHA_A / "source.md"
    original = source.read_bytes()
    import video_paper_wiki_research.light_index as light_index

    real = light_index._rank_on_snapshot
    calls = {"n": 0}

    def _mutate_after_first(*args, **kwargs):
        result = real(*args, **kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            source.write_text(source.read_text(encoding="utf-8").replace("quasar", "changed"), encoding="utf-8")
        return result

    monkeypatch.setattr(light_index, "_rank_on_snapshot", _mutate_after_first)
    result = export_rewritten_context(
        workspace,
        kind="qa",
        query="类星体问题",
        rewrite=_rewrite("类星体问题", "quasar method"),
    )
    source.write_bytes(original)
    assert result["ok"] is False
    assert result["status"] == INDEX_STALE
    assert "query_plan" not in result
    assert calls["n"] >= 1


def test_source_change_between_export_and_import(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_rewritten_context(
        workspace,
        kind="qa",
        query="类星体问题",
        rewrite=_rewrite("类星体问题", "quasar method"),
    )
    assert context["ok"] is True
    output = tmp_path / "keep.md"
    output.write_text("user-owned\n", encoding="utf-8")
    before = output.read_bytes()
    source = workspace / "papers" / SHA_A / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("quasar", "changed"), encoding="utf-8")
    live = validate_live_context(workspace, context)
    assert live["status"] == INDEX_STALE
    imported = import_document(
        workspace,
        context,
        {"text": f"cite [@{context['evidence'][0]['chunk_id']}]", "citations": [{"chunk_id": context["evidence"][0]["chunk_id"]}]},
        output=output,
        overwrite=True,
    )
    assert imported["status"] == INDEX_STALE
    assert output.read_bytes() == before


def test_import_rejects_malformed_trace_and_foreign_citations(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_rewritten_context(
        workspace,
        kind="qa",
        query="类星体问题",
        rewrite=_rewrite("类星体问题", "quasar method"),
    )
    keep = tmp_path / "owned.md"
    keep.write_text("preserve-me\n", encoding="utf-8")
    before = keep.read_bytes()
    chunk = context["evidence"][0]["chunk_id"]

    extra = json.loads(json.dumps(context))
    extra["query_plan"]["extra"] = True
    assert validate_live_context(workspace, extra)["status"] == LIGHT_CONTEXT_INVALID

    hashed = json.loads(json.dumps(context))
    hashed["query_plan"]["rewrite_sha256"] = "a" * 64
    hashed["query_plan"]["plan_sha256"] = "b" * 64
    assert validate_live_context(workspace, hashed)["status"] == LIGHT_CONTEXT_INVALID

    bool_rank = json.loads(json.dumps(context))
    bool_rank["query_plan"]["routes"][1]["candidates"][0]["rank"] = True
    assert validate_live_context(workspace, bool_rank)["status"] == LIGHT_CONTEXT_INVALID

    score = json.loads(json.dumps(context))
    score["evidence"][0]["score"] = float(score["evidence"][0]["score"]) + 1.0
    assert validate_live_context(workspace, score)["status"] == LIGHT_CONTEXT_INVALID

    legacy = export_context(workspace, kind="qa", query="quasar method")
    assert "query_plan" not in legacy
    assert validate_live_context(workspace, legacy)["ok"] is True
    legacy_score = json.loads(json.dumps(legacy))
    legacy_score["evidence"][0]["score"] = float(legacy_score["evidence"][0]["score"]) + 1.0
    assert validate_live_context(workspace, legacy_score)["ok"] is True

    imported = import_document(
        workspace,
        extra,
        {"text": f"cite [@{chunk}]", "citations": [{"chunk_id": chunk}]},
        output=tmp_path / "forged-plan.md",
    )
    assert imported["status"] == LIGHT_CONTEXT_INVALID
    assert not (tmp_path / "forged-plan.md").exists()

    foreign = import_document(
        workspace,
        context,
        {"text": "Invented [@chk-foreign]", "citations": [{"chunk_id": "chk-foreign"}]},
        output=tmp_path / "foreign.md",
    )
    assert foreign["ok"] is False
    assert foreign["status"] == "INVALID_CITATION"
    assert not (tmp_path / "foreign.md").exists()
    assert keep.read_bytes() == before

    ok = import_document(
        workspace,
        context,
        {"text": f"Synthetic method [@{chunk}].", "citations": [{"chunk_id": chunk}]},
        output=tmp_path / "ok.md",
    )
    assert ok["ok"] is True
    assert (tmp_path / "ok.md").is_file()


def test_forged_index_cannot_succeed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    index_path = workspace / ".light-index" / "index.v1.json"
    stored = json.loads(index_path.read_text(encoding="utf-8"))
    stored["chunks"][0]["text"] = "forged lexical content"
    stored["chunks"][0]["text_sha256"] = hashlib.sha256(b"forged lexical content").hexdigest()
    index_path.write_bytes(json.dumps(stored, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
    result = export_rewritten_context(
        workspace,
        kind="qa",
        query="类星体问题",
        rewrite=_rewrite("类星体问题", "quasar method"),
    )
    assert result["ok"] is False
    assert result["status"] == INDEX_STALE
    assert "query_plan" not in result
    assert result["evidence"] == []


def test_query_plan_public_shape_example(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_rewritten_context(
        workspace,
        kind="qa",
        query="类星体问题",
        rewrite=_rewrite("类星体问题", "quasar method"),
    )
    plan = context["query_plan"]
    assert set(plan) == {
        "schema",
        "original_query",
        "rewrite",
        "rewrite_sha256",
        "workspace_id",
        "index_id",
        "selected_paper_ids",
        "paper_snapshots",
        "fusion",
        "routes",
        "fused",
        "plan_sha256",
    }
    assert set(plan["rewrite"]) == {"schema", "original_query", "rewritten_query", "language"}
    assert set(plan["fusion"]) == {"algorithm", "rank_constant", "candidate_k", "top_k"}
    assert set(plan["routes"][0]) == {"name", "query", "status", "index_id", "candidates"}
    assert set(plan["fused"][0]) == {"chunk_id", "score", "route_names"}
    assert set(plan["paper_snapshots"][0]) == {"paper_id", "markdown_sha256", "source_json_sha256"}
    assert context["workspace_root"] == str(workspace.resolve())
    roundtrip = json.loads(json.dumps(context, ensure_ascii=False, allow_nan=False))
    assert validate_live_context(workspace, roundtrip)["ok"] is True


def _answer(context: dict) -> dict:
    chunk = context["evidence"][0]["chunk_id"]
    return {"text": f"Synthetic method [@{chunk}].", "citations": [{"chunk_id": chunk}]}


def test_r2_closed_repairs_on_rewritten_export(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    query = "类星体问题"
    rewrite = _rewrite(query, "quasar method")
    context = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    assert context["ok"] is True
    assert context["query"] == query

    forged_status = json.loads(json.dumps(context))
    forged_status["query_plan"]["routes"][0]["status"] = ["OK"]
    assert query_plan_shape_error(forged_status["query_plan"]) is not None
    assert validate_live_context(workspace, forged_status)["status"] == LIGHT_CONTEXT_INVALID
    list_out = tmp_path / "list-status.md"
    assert render_document(workspace, forged_status, _answer(context), output=list_out)["status"] == LIGHT_CONTEXT_INVALID
    imported_status = import_document(workspace, forged_status, _answer(context), output=list_out)
    assert imported_status["status"] == LIGHT_CONTEXT_INVALID
    assert not list_out.exists()

    forged_name = json.loads(json.dumps(context))
    forged_name["query_plan"]["routes"][0]["name"] = {"original": True}
    assert validate_live_context(workspace, forged_name)["status"] == LIGHT_CONTEXT_INVALID

    forged_score = json.loads(json.dumps(context))
    forged_score["query_plan"]["routes"][1]["candidates"][0]["score"] = 10**400
    assert query_plan_shape_error(forged_score["query_plan"]) is not None
    assert validate_live_context(workspace, forged_score)["status"] == LIGHT_CONTEXT_INVALID
    huge_out = tmp_path / "huge-score.md"
    assert import_document(workspace, forged_score, _answer(context), output=huge_out)["status"] == LIGHT_CONTEXT_INVALID
    assert not huge_out.exists()

    bool_score = json.loads(json.dumps(context))
    bool_score["query_plan"]["routes"][1]["candidates"][0]["score"] = True
    assert validate_live_context(workspace, bool_score)["status"] == LIGHT_CONTEXT_INVALID

    surrogate_query = export_rewritten_context(workspace, kind="qa", query="\ud800", rewrite=_rewrite("\ud800", "quasar"))
    assert surrogate_query["ok"] is False
    assert surrogate_query["status"] == QUERY_REWRITE_INVALID
    assert "query_plan" not in surrogate_query
    surrogate_rewrite = export_rewritten_context(
        workspace,
        kind="qa",
        query=query,
        rewrite=_rewrite(query, "quasar\ud800"),
    )
    assert surrogate_rewrite["status"] == QUERY_REWRITE_INVALID
    assert "query_plan" not in surrogate_rewrite
    chinese = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    assert chinese["ok"] is True
    assert chinese["query"] == query
    forged_surrogate = json.loads(json.dumps(context))
    forged_surrogate["query_plan"]["original_query"] = query + "\ud800"
    assert validate_live_context(workspace, forged_surrogate)["status"] == LIGHT_CONTEXT_INVALID

    held = try_workspace_lock(workspace)
    assert held is not None
    try:
        busy = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    finally:
        held.release()
    assert busy["ok"] is False
    assert busy["status"] == LIGHT_WORKSPACE_BUSY
    assert "query_plan" not in busy
    released = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    assert released["ok"] is True

    outside = tmp_path / "outside-ws"
    outside.mkdir()
    _write_paper(outside, SHA_A, "Alpha paper", ["Synthetic quasar method evidence 类星体方法。"])
    build_index(outside)
    with pytest.raises(ResearchError) as exc:
        export_rewritten_context(outside, kind="qa", query=query, rewrite=rewrite)
    assert exc.value.code == WORKSPACE_INVALID
    legacy = export_context(outside, kind="qa", query="quasar method")
    assert legacy["ok"] is True
    assert "query_plan" not in legacy
    assert validate_live_context(outside, legacy)["ok"] is True
    assert export_context(outside, kind="qa", query="quasar", paper_ids=[PAPER_A, PAPER_A])["selected_paper_ids"] == [PAPER_A]

    real_parent = tmp_path / ".work" / "real-parent"
    aliased_ws = _workspace(tmp_path / "alias-source")
    real_parent.mkdir(parents=True)
    real_ws = real_parent / "ws"
    aliased_ws.rename(real_ws)
    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(real_parent)
    aliased = alias_parent / "ws"
    with pytest.raises(ResearchError) as exc:
        export_rewritten_context(aliased, kind="qa", query=query, rewrite=rewrite)
    assert exc.value.code == WORKSPACE_INVALID
    traced = export_rewritten_context(real_ws, kind="qa", query=query, rewrite=rewrite)
    assert traced["ok"] is True
    keep = tmp_path / "keep-parent.md"
    keep.write_text("preserve-parent\n", encoding="utf-8")
    before = keep.read_bytes()
    with pytest.raises(ResearchError) as exc:
        validate_live_context(aliased, traced)
    assert exc.value.code == WORKSPACE_INVALID
    with pytest.raises(ResearchError) as exc:
        import_document(aliased, traced, _answer(traced), output=keep)
    assert exc.value.code == WORKSPACE_INVALID
    assert keep.read_bytes() == before

    md = workspace / "papers" / SHA_A / "source.md"
    md_copy = tmp_path / "hard-source.md"
    md_copy.write_bytes(md.read_bytes())
    original_md = md.read_bytes()
    md.unlink()
    os.link(md_copy, md)
    hard_md = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    assert hard_md["ok"] is False
    assert hard_md["status"] == SOURCE_INVALID
    assert "query_plan" not in hard_md
    md.unlink()
    md.write_bytes(original_md)
    assert export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)["ok"] is True

    meta = workspace / "papers" / SHA_A / "source.json"
    meta_copy = tmp_path / "hard-source.json"
    meta_copy.write_bytes(meta.read_bytes())
    original_meta = meta.read_bytes()
    meta.unlink()
    os.link(meta_copy, meta)
    hard_json = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    assert hard_json["status"] == SOURCE_INVALID
    assert "query_plan" not in hard_json
    live_hard = validate_live_context(workspace, context)
    assert live_hard["status"] == SOURCE_INVALID
    hard_out = tmp_path / "hard-import.md"
    hard_out.write_text("owned-hard\n", encoding="utf-8")
    hard_before = hard_out.read_bytes()
    imported_hard = import_document(workspace, context, _answer(context), output=hard_out)
    assert imported_hard["status"] == SOURCE_INVALID
    assert hard_out.read_bytes() == hard_before
    meta.unlink()
    meta.write_bytes(original_meta)

    empty_link = tmp_path / ".work" / "papers-link"
    empty_link.mkdir(parents=True)
    empty_papers = tmp_path / "empty-papers"
    empty_papers.mkdir()
    (empty_link / "papers").symlink_to(empty_papers)
    built = build_index(empty_link)
    assert built["ok"] is True
    assert built["paper_count"] == 0
    linked_root = export_rewritten_context(
        empty_link,
        kind="qa",
        query=query,
        rewrite=rewrite,
    )
    assert linked_root["ok"] is False
    assert linked_root["status"] == SOURCE_INVALID
    assert "query_plan" not in linked_root

    digest_link = workspace / "papers" / ("c" * 64)
    digest_link.symlink_to(tmp_path / "missing-paper-dir")
    linked_dir = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    assert linked_dir["status"] == SOURCE_INVALID
    assert "query_plan" not in linked_dir
    digest_link.unlink()

    empty_ok = tmp_path / ".work" / "empty-regular"
    empty_ok.mkdir(parents=True)
    (empty_ok / "papers").mkdir()
    build_index(empty_ok)
    no_hits = export_rewritten_context(
        empty_ok,
        kind="qa",
        query="完全不存在的中文检索词组",
        rewrite=_rewrite("完全不存在的中文检索词组", "AbsentLatinTokenXYZ"),
    )
    assert no_hits["ok"] is False
    assert no_hits["status"] == NO_RESULTS
    assert no_hits["query_plan"]["fused"] == []
    assert no_hits["evidence"] == []


def test_r3_huge_evidence_score_closes_before_legacy_isfinite(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    query = "类星体问题"
    rewrite = _rewrite(query, "quasar method")
    context = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    assert context["ok"] is True
    assert [row["score"] for row in context["evidence"]] == [row["score"] for row in context["query_plan"]["fused"]]
    assert validate_live_context(workspace, context)["ok"] is True
    keep = tmp_path / "owned-evidence-score.md"
    keep.write_text("preserve-evidence-score\n", encoding="utf-8")
    before = keep.read_bytes()
    document = _answer(context)

    huge = json.loads(json.dumps(context))
    huge["evidence"][0]["score"] = 10**400
    validated = validate_live_context(workspace, huge)
    assert validated["ok"] is False
    assert validated["status"] == LIGHT_CONTEXT_INVALID
    assert "exception" not in validated
    rendered = render_document(workspace, huge, document, output=keep)
    assert rendered["ok"] is False
    assert rendered["status"] == LIGHT_CONTEXT_INVALID
    imported = import_document(workspace, huge, document, output=keep)
    assert imported["ok"] is False
    assert imported["status"] == LIGHT_CONTEXT_INVALID
    assert keep.read_bytes() == before

    boolean = json.loads(json.dumps(context))
    boolean["evidence"][0]["score"] = True
    assert validate_live_context(workspace, boolean)["status"] == LIGHT_CONTEXT_INVALID
    nan = json.loads(json.dumps(context))
    nan["evidence"][0]["score"] = float("nan")
    assert validate_live_context(workspace, nan)["status"] == LIGHT_CONTEXT_INVALID
    inf = json.loads(json.dumps(context))
    inf["evidence"][0]["score"] = float("inf")
    assert validate_live_context(workspace, inf)["status"] == LIGHT_CONTEXT_INVALID
    assert keep.read_bytes() == before

    legacy = export_context(workspace, kind="qa", query="quasar method")
    assert "query_plan" not in legacy
    assert validate_live_context(workspace, legacy)["ok"] is True
    legacy_huge = json.loads(json.dumps(legacy))
    legacy_huge["evidence"][0]["score"] = 10**400
    with pytest.raises(OverflowError, match="int too large to convert to float"):
        validate_live_context(workspace, legacy_huge)
    assert keep.read_bytes() == before


def test_r3_symlink_dotdot_is_refused_before_normpath(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    query = "类星体问题"
    rewrite = _rewrite(query, "quasar method")
    real_root = tmp_path / "real"
    workspace = _workspace(real_root)
    other_subdir = tmp_path / "other" / "subdir"
    other_subdir.mkdir(parents=True)
    (tmp_path / "other" / "ws").mkdir()
    link = real_root / ".work" / "link"
    link.symlink_to(other_subdir)
    given = real_root / ".work" / "link" / ".." / "ws"
    assert ".." in given.parts
    assert Path(os.path.normpath(given)) == workspace
    assert given.resolve() == (tmp_path / "other" / "ws").resolve()

    context = export_rewritten_context(workspace, kind="qa", query=query, rewrite=rewrite)
    assert context["ok"] is True
    document = _answer(context)
    keep = tmp_path / "owned-dotdot.md"
    keep.write_text("preserve-dotdot\n", encoding="utf-8")
    before = keep.read_bytes()

    with pytest.raises(ResearchError) as exported:
        export_rewritten_context(given, kind="qa", query=query, rewrite=rewrite)
    assert exported.value.code == WORKSPACE_INVALID
    with pytest.raises(ResearchError) as validated:
        validate_live_context(given, context)
    assert validated.value.code == WORKSPACE_INVALID
    with pytest.raises(ResearchError) as rendered:
        render_document(given, context, document, output=keep)
    assert rendered.value.code == WORKSPACE_INVALID
    with pytest.raises(ResearchError) as imported:
        import_document(given, context, document, output=keep)
    assert imported.value.code == WORKSPACE_INVALID
    assert keep.read_bytes() == before

    relative = Path(".work") / "ws"
    monkeypatch.chdir(real_root)
    relative_export = export_rewritten_context(relative, kind="qa", query=query, rewrite=rewrite)
    assert relative_export["ok"] is True
    assert validate_live_context(relative, relative_export)["ok"] is True
    relative_out = tmp_path / "relative-ok.md"
    relative_import = import_document(relative, relative_export, _answer(relative_export), output=relative_out)
    assert relative_import["ok"] is True
    assert relative_out.is_file()

    try:
        legacy = export_context(given, kind="qa", query="quasar method")
    except ResearchError as exc:
        assert exc.code != WORKSPACE_INVALID or "parent-traversal" not in exc.message
    else:
        assert "query_plan" not in legacy
    assert keep.read_bytes() == before
