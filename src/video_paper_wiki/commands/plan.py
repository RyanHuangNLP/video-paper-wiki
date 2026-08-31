"""Offline ingest/code-map plan. Writes only .work/<batch>/plan/ingest-plan.v1.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.contracts import SCHEMA_INVALID, ContractError, validate_document
from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success
from video_paper_wiki.identity import IdentityError, pipeline_fingerprint, plan_approval_hash
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.secure_io import (
    SOURCE_CHANGED,
    SecureIOError,
    load_strict_json,
)
from video_paper_wiki.staging import (
    CODE_INVALID_BATCH_ID,
    StagingError,
    stage_bytes,
    validate_batch_id,
)

PLAN_SCHEMA = "video-paper-wiki.ingest-plan.v1"
PLAN_FILENAME = "ingest-plan.v1.json"
PLAN_REQUEST_INVALID = "PLAN_REQUEST_INVALID"
PLAN_KIND_MISMATCH = "PLAN_KIND_MISMATCH"
DERIVED_FIELDS = frozenset({"approval_hash", "pipeline_fingerprint"})
FAMILY_KIND = {"ingest": "paper-source", "code-map": "code-evidence"}


def _command_name(family: str) -> str:
    return "ingest.plan" if family == "ingest" else "code-map.plan"


def _emit(command: str, exc: BaseException) -> int:
    if isinstance(exc, StagingError):
        return emit_staging_error(command, exc)
    if isinstance(exc, TypeError):
        return emit_error(
            command,
            PLAN_REQUEST_INVALID,
            "request is not a valid plan shape",
            {},
            exit_code=2,
        )
    code = str(getattr(exc, "code", PLAN_REQUEST_INVALID))
    message = str(getattr(exc, "message", exc))
    details = dict(getattr(exc, "details", {}) or {})
    exit_code = int(getattr(exc, "exit_code", 2))
    if code == SCHEMA_INVALID:
        code = PLAN_REQUEST_INVALID
        exit_code = 2
    return emit_error(command, code, message, details, exit_code=exit_code)


def _request_error(message: str, details: dict[str, Any] | None = None) -> SecureIOError:
    return SecureIOError(PLAN_REQUEST_INVALID, message, details)


def _build_plan(request: object, expected_kind: str) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise _request_error("request must be a JSON object")
    stated_schema = request.get("schema")
    if stated_schema is not None and not isinstance(stated_schema, str):
        raise _request_error("request schema must be a string")
    present = sorted(DERIVED_FIELDS.intersection(request))
    if present:
        raise _request_error(
            "request must not include derived fields",
            {"fields": present},
        )
    kind = request.get("plan_kind")
    if kind != expected_kind:
        if kind in FAMILY_KIND.values():
            raise SecureIOError(
                PLAN_KIND_MISMATCH,
                "command family does not match plan_kind",
                {"plan_kind": kind},
            )
        raise _request_error("request plan_kind is not valid for this command")
    parser = request.get("parser")
    if not isinstance(parser, dict):
        raise _request_error("request parser is missing")
    plan = {key: value for key, value in request.items()}
    try:
        plan["pipeline_fingerprint"] = pipeline_fingerprint(parser)
        plan["approval_hash"] = plan_approval_hash(plan)
    except (IdentityError, CanonicalJsonError, TypeError) as exc:
        raise _request_error(
            "request cannot be canonicalized into a plan",
            dict(getattr(exc, "details", {}) or {}),
        ) from exc
    try:
        validate_document(plan, expected_schema=PLAN_SCHEMA)
    except ContractError as exc:
        if getattr(exc, "code", None) == SCHEMA_INVALID:
            raise _request_error(str(exc.message), dict(exc.details)) from exc
        raise
    except TypeError as exc:
        raise _request_error("request is not a valid plan shape") from exc
    try:
        validate_batch_id(plan.get("batch_id"))
    except StagingError as exc:
        if exc.code == CODE_INVALID_BATCH_ID:
            raise _request_error(
                "request batch_id is not a legal staging batch id",
                dict(exc.details),
            ) from exc
        raise
    except TypeError as exc:
        raise _request_error("request is not a valid plan shape") from exc
    return plan


def run(args: object | None = None) -> int:
    family = str(getattr(args, "_vpkb_family", "") or "")
    command = _command_name(family) if family in FAMILY_KIND else "vpwiki.plan"
    raw = getattr(args, "request", None) if args is not None else None
    if family not in FAMILY_KIND or raw is None or str(raw).strip() == "":
        return emit_error(command, "USAGE", "plan requires --request")
    path = Path(str(raw))
    expected_kind = FAMILY_KIND[family]
    try:
        request = load_strict_json(
            path,
            missing_code=PLAN_REQUEST_INVALID,
            unsafe_code=PLAN_REQUEST_INVALID,
            invalid_code=PLAN_REQUEST_INVALID,
            changed_code=SOURCE_CHANGED,
        )
        plan = _build_plan(request, expected_kind)
        payload = canonicalize(plan)
        staged = stage_bytes(
            batch_id=plan["batch_id"],
            relative=("plan", PLAN_FILENAME),
            data=payload,
        )
    except (SecureIOError, StagingError, ContractError, IdentityError, CanonicalJsonError, TypeError) as exc:
        return _emit(command, exc)
    return emit_success(
        command,
        {
            "plan": plan,
            "plan_path": staged.path.as_posix(),
            "approval_hash": plan["approval_hash"],
            "pipeline_fingerprint": plan["pipeline_fingerprint"],
            "already_staged": staged.already_staged,
        },
    )
