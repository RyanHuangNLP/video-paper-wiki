"""Architect's independent local acceptance probes, not product implementation.

Run only against a stopped owner handoff. All mutations are disposable fixtures.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--handoff", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
source = args.source.resolve()
handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
sys.path[:0] = [str(source / "src"), str(source)]

from tests.research.test_light_index import SHA_A, _write_paper
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import (
    export_context, import_document, render_document, validate_live_context,
)
from video_paper_wiki_research.light_index import build_index
from video_paper_wiki_research.light_query import export_rewritten_context
from video_paper_wiki_research.light_workflow import _workspace_lock_path


def verify_source() -> None:
    for item in handoff["files"]:
        data = (source / item["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
        assert len(data) == item["size_bytes"], item["path"]
        assert data == (args.handoff.parent / "files" / item["path"]).read_bytes()


def invoke(fn, *pos, **kwargs):
    try:
        return fn(*pos, **kwargs)
    except ResearchError as exc:
        return {"ok": False, "status": exc.code, "message": exc.message,
                "closed_research_error": True}
    except Exception as exc:
        return {"ok": False, "exception": type(exc).__name__, "message": str(exc)}


def compact(result):
    return {key: result[key] for key in ("ok", "status", "message", "exception",
                                        "closed_research_error") if key in result}


def make_workspace(path):
    path.mkdir(parents=True)
    _write_paper(path, SHA_A, "Alpha", ["Quasar evidence explains spatial temporal attention."])
    result = build_index(path)
    assert result["ok"], result
    return path


def rewritten(ws, query="中文问题", english="spatial temporal attention", paper_ids=None):
    return invoke(export_rewritten_context, ws, kind="qa", query=query,
                  rewrite={"schema": "video-paper-wiki.light-query-rewrite.v1",
                           "original_query": query, "rewritten_query": english,
                           "language": "en"}, paper_ids=paper_ids)


rows = []


def record(name, result, *, success=False, status=None, preserved=True):
    passed = ("exception" not in result and result.get("ok") is success and preserved
              and (status is None or result.get("status") == status))
    rows.append({"case": name, "passed": passed, "expected_success": success,
                 "expected_status": status, "preexisting_output_preserved": preserved,
                 "result": compact(result)})


verify_source()
with tempfile.TemporaryDirectory(prefix="t1acc.", dir="/private/tmp") as temp:
    tmp = Path(temp)
    ws = make_workspace(tmp / "real" / ".work" / "ws")
    context = rewritten(ws)
    record("normal_rewritten_export", context, success=True, status="OK")
    if context.get("ok"):
        citation = context["evidence"][0]["chunk_id"]
        document = {"text": f"Local fixture evidence [@{citation}]",
                    "citations": [{"chunk_id": citation}]}
        output = tmp / ".work" / "reports" / "answer.md"
        output.parent.mkdir(parents=True)
        record("normal_rewritten_import", invoke(import_document, ws, context, document,
                                                   output=output), success=True, status="OK")

        mutations = [
            ("list_route_status", lambda c: c["query_plan"]["routes"][0].update(status=[])),
            ("object_route_status", lambda c: c["query_plan"]["routes"][0].update(status={})),
            ("huge_route_score", lambda c: c["query_plan"]["routes"][-1]["candidates"][0].update(score=10**400)),
            ("huge_fused_score", lambda c: c["query_plan"]["fused"][0].update(score=10**400)),
            ("huge_evidence_score", lambda c: c["evidence"][0].update(score=10**400)),
            ("surrogate_trace_query", lambda c: c["query_plan"]["rewrite"].update(rewritten_query="quasar\ud800")),
        ]
        sentinel = b"Existing user output must survive refusal.\n"
        for name, mutate in mutations:
            altered = copy.deepcopy(context)
            mutate(altered)
            for operation in (validate_live_context, render_document, import_document):
                output.write_bytes(sentinel)
                result = invoke(operation, ws, altered, **{}) if operation is validate_live_context else invoke(
                    operation, ws, altered, document, output=output)
                record(name + ":" + operation.__name__, result,
                       status="LIGHT_CONTEXT_INVALID", preserved=output.read_bytes() == sentinel)

        alias = tmp / "alias"
        alias.symlink_to(tmp / "real", target_is_directory=True)
        given = alias / ".work" / "ws"
        record("symlink_parent_export", rewritten(given))
        for operation in (validate_live_context, render_document, import_document):
            output.write_bytes(sentinel)
            result = invoke(operation, given, context) if operation is validate_live_context else invoke(
                operation, given, context, document, output=output)
            record("symlink_parent:" + operation.__name__, result,
                   preserved=output.read_bytes() == sentinel)

        for filename in ("source.md", "source.json"):
            original = ws / "papers" / SHA_A / filename
            hardlink = tmp / (filename + ".hardlink")
            os.link(original, hardlink)
            record("hardlinked_" + filename + ":export", rewritten(ws))
            for operation in (validate_live_context, render_document, import_document):
                output.write_bytes(sentinel)
                result = invoke(operation, ws, context) if operation is validate_live_context else invoke(
                    operation, ws, context, document, output=output)
                record("hardlinked_" + filename + ":" + operation.__name__, result,
                       preserved=output.read_bytes() == sentinel)
            hardlink.unlink()

    record("duplicate_selection", rewritten(ws, paper_ids=["sha256:" + SHA_A] * 2),
           status="LIGHT_SELECTION_INVALID")
    record("surrogate_original_query", rewritten(ws, query="\ud800"), status="QUERY_REWRITE_INVALID")
    record("surrogate_rewritten_query", rewritten(ws, english="quasar\ud800"), status="QUERY_REWRITE_INVALID")
    lock_path = _workspace_lock_path(ws)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as held_lock:
        fcntl.flock(held_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        record("occupied_workspace_lock", rewritten(ws), status="LIGHT_WORKSPACE_BUSY")

    bare = make_workspace(tmp / "outside_workspace")
    record("workspace_without_work_component", rewritten(bare))
    record("untraced_legacy_export", invoke(export_context, bare, kind="qa", query="quasar"),
           success=True, status="OK")

    for kind in ("papers_root", "paper_directory"):
        empty = tmp / ".work" / kind
        empty.mkdir(parents=True)
        target = tmp / (kind + "_target")
        target.mkdir()
        link = empty / "papers" if kind == "papers_root" else empty / "papers" / SHA_A
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target, target_is_directory=True)
        # The unchanged legacy producer may skip these edges. The new route
        # must still refuse instead of certifying an empty source snapshot.
        build_index(empty)
        result = rewritten(empty)
        record(kind + "_symlink_no_results", result)
        rows[-1]["passed"] = rows[-1]["passed"] and result.get("status") != "NO_RESULTS"

verify_source()
report = {"schema": "lightweight-research-t1-independent-acceptance.v1",
          "at_utc": datetime.now(timezone.utc).isoformat(), "source": str(source),
          "snapshot_sha256": handoff["snapshot_sha256"],
          "verified_source_and_copies_before_after": True,
          "passed": sum(row["passed"] for row in rows), "total": len(rows),
          "cases": rows, "note": "Synthetic disposable fixtures only; no source/Git/external edits."}
assert not args.report.exists()
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2) + "\n")
print(json.dumps({"passed": report["passed"], "total": report["total"],
                  "failures": [row for row in rows if not row["passed"]]}, ensure_ascii=True))
raise SystemExit(0 if report["passed"] == report["total"] else 1)
