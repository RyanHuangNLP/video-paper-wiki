"""Consume desensitized approval-ref JSON. vpwiki never issues refs."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from video_paper_wiki.identity import (
    IdentityError,
    is_stable_subject_id,
    pipeline_fingerprint,
    plan_approval_hash,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.staging import StagingError, validate_batch_id

APPROVAL_REF_FORMAT = "video-paper-wiki.approval-ref.v1"
APPROVAL_REF_INVALID = "APPROVAL_REF_INVALID"
APPROVAL_REF_MISMATCH = "APPROVAL_REF_MISMATCH"
PIPELINE_FINGERPRINT_MISMATCH = "PIPELINE_FINGERPRINT_MISMATCH"
APPROVAL_REF_KEYS = (
    "format",
    "plan_approval_hash",
    "plan_kind",
    "batch_id",
    "stable_subject_id",
    "input_sha256",
    "limits_sha256",
    "network_targets_sha256",
    "pipeline_fingerprint",
)
PLAN_KINDS = frozenset({"paper-source", "code-evidence"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ApprovalError(Exception):
    """Fail-closed approval-ref error with a stable envelope code."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        *,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details) if details is not None else {}
        self.exit_code = exit_code


def _invalid(message: str, details: Mapping[str, Any] | None = None) -> ApprovalError:
    return ApprovalError(APPROVAL_REF_INVALID, message, details)


def _mismatch(field: str) -> ApprovalError:
    return ApprovalError(
        APPROVAL_REF_MISMATCH,
        "approval ref does not bind to the plan",
        {"field": field},
    )


def jcs_sha256(value: Any) -> str:
    try:
        return hashlib.sha256(canonicalize(value)).hexdigest()
    except CanonicalJsonError as exc:
        raise _invalid("approval ref digest is not integer-only JCS", dict(exc.details)) from exc


def approval_ref_sha256(ref: Mapping[str, Any]) -> str:
    return jcs_sha256(dict(ref))


def parse_approval_ref(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid("approval ref must be a JSON object")
    keys = tuple(value.keys())
    if set(keys) != set(APPROVAL_REF_KEYS):
        raise _invalid(
            "approval ref fields must match the v1 binding exactly",
            {"reason": "fields"},
        )
    if any(not isinstance(value[key], str) for key in APPROVAL_REF_KEYS):
        raise _invalid("approval ref field values must be strings")
    payload = {key: str(value[key]) for key in APPROVAL_REF_KEYS}
    if payload["format"] != APPROVAL_REF_FORMAT:
        raise _invalid("approval ref format is not video-paper-wiki.approval-ref.v1")
    if payload["plan_kind"] not in PLAN_KINDS:
        raise _invalid("approval ref plan_kind is not a legal plan kind")
    for field in (
        "plan_approval_hash",
        "input_sha256",
        "limits_sha256",
        "network_targets_sha256",
        "pipeline_fingerprint",
    ):
        if not SHA256_RE.fullmatch(payload[field]):
            raise _invalid("approval ref digest is not 64 lowercase hex", {"field": field})
    try:
        payload["batch_id"] = validate_batch_id(payload["batch_id"])
    except StagingError as exc:
        raise _invalid("approval ref batch_id is not a legal staging batch id") from exc
    if not is_stable_subject_id(payload["stable_subject_id"]):
        raise _invalid("approval ref stable_subject_id is not a legal stable subject")
    return payload


def require_pipeline_fingerprint(plan: Mapping[str, Any]) -> str:
    """Require plan.pipeline_fingerprint present and equal to the parser digest."""

    parser = plan.get("parser")
    if not isinstance(parser, Mapping):
        raise ApprovalError(
            PIPELINE_FINGERPRINT_MISMATCH,
            "plan pipeline_fingerprint does not match the parser",
            {"field": "pipeline_fingerprint"},
        )
    try:
        expected = pipeline_fingerprint(parser)
    except (IdentityError, CanonicalJsonError) as exc:
        raise ApprovalError(
            PIPELINE_FINGERPRINT_MISMATCH,
            "plan pipeline_fingerprint does not match the parser",
            {"field": "pipeline_fingerprint"},
        ) from exc
    stated = plan.get("pipeline_fingerprint")
    if not isinstance(stated, str) or stated != expected:
        raise ApprovalError(
            PIPELINE_FINGERPRINT_MISMATCH,
            "plan pipeline_fingerprint does not match the parser",
            {"field": "pipeline_fingerprint"},
        )
    return expected


def bind_approval_ref(plan: Mapping[str, Any], ref: Mapping[str, Any]) -> str:
    """Bind *ref* to *plan*. Return approval_ref_sha256. Never claims human approval."""

    parsed = parse_approval_ref(ref)
    expected_pipeline = require_pipeline_fingerprint(plan)
    try:
        expected_approval = plan_approval_hash(plan)
        expected_limits = jcs_sha256(plan.get("limits"))
        expected_targets = jcs_sha256(plan.get("network_targets"))
    except (IdentityError, CanonicalJsonError) as exc:
        raise ApprovalError(
            APPROVAL_REF_MISMATCH,
            "approval ref does not bind to the plan",
            {"field": "plan_approval_hash"},
        ) from exc
    stated_approval = plan.get("approval_hash")
    if not isinstance(stated_approval, str) or stated_approval != expected_approval:
        raise _mismatch("plan_approval_hash")
    if parsed["plan_approval_hash"] != expected_approval:
        raise _mismatch("plan_approval_hash")
    if parsed["plan_kind"] != plan.get("plan_kind"):
        raise _mismatch("plan_kind")
    if parsed["batch_id"] != plan.get("batch_id"):
        raise _mismatch("batch_id")
    if parsed["stable_subject_id"] != plan.get("stable_subject_id"):
        raise _mismatch("stable_subject_id")
    if parsed["limits_sha256"] != expected_limits:
        raise _mismatch("limits_sha256")
    if parsed["network_targets_sha256"] != expected_targets:
        raise _mismatch("network_targets_sha256")
    if parsed["pipeline_fingerprint"] != expected_pipeline:
        raise _mismatch("pipeline_fingerprint")
    source = plan.get("input")
    if isinstance(source, Mapping) and isinstance(source.get("local_sha256"), str):
        if parsed["input_sha256"] != source["local_sha256"]:
            raise _mismatch("input_sha256")
    return approval_ref_sha256(parsed)
