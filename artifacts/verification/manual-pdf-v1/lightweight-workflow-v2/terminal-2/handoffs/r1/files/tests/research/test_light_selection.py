from __future__ import annotations

from pathlib import Path

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from video_paper_wiki_research.light_context import (
    LIGHT_SELECTION_INVALID,
    export_context,
)
from video_paper_wiki_research.light_index import NO_RESULTS, OK, build_index

PAPER_A = "sha256:" + SHA_A
PAPER_B = "sha256:" + SHA_B
UNKNOWN = "sha256:" + "f" * 64


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_paper(workspace, SHA_A, "Alpha paper", ["alpha method evidence uniquealpha sharedterm"])
    _write_paper(workspace, SHA_B, "Beta paper", ["beta method evidence uniquebeta sharedterm"])
    build_index(workspace)
    return workspace


def test_none_and_empty_select_all_papers_for_qa_and_writing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    for kind, query in (("qa", "sharedterm"), ("writing", "sharedterm")):
        none = export_context(workspace, kind=kind, query=query, paper_ids=None)
        empty = export_context(workspace, kind=kind, query=query, paper_ids=[])
        assert none["ok"] is True and empty["ok"] is True
        assert none["status"] == empty["status"] == OK
        assert none["selected_paper_ids"] == []
        assert empty["selected_paper_ids"] == []
        assert {item["paper_id"] for item in none["evidence"]} == {PAPER_A, PAPER_B}
        assert {item["paper_id"] for item in empty["evidence"]} == {PAPER_A, PAPER_B}


def test_duplicates_normalize_first_seen_order(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    for kind in ("qa", "writing"):
        exported = export_context(
            workspace,
            kind=kind,
            query="sharedterm",
            paper_ids=[PAPER_B, PAPER_B, PAPER_A, PAPER_A],
        )
        assert exported["ok"] is True
        assert exported["selected_paper_ids"] == [PAPER_B, PAPER_A]
        assert {item["paper_id"] for item in exported["evidence"]} <= {PAPER_A, PAPER_B}


def test_unknown_or_malformed_ids_do_not_fall_back_to_all(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    cases = (
        [UNKNOWN],
        [PAPER_A, UNKNOWN],
        [""],
        ["sha256:" + "A" * 64],
        ["not-a-paper-id"],
        [PAPER_A, ""],
        PAPER_A,
    )
    for kind in ("qa", "writing"):
        for paper_ids in cases:
            exported = export_context(workspace, kind=kind, query="sharedterm", paper_ids=paper_ids)
            assert exported["ok"] is False
            assert exported["status"] == LIGHT_SELECTION_INVALID
            assert exported["evidence"] == []
            assert exported["selected_paper_ids"] == []
            assert all(item.get("paper_id") != PAPER_B for item in exported.get("evidence") or [])


def test_selected_paper_without_hits_does_not_cite_other_papers(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    for kind in ("qa", "writing"):
        exported = export_context(workspace, kind=kind, query="uniquebeta", paper_ids=[PAPER_A])
        assert exported["ok"] is False
        assert exported["status"] == NO_RESULTS
        assert exported["evidence"] == []
        assert exported["selected_paper_ids"] == [PAPER_A]
        blob = str(exported)
        assert "uniquebeta" not in blob or exported["evidence"] == []
        assert all(item.get("paper_id") != PAPER_B for item in exported.get("evidence") or [])


def test_filter_happens_before_topk(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    for kind in ("qa", "writing"):
        exported = export_context(workspace, kind=kind, query="sharedterm", paper_ids=[PAPER_B])
        assert exported["ok"] is True
        assert exported["selected_paper_ids"] == [PAPER_B]
        assert {item["paper_id"] for item in exported["evidence"]} == {PAPER_B}
        assert all(item["paper_id"] != PAPER_A for item in exported["evidence"])
