"""Pure transaction transport validation plus fixed local staging."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, NoReturn

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.staging import (
    _RetainedBatchSession,
    _stage_transaction_inspect_files,
    _stage_transaction_inspect_files_in_session,
    validate_batch_id,
)
from video_paper_wiki.transaction_contracts import (
    _collisions,
    _json_preflight,
    _path,
    validate_transaction,
    verify_transaction_bytes,
)

STAGING_SCHEMA = "video-paper-wiki.transaction-staging.v1"
MAX_BUNDLE_BYTES = 8 * 1024 * 1024
CODE_STAGING_MISMATCH = "TRANSACTION_STAGING_MISMATCH"
CODE_TRANSACTION_LIMIT = "TRANSACTION_LIMIT_EXCEEDED"


def _fail(code: str, pointer: str, message: str) -> NoReturn:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _bundle_value(proposal: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "claude-obsidian.transaction.v1",
        "operation_id": proposal["operation_id"],
        "operation_type": proposal["operation_type"],
        "writes": [
            {
                "path": item["path"],
                "mode": item["mode"],
                "content_file": "content/" + item["sha256"],
                "sha256": item["sha256"],
            }
            for item in proposal["writes"]
        ],
        "expected_hashes": proposal["expected_hashes"],
        "read_preconditions": proposal["read_preconditions"],
        "address_requests": [],
        "source_manifest_updates": {},
    }


def encode_transaction_inspect_bundle(material: object) -> bytes:
    """Validate and encode the portable upstream transaction bundle."""
    _json_preflight(material)
    if type(material) is not dict or set(material) != {
        "operation_id", "operation_type", "writes", "expected_hashes",
        "read_preconditions",
    }:
        _fail("SCHEMA_INVALID", "", "bundle material must have the exact fields")
    operation_id = material["operation_id"]
    operation_type = material["operation_type"]
    writes = material["writes"]
    expected = material["expected_hashes"]
    reads = material["read_preconditions"]
    if type(operation_id) is not str or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", operation_id,
    ) is None:
        _fail("SCHEMA_INVALID", "/operation_id", "invalid bounded operation ID")
    if type(operation_type) is not str or operation_type not in {"capture", "ingest", "generic"}:
        _fail("SCHEMA_INVALID", "/operation_type", "invalid operation type")
    if type(writes) is not list or not writes or len(writes) > 1024:
        _fail("SCHEMA_INVALID", "/writes", "writes must be a bounded nonempty list")
    if type(expected) is not dict or type(reads) is not dict:
        _fail("SCHEMA_INVALID", "", "precondition maps must be objects")
    paths: list[tuple[str, str]] = []
    output_writes: list[dict[str, object]] = []
    for index, item in enumerate(writes):
        pointer = f"/writes/{index}"
        if type(item) is not dict or set(item) != {"path", "mode", "sha256"}:
            _fail("SCHEMA_INVALID", pointer, "write descriptor must have exact fields")
        path, mode, digest = item["path"], item["mode"], item["sha256"]
        if type(path) is not str or type(mode) is not str or type(digest) is not str:
            _fail("SCHEMA_INVALID", pointer, "write descriptor scalars must be strings")
        if mode not in {"create", "replace"}:
            _fail("SCHEMA_INVALID", pointer + "/mode", "invalid write mode")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            _fail("SCHEMA_INVALID", pointer + "/sha256", "invalid content digest")
        _path(path, pointer + "/path", new=True)
        paths.append((path, pointer + "/path"))
        output_writes.append({
            "path": path, "mode": mode,
            "content_file": "content/" + digest, "sha256": digest,
        })
    _collisions(paths)
    write_keys = {item["path"] for item in writes}
    if set(expected) != write_keys:
        _fail("TRANSACTION_PRECONDITION_MISMATCH", "/expected_hashes", "expected hashes must match writes")
    for key, value in expected.items():
        _path(key, "/expected_hashes", new=True)
        if value is not None and (type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None):
            _fail("SCHEMA_INVALID", "/expected_hashes", "invalid expected hash")
        mode = next(item["mode"] for item in writes if item["path"] == key)
        if (mode == "create") != (value is None):
            _fail("TRANSACTION_PRECONDITION_MISMATCH", "/expected_hashes", "write mode and expected hash differ")
    read_entries: list[tuple[str, str]] = []
    for key, value in reads.items():
        _path(key, "/read_preconditions")
        if value is not None and (type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None):
            _fail("SCHEMA_INVALID", "/read_preconditions", "invalid read hash")
        read_entries.append((key, "/read_preconditions"))
    _collisions(paths + read_entries)
    value = {
        "schema": "claude-obsidian.transaction.v1",
        "operation_id": operation_id,
        "operation_type": operation_type,
        "writes": output_writes,
        "expected_hashes": expected,
        "read_preconditions": reads,
        "address_requests": [],
        "source_manifest_updates": {},
    }
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail(CODE_STAGING_MISMATCH, "", "bundle cannot be encoded")


def _compact_bundle_bytes(proposal: Mapping[str, Any]) -> bytes:
    return encode_transaction_inspect_bundle({
        "operation_id": proposal["operation_id"],
        "operation_type": proposal["operation_type"],
        "writes": [
            {"path": item["path"], "mode": item["mode"], "sha256": item["sha256"]}
            for item in proposal["writes"]
        ],
        "expected_hashes": proposal["expected_hashes"],
        "read_preconditions": proposal["read_preconditions"],
    })


def _check_transaction_staging(document: Mapping[str, Any]) -> None:
    previous = ""
    for index, item in enumerate(document["content_files"]):
        digest = item["sha256"]
        if digest <= previous:
            _fail(
                CODE_STAGING_MISMATCH,
                f"/content_files/{index}/sha256",
                "content digests must be strictly ascending and unique",
            )
        if item["content_file"] != "transaction-inspect/content/" + digest:
            _fail(
                CODE_STAGING_MISMATCH,
                f"/content_files/{index}/content_file",
                "content file does not match digest",
            )
        previous = digest


def validate_transaction_staging(document: object) -> dict[str, object]:
    """Return an independent validated portable staging result."""
    return copy.deepcopy(validate_document(document, STAGING_SCHEMA))


def stage_transaction_inspect_transport(
    proposal: object,
    *,
    write_bytes: object,
    original_bytes: object,
    read_bytes: object,
    batch_id: object,
) -> dict[str, object]:
    """Validate and stage one facade proposal under the fixed local layout."""
    return _stage_transaction_inspect_transport(
        proposal, write_bytes=write_bytes, original_bytes=original_bytes,
        read_bytes=read_bytes, batch_id=batch_id, session=None,
    )


def _stage_transaction_inspect_transport(
    proposal: object,
    *,
    write_bytes: object,
    original_bytes: object,
    read_bytes: object,
    batch_id: object,
    session: _RetainedBatchSession | None,
) -> dict[str, object]:
    transaction = validate_transaction(proposal)
    if transaction["phase"] != "proposal":
        _fail(
            "TRANSACTION_UPSTREAM_MISMATCH",
            "/phase",
            "only proposal phase can be staged",
        )
    verify_transaction_bytes(
        transaction,
        write_bytes=write_bytes,
        original_bytes=original_bytes,
        read_bytes=read_bytes,
    )
    batch = validate_batch_id(batch_id)
    bundle = _compact_bundle_bytes(transaction)
    bundle_sha = hashlib.sha256(bundle).hexdigest()
    if bundle_sha != transaction["input_bundle_sha256"]:
        _fail(
            CODE_STAGING_MISMATCH,
            "/input_bundle_sha256",
            "bundle digest differs from proposal",
        )
    grouped: dict[str, bytes] = {}
    sizes: dict[str, int] = {}
    if type(write_bytes) is not dict:
        _fail("TRANSACTION_BYTES_MISMATCH", "/write_bytes", "write byte map changed")
    for write in transaction["writes"]:
        digest = write["sha256"]
        data = write_bytes[write["path"]]
        if digest in grouped and (
            grouped[digest] != data or sizes[digest] != write["size_bytes"]
        ):
            _fail(
                CODE_STAGING_MISMATCH,
                "/writes",
                "equal content digests have different payloads",
            )
        grouped[digest] = data
        sizes[digest] = write["size_bytes"]
    if len(bundle) < 1 or len(bundle) > MAX_BUNDLE_BYTES:
        _fail(
            CODE_TRANSACTION_LIMIT,
            "/bundle_size_bytes",
            "bundle exceeds the transaction staging limit",
        )
    ordered = tuple((digest, grouped[digest]) for digest in sorted(grouped))
    content_files = [
        {
            "content_file": "transaction-inspect/content/" + digest,
            "sha256": digest,
            "size_bytes": sizes[digest],
        }
        for digest, _data in ordered
    ]
    base: dict[str, object] = {
        "schema": STAGING_SCHEMA,
        "batch_id": batch,
        "operation_id": transaction["operation_id"],
        "operation_type": transaction["operation_type"],
        "transaction_declaration_sha256": transaction["declaration_sha256"],
        "bundle_file": "transaction-inspect/bundle.json",
        "bundle_sha256": bundle_sha,
        "bundle_size_bytes": len(bundle),
        "content_files": content_files,
        "already_staged": False,
    }
    validate_transaction_staging(base)
    reused_variant = copy.deepcopy(base)
    reused_variant["already_staged"] = True
    validate_transaction_staging(reused_variant)

    if session is None:
        staged = _stage_transaction_inspect_files(
            batch_id=batch, content=ordered, bundle=bundle,
        )
    else:
        if session.batch != batch:
            _fail(CODE_STAGING_MISMATCH, "/batch_id", "retained batch differs")
        staged = _stage_transaction_inspect_files_in_session(
            session, content=ordered, bundle=bundle,
        )
    result = copy.deepcopy(base)
    result["already_staged"] = (
        all(staged.content_already_staged) and staged.bundle_already_staged
    )
    return validate_transaction_staging(result)
