from __future__ import annotations

from pathlib import Path

from tests.research.test_light_compare import _comparison_document
from tests.research.test_light_index import SHA_A
from tests.research.test_light_knowledge import (
    PAPER_A,
    PAPER_B,
    _knowledge_document,
    _workspace,
)
from video_paper_wiki_research.light_compare import LIGHT_COMPARISON_INVALID, export_comparison_context, import_comparison
from video_paper_wiki_research.light_index import INDEX_STALE, build_index
from video_paper_wiki_research.light_knowledge import LIGHT_KNOWLEDGE_INVALID, export_knowledge_context, import_knowledge


def test_knowledge_citations_must_belong_to_selected_live_paper(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported_a = export_knowledge_context(workspace, paper_id=PAPER_A)
    exported_b = export_knowledge_context(workspace, paper_id=PAPER_B)
    chunk_a = exported_a["context"]["evidence"][0]["chunk_id"]
    chunk_b = exported_b["context"]["evidence"][0]["chunk_id"]
    mixed = _knowledge_document(PAPER_A, chunk_b)
    refused = import_knowledge(workspace, exported_a, mixed)
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_KNOWLEDGE_INVALID
    assert not any((workspace / ".light-knowledge" / "records").glob("*")) if (workspace / ".light-knowledge" / "records").exists() else True
    valid = import_knowledge(workspace, exported_a, _knowledge_document(PAPER_A, chunk_a))
    assert valid["ok"] is True
    page = Path(valid["page_path"]).read_text(encoding="utf-8")
    assert chunk_a not in page or "[@" not in page
    assert "source.md#page-1" in page


def test_comparison_cell_citations_are_paper_owned(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture uniquealpha"],
        pages_b=["transformer architecture uniquebeta"],
    )
    exported = export_comparison_context(workspace, query="transformer", paper_ids=[PAPER_A, PAPER_B])
    by_paper = {item["paper_id"]: item["chunk_id"] for item in exported["context"]["evidence"]}
    mixed = _comparison_document([PAPER_A, PAPER_B], by_paper)
    mixed["rows"][0]["cells"][0]["citations"] = [by_paper[PAPER_B]]
    output = workspace / "reports" / "mixed.md"
    refused = import_comparison(workspace, exported, mixed, output=output)
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_COMPARISON_INVALID
    assert not output.exists()
    ok = import_comparison(
        workspace,
        exported,
        _comparison_document([PAPER_A, PAPER_B], by_paper),
        output=output,
    )
    assert ok["ok"] is True
    for item in ok["citations"]:
        source = workspace / item["markdown_path"]
        markdown = source.read_text(encoding="utf-8")
        stored = None
        for chunk in exported["context"]["evidence"]:
            if chunk["chunk_id"] == item["chunk_id"]:
                stored = chunk
                break
        assert stored is not None
        assert markdown[stored["text_start"] : stored["text_end"]] == stored["text"]
        assert item["paper_id"] in {PAPER_A, PAPER_B}


def test_stale_source_refuses_both_imports_without_writing(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture uniquealpha"],
        pages_b=["transformer architecture uniquebeta"],
    )
    knowledge = export_knowledge_context(workspace, paper_id=PAPER_A)
    comparison = export_comparison_context(workspace, query="transformer", paper_ids=[PAPER_A, PAPER_B])
    source = workspace / "papers" / SHA_A / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("transformer", "rewritten"), encoding="utf-8")
    build_index(workspace)
    knowledge_out = import_knowledge(
        workspace,
        knowledge,
        _knowledge_document(PAPER_A, knowledge["context"]["evidence"][0]["chunk_id"]),
    )
    assert knowledge_out["ok"] is False
    assert knowledge_out["status"] in {INDEX_STALE, LIGHT_KNOWLEDGE_INVALID}
    by_paper = {item["paper_id"]: item["chunk_id"] for item in comparison["context"]["evidence"]}
    compare_out = workspace / "reports" / "after-stale.md"
    comparison_result = import_comparison(
        workspace,
        comparison,
        _comparison_document([PAPER_A, PAPER_B], by_paper),
        output=compare_out,
    )
    assert comparison_result["ok"] is False
    assert comparison_result["status"] in {INDEX_STALE, LIGHT_COMPARISON_INVALID}
    assert not compare_out.exists()
    assert not (workspace / ".light-knowledge" / "records").exists()
