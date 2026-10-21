"""Historical registration consistency from explicit bytes, without Vault reads.

The retained publisher must supply the complete audited receipt inventory and
correlate these bytes with real state. This module cannot authenticate a receipt.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json
from video_paper_wiki.source_semantics_contracts import (
    LIMIT, SHA, byte_map, calendar, fail, preflight, sha, source_id as derive_source_id,
)

CODE = "SOURCE_REGISTRATION_INVALID"
LEDGER = "wiki/meta/ledgers/source-ledger.json"
SID = re.compile(r"src-[A-Za-z0-9][A-Za-z0-9._-]*")
RECEIPT = re.compile(r"wiki/meta/operations/[0-9]{12}-[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json")
KINDS = {"document", "webpage", "dataset", "image", "audio", "video", "code",
         "conversation", "synthetic", "other"}
AUTHORITIES = {"official", "primary", "secondary", "community", "synthetic", "unknown"}
STATUSES = {"unreviewed", "active", "superseded", "rejected"}
REQUIRED = {"origin", "content_kind", "title", "authority", "review_status", "pages"}
OPTIONAL = {"content_sha256", "ingested_at", "retrieved_at", "refresh_due", "independence_key", "supersedes"}


def _bad(message, at=""):
    fail(CODE, message, at)


def _parse(raw, at, *, schema=None, exact=False):
    if type(raw) is not bytes:
        _bad("historical material requires exact bytes", at)
    if len(raw) > 16 * 1024 * 1024:
        fail(LIMIT, "historical object exceeds its byte limit", at)
    try:
        value = parse_strict_json(raw, invalid_code=CODE)
        preflight(value)
        if schema:
            validate_document(value, schema)
        if exact and raw != canonicalize(value):
            _bad("historical authority spelling is not exact canonical JSON", at)
        return value
    except SecureIOError as exc:
        if exc.details.get("reason") in {"depth", "integer"}:
            fail(LIMIT, "historical JSON exceeds its bound", at)
        _bad("historical object is malformed", at)
    except ContractError as exc:
        if exc.code == LIMIT:
            raise
        _bad("historical object is malformed", at + exc.details.get("instance_pointer", ""))


def _closed(value, required, optional=frozenset(), at=""):
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - optional:
        _bad("historical object fields differ from the closed projection", at)


def _text(value, at):
    if type(value) is not str or not value.strip():
        _bad("historical text must be nonempty", at)


def _path(value, at, *, wiki=False):
    _text(value, at)
    if (value.startswith("/") or "\\" in value or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(p in {"", ".", ".."} for p in value.split("/"))
            or (wiki and not value.startswith("wiki/"))):
        _bad("historical path is not canonical Vault-relative text", at)


def historical_source_ledger(raw):
    """Validate the bounded closed projection; this is not vendor authorization."""
    doc = _parse(raw, "/ledger_bytes")
    _closed(doc, {"schema", "generated_at", "sources"}, at="/ledger")
    if doc["schema"] != "claude-obsidian.source-ledger.v1" or type(doc["sources"]) is not dict:
        _bad("historical source ledger discriminator or sources differ", "/ledger")
    try:
        calendar(doc["generated_at"], timestamp=True)
        if len(doc["generated_at"]) != 20:
            _bad("ledger timestamp requires whole UTC seconds", "/ledger/generated_at")
        for sid, row in sorted(doc["sources"].items()):
            at = "/ledger/sources/" + sid
            if SID.fullmatch(sid) is None:
                _bad("historical source ID is unsafe", at)
            _closed(row, REQUIRED, OPTIONAL, at)
            _closed(row["origin"], {"kind", "locator"}, at=at + "/origin")
            origin = row["origin"]
            if type(origin["kind"]) is not str or origin["kind"] not in {"file", "url", "manual"}:
                _bad("unknown historical origin kind", at + "/origin/kind")
            _text(origin["locator"], at + "/origin/locator")
            if origin["kind"] == "file":
                _path(origin["locator"], at + "/origin/locator")
            elif origin["kind"] == "url":
                try:
                    parsed = urlsplit(origin["locator"])
                    parsed.port
                    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                            or parsed.password is not None or parsed.fragment
                            or any(c.isspace() for c in origin["locator"])):
                        raise ValueError
                except ValueError:
                    _bad("historical URL must be HTTPS without credentials or fragment", at + "/origin/locator")
            for field, allowed in (("content_kind", KINDS), ("authority", AUTHORITIES), ("review_status", STATUSES)):
                if type(row[field]) is not str or row[field] not in allowed:
                    _bad("historical source enum is outside its profile", at + "/" + field)
            if (row["content_kind"] == "synthetic") != (row["authority"] == "synthetic"):
                _bad("synthetic content and authority must agree", at + "/authority")
            _text(row["title"], at + "/title")
            value = row.get("content_sha256")
            if value is not None and (type(value) is not str or SHA.fullmatch(value) is None):
                _bad("historical content hash is invalid", at + "/content_sha256")
            for field in ("ingested_at", "retrieved_at", "refresh_due"):
                if row.get(field) is not None:
                    calendar(row[field], at + "/" + field, timestamp=False)
            observed = row.get("retrieved_at") or row.get("ingested_at")
            if observed and row.get("refresh_due") and row["refresh_due"] < observed:
                _bad("refresh date precedes historical observation", at + "/refresh_due")
            if type(row["pages"]) is not list:
                _bad("historical pages must be an array", at + "/pages")
            for number, page in enumerate(row["pages"]):
                _path(page, at + f"/pages/{number}", wiki=True)
            if row.get("independence_key") is not None:
                _text(row["independence_key"], at + "/independence_key")
            if row.get("supersedes") is not None and (type(row["supersedes"]) is not str or not SID.fullmatch(row["supersedes"])):
                _bad("historical supersedes identifier is invalid", at + "/supersedes")
    except ContractError as exc:
        if exc.code in (CODE, LIMIT):
            raise
        _bad("historical ledger field is invalid", exc.details.get("instance_pointer", "/ledger"))
    return doc


def receipt_chain(head_bytes, receipt_bytes):
    """Return the complete chronological supplied chain, after exact replay."""
    try:
        byte_map(receipt_bytes, "/receipt_bytes", maximum=1024 * 1024)
    except ContractError as exc:
        if exc.code == LIMIT:
            raise
        _bad("receipts must be a path-to-bytes map", "/receipt_bytes")
    if type(head_bytes) is bytes and len(head_bytes) > 1024 * 1024:
        fail(LIMIT, "head exceeds its byte bound", "/head_bytes")
    head = _parse(head_bytes, "/head_bytes", schema="video-paper-wiki.operation-head.v1", exact=True)
    if head["sequence"] > 8192:
        fail(LIMIT, "receipt sequence exceeds the pure inventory bound", "/head_bytes/sequence")
    parsed = {}
    for path, raw in sorted(receipt_bytes.items()):
        if RECEIPT.fullmatch(path) is None:
            _bad("receipt filename does not use the canonical grammar", "/receipt_bytes")
        doc = _parse(raw, "/receipt_bytes/" + path, schema="video-paper-wiki.operation-receipt.v1", exact=True)
        if (path != f"wiki/meta/operations/{doc['sequence']:012d}-{doc['operation_id']}.json"
                or doc["intent_sha256"] != receipt_intent_sha256(doc)):
            _bad("receipt filename or intent identity differs", "/receipt_bytes/" + path)
        for field in ("writes", "claimed_inputs"):
            names = [item["path"] for item in doc[field]]
            if len(names) != len(set(names)):
                _bad("receipt repeats a path within one operation role", "/receipt_bytes/" + path)
        parsed[path] = doc
    path, checksum, chain, seen = head["receipt_path"], head["receipt_sha256"], [], set()
    while path is not None:
        if path in seen or path not in parsed or sha(receipt_bytes[path]) != checksum:
            _bad("receipt edge is absent, cyclic or has different bytes", "/receipt_bytes")
        seen.add(path)
        doc = parsed[path]
        chain.append((path, doc))
        previous = doc["previous"]
        path, checksum = (None, None) if previous is None else (previous["path"], previous["sha256"])
    if seen != set(receipt_bytes) or [x[1]["sequence"] for x in chain] != list(range(head["sequence"], 0, -1)):
        _bad("complete receipt sequence has gaps, orphans or rollback", "/receipt_bytes")
    chain.reverse()
    state = {}
    for path, doc in chain:
        for item in doc["claimed_inputs"]:
            key = item["path"]
            known = state.get(key)
            if known is not None and known != item["sha256"]:
                _bad("receipt claim differs from the replay state", "/receipt_bytes/" + path)
            if known is None:
                pristine = doc["sequence"] == 1 and key in {LEDGER, "wiki/meta/ledgers/claim-ledger.json"}
                match = re.fullmatch(r"\.raw/captured/([0-9a-f]{64})\.[A-Za-z0-9][A-Za-z0-9._-]*", key)
                if not pristine and not (match and match[1] == item["sha256"]):
                    _bad("receipt introduces an unknown claimed input", "/receipt_bytes/" + path)
                state[key] = item["sha256"]
        for item in doc["writes"]:
            known = state.get(item["path"])
            if ((item["mode"] == "create" and (known is not None or item["before_sha256"] is not None))
                    or (item["mode"] == "replace" and known != item["before_sha256"])):
                _bad("receipt write precondition differs from replay state", "/receipt_bytes/" + path)
            state[item["path"]] = item["after_sha256"]
    return chain


def registration_proof(raw, source_id, *, head_bytes, receipt_bytes, ledger_bytes):
    preflight({"raw": raw, "source_id": source_id})
    if (type(raw) is not dict or set(raw) != {"path", "sha256", "size_bytes"}
            or type(raw.get("sha256")) is not str or not SHA.fullmatch(raw["sha256"])
            or type(raw.get("size_bytes")) is not int or not 1 <= raw["size_bytes"] <= 8388608
            or raw.get("path") != f".raw/captured/{raw['sha256']}.md"
            or type(source_id) is not str or source_id != derive_source_id(raw)):
        _bad("registration source identity is invalid", "/raw")
    chain = receipt_chain(head_bytes, receipt_bytes)
    first = None
    for path, receipt in chain:
        claims = [x for x in receipt["claimed_inputs"] if x["path"] == raw["path"]]
        writes = [x for x in receipt["writes"] if x["path"] == raw["path"]]
        if not claims and not writes:
            continue
        ledger_writes = [x for x in receipt["writes"] if x["path"] == LEDGER]
        if (writes or len(claims) != 1 or claims[0]["sha256"] != raw["sha256"]
                or receipt["operation_type"] != "ingest" or len(ledger_writes) != 1):
            _bad("earliest raw receipt is not source registration", "/receipt_bytes/" + path)
        first = path, ledger_writes[0]["after_sha256"]
        break
    if first is None:
        _bad("source has no registration receipt", "/receipt_bytes")
    if any(item["path"] == raw["path"] for _, receipt in chain for item in receipt["writes"]):
        _bad("a receipt writes the immutable registered captured path", "/receipt_bytes")
    ledger = historical_source_ledger(ledger_bytes)
    if sha(ledger_bytes) != first[1]:
        _bad("historical ledger bytes differ from first registration write", "/ledger_bytes")
    target = ledger["sources"].get(source_id)
    if (target is None or set(target) != REQUIRED | OPTIONAL
            or target["origin"] != {"kind": "file", "locator": raw["path"]}
            or target["content_sha256"] != raw["sha256"] or target["content_kind"] != "document"
            or target["authority"] != "primary" or target["ingested_at"] is None):
        _bad("source ledger row does not bind the registered Markdown", "/ledger_bytes")
    for sid, row in ledger["sources"].items():
        if sid != source_id and (row["origin"]["locator"] == raw["path"] or row.get("content_sha256") == raw["sha256"]):
            _bad("source path or hash has another ledger identity", "/ledger_bytes")
    return {"receipt_path": first[0], "receipt_sha256": sha(receipt_bytes[first[0]]),
            "source_ledger_path": f".raw/derived/source-ledgers/{first[1]}.json",
            "source_ledger_sha256": first[1]}
