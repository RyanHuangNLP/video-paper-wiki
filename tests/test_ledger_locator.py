"""Exact wire vectors and hostile boundary cases for the supplied-data codec."""
import builtins
import copy
import hashlib
import json
import math
import socket
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, schema_by_title
from video_paper_wiki.identity import evidence_fingerprint
from video_paper_wiki.ledger_locator import (
    PREFIX, decode_ledger_evidence, decode_ledger_locator,
    encode_ledger_evidence, encode_ledger_locator,
)

VECTORS = json.loads((Path(__file__).parent / "fixtures/ledger-locator/wire-vectors.json").read_text())["vectors"]
LOC = "LEDGER_LOCATOR_INVALID"
EVI = "LEDGER_EVIDENCE_INVALID"
LIMIT = "PROJECTION_LIMIT_EXCEEDED"


def pdf():
    return copy.deepcopy(VECTORS[1]["locator"])


def code():
    return copy.deepcopy(VECTORS[2]["locator"])


def wire(envelope):
    # Test adversaries deliberately use non-production integer envelope JSON.
    return PREFIX + json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def envelope(locator=None, ratios=None):
    result = {"schema": "video-paper-wiki.ledger-locator.v1", "locator": pdf() if locator is None else locator}
    if ratios is not None:
        result["bbox_rationals"] = ratios
    return result


def refused(expected, function, *args, pointer=None):
    with pytest.raises(ContractError) as caught:
        function(*args)
    error = caught.value
    assert error.code == expected and error.exit_code == 2
    assert type(error.details["instance_pointer"]) is str
    json.dumps(error.details, ensure_ascii=False).encode("utf-8")
    if pointer is not None:
        assert error.details["instance_pointer"] == pointer


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["name"])
def test_independent_complete_wire_and_sha_vectors(vector):
    actual = encode_ledger_locator(vector["locator"])
    assert actual.encode() == vector["wire"].encode()
    assert hashlib.sha256(actual.encode()).hexdigest() == vector["sha256"]
    restored = decode_ledger_locator(vector["wire"])
    assert restored == vector["locator"]
    assert encode_ledger_locator(restored) == vector["wire"]


@pytest.mark.parametrize("domain_relation,upstream_relation", [("supports", "supports"), ("contradicts", "contradicts"), ("uncertain", "context")])
@pytest.mark.parametrize("factory", [pdf, code])
def test_flat_evidence_transport_and_copy(domain_relation, upstream_relation, factory):
    original = {**factory(), "relation": domain_relation}
    before = copy.deepcopy(original)
    encoded = encode_ledger_evidence(original)
    assert encoded == {"source_id": original["source_id"], "relation": upstream_relation,
                       "locator": encode_ledger_locator(factory())}
    restored = decode_ledger_evidence(encoded)
    assert restored == original and restored is not original
    assert evidence_fingerprint([original]) == evidence_fingerprint([restored])
    if "lines" in restored:
        restored["lines"]["start"] = 2
        assert original == before


def test_optional_coordinate_copy_and_numeric_equivalence():
    locator = {**pdf(), "bbox": [-0.0, 0, 1.0, -1.0], "charspan": [0, 4]}
    canonical = {**locator, "bbox": [0, 0, 1, -1]}
    assert encode_ledger_locator(locator) == encode_ledger_locator(canonical)
    restored = decode_ledger_locator(encode_ledger_locator(locator))
    assert all(type(v) is int for v in restored["bbox"])
    restored["bbox"][0] = 3
    restored["charspan"][0] = 1
    assert locator["bbox"][0] == 0 and locator["charspan"][0] == 0
    without = decode_ledger_locator(encode_ledger_locator(pdf()))
    assert "bbox" not in without and "charspan" not in without
    assert "symbol" not in decode_ledger_locator(encode_ledger_locator(code()))


@pytest.mark.parametrize("number", [float.fromhex("0x0.0000000000001p-1022"), float.fromhex("0x1.fffffffffffffp+1023"), math.nextafter(1.0, math.inf), -0.1, (1 << 2048) - 1, -((1 << 2048) - 1)])
def test_exact_numeric_extremes(number):
    locator = {**pdf(), "bbox": [number, 0, 1, 2]}
    restored = decode_ledger_locator(encode_ledger_locator(locator))
    assert restored["bbox"][0] == number
    if type(restored["bbox"][0]) is float:
        assert restored["bbox"][0].as_integer_ratio() == number.as_integer_ratio()


@pytest.mark.parametrize("pair", [[1, 0], [1, -2], [0, 2], [2, 4], [1, 3], [1, 1 << 1075], [(1 << 2047) - 1, 2], [(1 << 54) + 1, 2], [True, 1], [1, 2.0], [1], [1, 2, 3], None])
def test_invalid_ratios(pair):
    refused(LOC, decode_ledger_locator, wire(envelope(ratios=[pair, [0, 1], [1, 1], [2, 1]])), pointer="/bbox_rationals/0")


def test_ratio_magnitude_resource_limit_precedes_representation():
    refused(LIMIT, decode_ledger_locator, wire(envelope(ratios=[[1, 1 << 2048], [0, 1], [1, 1], [2, 1]])))


def test_complete_shapes_precede_locator_and_ratio_relationships():
    value = envelope({**pdf(), "charspan": [2, 1]}, ratios=[])
    refused(LOC, decode_ledger_locator, wire(value), pointer="/bbox_rationals")
    value = envelope(ratios=[[1, 3], [True, 1], [0, 1], [0, 1]])
    refused(LOC, decode_ledger_locator, wire(value), pointer="/bbox_rationals/1")


@pytest.mark.parametrize("factory,field,value", [
    (pdf, "page", True), (pdf, "page", 1.0), (pdf, "page", 0), (pdf, "page", 301),
    (pdf, "bbox", None), (pdf, "bbox", [0, 1, 2]), (pdf, "bbox", [0, 1, 2, True]),
    (pdf, "charspan", None), (pdf, "charspan", [1, 0]), (pdf, "charspan", [-1, 0]), (pdf, "charspan", [0, 1.0]),
    (pdf, "ref", ""), (pdf, "artifact_path", ".raw/captured/" + "a" * 64 + ".pdf"),
    (pdf, "source_id", "src-"), (pdf, "source_id", "source"),
    (code, "lines", {"start": 2, "end": 1}), (code, "lines", {"start": 0, "end": 1}),
    (code, "lines", {"start": 1, "end": True}), (code, "symbol", ""), (code, "symbol", None),
    (code, "commit", "C" * 40), (code, "path", "a/../b.py"), (code, "repository", "owner"),
])
def test_closed_domain_fields(factory, field, value):
    locator = factory(); locator[field] = value
    refused(LOC, encode_ledger_locator, locator)


@pytest.mark.parametrize("factory,field", [(pdf, "source_id"), (pdf, "artifact_path"), (pdf, "artifact_sha256"), (pdf, "text_sha256"), (code, "repository"), (code, "commit"), (code, "path"), (code, "snippet_sha256")])
def test_every_pattern_fullmatch_rejects_terminal_lf(factory, field):
    locator = factory(); locator[field] += "\n"
    refused(LOC, encode_ledger_locator, locator)


@pytest.mark.parametrize("mutation", [
    lambda d: {**d, "extra": 0}, lambda d: {"locator": d["locator"]},
    lambda d: {**d, "schema": "wrong"}, lambda d: {**d, "locator": []},
    lambda d: {**d, "locator": {**d["locator"], "bbox": [0, 1, 2, 3]}},
    lambda d: {**d, "locator": {**d["locator"], "relation": "supports"}},
    lambda d: {**d, "bbox_rationals": []},
    lambda d: {**d, "locator": code(), "bbox_rationals": [[0, 1]] * 4},
])
def test_envelope_shape_refusals(mutation):
    refused(LOC, decode_ledger_locator, wire(mutation(envelope())))


@pytest.mark.parametrize("change", [
    lambda s: s + "\n", lambda s: s.replace('{"locator"', '{ "locator"', 1),
    lambda s: s.replace('"page":1', '"page":1.0'), lambda s: s.replace('"page":1', '"page":1e0'),
    lambda s: s.replace('"page":1', '"page":NaN'), lambda s: s.replace('"page":1', '"page":Infinity'),
    lambda s: s.replace('"page":1', '"page":1e400'),
    lambda s: s.replace('"page":1', '"page":1,"page":1'),
    lambda s: s.replace('"page":1', '"page":1,"p\\u0061ge":1'),
    lambda s: s.replace('"kind"', '"k\\u0069nd"'),
    lambda s: PREFIX + '\ufeff' + s[len(PREFIX):],
    lambda s: PREFIX + json.dumps(json.loads(s[len(PREFIX):]), sort_keys=False),
])
def test_noncanonical_or_invalid_wire(change):
    refused(LOC, decode_ledger_locator, change(VECTORS[1]["wire"]))


def test_noncanonical_negative_zero_and_extra_numeric_spellings():
    good = wire(envelope(ratios=[[0, 1]] * 4))
    refused(LOC, decode_ledger_locator, good.replace("[0,1]", "[-0,1]", 1), pointer="")
    refused(LOC, decode_ledger_locator, good.replace("[0,1]", "[0,1e0]", 1))


@pytest.mark.parametrize("value", [None, 1, b"x", "legacy locator", "", PREFIX, PREFIX + "[]", PREFIX + "\ud800"])
def test_wire_argument_and_raw_errors(value):
    refused(LOC, decode_ledger_locator, value)


def test_wire_utf8_boundaries():
    base = pdf(); base["ref"] = "x"
    overhead = len(encode_ledger_locator(base).encode()) - 1
    for token in ("a", "中", "\n"):
        cost = len(json.dumps(token, ensure_ascii=False).encode()) - 2
        count, padding = divmod(65536 - overhead, cost)
        base["ref"] = token * count + "a" * padding
        encoded = encode_ledger_locator(base)
        assert len(encoded.encode()) == 65536
        assert decode_ledger_locator(encoded) == base
        refused(LIMIT, decode_ledger_locator, encoded + " ")
        base["ref"] += "a"
        refused(LIMIT, encode_ledger_locator, base)
    refused(LIMIT, decode_ledger_locator, "a" * 65537)


class DictSubclass(dict):
    pass


class StringSubclass(str):
    pass


@pytest.mark.parametrize("value", [DictSubclass(), StringSubclass("x"), (), Decimal("1"), {1: None}, object()])
def test_exact_types_and_root_keys(value):
    refused(LOC, encode_ledger_locator, value)
    refused(EVI, encode_ledger_evidence, value)
    refused(EVI, decode_ledger_evidence, value)


def test_preflight_error_layers_and_deep_inputs():
    cyclic = []; cyclic.append(cyclic)
    for field, value in [("ref", cyclic), ("bbox", [float("nan"), 0, 1, 2]), ("ref", "\ud800")]:
        refused(LOC, encode_ledger_evidence, {**pdf(), "relation": "supports", field: value}, pointer="/" + field + ("/0" if field == "bbox" or field == "ref" and value is cyclic else ""))
    refused(EVI, encode_ledger_evidence, {**pdf(), "relation": cyclic}, pointer="/relation/0")
    refused(EVI, decode_ledger_evidence, {"source_id": "src-a", "relation": "context", "locator": cyclic}, pointer="/locator/0")
    deep = None
    for _ in range(65): deep = [deep]
    refused(LIMIT, encode_ledger_locator, deep)
    refused(LIMIT, decode_ledger_locator, PREFIX + "[" * 65 + "]" * 65)
    refused(LIMIT, encode_ledger_locator, {**pdf(), "page": 1 << 2048})
    refused(LIMIT, decode_ledger_locator, PREFIX + '{"page":' + "9" * 618 + "}")


def test_resource_refusals_precede_copy_and_schema(monkeypatch):
    import video_paper_wiki.ledger_locator as codec
    def unexpected(*args, **kwargs):
        raise AssertionError("oversized input reached copying or schema access")
    monkeypatch.setattr(codec.copy, "deepcopy", unexpected)
    monkeypatch.setattr(codec, "schema_by_title", unexpected)
    refused(LIMIT, encode_ledger_locator, [None] * 1_000_000)
    refused(LIMIT, encode_ledger_locator, "a" * (64 * 1024 * 1024))
    refused(LIMIT, decode_ledger_locator, "a" * 65537)


def test_shared_acyclic_values_do_not_look_like_cycles():
    # This is invalid locator shape, but shared values are not non-JSON/cycles.
    # The field failure remains a normal locator error after complete preflight.
    shared = [0, 1]
    refused(LOC, encode_ledger_locator, {**pdf(), "charspan": shared, "extra": shared})


def test_evidence_phase_errors_and_forwarded_pointers():
    refused(EVI, encode_ledger_evidence, {"relation": "context"}, pointer="/relation")
    refused(LOC, encode_ledger_evidence, {"relation": "supports"})
    refused(LOC, encode_ledger_evidence, {**pdf(), "relation": "supports", "extra": 1})
    encoded = encode_ledger_evidence({**pdf(), "relation": "supports"})
    for field, value in [("relation", "uncertain"), ("source_id", "src-other"), ("source_id", "src-bad\n"), ("locator", None)]:
        refused(EVI, decode_ledger_evidence, {**encoded, field: value}, pointer="/" + field)
    refused(EVI, decode_ledger_evidence, {**encoded, "extra": 0})
    refused(LOC, decode_ledger_evidence, {**encoded, "locator": "legacy"}, pointer="")
    bad = envelope(); bad["locator"]["page"] = 301
    refused(LOC, decode_ledger_evidence, {**encoded, "locator": wire(bad)}, pointer="/locator/page")


def test_pure_operations_after_registry_warmup(monkeypatch):
    schema_by_title("video-paper-wiki.common.v1")
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected caller I/O")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for locator in (pdf(), code()):
        assert decode_ledger_locator(encode_ledger_locator(locator)) == locator
        evidence = {**locator, "relation": "uncertain"}
        assert decode_ledger_evidence(encode_ledger_evidence(evidence)) == evidence
