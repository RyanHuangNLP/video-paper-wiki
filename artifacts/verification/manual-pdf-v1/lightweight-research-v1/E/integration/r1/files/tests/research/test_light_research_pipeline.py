"""Integrated research pipeline through the public CLI.

Live owner backends are required. Missing modules fail. Labelled fixtures are
not current-model trials.
"""

from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

from tests.research.conftest import stdout_json
from tests.research.test_light_cli import _pdf_with_page_texts
from tests.research.test_light_knowledge import _knowledge_document
from tests.research.test_light_knowledge_batch import _merge_document
from tests.research.test_light_research_cli import OWNER_APIS, _require_live_backends
from tests.research.test_light_writing_project import _outline_document, _section_document
from video_paper_wiki_research.cli import main as research_main
from video_paper_wiki_research.light_knowledge import SECTION_KEYS
from video_paper_wiki_research.light_query import REWRITE_SCHEMA

ROOT = Path(__file__).resolve().parents[2]
READ = ROOT / ".agents" / "skills" / "video-paper-read"


def _run(args: list[str], capsys, *, expect: int = 0) -> dict:
    code = research_main(args)
    payload = stdout_json(capsys)
    assert code == expect, payload
    return payload


def _save(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _rewrite(query: str, rewritten: str) -> dict[str, str]:
    return {
        "language": "en",
        "original_query": query,
        "rewritten_query": rewritten,
        "schema": REWRITE_SCHEMA,
    }


def test_owner_modules_must_be_present() -> None:
    _require_live_backends()
    for module_name, attr in OWNER_APIS:
        module = importlib.import_module(f"video_paper_wiki_research.{module_name}")
        assert callable(getattr(module, attr))


def test_existing_workflow_kinds_are_unchanged(checkout: Path, capsys) -> None:
    workspace = checkout / ".work" / "pipeline-kinds"
    workspace.mkdir(parents=True)
    payload = _run(
        ["workflow", "prepare", "--workspace", str(workspace), "--kind", "notes", "--query", "q"],
        capsys,
        expect=2,
    )
    assert payload["error"]["code"] == "USAGE"
    help_text = __import__("video_paper_wiki_research.cli", fromlist=["build_parser"]).build_parser().format_help()
    assert "workflow" in help_text
    assert "outline-export" in help_text or "writing" in help_text


def test_skill_and_docs_describe_research_actions() -> None:
    skill = (READ / "SKILL.md").read_text(encoding="utf-8")
    research = (READ / "references" / "research.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "docs" / "lightweight-research-quickstart.md").read_text(encoding="utf-8")
    assert "Create internal JSON yourself" in skill
    assert "references/research.md" in skill
    assert "project_id" in research
    assert "video-paper-wiki.light-writing-section.v1" in research
    assert "--keep-sections" in research
    assert "--accept-concepts" in research
    assert "尚未撰写" in research or "unwritten" in research
    assert "processing_complete" in research
    assert "用户" in quickstart or "不要" in quickstart
    assert "batch-plan" in quickstart
    assert "outline-export" in quickstart


def test_rewritten_query_outline_sections_backup_and_restore(checkout: Path, capsys) -> None:
    _require_live_backends()
    workspace = checkout / ".work" / "research-write"
    workspace.mkdir(parents=True)
    first = checkout / "alpha.pdf"
    first.write_bytes(_pdf_with_page_texts(["Synthetic quasar method evidence uniquealpha."]))
    second = checkout / "beta.pdf"
    second.write_bytes(_pdf_with_page_texts(["Nebula writing token evidence uniquebeta."]))
    alpha = _run(["pdf", "add", "--pdf", str(first), "--workspace", str(workspace), "--title", "Alpha"], capsys)
    beta = _run(["pdf", "add", "--pdf", str(second), "--workspace", str(workspace), "--title", "Beta"], capsys)
    assert alpha["ok"] is True and beta["ok"] is True
    _run(["index", "build", "--workspace", str(workspace)], capsys)

    question = "这篇论文的方法是什么"
    rewrite = _save(workspace / "qa-rewrite.json", _rewrite(question, "quasar method"))
    qa = _run(
        [
            "qa",
            "export",
            "--question",
            question,
            "--workspace",
            str(workspace),
            "--rewrite",
            str(rewrite),
            "--paper-id",
            alpha["paper_id"],
        ],
        capsys,
    )
    assert qa["ok"] is True
    assert qa["query"] == question
    assert qa["query_plan"]["routes"][0]["name"] == "original"
    chunk = qa["evidence"][0]["chunk_id"]
    answer = _save(
        workspace / "qa-answer.json",
        {"citations": [{"chunk_id": chunk}], "text": f"方法见证据。 [@{chunk}]"},
    )
    imported_qa = _run(
        [
            "qa",
            "import",
            "--workspace",
            str(workspace),
            "--context",
            str(_save(workspace / "qa-ctx.json", qa)),
            "--answer",
            str(answer),
            "--output",
            str(workspace / "reports" / "qa.md"),
        ],
        capsys,
    )
    assert imported_qa["ok"] is True
    qa_md = Path(imported_qa["path"]).read_text(encoding="utf-8")
    assert "source.md#page-1" in qa_md

    topic = "请按证据写提纲"
    writing_rewrite = _save(workspace / "w-rewrite.json", _rewrite(topic, "quasar method nebula writing"))
    writing = _run(
        [
            "writing",
            "export",
            "--topic",
            topic,
            "--requirements",
            "用中文写提纲并修订章节。",
            "--workspace",
            str(workspace),
            "--rewrite",
            str(writing_rewrite),
        ],
        capsys,
    )
    assert writing["ok"] is True
    assert writing["kind"] == "writing"
    wctx = _save(workspace / "wctx.json", writing)
    outline_export = _run(
        ["writing", "outline-export", "--workspace", str(workspace), "--context", str(wctx)],
        capsys,
    )
    assert outline_export["ok"] is True
    outline_ctx = _save(workspace / "outline-ctx.json", outline_export)
    outline_doc = _save(workspace / "outline-doc.json", _outline_document(writing))
    created = _run(
        [
            "writing",
            "outline-import",
            "--workspace",
            str(workspace),
            "--context",
            str(outline_ctx),
            "--document",
            str(outline_doc),
        ],
        capsys,
    )
    assert created["ok"] is True
    assert created["progress"]["unwritten"] == 2
    assert created["progress"]["complete"] is False
    project_id = created["project_id"]
    outline_revision = created["revision_id"]

    pending_dir = workspace / ".light-writing" / "staging"
    pending_dir.mkdir(parents=True, exist_ok=True)
    orphan = pending_dir / "orphan.txt"
    orphan.write_text("pending publication\n", encoding="utf-8")
    backup_dir = checkout / ".work" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    blocked = _run(
        [
            "backup",
            "create",
            "--workspace",
            str(workspace),
            "--output",
            str(backup_dir / "pending-writing.zip"),
        ],
        capsys,
        expect=2,
    )
    assert blocked["ok"] is False
    assert blocked["status"] == "LIGHT_BACKUP_INVALID"
    assert orphan.read_text(encoding="utf-8") == "pending publication\n"
    orphan.unlink()

    unwritten_backup = _run(
        [
            "backup",
            "create",
            "--workspace",
            str(workspace),
            "--output",
            str(backup_dir / "unwritten-writing.zip"),
        ],
        capsys,
    )
    assert unwritten_backup["ok"] is True

    first_export = _run(
        [
            "writing",
            "section-export",
            "--workspace",
            str(workspace),
            "--project-id",
            project_id,
            "--section-id",
            "s1",
        ],
        capsys,
    )
    assert first_export["ok"] is True
    first_chunk = writing["evidence"][0]["chunk_id"]
    first_doc = _save(
        workspace / "s1.json",
        _section_document(project_id, "s1", first_chunk, "第一段方法。"),
    )
    first = _run(
        [
            "writing",
            "section-import",
            "--workspace",
            str(workspace),
            "--context",
            str(_save(workspace / "s1-ctx.json", first_export)),
            "--document",
            str(first_doc),
        ],
        capsys,
    )
    assert first["ok"] is True
    assert first["parent_revision_id"] == outline_revision
    assert first["progress"]["written"] == 1
    assert first["progress"]["unwritten"] == 1
    outline_page = (workspace / created["page_path"]).read_text(encoding="utf-8")
    assert "尚未撰写" in outline_page
    assert "第一段方法。" not in outline_page

    bad = dict(_section_document(project_id, "s2", "chk-missing", "伪造。"))
    bad["citations"] = ["chk-missing"]
    bad["markdown"] = "伪造。 [@chk-missing]"
    second_export = _run(
        [
            "writing",
            "section-export",
            "--workspace",
            str(workspace),
            "--project-id",
            project_id,
            "--section-id",
            "s2",
            "--instructions",
            "补实验段。",
        ],
        capsys,
    )
    assert second_export["ok"] is True
    invalid = _run(
        [
            "writing",
            "section-import",
            "--workspace",
            str(workspace),
            "--context",
            str(_save(workspace / "s2-bad-ctx.json", second_export)),
            "--document",
            str(_save(workspace / "s2-bad.json", bad)),
        ],
        capsys,
        expect=2,
    )
    assert invalid["ok"] is False
    assert invalid["status"] == "LIGHT_WRITING_PROJECT_INVALID"
    second_chunk = writing["evidence"][1]["chunk_id"] if len(writing["evidence"]) > 1 else first_chunk
    second = _run(
        [
            "writing",
            "section-import",
            "--workspace",
            str(workspace),
            "--context",
            str(_save(workspace / "s2-ctx.json", second_export)),
            "--document",
            str(_save(workspace / "s2.json", _section_document(project_id, "s2", second_chunk, "第二段实验。"))),
        ],
        capsys,
    )
    assert second["ok"] is True
    assert second["progress"]["complete"] is True
    assert "尚未撰写" in (workspace / created["page_path"]).read_text(encoding="utf-8")
    assert "第一段方法。" in (workspace / first["page_path"]).read_text(encoding="utf-8")
    assert "第二段实验。" not in (workspace / first["page_path"]).read_text(encoding="utf-8")

    exported_md = _run(
        [
            "writing",
            "project-export",
            "--workspace",
            str(workspace),
            "--project-id",
            project_id,
            "--output",
            str(workspace / "reports" / "article.md"),
        ],
        capsys,
    )
    assert exported_md["ok"] is True
    article = Path(exported_md["path"]).read_text(encoding="utf-8")
    assert "第一段方法。" in article
    assert "第二段实验。" in article
    assert "source.md#page-" in article
    history = _run(
        ["writing", "history", "--workspace", str(workspace), "--project-id", project_id],
        capsys,
    )
    assert history["ok"] is True
    assert history["head_revision_id"] == second["revision_id"]
    assert len(history["revisions"]) == 3

    source = workspace / "papers" / alpha["paper_id"].split(":", 1)[1] / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("quasar method evidence", "changed evidence"), encoding="utf-8")
    _run(["index", "build", "--workspace", str(workspace)], capsys)
    stale = _run(
        [
            "writing",
            "section-export",
            "--workspace",
            str(workspace),
            "--project-id",
            project_id,
            "--section-id",
            "s1",
        ],
        capsys,
        expect=2,
    )
    assert stale["ok"] is False
    assert stale["status"] == "INDEX_STALE"

    archive = backup_dir / "complete-writing.zip"
    created_backup = _run(
        ["backup", "create", "--workspace", str(workspace), "--output", str(archive)],
        capsys,
    )
    assert created_backup["ok"] is True
    verified = _run(["backup", "verify", "--archive", str(archive)], capsys)
    assert verified["ok"] is True
    dest = checkout / ".work" / "restored-writing"
    restored = _run(
        ["backup", "restore", "--archive", str(archive), "--destination", str(dest)],
        capsys,
    )
    assert restored["ok"] is True
    relocated = _run(
        ["writing", "history", "--workspace", str(dest), "--project-id", project_id],
        capsys,
    )
    assert relocated["ok"] is True
    assert {row["source_status"] for row in relocated["revisions"]} == {"historical"}
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
    assert any(project_id in name for name in names)


def test_batch_merge_refresh_selected_apply_and_handoffs(checkout: Path, capsys) -> None:
    _require_live_backends()
    workspace = checkout / ".work" / "research-batch"
    workspace.mkdir(parents=True)
    pages = [f"Synthetic quasar method evidence uniquealpha page {index:04d}." for index in range(50)]
    long_pdf = checkout / "long.pdf"
    long_pdf.write_bytes(_pdf_with_page_texts(pages))
    added = _run(["pdf", "add", "--pdf", str(long_pdf), "--workspace", str(workspace), "--title", "Long"], capsys)
    paper_id = added["paper_id"]
    _run(["index", "build", "--workspace", str(workspace)], capsys)
    planned = _run(
        ["knowledge", "batch-plan", "--workspace", str(workspace), "--paper-id", paper_id],
        capsys,
    )
    assert planned["ok"] is True
    assert planned["batch_count"] >= 2
    plan_id = planned["plan_id"]
    for index in range(planned["batch_count"]):
        exported = _run(
            [
                "knowledge",
                "batch-export",
                "--workspace",
                str(workspace),
                "--plan-id",
                plan_id,
                "--batch-index",
                str(index),
            ],
            capsys,
        )
        assert exported["ok"] is True
        chunk = exported["context"]["evidence"][0]["chunk_id"]
        imported = _run(
            [
                "knowledge",
                "batch-import",
                "--workspace",
                str(workspace),
                "--context",
                str(_save(workspace / f"batch-{index}.json", exported)),
                "--document",
                str(_save(workspace / f"batch-{index}-doc.json", _knowledge_document(paper_id, chunk))),
            ],
            capsys,
        )
        assert imported["ok"] is True
        merge = _run(
            ["knowledge", "merge-export", "--workspace", str(workspace), "--plan-id", plan_id],
            capsys,
        )
        assert merge["ok"] is True
        merged = _run(
            [
                "knowledge",
                "merge-import",
                "--workspace",
                str(workspace),
                "--context",
                str(_save(workspace / f"merge-{index}.json", merge)),
                "--document",
                str(_save(workspace / f"merge-{index}-doc.json", _merge_document(paper_id, merge))),
            ],
            capsys,
        )
        assert merged["ok"] is True
    status = _run(
        ["knowledge", "batch-status", "--workspace", str(workspace), "--plan-id", plan_id],
        capsys,
    )
    assert status["ok"] is True
    finalized = _run(
        ["knowledge", "finalize", "--workspace", str(workspace), "--plan-id", plan_id],
        capsys,
    )
    assert finalized["ok"] is True
    listed = _run(["knowledge", "list", "--workspace", str(workspace)], capsys)
    base_id = listed["heads"][paper_id]
    assert base_id == finalized["record_id"]

    refresh = _run(
        ["knowledge", "refresh-plan", "--workspace", str(workspace), "--paper-id", paper_id],
        capsys,
    )
    assert refresh["ok"] is True
    assert refresh["batch_count"] == 0
    meta_final = _run(
        ["knowledge", "finalize", "--workspace", str(workspace), "--plan-id", refresh["plan_id"]],
        capsys,
    )
    assert meta_final["ok"] is True
    assert meta_final.get("advanced_head") is False
    diff = _run(
        [
            "knowledge",
            "diff",
            "--workspace",
            str(workspace),
            "--base-record-id",
            base_id,
            "--candidate-record-id",
            meta_final["record_id"],
        ],
        capsys,
    )
    assert diff["ok"] is True
    applied = _run(
        [
            "knowledge",
            "apply",
            "--workspace",
            str(workspace),
            "--diff",
            str(_save(workspace / "meta-diff.json", diff)),
            "--accept-section",
            "summary",
            "--keep-concepts",
        ],
        capsys,
    )
    assert applied["ok"] is True
    assert applied["accepted_sections"] == ["summary"]
    assert applied["accept_concepts"] is False
    after_meta = _run(["knowledge", "list", "--workspace", str(workspace)], capsys)
    assert after_meta["heads"][paper_id] == applied["record_id"]

    digest = paper_id.split(":", 1)[1]
    source = workspace / "papers" / digest / "source.md"
    source.write_text(
        source.read_text(encoding="utf-8").replace("uniquealpha page 0000", "changedalpha page 0000", 1),
        encoding="utf-8",
    )
    _run(["index", "build", "--workspace", str(workspace)], capsys)
    changed = _run(
        ["knowledge", "refresh-plan", "--workspace", str(workspace), "--paper-id", paper_id],
        capsys,
    )
    assert changed["ok"] is True
    assert changed["batch_count"] >= 1
    change_plan = changed["plan_id"]
    for index in range(changed["batch_count"]):
        exported = _run(
            [
                "knowledge",
                "batch-export",
                "--workspace",
                str(workspace),
                "--plan-id",
                change_plan,
                "--batch-index",
                str(index),
            ],
            capsys,
        )
        chunk = exported["context"]["evidence"][0]["chunk_id"]
        _run(
            [
                "knowledge",
                "batch-import",
                "--workspace",
                str(workspace),
                "--context",
                str(_save(workspace / f"chg-batch-{index}.json", exported)),
                "--document",
                str(
                    _save(
                        workspace / f"chg-batch-{index}-doc.json",
                        _knowledge_document(paper_id, chunk, extra_provisional="method"),
                    )
                ),
            ],
            capsys,
        )
        merge = _run(
            ["knowledge", "merge-export", "--workspace", str(workspace), "--plan-id", change_plan],
            capsys,
        )
        _run(
            [
                "knowledge",
                "merge-import",
                "--workspace",
                str(workspace),
                "--context",
                str(_save(workspace / f"chg-merge-{index}.json", merge)),
                "--document",
                str(_save(workspace / f"chg-merge-{index}-doc.json", _merge_document(paper_id, merge))),
            ],
            capsys,
        )
    changed_final = _run(
        ["knowledge", "finalize", "--workspace", str(workspace), "--plan-id", change_plan],
        capsys,
    )
    assert changed_final["ok"] is True
    current = _run(["knowledge", "list", "--workspace", str(workspace)], capsys)
    changed_diff = _run(
        [
            "knowledge",
            "diff",
            "--workspace",
            str(workspace),
            "--base-record-id",
            current["heads"][paper_id],
            "--candidate-record-id",
            changed_final["record_id"],
        ],
        capsys,
    )
    assert changed_diff["ok"] is True
    selected = _run(
        [
            "knowledge",
            "apply",
            "--workspace",
            str(workspace),
            "--diff",
            str(_save(workspace / "changed-diff.json", changed_diff)),
            "--accept-section",
            "summary",
            "--accept-section",
            "method",
            "--accept-concepts",
        ],
        capsys,
    )
    assert selected["ok"] is True
    assert selected["accepted_sections"] == [key for key in SECTION_KEYS if key in {"summary", "method"}]
    assert selected["accept_concepts"] is True
    keep_only = _run(
        [
            "knowledge",
            "apply",
            "--workspace",
            str(workspace),
            "--diff",
            str(_save(workspace / "keep-diff.json", {"schema": "not-current"})),
            "--keep-sections",
            "--keep-concepts",
        ],
        capsys,
        expect=2,
    )
    assert keep_only["ok"] is False
