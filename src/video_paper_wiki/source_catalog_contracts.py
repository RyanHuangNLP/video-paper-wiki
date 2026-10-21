"""Closed source catalog artifact, exact digests and bounded caller values."""
from __future__ import annotations

import re

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json
from video_paper_wiki.source_semantics_contracts import sha

SCHEMA = "video-paper-wiki.source-catalog.v1"
PROFILE = "source-catalog-v1"
PROFILE_SHA = "3263bdc02f570d5d6fbd06aa3c8c7e0a6d796ecf80cf76f673e84aea0d3b83f8"
MAX_CACHE = 64 * 1024 * 1024
MAX_DOCUMENT = 16 * 1024 * 1024
MAX_EXCERPT = 65536
MAX_INVENTORY = 100000
MAX_ROWS = 1000000
HEX = re.compile(r"[0-9a-f]{64}")
KEYS = {
    "documents": ("path",), "papers": ("paper_id",), "repositories": ("repo_id",),
    "claims": ("claim_id",), "evidence": ("claim_id", "ordinal"),
    "sources": ("source_id",), "associations": ("association_id",),
    "display_decisions": ("decision_id",), "assessment_heads": ("claim_id",),
    "display_heads": ("paper_id",), "artifacts": ("path",),
    "compiled_pages": ("path",), "coverage": ("kind", "id"),
}
REASONS = {
    "registered_owned": "source_has_canonical_owner",
    "registered_unclaimed": "source_has_no_canonical_owner",
    "captured_registered": "capture_has_registered_source",
    "captured_unregistered": "capture_has_no_source_row",
    "derived_referenced": "artifact_in_canonical_evidence_ancestry",
    "derived_unreferenced": "artifact_without_canonical_evidence_reference",
}


def fail(code, message, pointer="", *, exit_code=75):
    raise ContractError(code, message, {"instance_pointer": pointer}, exit_code=exit_code)


def invalid(message, pointer=""):
    fail("SOURCE_CATALOG_INVALID", message, pointer, exit_code=2)


def limit(message, pointer=""):
    fail("SOURCE_CATALOG_LIMIT", message, pointer)


def text(value, pointer, *, nonempty=True):
    if type(value) is not str:
        invalid("value must be an exact string", pointer)
    try:
        value.encode("utf-8")
    except UnicodeError:
        invalid("value must be valid UTF-8", pointer)
    if nonempty and not value.strip():
        invalid("value must be nonempty", pointer)
    return value


def integer(value, pointer, lower, upper):
    if type(value) is not int:
        invalid("value must be an exact integer", pointer)
    if not lower <= value <= upper:
        limit("integer is outside its supported bounds", pointer)
    return value


def choice(value, choices, pointer):
    if type(value) is not str or value not in choices:
        invalid("value is outside the supported choices", pointer)
    return value


def checksum(value):
    if value is not None and (type(value) is not str or HEX.fullmatch(value) is None):
        invalid("catalog digest must be SHA-256", "/catalog_sha256")
    return value


def row_key(row, fields):
    return tuple(row[k].encode("utf-8") if type(row[k]) is str else row[k] for k in fields)


def ordered(rows):
    if set(rows) != set(KEYS):
        invalid("catalog row groups differ", "/rows")
    if sum(len(x) for x in rows.values()) > MAX_ROWS:
        limit("catalog exceeds the complete row bound", "/rows")
    for name, fields in KEYS.items():
        rows[name].sort(key=lambda row: row_key(row, fields))
        keys = [row_key(row, fields) for row in rows[name]]
        if len(set(keys)) != len(keys):
            invalid("catalog group contains duplicate identities", "/rows/" + name)
    return rows


def digest(document):
    return sha(SCHEMA.encode() + b"\0" + canonicalize({k: v for k, v in document.items() if k != "catalog_sha256"}))


def _assert_key_order(document):
    """Refuse malformed retained input without sorting or repairing it."""
    def keys_are_ordered(keys, pointer):
        if keys != sorted(set(keys)):
            invalid("catalog identities are duplicated or unordered", pointer)
    for name, fields in KEYS.items():
        keys_are_ordered([row_key(row, fields) for row in document["rows"][name]], "/rows/" + name)
    for parent, name in (("basis", "inventory"), ("generation", "implementation"), ("generation", "resources")):
        keys_are_ordered([row["path"].encode("utf-8") for row in document[parent][name]], "/" + parent + "/" + name)
    for group, fields in (("papers", ("association_ids",)), ("artifacts", ("source_ids",)),
                          ("coverage", ("source_ids", "paper_ids", "repo_ids"))):
        for row in document["rows"][group]:
            for field in fields:
                keys_are_ordered([value.encode("utf-8") for value in row[field]], "/rows/" + group + "/" + field)


def encode(document):
    """Validate a complete projection before staging or comparing its bytes."""
    try:
        validate_document(document, SCHEMA)
        raw = canonicalize(document)
    except (ContractError, ValueError, TypeError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, ContractError) and exc.code in {"WORK_PATH_UNSAFE", "SOURCE_CATALOG_LIMIT"}:
            raise
        invalid("catalog violates its closed artifact schema", getattr(exc, "details", {}).get("instance_pointer", ""))
    _assert_key_order(document)
    if len(raw) > MAX_CACHE:
        limit("catalog exceeds its complete byte bound")
    if len(document["basis"]["inventory"]) > MAX_INVENTORY:
        limit("catalog inventory exceeds its bound", "/basis/inventory")
    if sum(len(x) for x in document["rows"].values()) > MAX_ROWS:
        limit("catalog row count exceeds its bound", "/rows")
    for row in document["rows"]["documents"]:
        if len(row["json_text"].encode()) > MAX_DOCUMENT:
            limit("exact semantic document exceeds its byte bound", "/rows/documents")
    for row in document["rows"]["evidence"]:
        excerpt = row["resolution"]["excerpt"]
        if excerpt is not None and len(excerpt.encode()) > MAX_EXCERPT:
            limit("resolved excerpt exceeds its byte bound", "/rows/evidence")
    if (document["catalog_sha256"] != digest(document)
            or document["generation"]["rows_sha256"] != sha(canonicalize(document["rows"]))):
        invalid("catalog self-digest differs", "/catalog_sha256")
    return raw


def parse_cache(raw):
    if type(raw) is not bytes:
        invalid("catalog cache requires exact bytes")
    if len(raw) > MAX_CACHE:
        limit("catalog cache exceeds its byte bound")
    try:
        document = parse_strict_json(raw, invalid_code="SOURCE_CATALOG_INVALID")
    except (SecureIOError, ValueError, TypeError, RecursionError, UnicodeError):
        invalid("catalog cache is not strict UTF-8 JSON")
    if encode(document) != raw:
        invalid("catalog cache bytes are not canonical")
    return document
