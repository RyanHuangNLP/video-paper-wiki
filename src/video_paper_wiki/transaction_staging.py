"""Pure transaction transport validation plus fixed local staging."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any, NoReturn

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.staging import (
    _stage_transaction_inspect_files,
    validate_batch_id,
)
from video_paper_wiki.transaction_contracts import (
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


def _compact_bundle_bytes(proposal: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            _bundle_value(proposal),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail(CODE_STAGING_MISMATCH, "/input_bundle_sha256", "bundle cannot be encoded")


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

    staged = _stage_transaction_inspect_files(
        batch_id=batch,
        content=ordered,
        bundle=bundle,
    )
    result = copy.deepcopy(base)
    result["already_staged"] = (
        all(staged.content_already_staged) and staged.bundle_already_staged
    )
    return validate_transaction_staging(result)
