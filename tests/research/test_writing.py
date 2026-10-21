from __future__ import annotations

import copy
import json
from pathlib import Path

from tests.research.test_qa import PAPER_ID, RESEARCH, _valid_answer, plant_catalog
from video_paper_wiki_research.qa import INDEX_STALE, INSUFFICIENT_EVIDENCE, INVALID_CITATION, NO_RESULTS
from video_paper_wiki_research.writing import export_from_request, import_and_render
from video_paper_wiki_research.writing_cli import main as writing_main

TOPIC = "video generation transformers"
REQUIREMENTS = "Write a short editable overview with sources."


def _export(env, paper_ids=None):
    return export_from_request(
        topic=TOPIC,
        requirements=REQUIREMENTS,
        paper_ids=paper_ids or [PAPER_ID],
        vault_root=env.vault,
        upstream_root=env.upstream,
        retrieval_config=env.config,
    )


def test_topic_requirements_papers_render_editable_markdown(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    context = _export(env)
    assert context["ok"] is True
    assert context["kind"] == "writing-context"
    assert context["topic"] == TOPIC
    assert context["requirements"] == REQUIREMENTS
    assert [item["paper_id"] for item in context["papers"]] == [PAPER_ID]
    unit = context["evidence"][0]
    rendered = import_and_render(context=context, draft=_valid_answer(context))
    assert rendered["ok"] is True
    assert rendered["kind"] == "editable-markdown"
    assert rendered.get("schema") != "video-paper-wiki.paper-analysis-draft.v1"
    markdown = rendered["markdown"]
    assert markdown.startswith(f"# {TOPIC}")
    assert REQUIREMENTS in markdown
    assert "## 参考文献" in markdown
    assert PAPER_ID in markdown
    assert unit["evidence_unit_id"] in markdown
    assert "video-paper-wiki.paper-analysis-draft.v1" not in markdown
    assert "事实正确性" not in json.dumps(rendered, ensure_ascii=False)
    assert rendered["references"]
    assert all(item["paper_id"] == PAPER_ID for item in rendered["references"])
    assert any(item.get("evidence_unit_id") == unit["evidence_unit_id"] for item in rendered["references"])


def test_writing_stale_index_is_distinct(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    stale = copy.deepcopy(env.config)
    stale["query_version"] = "changed"
    result = export_from_request(
        topic=TOPIC,
        requirements=REQUIREMENTS,
        paper_ids=[PAPER_ID],
        vault_root=env.vault,
        upstream_root=env.upstream,
        retrieval_config=stale,
    )
    assert result["status"] == INDEX_STALE
    assert result["label"] == "旧索引"
    assert result["papers"] == []
    assert result["evidence"] == []
    assert PAPER_ID not in json.dumps(result, ensure_ascii=False)


def test_writing_unknown_paper_is_empty_result(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    result = _export(env, paper_ids=["arxiv:0001.00001"])
    assert result["status"] == NO_RESULTS
    assert result["label"] == "无结果"
    assert result["papers"] == []
    assert result["evidence"] == []
    assert result["missing_paper_ids"] == ["arxiv:0001.00001"]
    assert PAPER_ID not in json.dumps(result, ensure_ascii=False)


def test_writing_insufficient_evidence_is_distinct(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch, with_evidence=False)
    result = _export(env)
    assert result["status"] == INSUFFICIENT_EVIDENCE
    assert result["label"] == "证据不足"
    assert [item["paper_id"] for item in result["papers"]] == [PAPER_ID]
    assert result["evidence"] == []


def test_writing_invalid_citation_is_refused(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    context = _export(env)
    invented = "arxiv:0000.00000"
    rendered = import_and_render(
        context=context,
        draft={"markdown": "Invented draft.", "citations": [{"paper_id": invented}]},
    )
    assert rendered["status"] == INVALID_CITATION
    assert rendered["label"] == "无效引用"
    assert rendered["markdown"] == ""
    assert invented not in [item["paper_id"] for item in rendered["papers"]]
    assert invented not in [item["paper_id"] for item in rendered.get("references") or []]


def test_writing_modules_do_not_embed_model_clients() -> None:
    forbidden = ("api_key", "openai", "anthropic", "httpx", "urllib.request")
    for name in ("writing.py", "writing_cli.py"):
        text = (RESEARCH / name).read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text


def test_writing_cli_export_then_import(tmp_path, monkeypatch, capsys) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    export_code = writing_main(
        [
            "export",
            "--topic",
            TOPIC,
            "--requirements",
            REQUIREMENTS,
            "--paper-id",
            PAPER_ID,
            "--vault-root",
            str(env.vault),
            "--upstream-root",
            str(env.upstream),
            "--config",
            str(env.config_path),
        ]
    )
    exported = json.loads(capsys.readouterr().out)
    assert export_code == 0
    assert exported["ok"] is True
    assert exported["evidence"][0]["paper_id"] == PAPER_ID
    context_path = tmp_path / "writing-context.json"
    draft_path = tmp_path / "writing-draft.json"
    context_path.write_text(json.dumps(exported, ensure_ascii=False), encoding="utf-8")
    draft_path.write_text(json.dumps(_valid_answer(exported), ensure_ascii=False), encoding="utf-8")
    import_code = writing_main(["import", "--context", str(context_path), "--draft", str(draft_path)])
    imported = json.loads(capsys.readouterr().out)
    assert import_code == 0
    assert imported["ok"] is True
    assert imported["kind"] == "editable-markdown"
    assert imported["markdown"]
    assert imported["references"]
    assert "video-paper-wiki.paper-analysis-draft.v1" not in imported["markdown"]
