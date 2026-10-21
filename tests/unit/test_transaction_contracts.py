"""Pure API refusal, byte snapshots and declaration material regressions."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.transaction_contracts import (
    HEAD_PATH, attach_runtime_result, attach_upstream_inspection,
    transaction_declaration_hash, validate_transaction, verify_transaction_bytes,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/contracts"


def proposal():
    return json.loads((FIXTURES / "valid/video-paper-wiki.transaction-facade.v1.json").read_text())


def capture():
    document = proposal()
    digest = hashlib.sha256(b"").hexdigest()
    path = f".raw/captured/{digest}.pdf"
    document.update(operation_type="capture", receipt=None, head=None,
                    writes=[dict(path=path, role="business", mode="create", sha256=digest,
                                 size_bytes=0, original_size_bytes=0, original_mode=None)],
                    expected_hashes={path: None})
    return seal(document)


def seal(document):
    document["declaration_sha256"] = transaction_declaration_hash(document)
    return document


def refusal(code, document):
    with pytest.raises(ContractError) as caught:
        validate_transaction(document)
    assert caught.value.code == code
    assert caught.value.exit_code == 2
    assert "instance_pointer" in caught.value.details


def test_hash_excludes_exactly_status_fields_and_binds_unknown_material():
    document = proposal()
    digest = transaction_declaration_hash(document)
    for name in ("phase", "declaration_sha256", "inspection", "runtime_result"):
        changed = copy.deepcopy(document)
        changed[name] = {"unvalidated": True}
        assert transaction_declaration_hash(changed) == digest
    document["additional_material"] = {"x": 1}
    assert transaction_declaration_hash(document) != digest
    refusal("SCHEMA_INVALID", document)


@pytest.mark.parametrize("field", ["schema", "operation_id", "operation_type", "writes", "expected_hashes", "read_preconditions", "claimed_inputs", "address_requests", "source_manifest_updates", "engine_expanded_paths", "receipt", "head", "input_bundle_sha256"])
def test_hash_requires_every_material_field(field):
    document = proposal()
    del document[field]
    with pytest.raises(ContractError, match="material") as caught:
        transaction_declaration_hash(document)
    assert caught.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("value", [1.0, float("nan"), (), set(), b"x", object()])
def test_hash_and_validation_have_separate_nonjson_errors(value):
    document = proposal()
    document["payload"] = value
    refusal("SCHEMA_INVALID", document)
    with pytest.raises(ContractError) as caught:
        transaction_declaration_hash(document)
    assert caught.value.code == "CANONICAL_JSON_INVALID"


def test_cycle_and_shared_acyclic_values():
    document = proposal()
    document["payload"] = document
    refusal("SCHEMA_INVALID", document)
    with pytest.raises(ContractError) as caught:
        transaction_declaration_hash(document)
    assert caught.value.code == "CANONICAL_JSON_INVALID"
    shared = []
    document = proposal()
    document["address_requests"] = document["engine_expanded_paths"] = shared
    validate_transaction(document)


@pytest.mark.parametrize("bad", ["/absolute", "a\\b", "a//b", "a/../b", "a/./b", "a/\x7f", "a/\ud800", "a/e\u0301", "a/" + "z" * 1023, ".GIT/config", "x/.VaUlT-MeTa/a"])
def test_lexical_read_paths(bad):
    document = capture()
    document["read_preconditions"] = {bad: None}
    refusal("TRANSACTION_PATH_INVALID", document)


@pytest.mark.parametrize("legacy", ["old/CON", "old/中文 notes?.md", "old/trailing.", "sequence", "operation_id"])
def test_legacy_reads_do_not_inherit_destination_grammar(legacy):
    document = capture()
    document["read_preconditions"] = {legacy: None}
    validate_transaction(seal(document))


@pytest.mark.parametrize("tail", ["CON.md", "nul", "COM1.foo", "name.", "中文", "with space", "a?/b"])
def test_new_component_refusals(tail):
    document = proposal()
    document["writes"][0]["path"] = "wiki/papers/" + tail
    refusal("TRANSACTION_PATH_INVALID", document)


@pytest.mark.parametrize("change", ["empty", "missing", "extra", "create-old", "create-mode", "replace-absent"])
def test_snapshot_declaration_failures(change):
    document = capture()
    path = document["writes"][0]["path"]
    if change == "empty":
        document["writes"] = []
        document["expected_hashes"] = {}
        code = "TRANSACTION_LIMIT_EXCEEDED"
    else:
        code = "TRANSACTION_PRECONDITION_MISMATCH"
        if change == "missing": document["expected_hashes"] = {}
        elif change == "extra": document["expected_hashes"]["wiki/papers/extra.md"] = None
        elif change == "create-old": document["expected_hashes"][path] = "a" * 64
        elif change == "create-mode": document["writes"][0]["original_mode"] = 384
        else:
            document = proposal()
            document["writes"][0]["mode"] = "replace"
            document["writes"][0]["original_mode"] = 384
    refusal(code, document)


@pytest.mark.parametrize("field", ["size_bytes", "original_size_bytes"])
def test_size_edges_without_allocating_payloads(field):
    document = proposal()
    write = document["writes"][0]
    write[field] = 67108865
    refusal("TRANSACTION_LIMIT_EXCEEDED", document)


@pytest.mark.parametrize("value", [None, "", bytearray(), memoryview(b""), b"wrong"])
def test_exact_write_byte_types(value):
    document = capture()
    path = document["writes"][0]["path"]
    with pytest.raises(ContractError) as caught:
        verify_transaction_bytes(document, write_bytes={path: value}, original_bytes={path: None}, read_bytes={})
    assert caught.value.code == "TRANSACTION_BYTES_MISMATCH"


def test_bytes_validates_document_before_snapshot_shape():
    document = capture()
    document["declaration_sha256"] = "0" * 64
    with pytest.raises(ContractError) as caught:
        verify_transaction_bytes(document, write_bytes=None, original_bytes=None, read_bytes=None)
    assert caught.value.code == "TRANSACTION_DECLARATION_MISMATCH"


def test_central_return_identity_and_wrapper_independence():
    document = proposal()
    assert validate_document(document) is document
    result = validate_transaction(document)
    result["receipt"]["writes"].clear()
    assert document["receipt"]["writes"]


def test_attach_rejects_bad_shapes_without_mutation():
    document = capture()
    before = copy.deepcopy(document)
    cycle = {}; cycle["self"] = cycle
    with pytest.raises(ContractError) as caught:
        attach_upstream_inspection(document, cycle)
    assert caught.value.code == "SCHEMA_INVALID"
    assert document == before
    with pytest.raises(ContractError) as caught:
        attach_runtime_result(document, None)
    assert caught.value.code == "TRANSACTION_UPSTREAM_MISMATCH"


def publication_at(path, *, operation="generic", mode="create", original_mode=0):
    """Rebind a complete receipt chain for focused authority/permission tests."""
    from video_paper_wiki.identity import receipt_intent_sha256
    from video_paper_wiki.jcs import canonicalize
    document = proposal()
    old_head = canonicalize(document["head"])
    old_receipt = canonicalize(document["receipt"])
    old_receipt_path = document["head"]["receipt_path"]
    business = document["writes"][0]
    business.update(path=path, mode=mode, original_mode=original_mode if mode == "replace" else None)
    before = hashlib.sha256(b"").hexdigest() if mode == "replace" else None
    document["expected_hashes"] = {path: before}
    receipt = document["receipt"]
    document["operation_type"] = receipt["operation_type"] = operation
    receipt["writes"] = [{"path": path, "mode": mode, "before_sha256": before, "after_sha256": business["sha256"]}]
    if operation == "ingest":
        receipt["sequence"] = 2
        receipt["previous"] = {"path": old_receipt_path, "sha256": hashlib.sha256(old_receipt).hexdigest()}
        document["read_preconditions"] = {old_receipt_path: hashlib.sha256(old_receipt).hexdigest()}
        document["writes"][-1].update(mode="replace", original_mode=511, original_size_bytes=len(old_head))
        document["expected_hashes"][HEAD_PATH] = hashlib.sha256(old_head).hexdigest()
    else:
        document["expected_hashes"][HEAD_PATH] = None
    receipt["intent_sha256"] = receipt_intent_sha256(receipt)
    receipt_path = f"wiki/meta/operations/{receipt['sequence']:012d}-genesis.json"
    document["expected_hashes"][receipt_path] = None
    receipt_bytes = canonicalize(receipt)
    document["head"].update(sequence=receipt["sequence"], receipt_path=receipt_path, receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest())
    for write, content, dest in [(document["writes"][1], receipt_bytes, receipt_path),
                                 (document["writes"][2], canonicalize(document["head"]), HEAD_PATH)]:
        write.update(path=dest, sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
    return seal(document)


@pytest.mark.parametrize("path", ["wiki/papers/p.md", "wiki/code/c.md", "wiki/concepts/c.md", "wiki/meta/ledgers/source-ledger.json", "wiki/meta/records/r.json", "wiki/meta/reviews/r.json", "wiki/meta/gates/g.json", "wiki/meta/registries/gate-heads.json"])
@pytest.mark.parametrize("operation", ["generic", "ingest"])
def test_complete_business_whitelist(path, operation):
    validate_transaction(publication_at(path, operation=operation))


@pytest.mark.parametrize("path", ["wiki/index.md", "wiki/notes/n.md", "wiki/meta/operations/fake.json", "wiki/meta/registries/other.json", ".raw/.manifest.json", "Wiki/papers/p.md"])
def test_paths_outside_business_authority(path):
    document = publication_at(path)
    with pytest.raises(ContractError) as caught:
        validate_transaction(document)
    # The hidden legacy manifest also violates new component grammar.
    assert caught.value.code in {"SCHEMA_INVALID", "TRANSACTION_POLICY_INVALID", "TRANSACTION_PATH_INVALID"}


@pytest.mark.parametrize("path", ["wiki/meta/reviews/r.json", "wiki/meta/gates/g.json", ".raw/derived/x.txt"])
def test_append_only_business_refuses_replace(path):
    refusal("TRANSACTION_POLICY_INVALID", publication_at(path, operation="ingest", mode="replace"))


def test_derived_write_only_for_ingest():
    validate_transaction(publication_at(".raw/derived/x.txt", operation="ingest"))
    refusal("TRANSACTION_POLICY_INVALID", publication_at(".raw/derived/x.txt"))


@pytest.mark.parametrize("mode", [0, 384, 511])
def test_replacement_permissions_preserved(mode):
    document = publication_at("wiki/papers/p.md", mode="replace", original_mode=mode)
    validate_transaction(document)


@pytest.mark.parametrize("count", [1, 1024, 1025])
def test_write_count_edges(count):
    document = capture()
    prototype = document["writes"][0]
    document["writes"] = [dict(prototype, path=f".raw/captured/{i:064x}.pdf", sha256=f"{i:064x}") for i in range(count)]
    document["expected_hashes"] = {write["path"]: None for write in document["writes"]}
    seal(document)
    if count > 1024:
        refusal("TRANSACTION_LIMIT_EXCEEDED", document)
    else:
        validate_transaction(document)


def test_new_total_inclusive_boundary():
    document = capture()
    prototype = document["writes"][0]
    document["writes"] = [dict(prototype, path=f".raw/captured/{i:064x}.pdf", sha256=f"{i:064x}", size_bytes=67108864) for i in range(2)]
    document["expected_hashes"] = {write["path"]: None for write in document["writes"]}
    validate_transaction(seal(document))
    document["writes"].append(dict(prototype, path=f".raw/captured/{2:064x}.pdf", sha256=f"{2:064x}", size_bytes=1))
    document["expected_hashes"][document["writes"][-1]["path"]] = None
    refusal("TRANSACTION_LIMIT_EXCEEDED", document)


@pytest.mark.parametrize("field", ["original_mode", "sequence"])
def test_oversized_python_integer_keeps_typed_schema_refusal(field):
    document = proposal()
    if field == "sequence":
        document["head"][field] = 10 ** 5000
    else:
        document["writes"][0][field] = 10 ** 5000
    refusal("SCHEMA_INVALID", document)
