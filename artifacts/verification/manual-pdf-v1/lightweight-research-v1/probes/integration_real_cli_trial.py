"""Replay reviewed real-paper artifacts through a stopped integrated CLI.

This is an engineering replay of existing model-authored documents, not new
model generation. Outputs and the report are immutable per invocation folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tree(path):
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--handoff", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root, source, out = args.root.resolve(), args.source.resolve(), args.output.resolve()
    handoff = read(args.handoff)
    assert handoff["stopped_writing"] is True
    for row in handoff["files"]:
        assert sha(source / row["path"]) == row["sha256"], row["path"]
    out.mkdir(parents=True, exist_ok=False)
    trial = root / ".work/trials/lightweight-research-v1"
    ws = trial / "workspace"
    env = dict(os.environ, PYTHONPATH=str(source / "src"), PYTHONDONTWRITEBYTECODE="1",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never")
    calls = []
    report = {"schema": "lightweight-research-real-cli-trial.v1",
              "at_utc": datetime.now(timezone.utc).isoformat(), "source": str(source),
              "handoff_sha256": sha(args.handoff), "calls": calls,
              "authorship": "CLI replay of previously exported and independently reviewed actual-paper current-model documents; no model generation by this script.",
              "human_scientific_acceptance": False}

    def call(name, argv, *, success=True, status=None):
        cmd = [sys.executable, "-c", "from video_paper_wiki_research.cli import main; raise SystemExit(main())", *map(str, argv)]
        p = subprocess.run(cmd, cwd=source, env=env, text=True, capture_output=True)
        (out / (name + ".json")).write_text(p.stdout, encoding="utf-8")
        (out / (name + ".stderr")).write_text(p.stderr, encoding="utf-8")
        payload = json.loads(p.stdout)
        item = {"name": name, "command": cmd, "exit_code": p.returncode,
                "stdout_sha256": sha(out / (name + ".json")), "status": payload.get("status"),
                "ok": payload.get("ok"), "traceback": "Traceback" in p.stderr}
        calls.append(item)
        assert payload.get("ok") is success and (p.returncode == 0) is success, item
        assert not item["traceback"], item
        if status is not None:
            assert payload["status"] == status, item
        return payload

    def links(path):
        count = 0
        for href in re.findall(r"\]\(([^\n)]+source\.md#page-\d+)\)", path.read_text()):
            rel, anchor = href.rsplit("#", 1)
            target = (path.parent / rel).resolve()
            assert target.is_file() and f'id="{anchor}"' in target.read_text(), href
            count += 1
        assert count > 0, path
        return count

    original_pdfs = read(root / "artifacts/verification/manual-pdf-v1/lightweight-research-v1/batch-three-paper-trial-r1.json")["original_pdfs_verified_unchanged"]
    notes_before = {str(p.relative_to(ws)): sha(p) for p in ws.rglob("notes.md")}
    writing_before = tree(ws / ".light-writing")
    try:
        for name in ("svd-training-curation", "vdm-spatial-temporal", "vbench-evaluation", "vbench-human-alignment"):
            rewrite_path = trial / "queries" / (name + ".rewrite.json")
            expected = read(trial / "queries" / (name + ".rewritten-r3.json"))
            selected = expected["paper_ids"]
            argv = ["qa", "export", "--workspace", ws, "--question", read(rewrite_path)["original_query"], "--rewrite", rewrite_path]
            for pid in selected:
                argv += ["--paper-id", pid]
            actual = call(name + ".export", argv)
            assert actual == expected, name
            answer_path = out / (name + ".md")
            call(name + ".import", ["qa", "import", "--workspace", ws, "--context", out / (name + ".export.json"), "--answer", trial / "answers" / (name + ".model-document.json"), "--output", answer_path])
            report.setdefault("qa_links", {})[name] = links(answer_path)

        batch_info = read(root / "artifacts/verification/manual-pdf-v1/lightweight-research-v1/batch-three-paper-trial-r1.json")
        for row in batch_info["papers"]:
            actual = call(row["paper"] + ".batch-status", ["knowledge", "batch-status", "--workspace", ws, "--plan-id", row["plan_id"]])
            report.setdefault("batch_statuses", {})[row["paper"]] = actual

        project = read(trial / "writing/project-export-result.json")["project_id"]
        history = call("writing.history", ["writing", "history", "--workspace", ws, "--project-id", project])
        assert len(history["revisions"]) == 4
        exported = call("writing.project-export", ["writing", "project-export", "--workspace", ws, "--project-id", project, "--output", out / "writing.md"])
        assert exported["progress"]["complete"] is True
        report["writing_links"] = links(out / "writing.md")
        retry = call("writing.section-exact-retry", ["writing", "section-import", "--workspace", ws, "--context", trial / "writing/s1.edit-wrapper.json", "--document", trial / "writing/s1.edit-model-document.json"])
        assert retry["reused"] is True and retry["revision_id"] == history["head_revision_id"]
        selected_ws = trial / "refresh/selected/workspace"
        selected_apply = call("refresh.selected-exact-retry", ["knowledge", "apply", "--workspace", selected_ws, "--diff", trial / "refresh/selected/diff.json", "--accept-section", "architecture", "--keep-concepts"])
        assert selected_apply["reused"] is True

        archive = out / "research.zip"
        create = call("backup.create", ["backup", "create", "--workspace", ws, "--output", archive])
        verified = call("backup.verify", ["backup", "verify", "--archive", archive])
        assert create["manifest_sha256"] == verified["manifest_sha256"]
        destination = out / "restored-workspace"
        restored = call("backup.restore", ["backup", "restore", "--archive", archive, "--destination", destination])
        assert tree(destination / ".light-writing") == writing_before
        assert {str(p.relative_to(destination)): sha(p) for p in destination.rglob("notes.md")} == notes_before
        assert not list(destination.rglob("*.pdf"))
        relocated = call("writing.restored-history", ["writing", "history", "--workspace", destination, "--project-id", project])
        assert len(relocated["revisions"]) == 4 and all(r["source_status"] == "historical" for r in relocated["revisions"])
        call("writing.restored-live-refusal", ["writing", "project-export", "--workspace", destination, "--project-id", project, "--output", out / "relocated-live.md"], success=False, status="LIGHT_WORKSPACE_MISMATCH")
        assert not (out / "relocated-live.md").exists()
        call("backup.restored-history", ["backup", "create", "--workspace", destination, "--output", out / "restored-history.zip"])
        pending = trial / "writing/pending-publication/workspace"
        pending_before = tree(pending)
        pending_result = call("backup.pending-refusal", ["backup", "create", "--workspace", pending, "--output", out / "pending.zip"], success=False)
        assert pending_result["status"] == "LIGHT_BACKUP_CONFLICT" and not (out / "pending.zip").exists()
        assert tree(pending) == pending_before
        assert tree(ws / ".light-writing") == writing_before
        assert {str(p.relative_to(ws)): sha(p) for p in ws.rglob("notes.md")} == notes_before
        for row in original_pdfs:
            assert sha(row["path"]) == row["sha256"]
        for row in handoff["files"]:
            assert sha(source / row["path"]) == row["sha256"]
        report.update(passed=True, unchanged_original_pdfs=True, unchanged_notes=True,
                      intact_writing_history=True, backup_archive_sha256=sha(archive),
                      restored=restored, processing_not_scientific_completeness=True)
    except BaseException as exc:
        report.update(passed=False, error=repr(exc))
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "commands": len(calls), "report": str(out / "report.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
