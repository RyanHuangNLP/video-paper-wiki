"""Drive the shipped vpwiki-research light CLI. No converter stub or planted index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from video_paper_wiki_research.cli import main as research_main


def run_argv(argv: list[str]) -> dict[str, Any]:
    from io import StringIO
    import sys

    buffer = StringIO()
    old = sys.stdout
    try:
        sys.stdout = buffer
        code = research_main(argv)
    finally:
        sys.stdout = old
    text = buffer.getvalue().strip()
    payload = json.loads(text) if text else {}
    payload["_exit_code"] = code
    return payload


def add_pdf(pdf: Path, workspace: Path, *, title: str | None = None) -> dict[str, Any]:
    argv = ["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)]
    if title:
        argv.extend(["--title", title])
    return run_argv(argv)


def build_workspace_index(workspace: Path) -> dict[str, Any]:
    return run_argv(["index", "build", "--workspace", str(workspace)])


def export_qa(question: str, workspace: Path) -> dict[str, Any]:
    return run_argv(["qa", "export", "--question", question, "--workspace", str(workspace)])


def import_qa(context: Path, answer: Path, output: Path) -> dict[str, Any]:
    return run_argv(
        ["qa", "import", "--context", str(context), "--answer", str(answer), "--output", str(output)]
    )


def export_writing(topic: str, requirements: str, workspace: Path, paper_ids: list[str] | None = None) -> dict[str, Any]:
    argv = [
        "writing",
        "export",
        "--topic",
        topic,
        "--requirements",
        requirements,
        "--workspace",
        str(workspace),
    ]
    for paper_id in paper_ids or []:
        argv.extend(["--paper-id", paper_id])
    return run_argv(argv)


def import_writing(context: Path, draft: Path, output: Path) -> dict[str, Any]:
    return run_argv(
        [
            "writing",
            "import",
            "--context",
            str(context),
            "--draft",
            str(draft),
            "--output",
            str(output),
        ]
    )
