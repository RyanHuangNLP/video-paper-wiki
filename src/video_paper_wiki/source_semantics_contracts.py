"""Pure closed source-version contracts; supplied consistency is not authority."""
from __future__ import annotations

import copy
import hashlib
import math
import re
from datetime import date, datetime

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import assessment_event_id, is_canonical_paper_id
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source_contracts import OBSERVATION

ASSOCIATION = "video-paper-wiki.source-version-association.v1"
DECISION = "video-paper-wiki.source-display-decision.v1"
HEADS = "video-paper-wiki.source-display-heads.v1"
PAPER = "video-paper-wiki.paper-record.v2"
LOCATOR = "video-paper-wiki.ledger-locator.v2"
EVENT = "video-paper-wiki.assessment-event.v2"
COMPILE = "video-paper-wiki.compile-input.v2"
SCHEMAS = frozenset({ASSOCIATION, DECISION, HEADS, PAPER, LOCATOR, EVENT, COMPILE})
INVALID = "SOURCE_SEMANTICS_INVALID"
LIMIT = "SOURCE_SEMANTICS_LIMIT"
SHA = re.compile(r"[0-9a-f]{64}")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z")
MAX_BYTES = 8 * 1024 * 1024


def fail(code: str, message: str, pointer: str = "", *, exit_code: int = 2, **details):
    raise ContractError(code, message, {"instance_pointer": pointer, **details}, exit_code=exit_code)


def pointer(base, key):
    return base + "/" + str(key).replace("~", "~0").replace("/", "~1")


_EVIDENCE_POSITIONS = {
    "item": re.compile(r""),
    "list": re.compile(r"/[0-9]+"),
    "claim": re.compile(r"/evidence/[0-9]+"),
    "history": re.compile(r"/claims/[0-9]+/evidence/[0-9]+"),
    "compile": re.compile(r"(?:/papers/[0-9]+/claims/[0-9]+/evidence/[0-9]+|/code/[0-9]+/alignment/officiality/evidence/[0-9]+)"),
}


def preflight(value, *, evidence_scope=None):
    """Bound a JSON tree, optionally admitting legacy bbox only at declared slots."""
    positions = _EVIDENCE_POSITIONS.get(evidence_scope)
    stack = [(value, "", 0, False, False)]
    active, count = set(), 0
    while stack:
        item, at, depth, leaving, bbox_values = stack.pop()
        if leaving:
            active.remove(id(item))
            continue
        count += 1
        if depth > 48 or count > 100000:
            fail(LIMIT, "source semantics structure exceeds its bound", at)
        if type(item) in (dict, list):
            if id(item) in active:
                fail(INVALID, "source semantics input contains a cycle", at)
            active.add(id(item))
            stack.append((item, at, depth, True, False))
            if type(item) is dict:
                if any(type(k) is not str for k in item):
                    fail(INVALID, "object keys must be exact strings", at)
                legacy_pdf = (positions is not None and positions.fullmatch(at) is not None
                              and type(item.get("kind")) is str and item["kind"] == "pdf")
                for key in reversed(sorted(item)):
                    bbox = legacy_pdf and key == "bbox" and type(item[key]) is list and len(item[key]) == 4
                    stack.append((item[key], pointer(at, key), depth + 1, False, bbox))
                    stack.append((key, pointer(at, key), depth + 1, False, False))
            else:
                stack.extend((x, pointer(at, i), depth + 1, False, bbox_values and type(x) is float)
                             for i, x in reversed(list(enumerate(item))))
        elif type(item) is str:
            try:
                raw = item.encode("utf-8")
            except UnicodeError:
                fail(INVALID, "text contains a non-scalar Unicode value", at)
            if "\0" in item:
                fail(INVALID, "text contains NUL", at)
            if len(raw) > MAX_BYTES:
                fail(LIMIT, "text exceeds its byte bound", at)
        elif type(item) is int:
            if abs(item) > 9007199254740991:
                fail(LIMIT, "integer exceeds exact JSON range", at)
        elif type(item) is float and bbox_values and math.isfinite(item):
            pass
        elif item is not None and type(item) is not bool:
            fail(INVALID, "value is not an exact integer JSON tree", at)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest(value) -> str:
    preflight(value)
    return sha(canonicalize(value))


def calendar(value, at="", *, timestamp=True):
    pattern = UTC if timestamp else re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
    if type(value) is not str or not pattern.fullmatch(value):
        fail("SCHEMA_INVALID", "date must use the canonical UTC/date grammar", at)
    try:
        if timestamp:
            datetime(int(value[:4]), int(value[5:7]), int(value[8:10]),
                     int(value[11:13]), int(value[14:16]), int(value[17:19]))
        else:
            date.fromisoformat(value)
    except ValueError:
        fail("SCHEMA_INVALID", "date is not a real Gregorian date", at)
    # Nine fractional digits compare without float rounding or ambient timezone.
    return value[:19] + "." + (value[20:-1] if len(value) > 20 else "").ljust(9, "0")


def validate(value, schema):
    preflight(value, evidence_scope="compile" if schema == COMPILE else None)
    try:
        return copy.deepcopy(validate_document(value, schema))
    except ContractError as exc:
        if "instance_pointer" in exc.details:
            raise
        raise ContractError(exc.code, exc.message, {"instance_pointer": "", **exc.details}, exit_code=exc.exit_code) from exc


def validate_shape(value, schema):
    """Check closed JSON shape before constructing a content-derived identity."""
    from video_paper_wiki.contracts import _raise_validation_error, _validator_for, schema_by_title
    preflight(value, evidence_scope="compile" if schema == COMPILE else None)
    errors = list(_validator_for(schema_by_title(schema)).iter_errors(value))
    if errors:
        errors.sort(key=lambda error: (tuple(str(x) for x in error.absolute_path), str(error.validator)))
        _raise_validation_error(errors[0], schema)


def association_id(value):
    preflight(value)
    if type(value) is not dict:
        fail("SOURCE_ASSOCIATION_INVALID", "association identity requires an object")
    return "sva-" + digest({k: v for k, v in value.items() if k != "association_id"})


def decision_id(value):
    preflight(value)
    if type(value) is not dict:
        fail("SOURCE_DISPLAY_INVALID", "display identity requires an object")
    return "svd-" + digest({k: v for k, v in value.items() if k != "decision_id"})


def association_reference(value):
    doc = validate(value, ASSOCIATION)
    return {"association_id": doc["association_id"], "sha256": digest(doc)}


def decision_reference(value):
    doc = validate(value, DECISION)
    return {"decision_id": doc["decision_id"], "sha256": digest(doc)}


def source_id(raw):
    preflight(raw)
    if (type(raw) is not dict or type(raw.get("path")) is not str
            or type(raw.get("sha256")) is not str or SHA.fullmatch(raw["sha256"]) is None):
        fail("SOURCE_ASSOCIATION_INVALID", "source identity requires a path and content hash")
    return "src-" + sha(f"file\0{raw['path']}\0{raw['sha256']}".encode())[:20]


def extraction_descriptor(observation):
    preflight(observation)
    raw = canonicalize(validate_document(observation, OBSERVATION))
    checksum = sha(raw)
    return {"path": f".raw/derived/markdown-source/{observation['markdown']['sha256']}/{checksum}.json",
            "sha256": checksum, "size_bytes": len(raw)}


def _nonempty(value, at):
    if not value.strip():
        fail("SCHEMA_INVALID", "text must contain a non-whitespace character", at)


def _association(doc):
    observation = validate_document(doc["observation"], OBSERVATION)
    raw = doc["raw"]
    if (doc["paper_id"] != observation["paper_id"] or doc["version"] != observation["version"]
            or {k: raw[k] for k in ("sha256", "size_bytes")} != observation["markdown"]
            or raw["path"] != f".raw/captured/{raw['sha256']}.md"
            or doc["source_id"] != source_id(raw)
            or doc["extraction"] != extraction_descriptor(observation)
            or doc["registration"]["source_ledger_path"] !=
            f".raw/derived/source-ledgers/{doc['registration']['source_ledger_sha256']}.json"):
        fail("SOURCE_ASSOCIATION_INVALID", "association fields do not bind the exact source")
    if doc["association_id"] != association_id(doc):
        fail("SOURCE_ASSOCIATION_INVALID", "association content identity differs", "/association_id")


def _decision(doc):
    calendar(doc["decided_at"], "/decided_at")
    for obj, field, at in ((doc, "reason", "/reason"), (doc["actor"], "identity", "/actor/identity"),
                           (doc["choice"], "reference", "/choice/reference"), (doc["choice"], "text", "/choice/text")):
        _nonempty(obj[field], at)
    if not is_canonical_paper_id(doc["paper_id"]):
        fail("SOURCE_DISPLAY_INVALID", "display paper identity is invalid", "/paper_id")
    if (doc["sequence"] == 1) != (doc["previous_decision_id"] is None):
        fail("SOURCE_DISPLAY_INVALID", "genesis and sequence disagree", "/previous_decision_id")
    if doc["decision_id"] != decision_id(doc):
        fail("SOURCE_DISPLAY_INVALID", "display decision identity differs", "/decision_id")


def _heads(doc):
    ids = [x["paper_id"] for x in doc["heads"]]
    if ids != sorted(set(ids)) or any(not is_canonical_paper_id(x) for x in ids):
        fail("SOURCE_DISPLAY_INVALID", "display head papers must be unique and sorted", "/heads")


def _paper(doc):
    from video_paper_wiki.contracts import _check_paper_record_object

    try:
        _check_paper_record_object(doc)
    except ContractError as exc:
        raise ContractError(exc.code, exc.message, {"instance_pointer": "/paper_id", **exc.details}, exit_code=exc.exit_code) from exc
    for field in ("created_at", "updated_at"):
        calendar(doc[field], "/" + field)
    calendar(doc["published_at"], "/published_at", timestamp="T" in doc["published_at"])
    if calendar(doc["created_at"]) > calendar(doc["updated_at"]):
        fail("SCHEMA_INVALID", "update precedes record creation", "/updated_at")
    ids = [x["association_id"] for x in doc["source_associations"]]
    if ids != sorted(set(ids)):
        fail("SOURCE_ASSOCIATION_INVALID", "record association refs must be unique and sorted", "/source_associations")
    if doc["source_ids"] != sorted(set(doc["source_ids"])):
        fail("SOURCE_ASSOCIATION_INVALID", "record source IDs must be unique and sorted", "/source_ids")
    selected = doc["display_head"] is not None
    if any((doc[k] is not None) != selected for k in ("active_extraction_path", "active_extraction_sha256")):
        fail("SOURCE_DISPLAY_INVALID", "display selection and active extraction mirrors disagree")


def _locator(doc):
    loc = doc["locator"]
    if (loc["charspan"][0] >= loc["charspan"][1]
            or loc["path"] != f".raw/captured/{loc['sha256']}.md"
            or loc["source_id"] != source_id(loc)):
        fail("MARKDOWN_LOCATOR_INVALID", "Markdown locator identity or interval differs", "/locator")


def _event(doc):
    calendar(doc["decided_at"], "/decided_at")
    _nonempty(doc["reason"], "/reason")
    _nonempty(doc["decided_by"], "/decided_by")
    if doc["event_id"] != assessment_event_id(doc):
        fail("EVENT_ID_MISMATCH", "assessment event content identity differs", "/event_id")


def _compile_calendar(doc):
    # Root schema validation has already established every field's closed shape.
    # Validate calendar values before any cross-object owner or graph edge.
    for index, group in enumerate(doc["papers"]):
        base = f"/papers/{index}"
        record = group["record"]
        if record["schema"] == PAPER:
            for field in ("created_at", "updated_at"):
                calendar(record[field], base + "/record/" + field)
            calendar(record["published_at"], base + "/record/published_at", timestamp="T" in record["published_at"])
            if calendar(record["created_at"]) > calendar(record["updated_at"]):
                fail("SCHEMA_INVALID", "update precedes record creation", base + "/record/updated_at")
            for number, decision in enumerate(group["display_decisions"]):
                calendar(decision["decided_at"], base + f"/display_decisions/{number}/decided_at")
        for number, claim in enumerate(group["claims"]):
            if claim["reviewed_at"] is not None:
                calendar(claim["reviewed_at"], base + f"/claims/{number}/reviewed_at", timestamp=False)
        for number, event in enumerate(group["events"]):
            calendar(event["decided_at"], base + f"/events/{number}/decided_at")


def check_document(doc, schema):
    {ASSOCIATION: _association, DECISION: _decision, HEADS: _heads,
     PAPER: _paper, LOCATOR: _locator, EVENT: _event, COMPILE: _compile_calendar}[schema](doc)


def byte_map(value, at, *, maximum=MAX_BYTES, total_limit=256 * 1024 * 1024):
    if type(value) is not dict or any(type(k) is not str or type(v) is not bytes for k, v in value.items()):
        fail("SOURCE_INVENTORY_INVALID", "material must be an exact path-to-bytes map", at)
    preflight(list(value))
    if len(value) > 8192 or any(len(x) > maximum for x in value.values()) or sum(map(len, value.values())) > total_limit:
        fail(LIMIT, "source material byte map exceeds its limit", at)
    return value
