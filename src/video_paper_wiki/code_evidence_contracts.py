"""Pure code evidence declarations and reproducible UTF-8 line locators."""

from __future__ import annotations

import hashlib
import re

from jsonschema.exceptions import best_match

from video_paper_wiki.capture_contracts import (
    CAPTURED_PATTERN, OPERATION_PATTERN, PATH_PATTERN, SHA_PATTERN,
    _bounded_bytes, _error, _hash_material, _payload_fields, _require_material,
    _strict_int, _strict_string, _verify_payload, validate_capture_inspection,
)
from video_paper_wiki.contracts import (
    ContractError, _raise_validation_error, _validator_for, schema_by_title, validate_document,
)

CODE_SCHEMA = "video-paper-wiki.code-evidence-manifest.v1"
LOCATOR_SCHEMA = "video-paper-wiki.common.v1#/$defs/code_locator"
REPOSITORY_PATTERN = r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+"
SOURCE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._:-]*"
PROPOSAL_FIELDS = (
    "schema", "state", "origin", "payload", "media_type", "encoding",
    "line_canonicalization", "newline_style", "ends_with_newline", "line_count",
    "normalized_sha256",
)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def code_proposal_hash(document: object) -> str:
    doc = _require_material(document, PROPOSAL_FIELDS, CODE_SCHEMA)
    material = {field: doc[field] for field in PROPOSAL_FIELDS}
    material["state"] = "proposal"
    return _hash_material(material, CODE_SCHEMA)


def code_manifest_hash(document: object) -> str:
    doc = _require_material(document, (*PROPOSAL_FIELDS, "proposal_sha256", "capture"), CODE_SCHEMA)
    return _hash_material({key: value for key, value in doc.items() if key != "manifest_sha256"}, CODE_SCHEMA)


def normalize_code_bytes(payload: bytes) -> bytes:
    _bounded_bytes(payload)
    if payload.startswith(b"\xef\xbb\xbf"):
        raise _error("CODE_TEXT_INVALID", "initial UTF-8 BOM is forbidden")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _error("CODE_TEXT_INVALID", "payload is not strict UTF-8") from exc
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u2028\u2029]", text):
        raise _error("CODE_TEXT_INVALID", "payload contains a forbidden control or line separator")
    normalized = text.replace("\r\n", "\n")
    if "\r" in normalized:
        raise _error("CODE_TEXT_INVALID", "bare CR is forbidden")
    return normalized.encode("utf-8")


def _line_count(normalized: bytes) -> int:
    if not normalized:
        return 0
    return normalized.count(b"\n") + (not normalized.endswith(b"\n"))


def code_text_metadata(payload: bytes) -> dict:
    normalized = normalize_code_bytes(payload)
    crlf = payload.count(b"\r\n")
    lf = payload.count(b"\n") - crlf
    style = "mixed" if crlf and lf else "crlf" if crlf else "lf" if lf else "none"
    return {
        "newline_style": style,
        "ends_with_newline": normalized.endswith(b"\n"),
        "line_count": _line_count(normalized),
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
    }


def code_snippet_sha256(payload: bytes, start: int, end: int) -> str:
    normalized = normalize_code_bytes(payload)
    count = _line_count(normalized)
    if type(start) is not int or type(end) is not int or start < 1 or start > end or end > count:
        raise _error("CODE_LINE_RANGE_INVALID", "line range is invalid or outside the text", "/lines")
    # Find only the selected boundaries; never allocate one object per line.
    first = 0
    for _ in range(start - 1):
        first = normalized.find(b"\n", first) + 1
    if end == count:
        last = len(normalized) - normalized.endswith(b"\n")
    else:
        last = first
        for _ in range(end - start + 1):
            last = normalized.find(b"\n", last) + 1
        last -= 1
    return hashlib.sha256(normalized[first:last]).hexdigest()


def _origin_fields(origin: dict, pointer: str, schema: str) -> None:
    _strict_string(origin["repository"], REPOSITORY_PATTERN, pointer + "/repository", schema)
    _strict_string(origin["commit"], r"[0-9a-f]{40}", pointer + "/commit", schema)
    _strict_string(origin["path"], PATH_PATTERN, pointer + "/path", schema)


def _check_code_evidence_manifest(document: dict) -> None:
    _payload_fields(document, CODE_SCHEMA)
    _origin_fields(document["origin"], "/origin", CODE_SCHEMA)
    _strict_int(document["line_count"], "/line_count", CODE_SCHEMA)
    for field in ("normalized_sha256", "proposal_sha256", "manifest_sha256"):
        if field in document:
            _strict_string(document[field], SHA_PATTERN, "/" + field, CODE_SCHEMA)
    if document["state"] == "inspected":
        capture = document["capture"]
        _strict_string(capture["stored_path"], CAPTURED_PATTERN, "/capture/stored_path", CODE_SCHEMA)
        _strict_string(capture["source_id"], SOURCE_ID_PATTERN, "/capture/source_id", CODE_SCHEMA)
        for field in ("source_identity", "inspection_approval_hash"):
            _strict_string(capture[field], SHA_PATTERN, "/capture/" + field, CODE_SCHEMA)
        if capture["operation_id"] is not None:
            _strict_string(capture["operation_id"], OPERATION_PATTERN, "/capture/operation_id", CODE_SCHEMA)
        if (capture["source_identity"] != document["payload"]["sha256"]
                or re.fullmatch(CAPTURED_PATTERN, capture["stored_path"]).group(1) != document["payload"]["sha256"]):
            raise _error("CAPTURE_BINDING_MISMATCH", "manifest capture identity differs from payload", "/capture", CODE_SCHEMA)
    size, count = document["payload"]["size_bytes"], document["line_count"]
    consistent = count <= size
    if size == 0:
        consistent = consistent and (
            count == 0 and document["newline_style"] == "none" and not document["ends_with_newline"]
            and document["payload"]["sha256"] == EMPTY_SHA256 and document["normalized_sha256"] == EMPTY_SHA256
        )
    else:
        consistent = consistent and count >= 1
    if document["newline_style"] == "none":
        consistent = consistent and not document["ends_with_newline"] and (size == 0 or count == 1)
    if not consistent:
        raise _error("CODE_MANIFEST_MISMATCH", "declared text metadata is inconsistent", "/line_count", CODE_SCHEMA)
    if document["proposal_sha256"] != code_proposal_hash(document):
        raise _error("CODE_MANIFEST_MISMATCH", "proposal hash differs", "/proposal_sha256", CODE_SCHEMA)
    if document["state"] == "inspected" and document["manifest_sha256"] != code_manifest_hash(document):
        raise _error("CODE_MANIFEST_MISMATCH", "manifest hash differs", "/manifest_sha256", CODE_SCHEMA)


def validate_code_evidence_manifest(document: object, *, payload: bytes | None = None) -> dict:
    doc = validate_document(document, expected_schema=CODE_SCHEMA)
    if payload is not None:
        _verify_payload(doc, payload, CODE_SCHEMA)
        try:
            metadata = code_text_metadata(payload)
        except ContractError as exc:
            raise _error(exc.code, exc.message, "", CODE_SCHEMA) from exc
        for field, value in metadata.items():
            if doc[field] != value:
                raise _error("CODE_MANIFEST_MISMATCH", "text metadata differs from supplied bytes", "/" + field, CODE_SCHEMA)
    return doc


def validate_code_capture_binding(manifest: object, inspection: object) -> None:
    doc = validate_code_evidence_manifest(manifest)
    observed = validate_capture_inspection(inspection)
    if doc["state"] != "inspected" or observed["route"] != "staged-capture" or observed["media_type"] != "text/plain":
        raise _error("CAPTURE_BINDING_MISMATCH", "binding requires inspected code and staged text capture", "", CODE_SCHEMA)
    for field in ("proposal_sha256", "payload"):
        if doc[field] != observed[field]:
            raise _error("CAPTURE_BINDING_MISMATCH", "manifest and inspection differ", "/" + field, CODE_SCHEMA)
    for field, inspection_field in (
        ("stored_path", "stored_path"), ("source_identity", "source_identity"),
        ("inspection_approval_hash", "approval_hash"), ("operation_id", "operation_id"),
    ):
        if doc["capture"][field] != observed[inspection_field]:
            raise _error("CAPTURE_BINDING_MISMATCH", "capture binding differs from inspection", "/capture/" + field, CODE_SCHEMA)


def validate_code_locator(locator: object, manifest: object, payload: bytes) -> None:
    common = schema_by_title("video-paper-wiki.common.v1")
    validator = _validator_for({"$ref": common["$id"] + "#/$defs/code_locator"})
    errors = list(validator.iter_errors(locator))
    if errors:
        _raise_validation_error(best_match(iter(errors)) or errors[0], LOCATOR_SCHEMA)
    _origin_fields(locator, "", LOCATOR_SCHEMA)
    _strict_string(locator["source_id"], SOURCE_ID_PATTERN, "/source_id", LOCATOR_SCHEMA)
    _strict_string(locator["snippet_sha256"], SHA_PATTERN, "/snippet_sha256", LOCATOR_SCHEMA)
    for field in ("start", "end"):
        _strict_int(locator["lines"][field], "/lines/" + field, LOCATOR_SCHEMA)
    doc = validate_code_evidence_manifest(manifest, payload=payload)
    if doc["state"] != "inspected":
        raise _error("CODE_LOCATOR_MISMATCH", "locator requires an inspected manifest", "", LOCATOR_SCHEMA)
    for field in ("repository", "commit", "path"):
        actual, expected = locator[field], doc["origin"][field]
        if field == "repository":
            actual, expected = actual.casefold(), expected.casefold()
        if actual != expected:
            raise _error("CODE_LOCATOR_MISMATCH", "locator origin differs from manifest", "/" + field, LOCATOR_SCHEMA)
    if locator["source_id"] != doc["capture"]["source_id"]:
        raise _error("CODE_LOCATOR_MISMATCH", "locator source ID differs from declaration", "/source_id", LOCATOR_SCHEMA)
    try:
        snippet = code_snippet_sha256(payload, locator["lines"]["start"], locator["lines"]["end"])
    except ContractError as exc:
        raise _error(exc.code, exc.message, "/lines", LOCATOR_SCHEMA) from exc
    if locator["snippet_sha256"] != snippet:
        raise _error("CODE_LOCATOR_MISMATCH", "locator snippet digest differs", "/snippet_sha256", LOCATOR_SCHEMA)
