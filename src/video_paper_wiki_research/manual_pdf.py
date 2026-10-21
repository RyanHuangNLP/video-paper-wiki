"""Safe local PDF intake and optional ingest-plan handoff.

Internal helpers: existing identity, pypdf page counting (same semantics as
prepare), plan builder/stager, and stage_bytes. This command never creates an
approval-ref and is not a receipt-backed capture.
"""

from __future__ import annotations

import os
import stat
from io import BytesIO
from pathlib import Path
from typing import Any

from video_paper_wiki.commands.plan import _build_plan
from video_paper_wiki.identity import (
    IdentityError,
    establish_canonical_paper_id,
    paper_id_from_pdf_sha256,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SOURCE_CHANGED, SecureIOError, is_special, read_regular_file, stamp
from video_paper_wiki.staging import StagingError, stage_bytes, validate_batch_id

from video_paper_wiki_research.contracts import (
    INTAKE_BINDING_MISMATCH,
    INTAKE_INVALID,
    MANUAL_PDF_CHANGED,
    MANUAL_PDF_INVALID,
    PDF_MAGIC,
    PDF_MAX_BYTES,
    PDF_MAX_PAGES,
    PARSER_PROFILE_INVALID,
    ResearchError,
    exact_ref,
    seal_document,
    sha256_bytes,
)
from video_paper_wiki_research.parser_profile import load_profile
from video_paper_wiki_research.storage import (
    RetainedResearchSession,
    RetainedSource,
    load_saved_document,
    session_from_research_path,
    stage_blob,
    write_document,
)


def _pdf_page_count(data: bytes) -> int:
    try:
        from pypdf import PdfReader
        from pypdf.errors import FileNotDecryptedError, PdfReadError, PdfStreamError
    except ImportError as exc:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF parser is unavailable") from exc
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, PdfStreamError, OSError, ValueError) as exc:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF is not parseable") from exc
    except Exception as exc:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF is not parseable") from exc
    if bool(getattr(reader, "is_encrypted", False)):
        raise ResearchError(MANUAL_PDF_INVALID, "PDF is encrypted")
    try:
        pages = len(reader.pages)
    except FileNotDecryptedError as exc:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF is encrypted") from exc
    except Exception as exc:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF is not parseable") from exc
    if pages < 1:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF has no pages")
    if pages > PDF_MAX_PAGES:
        raise ResearchError(
            MANUAL_PDF_INVALID,
            "PDF page count exceeds 300",
            {"page_count": pages, "max_pages": PDF_MAX_PAGES},
        )
    return pages


def _original_name(path: Path) -> str:
    name = path.name
    encoded = name.encode("utf-8")
    if not name or len(encoded) > 255:
        raise ResearchError(MANUAL_PDF_INVALID, "original_name must be a 1-255 UTF-8-byte basename")
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise ResearchError(MANUAL_PDF_INVALID, "original_name must not contain a host path")
    if any(ord(char) < 32 for char in name):
        raise ResearchError(MANUAL_PDF_INVALID, "original_name must not contain control characters")
    return name


def retain_pdf(path: Path) -> RetainedSource:
    target = path if path.is_absolute() else Path.cwd() / path
    try:
        first = os.lstat(target)
    except OSError as exc:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF path does not exist", {"path": target.as_posix()}) from exc
    if stat.S_ISLNK(first.st_mode):
        raise ResearchError(MANUAL_PDF_INVALID, "PDF path must not be a symlink")
    if is_special(first) or not stat.S_ISREG(first.st_mode):
        raise ResearchError(MANUAL_PDF_INVALID, "PDF path must be a regular file")
    if first.st_nlink != 1:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF path must have exactly one link")
    if first.st_size > PDF_MAX_BYTES:
        raise ResearchError(MANUAL_PDF_INVALID, "PDF exceeds 64 MiB")
    try:
        data = read_regular_file(
            target,
            missing_code=MANUAL_PDF_INVALID,
            unsafe_code=MANUAL_PDF_INVALID,
            changed_code=SOURCE_CHANGED,
            max_bytes=PDF_MAX_BYTES,
            limit_code=MANUAL_PDF_INVALID,
        )
    except SecureIOError as exc:
        if exc.code == SOURCE_CHANGED:
            raise ResearchError(MANUAL_PDF_CHANGED, str(exc.message), dict(exc.details), exit_code=75) from exc
        raise ResearchError(MANUAL_PDF_INVALID, str(exc.message), dict(exc.details)) from exc
    after = os.lstat(target)
    if stamp(after) != stamp(first) or after.st_nlink != 1:
        raise ResearchError(MANUAL_PDF_CHANGED, "PDF identity changed while read")
    if not data.startswith(PDF_MAGIC):
        raise ResearchError(MANUAL_PDF_INVALID, "PDF must start with %PDF-")
    digest = sha256_bytes(data)
    source = RetainedSource(target, first, digest, data)
    source.verify()
    return source


def _session_bindings(session: RetainedResearchSession) -> list[tuple[str, str]]:
    root = session.path("intakes")
    if not root.exists():
        return []
    bindings: list[tuple[str, str]] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or not path.name.endswith(".json"):
            continue
        document, _raw = load_saved_document(path, kind="intake", invalid_code=INTAKE_INVALID)
        bindings.append((str(document["data"]["paper_id"]), str(document["data"]["pdf_sha256"])))
    return bindings


def intake_pdf(session: RetainedResearchSession, pdf_path: Path, *, paper_id: str | None) -> dict[str, Any]:
    source = retain_pdf(pdf_path)
    try:
        pages = _pdf_page_count(source.data)
        source.verify()
        try:
            if paper_id:
                canonical, _aliases = establish_canonical_paper_id(
                    existing_paper_id=paper_id,
                    pdf_sha256=source.digest,
                )
                provided: str | None = canonical
            else:
                canonical = paper_id_from_pdf_sha256(source.digest)
                provided = None
        except IdentityError as exc:
            raise ResearchError(str(exc.code), str(exc.message), dict(exc.details), exit_code=int(exc.exit_code)) from exc
        for bound_id, bound_sha in _session_bindings(session):
            if bound_id == canonical and bound_sha != source.digest:
                raise ResearchError(INTAKE_BINDING_MISMATCH, "paper ID is already bound to a different PDF")
            if bound_sha == source.digest and bound_id != canonical:
                raise ResearchError(INTAKE_BINDING_MISMATCH, "PDF is already bound to a different paper ID")
        data = {
            "paper_id": canonical,
            "pdf_sha256": source.digest,
            "size_bytes": len(source.data),
            "page_count": pages,
            "media_type": "application/pdf",
            "blob_path": f".work/blobs/{source.digest}",
            "original_name": _original_name(source.path),
            "provided_identity": provided,
        }
        document = seal_document("intake", data)
        source.verify()
        session.verify()
        blob = stage_blob(source.digest, source.data)
        staged, ref = write_document(session, "intakes", document)
        source.verify()
        session.verify()
        return {
            "intake": document,
            "ref": ref,
            "path": staged.path.as_posix(),
            "blob_path": blob.path.as_posix(),
            "already_staged": staged.already_staged,
            "next_action": "awaiting_parser_profile",
            "state": "staged_input",
            "capture_authorized": False,
            "receipt_backed": False,
            "published": False,
        }
    except BaseException as exc:
        try:
            session.verify()
            source.verify()
        except StagingError as unsafe:
            raise unsafe from exc
        except ResearchError:
            raise
        raise


def load_intake(path: Path) -> tuple[str, dict[str, Any], bytes]:
    session_id = session_from_research_path(path, kind_dir="intakes")
    document, raw = load_saved_document(path, kind="intake", invalid_code=INTAKE_INVALID)
    return session_id, document, raw


def plan_handoff(
    session: RetainedResearchSession,
    intake_path: Path,
    profile_path: Path,
    batch_id: object,
) -> dict[str, Any]:
    try:
        batch = validate_batch_id(batch_id)
    except StagingError as exc:
        raise ResearchError(INTAKE_INVALID, "batch-id is not a legal staging batch id", dict(exc.details)) from exc
    _session, intake, intake_raw = load_intake(intake_path)
    if _session != session.session_id:
        raise ResearchError(INTAKE_INVALID, "intake does not belong to this session")
    profile, profile_raw = load_profile(profile_path)
    profile_session = session_from_research_path(profile_path, kind_dir="profile")
    if profile_session != session.session_id:
        raise ResearchError(PARSER_PROFILE_INVALID, "profile does not belong to this session")
    blob = session.checkout / ".work" / "blobs" / intake["data"]["pdf_sha256"]
    try:
        blob_bytes = read_regular_file(
            blob,
            missing_code=INTAKE_INVALID,
            unsafe_code=INTAKE_INVALID,
            changed_code=SOURCE_CHANGED,
            max_bytes=PDF_MAX_BYTES,
            limit_code=INTAKE_INVALID,
        )
    except SecureIOError as exc:
        raise ResearchError(INTAKE_INVALID, "intake blob is missing or unsafe", dict(exc.details)) from exc
    if sha256_bytes(blob_bytes) != intake["data"]["pdf_sha256"]:
        raise ResearchError(INTAKE_INVALID, "intake blob digest differs")
    request = {
        "schema": "video-paper-wiki.ingest-plan.v1",
        "plan_kind": "paper-source",
        "batch_id": batch,
        "stable_subject_id": "paper:" + intake["data"]["paper_id"],
        "input": {"kind": "local-blob", "local_sha256": intake["data"]["pdf_sha256"]},
        "limits": {"max_pages": PDF_MAX_PAGES, "max_bytes": PDF_MAX_BYTES, "max_requests": 1},
        "network_targets": [],
        "parser": profile["data"]["parser"],
    }
    plan = _build_plan(request, "paper-source")
    payload = canonicalize(plan)
    staged = stage_bytes(batch_id=batch, relative=("plan", "ingest-plan.v1.json"), data=payload)
    session.verify()
    return {
        "plan": plan,
        "plan_path": staged.path.as_posix(),
        "plan_sha256": sha256_bytes(payload),
        "intake": exact_ref(intake),
        "profile": exact_ref(profile),
        "already_staged": staged.already_staged,
        "next_action": "awaiting_external_approval_ref",
        "capture_authorized": False,
        "receipt_backed": False,
        "published": False,
        "note": "real capture requires the later genesis/admission workflow; this plan is not an approval-ref",
    }
