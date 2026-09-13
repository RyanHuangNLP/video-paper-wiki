"""Pure capture declarations; no filesystem or upstream execution authority."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize

CAPTURE_SCHEMA = "video-paper-wiki.capture-inspection.v1"
MAX_BYTES = 67108864
SHA_PATTERN = r"[0-9a-f]{64}"
OPERATION_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*"
PATH_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*"
CAPTURED_PATTERN = r"\.raw/captured/([0-9a-f]{64})\.[A-Za-z0-9][A-Za-z0-9._-]*"
CAPTURE_FIELDS = (
    "schema", "route", "media_type", "payload", "source_path", "proposal_sha256",
    "stored_path", "source_identity", "siblings", "would_change", "operation_id",
    "upstream_plan_sha256",
)


def _error(code: str, message: str, pointer: str = "", schema: str | None = None) -> ContractError:
    details = {"instance_pointer": pointer}
    if schema is not None:
        details["schema"] = schema
    return ContractError(code, message, details)


def _strict_string(value: str, pattern: str, pointer: str, schema: str) -> None:
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise _error("SCHEMA_INVALID", "value does not match the complete grammar", pointer, schema)


def _strict_int(value: int, pointer: str, schema: str) -> None:
    if type(value) is not int:
        raise _error("SCHEMA_INVALID", "value must be a Python integer, not bool or float", pointer, schema)


def _payload_fields(document: dict, schema: str) -> None:
    _strict_string(document["payload"]["sha256"], SHA_PATTERN, "/payload/sha256", schema)
    _strict_int(document["payload"]["size_bytes"], "/payload/size_bytes", schema)


def _hash_material(material: object, schema: str) -> str:
    try:
        return hashlib.sha256(canonicalize(material)).hexdigest()
    except (CanonicalJsonError, RecursionError) as exc:
        raise _error("CANONICAL_JSON_INVALID", "hash material cannot be canonicalized", "", schema) from exc


def _require_material(document: object, fields: tuple[str, ...], schema: str) -> dict:
    if not isinstance(document, dict):
        raise _error("SCHEMA_INVALID", "hash material must be an object", "", schema)
    for field in fields:
        if field not in document:
            raise _error("SCHEMA_INVALID", "required hash material is missing", "/" + field, schema)
    return document


def capture_approval_hash(document: object) -> str:
    """Hash the exact declaration except its self-hash; never attest it."""
    doc = _require_material(document, CAPTURE_FIELDS, CAPTURE_SCHEMA)
    return _hash_material({key: value for key, value in doc.items() if key != "approval_hash"}, CAPTURE_SCHEMA)


def _check_capture_inspection(document: dict[str, Any]) -> None:
    """Post-schema checks, called only by the central schema dispatcher."""
    schema = CAPTURE_SCHEMA
    _payload_fields(document, schema)
    for field in ("source_identity", "proposal_sha256", "upstream_plan_sha256", "approval_hash"):
        if document[field] is not None:
            _strict_string(document[field], SHA_PATTERN, "/" + field, schema)
    _strict_string(document["stored_path"], CAPTURED_PATTERN, "/stored_path", schema)
    if document["operation_id"] is not None:
        _strict_string(document["operation_id"], OPERATION_PATTERN, "/operation_id", schema)
    if document["source_path"] is not None:
        _strict_string(document["source_path"], PATH_PATTERN, "/source_path", schema)
        _strict_string(document["source_path"], r"inbox/.+\.pdf", "/source_path", schema)
    for index, sibling in enumerate(document["siblings"]):
        pointer = f"/siblings/{index}"
        _strict_string(sibling["path"], CAPTURED_PATTERN, pointer + "/path", schema)
        _strict_int(sibling["mode"], pointer + "/mode", schema)
        if sibling["sha256"] is not None:
            _strict_string(sibling["sha256"], SHA_PATTERN, pointer + "/sha256", schema)

    def binding(condition: bool, pointer: str) -> None:
        if not condition:
            raise _error("CAPTURE_BINDING_MISMATCH", "capture declarations are inconsistent", pointer, schema)

    pdf = document["media_type"] == "application/pdf"
    manual = document["route"] == "manual-inbox"
    binding(not manual or pdf, "/route")
    binding((document["source_path"] is not None) == manual, "/source_path")
    binding((document["proposal_sha256"] is None) == pdf, "/proposal_sha256")
    binding(not pdf or document["payload"]["size_bytes"] >= 5, "/payload/size_bytes")
    digest = document["payload"]["sha256"]
    binding(document["source_identity"] == digest, "/source_identity")
    binding(re.fullmatch(CAPTURED_PATTERN, document["stored_path"]).group(1) == digest, "/stored_path")
    siblings = document["siblings"]
    if len(siblings) > 1:
        raise _error("CAPTURE_SNAPSHOT_INVALID", "snapshot must contain at most one sibling", "/siblings", schema)
    if siblings:
        sibling = siblings[0]
        if (sibling["kind"] != "regular" or sibling["sha256"] != digest
                or re.fullmatch(CAPTURED_PATTERN, sibling["path"]).group(1) != digest
                or sibling["path"] != document["stored_path"]):
            raise _error("CAPTURE_SNAPSHOT_INVALID", "sibling is not the unique matching selected regular file", "/siblings/0", schema)
        binding(document["would_change"] is False, "/would_change")
        binding(document["operation_id"] is None, "/operation_id")
        binding(document["upstream_plan_sha256"] is None, "/upstream_plan_sha256")
    else:
        suffix = "pdf" if pdf else "bin"
        binding(document["stored_path"] == f".raw/captured/{digest}.{suffix}", "/stored_path")
        binding(document["would_change"] is True, "/would_change")
        binding(document["operation_id"] is not None, "/operation_id")
        binding(document["upstream_plan_sha256"] is not None, "/upstream_plan_sha256")
    if document["approval_hash"] != capture_approval_hash(document):
        raise _error("CAPTURE_APPROVAL_MISMATCH", "capture approval hash differs", "/approval_hash", schema)


def _bounded_bytes(payload: bytes) -> None:
    if not isinstance(payload, bytes):
        raise _error("SCHEMA_INVALID", "payload must be bytes")
    if len(payload) > MAX_BYTES:
        raise _error("PAYLOAD_MISMATCH", "payload exceeds the byte limit")


def _verify_payload(document: dict, payload: bytes, schema: str) -> None:
    try:
        _bounded_bytes(payload)
    except ContractError as exc:
        raise _error(exc.code, exc.message, "", schema) from exc
    if (len(payload) != document["payload"]["size_bytes"]
            or hashlib.sha256(payload).hexdigest() != document["payload"]["sha256"]):
        raise _error("PAYLOAD_MISMATCH", "payload bytes differ from size or hash declaration", "/payload", schema)


def validate_capture_inspection(document: object, *, payload: bytes | None = None) -> dict:
    """Validate supplied data without reading caller paths or executing capture."""
    doc = validate_document(document, expected_schema=CAPTURE_SCHEMA)
    if payload is not None:
        _verify_payload(doc, payload, CAPTURE_SCHEMA)
        if doc["media_type"] == "application/pdf":
            if not payload.startswith(b"%PDF-"):
                raise _error("PAYLOAD_MISMATCH", "payload lacks PDF media magic", "/payload", CAPTURE_SCHEMA)
        else:
            from video_paper_wiki.code_evidence_contracts import normalize_code_bytes

            try:
                normalize_code_bytes(payload)
            except ContractError as exc:
                raise _error(exc.code, exc.message, "", CAPTURE_SCHEMA) from exc
    return doc
