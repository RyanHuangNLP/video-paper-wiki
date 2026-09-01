"""Stage a local blob bound to a plan and external approval-ref. Zero network."""

from __future__ import annotations

import os
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

from video_paper_wiki.approval import (
    APPROVAL_REF_INVALID,
    ApprovalError,
    bind_approval_ref,
    jcs_sha256,
    parse_approval_ref,
    require_pipeline_fingerprint,
)
from video_paper_wiki.blob_store import BlobStore, resolve_blob_root
from video_paper_wiki.contracts import (
    MAX_BYTES as HARD_MAX_BYTES,
    MAX_PAGES as HARD_MAX_PAGES,
    SCHEMA_INVALID,
    ContractError,
    validate_document,
)
from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.identity import IdentityError
from video_paper_wiki.jcs import CanonicalJsonError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import (
    APPROVAL_REF_NOT_FOUND,
    PLAN_NOT_FOUND,
    PLAN_PATH_UNSAFE,
    SOURCE_CHANGED,
    SecureIOError,
    load_strict_json,
)
from video_paper_wiki.staging import (
    StagingError,
    resolve_checkout_root,
    _stage_prepared_pdf_capture,
    stage_bytes,
    validate_batch_id,
)

PLAN_SCHEMA = "video-paper-wiki.ingest-plan.v1"
PLAN_FILENAME = "ingest-plan.v1.json"
PLAN_KIND_MISMATCH = "PLAN_KIND_MISMATCH"
MEDIA_TYPE_INVALID = "MEDIA_TYPE_INVALID"
PDF_INVALID = "PDF_INVALID"
PAGE_LIMIT_EXCEEDED = "PAGE_LIMIT_EXCEEDED"
PDF_MAGIC = b"%PDF-"
FAMILY_KIND = {"ingest": "paper-source", "code-map": "code-evidence"}


class PrepareError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


def _command_name(family: str) -> str:
    return "ingest.prepare" if family == "ingest" else "code-map.prepare"


def _emit(command: str, exc: BaseException) -> int:
    if isinstance(exc, StagingError):
        return emit_staging_error(command, exc)
    code = str(getattr(exc, "code", "USAGE"))
    message = str(getattr(exc, "message", exc))
    details = dict(getattr(exc, "details", {}) or {})
    exit_code = int(getattr(exc, "exit_code", 2))
    return emit_error(command, code, message, details, exit_code=exit_code)


def _prescribed_batch(checkout: Path, raw: str) -> str:
    actual = os.path.normpath(os.path.abspath(os.fspath(raw)))
    checkout_abs = os.path.normpath(os.path.abspath(os.fspath(checkout)))
    work = os.path.normpath(os.path.join(checkout_abs, ".work"))
    prefix = work + os.sep
    if actual == work or not actual.startswith(prefix):
        raise SecureIOError(
            PLAN_PATH_UNSAFE,
            "plan path is outside the prescribed .work location",
            {"path": actual},
        )
    rest = actual[len(prefix) :]
    parts = rest.split(os.sep)
    if len(parts) != 3 or parts[1] != "plan" or parts[2] != PLAN_FILENAME:
        raise SecureIOError(
            PLAN_PATH_UNSAFE,
            "plan path is outside the prescribed .work location",
            {"path": actual},
        )
    try:
        return validate_batch_id(parts[0])
    except StagingError as exc:
        raise SecureIOError(
            PLAN_PATH_UNSAFE,
            "plan path is outside the prescribed .work location",
            {"path": actual, "batch_id": parts[0]},
        ) from exc


def _load_prescribed_plan(checkout: Path, raw: str) -> dict[str, Any]:
    batch_from_path = _prescribed_batch(checkout, raw)
    target = checkout / ".work" / batch_from_path / "plan" / PLAN_FILENAME
    document = load_strict_json(
        target,
        missing_code=PLAN_NOT_FOUND,
        unsafe_code=PLAN_PATH_UNSAFE,
        invalid_code=SCHEMA_INVALID,
        changed_code=SOURCE_CHANGED,
    )
    if not isinstance(document, dict):
        raise ContractError(SCHEMA_INVALID, "plan must be a JSON object", {"path": target.as_posix()})
    validate_document(document, expected_schema=PLAN_SCHEMA)
    batch = validate_batch_id(document.get("batch_id"))
    if batch != batch_from_path:
        raise SecureIOError(
            PLAN_PATH_UNSAFE,
            "plan path does not match plan batch_id",
            {"path": target.as_posix()},
        )
    return document


def _load_paper_plan_with_identity(checkout: Path, raw: str) -> tuple[dict[str, Any], os.stat_result]:
    target = checkout / ".work" / _prescribed_batch(checkout, raw) / "plan" / PLAN_FILENAME
    try:
        before = os.lstat(target)
    except OSError:
        # Preserve the accepted missing/unsafe classification from the secure loader.
        _load_prescribed_plan(checkout, raw)
        raise SecureIOError(SOURCE_CHANGED, "plan changed while read", {"path": target.as_posix()}) from None
    document = _load_prescribed_plan(checkout, raw)
    try:
        after = os.lstat(target)
    except OSError:
        raise SecureIOError(SOURCE_CHANGED, "plan changed while read", {"path": target.as_posix()}) from None
    stamp = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns)
    if stamp(before) != stamp(after):
        raise SecureIOError(SOURCE_CHANGED, "plan changed while read", {"path": target.as_posix()})
    return document, after


def _pdf_page_count(data: bytes) -> int:
    try:
        from pypdf import PdfReader
        from pypdf.errors import FileNotDecryptedError, PdfReadError, PdfStreamError
    except ImportError as exc:
        raise PrepareError(PDF_INVALID, "PDF parser is unavailable") from exc
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, PdfStreamError, OSError, ValueError) as exc:
        raise PrepareError(PDF_INVALID, "PDF is not parseable") from exc
    except Exception as exc:
        raise PrepareError(PDF_INVALID, "PDF is not parseable") from exc
    if bool(getattr(reader, "is_encrypted", False)):
        raise PrepareError(PDF_INVALID, "PDF is encrypted")
    try:
        pages = len(reader.pages)
    except FileNotDecryptedError as exc:
        raise PrepareError(PDF_INVALID, "PDF is encrypted") from exc
    except Exception as exc:
        raise PrepareError(PDF_INVALID, "PDF is not parseable") from exc
    if pages < 1:
        raise PrepareError(PDF_INVALID, "PDF has no pages")
    return pages


def _validate_paper_blob(data: bytes, *, max_pages: int) -> tuple[int, str]:
    if not data.startswith(PDF_MAGIC):
        raise PrepareError(MEDIA_TYPE_INVALID, "paper blob must start with %PDF-")
    pages = _pdf_page_count(data)
    allowed = min(int(max_pages), HARD_MAX_PAGES)
    if pages > allowed:
        raise PrepareError(
            PAGE_LIMIT_EXCEEDED,
            "PDF page count exceeds the approved limit",
            {"page_count": pages, "max_pages": allowed},
        )
    return pages, "application/pdf"


def run(args: object | None = None) -> int:
    family = str(getattr(args, "_vpkb_family", "") or "")
    command = _command_name(family) if family in FAMILY_KIND else "vpwiki.prepare"
    plan_raw = getattr(args, "plan", None) if args is not None else None
    ref_raw = getattr(args, "approval_ref", None) if args is not None else None
    if family not in FAMILY_KIND or plan_raw is None or str(plan_raw).strip() == "":
        return emit_error(command, "USAGE", "prepare requires --plan and --approval-ref")
    if ref_raw is None or str(ref_raw).strip() == "":
        return emit_error(command, "USAGE", "prepare requires --plan and --approval-ref")
    expected_kind = FAMILY_KIND[family]
    try:
        checkout = resolve_checkout_root()
        if expected_kind == "paper-source":
            plan, plan_identity = _load_paper_plan_with_identity(checkout, str(plan_raw))
        else:
            plan = _load_prescribed_plan(checkout, str(plan_raw))
            plan_identity = None
        if plan.get("plan_kind") != expected_kind:
            raise PrepareError(
                PLAN_KIND_MISMATCH,
                "command family does not match plan_kind",
                {"plan_kind": plan.get("plan_kind")},
            )
        require_pipeline_fingerprint(plan)
        ref_path = Path(str(ref_raw))
        ref_obj = load_strict_json(
            ref_path,
            missing_code=APPROVAL_REF_NOT_FOUND,
            unsafe_code=APPROVAL_REF_INVALID,
            invalid_code=APPROVAL_REF_INVALID,
            changed_code=SOURCE_CHANGED,
        )
        parsed_ref = parse_approval_ref(ref_obj)
        ref_digest = bind_approval_ref(plan, parsed_ref)
        limits = plan.get("limits") if isinstance(plan.get("limits"), dict) else {}
        plan_max_bytes = limits.get("max_bytes")
        if not isinstance(plan_max_bytes, int):
            raise ContractError(SCHEMA_INVALID, "plan limits.max_bytes is missing")
        max_bytes = min(plan_max_bytes, HARD_MAX_BYTES)
        digest = parsed_ref["input_sha256"]
        store = BlobStore(resolve_blob_root())
        data = store.read(digest, max_bytes=max_bytes)
        payload: dict[str, Any] = {
            "batch_id": plan["batch_id"],
            "sha256": digest,
            "byte_count": len(data),
            "plan_approval_hash": plan["approval_hash"],
            "approval_ref_sha256": ref_digest,
            "approval_ref_bound": True,
        }
        if expected_kind == "paper-source":
            max_pages = limits.get("max_pages")
            if not isinstance(max_pages, int):
                raise ContractError("SCHEMA_INVALID", "plan limits.max_pages is missing")
            page_count, media_type = _validate_paper_blob(data, max_pages=max_pages)
            payload["page_count"] = page_count
            payload["media_type"] = media_type
            plan_bytes = canonicalize(plan)
            def request_factory() -> bytes:
                from video_paper_wiki.staged_capture import validate_staged_pdf_capture_request

                request = validate_staged_pdf_capture_request({
                    "schema": "video-paper-wiki.staged-pdf-capture-request.v1",
                    "batch_id": plan["batch_id"],
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
                    "approval_ref": parsed_ref,
                    "approval_ref_sha256": ref_digest,
                    "payload": {
                        "file": f"prepared/{digest}.blob",
                        "sha256": digest,
                        "size_bytes": len(data),
                        "media_type": media_type,
                        "page_count": page_count,
                    },
                })
                return canonicalize(request)

            staged_pair = _stage_prepared_pdf_capture(
                batch_id=plan["batch_id"], plan_bytes=plan_bytes,
                plan_identity=plan_identity, blob_name=f"{digest}.blob",
                blob=data, request_factory=request_factory,
            )
            payload["staged_path"] = staged_pair.blob_path.as_posix()
            payload["request_path"] = staged_pair.request_path.as_posix()
            payload["request_sha256"] = staged_pair.request_sha256
            payload["already_staged"] = (
                staged_pair.blob_already_staged and staged_pair.request_already_staged
            )
        else:
            staged = stage_bytes(
                batch_id=plan["batch_id"], relative=("prepared", f"{digest}.blob"), data=data,
            )
            payload["staged_path"] = staged.path.as_posix()
            payload["already_staged"] = staged.already_staged
    except (
        SecureIOError,
        StagingError,
        ContractError,
        IdentityError,
        CanonicalJsonError,
        ApprovalError,
        PrepareError,
    ) as exc:
        return _emit(command, exc)
    return emit_success(command, payload)
