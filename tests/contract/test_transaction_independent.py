"""Steward probes for frozen transaction-facade-v1 revision 1.

Expected bindings use independent sorted JSON for ASCII/BMP-key, integer-only
fixtures. Supplied upstream objects are deliberately synthetic: acceptance of
their correlations proves neither authentic execution nor historical audit.
"""
from __future__ import annotations

import builtins
import copy
import hashlib
import io
import json
import os
import socket
import subprocess

import pytest

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.transaction_contracts import (
    attach_runtime_result,
    attach_upstream_inspection,
    transaction_declaration_hash,
    validate_operation_head,
    validate_transaction,
    verify_transaction_bytes,
)

EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
CAPTURE_HASH = "fe56fecf436d9737c96abab854903cbfd5570dc06c69534205eba42bb5f263b1"
HEAD_PATH = "wiki/meta/registries/operation-head.json"
EXCLUDED = {"phase", "declaration_sha256", "inspection", "runtime_result"}


def _wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _seal(document):
    document["declaration_sha256"] = _sha(_wire({k: v for k, v in document.items() if k not in EXCLUDED}))
    return document


def _capture():
    path = f".raw/captured/{EMPTY_SHA}.bin"
    return _seal({
        "schema": "video-paper-wiki.transaction-facade.v1", "phase": "proposal",
        "operation_id": "independent-capture", "operation_type": "capture",
        "writes": [{"path": path, "role": "business", "mode": "create", "sha256": EMPTY_SHA,
                    "size_bytes": 0, "original_size_bytes": 0, "original_mode": None}],
        "expected_hashes": {path: None}, "read_preconditions": {}, "claimed_inputs": [],
        "address_requests": [], "source_manifest_updates": {}, "engine_expanded_paths": [],
        "receipt": None, "head": None, "input_bundle_sha256": "b" * 64,
        "inspection": None, "runtime_result": None,
    })


def _publication(*, sequence=1, claims=None):
    document = _capture()
    operation = f"independent-{sequence}"
    business = f"wiki/meta/records/independent-{sequence}.json"
    payload = b'{"fixture":true}'
    document.update(operation_id=operation, operation_type="generic")
    claimed = [{"path": p, "mode": "read", "sha256": _sha(b)} for p, b in sorted((claims or {}).items())]
    previous = None
    originals = {business: None}
    reads = dict(claims or {})
    if sequence > 1:
        old, old_bytes, _, _ = _publication()
        previous_path = old["head"]["receipt_path"]
        previous = {"path": previous_path, "sha256": _sha(old_bytes[previous_path])}
        reads[previous_path] = old_bytes[previous_path]
        originals[HEAD_PATH] = old_bytes[HEAD_PATH]
    else:
        originals[HEAD_PATH] = None
    receipt = {
        "schema": "video-paper-wiki.operation-receipt.v1", "sequence": sequence,
        "previous": previous, "operation_id": operation, "operation_type": "generic",
        "writes": [{"path": business, "mode": "create", "before_sha256": None,
                    "after_sha256": _sha(payload)}], "claimed_inputs": claimed,
    }
    receipt["intent_sha256"] = _sha(_wire({k: receipt[k] for k in (
        "sequence", "previous", "operation_id", "writes", "claimed_inputs")}))
    receipt_path = f"wiki/meta/operations/{sequence:012d}-{operation}.json"
    head = {"schema": "video-paper-wiki.operation-head.v1", "sequence": sequence,
            "receipt_path": receipt_path, "receipt_sha256": _sha(_wire(receipt))}
    supplied = {business: payload, receipt_path: _wire(receipt), HEAD_PATH: _wire(head)}
    originals[receipt_path] = None
    writes = []
    for path, data in supplied.items():
        prior = originals[path]
        writes.append({"path": path, "role": "head" if path == HEAD_PATH else
                       "receipt" if path == receipt_path else "business",
                       "mode": "replace" if prior is not None else "create",
                       "sha256": _sha(data), "size_bytes": len(data),
                       "original_size_bytes": len(prior) if prior is not None else 0,
                       "original_mode": 0o640 if prior is not None else None})
    document.update(writes=writes, expected_hashes={p: _sha(b) if b is not None else None
                    for p, b in originals.items()}, read_preconditions={p: _sha(b) for p, b in reads.items()},
                    claimed_inputs=claimed, receipt=receipt, head=head)
    return _seal(document), supplied, originals, reads


def _plan(document):
    return {"schema": "claude-obsidian.transaction-plan.v1", "operation_id": document["operation_id"],
            "operation_type": document["operation_type"], "valid": True,
            "changed_paths": [w["path"] for w in document["writes"]],
            "hashes": {w["path"]: w["sha256"] for w in document["writes"]},
            "modes": {w["path"]: 384 if w["mode"] == "create" else w["original_mode"]
                      for w in document["writes"]},
            "input_bundle_sha256": document["input_bundle_sha256"],
            "expanded_bundle_sha256": document["input_bundle_sha256"],
            "vault_identity": {"state": "existing", "device": 0, "inode": 123},
            "approval_sha256": "c" * 64}


def _result(plan):
    return {"schema": "claude-obsidian.transaction-result.v1", "status": "complete",
            "bundle_sha256": plan["input_bundle_sha256"], **{k: copy.deepcopy(plan[k]) for k in (
                "operation_id", "operation_type", "expanded_bundle_sha256", "approval_sha256",
                "changed_paths", "hashes", "modes")}}


def test_empty_capture_known_binding_and_copy_isolation():
    document = _capture()
    assert document["declaration_sha256"] == CAPTURE_HASH
    assert transaction_declaration_hash(document) == CAPTURE_HASH
    returned = validate_transaction(document)
    returned["writes"][0]["sha256"] = "0" * 64
    assert document["writes"][0]["sha256"] == EMPTY_SHA
    path = document["writes"][0]["path"]
    assert verify_transaction_bytes(document, write_bytes={path: b""},
                                    original_bytes={path: None}, read_bytes={}) is None


@pytest.mark.parametrize("sequence", [1, 2])
def test_publication_exact_bytes_across_proposal_inspection_and_optional_result(sequence):
    document, supplied, originals, reads = _publication(sequence=sequence)
    before = copy.deepcopy(document)
    checked_head = validate_operation_head(document["head"])
    checked_head["sequence"] = 42
    assert document["head"]["sequence"] == sequence
    plan = _plan(document)
    inspected = attach_upstream_inspection(document, plan)
    assert document == before and document["inspection"] is None
    assert inspected["runtime_result"] is None
    assert transaction_declaration_hash(inspected) == document["declaration_sha256"]
    result = _result(plan)
    complete = attach_runtime_result(inspected, result)
    assert inspected["runtime_result"] is None
    result["hashes"].clear()
    plan["hashes"].clear()
    verify_transaction_bytes(complete, write_bytes=supplied, original_bytes=originals, read_bytes=reads)
    with pytest.raises(ContractError):
        attach_runtime_result(complete, complete["runtime_result"])


def test_generic_claims_derived_and_captured_but_extra_legacy_reads_are_not_claims():
    claims = {".raw/derived/parser-v1/text.txt": b"legacy",
              f".raw/captured/{EMPTY_SHA}.bin": b""}
    document, supplied, originals, reads = _publication(sequence=2, claims=claims)
    document["read_preconditions"]["legacy/中文 notes?.md"] = None
    reads["legacy/中文 notes?.md"] = None
    _seal(document)
    verify_transaction_bytes(document, write_bytes=supplied, original_bytes=originals, read_bytes=reads)
    assert len(document["claimed_inputs"]) == 2


def test_read_count_is_not_write_count():
    document = _capture()
    document["read_preconditions"] = {f"legacy/{n}.md": None for n in range(1025)}
    _seal(document)
    path = document["writes"][0]["path"]
    verify_transaction_bytes(document, write_bytes={path: b""}, original_bytes={path: None},
                             read_bytes={p: None for p in document["read_preconditions"]})


@pytest.mark.parametrize("paths", [
    ["legacy/ΐ.md", "legacy/Ϊ́.md"],
    ["legacy/A/one.md", "legacy/a/two.md"],
    ["legacy/file", "legacy/file/child"],
])
def test_unicode_casefold_and_component_collisions(paths):
    document = _capture()
    document["read_preconditions"] = {p: None for p in paths}
    _seal(document)
    with pytest.raises(ContractError) as caught:
        validate_transaction(document)
    assert caught.value.code == "TRANSACTION_PATH_COLLISION"


@pytest.mark.parametrize("path", [".GIT/config", "legacy/.git/config", "legacy/.OBSIDIAN/x",
                                  "legacy/.vault-meta/x", "legacy/e\u0301.md", "legacy/x\n"])
def test_all_read_components_obey_explicit_lexical_policy(path):
    document = _capture()
    document["read_preconditions"] = {path: None}
    _seal(document)
    with pytest.raises(ContractError):
        validate_transaction(document)


@pytest.mark.parametrize("field", ["size_bytes", "original_size_bytes"])
@pytest.mark.parametrize("bad", [0.0, False])
def test_exact_integer_types_even_when_jsonschema_would_accept_float(field, bad):
    document = _capture()
    document["writes"][0][field] = bad
    with pytest.raises(ContractError) as caught:
        validate_document(document)
    assert caught.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("bad", [1.0, True])
def test_head_sequence_exact_integer_precedes_linkage(bad):
    document, *_ = _publication()
    head = document["head"]
    head["sequence"] = bad
    with pytest.raises(ContractError) as caught:
        validate_operation_head(head)
    assert caught.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("field", ["operation_id", "input_bundle_sha256", "declaration_sha256"])
def test_trailing_lf_cannot_pass_scalar_regex(field):
    document = _capture()
    document[field] += "\n"
    with pytest.raises(ContractError) as caught:
        validate_document(document)
    assert caught.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("bad", [1, None, ("key",)])
def test_nonstring_root_keys_are_typed_errors_for_public_registry(bad):
    document = _capture()
    document[bad] = "not-json"
    with pytest.raises(ContractError) as caught:
        validate_document(document)
    assert caught.value.code == "SCHEMA_INVALID"


def test_cycles_distinguish_validator_from_standalone_hash_error():
    document = _capture()
    document["read_preconditions"]["legacy/cycle"] = document
    for validator in (validate_transaction, validate_document):
        with pytest.raises(ContractError) as caught:
            validator(document)
        assert caught.value.code == "SCHEMA_INVALID"
    with pytest.raises(ContractError) as caught:
        transaction_declaration_hash(document)
    assert caught.value.code == "CANONICAL_JSON_INVALID"


@pytest.mark.parametrize("change", ["input", "expanded", "approval", "order", "modes", "hashes", "extra"])
def test_supplied_evidence_must_match_every_binding(change):
    document, *_ = _publication(sequence=2)
    plan = _plan(document)
    inspected = attach_upstream_inspection(document, plan)
    result = _result(plan)
    if change in ("input", "expanded", "approval"):
        field = {"input": "bundle_sha256", "expanded": "expanded_bundle_sha256",
                 "approval": "approval_sha256"}[change]
        result[field] = "d" * 64
    elif change == "order":
        result["changed_paths"].reverse()
    elif change in ("modes", "hashes"):
        result[change].pop(HEAD_PATH)
    else:
        result["extra"] = True
    with pytest.raises(ContractError):
        attach_runtime_result(inspected, result)


def test_hash_excludes_only_phase_evidence_and_self_and_includes_unknown_material():
    document = _capture()
    changed = copy.deepcopy(document)
    changed.update(phase="inspected", inspection={"synthetic": True}, runtime_result={"synthetic": True},
                   declaration_sha256="0" * 64)
    assert transaction_declaration_hash(changed) == CAPTURE_HASH
    changed["input_bundle_sha256"] = "d" * 64
    assert transaction_declaration_hash(changed) != CAPTURE_HASH
    changed = copy.deepcopy(document)
    changed["unknown_material"] = {"must_not_be_dropped": True}
    assert transaction_declaration_hash(changed) == _seal(changed)["declaration_sha256"] != CAPTURE_HASH
    with pytest.raises(ContractError):
        validate_transaction(changed)


@pytest.mark.parametrize("change", ["new", "old", "read", "receipt_lf", "head_lf", "extra", "bytes_subclass"])
def test_byte_snapshots_do_not_coerce_or_ignore_maps(change):
    document, supplied, originals, reads = _publication(sequence=2)
    if change == "new":
        supplied[document["writes"][0]["path"]] = b"wrong"
    elif change == "old":
        originals[HEAD_PATH] = b"wrong"
    elif change == "read":
        reads[next(iter(reads))] = None
    elif change == "receipt_lf":
        supplied[document["head"]["receipt_path"]] += b"\n"
    elif change == "head_lf":
        supplied[HEAD_PATH] += b"\n"
    elif change == "extra":
        originals["legacy/extra"] = None
    else:
        class BytesSubclass(bytes):
            pass
        supplied[HEAD_PATH] = BytesSubclass(supplied[HEAD_PATH])
    with pytest.raises(ContractError) as caught:
        verify_transaction_bytes(document, write_bytes=supplied, original_bytes=originals, read_bytes=reads)
    assert caught.value.code == "TRANSACTION_BYTES_MISMATCH"


def test_two_full_size_writes_fit_but_three_exceed_total_without_allocating_payloads():
    document = _capture()
    first = document["writes"][0]
    first["size_bytes"] = 67108864
    second = copy.deepcopy(first)
    second.update(path=f'.raw/captured/{"f" * 64}.bin', sha256="f" * 64)
    document["writes"].append(second)
    document["expected_hashes"][second["path"]] = None
    validate_transaction(_seal(document))
    third = copy.deepcopy(first)
    third.update(path=f'.raw/captured/{"0" * 64}.bin', sha256="0" * 64)
    document["writes"].insert(0, third)
    document["expected_hashes"][third["path"]] = None
    with pytest.raises(ContractError) as caught:
        validate_transaction(_seal(document))
    assert caught.value.code == "TRANSACTION_LIMIT_EXCEEDED"


def test_warm_registry_pure_api_never_opens_supplied_paths_or_executes(monkeypatch):
    document, supplied, originals, reads = _publication(sequence=2)
    validate_transaction(document)
    validate_operation_head(document["head"])
    plan = _plan(document)

    def forbidden(*args, **kwargs):
        raise AssertionError("pure transaction helper attempted I/O")

    with monkeypatch.context() as guard:
        for owner, name in [(builtins, "open"), (io, "open"), (os, "open"), (os, "listdir"),
                            (os, "scandir"), (socket, "socket"), (socket, "create_connection"),
                            (subprocess, "Popen")]:
            guard.setattr(owner, name, forbidden)
        inspected = attach_upstream_inspection(document, plan)
        complete = attach_runtime_result(inspected, _result(plan))
        verify_transaction_bytes(complete, write_bytes=supplied, original_bytes=originals, read_bytes=reads)


@pytest.mark.parametrize("path", [
    "sequence", "operation_id", "sha256", "before_sha256", "after_sha256",
    "input_bundle_sha256", "expanded_bundle_sha256", "approval_sha256",
    "declaration_sha256", "receipt_sha256", "schema", "phase", "mode",
    "size_bytes", "original_size_bytes", "original_mode", "device", "inode",
    "hashes", "modes", "changed_paths", "valid", "status", "writes", "receipt",
    "head", "claimed_inputs", "inspection", "runtime_result",
])
@pytest.mark.parametrize("present", [False, True])
def test_dynamic_read_path_named_like_a_schema_field_is_still_a_path(path, present):
    document = _capture()
    document["read_preconditions"] = {path: EMPTY_SHA if present else None}
    _seal(document)
    captured = document["writes"][0]["path"]
    verify_transaction_bytes(document, write_bytes={captured: b""},
                             original_bytes={captured: None},
                             read_bytes={path: b"" if present else None})


@pytest.mark.parametrize("extension", ["sha256", "before_sha256", "input_bundle_sha256"])
def test_dynamic_upstream_mode_key_ending_sha256_contains_an_integer(extension):
    document = _capture()
    path = f".raw/captured/{EMPTY_SHA}.{extension}"
    document["writes"][0]["path"] = path
    document["expected_hashes"] = {path: None}
    _seal(document)
    plan = _plan(document)
    assert plan["modes"][path] == 384
    inspected = attach_upstream_inspection(document, plan)
    complete = attach_runtime_result(inspected, _result(plan))
    verify_transaction_bytes(complete, write_bytes={path: b""},
                             original_bytes={path: None}, read_bytes={})


@pytest.mark.parametrize("target", ["inspection", "result"])
@pytest.mark.parametrize("bad", [None, [], "not-an-object", 123, {None: "bad-key"},
                                {"extra": object()}, {"extra": float("nan")}])
def test_malformed_supplied_upstream_evidence_never_leaks_python_exceptions(target, bad):
    document = _capture()
    with pytest.raises(ContractError):
        if target == "inspection":
            attach_upstream_inspection(document, bad)
        else:
            attach_runtime_result(attach_upstream_inspection(document, _plan(document)), bad)


@pytest.mark.parametrize("target", ["inspection", "result"])
def test_cyclic_supplied_evidence_is_shape_refusal(target):
    document = _capture()
    cyclic = {"self": None}
    cyclic["self"] = cyclic
    with pytest.raises(ContractError) as caught:
        if target == "inspection":
            attach_upstream_inspection(document, cyclic)
        else:
            attach_runtime_result(attach_upstream_inspection(document, _plan(document)), cyclic)
    assert caught.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("map_name", ["write_bytes", "original_bytes", "read_bytes"])
@pytest.mark.parametrize("bad", [None, [], "not-a-map", {None: b""}, {1: None},
                                {("tuple",): b""}, {"extra": object()}])
def test_malformed_snapshot_maps_never_leak_python_exceptions(map_name, bad):
    document = _capture()
    path = document["writes"][0]["path"]
    maps = {"write_bytes": {path: b""}, "original_bytes": {path: None}, "read_bytes": {}}
    maps[map_name] = bad
    with pytest.raises(ContractError) as caught:
        verify_transaction_bytes(document, **maps)
    assert caught.value.code == "TRANSACTION_BYTES_MISMATCH"


@pytest.mark.parametrize("target", ["inspection", "result"])
def test_deep_unknown_upstream_field_is_typed_refusal_before_copy(target):
    deep = None
    for _ in range(1200):
        deep = [deep]
    document = _capture()
    with pytest.raises(ContractError) as caught:
        if target == "inspection":
            attach_upstream_inspection(document, {"extra": deep})
        else:
            attach_runtime_result(attach_upstream_inspection(document, _plan(document)), {"extra": deep})
    assert caught.value.code == "SCHEMA_INVALID"
