from __future__ import annotations

import json
import re
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
from video_paper_wiki_research.light_index import LIGHT_SELECTION_INVALID, OK, build_index
from video_paper_wiki_research.light_knowledge import WORKSPACE_INVALID, persisted_bytes
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


def _refused(call) -> None:
    try:
        result = call()
    except ResearchError:
        return
    assert result.get("ok") is False, result


def _comparison_pair(workspace: Path) -> tuple[dict, dict]:
    wrapper = export_comparison_context(
        workspace,
        query="transformer architecture training",
        paper_ids=[PAPER_A, PAPER_B],
        dimensions=["Method"],
    )
    assert wrapper["ok"] is True
    cells = []
    for paper_id in wrapper["paper_ids"]:
        evidence = next(item for item in wrapper["context"]["evidence"] if item["paper_id"] == paper_id)
        cells.append(
            {
                "citations": [evidence["chunk_id"]],
                "conditions": "dataset A | setting B\nprotocol C",
                "paper_id": paper_id,
                "status": "provisional",
                "text": "Mechanical cited fixture",
            }
        )
    document = {
        "rows": [
            {
                "cells": cells,
                "comparability": "not_comparable",
                "dimension": "Method",
                "reason": "Different fixture conditions",
            }
        ],
        "schema": COMPARISON_DOCUMENT_SCHEMA,
    }
    return wrapper, document


def test_duplicate_paper_selection_is_not_silently_rewritten(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture training experiment uniquealpha"],
        pages_b=["transformer architecture training experiment uniquebeta"],
    )
    wrapper, _ = _comparison_pair(workspace)
    a, b = wrapper["paper_ids"]
    _refused(lambda: export_comparison_context(workspace, query=wrapper["query"], paper_ids=[a, a, b]))
    _refused(lambda: export_comparison_context(workspace, query=wrapper["query"], paper_ids=[a, a]))
    over_limit = [a, a, b] + [f"sha256:{digit * 64}" for digit in "345678"]
    assert len(over_limit) == 9
    _refused(lambda: export_comparison_context(workspace, query=wrapper["query"], paper_ids=over_limit))
    for bad in ({}, [], "not-a-list", None):
        _refused(lambda bad=bad: export_comparison_context(workspace, query=wrapper["query"], paper_ids=bad))


def test_table_cells_have_real_citation_links(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture training experiment uniquealpha"],
        pages_b=["transformer architecture training experiment uniquebeta"],
    )
    wrapper, document = _comparison_pair(workspace)
    output = workspace / "reports" / "cited.md"
    imported = import_comparison(workspace, wrapper, document, output=output)
    assert imported["ok"] is True
    table = "\n".join(line for line in output.read_text(encoding="utf-8").splitlines() if line.startswith("| "))
    assert "[@" not in table, table
    hrefs = re.findall(r"\]\(([^)]*source\.md#page-\d+)\)", table)
    assert len(hrefs) >= 2, table
    for href in hrefs:
        relative = href.split("#", 1)[0].removeprefix("<").removesuffix(">")
        assert (output.parent / relative).resolve().is_file(), href


def test_table_conditions_are_escaped_exactly_once(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture training experiment uniquealpha"],
        pages_b=["transformer architecture training experiment uniquebeta"],
    )
    wrapper, document = _comparison_pair(workspace)
    output = workspace / "reports" / "conditions.md"
    imported = import_comparison(workspace, wrapper, document, output=output)
    assert imported["ok"] is True
    table = "\n".join(line for line in output.read_text(encoding="utf-8").splitlines() if line.startswith("| "))
    assert r"条件: dataset A \| setting B<br>protocol C" in table, table
    assert r"\<br\>" not in table, table


@pytest.mark.parametrize("bad", [{}, []])
def test_unhashable_comparability_is_closed(tmp_path: Path, bad: object) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture training experiment uniquealpha"],
        pages_b=["transformer architecture training experiment uniquebeta"],
    )
    wrapper, document = _comparison_pair(workspace)
    document["rows"][0]["comparability"] = bad
    output = workspace / "reports" / "invalid.md"
    _refused(lambda: import_comparison(workspace, wrapper, document, output=output))
    assert not output.exists()


def test_caller_markup_is_escaped_once_and_keeps_cell_boundaries(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture training experiment uniquealpha"],
        pages_b=["transformer architecture training experiment uniquebeta"],
    )
    wrapper = export_comparison_context(
        workspace,
        query="transformer architecture training",
        paper_ids=[PAPER_A, PAPER_B],
        dimensions=["method | [x] <y> \\ 中文"],
    )
    assert wrapper["ok"] is True
    cells = []
    for paper_id in wrapper["paper_ids"]:
        evidence = next(item for item in wrapper["context"]["evidence"] if item["paper_id"] == paper_id)
        cells.append(
            {
                "citations": [evidence["chunk_id"]],
                "conditions": "A|B\nC <tag> [n] \\ 路径",
                "paper_id": paper_id,
                "status": "provisional",
                "text": "claim | [raw] <x> \\ 对比",
            }
        )
    document = {
        "rows": [
            {
                "cells": cells,
                "comparability": "not_comparable",
                "dimension": "method | [x] <y> \\ 中文",
                "reason": "why | [r] <z> \\ 理由\nnext",
            }
        ],
        "schema": COMPARISON_DOCUMENT_SCHEMA,
    }
    output = workspace / "reports" / "markup.md"
    imported = import_comparison(workspace, wrapper, document, output=output)
    assert imported["ok"] is True
    table_lines = [line for line in output.read_text(encoding="utf-8").splitlines() if line.startswith("| ")]
    assert table_lines
    body = table_lines[2]
    cells_out = body.strip().strip("|").split(" | ")
    assert len(cells_out) == 5
    assert r"claim \| \[raw\] \<x\> \\ 对比" in cells_out[1]
    assert r"条件: A\|B<br>C \<tag\> \[n\] \\ 路径" in cells_out[1]
    assert r"\<br\>" not in body
    assert "[@" not in body
    assert r"why \| \[r\] \<z\> \\ 理由<br>next" in cells_out[4]
    assert len(re.findall(r"\]\([^)]*source\.md#page-\d+\)", body)) >= 2


def test_citation_title_newline_does_not_split_markdown_table(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        pages_a=["transformer architecture training experiment uniquealpha"],
        pages_b=["transformer architecture training experiment uniquebeta"],
    )
    paper = workspace / "papers" / SHA_A
    path = paper / "source.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["title"] = "Title first line\nTitle second | [line]"
    path.write_bytes(persisted_bytes(metadata))
    built = build_index(workspace)
    assert built["ok"] is True
    wrapper, document = _comparison_pair(workspace)
    output = workspace / "reports" / "title-newline.md"
    imported = import_comparison(workspace, wrapper, document, output=output)
    assert imported["ok"] is True
    text = output.read_text(encoding="utf-8")
    table_lines = [line for line in text.splitlines() if line.startswith("| ")]
    assert len(table_lines) == 3, table_lines
    header, _separator, row = table_lines
    assert "Title first line<br>Title second" in header
    assert "Title first line<br>Title second" in row
    assert "Title first line\nTitle second" not in header
    assert "Title first line\nTitle second" not in row
    assert header.startswith("| ") and header.endswith(" |")
    assert row.startswith("| ") and row.endswith(" |")
    assert "[@" not in row
    assert re.search(r"\]\([^)]*source\.md#page-\d+\)", row)
