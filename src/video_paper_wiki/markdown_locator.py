"""Exact Unicode-span Markdown locators and explicit mixed evidence fingerprints."""
from __future__ import annotations

import copy

from video_paper_wiki import identity
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import decode_ledger_evidence, encode_ledger_evidence
from video_paper_wiki.markdown_source import validate_payload
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json
from video_paper_wiki.source_semantics_contracts import (
    ASSOCIATION, INVALID, LIMIT, LOCATOR, association_reference, fail, preflight, sha, validate,
)

PREFIX = "vpwiki-locator-v2:"
MAX_WIRE = 65536
CODE = "MARKDOWN_LOCATOR_INVALID"
TO_WIRE = {"supports": "supports", "contradicts": "contradicts", "uncertain": "context"}
FROM_WIRE = {value: key for key, value in TO_WIRE.items()}


def _locator(value):
    preflight(value)
    try:
        return validate({"schema": LOCATOR, "locator": value}, LOCATOR)["locator"]
    except ContractError as exc:
        if exc.code in (INVALID, LIMIT):
            raise
        fail(CODE, "Markdown locator violates its closed profile", exc.details.get("instance_pointer", ""))


def encode_markdown_locator(locator):
    loc = _locator(locator)
    wire = PREFIX + canonicalize({"schema": LOCATOR, "locator": loc}).decode("utf-8")
    if len(wire.encode("utf-8")) > MAX_WIRE:
        fail(LIMIT, "Markdown locator wire exceeds its byte budget")
    return wire


def decode_markdown_locator(wire):
    preflight(wire)
    if type(wire) is not str or not wire.startswith(PREFIX):
        fail(CODE, "canonical Markdown locator prefix is required")
    if len(wire.encode("utf-8")) > MAX_WIRE:
        fail(LIMIT, "Markdown locator wire exceeds its byte budget")
    try:
        doc = parse_strict_json(wire[len(PREFIX):].encode("utf-8"), invalid_code=CODE)
        preflight(doc)
        doc = validate(doc, LOCATOR)
    except SecureIOError as exc:
        if exc.details.get("reason") in {"depth", "integer"}:
            fail(LIMIT, "Markdown locator JSON exceeds its bound")
        fail(CODE, "Markdown locator JSON is malformed")
    except ContractError as exc:
        if exc.code in (INVALID, LIMIT):
            raise
        fail(CODE, "Markdown locator envelope is malformed", exc.details.get("instance_pointer", ""))
    if encode_markdown_locator(doc["locator"]) != wire:
        fail(CODE, "Markdown locator spelling is not canonical")
    return doc["locator"]


def resolve_markdown_locator(locator, association, raw_bytes):
    preflight({"locator": locator, "association": association})
    loc = _locator(locator)
    doc = validate(association, ASSOCIATION)
    if (loc["association"] != association_reference(doc) or loc["source_id"] != doc["source_id"]
            or loc["path"] != doc["raw"]["path"] or loc["sha256"] != doc["raw"]["sha256"]):
        fail(CODE, "locator does not bind the exact source association")
    if type(raw_bytes) is not bytes:
        fail(CODE, "Markdown resolution requires exact bytes")
    if len(raw_bytes) > 8388608:
        fail(LIMIT, "Markdown source exceeds its byte budget")
    try:
        validate_payload(raw_bytes, doc["observation"])
        text = raw_bytes.decode("utf-8")
    except (ContractError, UnicodeError):
        fail(CODE, "Markdown source bytes or observed page intervals differ")
    start, end = loc["charspan"]
    if not 0 <= start < end <= len(text):
        fail(CODE, "Markdown character span is outside the source", "/charspan")
    excerpt = text[start:end]
    if not excerpt.strip() or sha(excerpt.encode("utf-8")) != loc["excerpt_sha256"]:
        fail(CODE, "Markdown excerpt hash or nonempty text differs", "/excerpt_sha256")
    if loc["page_anchor"] is not None:
        page = next((p for p in doc["observation"]["pages"] if p["anchor"] == loc["page_anchor"]), None)
        if page is None or not page["text_start"] <= start < end <= page["text_end"]:
            fail(CODE, "page anchor does not contain the entire excerpt", "/page_anchor")
    return excerpt


def encode_evidence(evidence):
    preflight(evidence, evidence_scope="item")
    if type(evidence) is not dict:
        fail(CODE, "evidence must be an exact object")
    if evidence.get("kind") != "markdown":
        return encode_ledger_evidence(evidence)
    relation = evidence.get("relation")
    if type(relation) is not str or relation not in TO_WIRE:
        fail(CODE, "Markdown evidence relation is invalid", "/relation")
    locator = {k: v for k, v in evidence.items() if k != "relation"}
    wire = encode_markdown_locator(locator)
    return {"source_id": locator["source_id"], "relation": TO_WIRE[relation], "locator": wire}


def decode_evidence(evidence):
    preflight(evidence)
    if type(evidence) is not dict or set(evidence) != {"source_id", "relation", "locator"}:
        fail(CODE, "wire evidence must have exactly the upstream transport fields")
    if any(type(x) is not str for x in evidence.values()):
        fail(CODE, "wire evidence fields must be strings")
    if not evidence["locator"].startswith(PREFIX):
        return decode_ledger_evidence(evidence)
    locator = decode_markdown_locator(evidence["locator"])
    if evidence["source_id"] != locator["source_id"] or evidence["relation"] not in FROM_WIRE:
        fail(CODE, "outer evidence relation or source differs")
    return {**locator, "relation": FROM_WIRE[evidence["relation"]]}


def evidence_profile(evidence):
    preflight(evidence, evidence_scope="list")
    if type(evidence) is not list:
        fail(CODE, "evidence inventory must be an array")
    for item in evidence:
        encode_evidence(item)
    return "mixed-v2" if any(x["kind"] == "markdown" for x in evidence) else "legacy-v1"


def evidence_fingerprint_versioned(evidence):
    profile = evidence_profile(evidence)
    if profile == "legacy-v1":
        return identity.evidence_fingerprint(evidence)
    by_bytes = {}
    for item in evidence:
        material = copy.deepcopy(item) if item["kind"] == "markdown" else identity._evidence_identity(item)
        by_bytes[canonicalize(material)] = material
    ordered = [by_bytes[key] for key in sorted(by_bytes)]
    return sha(b"video-paper-wiki.evidence.mixed.v2\0" + canonicalize(ordered))
