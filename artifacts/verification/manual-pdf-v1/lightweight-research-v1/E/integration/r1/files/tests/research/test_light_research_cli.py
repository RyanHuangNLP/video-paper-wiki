"""Integrated research CLI routing, secure handoffs, and live owner wiring.

Live T1/T2/T3 backends are required. Missing owner modules fail these tests.
No mocked owner APIs. Synthetic fixtures are not current-model trials.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

from tests.research.conftest import stdout_json
from tests.research.test_light_cli import _pdf_with_page_texts
from video_paper_wiki_research.cli import build_parser, main as research_main
from video_paper_wiki_research.contracts import JSON_MAX_BYTES
from video_paper_wiki_research.light_query import REWRITE_SCHEMA

ROOT = Path(__file__).resolve().parents[2]
READ = ROOT / ".agents" / "skills" / "video-paper-read"

OWNER_APIS = (
    ("light_query", "export_rewritten_context"),
    ("light_knowledge_batch", "plan_knowledge_batches"),
    ("light_knowledge_batch", "export_knowledge_batch"),
    ("light_knowledge_batch", "import_knowledge_batch"),
    ("light_knowledge_batch", "knowledge_batch_status"),
    ("light_knowledge_batch", "export_knowledge_merge_context"),
    ("light_knowledge_batch", "import_knowledge_merge"),
    ("light_knowledge_batch", "finalize_knowledge_batches"),
    ("light_knowledge_refresh", "plan_knowledge_refresh"),
    ("light_knowledge_refresh", "export_knowledge_diff"),
    ("light_knowledge_refresh", "apply_knowledge_refresh"),
    ("light_writing_project", "export_writing_outline"),
    ("light_writing_project", "import_writing_outline"),
    ("light_writing_project", "export_writing_section"),
    ("light_writing_project", "import_writing_section"),
    ("light_writing_project", "writing_project_history"),
    ("light_writing_project", "export_writing_project"),
    ("light_writing_project", "writing_backup_blockers"),
    ("light_backup", "create_backup"),
)


def _require_live_backends() -> None:
    missing: list[str] = []
    for module_name, attr in OWNER_APIS:
        try:
            module = importlib.import_module(f"video_paper_wiki_research.{module_name}")
        except ModuleNotFoundError:
            missing.append(f"{module_name}.{attr}")
            continue
        if not callable(getattr(module, attr, None)):
            missing.append(f"{module_name}.{attr}")
    if missing:
        raise AssertionError("owner modules/APIs are required for integrated research tests: " + ", ".join(missing))


def _workspace(checkout: Path, name: str = "research-cli") -> Path:
    path = checkout / ".work" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _rewrite_payload(query: str, rewritten: str) -> dict[str, str]:
    return {
        "language": "en",
        "original_query": query,
        "rewritten_query": rewritten,
        "schema": REWRITE_SCHEMA,
    }


def test_owner_modules_must_be_present() -> None:
    _require_live_backends()


def test_help_lists_research_commands_and_apply_choices() -> None:
    parser = build_parser()
    text = parser.format_help()
    for name in ("qa", "writing", "knowledge", "backup", "workflow"):
        assert name in text
    command = {action.dest: action for action in parser._actions if getattr(action, "dest", None) == "command"}
    writing = command["command"].choices["writing"]
    writing_help = writing.format_help()
    for item in ("outline-export", "outline-import", "section-export", "section-import", "history", "project-export"):
        assert item in writing_help
    qa_export = command["command"].choices["qa"]._subparsers._group_actions[0].choices["export"].format_help()
    assert "--rewrite" in qa_export
    writing_export = writing._subparsers._group_actions[0].choices["export"].format_help()
    assert "--rewrite" in writing_export
    knowledge = command["command"].choices["knowledge"]
    knowledge_help = knowledge.format_help()
    for item in (
        "batch-plan",
        "batch-export",
        "batch-import",
        "batch-status",
        "merge-export",
        "merge-import",
        "finalize",
        "refresh-plan",
        "diff",
        "apply",
    ):
        assert item in knowledge_help
    apply_help = knowledge._subparsers._group_actions[0].choices["apply"].format_help()
    assert "--accept-section" in apply_help
    assert "--keep-sections" in apply_help
    assert "--accept-concepts" in apply_help
    assert "--keep-concepts" in apply_help
    assert "--diff" in apply_help
    section_export = writing._subparsers._group_actions[0].choices["section-export"].format_help()
    assert "--project-id" in section_export
    assert "--section-id" in section_export
    assert "--instructions" in section_export


def test_missing_flags_and_apply_groups_are_usage(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    assert research_main(["writing", "outline-export", "--workspace", str(workspace)]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert research_main(["knowledge", "batch-export", "--workspace", str(workspace), "--plan-id", "ab" * 32]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(workspace / "missing.json"),
                "--accept-concepts",
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(workspace / "missing.json"),
                "--keep-sections",
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(workspace / "missing.json"),
                "--keep-sections",
                "--accept-concepts",
                "--keep-concepts",
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert "accept-concepts" in payload["error"]["message"]
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(workspace / "missing.json"),
                "--accept-section",
                "summary",
                "--accept-section",
                "summary",
                "--keep-concepts",
            ]
        )
        == 2
    )
    duplicated = stdout_json(capsys)
    assert duplicated["error"]["code"] == "USAGE"
    assert "duplicate" in duplicated["error"]["message"]


def test_rewrite_is_rejected_on_vault_route_and_duplicate_paper_ids(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    rewrite = _save(workspace / "rewrite.json", _rewrite_payload("方法是什么", "quasar method"))
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "方法是什么",
                "--rewrite",
                str(rewrite),
                "--vault-root",
                str(workspace),
                "--upstream-root",
                str(workspace),
                "--config",
                str(workspace / "cfg.json"),
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert "--rewrite" in payload["error"]["message"]
    paper = "sha256:" + ("01" * 32)
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "方法是什么",
                "--workspace",
                str(workspace),
                "--rewrite",
                str(rewrite),
                "--paper-id",
                paper,
                "--paper-id",
                paper,
            ]
        )
        == 2
    )
    duplicated = stdout_json(capsys)
    assert duplicated["error"]["code"] == "USAGE"
    assert "duplicate" in duplicated["error"]["message"]


def test_secure_handoffs_refuse_before_owner_work(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    document = _save(workspace / "doc.json", {"schema": "video-paper-wiki.light-writing-outline.v1"})
    missing = workspace / "absent.json"
    assert (
        research_main(
            [
                "writing",
                "outline-import",
                "--workspace",
                str(workspace),
                "--context",
                str(missing),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    duplicate = workspace / "dup.json"
    duplicate.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    assert (
        research_main(
            [
                "knowledge",
                "batch-import",
                "--workspace",
                str(workspace),
                "--context",
                str(duplicate),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    nan = workspace / "nan.json"
    nan.write_text('{"a": NaN}', encoding="utf-8")
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(nan),
                "--keep-sections",
                "--keep-concepts",
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    linked = workspace / "link.json"
    real = _save(workspace / "real.json", {"ok": True})
    linked.symlink_to(real)
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "方法是什么",
                "--workspace",
                str(workspace),
                "--rewrite",
                str(linked),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    hard = workspace / "hard.json"
    os.link(real, hard)
    assert (
        research_main(
            [
                "writing",
                "section-import",
                "--workspace",
                str(workspace),
                "--context",
                str(hard),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    huge = workspace / "huge.json"
    huge.write_bytes(b"{" + (b"a" * (JSON_MAX_BYTES + 1)) + b"}")
    assert (
        research_main(
            [
                "knowledge",
                "merge-import",
                "--workspace",
                str(workspace),
                "--context",
                str(huge),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"


def test_live_rewrite_export_and_keep_sections_reach_owner(checkout: Path, capsys) -> None:
    _require_live_backends()
    workspace = _workspace(checkout, "live-rewrite")
    pdf = checkout / "alpha.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Synthetic quasar method evidence uniquealpha."]))
    added = research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace), "--title", "Alpha"])
    payload = stdout_json(capsys)
    assert added == 0 and payload["ok"] is True
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    question = "这篇论文的方法是什么"
    rewrite = _save(workspace / "rewrite.json", _rewrite_payload(question, "quasar method"))
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                question,
                "--workspace",
                str(workspace),
                "--rewrite",
                str(rewrite),
            ]
        )
        == 0
    )
    exported = stdout_json(capsys)
    assert exported["ok"] is True
    assert exported["query"] == question
    assert exported["query_plan"]["rewrite"]["rewritten_query"] == "quasar method"
    assert exported["evidence"]
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(_save(workspace / "not-a-diff.json", {"schema": "not-a-diff"})),
                "--keep-sections",
                "--keep-concepts",
            ]
        )
        == 2
    )
    refused = stdout_json(capsys)
    assert refused["ok"] is False
    assert refused.get("status") or refused.get("error", {}).get("code")
    assert "Traceback" not in refused.get("message", "")
