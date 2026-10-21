from __future__ import annotations

import hashlib
import json

from video_paper_wiki_research.light_qa import (
    CITATION_CROSS,
    CITATION_MISMATCH,
    INDEX_STALE,
    INSUFFICIENT_EVIDENCE,
    INVALID_CITATION,
    NO_RESULTS,
    export_qa_context,
    render_answer,
)

PAPER_A = "sha256:" + "a" * 64
PAPER_B = "sha256:" + "b" * 64
SOURCE_A = "c" * 64
SOURCE_B = "d" * 64


def _item(*, chunk_id: str, paper_id: str, title: str, page: int, text: str, path: str, score: float) -> dict:
    return {
        "chunk_id": chunk_id,
        "paper_id": paper_id,
        "title": title,
        "source_sha256": SOURCE_A if paper_id == PAPER_A else SOURCE_B,
        "page": page,
        "markdown_path": path,
        "markdown_sha256": hashlib.sha256(path.encode()).hexdigest(),
        "text_start": 10,
        "text_end": 10 + len(text),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
        "score": score,
    }


def two_paper_retrieval() -> dict:
    text_a = "Stage I image pretraining then video finetuning."
    text_b = "The benchmark reports FVD on UCF-101."
    return {
        "ok": True,
        "status": "OK",
        "query": "training stages",
        "index_id": "idx-fixture-1",
        "message": "ok",
        "evidence": [
            _item(
                chunk_id="chk-sana-p3",
                paper_id=PAPER_A,
                title="SANA-Video 2.0",
                page=3,
                text=text_a,
                path="papers/" + "a" * 64 + "/source.md",
                score=2.5,
            ),
            _item(
                chunk_id="chk-svd-p6",
                paper_id=PAPER_B,
                title="Stable Video Diffusion",
                page=6,
                text=text_b,
                path="papers/" + "b" * 64 + "/source.md",
                score=1.25,
            ),
        ],
    }


def test_export_keeps_evidence_text_and_forbids_invented_sources() -> None:
    retrieval = two_paper_retrieval()
    context = export_qa_context("What are the training stages?", retrieval)
    assert context["ok"] is True
    assert context["schema"] == "video-paper-wiki.light-context.v1"
    assert context["kind"] == "qa"
    assert context["prompt"]
    assert "invent" in context["prompt"].lower() or "Do not invent" in context["prompt"]
    assert [item["text"] for item in context["evidence"]] == [item["text"] for item in retrieval["evidence"]]
    assert [item["page"] for item in context["evidence"]] == [3, 6]
    assert context["evidence"][0]["chunk_id"] == "chk-sana-p3"
    assert context["index_id"] == "idx-fixture-1"


def test_legal_multi_cite_renders_text_and_page_anchor() -> None:
    retrieval = two_paper_retrieval()
    context = export_qa_context("training stages", retrieval)
    answer = {
        "text": (
            "Pretraining is described here [@chk-sana-p3]. "
            "A reported metric appears here [@chk-svd-p6]."
        ),
        "citations": [{"chunk_id": "chk-sana-p3"}, {"chunk_id": "chk-svd-p6"}],
    }
    rendered = render_answer(context, answer)
    assert rendered["ok"] is True
    assert rendered["status"] == "OK"
    markdown = rendered["markdown"]
    assert "Stage I image pretraining then video finetuning." in markdown
    assert "The benchmark reports FVD on UCF-101." in markdown
    assert "SANA-Video 2.0, p.3" in markdown
    assert "papers/" + "a" * 64 + "/source.md#page-3" in markdown
    assert "PDF 第 6 页" in markdown
    assert "page-6" in markdown
    assert "事实正确性" not in markdown
    assert "事实正确性" not in rendered["message"]
    assert rendered["citations"][0]["chunk_id"] == "chk-sana-p3"
    assert rendered["citations"][1]["page"] == 6


def test_empty_evidence_is_insufficient() -> None:
    retrieval = {"ok": True, "status": "OK", "query": "x", "index_id": "idx", "evidence": [], "message": ""}
    context = export_qa_context("x", retrieval)
    assert context["ok"] is False
    assert context["status"] == INSUFFICIENT_EVIDENCE
    rendered = render_answer(context, {"text": "guess", "citations": []})
    assert rendered["status"] == INSUFFICIENT_EVIDENCE
    assert rendered["markdown"] == ""


def test_invented_chunk_fails_distinctly() -> None:
    context = export_qa_context("x", two_paper_retrieval())
    rendered = render_answer(
        context,
        {"text": "Invented [@chk-missing]", "citations": [{"chunk_id": "chk-missing"}]},
    )
    assert rendered["ok"] is False
    assert rendered["status"] == INVALID_CITATION


def test_body_list_mismatch_fails_distinctly() -> None:
    context = export_qa_context("x", two_paper_retrieval())
    rendered = render_answer(
        context,
        {
            "text": "Only one mark [@chk-sana-p3].",
            "citations": [{"chunk_id": "chk-sana-p3"}, {"chunk_id": "chk-svd-p6"}],
        },
    )
    assert rendered["status"] == CITATION_MISMATCH


def test_cross_paper_identity_fails_distinctly() -> None:
    context = export_qa_context("x", two_paper_retrieval())
    rendered = render_answer(
        context,
        {
            "text": "Mixed identity [@chk-sana-p3].",
            "citations": [{"chunk_id": "chk-sana-p3", "paper_id": PAPER_B, "page": 6}],
        },
    )
    assert rendered["status"] == CITATION_CROSS


def test_retrieval_no_results_and_stale_are_distinct() -> None:
    empty = export_qa_context(
        "x",
        {"ok": False, "status": NO_RESULTS, "query": "x", "index_id": "idx", "evidence": [], "message": "none"},
    )
    stale = export_qa_context(
        "x",
        {"ok": False, "status": INDEX_STALE, "query": "x", "index_id": "old", "evidence": [], "message": "stale"},
    )
    assert empty["status"] == NO_RESULTS
    assert stale["status"] == INDEX_STALE
    assert empty["status"] != stale["status"]


def test_success_is_not_paper_analysis_draft_json() -> None:
    context = export_qa_context("x", two_paper_retrieval())
    rendered = render_answer(
        context,
        {"text": "Cite [@chk-sana-p3].", "citations": [{"chunk_id": "chk-sana-p3"}]},
    )
    assert "video-paper-wiki.paper-analysis-draft.v1" not in json.dumps(rendered, ensure_ascii=False)
    assert rendered["markdown"].startswith("Cite")
