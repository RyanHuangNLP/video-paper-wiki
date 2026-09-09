from __future__ import annotations

import json

from tests.research.test_light_qa import PAPER_A, PAPER_B, two_paper_retrieval
from video_paper_wiki_research.light_qa import (
    CITATION_CROSS,
    CITATION_MISMATCH,
    INDEX_STALE,
    INSUFFICIENT_EVIDENCE,
    INVALID_CITATION,
    NO_RESULTS,
)
from video_paper_wiki_research.light_writing import export_writing_context, render_draft

TOPIC = "高效视频生成的训练阶段"
REQUIREMENTS = "用中文写两段可编辑草稿，并引用证据。"


def test_empty_paper_ids_keeps_retrieval_hits() -> None:
    context = export_writing_context(TOPIC, REQUIREMENTS, [], two_paper_retrieval())
    assert context["ok"] is True
    assert context["kind"] == "writing"
    assert context["schema"] == "video-paper-wiki.light-context.v1"
    assert {item["paper_id"] for item in context["evidence"]} == {PAPER_A, PAPER_B}
    assert context["requirements"] == REQUIREMENTS
    assert "Do not invent" in context["prompt"]


def test_nonempty_paper_ids_drops_other_papers() -> None:
    context = export_writing_context(TOPIC, REQUIREMENTS, [PAPER_A], two_paper_retrieval())
    assert context["ok"] is True
    assert [item["paper_id"] for item in context["evidence"]] == [PAPER_A]
    assert all(item["paper_id"] != PAPER_B for item in context["evidence"])


def test_unknown_paper_ids_are_insufficient() -> None:
    context = export_writing_context(TOPIC, REQUIREMENTS, ["sha256:" + "f" * 64], two_paper_retrieval())
    assert context["status"] == INSUFFICIENT_EVIDENCE
    assert context["evidence"] == []


def test_chinese_multiparagraph_draft_is_editable_markdown() -> None:
    context = export_writing_context(TOPIC, REQUIREMENTS, [], two_paper_retrieval())
    draft = {
        "markdown": (
            "第一段：预训练随后做视频微调。[ @chk-sana-p3]\n"
            "\n"
            "第二段：基准还报告了 FVD。[ @chk-svd-p6]\n"
        ).replace("[ @", "[@"),
        "citations": [{"chunk_id": "chk-sana-p3"}, {"chunk_id": "chk-svd-p6"}],
    }
    rendered = render_draft(context, draft)
    assert rendered["ok"] is True
    markdown = rendered["markdown"]
    assert "第一段：预训练随后做视频微调。" in markdown
    assert "第二段：基准还报告了 FVD。" in markdown
    assert "Stage I image pretraining then video finetuning." in markdown
    assert "## 参考文献" in markdown
    assert "SANA-Video 2.0" in markdown
    assert "PDF 第 3 页" in markdown
    assert "#page-3" in markdown
    assert rendered.get("kind") == "editable-markdown"
    assert rendered.get("schema") != "video-paper-wiki.paper-analysis-draft.v1"
    assert "video-paper-wiki.paper-analysis-draft.v1" not in markdown
    assert "事实正确性" not in markdown
    assert "事实正确性" not in rendered["message"]


def test_writing_refusal_classes_match_qa() -> None:
    context = export_writing_context(TOPIC, REQUIREMENTS, [], two_paper_retrieval())
    invented = render_draft(context, {"markdown": "x [@chk-missing]", "citations": [{"chunk_id": "chk-missing"}]})
    mismatch = render_draft(
        context,
        {"markdown": "x [@chk-sana-p3]", "citations": [{"chunk_id": "chk-sana-p3"}, {"chunk_id": "chk-svd-p6"}]},
    )
    crossed = render_draft(
        context,
        {
            "markdown": "x [@chk-sana-p3]",
            "citations": [{"chunk_id": "chk-sana-p3", "paper_id": PAPER_B, "page": 6}],
        },
    )
    assert invented["status"] == INVALID_CITATION
    assert mismatch["status"] == CITATION_MISMATCH
    assert crossed["status"] == CITATION_CROSS
    empty = export_writing_context(
        TOPIC,
        REQUIREMENTS,
        [],
        {"ok": True, "status": "OK", "query": TOPIC, "index_id": "idx", "evidence": [], "message": ""},
    )
    assert empty["status"] == INSUFFICIENT_EVIDENCE
    none = export_writing_context(
        TOPIC,
        REQUIREMENTS,
        [],
        {"ok": False, "status": NO_RESULTS, "query": TOPIC, "index_id": "idx", "evidence": [], "message": "none"},
    )
    stale = export_writing_context(
        TOPIC,
        REQUIREMENTS,
        [],
        {"ok": False, "status": INDEX_STALE, "query": TOPIC, "index_id": "old", "evidence": [], "message": "stale"},
    )
    assert none["status"] == NO_RESULTS
    assert stale["status"] == INDEX_STALE


def test_output_is_not_paper_analysis_json() -> None:
    context = export_writing_context(TOPIC, REQUIREMENTS, [PAPER_A], two_paper_retrieval())
    rendered = render_draft(
        context,
        {"markdown": "草稿 [@chk-sana-p3]", "citations": [{"chunk_id": "chk-sana-p3"}]},
    )
    blob = json.dumps(rendered, ensure_ascii=False)
    assert "video-paper-wiki.paper-analysis-draft.v1" not in blob
    assert rendered["markdown"].count("\n") >= 3
