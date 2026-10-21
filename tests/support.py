from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


def plant_unix_socket(path: Path) -> socket.socket:
    """Bind at a short same-device path, then move the socket entry to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Both supported CI platforms provide /tmp.  Its spelling stays below the
    # AF_UNIX path limit even when the test runner's TMPDIR is deeply nested.
    short_base=Path("/tmp")
    if not short_base.is_dir():
        raise RuntimeError("short socket temporary directory is unavailable")
    short_root=Path(tempfile.mkdtemp(prefix="vpws-",dir=short_base));short=short_root/"s"
    if os.stat(short_root).st_dev!=os.stat(path.parent).st_dev:
        short_root.rmdir();raise RuntimeError("short socket path is on another filesystem")
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        server.bind(str(short));server.listen(1);os.rename(short,path)
    except BaseException:
        server.close()
        try:short.unlink()
        except OSError:pass
        short_root.rmdir();raise
    short_root.rmdir();return server

PYPROJECT = '[project]\nname = "video-paper-wiki"\n'
ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
DEFAULT_PARSER = {
    "engine": "docling",
    "engine_version": "2.117.0",
    "core_version": "2.92.0",
    "config_sha256": "b" * 64,
    "model_manifest_sha256": "c" * 64,
}


def make_checkout(path: Path) -> Path:
    git = path / ".git"
    if not git.exists():
        git.mkdir()
    pyproject = path / "pyproject.toml"
    if not pyproject.exists():
        pyproject.write_text(PYPROJECT, encoding="utf-8")
    return path


def plant_blob(root: Path, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    dest = Path(root)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / digest
    path.write_bytes(data)
    return digest


def work_plan(root: Path, batch_id: str) -> Path:
    return root / ".work" / batch_id / "plan" / "ingest-plan.v1.json"


def work_prepared(root: Path, batch_id: str, sha256: str) -> Path:
    return root / ".work" / batch_id / "prepared" / f"{sha256}.blob"


def staged_pdf_capture_input(root: Path, *, batch_id: str = "staged-pdf") -> tuple[Path, bytes, dict[str, Any]]:
    """Build one canonical prepared request in a disposable checkout."""
    from video_paper_wiki.approval import approval_ref_sha256, jcs_sha256
    from video_paper_wiki.jcs import canonicalize
    from video_paper_wiki.staged_capture import validate_staged_pdf_capture_request
    from video_paper_wiki.staging import _stage_prepared_pdf_capture, stage_bytes

    data = pdf_bytes()
    digest = hashlib.sha256(data).hexdigest()
    plan = complete_ingest_plan(paper_source_request(batch_id=batch_id, local_sha256=digest))
    plan_bytes = canonicalize(plan)
    stage_bytes(batch_id=batch_id, relative=("plan", "ingest-plan.v1.json"), data=plan_bytes)
    ref = make_approval_ref(plan)
    request = validate_staged_pdf_capture_request({
        "schema": "video-paper-wiki.staged-pdf-capture-request.v1",
        "batch_id": batch_id,
        "plan": {
            "file": "plan/ingest-plan.v1.json", "sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "size_bytes": len(plan_bytes), "approval_hash": plan["approval_hash"],
            "plan_kind": "paper-source", "stable_subject_id": plan["stable_subject_id"],
            "input_kind": plan["input"]["kind"], "limits_sha256": jcs_sha256(plan["limits"]),
            "network_targets_sha256": jcs_sha256(plan["network_targets"]),
            "pipeline_fingerprint": plan["pipeline_fingerprint"],
        },
        "approval_ref": ref, "approval_ref_sha256": approval_ref_sha256(ref),
        "payload": {"file": f"prepared/{digest}.blob", "sha256": digest,
                    "size_bytes": len(data), "media_type": "application/pdf", "page_count": 1},
    })
    result = _stage_prepared_pdf_capture(
        batch_id=batch_id, plan_bytes=plan_bytes,
        plan_identity=os.lstat(work_plan(root, batch_id)),
        blob_name=f"{digest}.blob", blob=data,
        request_factory=lambda: canonicalize(request),
    )
    return result.request_path, data, request


def write_json(path: Path, obj: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def paper_source_request(
    *,
    batch_id: str = "batch-0001",
    local_sha256: str,
    arxiv_id: str = "2311.15127",
    max_pages: int = 200,
    max_bytes: int = 50_000_000,
    **overrides: Any,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": "video-paper-wiki.ingest-plan.v1",
        "plan_kind": "paper-source",
        "batch_id": batch_id,
        "stable_subject_id": f"paper:arxiv:{arxiv_id}",
        "input": {
            "kind": "local-blob",
            "local_sha256": local_sha256,
            "arxiv_id": arxiv_id,
        },
        "limits": {
            "max_pages": max_pages,
            "max_bytes": max_bytes,
            "max_requests": 1,
        },
        "network_targets": [],
        "parser": dict(DEFAULT_PARSER),
    }
    document.update(overrides)
    return document


def code_evidence_request(
    *,
    batch_id: str = "batch-code-1",
    repository: str = "Vchitect/Latte",
    commit: str = "a" * 40,
    source_path: str = "src/model.py",
    max_bytes: int = 50_000_000,
    **overrides: Any,
) -> dict[str, Any]:
    from video_paper_wiki.identity import repo_subject_id

    document: dict[str, Any] = {
        "schema": "video-paper-wiki.ingest-plan.v1",
        "plan_kind": "code-evidence",
        "batch_id": batch_id,
        "stable_subject_id": repo_subject_id(repository),
        "input": {
            "kind": "github-repo",
            "repository": repository,
            "commit": commit,
            "source_path": source_path,
        },
        "limits": {
            "max_bytes": max_bytes,
            "max_requests": 1,
        },
        "network_targets": [],
        "parser": dict(DEFAULT_PARSER),
    }
    document.update(overrides)
    return document


def complete_ingest_plan(request: dict[str, Any]) -> dict[str, Any]:
    from video_paper_wiki.contracts import validate_document
    from video_paper_wiki.identity import pipeline_fingerprint, plan_approval_hash

    plan = deepcopy(request)
    plan.pop("approval_hash", None)
    plan.pop("pipeline_fingerprint", None)
    plan["pipeline_fingerprint"] = pipeline_fingerprint(plan["parser"])
    plan["approval_hash"] = plan_approval_hash(plan)
    validate_document(plan, expected_schema="video-paper-wiki.ingest-plan.v1")
    return plan


def make_approval_ref(plan: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    from video_paper_wiki.approval import jcs_sha256
    from video_paper_wiki.identity import pipeline_fingerprint

    source = plan.get("input") if isinstance(plan.get("input"), dict) else {}
    input_sha256 = overrides.pop("input_sha256", source.get("local_sha256"))
    ref = {
        "format": "video-paper-wiki.approval-ref.v1",
        "plan_approval_hash": plan["approval_hash"],
        "plan_kind": plan["plan_kind"],
        "batch_id": plan["batch_id"],
        "stable_subject_id": plan["stable_subject_id"],
        "input_sha256": input_sha256,
        "limits_sha256": jcs_sha256(plan["limits"]),
        "network_targets_sha256": jcs_sha256(plan["network_targets"]),
        "pipeline_fingerprint": plan.get("pipeline_fingerprint")
        or pipeline_fingerprint(plan["parser"]),
    }
    ref.update(overrides)
    return ref


def pdf_bytes(*, pages: int = 1, encrypt: bool = False) -> bytes:
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if encrypt:
        writer.encrypt("secret")
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def work_draft(root: Path, batch_id: str) -> Path:
    return root / ".work" / batch_id / "draft" / "paper-analysis-draft.v1.json"


def work_review(root: Path, batch_id: str) -> Path:
    return root / ".work" / batch_id / "review" / "paper.md"


def write_catalog_paper_note(root: Path, paper_id: str, title: str | None = None) -> Path:
    from video_paper_wiki.notes import paper_note_link_suffix, render_paper_copy_markdown
    from video_paper_wiki.parse.title import catalog_title_for_paper_id

    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    document["title"] = title or catalog_title_for_paper_id(paper_id) or paper_id
    text = render_paper_copy_markdown(document) + paper_note_link_suffix(paper_id)
    path = root / "papers" / f"{paper_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
