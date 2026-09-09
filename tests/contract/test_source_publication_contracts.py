from __future__ import annotations

import copy

import pytest

from tests.source_semantics_fixture import fixture
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import AUTHORITY, HEADS, PROPOSAL, REQUEST, parse_json


@pytest.mark.parametrize("schema", [REQUEST, AUTHORITY, PROPOSAL, HEADS])
def test_closed_source_publication_fixture(schema):
    value = fixture(schema)
    assert validate_document(value, schema) == value
    assert parse_json(canonicalize(value), schema=schema, exact=True) == value
    extra = {**value, "published": True}
    with pytest.raises(ContractError) as err:
        validate_document(extra, schema)
    assert err.value.code == "SOURCE_PUBLICATION_INVALID" and "instance_pointer" in err.value.details


@pytest.mark.parametrize("field", ["schema", "batch_id", "operation_id", "kind", "basis", "prospective_inventory_sha256", "payloads", "registration"])
def test_request_requires_every_durable_field(field):
    value = fixture(REQUEST)
    del value[field]
    with pytest.raises(ContractError) as err:
        validate_document(value, REQUEST)
    assert err.value.code == "SOURCE_PUBLICATION_INVALID"


@pytest.mark.parametrize("mutation", ["unsorted", "duplicate", "case-alias", "content-path", "digest-size", "oversize", "illegal-role", "root-records", "registration-kind", "basis-null"])
def test_request_payload_and_branch_binding(mutation):
    value = fixture(REQUEST)
    if mutation == "unsorted":
        value["payloads"].reverse()
    elif mutation == "duplicate":
        value["payloads"].append(copy.deepcopy(value["payloads"][0]))
    elif mutation == "case-alias":
        row = copy.deepcopy(value["payloads"][-1]); row["path"] = row["path"].replace("wiki/papers/", "wiki/papers/A")
        value["payloads"].extend([row, {**row, "path": row["path"].replace("/A", "/a")}])
        value["payloads"].sort(key=lambda x: x["path"])
    elif mutation == "content-path":
        value["payloads"][0]["content_file"] = "content/" + value["payloads"][0]["sha256"]
    elif mutation == "digest-size":
        value["payloads"][1].update({k: value["payloads"][0][k] for k in ("content_file", "sha256")})
        value["payloads"][1]["size_bytes"] = value["payloads"][0]["size_bytes"] + 1
    elif mutation == "oversize":
        value["payloads"][0]["size_bytes"] = 67108865
    elif mutation == "illegal-role":
        value["payloads"][0]["path"] = "wiki/meta/registries/operation-head.json"
    elif mutation == "root-records":
        value["payloads"][0]["path"] = "records/assessment-heads.json"
    elif mutation == "registration-kind":
        value["kind"] = "registration"
    else:
        value["basis"]["operation_head_sha256"] = None
    with pytest.raises(ContractError):
        validate_document(value, REQUEST)


@pytest.mark.parametrize("fields,value", [(("request_sha256",), "a" * 64),
    (("prospective_inventory_sha256",), "b" * 64), (("request", "basis", "operation_head_sha256"), "c" * 64),
    (("request", "operation_id"), "different"), (("transaction_staging", "batch_id"), "different"),
    (("upstream_authority", "transport", "bundle_sha256"), "d" * 64)])
def test_authority_rebinds_every_child(fields, value):
    doc = fixture(AUTHORITY)
    parent = doc
    for key in fields[:-1]:
        parent = parent[key]
    parent[fields[-1]] = value
    with pytest.raises(ContractError):
        validate_document(doc, AUTHORITY)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"n":1.5}', b'{"n":NaN}', b'{"n":Infinity}', b'{"a":"\xff"}', b'{', br'"\ud800"'])
def test_malformed_json_is_structured(raw):
    with pytest.raises(ContractError) as err:
        parse_json(raw, schema=REQUEST, exact=True)
    assert "instance_pointer" in err.value.details


@pytest.mark.parametrize("field,value", [("event_id", "ase-unsafe"), ("event_sha256", None), ("evidence_profile", "markdown-only")])
def test_assessment_registry_closed_values(field, value):
    doc = fixture(HEADS)
    next(iter(doc["heads"].values()))[field] = value
    with pytest.raises(ContractError) as err:
        validate_document(doc, HEADS)
    assert err.value.code == "SOURCE_PUBLICATION_INVALID"


def test_empty_assessment_registry_is_valid():
    assert validate_document({"schema": HEADS, "heads": {}}, HEADS)["heads"] == {}


def test_json_node_limit_preserves_its_specific_error_code():
    raw = b"[" + b"null," * 100000 + b"null]"
    with pytest.raises(ContractError) as err:
        parse_json(raw)
    assert err.value.code == "SOURCE_SEMANTICS_LIMIT"
    assert err.value.details["instance_pointer"]


def test_json_contract_error_preserves_original_details():
    doc = fixture(HEADS)
    next(iter(doc["heads"].values()))["event_sha256"] = None
    with pytest.raises(ContractError) as direct:
        validate_document(doc, HEADS)
    with pytest.raises(ContractError) as parsed:
        parse_json(canonicalize(doc), schema=HEADS)
    assert (parsed.value.code, parsed.value.message, parsed.value.details, parsed.value.exit_code) == (
        direct.value.code, direct.value.message, direct.value.details, direct.value.exit_code)
