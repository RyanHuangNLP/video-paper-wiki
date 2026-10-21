"""Steward acceptance of frozen capture-contracts-v1 revision 2.

Expected digests were calculated independently with hashlib and ASCII-key,
integer-only sorted JSON, not with the production hash or text helpers. These
tests prove pure declarations/bytes only, never filesystem or upstream authority.
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

from video_paper_wiki.capture_contracts import (
    capture_approval_hash,
    validate_capture_inspection,
)
from video_paper_wiki.code_evidence_contracts import (
    code_manifest_hash,
    code_proposal_hash,
    code_snippet_sha256,
    code_text_metadata,
    normalize_code_bytes,
    validate_code_capture_binding,
    validate_code_evidence_manifest,
    validate_code_locator,
)
from video_paper_wiki.contracts import ContractError, validate_document

EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
A_SHA = "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"
RAW_SHA = "87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7"
PROPOSAL_SHA = "8f497138ddcdbbaaf2a4ea357ca52a490b37d890bc6e63d1fd4ca1dcd0194662"
APPROVAL_SHA = "25967b20d190cf27571c6e0a448b43b2c7c48dcd70ac940473aa1564cb660422"
MANIFEST_SHA = "7e9e2a057aaaff0e5e418cb9cfbf1606fd19b690edc12fa4384f30da856c8ae6"


def _digest(value: dict) -> str:
    # Our fixture keys are ASCII and values are integers, bools, strings or null;
    # this constrained independent serialization has the same JCS wire bytes.
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _proposal() -> dict:
    return {
        "schema": "video-paper-wiki.code-evidence-manifest.v1",
        "state": "proposal",
        "origin": {"repository": "Owner/Repo", "commit": "a" * 40, "path": "src/A.py"},
        "payload": {"sha256": RAW_SHA, "size_bytes": 2},
        "media_type": "text/plain", "encoding": "utf-8",
        "line_canonicalization": "utf8-lf-v1", "newline_style": "lf",
        "ends_with_newline": True, "line_count": 1,
        "normalized_sha256": RAW_SHA, "proposal_sha256": PROPOSAL_SHA,
    }


def _chain(proposal: dict | None = None) -> tuple[dict, dict]:
    proposal = copy.deepcopy(_proposal() if proposal is None else proposal)
    sha = proposal["payload"]["sha256"]
    inspection = {
        "schema": "video-paper-wiki.capture-inspection.v1", "route": "staged-capture",
        "media_type": "text/plain", "payload": copy.deepcopy(proposal["payload"]),
        "source_path": None, "proposal_sha256": proposal["proposal_sha256"],
        "stored_path": f".raw/captured/{sha}.bin", "source_identity": sha,
        "siblings": [], "would_change": True, "operation_id": "capture-001",
        "upstream_plan_sha256": "b" * 64,
    }
    inspection["approval_hash"] = _digest(inspection)
    manifest = dict(proposal, state="inspected", capture={
        "stored_path": inspection["stored_path"], "source_identity": sha,
        "source_id": "src:declared-001", "inspection_approval_hash": inspection["approval_hash"],
        "operation_id": inspection["operation_id"],
    })
    manifest["manifest_sha256"] = _digest(manifest)
    return inspection, manifest


def _reseal(document: dict, field: str) -> None:
    document[field] = _digest({key: value for key, value in document.items() if key != field})


def _locator() -> dict:
    return {"kind": "code", "source_id": "src:declared-001", "repository": "owner/repo",
            "commit": "a" * 40, "path": "src/A.py", "lines": {"start": 1, "end": 1},
            "snippet_sha256": A_SHA}


def test_independent_golden_hash_graph_and_unmutated_inputs() -> None:
    proposal = _proposal()
    inspection, manifest = _chain()
    original = copy.deepcopy((proposal, inspection, manifest))
    assert code_proposal_hash(proposal) == PROPOSAL_SHA
    assert code_proposal_hash(manifest) == PROPOSAL_SHA
    assert capture_approval_hash(inspection) == APPROVAL_SHA
    assert code_manifest_hash(manifest) == MANIFEST_SHA
    assert validate_code_evidence_manifest(proposal, payload=b"a\n") is proposal
    assert validate_capture_inspection(inspection, payload=b"a\n") is inspection
    assert validate_code_evidence_manifest(manifest, payload=b"a\n") is manifest
    assert validate_code_capture_binding(manifest, inspection) is None
    validate_code_locator(_locator(), manifest, b"a\n")
    assert (proposal, inspection, manifest) == original


@pytest.mark.parametrize("raw,normalized,style,count,digest", [
    (b"", b"", "none", 0, EMPTY_SHA),
    (b"\n", b"\n", "lf", 1, "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"),
    (b"a\n\n", b"a\n\n", "lf", 2, "a7da489976d0047490617adb4f7a1f27f7af8b52a5176fd002ffe471863520ab"),
    (b"A\r\nB\n", b"A\nB\n", "mixed", 2, "daee1cd25194ae952d046ad9b9c81d3c07dc5332440b58d6d7461b248be56712"),
    ("Ａ\t \r\nβ\n".encode(), "Ａ\t \nβ\n".encode(), "mixed", 2,
     "7c1359cd97aa6c10b9e1484d051a23d2fc73b8c7074b564ad76ad81bdad9c4b1"),
])
def test_independent_text_vectors(raw, normalized, style, count, digest) -> None:
    assert normalize_code_bytes(raw) == normalized
    assert code_text_metadata(raw) == {"newline_style": style, "ends_with_newline": raw.endswith(b"\n"),
                                      "line_count": count, "normalized_sha256": digest}


def test_snippets_keep_logical_empty_lines_and_literal_unicode() -> None:
    assert code_snippet_sha256(b"a", 1, 1) == code_snippet_sha256(b"a\n", 1, 1) == A_SHA
    assert code_snippet_sha256(b"a\n\n", 1, 2) == RAW_SHA
    assert code_snippet_sha256(b"\n", 1, 1) == EMPTY_SHA
    assert code_snippet_sha256("Ａ\t \r\nβ\n".encode(), 1, 2) == (
        "c3c3813c0133d12faf9907b1c627b940dbfbc30ec61904300831ab4e769f6dda")
    assert normalize_code_bytes("x\ufeff".encode()) == "x\ufeff".encode()
    with pytest.raises(ContractError) as exc:
        code_snippet_sha256(b"", 1, 1)
    assert exc.value.code == "CODE_LINE_RANGE_INVALID"


@pytest.mark.parametrize("field", ["repository", "commit", "path"])
def test_newline_in_logical_origin_cannot_exploit_dollar_anchor(field) -> None:
    proposal = _proposal()
    proposal["origin"][field] += "\n"
    _reseal(proposal, "proposal_sha256")
    with pytest.raises(ContractError) as exc:
        validate_document(proposal)
    assert exc.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("container,field", [
    ("payload", "sha256"), (None, "source_identity"), (None, "operation_id"),
    (None, "stored_path"), (None, "proposal_sha256"), (None, "upstream_plan_sha256"),
])
def test_newline_in_inspection_fields_is_shape_error_before_hash(container, field) -> None:
    inspection, _ = _chain()
    target = inspection if container is None else inspection[container]
    target[field] += "\n"
    _reseal(inspection, "approval_hash")
    with pytest.raises(ContractError) as exc:
        validate_capture_inspection(inspection)
    assert exc.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("field,value", [("line_count", 1.0), ("line_count", True), ("size_bytes", 2.0)])
def test_python_integer_boundary_precedes_self_hash(field, value) -> None:
    proposal = _proposal()
    (proposal["payload"] if field == "size_bytes" else proposal)[field] = value
    with pytest.raises(ContractError) as exc:
        validate_document(proposal)
    assert exc.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("value", [1.0, True, 0])
def test_locator_and_direct_snippet_have_distinct_range_error_contract(value) -> None:
    _, manifest = _chain()
    locator = _locator()
    locator["lines"]["start"] = value
    with pytest.raises(ContractError) as exc:
        validate_code_locator(locator, manifest, b"a\n")
    assert exc.value.code == "SCHEMA_INVALID"
    with pytest.raises(ContractError) as exc:
        code_snippet_sha256(b"a\n", value, 1)
    assert exc.value.code == "CODE_LINE_RANGE_INVALID"


@pytest.mark.parametrize("field", ["repository", "commit", "path", "source_id", "snippet_sha256"])
def test_locator_rejects_trailing_newline_in_every_identity_string(field) -> None:
    _, manifest = _chain()
    locator = _locator()
    locator[field] += "\n"
    with pytest.raises(ContractError) as exc:
        validate_code_locator(locator, manifest, b"a\n")
    assert exc.value.code == "SCHEMA_INVALID"


def test_reuse_mode_float_is_rejected_before_old_approval_hash() -> None:
    inspection, _ = _chain()
    inspection.update(would_change=False, operation_id=None, upstream_plan_sha256=None,
                      siblings=[{"path": inspection["stored_path"], "kind": "regular",
                                 "sha256": RAW_SHA, "mode": 420.0}])
    with pytest.raises(ContractError) as exc:
        validate_capture_inspection(inspection)
    assert exc.value.code == "SCHEMA_INVALID"


def test_empty_manifest_is_valid_but_cannot_supply_a_locator() -> None:
    proposal = _proposal()
    proposal.update(payload={"sha256": EMPTY_SHA, "size_bytes": 0},
                    normalized_sha256=EMPTY_SHA, line_count=0,
                    newline_style="none", ends_with_newline=False)
    _reseal(proposal, "proposal_sha256")
    inspection, manifest = _chain(proposal)
    validate_code_capture_binding(manifest, inspection)
    validate_code_evidence_manifest(manifest, payload=b"")
    locator = _locator()
    locator["snippet_sha256"] = EMPTY_SHA
    with pytest.raises(ContractError) as exc:
        validate_code_locator(locator, manifest, b"")
    assert exc.value.code == "CODE_LINE_RANGE_INVALID"


def test_two_origins_share_raw_identity_without_erasing_locator_identity() -> None:
    first_inspection, first = _chain()
    second_proposal = _proposal()
    second_proposal["origin"] = {"repository": "Other/Repo", "commit": "c" * 40, "path": "src/B.py"}
    _reseal(second_proposal, "proposal_sha256")
    second_inspection, second = _chain(second_proposal)
    validate_code_capture_binding(first, first_inspection)
    validate_code_capture_binding(second, second_inspection)
    assert first["capture"]["source_id"] == second["capture"]["source_id"]
    assert first["capture"]["stored_path"] == second["capture"]["stored_path"]
    assert first["proposal_sha256"] != second["proposal_sha256"]
    locator = _locator()
    validate_code_locator(locator, first, b"a\n")
    with pytest.raises(ContractError) as exc:
        validate_code_locator(locator, second, b"a\n")
    assert exc.value.code == "CODE_LOCATOR_MISMATCH"
    locator.update(second_proposal["origin"])
    validate_code_locator(locator, second, b"a\n")


@pytest.mark.parametrize("field,replacement", [
    ("schema", "different-schema"), ("route", "manual-inbox"), ("media_type", "application/pdf"),
    ("payload", {"sha256": RAW_SHA, "size_bytes": 3}), ("source_path", "inbox/a.pdf"),
    ("proposal_sha256", "c" * 64), ("stored_path", f".raw/captured/{RAW_SHA}.legacy"),
    ("source_identity", "c" * 64), ("siblings", [{"path": f".raw/captured/{RAW_SHA}.bin",
     "kind": "regular", "sha256": RAW_SHA, "mode": 420}]), ("would_change", False),
    ("operation_id", "capture-002"), ("upstream_plan_sha256", "c" * 64),
])
def test_approval_hash_binds_every_nonself_field_even_for_unattested_candidates(field, replacement) -> None:
    inspection, _ = _chain()
    inspection[field] = replacement
    expected = _digest({key: value for key, value in inspection.items() if key != "approval_hash"})
    assert expected != APPROVAL_SHA
    assert capture_approval_hash(inspection) == expected


def test_inspected_source_declaration_cannot_be_changed_without_manifest_rehash() -> None:
    _, manifest = _chain()
    manifest["capture"]["source_id"] = "src:different"
    with pytest.raises(ContractError) as exc:
        validate_code_evidence_manifest(manifest)
    assert exc.value.code == "CODE_MANIFEST_MISMATCH"
    # A new declaration remains representable, but is not upstream verification.
    _reseal(manifest, "manifest_sha256")
    validate_code_evidence_manifest(manifest)


def test_text_inspection_checks_utf8_even_without_manifest() -> None:
    inspection, _ = _chain()
    raw = b"\xff\xfe"
    sha = hashlib.sha256(raw).hexdigest()
    inspection["payload"]["sha256"] = sha
    inspection["source_identity"] = sha
    inspection["stored_path"] = f".raw/captured/{sha}.bin"
    _reseal(inspection, "approval_hash")
    validate_capture_inspection(inspection)  # Declared bytes alone prove no text policy.
    with pytest.raises(ContractError) as exc:
        validate_capture_inspection(inspection, payload=raw)
    assert exc.value.code == "CODE_TEXT_INVALID"


def test_warm_registry_validation_does_not_open_files_network_or_subprocesses(monkeypatch) -> None:
    inspection, manifest = _chain()
    validate_document(inspection)
    validate_document(manifest)  # Schema resource loading is initialization, not Vault I/O.

    def forbidden(*args, **kwargs):
        raise AssertionError("pure capture validation attempted I/O")

    with monkeypatch.context() as guard:
        for owner, name in [(builtins, "open"), (io, "open"), (os, "open"),
                            (socket, "socket"), (socket, "create_connection"), (subprocess, "Popen")]:
            guard.setattr(owner, name, forbidden)
        validate_capture_inspection(inspection, payload=b"a\n")
        validate_code_evidence_manifest(manifest, payload=b"a\n")
        validate_code_capture_binding(manifest, inspection)
        validate_code_locator(_locator(), manifest, b"a\n")
