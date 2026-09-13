"""Legal test-facility helpers for the isolated fixture-Vault publication chain."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from tests.research.conftest import UPSTREAM
from tests.research.test_source_admission import apply_capture, apply_publication, bootstrap_genesis
from tests.support import (
    DEFAULT_PARSER,
    complete_ingest_plan,
    make_approval_ref,
    work_plan,
)
from video_paper_wiki.approval import approval_ref_sha256, jcs_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.publication import inspect_publication, prepare_publication_source
from video_paper_wiki.staged_capture import inspect_staged_pdf_capture, validate_staged_pdf_capture_request
from video_paper_wiki.staging import _stage_prepared_pdf_capture, stage_bytes
from video_paper_wiki_research.publication_bridge import (
    bind_capture_operation,
    bridge_publication,
)
from video_paper_wiki_research.source_admission import admit_source


def inspection_changed_paths(authority: Mapping[str, Any]) -> list[str]:
    candidates = (
        authority.get("transaction", {}).get("inspection", {}).get("changed_paths"),
        authority.get("upstream_authority", {}).get("transaction", {}).get("inspection", {}).get("changed_paths"),
        authority.get("inspection", {}).get("changed_paths"),
    )
    for value in candidates:
        if type(value) is list and all(type(item) is str for item in value):
            return list(value)
    raise AssertionError("inspected transaction does not name changed paths")


def read_vault_file_state(vault: Path, paths: Sequence[str]) -> dict[str, dict[str, object] | None]:
    """Read live Vault file bytes/mode. Missing paths are None."""
    state: dict[str, dict[str, object] | None] = {}
    for relative in paths:
        target = vault / relative
        try:
            first = target.lstat()
        except FileNotFoundError:
            state[relative] = None
            continue
        if stat.S_ISLNK(first.st_mode) or not stat.S_ISREG(first.st_mode):
            state[relative] = None
            continue
        data = target.read_bytes()
        state[relative] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "mode": stat.S_IMODE(first.st_mode),
        }
    return state


def capture_pdf_bytes(checkout: Path, vault: Path, pdf: bytes, *, batch_id: str) -> dict[str, Any]:
    """Stage and apply a capture of the exact intake PDF through the test apply helper."""
    digest = hashlib.sha256(pdf).hexdigest()
    paper_id = "sha256:" + digest
    plan = complete_ingest_plan(
        {
            "schema": "video-paper-wiki.ingest-plan.v1",
            "plan_kind": "paper-source",
            "batch_id": batch_id,
            "stable_subject_id": "paper:" + paper_id,
            "input": {"kind": "local-blob", "local_sha256": digest},
            "limits": {"max_pages": 200, "max_bytes": 50_000_000, "max_requests": 1},
            "network_targets": [],
            "parser": dict(DEFAULT_PARSER),
        }
    )
    plan_bytes = canonicalize(plan)
    stage_bytes(batch_id=batch_id, relative=("plan", "ingest-plan.v1.json"), data=plan_bytes)
    ref = make_approval_ref(plan, input_sha256=digest)
    request = validate_staged_pdf_capture_request(
        {
            "schema": "video-paper-wiki.staged-pdf-capture-request.v1",
            "batch_id": batch_id,
            "plan": {
                "file": "plan/ingest-plan.v1.json",
                "sha256": hashlib.sha256(plan_bytes).hexdigest(),
                "size_bytes": len(plan_bytes),
                "approval_hash": plan["approval_hash"],
                "plan_kind": "paper-source",
                "stable_subject_id": plan["stable_subject_id"],
                "input_kind": plan["input"]["kind"],
                "limits_sha256": jcs_sha256(plan["limits"]),
                "network_targets_sha256": jcs_sha256(plan["network_targets"]),
                "pipeline_fingerprint": plan["pipeline_fingerprint"],
            },
            "approval_ref": ref,
            "approval_ref_sha256": approval_ref_sha256(ref),
            "payload": {
                "file": f"prepared/{digest}.blob",
                "sha256": digest,
                "size_bytes": len(pdf),
                "media_type": "application/pdf",
                "page_count": 1,
            },
        }
    )
    staged = _stage_prepared_pdf_capture(
        batch_id=batch_id,
        plan_bytes=plan_bytes,
        plan_identity=os.lstat(work_plan(checkout, batch_id)),
        blob_name=f"{digest}.blob",
        blob=pdf,
        request_factory=lambda: canonicalize(request),
    )
    authority = inspect_staged_pdf_capture(
        prepared=staged.request_path,
        operation_id=batch_id,
        upstream_root=UPSTREAM,
        vault_root=vault,
    )
    paths = inspection_changed_paths(authority)
    before = read_vault_file_state(vault, paths)
    applied = apply_capture(checkout, vault, authority)
    after = read_vault_file_state(vault, applied["changed_paths"])
    stored = authority["inspection"]["stored_path"]
    bound = bind_capture_operation(
        inspected_transaction=authority["upstream_authority"]["transaction"],
        apply_result=applied,
        vault_before=before,
        vault_after=after,
        expected_pdf_sha256=digest,
        stored_path=stored,
    )
    return {
        "authority": authority,
        "applied": applied,
        "bound": bound,
        "stored_path": stored,
        "before": before,
        "after": after,
        "digest": digest,
    }


def apply_inspected_publication(checkout: Path, vault: Path, *, request_path: str, operation_id: str, batch_id: str) -> dict[str, Any]:
    prepare_publication_source(request_path=request_path, batch_id=batch_id)
    inspected = inspect_publication(
        prepared=request_path,
        operation_id=operation_id,
        upstream_root=UPSTREAM,
        vault_root=vault,
    )
    applied = apply_publication(checkout, vault, inspected)
    return {"inspected": inspected, "applied": applied}


def load_saved_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
