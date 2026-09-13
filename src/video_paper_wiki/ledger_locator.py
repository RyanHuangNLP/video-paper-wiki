"""Pure versioned locator transport in the existing claim evidence field.

This validates supplied spelling and structure, not source authenticity,
artifact contents, scientific interpretation, or permission to publish.
"""
from __future__ import annotations

import copy
import math
import re

from jsonschema import Draft202012Validator, validators

from video_paper_wiki.contracts import ContractError, schema_by_title
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.projection_runtime import _preflight, parse_projection_json

PREFIX = "vpwiki-locator-v1:"
TITLE = "video-paper-wiki.ledger-locator.v1"
MAX_WIRE_BYTES = 65536
_LOCATOR = "LEDGER_LOCATOR_INVALID"
_EVIDENCE = "LEDGER_EVIDENCE_INVALID"
_LIMIT = "PROJECTION_LIMIT_EXCEEDED"
_SOURCE = re.compile(r"src-[A-Za-z0-9][A-Za-z0-9._-]*")
_TO_WIRE = {"supports": "supports", "contradicts": "contradicts", "uncertain": "context"}
_TO_DOMAIN = {wire: domain for domain, wire in _TO_WIRE.items()}
_TYPES = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_Validator = validators.extend(Draft202012Validator, type_checker=_TYPES)


def _fail(code: str, pointer: str, message: str) -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _pointer(parts) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _check_value(value: object, code: str, *, flat_evidence: bool = False) -> None:
    try:
        _preflight(value)
    except ContractError as exc:
        pointer = exc.details.get("instance_pointer", "")
        if exc.code == _LIMIT:
            raise
        if flat_evidence and pointer and pointer.split("/")[1] != "relation":
            code = _LOCATOR
        _fail(code, pointer, "value is not a supported scalar JSON tree")


def _validate_locator(value: object, base: str = "", *, relationships: bool = True) -> dict:
    if type(value) is not dict or type(value.get("kind")) is not str or value["kind"] not in {"pdf", "code"}:
        _fail(_LOCATOR, base, "locator must be a PDF or code object")
    definitions = schema_by_title("video-paper-wiki.common.v1")["$defs"]
    schema = {"$ref": f'#/$defs/{value["kind"]}_locator', "$defs": definitions}
    error = next(_Validator(schema).iter_errors(value), None)
    if error is not None:
        _fail(_LOCATOR, base + _pointer(error.absolute_path), "locator violates the closed common profile")
    if not _SOURCE.fullmatch(value["source_id"]):
        _fail(_LOCATOR, base + "/source_id", "source ID does not match the safe subset")
    fields = {"source_id": "source_id"}
    if value["kind"] == "pdf":
        fields.update(artifact_path="derived_artifact_path", artifact_sha256="sha256", text_sha256="sha256")
    else:
        fields.update(repository="repository", commit="full_commit", path="portable_vault_relative_path", snippet_sha256="sha256")
    for field, definition in fields.items():
        if re.fullmatch(definitions[definition]["pattern"], value[field]) is None:
            _fail(_LOCATOR, base + "/" + field, "locator field must match its complete grammar")
    if relationships:
        _locator_relationships(value, base)
    return value


def _locator_relationships(value: dict, base: str) -> None:
    if value["kind"] == "pdf" and "charspan" in value:
        start, end = value["charspan"]
        if not 0 <= start <= end:
            _fail(_LOCATOR, base + "/charspan", "character span must be nonnegative and ordered")
    if value["kind"] == "code" and value["lines"]["start"] > value["lines"]["end"]:
        _fail(_LOCATOR, base + "/lines", "code line interval must be ordered")


def _canonical(value: object) -> bytes:
    try:
        return canonicalize(value)
    except (CanonicalJsonError, RecursionError, OverflowError):
        _fail(_LOCATOR, "", "locator envelope is not integer canonical JSON")


def _encode_validated(locator: dict) -> str:
    fields = copy.deepcopy(locator)
    envelope = {"schema": TITLE, "locator": fields}
    if "bbox" in fields:
        coordinates = fields.pop("bbox")
        envelope["bbox_rationals"] = [
            [coordinate, 1] if type(coordinate) is int else list(coordinate.as_integer_ratio())
            for coordinate in coordinates
        ]
    payload = _canonical(envelope)
    if len(PREFIX) + len(payload) > MAX_WIRE_BYTES:
        _fail(_LIMIT, "", "locator wire byte budget exceeded")
    return PREFIX + payload.decode("utf-8")


def encode_ledger_locator(locator: object) -> str:
    """Validate a complete locator and encode its exact canonical wire form."""
    _check_value(locator, _LOCATOR)
    return _encode_validated(_validate_locator(locator))


def _bbox_pairs(value: object) -> list:
    if type(value) is not list or len(value) != 4:
        _fail(_LOCATOR, "/bbox_rationals", "bbox requires four coordinate pairs")
    for index, pair in enumerate(value):
        pointer = f"/bbox_rationals/{index}"
        if type(pair) is not list or len(pair) != 2 or any(type(member) is not int for member in pair):
            _fail(_LOCATOR, pointer, "coordinate pair requires two exact integers")
    return value


def _decode_bbox(value: list) -> list:
    result = []
    for index, pair in enumerate(value):
        pointer = f"/bbox_rationals/{index}"
        numerator, denominator = pair
        if denominator <= 0 or math.gcd(abs(numerator), denominator) != 1:
            _fail(_LOCATOR, pointer, "coordinate ratio must be reduced with positive denominator")
        if denominator == 1:
            result.append(numerator)
            continue
        if denominator & (denominator - 1):
            _fail(_LOCATOR, pointer, "fractional coordinate denominator must be a power of two")
        try:
            coordinate = numerator / denominator
        except OverflowError:
            _fail(_LOCATOR, pointer, "coordinate overflows binary64")
        if not math.isfinite(coordinate) or coordinate.as_integer_ratio() != (numerator, denominator):
            _fail(_LOCATOR, pointer, "coordinate ratio is not exactly representable as binary64")
        result.append(coordinate)
    return result


def decode_ledger_locator(wire: str) -> dict:
    """Decode only canonical tagged wire; no legacy free-text fallback."""
    if type(wire) is not str:
        _fail(_LOCATOR, "", "locator wire must be an exact scalar string")
    if len(wire) > MAX_WIRE_BYTES:
        _fail(_LIMIT, "", "locator wire character count exceeds byte budget")
    try:
        raw = wire.encode("utf-8")
    except UnicodeError:
        _fail(_LOCATOR, "", "locator wire contains a surrogate")
    if len(raw) > MAX_WIRE_BYTES:
        _fail(_LIMIT, "", "locator wire byte budget exceeded")
    if not wire.startswith(PREFIX):
        _fail(_LOCATOR, "", "locator wire prefix is missing")
    try:
        envelope = parse_projection_json(raw[len(PREFIX):])
    except ContractError as exc:
        if exc.code == _LIMIT:
            raise
        _fail(_LOCATOR, exc.details.get("instance_pointer", ""), "invalid locator envelope JSON")
    if (type(envelope) is not dict or not {"schema", "locator"} <= envelope.keys()
            or envelope.keys() - {"schema", "locator", "bbox_rationals"}):
        _fail(_LOCATOR, "", "locator envelope requires only the declared fields")
    if envelope["schema"] != TITLE:
        _fail(_LOCATOR, "/schema", "wrong locator envelope discriminator")
    fields = envelope["locator"]
    if type(fields) is not dict:
        _fail(_LOCATOR, "/locator", "envelope locator must be an object")
    if "bbox" in fields:
        _fail(_LOCATOR, "/locator/bbox", "bbox must occur only as envelope ratios")
    # Parsed containers are private; validation and reconstruction cannot mutate
    # any caller data. Shape checks precede coordinate representability checks.
    _validate_locator(fields, "/locator", relationships=False)
    if "bbox_rationals" in envelope:
        if fields["kind"] != "pdf":
            _fail(_LOCATOR, "/bbox_rationals", "code locators cannot contain bbox ratios")
        _bbox_pairs(envelope["bbox_rationals"])
    _locator_relationships(fields, "/locator")
    if "bbox_rationals" in envelope:
        fields["bbox"] = _decode_bbox(envelope["bbox_rationals"])
    if _encode_validated(fields) != wire:
        _fail(_LOCATOR, "", "locator wire spelling is not canonical")
    return fields


def encode_ledger_evidence(evidence: object) -> dict:
    """Transport one flat domain evidence item into existing upstream fields."""
    _check_value(evidence, _EVIDENCE, flat_evidence=True)
    if type(evidence) is not dict:
        _fail(_EVIDENCE, "", "domain evidence must be an object")
    relation = evidence.get("relation")
    if type(relation) is not str or relation not in _TO_WIRE:
        _fail(_EVIDENCE, "/relation", "invalid domain evidence relation")
    locator = {key: value for key, value in evidence.items() if key != "relation"}
    wire = encode_ledger_locator(locator)
    return {"source_id": locator["source_id"], "relation": _TO_WIRE[relation], "locator": wire}


def decode_ledger_evidence(evidence: object) -> dict:
    """Restore one validated tagged evidence item to the flat domain form."""
    _check_value(evidence, _EVIDENCE)
    if type(evidence) is not dict or evidence.keys() != {"source_id", "relation", "locator"}:
        _fail(_EVIDENCE, "", "wire evidence requires exactly source_id, relation and locator")
    for field in ("source_id", "relation", "locator"):
        if type(evidence[field]) is not str:
            _fail(_EVIDENCE, "/" + field, "outer evidence fields must be scalar strings")
    if not _SOURCE.fullmatch(evidence["source_id"]):
        _fail(_EVIDENCE, "/source_id", "outer source ID does not match the safe subset")
    if evidence["relation"] not in _TO_DOMAIN:
        _fail(_EVIDENCE, "/relation", "invalid upstream evidence relation")
    locator = decode_ledger_locator(evidence["locator"])
    if locator["source_id"] != evidence["source_id"]:
        _fail(_EVIDENCE, "/source_id", "outer source ID differs from the decoded locator")
    locator["relation"] = _TO_DOMAIN[evidence["relation"]]
    return locator
