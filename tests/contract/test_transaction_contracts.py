"""Frozen transaction/head fixtures and publication refusal contracts."""
import copy
import json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.transaction_contracts import validate_operation_head, validate_transaction

ROOT = Path(__file__).resolve().parents[1] / "fixtures/contracts"


def load(name):
    return json.loads((ROOT / name).read_text())


@pytest.mark.parametrize("filename,code", [
    ("invalid-head-sequence.json", "TRANSACTION_RECEIPT_MISMATCH"),
    ("invalid-declaration.json", "TRANSACTION_DECLARATION_MISMATCH"),
])
def test_invalid_fixtures(filename, code):
    with pytest.raises(ContractError) as caught:
        validate_document(load("transaction/" + filename))
    assert caught.value.code == code


@pytest.mark.parametrize("field,value", [("sequence", 0), ("sequence", 10**12), ("sequence", True), ("sequence", 1.0), ("receipt_sha256", "a" * 64 + "\n"), ("receipt_path", "wiki/meta/operations/000000000001-genesis.json\n")])
def test_head_boundaries(field, value):
    document = load("valid/video-paper-wiki.operation-head.v1.json")
    document[field] = value
    with pytest.raises(ContractError):
        validate_operation_head(document)


@pytest.mark.parametrize("case,code", [
    ("head-first", "TRANSACTION_ORDER_INVALID"),
    ("receipt-path", "TRANSACTION_RECEIPT_MISMATCH"),
    ("head-digest", "TRANSACTION_RECEIPT_MISMATCH"),
    ("receipt-bytes", "TRANSACTION_RECEIPT_MISMATCH"),
    ("intent", "RECEIPT_INTENT_MISMATCH"),
    ("no-business", "TRANSACTION_RECEIPT_MISMATCH"),
    ("no-head", "TRANSACTION_RECEIPT_MISMATCH"),
])
def test_publication_correlations(case, code):
    document = load("valid/video-paper-wiki.transaction-facade.v1.json")
    if case == "head-first": document["writes"] = document["writes"][-1:] + document["writes"][:-1]
    elif case == "receipt-path":
        write = document["writes"][1]
        old = write["path"]; write["path"] = old.replace("genesis", "other")
        document["expected_hashes"][write["path"]] = document["expected_hashes"].pop(old)
    elif case == "head-digest": document["head"]["receipt_sha256"] = "0" * 64
    elif case == "receipt-bytes": document["writes"][1]["size_bytes"] += 1
    elif case == "intent": document["receipt"]["intent_sha256"] = "0" * 64
    elif case == "no-head": document["head"] = None
    else:
        path = document["writes"].pop(0)["path"]; del document["expected_hashes"][path]
    with pytest.raises(ContractError) as caught:
        validate_transaction(document)
    assert caught.value.code == code


@pytest.mark.parametrize("field,value", [("address_requests", [{}]), ("source_manifest_updates", {"legacy": {}}), ("engine_expanded_paths", [".raw/.manifest.json"])])
def test_empty_expansion_policy_is_schema_closed(field, value):
    document = load("valid/video-paper-wiki.transaction-facade.v1.json")
    document[field] = value
    with pytest.raises(ContractError) as caught:
        validate_transaction(document)
    assert caught.value.code == "SCHEMA_INVALID"
