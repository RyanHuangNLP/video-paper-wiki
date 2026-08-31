"""Pure transaction declarations; supplied evidence never grants execution authority."""
from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from typing import Any

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize

TRANSACTION_SCHEMA = "video-paper-wiki.transaction-facade.v1"
HEAD_SCHEMA = "video-paper-wiki.operation-head.v1"
HEAD_PATH = "wiki/meta/registries/operation-head.json"
MAX_FILE_BYTES = 67108864
MAX_TOTAL_BYTES = 134217728
MAX_WRITES = 1024
_HASH = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_RECEIPT = re.compile(r"wiki/meta/operations/([0-9]{12})-([A-Za-z0-9][A-Za-z0-9._-]{0,127})\.json")
_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", re.I)
_EXCLUDED = frozenset({"phase", "declaration_sha256", "inspection", "runtime_result"})
_MATERIAL = frozenset({"schema", "operation_id", "operation_type", "writes", "expected_hashes", "read_preconditions", "claimed_inputs", "address_requests", "source_manifest_updates", "engine_expanded_paths", "receipt", "head", "input_bundle_sha256"})
_PREFIXES = ("wiki/papers/", "wiki/code/", "wiki/concepts/", "wiki/meta/ledgers/", "wiki/meta/records/", "wiki/meta/reviews/", "wiki/meta/gates/")


def _fail(code: str, pointer: str, message: str) -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _pointer(parent: str, key: object) -> str:
    return parent + "/" + str(key).replace("~", "~0").replace("/", "~1")


def _json_preflight(document: object) -> None:
    """Reject non-JSON Python values and cycles before entering jsonschema."""
    active: set[int] = set()
    stack = [(document, "", False)]
    while stack:
        value, pointer, leaving = stack.pop()
        if leaving:
            active.remove(id(value))
        elif type(value) in (dict, list):
            if id(value) in active:
                _fail("SCHEMA_INVALID", pointer, "cyclic JSON input")
            active.add(id(value))
            stack.append((value, pointer, True))
            if type(value) is dict:
                if any(type(key) is not str for key in value):
                    _fail("SCHEMA_INVALID", pointer, "object keys must be strings")
                stack.extend((item, _pointer(pointer, key), False) for key, item in value.items())
            else:
                stack.extend((item, _pointer(pointer, index), False) for index, item in enumerate(value))
        elif value is not None and type(value) not in (str, int, bool):
            _fail("SCHEMA_INVALID", pointer, "expected integer-only JSON data")


def _canonical(value: object) -> bytes:
    try:
        return canonicalize(value)
    except (CanonicalJsonError, RecursionError) as exc:
        _fail("CANONICAL_JSON_INVALID", "", str(exc))


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def transaction_declaration_hash(document: object) -> str:
    """Hash material only, without validating or authenticating upstream evidence."""
    if not isinstance(document, dict) or not _MATERIAL <= document.keys():
        _fail("SCHEMA_INVALID", "", "declaration material fields are required")
    return _sha(_canonical({key: value for key, value in document.items() if key not in _EXCLUDED}))


def _portable_key(component: str) -> str:
    return unicodedata.normalize("NFC", component.casefold())


def _path(path: str, pointer: str, *, new: bool = False) -> None:
    parts = path.split("/")
    try:
        length = len(path.encode("utf-8"))
    except UnicodeError:
        _fail("TRANSACTION_PATH_INVALID", pointer, "path contains a surrogate")
    if (not path or "\\" in path or any(p in {"", ".", ".."} for p in parts)
            or any(ord(c) < 32 or ord(c) == 127 for c in path)
            or unicodedata.normalize("NFC", path) != path or length > 1024
            or any(_portable_key(p) in {".git", ".obsidian", ".vault-meta"} for p in parts)):
        _fail("TRANSACTION_PATH_INVALID", pointer, "invalid lexical path")
    if new:
        # The only dot-leading authorized prefix is .raw; scope is checked below.
        for part in parts[1:] if parts[0] == ".raw" else parts:
            if not _COMPONENT.fullmatch(part) or part.endswith(".") or _DEVICE.fullmatch(part.split(".", 1)[0]):
                _fail("TRANSACTION_PATH_INVALID", pointer, "invalid portable destination component")


def _receipt_path(path: str, pointer: str) -> tuple[int, str]:
    _path(path, pointer, new=True)
    match = _RECEIPT.fullmatch(path)
    if match is None or int(match[1]) == 0:
        _fail("TRANSACTION_RECEIPT_MISMATCH", pointer, "invalid receipt filename")
    return int(match[1]), match[2]


def _check_operation_head(document: dict[str, Any]) -> None:
    sequence, _operation = _receipt_path(document["receipt_path"], "/receipt_path")
    if sequence != document["sequence"]:
        _fail("TRANSACTION_RECEIPT_MISMATCH", "/sequence", "head and receipt sequence differ")


def _business(path: str, digest: str, pointer: str, *, operation: str | None = None, mode: str | None = None) -> None:
    _path(path, pointer, new=True)
    captured = re.fullmatch(r"\.raw/captured/([0-9a-f]{64})\.([A-Za-z0-9][A-Za-z0-9._-]*)", path)
    if captured:
        if captured[1] != digest:
            _fail("TRANSACTION_PRECONDITION_MISMATCH", pointer, "captured filename digest differs")
        allowed = operation in {None, "capture"} and mode in {None, "create"}
    elif path.startswith(".raw/derived/") and len(path) > len(".raw/derived/"):
        allowed = operation in {None, "ingest"} and mode in {None, "create"}
    elif any(path.startswith(prefix) and len(path) > len(prefix) for prefix in _PREFIXES) or path == "wiki/meta/registries/gate-heads.json":
        allowed = operation in {None, "ingest", "generic"}
        if path.startswith(("wiki/meta/reviews/", "wiki/meta/gates/")) and mode not in {None, "create"}:
            allowed = False
    else:
        allowed = False
    if not allowed:
        _fail("TRANSACTION_POLICY_INVALID", pointer, "path or mode outside business authority")


def _collisions(entries: list[tuple[str, str]]) -> None:
    # A trie retains the original spelling of every ancestor, not just leaves.
    root: dict = {}
    for path, pointer in entries:
        node = root
        for part in path.split("/"):
            if None in node:
                _fail("TRANSACTION_PATH_COLLISION", pointer, "file is an ancestor of another path")
            key = _portable_key(part)
            if key in node and node[key][0] != part:
                _fail("TRANSACTION_PATH_COLLISION", pointer, "portable component aliases")
            if key not in node:
                node[key] = (part, {})
            node = node[key][1]
        if node:
            _fail("TRANSACTION_PATH_COLLISION", pointer, "duplicate or ancestor path")
        node[None] = True


def _strict_embedded_scalars(value: object, pointer: str = "") -> None:
    """Old embedded receipt regexes remain unchanged; facade checks full strings."""
    if isinstance(value, dict):
        for key, item in value.items():
            here = _pointer(pointer, key)
            if (key.endswith("sha256") and item is not None and not _HASH.fullmatch(item)):
                _fail("SCHEMA_INVALID", here, "expected full lowercase SHA-256")
            if key == "operation_id" and not _ID.fullmatch(item):
                _fail("SCHEMA_INVALID", here, "invalid bounded operation ID")
            if key == "sequence" and (type(item) is not int or not 1 <= item <= 999999999999):
                _fail("SCHEMA_INVALID", here, "invalid bounded sequence")
            _strict_embedded_scalars(item, here)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _strict_embedded_scalars(item, _pointer(pointer, index))


def _check_transaction(document: dict[str, Any]) -> None:
    for name in ("operation_id", "input_bundle_sha256", "declaration_sha256"):
        _strict_embedded_scalars({name: document[name]})
    if document["receipt"] is not None:
        _strict_embedded_scalars(document["receipt"], "/receipt")
    for name in ("inspection", "runtime_result"):
        if document[name] is not None:
            _strict_embedded_scalars({"operation_id": document[name]["operation_id"]}, "/" + name)
    writes = document["writes"]
    expected = document["expected_hashes"]
    reads = document["read_preconditions"]
    claims = document["claimed_inputs"]
    for index, write in enumerate(writes):
        _path(write["path"], f"/writes/{index}/path", new=True)
    for path in reads:
        _path(path, _pointer("/read_preconditions", path))
    for path in expected:
        _path(path, _pointer("/expected_hashes", path), new=True)
    for index, claim in enumerate(claims):
        _path(claim["path"], f"/claimed_inputs/{index}/path", new=True)
    if document["address_requests"] or document["source_manifest_updates"] or document["engine_expanded_paths"]:
        _fail("TRANSACTION_POLICY_INVALID", "/address_requests", "managed expansion is forbidden")
    paths = [write["path"] for write in writes]
    _collisions([(write["path"], f"/writes/{i}/path") for i, write in enumerate(writes)] + [(path, _pointer("/read_preconditions", path)) for path in reads])
    if set(paths) != set(expected):
        _fail("TRANSACTION_PRECONDITION_MISMATCH", "/expected_hashes", "expected keys must equal write paths")
    if not 1 <= len(writes) <= MAX_WRITES:
        _fail("TRANSACTION_LIMIT_EXCEEDED", "/writes", "write count outside budget")
    business = [write for write in writes if write["role"] == "business"]
    business_paths = [write["path"] for write in business]
    if business_paths != sorted(business_paths):
        _fail("TRANSACTION_ORDER_INVALID", "/writes", "business paths must be sorted")
    operation = document["operation_type"]
    for index, write in enumerate(writes):
        pointer = f"/writes/{index}"
        if write["role"] == "business":
            _business(write["path"], write["sha256"], pointer + "/path", operation=operation, mode=write["mode"])
        if max(write["size_bytes"], write["original_size_bytes"]) > MAX_FILE_BYTES:
            _fail("TRANSACTION_LIMIT_EXCEEDED", pointer, "file size exceeds budget")
        if write["mode"] == "create":
            valid = expected[write["path"]] is None and write["original_size_bytes"] == 0 and write["original_mode"] is None
        else:
            valid = expected[write["path"]] is not None and type(write["original_mode"]) is int
        if not valid:
            _fail("TRANSACTION_PRECONDITION_MISMATCH", pointer, "mode and original state differ")
    for field in ("size_bytes", "original_size_bytes"):
        if sum(write[field] for write in writes) > MAX_TOTAL_BYTES:
            _fail("TRANSACTION_LIMIT_EXCEEDED", "/writes", "total file bytes exceed budget")
    claim_paths = [claim["path"] for claim in claims]
    if len(set(claim_paths)) != len(claim_paths):
        _fail("TRANSACTION_PRECONDITION_MISMATCH", "/claimed_inputs", "duplicate claims")
    if claim_paths != sorted(claim_paths):
        _fail("TRANSACTION_ORDER_INVALID", "/claimed_inputs", "claims must be sorted")
    for index, claim in enumerate(claims):
        pointer = f"/claimed_inputs/{index}"
        _business(claim["path"], claim["sha256"], pointer + "/path")
        if reads.get(claim["path"]) != claim["sha256"]:
            _fail("TRANSACTION_PRECONDITION_MISMATCH", pointer, "claim requires equal non-null read digest")
    if operation == "capture":
        if claims or document["receipt"] is not None or document["head"] is not None or len(business) != len(writes):
            _fail("TRANSACTION_RECEIPT_MISMATCH", "/receipt", "capture cannot publish a receipt or claims")
    else:
        if not business or document["receipt"] is None or document["head"] is None:
            _fail("TRANSACTION_RECEIPT_MISMATCH", "/receipt", "publication requires business, receipt and head")
        if [write["role"] for write in writes] != ["business"] * len(business) + ["receipt", "head"]:
            _fail("TRANSACTION_ORDER_INVALID", "/writes", "receipt and head must finish the write list")
        _publication(document, business)
    if transaction_declaration_hash(document) != document["declaration_sha256"]:
        _fail("TRANSACTION_DECLARATION_MISMATCH", "/declaration_sha256", "declaration digest differs")
    _upstream(document)


def _publication(document: dict, business: list[dict]) -> None:
    receipt, head = document["receipt"], document["head"]
    validate_document(receipt, "video-paper-wiki.operation-receipt.v1")
    validate_document(head, HEAD_SCHEMA)
    rwrite, hwrite = document["writes"][-2:]
    expected = document["expected_hashes"]
    reads = document["read_preconditions"]
    sequence = receipt["sequence"]
    path = f"wiki/meta/operations/{sequence:012d}-{document['operation_id']}.json"
    projected = [{"path": w["path"], "mode": w["mode"], "before_sha256": expected[w["path"]], "after_sha256": w["sha256"]} for w in business]
    if (receipt["operation_id"] != document["operation_id"] or receipt["operation_type"] != document["operation_type"] or receipt["writes"] != projected or receipt["claimed_inputs"] != document["claimed_inputs"]):
        _fail("TRANSACTION_RECEIPT_MISMATCH", "/receipt", "receipt does not project transaction business data")
    if rwrite["path"] != path or rwrite["mode"] != "create" or hwrite["path"] != HEAD_PATH:
        _fail("TRANSACTION_RECEIPT_MISMATCH", "/writes", "publication paths or receipt mode differ")
    previous = receipt["previous"]
    if sequence == 1:
        if document["operation_type"] != "generic" or previous is not None or hwrite["mode"] != "create":
            _fail("TRANSACTION_RECEIPT_MISMATCH", "/receipt/previous", "invalid generic genesis")
    else:
        if previous is None or hwrite["mode"] != "replace":
            _fail("TRANSACTION_RECEIPT_MISMATCH", "/receipt/previous", "publication requires previous receipt and replacing head")
        prior_sequence, _ = _receipt_path(previous["path"], "/receipt/previous/path")
        if prior_sequence != sequence - 1 or reads.get(previous["path"]) != previous["sha256"]:
            _fail("TRANSACTION_RECEIPT_MISMATCH", "/receipt/previous", "previous sequence or read binding differs")
    receipt_bytes = _canonical(receipt)
    if head != {"schema": HEAD_SCHEMA, "sequence": sequence, "receipt_path": path, "receipt_sha256": _sha(receipt_bytes)}:
        _fail("TRANSACTION_RECEIPT_MISMATCH", "/head", "head does not identify receipt bytes")
    for descriptor, data in ((rwrite, receipt_bytes), (hwrite, _canonical(head))):
        if descriptor["sha256"] != _sha(data) or descriptor["size_bytes"] != len(data):
            _fail("TRANSACTION_RECEIPT_MISMATCH", "/writes", "receipt/head descriptor differs from canonical bytes")


def _upstream(document: dict) -> None:
    plan, result = document["inspection"], document["runtime_result"]
    if document["phase"] == "proposal":
        if plan is not None or result is not None:
            _fail("TRANSACTION_UPSTREAM_MISMATCH", "/phase", "proposal cannot contain inspection or result")
        return
    if plan is None:
        _fail("TRANSACTION_UPSTREAM_MISMATCH", "/inspection", "inspected phase requires plan")
    paths = [write["path"] for write in document["writes"]]
    hashes = {write["path"]: write["sha256"] for write in document["writes"]}
    modes = {write["path"]: 384 if write["mode"] == "create" else write["original_mode"] for write in document["writes"]}
    for name, evidence in (("inspection", plan), ("runtime_result", result)):
        if evidence is None:
            continue
        if any(evidence[key] != value for key, value in {"operation_id": document["operation_id"], "operation_type": document["operation_type"], "changed_paths": paths, "hashes": hashes, "modes": modes}.items()):
            _fail("TRANSACTION_UPSTREAM_MISMATCH", "/" + name, "upstream write declarations differ")
        key = "input_bundle_sha256" if name == "inspection" else "bundle_sha256"
        if evidence[key] != document["input_bundle_sha256"] or evidence["expanded_bundle_sha256"] != document["input_bundle_sha256"]:
            _fail("TRANSACTION_UPSTREAM_MISMATCH", "/" + name, "upstream bundle digests differ")
        if name == "runtime_result" and evidence["approval_sha256"] != plan["approval_sha256"]:
            _fail("TRANSACTION_UPSTREAM_MISMATCH", "/runtime_result/approval_sha256", "approval differs from inspection")


def validate_transaction(document: object) -> dict:
    """Return an independent validated copy without reading caller paths."""
    return copy.deepcopy(validate_document(document, TRANSACTION_SCHEMA))


def validate_operation_head(document: object) -> dict:
    """Validate only supplied head data, never follow its receipt path."""
    return copy.deepcopy(validate_document(document, HEAD_SCHEMA))


def attach_upstream_inspection(proposal: object, inspection: object) -> dict:
    result = validate_transaction(proposal)
    _json_preflight(inspection)
    if result["phase"] != "proposal":
        _fail("TRANSACTION_UPSTREAM_MISMATCH", "/phase", "inspection attaches only to proposal")
    result["phase"] = "inspected"
    result["inspection"] = inspection
    return validate_transaction(result)


def attach_runtime_result(inspected: object, result: object) -> dict:
    document = validate_transaction(inspected)
    _json_preflight(result)
    if document["phase"] != "inspected" or document["runtime_result"] is not None or result is None:
        _fail("TRANSACTION_UPSTREAM_MISMATCH", "/runtime_result", "result attaches only once to inspected data")
    document["runtime_result"] = result
    return validate_transaction(document)


def verify_transaction_bytes(document: object, *, write_bytes: object, original_bytes: object, read_bytes: object) -> None:
    """Compare exact supplied snapshots; absence never triggers a filesystem probe."""
    doc = validate_transaction(document)
    writes = {write["path"]: write for write in doc["writes"]}
    for name, value, keys in (("write_bytes", write_bytes, writes), ("original_bytes", original_bytes, writes), ("read_bytes", read_bytes, doc["read_preconditions"])):
        if type(value) is not dict or set(value) != set(keys) or any(type(key) is not str for key in value):
            _fail("TRANSACTION_BYTES_MISMATCH", "/" + name, "snapshot keys must match declarations")
    for path, write in writes.items():
        data = write_bytes[path]
        if type(data) is not bytes or len(data) != write["size_bytes"] or _sha(data) != write["sha256"]:
            _fail("TRANSACTION_BYTES_MISMATCH", _pointer("/write_bytes", path), "new bytes differ")
        if write["role"] in {"receipt", "head"} and data != _canonical(doc[write["role"]]):
            _fail("TRANSACTION_BYTES_MISMATCH", _pointer("/write_bytes", path), "publication bytes must be canonical")
        prior = original_bytes[path]
        digest = doc["expected_hashes"][path]
        if digest is None:
            valid = prior is None
        else:
            valid = type(prior) is bytes and len(prior) == write["original_size_bytes"] and _sha(prior) == digest
        if not valid:
            _fail("TRANSACTION_BYTES_MISMATCH", _pointer("/original_bytes", path), "original bytes differ")
    for path, digest in doc["read_preconditions"].items():
        data = read_bytes[path]
        if not (data is None if digest is None else type(data) is bytes and _sha(data) == digest):
            _fail("TRANSACTION_BYTES_MISMATCH", _pointer("/read_bytes", path), "read bytes differ")
