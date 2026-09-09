"""Closed schema, bounded hostile input, and actual synthetic capture->ingest."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.source_semantics_fixture import compile_fixture, fixture, locator_for, selection, source_fixture
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.source_semantics_contracts import SCHEMAS, preflight


@pytest.mark.parametrize("schema", sorted(SCHEMAS))
def test_new_schema_valid_synthetic_fixture_and_closed_shape(schema):
    value = fixture(schema)
    assert validate_document(value, schema) == value
    with pytest.raises(ContractError) as caught:
        validate_document(value | {"unexpected": 1}, schema)
    assert caught.value.code == "SCHEMA_INVALID"
    assert type(caught.value.details["instance_pointer"]) is str


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1.0, {1: "value"}, b"bytes", {"bad": "\ud800"}, {"bad": "\0"}, {"bad": object()}, (1, 2)])
def test_strict_integer_json_preflight(value):
    with pytest.raises(ContractError) as caught:
        preflight(value)
    assert caught.value.code == "SOURCE_SEMANTICS_INVALID"


@pytest.mark.parametrize("kind", ["dict", "list", "str", "int"])
def test_subclasses_are_not_allowed(kind):
    parent = {"dict": dict, "list": list, "str": str, "int": int}[kind]
    custom = type("Custom", (parent,), {})
    value = custom() if kind != "int" else custom(1)
    with pytest.raises(ContractError) as caught:
        preflight(value)
    assert caught.value.code == "SOURCE_SEMANTICS_INVALID"


@pytest.mark.parametrize("case", ["cycle", "depth", "nodes", "integer", "string"])
def test_bounded_structure_precedes_recursive_schema_and_identity(case):
    if case == "cycle":
        value = []; value.append(value)
    elif case == "depth":
        value = 0
        for _ in range(50):
            value = [value]
    elif case == "nodes":
        value = [None] * 100001
    elif case == "integer":
        value = 9007199254740992
    else:
        value = "a" * (8388608 + 1)
    with pytest.raises(ContractError) as caught:
        preflight(value)
    assert caught.value.code == ("SOURCE_SEMANTICS_INVALID" if case == "cycle" else "SOURCE_SEMANTICS_LIMIT")


def test_material_preflight_order_is_stable_and_inputs_are_unchanged():
    from video_paper_wiki.canonical_compiler_v2 import compile_pages
    material, kwargs = compile_fixture()
    before = copy.deepcopy((material, kwargs))
    compile_pages(material, **kwargs)
    assert before == (material, kwargs)
    material["z"] = {"bad": 1.5}
    material["a"] = {"bad": 2.5}
    with pytest.raises(ContractError) as caught:
        compile_pages(material, **kwargs)
    assert caught.value.details["instance_pointer"] == "/a/bad"


@pytest.mark.parametrize("raw", [b'{', b'{"x":1,"x":2}', b'{"x":1.5}', b'{"x":"\\ud800"}', b'\xff', b'{"x":NaN}'])
def test_historical_parser_errors_are_public_contract_errors(raw):
    from video_paper_wiki.source_registration import historical_source_ledger
    with pytest.raises(ContractError) as caught:
        historical_source_ledger(raw)
    assert caught.value.code == "SOURCE_REGISTRATION_INVALID"
    assert "instance_pointer" in caught.value.details


def test_public_new_paper_schema_supplies_pointer_for_legacy_identity_refusal():
    value = fixture("video-paper-wiki.paper-record.v2")
    value["paper_id"] = "arxiv:2311.15127\n"
    with pytest.raises(ContractError) as caught:
        validate_document(value)
    assert type(caught.value.details["instance_pointer"]) is str


def test_actual_generic_capture_has_no_receipt_and_ingest_supplies_first_proof(checkout):
    from tests.upstream.test_markdown_source import _admit, _captured_fixture
    from tests.research.test_source_admission import apply_publication
    from video_paper_wiki.markdown_source import _proposal
    from video_paper_wiki.receipt_audit import HEAD
    from video_paper_wiki.source_versions import associate_source, validate_source_inventory
    from video_paper_wiki.jcs import canonicalize
    vault, _, authority, bound = _captured_fixture(checkout)
    raw = (vault / authority["stored_path"]).read_bytes()
    proposal = _proposal("synthetic-inspection-only", raw)
    assert proposal["receipt"] is None and proposal["head"] is None and proposal["claimed_inputs"] == []
    receipts_before = sorted((vault / "wiki/meta/operations").glob("*.json"))
    observed = authority["request"]["plan"]["observation"]
    kwargs = {"head_bytes": (vault / HEAD).read_bytes(),
              "receipt_bytes": {str(p.relative_to(vault)): p.read_bytes() for p in receipts_before},
              "ledger_bytes": (vault / "wiki/meta/ledgers/source-ledger.json").read_bytes()}
    with pytest.raises(ContractError) as caught:
        associate_source(observed, raw_bytes=raw, existing=[], **kwargs)
    assert caught.value.code == "SOURCE_REGISTRATION_INVALID"
    admitted = _admit(vault, authority, bound)
    apply_publication(checkout, vault, admitted["publication_authority"])
    receipts = {str(p.relative_to(vault)): p.read_bytes() for p in (vault / "wiki/meta/operations").glob("*.json")}
    assert len(receipts) == len(receipts_before) + 1
    kwargs.update(head_bytes=(vault / HEAD).read_bytes(), receipt_bytes=receipts,
                  ledger_bytes=(vault / "wiki/meta/ledgers/source-ledger.json").read_bytes())
    a = associate_source(observed, raw_bytes=raw, existing=[], **kwargs)["association"]
    assert a["registration"]["receipt_path"].endswith("-admit-md.json")
    snapshot = {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
    assert validate_source_inventory([a], raw_sources={a["raw"]["path"]: raw},
        extraction_artifacts={a["extraction"]["path"]: canonicalize(observed)},
        head_bytes=kwargs["head_bytes"], receipt_bytes=receipts,
        registration_ledgers={a["registration"]["source_ledger_path"]: kwargs["ledger_bytes"]}) == {a["association_id"]: a}
    assert snapshot == {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
    assert not list(vault.rglob("*.pdf"))
