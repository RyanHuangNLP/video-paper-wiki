from __future__ import annotations

from pathlib import Path

import pytest

from tests.research.test_light_index import SHA_A
from tests.research.test_light_knowledge import PAPER_A, PAPER_B, _workspace
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_compare import (
    COMPARISON_CONTEXT_SCHEMA,
    COMPARISON_DOCUMENT_SCHEMA,
    DEFAULT_DIMENSIONS,
    LIGHT_COMPARISON_INVALID,
    export_comparison_context,
    import_comparison,
)
from video_paper_wiki_research.light_context import LIGHT_OUTPUT_CONFLICT
from video_paper_wiki_research.light_index import LIGHT_SELECTION_INVALID, OK
from video_paper_wiki_research.light_knowledge import WORKSPACE_INVALID
from video_paper_wiki_research.light_qa import INSUFFICIENT_EVIDENCE


def _cell(paper_id: str, chunk_id: str | None, *, conditions: str = "synthetic fixture") -> dict:
    if chunk_id is None:
        return {
            "citations": [],
            "conditions": "unknown",
            "paper_id": paper_id,
            "status": "unknown",
            "text": "证据不足",
        }
    return {
        "citations": [chunk_id],
        "conditions": conditions,
        "paper_id": paper_id,
        "status": "provisional",
        "text": "Observed method text.",
    }


def _comparison_document(paper_ids: list[str], chunks: dict[str, str | None], *, dimensions: list[str] | None = None) -> dict:
    labels = list(dimensions or DEFAULT_DIMENSIONS)
    rows = []
    for label in labels:
        cells = [_cell(paper_id, chunks.get(paper_id)) for paper_id in paper_ids]
        comparable = all(
            cell["status"] == "provisional" and cell["citations"] and cell["conditions"] != "unknown" for cell in cells
        )
        rows.append(
            {
                "cells": cells,
                "comparability": "comparable" if comparable else "unknown",
                "dimension": label,
                "reason": "Fixture comparison under matching synthetic conditions.",
            }
        )
    return {"rows": rows, "schema": COMPARISON_DOCUMENT_SCHEMA}


def test_balanced_export_import_table_and_default_output(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture training experiment limitation uniquealpha"],
        pages_b=["transformer architecture training experiment limitation uniquebeta"],
    )
    exported = export_comparison_context(
        workspace,
        query="transformer",
        paper_ids=[PAPER_A, PAPER_B],
    )
    assert exported["ok"] is True
    assert exported["schema"] == COMPARISON_CONTEXT_SCHEMA
    assert exported["paper_ids"] == [PAPER_A, PAPER_B]
    assert exported["dimensions"] == list(DEFAULT_DIMENSIONS)
    assert exported["context"]["kind"] == "writing"
    assert [item["paper_id"] for item in exported["coverage"]] == [PAPER_A, PAPER_B]
    assert all(item["exported_chunks"] >= 1 for item in exported["coverage"])
    by_paper = {item["paper_id"]: item["chunk_id"] for item in exported["context"]["evidence"]}
    document = _comparison_document([PAPER_A, PAPER_B], by_paper)
    imported = import_comparison(workspace, exported, document)
    assert imported["ok"] is True
    assert imported["status"] == OK
    path = Path(imported["path"])
    assert path.is_file()
    assert path.parent.name == "reports"
    markdown = path.read_text(encoding="utf-8")
    assert markdown.startswith("# 论文对比")
    assert "不是确定性科学核验" in markdown
    assert "|" in markdown
    assert "条件:" in markdown
    assert "comparable" in markdown
    assert "source.md#page-1" in markdown
    assert imported["citations"]
    assert imported["output_sha256"] == __import__("hashlib").sha256(path.read_bytes()).hexdigest()


def test_missing_paper_hits_remain_visible(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture uniquealpha"],
        pages_b=["unrelated nebula token uniquebeta"],
    )
    exported = export_comparison_context(workspace, query="transformer", paper_ids=[PAPER_A, PAPER_B])
    assert exported["ok"] is True
    coverage = {item["paper_id"]: item["exported_chunks"] for item in exported["coverage"]}
    assert coverage[PAPER_A] >= 1
    assert coverage[PAPER_B] == 0
    assert all(item["paper_id"] != PAPER_B for item in exported["context"]["evidence"])
    by_paper = {item["paper_id"]: item["chunk_id"] for item in exported["context"]["evidence"]}
    document = _comparison_document([PAPER_A, PAPER_B], {PAPER_A: by_paper[PAPER_A], PAPER_B: None})
    imported = import_comparison(workspace, exported, document, output=workspace / "reports" / "gap.md")
    assert imported["ok"] is True
    markdown = Path(imported["path"]).read_text(encoding="utf-8")
    assert "证据不足" in markdown
    assert "Beta paper" in markdown


def test_no_global_evidence_and_selection_bounds(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    empty = export_comparison_context(workspace, query="zzz-no-such-term", paper_ids=[PAPER_A, PAPER_B])
    assert empty["ok"] is False
    assert empty["status"] == INSUFFICIENT_EVIDENCE
    one = export_comparison_context(workspace, query="quasar", paper_ids=[PAPER_A])
    assert one["ok"] is False
    assert one["status"] == LIGHT_SELECTION_INVALID
    missing = export_comparison_context(
        workspace,
        query="quasar",
        paper_ids=[PAPER_A, "sha256:" + ("c" * 64)],
    )
    assert missing["status"] == LIGHT_SELECTION_INVALID
    with pytest.raises(ResearchError) as exc:
        export_comparison_context(workspace, query="   ", paper_ids=[PAPER_A, PAPER_B])
    assert exc.value.code == LIGHT_COMPARISON_INVALID
    with pytest.raises(ResearchError):
        export_comparison_context(workspace, query="transformer", paper_ids=[PAPER_A, PAPER_B], dimensions=[])


def test_cell_completeness_ownership_and_comparability(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture uniquealpha"],
        pages_b=["transformer architecture uniquebeta"],
    )
    exported = export_comparison_context(workspace, query="transformer", paper_ids=[PAPER_A, PAPER_B])
    by_paper = {item["paper_id"]: item["chunk_id"] for item in exported["context"]["evidence"]}
    swapped = _comparison_document([PAPER_A, PAPER_B], by_paper)
    swapped["rows"][0]["cells"][0]["citations"] = [by_paper[PAPER_B]]
    assert import_comparison(workspace, exported, swapped, output=workspace / "reports" / "swap.md")[
        "status"
    ] == LIGHT_COMPARISON_INVALID
    incomplete = _comparison_document([PAPER_A, PAPER_B], by_paper)
    incomplete["rows"][0]["cells"] = incomplete["rows"][0]["cells"][:1]
    assert import_comparison(workspace, exported, incomplete, output=workspace / "reports" / "short.md")[
        "status"
    ] == LIGHT_COMPARISON_INVALID
    bad_comp = _comparison_document([PAPER_A, PAPER_B], {PAPER_A: by_paper[PAPER_A], PAPER_B: None})
    bad_comp["rows"][0]["comparability"] = "comparable"
    assert import_comparison(workspace, exported, bad_comp, output=workspace / "reports" / "comp.md")[
        "status"
    ] == LIGHT_COMPARISON_INVALID
    unknown_cond = _comparison_document([PAPER_A, PAPER_B], by_paper)
    unknown_cond["rows"][0]["cells"][1]["status"] = "unknown"
    unknown_cond["rows"][0]["cells"][1]["text"] = "证据不足"
    unknown_cond["rows"][0]["cells"][1]["citations"] = []
    unknown_cond["rows"][0]["cells"][1]["conditions"] = "dataset A"
    unknown_cond["rows"][0]["comparability"] = "not_comparable"
    assert import_comparison(workspace, exported, unknown_cond, output=workspace / "reports" / "cond.md")[
        "status"
    ] == LIGHT_COMPARISON_INVALID
    assert not (workspace / "reports" / "swap.md").exists()


def test_table_escaping_output_conflict_and_stale_refusal(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture uniquealpha"],
        pages_b=["transformer architecture uniquebeta"],
    )
    exported = export_comparison_context(workspace, query="transformer", paper_ids=[PAPER_A, PAPER_B])
    by_paper = {item["paper_id"]: item["chunk_id"] for item in exported["context"]["evidence"]}
    document = _comparison_document([PAPER_A, PAPER_B], by_paper)
    document["rows"][0]["reason"] = "a|b\nnewline"
    output = workspace / "reports" / "table.md"
    imported = import_comparison(workspace, exported, document, output=output)
    assert imported["ok"] is True
    markdown = output.read_text(encoding="utf-8")
    assert "a\\|b<br>newline" in markdown
    original = output.read_bytes()
    conflict = import_comparison(workspace, exported, document, output=output)
    assert conflict["ok"] is False
    assert conflict["status"] == LIGHT_OUTPUT_CONFLICT
    assert output.read_bytes() == original
    source = workspace / "papers" / SHA_A / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("transformer", "changedterm"))
    stale_out = workspace / "reports" / "stale.md"
    stale = import_comparison(workspace, exported, document, output=stale_out)
    assert stale["ok"] is False
    assert stale["status"] in {__import__("video_paper_wiki_research.light_index", fromlist=["INDEX_STALE"]).INDEX_STALE, LIGHT_COMPARISON_INVALID}
    assert not stale_out.exists()
    assert output.read_bytes() == original


def test_custom_dimensions_and_unsafe_output(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture uniquealpha"],
        pages_b=["transformer architecture uniquebeta"],
    )
    exported = export_comparison_context(
        workspace,
        query="transformer",
        paper_ids=[PAPER_A, PAPER_B],
        dimensions=["method", "limitations"],
    )
    assert exported["dimensions"] == ["method", "limitations"]
    by_paper = {item["paper_id"]: item["chunk_id"] for item in exported["context"]["evidence"]}
    document = _comparison_document([PAPER_A, PAPER_B], by_paper, dimensions=["method", "limitations"])
    imported = import_comparison(workspace, exported, document, output=workspace / "reports" / "dims.md")
    assert imported["ok"] is True
    assert "architecture" not in Path(imported["path"]).read_text(encoding="utf-8").split("\n", 8)[6]
    outside = tmp_path / "not-work.md"
    with pytest.raises(ResearchError) as exc:
        import_comparison(workspace, exported, document, output=outside)
    assert exc.value.code == WORKSPACE_INVALID
    assert not outside.exists()
    managed = workspace / "knowledge" / "compare.md"
    with pytest.raises(ResearchError) as exc:
        import_comparison(workspace, exported, document, output=managed)
    assert exc.value.code == WORKSPACE_INVALID
    assert not managed.exists()


def test_missing_comparison_wrapper_field_closes_without_traceback(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture uniquealpha"],
        pages_b=["transformer architecture uniquebeta"],
    )
    wrapper = export_comparison_context(workspace, query="transformer", paper_ids=[PAPER_A, PAPER_B])
    assert wrapper["ok"] is True
    del wrapper["coverage"]
    try:
        result = import_comparison(workspace, wrapper, {}, output=workspace / "reports" / "bad.md")
    except ResearchError:
        return
    assert result.get("ok") is False
    assert not (workspace / "reports" / "bad.md").exists()
