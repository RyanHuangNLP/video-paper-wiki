"""Closed source publication transports; parsed consistency is not apply authority."""
from __future__ import annotations

import copy
import re

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source_contracts import AUTHORITY as CAPTURE, validate as capture_validate
from video_paper_wiki.operation_result import validate_operation_result_authority
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json
from video_paper_wiki.source_semantics_contracts import calendar, fail, preflight, sha
from video_paper_wiki.staging import validate_batch_id
from video_paper_wiki.transaction_contracts import _collisions, _path

REQUEST = "video-paper-wiki.source-publication-request.v1"
AUTHORITY = "video-paper-wiki.source-publication-authority.v1"
PROPOSAL = "video-paper-wiki.source-publication-proposal.v1"
HEADS = "video-paper-wiki.assessment-heads.v2"
SCHEMAS = frozenset({REQUEST, AUTHORITY, PROPOSAL, HEADS})
INVALID = "SOURCE_PUBLICATION_INVALID"
MAX_JSON = 8 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_PAYLOADS = 1022
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
HEX = re.compile(r"[0-9a-f]{64}")
SOURCE_LEDGER = "wiki/meta/ledgers/source-ledger.json"
CLAIM_LEDGER = "wiki/meta/ledgers/claim-ledger.json"
ASSESSMENT_HEADS = "wiki/meta/records/assessment-heads.json"
DISPLAY_HEADS = "wiki/meta/records/source-display-heads.json"
PATTERNS = {
    "paper": re.compile(r"wiki/meta/records/papers/[A-Za-z0-9][A-Za-z0-9._-]*\.json"),
    "repo": re.compile(r"wiki/meta/records/repos/[A-Za-z0-9][A-Za-z0-9._-]*\.json"),
    "event": re.compile(r"wiki/meta/reviews/(clm-[0-9a-f]{20})/(ase-[0-9a-f]{20})\.json"),
    "association": re.compile(r"wiki/meta/records/source-versions/(sva-[0-9a-f]{64})\.json"),
    "decision": re.compile(r"wiki/meta/reviews/source-display/(svd-[0-9a-f]{64})\.json"),
    "snapshot": re.compile(r"\.raw/derived/source-ledgers/([0-9a-f]{64})\.json"),
    "observation": re.compile(r"\.raw/derived/markdown-source/([0-9a-f]{64})/([0-9a-f]{64})\.json"),
    "page": re.compile(r"wiki/(?:papers|code|concepts)/[A-Za-z0-9][A-Za-z0-9._-]*\.md"),
}
IMMUTABLE = frozenset({"event", "association", "decision", "snapshot", "observation"})
WRITABLE = frozenset({"paper", "event", "association", "decision", "snapshot", "observation",
                      "page", "source", "claim", "assessment_heads", "display_heads"})


def invalid(message, pointer=""):
    fail(INVALID, message, pointer)


def operation_name(value):
    if type(value) is not str or ID.fullmatch(value) is None:
        invalid("operation ID is not a bounded portable name", "/operation_id")
    return value


def kind_for_path(path):
    exact = {SOURCE_LEDGER: "source", CLAIM_LEDGER: "claim",
             ASSESSMENT_HEADS: "assessment_heads", DISPLAY_HEADS: "display_heads"}
    if path in exact:
        return exact[path]
    return next((kind for kind, pattern in PATTERNS.items() if pattern.fullmatch(path)), None)


def publication_path(path, pointer="/payloads"):
    if type(path) is not str:
        invalid("payload path must be text", pointer)
    try:
        _path(path, pointer, new=True)
    except ContractError as exc:
        invalid(exc.message, pointer)
    if kind_for_path(path) not in WRITABLE:
        invalid("path is outside source publication authority", pointer)
    return path


def parse_json(raw, *, schema=None, exact=False, pointer="", maximum=MAX_JSON):
    if type(raw) is not bytes or len(raw) > maximum:
        invalid("JSON bytes exceed the closed input limit", pointer)
    try:
        doc = parse_strict_json(raw, invalid_code=INVALID)
        preflight(doc)
        if schema:
            doc = validate(doc, schema)
        if exact and canonicalize(doc) != raw:
            invalid("JSON spelling is not exact canonical form", pointer)
        return doc
    except SecureIOError as exc:
        if exc.details.get("reason") in {"depth", "integer"}:
            fail("SOURCE_SEMANTICS_LIMIT", "publication JSON exceeds structural bounds", pointer)
        invalid("input is not bounded strict UTF-8 JSON", pointer + exc.details.get("instance_pointer", ""))
    except ContractError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        invalid("input is not bounded strict UTF-8 JSON", pointer)


def validate_registration(value):
    preflight(value)
    if type(value) is not dict or set(value) != {"authority", "capture_result", "ingested_at"}:
        invalid("registration fields differ", "/registration")
    calendar(value["ingested_at"], "/registration/ingested_at")
    if len(value["ingested_at"]) != 20:
        invalid("ingested_at requires whole UTC seconds", "/registration/ingested_at")
    authority = capture_validate(value["authority"], CAPTURE)
    proof = validate_operation_result_authority(value["capture_result"])
    observed = proof["vault_after"].get(authority["stored_path"])
    if type(observed) is not dict or type(observed.get("mode")) is not int:
        invalid("capture result has no matching after-state", "/registration/capture_result")
    from video_paper_wiki.markdown_source import _capture_proof
    _capture_proof(authority, proof, mode=observed["mode"])
    return copy.deepcopy(value)


def payload_map(value):
    if type(value) is not dict or any(type(k) is not str or type(v) is not bytes for k, v in value.items()):
        invalid("payloads must be an exact path-to-bytes map", "/payloads")
    if len(value) > MAX_PAYLOADS or any(len(v) > MAX_FILE for v in value.values()) or sum(map(len, value.values())) > MAX_TOTAL:
        fail("TRANSACTION_LIMIT_EXCEEDED", "proposed business bytes exceed the publication limit", "/payloads")
    for path in value:
        publication_path(path)
    _collisions([(p, "/payloads") for p in value])
    return dict(sorted(value.items(), key=lambda x: x[0].encode()))


def _payloads(doc, *, proposal=False):
    paths = []
    total = 0
    digest_sizes = {}
    for index, item in enumerate(doc["payloads"]):
        pointer = f"/payloads/{index}"
        paths.append(publication_path(item["path"], pointer + "/path"))
        if proposal:
            name = item["content_file"]
            if not name.startswith("content/") or HEX.fullmatch(name[8:]) is None:
                invalid("proposal payload must use a digest-named sibling content slot", pointer)
        else:
            if item["content_file"] != "source-publication/content/" + item["sha256"]:
                invalid("request content slot differs from its digest", pointer)
            total += item["size_bytes"]
            if item["sha256"] in digest_sizes and digest_sizes[item["sha256"]] != item["size_bytes"]:
                invalid("one digest cannot declare different payload sizes", pointer)
            digest_sizes[item["sha256"]] = item["size_bytes"]
    if paths != sorted(set(paths), key=lambda p: p.encode()):
        invalid("payload paths must be unique and strictly sorted", "/payloads")
    _collisions([(p, "/payloads") for p in paths])
    if total > MAX_TOTAL:
        fail("TRANSACTION_LIMIT_EXCEEDED", "declared payload total exceeds the limit", "/payloads")


def _kind(doc):
    if (doc["kind"] == "knowledge") != (doc["registration"] is None):
        invalid("kind and registration branch differ", "/registration")
    if doc["registration"] is not None:
        validate_registration(doc["registration"])


def _authority(doc):
    req = validate(doc["request"], REQUEST)
    if doc["request_sha256"] != sha(canonicalize(req)) or doc["prospective_inventory_sha256"] != req["prospective_inventory_sha256"]:
        invalid("authority request or prospective digest differs")
    tx = validate_document(doc["transaction"], "video-paper-wiki.transaction-facade.v1")
    stage = validate_document(doc["transaction_staging"], "video-paper-wiki.transaction-staging.v1")
    upstream = validate_document(doc["upstream_authority"], "video-paper-wiki.upstream-authority.v1")
    actual = [{k: w[k] for k in ("path", "sha256", "size_bytes")} for w in tx["writes"] if w["role"] == "business"]
    expected = [{k: p[k] for k in ("path", "sha256", "size_bytes")} for p in req["payloads"]]
    claims = []
    if req["kind"] == "registration":
        authority = req["registration"]["authority"]
        claims = [{"path": authority["stored_path"], "mode": "read",
                   "sha256": authority["request"]["plan"]["observation"]["markdown"]["sha256"]}]
    if (tx["phase"] != "inspected" or tx["runtime_result"] is not None
            or tx["operation_type"] != "ingest" or tx["operation_id"] != req["operation_id"]
            or tx != upstream["transaction"] or actual != expected or tx["claimed_inputs"] != claims
            or tx["receipt"] is None or tx["head"] is None
            or tx["receipt"]["operation_type"] != "ingest"
            or stage["batch_id"] != req["batch_id"] or stage["operation_id"] != req["operation_id"]
            or stage["operation_type"] != "ingest"
            or stage["transaction_declaration_sha256"] != tx["declaration_sha256"]
            or stage["bundle_sha256"] != tx["input_bundle_sha256"]
            or stage["bundle_sha256"] != upstream["transport"]["bundle_sha256"]):
        invalid("source publication transaction layers differ")
    from video_paper_wiki.receipt_audit import HEAD
    if tx["expected_hashes"].get(HEAD) != req["basis"]["operation_head_sha256"]:
        invalid("transaction head precondition differs from request basis", "/request/basis")


def check_document(doc, schema):
    preflight(doc)
    if schema == HEADS:
        return
    if schema == AUTHORITY:
        _authority(doc)
        return
    _kind(doc)
    _payloads(doc, proposal=schema == PROPOSAL)
    if schema == REQUEST:
        validate_batch_id(doc["batch_id"])
        operation_name(doc["operation_id"])
        if doc["registration"] is not None:
            authority = doc["registration"]["authority"]
            proof = doc["registration"]["capture_result"]
            if (doc["batch_id"] == authority["request"]["plan"]["batch_id"]
                    or doc["operation_id"] in {authority["requested_operation_id"], proof["transaction"]["operation_id"]}):
                invalid("registration needs a distinct capture batch and operation")


def validate(doc, schema):
    preflight(doc)
    return copy.deepcopy(validate_document(doc, schema))
