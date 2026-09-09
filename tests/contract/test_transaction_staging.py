from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.transaction_staging import validate_transaction_staging

ROOT = Path(__file__).resolve().parents[2]
VALID = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.transaction-staging.v1.json"
INVALID = ROOT / "tests/fixtures/contracts/invalid/video-paper-wiki.transaction-staging.v1.invalid.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_valid_direct_and_central_dispatch_and_copy() -> None:
    document = load(VALID)
    direct = validate_transaction_staging(document)
    assert direct == document and direct is not document
    assert direct["content_files"] is not document["content_files"]
    assert validate_document(document) is document


def test_invalid_fixture_fails_semantic_relation() -> None:
    for function in (validate_transaction_staging, validate_document):
        with pytest.raises(ContractError) as caught:
            function(load(INVALID))
        assert caught.value.code == "TRANSACTION_STAGING_MISMATCH"


@pytest.mark.parametrize("mutation", ["reversed", "duplicate", "wrong_path"])
def test_order_uniqueness_and_digest_path_relation(mutation: str) -> None:
    document = load(VALID)
    first = document["content_files"][0]
    if mutation == "reversed":
        document["content_files"] = list(reversed(document["content_files"]))
    elif mutation == "duplicate":
        document["content_files"][1] = copy.deepcopy(first)
    else:
        first["content_file"] = "transaction-inspect/content/" + "0" * 64
    with pytest.raises(ContractError) as caught:
        validate_transaction_staging(document)
    assert caught.value.code in {"SCHEMA_INVALID", "TRANSACTION_STAGING_MISMATCH"}


@pytest.mark.parametrize("bad", [{1: True}, {None: True}, {("x",): True}])
def test_non_string_root_keys_are_schema_invalid(bad: dict) -> None:
    document = load(VALID)
    document.update(bad)
    with pytest.raises(ContractError) as caught:
        validate_transaction_staging(document)
    assert caught.value.code == "SCHEMA_INVALID"


def test_cycle_is_schema_invalid() -> None:
    document = load(VALID)
    cycle: list[object] = []
    cycle.append(cycle)
    document["content_files"] = cycle
    with pytest.raises(ContractError) as caught:
        validate_transaction_staging(document)
    assert caught.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("value", [1.0, True])
def test_integer_fields_refuse_float_and_bool(value: object) -> None:
    document = load(VALID)
    document["bundle_size_bytes"] = value
    with pytest.raises(ContractError) as caught:
        validate_transaction_staging(document)
    assert caught.value.code == "SCHEMA_INVALID"
