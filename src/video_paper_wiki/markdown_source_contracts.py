"""Closed Markdown-native handoff contracts; no PDF or code authority coercion."""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import PurePosixPath

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import is_canonical_paper_id
from video_paper_wiki.jcs import canonicalize

OBSERVATION = "video-paper-wiki.markdown-source-observation.v1"
PLAN = "video-paper-wiki.markdown-capture-plan.v1"
APPROVAL = "video-paper-wiki.markdown-capture-approval-ref.v1"
REQUEST = "video-paper-wiki.markdown-capture-request.v1"
AUTHORITY = "video-paper-wiki.markdown-capture-authority.v1"
SCHEMAS = frozenset({OBSERVATION, PLAN, APPROVAL, REQUEST, AUTHORITY})
LIMITS = {"max_markdown_bytes": 8388608, "max_metadata_bytes": 1048576,
          "max_pages": 300, "max_requests": 0}
PIPELINE = {"engine": "markdown-native", "version": "1", "normalization": "preserve-exact-utf8"}


def fail(code: str, message: str, pointer: str = "") -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(document: object) -> str:
    return sha(canonicalize(document))


def json_preflight(document: object) -> None:
    """Bound depth and reject floats, invalid Unicode and non-JSON Python values."""
    stack = [(document, 0)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if depth > 48 or count > 100000:
            fail("MARKDOWN_SOURCE_INVALID", "JSON structure exceeds limits")
        if type(value) is dict:
            for key, child in value.items():
                if type(key) is not str:
                    fail("MARKDOWN_SOURCE_INVALID", "JSON keys must be strings")
                stack.extend(((key, depth + 1), (child, depth + 1)))
        elif type(value) is list:
            stack.extend((child, depth + 1) for child in value)
        elif type(value) is str:
            try:
                value.encode("utf-8")
            except UnicodeError:
                fail("MARKDOWN_SOURCE_INVALID", "JSON contains invalid Unicode")
            if "\0" in value or len(value) > 8388608:
                fail("MARKDOWN_SOURCE_INVALID", "JSON string exceeds limits or contains NUL")
        elif value is not None and type(value) not in {bool, int}:
            fail("MARKDOWN_SOURCE_INVALID", "JSON permits only integer numbers")
        elif type(value) is int and abs(value) > 9007199254740991:
            fail("MARKDOWN_SOURCE_INVALID", "JSON integer exceeds exact range")


def validate(document: object, schema: str) -> dict:
    json_preflight(document)
    return copy.deepcopy(validate_document(document, schema))


def _observation(doc: dict) -> None:
    if not is_canonical_paper_id(doc["paper_id"]):
        fail("MARKDOWN_SOURCE_INVALID", "paper ID is not canonical")
    if not doc["title"].strip() or (doc["version"]["label"] is not None and not doc["version"]["label"].strip()):
        fail("MARKDOWN_SOURCE_INVALID", "title and declared version must contain text")
    previous = 0
    for number, page in enumerate(doc["pages"], 1):
        if (type(page["page"]) is not int or page["page"] != number
                or page["anchor"] != f"page-{number}"
                or not previous <= page["text_start"] <= page["text_end"] <= doc["markdown"]["size_bytes"]):
            fail("MARKDOWN_SOURCE_INVALID", "page sequence, anchor or character span differs")
        previous = page["text_end"]


def _plan(doc: dict) -> None:
    validate(doc["observation"], OBSERVATION)
    root = doc["workspace_root"]
    parts = root.split("/")
    if (not root.startswith("/") or any(p in {".", ".."} for p in parts)
            or "\\" in root or PurePosixPath(root).as_posix() != root or ".work" not in parts):
        fail("MARKDOWN_PLAN_INVALID", "workspace root is not an exact absolute .work path")
    light_sha = doc["observation"]["light_paper_id"].split(":", 1)[1]
    if (doc["source_markdown_path"] != f"papers/{light_sha}/source.md"
            or doc["source_metadata_path"] != f"papers/{light_sha}/source.json"
            or doc["limits"] != LIMITS or doc["pipeline"] != PIPELINE):
        fail("MARKDOWN_PLAN_INVALID", "plan does not bind fixed lightweight source slots")


def bind_approval(plan: dict, reference: object) -> dict:
    if reference is None:
        fail("MARKDOWN_APPROVAL_REQUIRED", "an external Markdown approval reference is required")
    ref = validate(reference, APPROVAL)
    expected = {"schema": APPROVAL, "plan_sha256": digest(plan), "batch_id": plan["batch_id"],
                "paper_id": plan["observation"]["paper_id"],
                "markdown_sha256": plan["observation"]["markdown"]["sha256"]}
    if ref != expected:
        fail("MARKDOWN_APPROVAL_MISMATCH", "external approval does not bind this exact plan")
    return ref


def _request(doc: dict) -> None:
    plan = validate(doc["plan"], PLAN)
    bind_approval(plan, doc["approval_ref"])
    if (doc["plan_sha256"] != digest(plan)
            or doc["approval_ref_sha256"] != digest(doc["approval_ref"])
            or doc["payload_file"] != f'markdown-source/{plan["observation"]["markdown"]["sha256"]}.md'):
        fail("MARKDOWN_REQUEST_MISMATCH", "request hash or payload slot differs")


def _authority(doc: dict) -> None:
    request = validate(doc["request"], REQUEST)
    payload = request["plan"]["observation"]["markdown"]
    target = f'.raw/captured/{payload["sha256"]}.md'
    if doc["request_sha256"] != digest(request) or doc["stored_path"] != target:
        fail("MARKDOWN_AUTHORITY_MISMATCH", "authority request or captured slot differs")
    expected_source = "src-" + sha(f'file\0{target}\0{payload["sha256"]}'.encode("utf-8"))[:20]
    if doc["source_id"] != expected_source:
        fail("MARKDOWN_AUTHORITY_MISMATCH", "source ID does not bind the file source identity")
    # The file source identity is independently verified against the pinned runtime
    # on inspect/admit. This pure contract cannot confer upstream execution authority.
    staging, upstream = doc["transaction_staging"], doc["upstream_authority"]
    if doc["disposition"] == "reuse":
        if staging is not None or upstream is not None:
            fail("MARKDOWN_AUTHORITY_MISMATCH", "reuse cannot carry child operation authorities")
        return
    if staging is None or upstream is None:
        fail("MARKDOWN_AUTHORITY_MISMATCH", "create requires both transaction authorities")
    validate_document(staging, "video-paper-wiki.transaction-staging.v1")
    validate_document(upstream, "video-paper-wiki.upstream-authority.v1")
    tx = upstream["transaction"]
    business = [{"path": target, "role": "business", "mode": "create", "sha256": payload["sha256"],
                 "size_bytes": payload["size_bytes"], "original_size_bytes": 0, "original_mode": None}]
    if (tx["operation_id"] != doc["requested_operation_id"] or tx["operation_type"] != "capture"
            or tx["phase"] != "inspected" or tx["runtime_result"] is not None
            or tx["writes"] != business or tx["expected_hashes"] != {target: None}
            or tx["read_preconditions"] or tx["claimed_inputs"] or tx["address_requests"]
            or tx["source_manifest_updates"] or tx["engine_expanded_paths"]
            or tx["receipt"] is not None or tx["head"] is not None
            or staging["batch_id"] != request["plan"]["batch_id"]
            or staging["operation_id"] != tx["operation_id"] or staging["operation_type"] != "capture"
            or staging["transaction_declaration_sha256"] != tx["declaration_sha256"]
            or staging["bundle_sha256"] != tx["input_bundle_sha256"]
            or staging["bundle_sha256"] != upstream["transport"]["bundle_sha256"]
            or staging["content_files"] != [{"content_file": "transaction-inspect/content/" + payload["sha256"],
                                             "sha256": payload["sha256"], "size_bytes": payload["size_bytes"]}]):
        fail("MARKDOWN_AUTHORITY_MISMATCH", "capture transaction layers do not bind exact Markdown create")


def check_document(document: dict, schema: str) -> None:
    json_preflight(document)
    checks = {OBSERVATION: _observation, PLAN: _plan, REQUEST: _request, AUTHORITY: _authority}
    if schema == APPROVAL:
        if not is_canonical_paper_id(document["paper_id"]):
            fail("MARKDOWN_APPROVAL_MISMATCH", "approval paper ID is not canonical")
    else:
        checks[schema](document)
