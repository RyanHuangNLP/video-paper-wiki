#!/usr/bin/env python3
"""Independent pre-acceptance probes for the lightweight research CLI.

This harness is intentionally outside ``src/`` and ``tests/``.  It launches
the candidate CLI in a subprocess with an explicit source root and interpreter,
creates a disposable real backend fixture under ``/private/tmp``, and prints a
single JSON report.  It does not patch/import-test doubles, install packages,
or fall back to an optional skip when a required route is absent.

Run only after a stopped integration candidate exists, for example:

    .venv/bin/python artifacts/verification/manual-pdf-v1/lightweight-research-v1/probes/cli_preacceptance_harness_r3.py \
      --source-root .work/parallel/lightweight-research-v1/terminal-3/source

Use ``--static-only`` before that point to record the current CLI observations.
The candidate is expected to close the dynamic cases with nonzero JSON errors;
the harness reports a missing route as a failed required probe rather than
silently skipping it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


JSON_MAX_DEPTH = 64
LEGACY_JSON_DEPTH = 1400
LARGE_ARRAY_JSON_DEPTH = 10000
LARGE_INTEGER_DIGITS = 5000
JSON_MAX_BYTES = 8 * 1024 * 1024
PAPER_DIGEST = "a" * 64
PAPER_ID = "sha256:" + PAPER_DIGEST
ROOT = Path(__file__).resolve().parents[5]
DEFAULT_SOURCE_ROOT = ROOT / ".work/parallel/lightweight-research-v1/terminal-3/source"

# The complete inherited integration candidate has 26 source paths.  Keep the
# list explicit so every dynamic report records each path's exact bytes rather
# than relying on a directory walk whose contents can drift between runs.
CANDIDATE_26_PATHS = (
    ".agents/skills/video-paper-read/SKILL.md",
    ".agents/skills/video-paper-read/references/research.md",
    "README.md",
    "docs/lightweight-library-quickstart.md",
    "docs/lightweight-pdf-quickstart.md",
    "docs/lightweight-research-quickstart.md",
    "src/video_paper_wiki_research/cli.py",
    "src/video_paper_wiki_research/light_backup.py",
    "tests/research/test_light_backup.py",
    "tests/research/test_light_research_cli.py",
    "tests/research/test_light_research_installed.py",
    "tests/research/test_light_research_pipeline.py",
    "src/video_paper_wiki_research/light_context.py",
    "src/video_paper_wiki_research/light_index.py",
    "src/video_paper_wiki_research/light_knowledge.py",
    "src/video_paper_wiki_research/light_knowledge_batch.py",
    "src/video_paper_wiki_research/light_knowledge_refresh.py",
    "src/video_paper_wiki_research/light_query.py",
    "src/video_paper_wiki_research/light_writing_project.py",
    "tests/research/test_light_context.py",
    "tests/research/test_light_index.py",
    "tests/research/test_light_knowledge.py",
    "tests/research/test_light_knowledge_batch.py",
    "tests/research/test_light_knowledge_refresh.py",
    "tests/research/test_light_query.py",
    "tests/research/test_light_writing_project.py",
)


class ProbeFailure(RuntimeError):
    pass


_DYNAMIC_FAILURES: list[str] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_26path_manifest(source_root: Path) -> dict[str, Any]:
    """Hash every inherited candidate path, preserving missing-path evidence."""
    files: list[dict[str, Any]] = []
    for relative in CANDIDATE_26_PATHS:
        path = source_root / relative
        if path.is_file():
            files.append(
                {
                    "path": relative,
                    "sha256": sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        else:
            files.append(
                {
                    "path": relative,
                    "sha256": None,
                    "size_bytes": None,
                    "missing": True,
                }
            )
    return {
        "count": len(files),
        "complete": all(item.get("sha256") for item in files),
        "files": files,
    }


def _json_payload(stdout: str, *, argv: list[str]) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ProbeFailure(f"CLI did not return exactly one JSON line for {argv!r}: {stdout!r}")
    try:
        value = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise ProbeFailure(f"CLI returned non-JSON stdout for {argv!r}: {stdout!r}") from exc
    if type(value) is not dict:
        raise ProbeFailure(f"CLI JSON root is not an object for {argv!r}")
    return value


def run_cli(source_root: Path, python: str, argv: list[str]) -> dict[str, Any]:
    """Run the exact source checkout with a fixed import origin."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str((source_root / "src").resolve()),
    }
    command = [python, "-m", "video_paper_wiki_research", *argv]
    completed = subprocess.run(
        command,
        cwd=source_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    traceback_leaked = "Traceback (most recent call last)" in completed.stderr or "Traceback (most recent call last)" in completed.stdout
    try:
        payload = _json_payload(completed.stdout, argv=argv)
    except ProbeFailure as exc:
        if not traceback_leaked:
            raise
        payload = {
            "ok": False,
            "error": {"code": "TRACEBACK_LEAKED", "message": str(exc)},
        }
    error = payload.get("error") if type(payload) is dict else None
    error_code = error.get("code") if type(error) is dict else None
    if error_code is None and type(payload) is dict:
        error_code = payload.get("status")
    return {
        "argv": argv,
        "command": command,
        "exit_code": completed.returncode,
        "error_code": error_code,
        "payload": payload,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "traceback_leaked": traceback_leaked,
        "source_root": str(source_root),
        "pythonpath": env["PYTHONPATH"],
        "python": python,
    }


def _write_paper(workspace: Path, *, body: str, title: str = "Alpha paper") -> Path:
    """Create the same regular source fixture used by the real index backend."""
    directory = workspace / "papers" / PAPER_DIGEST
    directory.mkdir(parents=True, exist_ok=False)
    header = '<a id="page-1"></a>\n\n## PDF 第 1 页\n\n'
    markdown = header + body + "\n\n"
    markdown_path = directory / "source.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    text_start = len(header)
    metadata = {
        "schema": "video-paper-wiki.light-paper.v1",
        "paper_id": PAPER_ID,
        "title": title,
        "source": {
            "path": f"/absolute/{PAPER_DIGEST}.pdf",
            "sha256": PAPER_DIGEST,
            "size_bytes": 12,
        },
        "parser": {"engine": "pypdf-native-text", "version": "6.16.2"},
        "page_count": 1,
        "document": {
            "path": f"papers/{PAPER_DIGEST}/source.md",
            "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        },
        "pages": [
            {
                "page": 1,
                "anchor": "page-1",
                "text_start": text_start,
                "text_end": text_start + len(body),
                "text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        ],
        "warnings": [],
    }
    (directory / "source.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return markdown_path


def _unknown() -> dict[str, Any]:
    from video_paper_wiki_research.light_knowledge import UNKNOWN_TEXT

    return {"citations": [], "status": "unknown", "text": UNKNOWN_TEXT}


def _knowledge_document(chunk_id: str) -> dict[str, Any]:
    from video_paper_wiki_research.light_knowledge import (
        KNOWLEDGE_DOCUMENT_SCHEMA,
        SECTION_KEYS,
    )

    sections = {key: _unknown() for key in SECTION_KEYS}
    sections["summary"] = {
        "citations": [chunk_id],
        "status": "provisional",
        "text": "The paper describes a synthetic method.",
    }
    return {
        "concepts": [{"citations": [chunk_id], "name": "Synthetic Method"}],
        "paper_id": PAPER_ID,
        "schema": KNOWLEDGE_DOCUMENT_SCHEMA,
        "sections": sections,
    }


def _seed_real_workspace(root: Path) -> dict[str, Any]:
    """Seed regular paper/index/context data through real source modules."""
    from video_paper_wiki_research.light_context import export_context
    from video_paper_wiki_research.light_index import build_index

    workspace = root / ".work" / "fixture"
    workspace.mkdir(parents=True)
    markdown = _write_paper(
        workspace,
        body="Synthetic quasar method evidence uniquealpha sharedconcept.",
    )
    built = build_index(workspace)
    if built.get("ok") is not True:
        raise ProbeFailure(f"real index fixture failed: {built}")
    qa_context = export_context(workspace, kind="qa", query="uniquealpha")
    writing_context = export_context(
        workspace,
        kind="writing",
        query="uniquealpha",
        requirements="one concise paragraph",
        paper_ids=[PAPER_ID],
    )
    if qa_context.get("ok") is not True or writing_context.get("ok") is not True:
        raise ProbeFailure(f"real context fixture failed: {qa_context} / {writing_context}")
    chunk_id = qa_context["evidence"][0]["chunk_id"]
    handoffs = root / ".work" / "handoffs"
    handoffs.mkdir(parents=True)
    paths = {
        "workspace": workspace,
        "markdown": markdown,
        "qa_context": handoffs / "qa-context.json",
        "writing_context": handoffs / "writing-context.json",
        "rewrite": handoffs / "rewrite.json",
        "qa_answer": handoffs / "qa-answer.json",
        "writing_draft": handoffs / "writing-draft.json",
    }
    paths["qa_context"].write_text(json.dumps(qa_context, ensure_ascii=False), encoding="utf-8")
    paths["writing_context"].write_text(json.dumps(writing_context, ensure_ascii=False), encoding="utf-8")
    paths["rewrite"].write_text(
        json.dumps(
            {
                "schema": "video-paper-wiki.light-query-rewrite.v1",
                "original_query": "uniquealpha",
                "rewritten_query": "uniquealpha",
                "language": "en",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paths["qa_answer"].write_text(
        json.dumps(
            {
                "text": f"The method uses quasar evidence. [@{chunk_id}]",
                "citations": [{"chunk_id": chunk_id}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paths["writing_draft"].write_text(
        json.dumps(
            {
                "markdown": f"The method uses quasar evidence. [@{chunk_id}]",
                "citations": [{"chunk_id": chunk_id}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paths["chunk_id"] = chunk_id  # type: ignore[assignment]
    paths["qa_context_obj"] = qa_context  # type: ignore[assignment]
    paths["writing_context_obj"] = writing_context  # type: ignore[assignment]
    return paths


def _seed_real_writing_project(fixture: dict[str, Any]) -> str:
    """Create a genuine outline project for the project-export path probe."""
    from video_paper_wiki_research.light_writing_project import (
        export_writing_outline,
        export_writing_section,
        import_writing_outline,
        import_writing_section,
    )

    workspace = fixture["workspace"]
    context = fixture["writing_context_obj"]
    wrapper = export_writing_outline(workspace, context)
    if wrapper.get("ok") is not True:
        raise ProbeFailure(f"writing outline fixture export failed: {wrapper}")
    chunk_id = context["evidence"][0]["chunk_id"]
    document = {
        "schema": "video-paper-wiki.light-writing-outline.v1",
        "sections": [
            {
                "citations": [chunk_id],
                "goal": "Record the method evidence.",
                "section_id": "s1",
                "status": "provisional",
                "title": "Method",
            }
        ],
        "title": "Probe outline",
    }
    imported = import_writing_outline(workspace, wrapper, document)
    if imported.get("ok") is not True:
        raise ProbeFailure(f"writing outline fixture import failed: {imported}")
    project_id = str(imported["project_id"])
    section = export_writing_section(workspace, project_id=project_id, section_id="s1")
    if section.get("ok") is not True:
        raise ProbeFailure(f"writing section fixture export failed: {section}")
    section_document = {
        "citations": [chunk_id],
        "markdown": f"The method evidence is recorded. [@{chunk_id}]",
        "project_id": project_id,
        "schema": "video-paper-wiki.light-writing-section.v1",
        "section_id": "s1",
        "status": "provisional",
    }
    completed = import_writing_section(workspace, section, section_document)
    if completed.get("ok") is not True or completed.get("progress", {}).get("complete") is not True:
        raise ProbeFailure(f"writing section fixture import failed to complete project: {completed}")
    return project_id


def _configure_source_origin(source_root: Path) -> None:
    """Make direct fixture imports resolve only from the candidate source tree."""
    source_src = str((source_root / "src").resolve())
    sys.path[:] = [item for item in sys.path if item != source_src]
    sys.path.insert(0, source_src)
    os.environ["PYTHONPATH"] = source_src
    # Fail loudly if an installed/editable package shadows the requested tree.
    import importlib.util

    spec = importlib.util.find_spec("video_paper_wiki_research")
    origin = str(getattr(spec, "origin", ""))
    if origin and not origin.startswith(source_src):
        raise ProbeFailure(f"candidate package origin escaped fixed PYTHONPATH: {origin}")


def _seed_real_diff_fixture(root: Path, fixture: dict[str, Any]) -> Path:
    """Create one genuine refresh diff for the apply argument probes."""
    from video_paper_wiki_research.light_index import build_index
    from video_paper_wiki_research.light_knowledge import export_knowledge_context, import_knowledge
    from video_paper_wiki_research.light_knowledge_batch import (
        export_knowledge_batch,
        export_knowledge_merge_context,
        finalize_knowledge_batches,
        import_knowledge_batch,
        import_knowledge_merge,
    )
    from video_paper_wiki_research.light_knowledge_refresh import (
        export_knowledge_diff,
        plan_knowledge_refresh,
    )

    workspace = fixture["workspace"]
    exported = export_knowledge_context(workspace, paper_id=PAPER_ID)
    if exported.get("ok") is not True:
        raise ProbeFailure(f"base knowledge export failed: {exported}")
    base_document = _knowledge_document(exported["context"]["evidence"][0]["chunk_id"])
    published = import_knowledge(workspace, exported, base_document)
    if published.get("ok") is not True:
        raise ProbeFailure(f"base knowledge import failed: {published}")

    source = fixture["markdown"]
    original = source.read_text(encoding="utf-8")
    changed_body = original[:-2] + " changed-source-token.\n\n"
    source.write_text(changed_body, encoding="utf-8")
    metadata_path = source.with_name("source.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["document"]["sha256"] = hashlib.sha256(changed_body.encode("utf-8")).hexdigest()
    page = metadata["pages"][0]
    header = '<a id="page-1"></a>\n\n## PDF 第 1 页\n\n'
    body = changed_body[len(header) : -2]
    page["text_end"] = len(header) + len(body)
    page["text_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rebuilt = build_index(workspace)
    if rebuilt.get("ok") is not True:
        raise ProbeFailure(f"changed-source index rebuild failed: {rebuilt}")

    planned = plan_knowledge_refresh(workspace, paper_id=PAPER_ID)
    if planned.get("ok") is not True or not planned.get("batch_count"):
        raise ProbeFailure(f"refresh fixture did not produce a batch: {planned}")
    for batch_index in range(planned["batch_count"]):
        batch = export_knowledge_batch(
            workspace, plan_id=planned["plan_id"], batch_index=batch_index
        )
        if batch.get("ok") is not True:
            raise ProbeFailure(f"refresh batch export failed: {batch}")
        document = _knowledge_document(batch["context"]["evidence"][0]["chunk_id"])
        accepted = import_knowledge_batch(workspace, batch, document)
        if accepted.get("ok") is not True:
            raise ProbeFailure(f"refresh batch import failed: {accepted}")
        merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
        if merge.get("ok") is not True:
            raise ProbeFailure(f"refresh merge export failed: {merge}")
        merged = import_knowledge_merge(workspace, merge, document)
        if merged.get("ok") is not True:
            raise ProbeFailure(f"refresh merge import failed: {merged}")
    candidate = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    if candidate.get("ok") is not True:
        raise ProbeFailure(f"refresh candidate finalize failed: {candidate}")
    diff = export_knowledge_diff(
        workspace,
        base_record_id=published["record_id"],
        candidate_record_id=candidate["record_id"],
    )
    if diff.get("ok") is not True:
        raise ProbeFailure(f"refresh diff export failed: {diff}")
    path = root / ".work" / "handoffs" / "refresh-diff.json"
    path.write_text(json.dumps(diff, ensure_ascii=False), encoding="utf-8")
    return path


def _expect_closed(result: dict[str, Any], *, codes: Iterable[str], label: str) -> None:
    if result.get("traceback_leaked"):
        _DYNAMIC_FAILURES.append(f"{label} leaked a traceback: {result}")
    payload = result["payload"]
    if result["exit_code"] == 0 or payload.get("ok") is True:
        _DYNAMIC_FAILURES.append(f"{label} unexpectedly succeeded: {result}")
        return
    code = payload.get("error", {}).get("code") or payload.get("status")
    if code not in set(codes):
        _DYNAMIC_FAILURES.append(
            f"{label} returned {code!r}, expected one of {sorted(set(codes))}: {result}"
        )


def _expect_usage(result: dict[str, Any], *, label: str) -> None:
    _expect_closed(result, codes={"USAGE"}, label=label)


def _static_observations(source_root: Path) -> dict[str, Any]:
    cli = source_root / "src/video_paper_wiki_research/cli.py"
    if not cli.is_file():
        raise ProbeFailure(f"candidate CLI is missing: {cli}")
    text = cli.read_text(encoding="utf-8")
    qa_import = text.split("def _cmd_qa_import", 1)[-1].split("def _cmd_writing_export", 1)[0]
    writing_import = text.split("def _cmd_writing_import", 1)[-1].split("def _cmd_workspace_inspect", 1)[0]
    return {
        "source_root": str(source_root),
        "cli_path": str(cli),
        "cli_sha256": sha256(cli),
        "pyproject_sha256": sha256(source_root / "pyproject.toml"),
        "candidate_26path_manifest": candidate_26path_manifest(source_root),
        "workspace_resolve_before_backend_observed": "resolved = given.resolve()" in text
        and "def _workspace_root" in text,
        "qa_workspace_import_uses_secure_reader_observed": "if args.workspace:" in qa_import
        and "context = _read_library_json(args.context)" in qa_import
        and "_read_library_json(args.answer)" in qa_import,
        "writing_workspace_import_uses_secure_reader_observed": "if args.workspace:" in writing_import
        and "context = _read_library_json(args.context)" in writing_import
        and "_read_library_json(args.draft)" in writing_import,
        "legacy_permissive_import_fallback_preserved": "context = _read_json(args.context)" in qa_import
        and "context = _read_json(args.context)" in writing_import,
        "paper_id_list_helper_forwards_raw": "return list(raw)" in text,
        "duplicate_guard_is_present_for_rewrite_branch": "if rewrite is not None:\n        _reject_duplicate_paper_ids(paper_ids)" in text,
        "knowledge_apply_surface_present": 'knowledge_sub.add_parser("apply"' in text
        and "def _cmd_knowledge_apply" in text,
        "secure_reader_definition_present": "def _read_library_json" in text,
    }


def _run_dynamic(source_root: Path, python: str) -> dict[str, Any]:
    _DYNAMIC_FAILURES.clear()
    if not Path("/private/tmp").is_dir():
        raise ProbeFailure("/private/tmp is required for the short disposable fixture")
    _configure_source_origin(source_root)
    with tempfile.TemporaryDirectory(prefix="vpwiki-cli-preaccept-", dir="/private/tmp") as temp:
        root = Path(temp)
        fixture = _seed_real_workspace(root)
        project_id = _seed_real_writing_project(fixture)
        workspace = fixture["workspace"]
        alias = root / ".work" / "workspace-alias"
        alias.symlink_to(workspace, target_is_directory=True)
        raw_workspace = alias / ".." / workspace.name

        results: dict[str, Any] = {}
        raw_case = run_cli(
            source_root,
            python,
            ["knowledge", "batch-status", "--workspace", str(raw_workspace)],
        )
        _expect_closed(raw_case, codes={"WORKSPACE_INVALID"}, label="raw symlink/.. workspace")
        results["raw_workspace"] = raw_case

        raw_qa_rewrite = run_cli(
            source_root,
            python,
            [
                "qa",
                "export",
                "--question",
                "uniquealpha",
                "--rewrite",
                str(fixture["rewrite"]),
                "--workspace",
                str(raw_workspace),
            ],
        )
        _expect_closed(raw_qa_rewrite, codes={"WORKSPACE_INVALID"}, label="raw symlink/.. QA rewrite workspace")
        results["raw_qa_rewrite_workspace"] = raw_qa_rewrite

        raw_writing_rewrite = run_cli(
            source_root,
            python,
            [
                "writing",
                "export",
                "--topic",
                "uniquealpha",
                "--requirements",
                "one concise paragraph",
                "--rewrite",
                str(fixture["rewrite"]),
                "--workspace",
                str(raw_workspace),
            ],
        )
        _expect_closed(
            raw_writing_rewrite,
            codes={"WORKSPACE_INVALID"},
            label="raw symlink/.. writing rewrite workspace",
        )
        results["raw_writing_rewrite_workspace"] = raw_writing_rewrite

        output_alias = root / ".work" / "writing-output-alias"
        output_target = root / ".work" / "writing-output-target"
        output_target.mkdir(parents=True)
        output_alias.symlink_to(output_target, target_is_directory=True)
        raw_output = output_alias / ".." / "writing-project.md"
        canonical_output = raw_output.resolve()
        raw_project_export = run_cli(
            source_root,
            python,
            [
                "writing",
                "project-export",
                "--workspace",
                str(workspace),
                "--project-id",
                project_id,
                "--output",
                str(raw_output),
            ],
        )
        _expect_closed(
            raw_project_export,
            codes={"WORKSPACE_INVALID"},
            label="writing project-export raw parent symlink/.. output",
        )
        if canonical_output.exists():
            _DYNAMIC_FAILURES.append(
                f"raw parent symlink/.. output was materialized at canonical path: {canonical_output}"
            )
        results["raw_writing_project_export_output"] = raw_project_export

        duplicate_qa = run_cli(
            source_root,
            python,
            [
                "qa",
                "export",
                "--question",
                "uniquealpha",
                "--rewrite",
                str(fixture["rewrite"]),
                "--workspace",
                str(workspace),
                "--paper-id",
                PAPER_ID,
                "--paper-id",
                PAPER_ID,
            ],
        )
        _expect_closed(
            duplicate_qa,
            codes={"LIGHT_SELECTION_INVALID", "QUERY_REWRITE_INVALID"},
            label="duplicate QA paper ids in traced rewrite",
        )
        results["duplicate_qa_paper_ids"] = duplicate_qa

        duplicate_writing = run_cli(
            source_root,
            python,
            [
                "writing",
                "export",
                "--topic",
                "uniquealpha",
                "--requirements",
                "one concise paragraph",
                "--rewrite",
                str(fixture["rewrite"]),
                "--workspace",
                str(workspace),
                "--paper-id",
                PAPER_ID,
                "--paper-id",
                PAPER_ID,
            ],
        )
        _expect_closed(
            duplicate_writing,
            codes={"LIGHT_SELECTION_INVALID", "QUERY_REWRITE_INVALID"},
            label="duplicate writing paper ids in traced rewrite",
        )
        results["duplicate_writing_paper_ids"] = duplicate_writing

        import_cases = [
            ("qa", "--answer", fixture["qa_answer"], fixture["qa_context"]),
            ("writing", "--draft", fixture["writing_draft"], fixture["writing_context"]),
        ]
        for kind, document_flag, document_path, context_path in import_cases:
            valid = run_cli(
                source_root,
                python,
                [
                    kind,
                    "import",
                    "--context",
                    str(context_path),
                    document_flag,
                    str(document_path),
                    "--workspace",
                    str(workspace),
                ],
            )
            if valid["exit_code"] != 0 or valid["payload"].get("ok") is not True:
                _DYNAMIC_FAILURES.append(f"valid {kind} import failed: {valid}")
            results[f"valid_{kind}_import"] = valid

            malformed_dir = root / ".work" / f"malformed-{kind}"
            malformed_dir.mkdir(parents=True)
            duplicate_context = malformed_dir / "duplicate-context.json"
            duplicate_context.write_bytes(b'{"schema":"video-paper-wiki.light-context.v1","schema":"duplicate"}')
            duplicate = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(duplicate_context), document_flag, str(document_path), "--workspace", str(workspace)],
            )
            _expect_closed(duplicate, codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"}, label=f"duplicate {kind} context keys")
            results[f"duplicate_{kind}_context_keys"] = duplicate

            symlink_context = malformed_dir / "context-symlink.json"
            symlink_context.symlink_to(context_path)
            symlink = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(symlink_context), document_flag, str(document_path), "--workspace", str(workspace)],
            )
            _expect_closed(symlink, codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"}, label=f"symlink {kind} context")
            results[f"symlink_{kind}_context"] = symlink

            hardlink_context = malformed_dir / "context-hardlink.json"
            os.link(context_path, hardlink_context)
            hardlink = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(hardlink_context), document_flag, str(document_path), "--workspace", str(workspace)],
            )
            _expect_closed(hardlink, codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"}, label=f"hardlink {kind} context")
            results[f"hardlink_{kind}_context"] = hardlink

            invalid_utf8 = malformed_dir / "invalid-utf8.json"
            invalid_utf8.write_bytes(b"\xff")
            utf8 = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(invalid_utf8), document_flag, str(document_path), "--workspace", str(workspace)],
            )
            _expect_closed(utf8, codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"}, label=f"invalid UTF-8 {kind} context")
            results[f"invalid_utf8_{kind}_context"] = utf8

            deep = malformed_dir / "deep.json"
            nested: Any = "leaf"
            for _ in range(JSON_MAX_DEPTH + 8):
                nested = [nested]
            deep.write_text(json.dumps({"nested": nested}), encoding="utf-8")
            deep_result = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(deep), document_flag, str(document_path), "--workspace", str(workspace)],
            )
            _expect_closed(deep_result, codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"}, label=f"deep {kind} context")
            results[f"deep_{kind}_context"] = deep_result

            nonfinite = malformed_dir / "nonfinite.json"
            nonfinite.write_text('{"score":NaN}', encoding="utf-8")
            nonfinite_result = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(nonfinite), document_flag, str(document_path), "--workspace", str(workspace)],
            )
            _expect_closed(nonfinite_result, codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"}, label=f"nonfinite {kind} context")
            results[f"nonfinite_{kind}_context"] = nonfinite_result

            unknown = json.loads(context_path.read_text(encoding="utf-8"))
            unknown["unexpected_transport_field"] = True
            unknown_path = malformed_dir / "unknown.json"
            unknown_path.write_text(json.dumps(unknown, ensure_ascii=False), encoding="utf-8")
            unknown_result = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(unknown_path), document_flag, str(document_path), "--workspace", str(workspace)],
            )
            # Ordinary outer context extras are legacy-compatible and are
            # intentionally observed without turning success into a blocker.
            results[f"unknown_{kind}_outer_context_field_legacy"] = unknown_result

            # Unknown fields inside the identity-bearing query_plan are a
            # strict traced-rewrite contract case and must close.
            strict_unknown = json.loads(context_path.read_text(encoding="utf-8"))
            query_plan = strict_unknown.get("query_plan")
            if type(query_plan) is not dict:
                raise ProbeFailure(f"{kind} fixture did not contain a query_plan")
            query_plan["unexpected_query_plan_field"] = True
            strict_unknown_path = malformed_dir / "unknown-query-plan-field.json"
            strict_unknown_path.write_text(
                json.dumps(strict_unknown, ensure_ascii=False), encoding="utf-8"
            )
            strict_unknown_result = run_cli(
                source_root,
                python,
                [
                    kind,
                    "import",
                    "--context",
                    str(strict_unknown_path),
                    document_flag,
                    str(document_path),
                    "--workspace",
                    str(workspace),
                ],
            )
            _expect_closed(
                strict_unknown_result,
                codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"},
                label=f"unknown {kind} query_plan field",
            )
            results[f"unknown_{kind}_query_plan_field"] = strict_unknown_result

            # Legacy import inference from context.workspace_root remains a
            # supported light-context route.  A deeply nested extra member
            # must close before permissive json.loads can leak RecursionError.
            deep_legacy = malformed_dir / "deep-legacy-context.json"
            nested_text = "[" * LEGACY_JSON_DEPTH + "0" + "]" * LEGACY_JSON_DEPTH
            deep_legacy.write_text(
                '{"schema":"video-paper-wiki.light-context.v1","workspace_root":'
                + json.dumps(str(workspace))
                + ',"nested":'
                + nested_text
                + "}",
                encoding="utf-8",
            )
            deep_legacy_result = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(deep_legacy), document_flag, str(document_path)],
            )
            _expect_closed(
                deep_legacy_result,
                codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"},
                label=f"deep legacy {kind} context without workspace",
            )
            results[f"deep_legacy_{kind}_context"] = deep_legacy_result

            # The 1400-level legacy observation remains in the report.  These
            # larger no-workspace inputs exercise the initial permissive JSON
            # reader paths that can otherwise leak RecursionError/ValueError.
            large_array = malformed_dir / "deep-array-10000.json"
            large_array.write_text(
                '{"schema":"video-paper-wiki.light-context.v1","workspace_root":'
                + json.dumps(str(workspace))
                + ',"nested":'
                + "[" * LARGE_ARRAY_JSON_DEPTH
                + "0"
                + "]" * LARGE_ARRAY_JSON_DEPTH
                + "}",
                encoding="utf-8",
            )
            large_array_result = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(large_array), document_flag, str(document_path)],
            )
            _expect_closed(
                large_array_result,
                codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"},
                label=f"10000-array {kind} context without workspace",
            )
            results[f"deep_10000_{kind}_context"] = large_array_result

            large_integer = malformed_dir / "integer-5000-digits.json"
            large_integer.write_text(
                '{"schema":"video-paper-wiki.light-context.v1","workspace_root":'
                + json.dumps(str(workspace))
                + ',"score":'
                + "9" * LARGE_INTEGER_DIGITS
                + "}",
                encoding="utf-8",
            )
            large_integer_result = run_cli(
                source_root,
                python,
                [kind, "import", "--context", str(large_integer), document_flag, str(document_path)],
            )
            _expect_closed(
                large_integer_result,
                codes={"LIGHT_HANDOFF_INVALID", "LIGHT_CONTEXT_INVALID"},
                label=f"5000-digit {kind} context without workspace",
            )
            results[f"integer_5000_{kind}_context"] = large_integer_result

        # Build the refresh diff only after import probes, because the fixture
        # deliberately changes its source snapshot to produce a real candidate.
        diff_path = _seed_real_diff_fixture(root, fixture)
        apply_cases = {
            "missing_both_groups": ["knowledge", "apply", "--workspace", str(workspace), "--diff", str(diff_path)],
            "missing_concepts_group": ["knowledge", "apply", "--workspace", str(workspace), "--diff", str(diff_path), "--keep-sections"],
            "missing_sections_group": ["knowledge", "apply", "--workspace", str(workspace), "--diff", str(diff_path), "--keep-concepts"],
            "conflicting_sections": ["knowledge", "apply", "--workspace", str(workspace), "--diff", str(diff_path), "--accept-section", "summary", "--keep-sections", "--keep-concepts"],
            "conflicting_concepts": ["knowledge", "apply", "--workspace", str(workspace), "--diff", str(diff_path), "--keep-sections", "--accept-concepts", "--keep-concepts"],
            "duplicate_section": ["knowledge", "apply", "--workspace", str(workspace), "--diff", str(diff_path), "--accept-section", "summary", "--accept-section", "summary", "--keep-concepts"],
            "unknown_section": ["knowledge", "apply", "--workspace", str(workspace), "--diff", str(diff_path), "--accept-section", "does-not-exist", "--keep-concepts"],
            "valid_explicit_choices": ["knowledge", "apply", "--workspace", str(workspace), "--diff", str(diff_path), "--accept-section", "summary", "--keep-concepts"],
        }
        for name, argv in apply_cases.items():
            result = run_cli(source_root, python, argv)
            if name in {"missing_both_groups", "missing_concepts_group", "missing_sections_group", "conflicting_sections", "conflicting_concepts"}:
                _expect_usage(result, label=name)
            elif name in {"duplicate_section", "unknown_section"}:
                _expect_closed(result, codes={"LIGHT_REFRESH_INVALID", "LIGHT_SELECTION_INVALID", "USAGE"}, label=name)
            else:
                if result["exit_code"] == 2 and result["payload"].get("error", {}).get("code") == "USAGE":
                    _DYNAMIC_FAILURES.append(f"valid apply choices were rejected as USAGE: {result}")
            results[f"apply_{name}"] = result

        return {
            "temporary_root": str(root),
            "workspace": str(workspace),
            "refresh_diff": str(diff_path),
            "harness_path": str(Path(__file__).resolve()),
            "harness_sha256": sha256(Path(__file__).resolve()),
            "candidate_26path_manifest": candidate_26path_manifest(source_root),
            "failures": list(_DYNAMIC_FAILURES),
            "cases": results,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args(argv)
    source_root = args.source_root.expanduser().resolve()
    static = _static_observations(source_root)
    harness_path = Path(__file__).resolve()
    harness_digest = sha256(harness_path)
    report: dict[str, Any] = {
        "schema": "lightweight-research-v1-cli-preacceptance-probe-r3.v1",
        "probe_revision": "R3",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "clock_source": "datetime.now(timezone.utc) on the probe host",
        "scope": "Independent CLI pre-acceptance probe; no product/test/Git/external mutation. Dynamic fixtures are disposable regular files under /private/tmp.",
        "harness_path": str(harness_path),
        "harness_sha256": harness_digest,
        "candidate_26path_manifest": candidate_26path_manifest(source_root),
        "static_observations": static,
        "source_imported_or_executed": False,
        "dynamic_ran": not args.static_only,
    }
    if args.static_only:
        report["decision"] = "BASELINE_OBSERVATIONS_ONLY_DYNAMIC_PROBES_DEFERRED_UNTIL_STOPPED_CANDIDATE"
    else:
        try:
            report["dynamic"] = _run_dynamic(source_root, args.python)
            report["source_imported_or_executed"] = True
            report["decision"] = (
                "PASS_CLI_PREACCEPTANCE_PROBES"
                if not report["dynamic"].get("failures")
                else "FAIL_CLI_PREACCEPTANCE_PROBE"
            )
        except ProbeFailure as exc:
            report["dynamic_failure"] = str(exc)
            report["decision"] = "FAIL_CLI_PREACCEPTANCE_PROBE"
    print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
    return 0 if args.static_only or report["decision"] == "PASS_CLI_PREACCEPTANCE_PROBES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
