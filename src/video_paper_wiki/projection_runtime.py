"""Pure, bounded comparison of values and pinned upstream runtime records.

This numeric domain is separate from canonical identity and raw content hashes.
Validation of supplied records neither authenticates upstream execution nor
reads the pages/chunks named by those records.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime

from jsonschema import Draft202012Validator, validators

from video_paper_wiki.contracts import ContractError, schema_by_title
from video_paper_wiki.jcs import canonicalize

MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_SCALAR_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 64
MAX_OCCURRENCES = 1_000_000
MAX_INTEGER_BITS = 2048
MAX_INDEX = 2147483647
PROFILE_TITLES = {
    "chunk": "video-paper-wiki.upstream-chunk-profile.v1",
    "bm25": "video-paper-wiki.upstream-bm25-profile.v1",
}
_PROFILES = {"chunk": "claude-obsidian.chunk.v1", "bm25": "claude-obsidian.bm25.v2"}
_PROFILE = re.compile(r"[a-z][a-z0-9._-]{0,127}")
_ADDRESS = r"(?:[cl]-[0-9]{6}|syn-[0-9a-f]{64})"
_CHUNK_ID = re.compile(rf"({_ADDRESS}):(0|[1-9][0-9]*)")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_STRICT_TYPES = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_RuntimeValidator = validators.extend(Draft202012Validator, type_checker=_STRICT_TYPES)


def _fail(code: str, pointer: str | tuple[str | int, ...], message: str) -> None:
    if type(pointer) is tuple:
        pointer = "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in pointer)
    raise ContractError(code, message, {"instance_pointer": pointer})


def _pointer(parent: str, key: str | int) -> str:
    return parent + "/" + str(key).replace("~", "~0").replace("/", "~1")


def _preflight(value: object) -> None:
    """Bound the original tree before constructing the tagged comparison tree."""
    occurrences = 0
    scalar_bytes = 0
    active: set[int] = set()

    def count(pointer: tuple) -> None:
        nonlocal occurrences
        occurrences += 1
        if occurrences > MAX_OCCURRENCES:
            _fail("PROJECTION_LIMIT_EXCEEDED", pointer, "tree occurrence budget exceeded")

    def charge(amount: int, pointer: tuple) -> None:
        nonlocal scalar_bytes
        scalar_bytes += amount
        if scalar_bytes > MAX_SCALAR_BYTES:
            _fail("PROJECTION_LIMIT_EXCEEDED", pointer, "scalar encoding budget exceeded")

    def string_token(text: str, pointer: tuple) -> None:
        # Every code point costs at least one byte. Escape bounded slices so a
        # hostile long string cannot allocate an oversized temporary token.
        if len(text) + 2 > MAX_SCALAR_BYTES - scalar_bytes:
            _fail("PROJECTION_LIMIT_EXCEEDED", pointer, "scalar encoding budget exceeded")
        charge(2, pointer)
        for offset in range(0, len(text), 4096):
            try:
                token = json.dumps(text[offset:offset + 4096], ensure_ascii=False).encode("utf-8")
            except UnicodeError:
                _fail("PROJECTION_VALUE_INVALID", pointer, "string contains a surrogate")
            charge(len(token) - 2, pointer)

    def visit(item: object, depth: int, pointer: tuple) -> None:
        count(pointer)
        kind = type(item)
        if item is None or kind is bool:
            return
        if kind is str:
            string_token(item, pointer)
        elif kind is int:
            if item.bit_length() > MAX_INTEGER_BITS:
                _fail("PROJECTION_LIMIT_EXCEEDED", pointer, "integer magnitude budget exceeded")
            charge(len(str(item)) + 1, pointer)
        elif kind is float:
            if not math.isfinite(item):
                _fail("PROJECTION_VALUE_INVALID", pointer, "number must be finite")
            numerator, denominator = item.as_integer_ratio()
            charge(len(str(numerator)) + len(str(denominator)), pointer)
        elif kind in (dict, list):
            if depth == MAX_DEPTH:
                _fail("PROJECTION_LIMIT_EXCEEDED", pointer, "container depth budget exceeded")
            if id(item) in active:
                _fail("PROJECTION_VALUE_INVALID", pointer, "ancestor cycle in value tree")
            # Each child and dictionary key consumes at least one occurrence.
            minimum = len(item) * (2 if kind is dict else 1)
            if minimum > MAX_OCCURRENCES - occurrences:
                _fail("PROJECTION_LIMIT_EXCEEDED", pointer, "tree occurrence budget exceeded")
            active.add(id(item))
            if kind is dict:
                for key in item:
                    if type(key) is not str:
                        _fail("PROJECTION_VALUE_INVALID", pointer, "object keys must be exact strings")
                    count(pointer)
                    string_token(key, pointer)
                for key, child in item.items():
                    visit(child, depth + 1, (*pointer, key))
            else:
                for index, child in enumerate(item):
                    visit(child, depth + 1, (*pointer, index))
            active.remove(id(item))
        else:
            _fail("PROJECTION_VALUE_INVALID", pointer, "unsupported Python value type")

    visit(value, 0, ())


_JSON_TOKEN = re.compile(r'["{}\[\]]|[^ \t\r\n,:\[\]{}"]+')
_JSON_STRING_SPECIAL = re.compile(r'["\\]')


def _json_shape_preflight(text: str) -> None:
    """Bound allocation before json.loads, without constructing decoded values.

    For valid JSON every container, string (including a key), or primitive is
    one occurrence. Strings are skipped without interpreting their escapes.
    The standard decoder remains the syntax/escape/duplicate/number authority;
    this pass only refuses resource excess, including overly deep raw input.
    """
    position = depth = occurrences = 0
    while match := _JSON_TOKEN.search(text, position):
        position = match.end()
        character = text[match.start()]
        if character in "}]":
            depth -= 1
            if depth < 0:
                return  # Let the decoder diagnose invalid syntax.
            continue
        occurrences += 1
        if occurrences > MAX_OCCURRENCES:
            _fail("PROJECTION_LIMIT_EXCEEDED", "", "JSON tree occurrence budget exceeded")
        if character in "{[":
            depth += 1
            if depth > MAX_DEPTH:
                _fail("PROJECTION_LIMIT_EXCEEDED", "", "JSON container depth budget exceeded")
        elif character == '"':
            while special := _JSON_STRING_SPECIAL.search(text, position):
                position = special.end()
                if text[special.start()] == '"':
                    break
                position += 1  # Skip the escaped character, even if malformed.
            else:
                return  # Unterminated string: defer to the syntax decoder.


def parse_projection_json(payload: bytes) -> object:
    """Parse strict UTF-8 JSON and apply the comparison domain's resource limits."""
    if type(payload) is not bytes:
        _fail("PROJECTION_VALUE_INVALID", "", "JSON input must be exact bytes")
    if len(payload) > MAX_JSON_BYTES:
        _fail("PROJECTION_LIMIT_EXCEEDED", "", "JSON byte budget exceeded")
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        _fail("PROJECTION_JSON_INVALID", "", "JSON input is not UTF-8")
    if text.startswith("\ufeff"):
        _fail("PROJECTION_JSON_INVALID", "", "JSON BOM is forbidden")
    _json_shape_preflight(text)

    def pairs(items: list[tuple[str, object]]) -> dict:
        result = {}
        for key, item in items:
            if key in result:
                _fail("PROJECTION_JSON_INVALID", "", "duplicate JSON object key")
            result[key] = item
        return result

    def constant(_token: str) -> None:
        _fail("PROJECTION_JSON_INVALID", "", "nonfinite JSON token")

    def finite_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            _fail("PROJECTION_JSON_INVALID", "", "floating JSON token overflows")
        return value

    def bounded_integer(token: str) -> int:
        # Every permitted 2048-bit integer has at most 617 decimal digits.
        # Bound before int(), independently of the process-wide digit policy.
        digits = len(token) - token.startswith("-")
        if digits > 617:
            _fail("PROJECTION_LIMIT_EXCEEDED", "", "JSON integer magnitude budget exceeded")
        return int(token)

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant,
                           parse_float=finite_float, parse_int=bounded_integer)
    except ContractError:
        raise
    except json.JSONDecodeError:
        _fail("PROJECTION_JSON_INVALID", "", "invalid JSON syntax")
    except (RecursionError, ValueError, OverflowError):
        _fail("PROJECTION_LIMIT_EXCEEDED", "", "JSON decoder resource limit exceeded")
    _preflight(value)
    return value


def _tag(value: object) -> list:
    if value is None:
        return ["null"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is str:
        return ["string", value]
    if type(value) is int:
        return ["number", value, 1]
    if type(value) is float:
        return ["number", *value.as_integer_ratio()]
    if type(value) is list:
        return ["array", [_tag(item) for item in value]]
    return ["object", [[key, _tag(value[key])] for key in sorted(value, key=lambda key: key.encode("utf-16-be"))]]


def projection_value_bytes(value: object, *, profile: str) -> bytes:
    """Encode exact typed numeric material, independent of business identity JCS."""
    if type(profile) is not str or not _PROFILE.fullmatch(profile):
        _fail("PROJECTION_VALUE_INVALID", "/profile", "invalid comparison profile")
    _preflight(value)
    return canonicalize({"codec": "vpwiki.runtime-tree.v1", "profile": profile, "tree": _tag(value)})


def projection_value_sha256(value: object, *, profile: str) -> str:
    return hashlib.sha256(projection_value_bytes(value, profile=profile)).hexdigest()


def _kind(kind: object) -> str:
    if type(kind) is not str or kind not in PROFILE_TITLES:
        _fail("PROJECTION_VALUE_INVALID", "/kind", "runtime kind must be chunk or bm25")
    return kind


def _timestamp(value: str, pointer: str) -> None:
    if not _TIMESTAMP.fullmatch(value):
        _fail("RUNTIME_PROFILE_INVALID", pointer, "timestamp must be a complete UTC second")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _fail("RUNTIME_PROFILE_INVALID", pointer, "timestamp is not a real UTC datetime")


def _lexical_path(value: str, pointer: str) -> None:
    if (not value or "\\" in value or re.match(r"[A-Za-z]:", value)
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        _fail("RUNTIME_PROFILE_INVALID", pointer, "invalid runtime relative path")


def _chunk_fields(document: dict) -> None:
    if re.fullmatch(_ADDRESS, document["page_address"]) is None:
        _fail("RUNTIME_PROFILE_INVALID", "/page_address", "invalid complete address")
    _lexical_path(document["page_path"], "/page_path")
    _timestamp(document["created_at"], "/created_at")
    if document["prefix"] != document["prefix"].strip():
        _fail("RUNTIME_PROFILE_INVALID", "/prefix", "prefix must already be stripped")


def _chunk_content(document: dict) -> None:
    address = document["page_address"]
    if address.startswith("syn-") and address != "syn-" + hashlib.sha256(document["page_path"].encode("utf-8")).hexdigest():
        _fail("RUNTIME_CONTENT_MISMATCH", "/page_address", "synthetic identity differs from page path")
    raw, prefix = document["raw_text"], document["prefix"]
    if document["char_count"] != len(raw):
        _fail("RUNTIME_CONTENT_MISMATCH", "/char_count", "character count differs")
    if document["contextualized_text"] != (prefix + "\n\n" + raw if prefix else raw):
        _fail("RUNTIME_CONTENT_MISMATCH", "/contextualized_text", "contextualized text differs")
    if document["body_hash"] != "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest():
        _fail("RUNTIME_CONTENT_MISMATCH", "/body_hash", "raw text digest differs")


def _bm25_fields(document: dict) -> None:
    _timestamp(document["updated_at"], "/updated_at")
    for chunk_id, item in document["docs"].items():
        pointer = _pointer("/docs", chunk_id)
        match = _CHUNK_ID.fullmatch(chunk_id)
        # Length refusal precedes integer conversion of untrusted ID text.
        if match is None or len(match[2]) > 10 or int(match[2]) > MAX_INDEX:
            _fail("RUNTIME_PROFILE_INVALID", pointer, "invalid chunk identity")
        _lexical_path(item["path"], pointer + "/path")
        expected = f".vault-meta/chunks/{match[1]}/chunk-{int(match[2]):03d}.json"
        if item["path"] != expected:
            _fail("RUNTIME_PROFILE_INVALID", pointer + "/path", "chunk path differs from identity")


def _bm25_content(document: dict) -> None:
    docs = document["docs"]
    count = document["doc_count"]
    if count != len(docs):
        _fail("RUNTIME_CONTENT_MISMATCH", "/doc_count", "document count differs")
    paths = [item["path"] for item in docs.values()]
    if len(set(paths)) != len(paths):
        _fail("RUNTIME_CONTENT_MISMATCH", "/docs", "duplicate chunk paths")
    expected_mean = sum(item["dl"] for item in docs.values()) / count if count else 0
    if document["avg_dl"] != expected_mean:
        _fail("RUNTIME_CONTENT_MISMATCH", "/avg_dl", "mean differs from actual document lengths")
    totals = dict.fromkeys(docs, 0)
    for term, item in document["vocab"].items():
        pointer = _pointer("/vocab", term)
        if item["df"] > count or item["df"] != len(item["postings"]):
            _fail("RUNTIME_CONTENT_MISMATCH", pointer + "/df", "document frequency differs")
        seen = set()
        for index, (chunk_id, frequency) in enumerate(item["postings"]):
            if chunk_id not in docs or chunk_id in seen:
                _fail("RUNTIME_CONTENT_MISMATCH", f"{pointer}/postings/{index}", "unknown or duplicate posting document")
            seen.add(chunk_id)
            totals[chunk_id] += frequency
    if any(totals[key] != item["dl"] for key, item in docs.items()):
        _fail("RUNTIME_CONTENT_MISMATCH", "/vocab", "posting totals differ from document lengths")


def validate_runtime_record(kind: object, document: object) -> dict:
    """Validate all supplied fields before copying or excluding a timestamp."""
    kind = _kind(kind)
    _preflight(document)
    schema = schema_by_title(PROFILE_TITLES[kind])
    error = next(_RuntimeValidator(schema).iter_errors(document), None)
    if error is not None:
        pointer = ""
        for component in error.absolute_path:
            pointer = _pointer(pointer, component)
        _fail("RUNTIME_PROFILE_INVALID", pointer, "runtime record violates closed profile")
    if kind == "chunk":
        _chunk_fields(document)
        _chunk_content(document)
    else:
        _bm25_fields(document)
        _bm25_content(document)
    return copy.deepcopy(document)


def runtime_projection_bytes(kind: object, document: object) -> bytes:
    kind = _kind(kind)
    result = validate_runtime_record(kind, document)
    del result["created_at" if kind == "chunk" else "updated_at"]
    return projection_value_bytes(result, profile=_PROFILES[kind])


def runtime_projection_sha256(kind: object, document: object) -> str:
    return hashlib.sha256(runtime_projection_bytes(kind, document)).hexdigest()


def runtime_projection_equal(kind: object, left: object, right: object) -> bool:
    left_bytes = runtime_projection_bytes(kind, left)
    right_bytes = runtime_projection_bytes(kind, right)
    return left_bytes == right_bytes


def markdown_projection_equal(left: bytes, right: bytes) -> bool:
    if type(left) is not bytes or type(right) is not bytes:
        _fail("PROJECTION_VALUE_INVALID", "", "Markdown comparison requires exact bytes")
    return left == right
