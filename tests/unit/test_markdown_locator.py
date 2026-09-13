"""Exact Unicode/CRLF tests over synthetic Markdown, never inferred PDF boxes."""
from __future__ import annotations

import copy
import json

import pytest

from tests.source_semantics_fixture import FIXTURES, locator_for, source_fixture
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import evidence_fingerprint
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import decode_ledger_evidence, encode_ledger_evidence
from video_paper_wiki.markdown_locator import (
    PREFIX, decode_evidence, decode_markdown_locator, encode_evidence, encode_markdown_locator,
    evidence_fingerprint_versioned, evidence_profile, resolve_markdown_locator,
)
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.source_versions import associate_source


@pytest.mark.parametrize("excerpt", ["精确", "e\u0301", "😀", "evidence.\r\nSecond"])
def test_exact_decoded_unicode_spans_preserve_bytes(excerpt):
    a, raw, _ = source_fixture()
    start = raw.decode().index(excerpt)
    loc = locator_for(a, raw, span=(start, start + len(excerpt)))
    wire = encode_markdown_locator(loc)
    assert decode_markdown_locator(wire) == loc
    assert resolve_markdown_locator(loc, a, raw) == excerpt
    assert loc["excerpt_sha256"] == sha(excerpt.encode())
    assert len(wire.encode()) < 65536


def test_cross_page_and_unanchored_spans_are_exact():
    a, raw, _ = source_fixture()
    p1, p2 = a["observation"]["pages"]
    loc = locator_for(a, raw, span=(p1["text_start"], p2["text_end"]), anchor=None)
    assert "page-2" in resolve_markdown_locator(loc, a, raw)
    with pytest.raises(ContractError) as caught:
        resolve_markdown_locator(loc | {"page_anchor": "page-1"}, a, raw)
    assert caught.value.code == "MARKDOWN_LOCATOR_INVALID"


@pytest.mark.parametrize("field,value", [("charspan", [0, 0]), ("charspan", [True, 10]), ("charspan", [-1, 1]), ("charspan", [0, 99999]), ("charspan", [0, 1, 2]), ("charspan", [1, "2"]), ("excerpt_sha256", "0" * 64), ("page_anchor", "page-999"), ("source_id", "src-other"), ("sha256", "0" * 64), ("path", "../bad"), ("extra", True)])
def test_malformed_or_unbound_locator_refuses(field, value):
    a, raw, _ = source_fixture()
    loc = locator_for(a, raw)
    loc[field] = value
    with pytest.raises(ContractError) as caught:
        resolve_markdown_locator(loc, a, raw)
    assert caught.value.code == "MARKDOWN_LOCATOR_INVALID"


@pytest.mark.parametrize("case", ["prefix", "whitespace", "duplicate_key", "extra_envelope", "missing_envelope", "invalid_json", "surrogate", "float", "trailing", "over_limit"])
def test_wire_must_have_exact_canonical_spelling(case):
    a, raw, _ = source_fixture()
    wire = encode_markdown_locator(locator_for(a, raw))
    if case == "prefix":
        wire = wire.replace("v2:", "v1:", 1)
    elif case == "whitespace":
        wire = wire.replace("{", "{ ", 1)
    elif case == "duplicate_key":
        wire = wire.replace('"schema":', '"schema":"extra","schema":')
    elif case in {"extra_envelope", "missing_envelope"}:
        doc = json.loads(wire[len(PREFIX):])
        if case == "extra_envelope":
            doc["extra"] = True
        else:
            del doc["schema"]
        wire = PREFIX + canonicalize(doc).decode()
    elif case == "invalid_json":
        wire = PREFIX + "{"
    elif case == "surrogate":
        wire = PREFIX + '{"x":"\\ud800"}'
    elif case == "float":
        wire = PREFIX + '{"x":1.5}'
    elif case == "trailing":
        wire += "\n"
    else:
        wire = PREFIX + " " * 65536
    with pytest.raises(ContractError) as caught:
        decode_markdown_locator(wire)
    assert caught.value.code in {"MARKDOWN_LOCATOR_INVALID", "SOURCE_SEMANTICS_INVALID", "SOURCE_SEMANTICS_LIMIT"}
    assert type(caught.value.details["instance_pointer"]) is str


@pytest.mark.parametrize("relation,outer", [("supports", "supports"), ("contradicts", "contradicts"), ("uncertain", "context")])
def test_outer_transport_roundtrip_and_v1_refusal(relation, outer):
    a, raw, _ = source_fixture()
    item = {**locator_for(a, raw), "relation": relation}
    wire = encode_evidence(item)
    assert wire["relation"] == outer
    assert decode_evidence(wire) == item
    with pytest.raises(ContractError):
        decode_ledger_evidence(wire)
    with pytest.raises(ContractError):
        decode_evidence(wire | {"source_id": "src-other"})


def test_legacy_fingerprints_and_transport_are_byte_unchanged():
    evidence = json.loads((FIXTURES.parents[1] / "assessment-history/complete-vectors.json").read_bytes())["evidence"]
    old = [evidence["code"], evidence["pdf"], evidence["code"]]
    assert evidence_profile(old) == "legacy-v1"
    assert evidence_fingerprint_versioned(old) == evidence_fingerprint(old)
    assert evidence_fingerprint_versioned(old) != evidence_fingerprint_versioned(old[:2])
    for item in old:
        assert encode_evidence(item) == encode_ledger_evidence(item)
        assert decode_evidence(encode_evidence(item)) == decode_ledger_evidence(encode_ledger_evidence(item))


def test_mixed_fingerprint_binds_association_and_collapses_exact_duplicates():
    a, raw, authority = source_fixture()
    first = {**locator_for(a, raw), "relation": "supports"}
    observation = copy.deepcopy(a["observation"])
    observation["version"] = {"kind": "declared", "label": "v2"}
    b = associate_source(observation, raw_bytes=raw, existing=[a], **authority)["association"]
    second = {**locator_for(b, raw), "relation": "supports"}
    assert evidence_profile([first]) == "mixed-v2"
    assert evidence_fingerprint_versioned([first]) != evidence_fingerprint_versioned([second])
    assert evidence_fingerprint_versioned([first, second]) == evidence_fingerprint_versioned([second, first, first])
    assert evidence_fingerprint_versioned([first]) == sha(b"video-paper-wiki.evidence.mixed.v2\0" + canonicalize([first]))
    assert evidence_fingerprint_versioned([first]) != evidence_fingerprint_versioned([first | {"relation": "contradicts"}])


def test_whitespace_excerpt_and_unicode_normalization_are_not_accepted():
    a, raw, _ = source_fixture()
    blank = raw.decode().index("\n\n")
    with pytest.raises(ContractError):
        resolve_markdown_locator(locator_for(a, raw, span=(blank, blank + 2), anchor=None), a, raw)
    start = raw.decode().index("e\u0301")
    loc = locator_for(a, raw, span=(start, start + 2))
    with pytest.raises(ContractError):
        resolve_markdown_locator(loc | {"excerpt_sha256": sha("é".encode())}, a, raw)
    with pytest.raises(ContractError):
        resolve_markdown_locator(loc, a, raw.replace(b"\r\n", b"\n"))


def test_mixed_legacy_bbox_display_values_do_not_change_fingerprint():
    a, raw, _ = source_fixture()
    pdf = json.loads((FIXTURES.parents[1] / "assessment-history/complete-vectors.json").read_bytes())["evidence"]["pdf"]
    item = {**locator_for(a, raw), "relation": "supports"}
    changed = copy.deepcopy(pdf)
    changed["bbox"] = [0.125, 1.5, 20.25, 30.875]
    assert decode_evidence(encode_evidence(changed)) == changed
    assert evidence_fingerprint_versioned([item, pdf]) == evidence_fingerprint_versioned([item, changed])
    assert encode_evidence(pdf) != encode_evidence(changed)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_legacy_bbox_cannot_enter_new_wrappers(bad):
    pdf = json.loads((FIXTURES.parents[1] / "assessment-history/complete-vectors.json").read_bytes())["evidence"]["pdf"]
    pdf["bbox"][0] = bad
    with pytest.raises(ContractError) as caught:
        encode_evidence(pdf)
    assert caught.value.code == "SOURCE_SEMANTICS_INVALID"


@pytest.mark.parametrize("field,value", [("page", 1.0), ("charspan", [0.0, 1]), ("extra", {"kind": "pdf", "bbox": [0.5, 1.0, 2.0, 3.0]})])
def test_legacy_float_exception_is_only_the_four_bbox_values(field, value):
    pdf = json.loads((FIXTURES.parents[1] / "assessment-history/complete-vectors.json").read_bytes())["evidence"]["pdf"]
    pdf[field] = value
    with pytest.raises(ContractError) as caught:
        encode_evidence(pdf)
    assert caught.value.code == "SOURCE_SEMANTICS_INVALID"
