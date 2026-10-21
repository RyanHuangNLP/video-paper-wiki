"""Runtime codec and raw-profile contracts; expected numeric bytes are independent."""
from __future__ import annotations

import builtins
import copy
import hashlib
import json
import math
import socket
import subprocess
import tracemalloc
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.projection_runtime import (
    MAX_DEPTH, MAX_INTEGER_BITS, MAX_JSON_BYTES, MAX_OCCURRENCES, MAX_SCALAR_BYTES,
    PROFILE_TITLES, markdown_projection_equal, parse_projection_json,
    projection_value_bytes, projection_value_sha256, runtime_projection_bytes,
    runtime_projection_equal, runtime_projection_sha256, validate_runtime_record,
)

FIXTURES = Path(__file__).parent / "fixtures/projection-runtime"


def chunk():
    path, text = "wiki/papers/Example.md", "全文检索"
    return {
        "schema_version": 1, "page_path": path,
        "page_address": "syn-" + hashlib.sha256(path.encode()).hexdigest(),
        "chunk_index": 0, "raw_text": text, "contextualized_text": text,
        "prefix": "", "prefix_source": "synthetic", "char_count": len(text),
        "body_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        "page_body_hash": "sha256:" + "a" * 64, "created_at": "2026-08-31T00:00:00Z",
    }


def bm25():
    docs = {}
    for address, length in [("c-000001", 3), ("c-000002", 1)]:
        docs[address + ":0"] = {
            "path": f".vault-meta/chunks/{address}/chunk-000.json", "dl": length,
            "body_hash": "sha256:" + "a" * 64, "page_body_hash": "sha256:" + "b" * 64,
        }
    return {
        "schema_version": 2, "params": {"k1": 1.5, "b": 0.75},
        "doc_count": 2, "avg_dl": 2.0, "updated_at": "2026-08-31T00:00:00Z",
        "vocab": {
            "updated_at": {"df": 2, "postings": [["c-000001:0", 2], ["c-000002:0", 1]]},
            "检索": {"df": 1, "postings": [["c-000001:0", 1]]},
        }, "docs": docs,
    }


def refused(code, function, *args, **kwargs):
    with pytest.raises(ContractError) as error:
        function(*args, **kwargs)
    assert error.value.code == code
    assert error.value.exit_code == 2
    assert isinstance(error.value.details["instance_pointer"], str)
    json.dumps(error.value.details, ensure_ascii=False).encode("utf-8")


def test_independent_full_byte_and_sha_vectors():
    vectors = json.loads((FIXTURES / "number-vectors.json").read_text())
    values = {
        "null": None, "true": True, "one_int": 1, "one_float": 1.0,
        "zero_int": 0, "negative_zero": -0.0, "point_one": 0.1,
        "next_one": math.nextafter(1.0, math.inf), "k1": 1.5, "b": 0.75,
        "subnormal": float.fromhex("0x0.0000000000001p-1022"),
        "max_float": float.fromhex("0x1.fffffffffffffp+1023"),
        "tag_like_array": ["number", 1, 1], "utf16_order": {"\ue000": 1, "\U00010000": 2},
    }
    assert len(vectors["vectors"]) == len(values) == 14
    for name, value in values.items():
        expected = vectors["vectors"][name]
        encoded = expected["canonical_utf8"].encode("utf-8")
        assert hashlib.sha256(encoded).hexdigest() == expected["sha256"]
        assert projection_value_bytes(value, profile=vectors["profile"]) == encoded
        assert projection_value_sha256(value, profile=vectors["profile"]) == expected["sha256"]


def test_type_separation_and_all_order_rules():
    encode = lambda value: projection_value_bytes(value, profile="order.v1")
    assert encode(True) != encode(1)
    assert encode(None) != encode(["null"])
    assert encode({"a": 1, "b": 2}) == encode({"b": 2.0, "a": 1.0})
    assert encode([1, 2]) != encode([2, 1]) != encode([2, 1, 1])
    assert encode("é") != encode("e\u0301")
    assert encode(0.1) != encode(math.nextafter(0.1, math.inf))
    assert encode(-0.0) == encode(0)
    assert projection_value_bytes(1, profile="one") != projection_value_bytes(1, profile="two")
    with pytest.raises(CanonicalJsonError):
        canonicalize(0.1)


@pytest.mark.parametrize("payload,code", [
    (b"", "PROJECTION_JSON_INVALID"), (b"{} x", "PROJECTION_JSON_INVALID"),
    (b"\xef\xbb\xbf{}", "PROJECTION_JSON_INVALID"), (b"\xff", "PROJECTION_JSON_INVALID"),
    (b'{"x":1,"\\u0078":2}', "PROJECTION_JSON_INVALID"),
    (b'{"x":{"a":1,"a":2}}', "PROJECTION_JSON_INVALID"),
    (b"NaN", "PROJECTION_JSON_INVALID"), (b"Infinity", "PROJECTION_JSON_INVALID"),
    (b"-Infinity", "PROJECTION_JSON_INVALID"), (b"1e9999", "PROJECTION_JSON_INVALID"),
    (b'"\\ud800"', "PROJECTION_VALUE_INVALID"),
    (b"[" * 2000 + b"0" + b"]" * 2000, "PROJECTION_LIMIT_EXCEEDED"),
    (b"1" * 5000, "PROJECTION_LIMIT_EXCEEDED"),
])
def test_strict_json_refusals(payload, code):
    refused(code, parse_projection_json, payload)


def test_strict_json_rounding_and_whitespace():
    assert parse_projection_json(b' {"a":1,"b":1.0,"c":1e-9999} \r\n') == {"a": 1, "b": 1.0, "c": 0.0}
    assert type(parse_projection_json(b"1")) is int
    assert type(parse_projection_json(b"1.0")) is float


class StringSubclass(str):
    pass


class DictSubclass(dict):
    pass


@pytest.mark.parametrize("value", [(), set(), b"x", Decimal("1"), Fraction(1, 2), StringSubclass("x"), DictSubclass(), {1: None}, {StringSubclass("x"): 1}, "\udfff", float("nan"), float("inf"), object()])
def test_non_json_python_values(value):
    refused("PROJECTION_VALUE_INVALID", projection_value_bytes, value, profile="test")


@pytest.mark.parametrize("profile", [None, True, 1, StringSubclass("test"), "A", "x\n", "x" * 129, "é", ""])
def test_profile_is_exact_bounded_ascii_string(profile):
    refused("PROJECTION_VALUE_INVALID", projection_value_bytes, None, profile=profile)


def test_cycles_and_shared_objects():
    cycle = []; cycle.append(cycle)
    refused("PROJECTION_VALUE_INVALID", projection_value_bytes, cycle, profile="test")
    shared = {"a": [1]}
    assert projection_value_bytes([shared, shared], profile="test") == projection_value_bytes([{"a": [1]}, {"a": [1]}], profile="test")


def test_depth_and_integer_magnitude_edges():
    value = 0
    for _ in range(MAX_DEPTH): value = [value]
    projection_value_bytes(value, profile="test")
    refused("PROJECTION_LIMIT_EXCEEDED", projection_value_bytes, [value], profile="test")
    for integer in [(1 << MAX_INTEGER_BITS) - 1, -((1 << MAX_INTEGER_BITS) - 1)]:
        projection_value_bytes(integer, profile="test")
    refused("PROJECTION_LIMIT_EXCEEDED", projection_value_bytes, 1 << MAX_INTEGER_BITS, profile="test")


def test_occurrence_limit_includes_root_keys_and_shared_repetition():
    encoded = projection_value_bytes([None] * (MAX_OCCURRENCES - 1), profile="test")
    assert encoded.startswith(b'{"codec":')
    refused("PROJECTION_LIMIT_EXCEEDED", projection_value_bytes, [None] * MAX_OCCURRENCES, profile="test")


def test_exact_scalar_and_raw_json_byte_limits():
    # Quotes count, wrapper/profile does not; this exercises the real 64 MiB cap.
    value = "a" * (MAX_SCALAR_BYTES - 2)
    assert len(projection_value_bytes(value, profile="test")) > MAX_SCALAR_BYTES
    refused("PROJECTION_LIMIT_EXCEEDED", projection_value_bytes, value + "a", profile="test")
    payload = b"0" + b" " * (MAX_JSON_BYTES - 1)
    assert parse_projection_json(payload) == 0
    refused("PROJECTION_LIMIT_EXCEEDED", parse_projection_json, payload + b" ")


def test_budget_accounting_small_examples(monkeypatch):
    import video_paper_wiki.projection_runtime as runtime
    for value, budget in [(1, 2), ("x", 3), ({"a": 1}, 5), ("\n", 4), (0.1, 33)]:
        monkeypatch.setattr(runtime, "MAX_SCALAR_BYTES", budget)
        projection_value_bytes(value, profile="test")
        monkeypatch.setattr(runtime, "MAX_SCALAR_BYTES", budget - 1)
        refused("PROJECTION_LIMIT_EXCEEDED", projection_value_bytes, value, profile="test")
    monkeypatch.setattr(runtime, "MAX_SCALAR_BYTES", 0)
    projection_value_bytes([None, True], profile="test")


def test_json_budgets_are_checked_before_decoder_allocation(monkeypatch):
    import video_paper_wiki.projection_runtime as runtime
    original = runtime.json.loads
    def unexpected(*args, **kwargs):
        raise AssertionError("oversized tree reached allocating decoder")
    monkeypatch.setattr(runtime.json, "loads", unexpected)
    monkeypatch.setattr(runtime, "MAX_OCCURRENCES", 5)
    refused("PROJECTION_LIMIT_EXCEEDED", parse_projection_json, b"[[],[],[],[],[]]")
    refused("PROJECTION_LIMIT_EXCEEDED", parse_projection_json, b'{"a":0,"b":0,"c":0}')
    monkeypatch.setattr(runtime, "MAX_DEPTH", 2)
    refused("PROJECTION_LIMIT_EXCEEDED", parse_projection_json, b"[[[]]]")
    monkeypatch.setattr(runtime.json, "loads", original)
    assert parse_projection_json(b"[[],[],[],[]]") == [[], [], [], []]
    # Brackets/token spellings and escaped quotes within strings do not count.
    payload = b'{"a":["[ \\" \\\\ null {}",null]}'
    assert parse_projection_json(payload) == json.loads(payload)


def test_preflight_paths_do_not_copy_every_ancestor_key():
    import video_paper_wiki.projection_runtime as runtime
    key = "x" * 4096
    value = None
    for _ in range(MAX_DEPTH):
        value = {key: value}
    tracemalloc.start()
    try:
        runtime._preflight(value)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # The old eager pointers required 8+ MiB for this 256 KiB original tree.
    assert peak < 2 * 1024 * 1024
    with pytest.raises(ContractError) as error:
        projection_value_bytes({"a/b": [{"~key": object()}]}, profile="test")
    assert error.value.details["instance_pointer"] == "/a~1b/0/~0key"


def test_json_integer_conversion_is_bounded_without_global_policy(monkeypatch):
    import video_paper_wiki.projection_runtime as runtime
    maximum = (1 << MAX_INTEGER_BITS) - 1
    for number in (maximum, -maximum):
        assert len(str(abs(number))) == 617
        assert parse_projection_json(str(number).encode()) == number
    refused("PROJECTION_LIMIT_EXCEEDED", parse_projection_json, str(maximum + 1).encode())
    def unexpected(_token):
        raise AssertionError("oversized integer reached bigint conversion")
    monkeypatch.setattr(runtime, "int", unexpected, raising=False)
    for payload in (b"9" * 618, b"-" + b"9" * 618):
        refused("PROJECTION_LIMIT_EXCEEDED", parse_projection_json, payload)


@pytest.mark.parametrize("kind,factory", [("chunk", chunk), ("bm25", bm25)])
def test_profiles_central_dispatch_copy_and_root_time_exclusion(kind, factory):
    document = factory()
    original = copy.deepcopy(document)
    checked = validate_document(document, expected_schema=PROFILE_TITLES[kind])
    assert checked == document and checked is not document
    if kind == "bm25": checked["params"]["b"] = 0
    assert document == original
    changed = copy.deepcopy(document)
    changed["created_at" if kind == "chunk" else "updated_at"] = "2026-09-01T12:34:56Z"
    assert runtime_projection_equal(kind, document, changed)
    assert runtime_projection_bytes(kind, document) == runtime_projection_bytes(kind, changed)
    assert runtime_projection_sha256(kind, document) == runtime_projection_sha256(kind, changed)
    changed["schema"] = "not-an-upstream-field"
    refused("RUNTIME_PROFILE_INVALID", validate_document, changed, expected_schema=PROFILE_TITLES[kind])


def test_minimal_markdown_component_is_valid():
    document = chunk()
    document["page_path"] = "wiki/.md"
    document["page_address"] = "syn-" + hashlib.sha256(b"wiki/.md").hexdigest()
    assert validate_runtime_record("chunk", document) == document
    assert validate_document(document, expected_schema=PROFILE_TITLES["chunk"]) == document


@pytest.mark.parametrize("field,value,code", [
    ("schema_version", 1.0, "RUNTIME_PROFILE_INVALID"),
    ("chunk_index", True, "RUNTIME_PROFILE_INVALID"),
    ("page_address", "c-000001\n", "RUNTIME_PROFILE_INVALID"),
    ("page_address", "c-０００００１", "RUNTIME_PROFILE_INVALID"),
    ("page_path", "wiki/a/../b.md", "RUNTIME_PROFILE_INVALID"),
    ("page_path", "C:/wiki/a.md", "RUNTIME_PROFILE_INVALID"),
    ("page_path", "wiki/ab\\cd.md", "RUNTIME_PROFILE_INVALID"),
    ("prefix", " x ", "RUNTIME_PROFILE_INVALID"),
    ("prefix_source", "skipped", "RUNTIME_PROFILE_INVALID"),
    ("created_at", "2026-02-30T00:00:00Z", "RUNTIME_PROFILE_INVALID"),
    ("created_at", "2026-08-31T00:00:60Z", "RUNTIME_PROFILE_INVALID"),
    ("created_at", "2026-08-31T00:00:00+00:00", "RUNTIME_PROFILE_INVALID"),
    ("created_at", "2026-08-31T00:00:00.0Z", "RUNTIME_PROFILE_INVALID"),
    ("page_address", "syn-" + "a" * 64, "RUNTIME_CONTENT_MISMATCH"),
    ("char_count", 0, "RUNTIME_CONTENT_MISMATCH"),
    ("body_hash", "sha256:" + "0" * 64, "RUNTIME_CONTENT_MISMATCH"),
    ("contextualized_text", "changed", "RUNTIME_CONTENT_MISMATCH"),
])
def test_chunk_refusals(field, value, code):
    document = chunk(); document[field] = value
    refused(code, validate_runtime_record, "chunk", document)


@pytest.mark.parametrize("mutation,code", [
    ("int-float", "RUNTIME_PROFILE_INVALID"), ("params-bool", "RUNTIME_PROFILE_INVALID"),
    ("params-extra", "RUNTIME_PROFILE_INVALID"), ("missing-hash", "RUNTIME_PROFILE_INVALID"),
    ("bad-id", "RUNTIME_PROFILE_INVALID"), ("bad-path", "RUNTIME_PROFILE_INVALID"),
    ("count", "RUNTIME_CONTENT_MISMATCH"), ("mean-ulp", "RUNTIME_CONTENT_MISMATCH"),
    ("df", "RUNTIME_CONTENT_MISMATCH"), ("unknown-posting", "RUNTIME_CONTENT_MISMATCH"),
    ("duplicate-posting", "RUNTIME_CONTENT_MISMATCH"), ("totals", "RUNTIME_CONTENT_MISMATCH"),
])
def test_bm25_refusals(mutation, code):
    document = bm25()
    if mutation == "int-float": document["docs"]["c-000001:0"]["dl"] = 3.0
    elif mutation == "params-bool": document["params"]["b"] = True
    elif mutation == "params-extra": document["params"]["updated_at"] = "2026-01-01"
    elif mutation == "missing-hash": del document["docs"]["c-000001:0"]["body_hash"]
    elif mutation == "bad-id": document["docs"]["c-000001:00"] = document["docs"].pop("c-000001:0")
    elif mutation == "bad-path": document["docs"]["c-000001:0"]["path"] = ".vault-meta/chunks/c-000001/chunk-0.json"
    elif mutation == "count": document["doc_count"] = 3
    elif mutation == "mean-ulp": document["avg_dl"] = math.nextafter(2.0, math.inf)
    elif mutation == "df": document["vocab"]["updated_at"]["df"] = 1
    elif mutation == "unknown-posting": document["vocab"]["检索"]["postings"][0][0] = "c-999999:0"
    elif mutation == "duplicate-posting": document["vocab"]["updated_at"]["postings"][1][0] = "c-000001:0"
    else: document["vocab"]["检索"]["postings"][0][1] = 2
    refused(code, validate_runtime_record, "bm25", document)


def test_nonvolatile_mutations_and_posting_order_are_material():
    document = bm25()
    changed = copy.deepcopy(document); changed["params"]["b"] = math.nextafter(0.75, math.inf)
    assert not runtime_projection_equal("bm25", document, changed)
    changed = copy.deepcopy(document); changed["vocab"]["updated_at"]["postings"].reverse()
    assert not runtime_projection_equal("bm25", document, changed)
    changed = copy.deepcopy(document); changed["vocab"]["created_at"] = changed["vocab"].pop("updated_at")
    assert not runtime_projection_equal("bm25", document, changed)
    changed = chunk(); changed["page_body_hash"] = "sha256:" + "b" * 64
    assert not runtime_projection_equal("chunk", chunk(), changed)


def test_empty_index_and_numeric_equivalence():
    document = bm25(); document.update(docs={}, vocab={}, doc_count=0, avg_dl=-0.0)
    validate_runtime_record("bm25", document)
    changed = copy.deepcopy(document); changed["avg_dl"] = 0
    assert runtime_projection_equal("bm25", document, changed)


def test_equality_checks_both_sides_and_preflight_before_removal():
    document = chunk(); document["created_at"] = document
    refused("PROJECTION_VALUE_INVALID", runtime_projection_equal, "chunk", document, document)
    refused("PROJECTION_VALUE_INVALID", runtime_projection_equal, "chunk", chunk(), document)
    refused("PROJECTION_VALUE_INVALID", validate_document, document, expected_schema=PROFILE_TITLES["chunk"])
    refused("PROJECTION_VALUE_INVALID", validate_runtime_record, StringSubclass("chunk"), chunk())


def test_markdown_exact_bytes_and_no_size_limit():
    assert markdown_projection_equal(b"", b"")
    assert not markdown_projection_equal(b"a\n", b"a\r\n")
    assert markdown_projection_equal(b"\xff", b"\xff")
    for value in [None, "", bytearray(), memoryview(b"")]:
        refused("PROJECTION_VALUE_INVALID", markdown_projection_equal, b"", value)
    large = b"a" * (MAX_JSON_BYTES + 1)
    assert markdown_projection_equal(large, large)


def test_runtime_apis_do_not_access_caller_paths(monkeypatch):
    valid_chunk, valid_index = chunk(), bm25()
    validate_runtime_record("chunk", valid_chunk)
    validate_runtime_record("bm25", valid_index)  # warm immutable schema registry
    def forbidden(*args, **kwargs):
        pytest.fail("runtime comparison attempted I/O")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert runtime_projection_equal("chunk", valid_chunk, copy.deepcopy(valid_chunk))
    assert runtime_projection_equal("bm25", valid_index, copy.deepcopy(valid_index))
    parse_projection_json(b'{"a":0.1}')
