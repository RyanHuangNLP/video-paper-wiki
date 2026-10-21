from __future__ import annotations

import copy
import hashlib

import pytest

from video_paper_wiki.capture_contracts import (
    CAPTURE_SCHEMA, capture_approval_hash, validate_capture_inspection,
)
from video_paper_wiki.code_evidence_contracts import (
    CODE_SCHEMA, code_manifest_hash, code_proposal_hash, code_snippet_sha256,
    code_text_metadata, validate_code_capture_binding, validate_code_evidence_manifest,
    validate_code_locator,
)
from video_paper_wiki.contracts import ContractError, validate_document

from .paths import FIXTURES, VALID, load_json


def proposal(raw=b"a\r\nb\n"):
    doc = {
        "schema": CODE_SCHEMA, "state": "proposal",
        "origin": {"repository": "Owner/Repo", "commit": "a" * 40, "path": "src/model.py"},
        "payload": {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)},
        "media_type": "text/plain", "encoding": "utf-8", "line_canonicalization": "utf8-lf-v1",
        **code_text_metadata(raw),
    }
    doc["proposal_sha256"] = code_proposal_hash(doc)
    return doc


def inspection(raw=b"%PDF-fixture", *, code=False, reuse=False, manual=False, proposal_hash=None):
    digest = hashlib.sha256(raw).hexdigest()
    target = f".raw/captured/{digest}." + ("legacy" if reuse else "bin" if code else "pdf")
    doc = {
        "schema": CAPTURE_SCHEMA, "route": "manual-inbox" if manual else "staged-capture",
        "media_type": "text/plain" if code else "application/pdf",
        "payload": {"sha256": digest, "size_bytes": len(raw)},
        "source_path": "inbox/paper.pdf" if manual else None,
        "proposal_sha256": (proposal_hash or proposal(raw)["proposal_sha256"]) if code else None,
        "stored_path": target, "source_identity": digest,
        "siblings": [{"path": target, "kind": "regular", "sha256": digest, "mode": 420}] if reuse else [],
        "would_change": not reuse, "operation_id": None if reuse else "capture-fixture-1",
        "upstream_plan_sha256": None if reuse else "b" * 64,
    }
    doc["approval_hash"] = capture_approval_hash(doc)
    return doc


def inspected(raw=b"a\r\nb\n", *, reuse=False):
    doc = proposal(raw)
    observed = inspection(raw, code=True, reuse=reuse, proposal_hash=doc["proposal_sha256"])
    doc["state"] = "inspected"
    doc["capture"] = {
        "stored_path": observed["stored_path"], "source_identity": observed["source_identity"],
        "source_id": "src-declared-1", "inspection_approval_hash": observed["approval_hash"],
        "operation_id": observed["operation_id"],
    }
    doc["manifest_sha256"] = code_manifest_hash(doc)
    return doc, observed


def assert_error(code, function, *args, **kwargs):
    with pytest.raises(ContractError) as result:
        function(*args, **kwargs)
    assert result.value.code == code
    assert result.value.exit_code == 2
    assert "instance_pointer" in result.value.details


def set_path(doc, path, value):
    parts = path.split("/")
    node = doc
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    node[int(parts[-1]) if isinstance(node, list) else parts[-1]] = value


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("manual", [False, True])
def test_pdf_routes_create_reuse_preserve_original(reuse, manual):
    doc = inspection(reuse=reuse, manual=manual)
    before = copy.deepcopy(doc)
    assert validate_capture_inspection(doc, payload=b"%PDF-fixture") is doc
    assert validate_document(doc) is doc
    assert doc == before


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("raw", [b"", b"a\r\nb\n", "全角Ａ\tZ\n".encode()])
def test_code_states_binding_and_bytes(reuse, raw):
    doc, observed = inspected(raw, reuse=reuse)
    before = copy.deepcopy((doc, observed))
    assert validate_code_evidence_manifest(doc, payload=raw) is doc
    assert validate_capture_inspection(observed, payload=raw) is observed
    validate_code_capture_binding(doc, observed)
    assert (doc, observed) == before
    initial = proposal(raw)
    assert code_proposal_hash(doc) == initial["proposal_sha256"]
    assert validate_code_evidence_manifest(initial, payload=raw) is initial


@pytest.mark.parametrize("path,value", [
    ("route", "manual-inbox"), ("source_path", "inbox/source.pdf"),
    ("proposal_sha256", "c" * 64), ("source_identity", "c" * 64),
    ("would_change", False), ("operation_id", None), ("upstream_plan_sha256", None),
])
def test_capture_cross_field_refusals(path, value):
    doc = inspection()
    set_path(doc, path, value)
    doc["approval_hash"] = capture_approval_hash(doc)
    assert_error("CAPTURE_BINDING_MISMATCH", validate_capture_inspection, doc)


@pytest.mark.parametrize("path,value", [
    ("siblings/0/kind", "symlink"), ("siblings/0/kind", "special"),
    ("siblings/0/sha256", None), ("siblings/0/sha256", "c" * 64),
])
def test_snapshot_refuses_nonmatching_or_nonregular(path, value):
    doc = inspection(reuse=True)
    set_path(doc, path, value)
    doc["approval_hash"] = capture_approval_hash(doc)
    assert_error("CAPTURE_SNAPSHOT_INVALID", validate_capture_inspection, doc)


@pytest.mark.parametrize("variant", ["duplicate", "sorted", "unsorted", "selection", "path-digest"])
def test_snapshot_count_selection_digest(variant):
    doc = inspection(reuse=True)
    if variant in {"duplicate", "sorted", "unsorted"}:
        sibling = copy.deepcopy(doc["siblings"][0])
        if variant != "duplicate":
            sibling["path"] += "z"
        doc["siblings"].append(sibling)
        if variant == "unsorted":
            doc["siblings"].reverse()
    elif variant == "selection":
        doc["siblings"][0]["path"] += "z"
    else:
        doc["siblings"][0]["path"] = f".raw/captured/{'c' * 64}.legacy"
    doc["approval_hash"] = capture_approval_hash(doc)
    assert_error("CAPTURE_SNAPSHOT_INVALID", validate_capture_inspection, doc)


@pytest.mark.parametrize("path,value", [
    ("source_path", "inbox/a.PDF"), ("source_path", "inbox/../a.pdf"),
    ("stored_path", "/tmp/a.pdf"), ("stored_path", ".raw/captured/nested/a.pdf"),
    ("operation_id", "capture/one"), ("payload/size_bytes", 12.0),
    ("payload/size_bytes", True), ("siblings/0/mode", 420.0),
    ("siblings/0/mode", 4096), ("siblings/0/mode", True),
])
def test_capture_shape_and_exact_integer_refusals(path, value):
    doc = inspection(reuse=True, manual=True)
    set_path(doc, path, value)
    assert_error("SCHEMA_INVALID", validate_capture_inspection, doc)


@pytest.mark.parametrize("path", [
    "source_path", "stored_path", "source_identity", "payload/sha256", "approval_hash",
    "siblings/0/path", "siblings/0/sha256",
])
def test_capture_trailing_newline_refusals(path):
    doc = inspection(reuse=True, manual=True)
    node = doc
    for part in path.split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    set_path(doc, path, node + "\n")
    assert_error("SCHEMA_INVALID", validate_capture_inspection, doc)


@pytest.mark.parametrize("path", ["", "payload", "siblings/0"])
def test_capture_nested_unknown_fields(path):
    doc = inspection(reuse=True)
    if path:
        set_path(doc, path + "/unexpected", 1)
    else:
        doc["unexpected"] = 1
    assert_error("SCHEMA_INVALID", validate_capture_inspection, doc)


@pytest.mark.parametrize("path", ["", "origin", "payload", "capture"])
def test_manifest_nested_unknown_fields(path):
    doc, _ = inspected()
    if path:
        doc[path]["unexpected"] = 1
    else:
        doc["unexpected"] = 1
    assert_error("SCHEMA_INVALID", validate_code_evidence_manifest, doc)


@pytest.mark.parametrize("field", ["capture", "manifest_sha256"])
def test_manifest_state_field_presence(field):
    doc = proposal()
    doc[field] = None
    assert_error("SCHEMA_INVALID", validate_code_evidence_manifest, doc)
    doc, _ = inspected()
    del doc[field]
    assert_error("SCHEMA_INVALID", validate_code_evidence_manifest, doc)


@pytest.mark.parametrize("path", [
    "origin/repository", "origin/commit", "origin/path", "payload/sha256",
    "normalized_sha256", "proposal_sha256", "manifest_sha256", "capture/stored_path",
    "capture/source_identity", "capture/source_id", "capture/inspection_approval_hash", "capture/operation_id",
])
def test_manifest_fullmatch_refusals(path):
    doc, _ = inspected()
    node = doc
    for part in path.split("/"):
        node = node[part]
    set_path(doc, path, node + "\n")
    assert_error("SCHEMA_INVALID", validate_code_evidence_manifest, doc)


@pytest.mark.parametrize("path,value", [
    ("line_count", 2.0), ("line_count", True), ("payload/size_bytes", 5.0),
    ("origin/path", "src/.hidden"), ("origin/path", "src/../x"),
    ("origin/path", "src/路径.py"), ("origin/commit", "main"),
])
def test_manifest_type_path_refusals(path, value):
    doc = proposal()
    set_path(doc, path, value)
    assert_error("SCHEMA_INVALID", validate_code_evidence_manifest, doc)


@pytest.mark.parametrize("raw,path,value", [
    (b"", "line_count", 1), (b"", "newline_style", "lf"),
    (b"", "ends_with_newline", True), (b"", "payload/sha256", "a" * 64),
    (b"", "normalized_sha256", "a" * 64), (b"a", "line_count", 0),
    (b"a", "line_count", 2), (b"a", "ends_with_newline", True),
    (b"ab", "line_count", 2),
])
def test_object_metadata_consistency(raw, path, value):
    doc = proposal(raw)
    set_path(doc, path, value)
    doc["proposal_sha256"] = code_proposal_hash(doc)
    assert_error("CODE_MANIFEST_MISMATCH", validate_code_evidence_manifest, doc)


@pytest.mark.parametrize("field,value", [
    ("newline_style", "lf"), ("ends_with_newline", False),
    ("line_count", 1), ("normalized_sha256", "a" * 64),
])
def test_all_byte_derived_metadata_is_checked(field, value):
    doc = proposal()
    doc[field] = value
    doc["proposal_sha256"] = code_proposal_hash(doc)
    validate_code_evidence_manifest(doc)
    assert_error("CODE_MANIFEST_MISMATCH", validate_code_evidence_manifest, doc, payload=b"a\r\nb\n")


def test_stale_hashes_and_payloads():
    doc = inspection()
    doc["upstream_plan_sha256"] = "c" * 64
    assert_error("CAPTURE_APPROVAL_MISMATCH", validate_capture_inspection, doc)
    doc = proposal()
    doc["origin"]["path"] = "other.py"
    assert_error("CODE_MANIFEST_MISMATCH", validate_code_evidence_manifest, doc)
    doc, _ = inspected()
    doc["capture"]["source_id"] = "src-other"
    assert_error("CODE_MANIFEST_MISMATCH", validate_code_evidence_manifest, doc)
    assert_error("PAYLOAD_MISMATCH", validate_capture_inspection, inspection(), payload=b"%PDF-different")
    assert_error("PAYLOAD_MISMATCH", validate_code_evidence_manifest, proposal(), payload=b"wrong")
    fake = inspection(b"not-a-pdf")
    assert_error("PAYLOAD_MISMATCH", validate_capture_inspection, fake, payload=b"not-a-pdf")


def test_code_inspection_checks_utf8_even_without_manifest():
    doc = inspection(b"bad\x00", proposal_hash="a" * 64, code=True)
    assert_error("CODE_TEXT_INVALID", validate_capture_inspection, doc, payload=b"bad\x00")


@pytest.mark.parametrize("path,value", [
    ("origin/path", "other.py"), ("capture/stored_path", None),
    ("capture/inspection_approval_hash", "c" * 64), ("capture/operation_id", "other-op"),
])
def test_rehashed_cross_object_mismatches(path, value):
    doc, observed = inspected()
    if value is None:
        value = doc["capture"]["stored_path"] + "legacy"
    set_path(doc, path, value)
    doc["proposal_sha256"] = code_proposal_hash(doc)
    doc["manifest_sha256"] = code_manifest_hash(doc)
    validate_code_evidence_manifest(doc)
    assert_error("CAPTURE_BINDING_MISMATCH", validate_code_capture_binding, doc, observed)


def test_hash_helpers_exclude_self_and_do_not_validate():
    doc = inspection()
    before = doc.pop("approval_hash")
    assert capture_approval_hash(doc) == before
    doc["schema"] = "not-a-schema"
    assert capture_approval_hash(doc) != before
    for function, document in [(capture_approval_hash, {}), (code_proposal_hash, {}), (code_manifest_hash, {})]:
        assert_error("SCHEMA_INVALID", function, document)
    doc = proposal()
    doc["origin"]["path"] = object()
    assert_error("CANONICAL_JSON_INVALID", code_proposal_hash, doc)


@pytest.mark.parametrize("key", [1, None, ("tuple",)])
@pytest.mark.parametrize("function,factory", [
    (validate_document, proposal), (validate_code_evidence_manifest, proposal),
    (validate_document, inspection), (validate_capture_inspection, inspection),
])
def test_python_object_keys_fail_with_contract_error(key, function, factory):
    doc = factory()
    doc[key] = True
    assert_error("SCHEMA_INVALID", function, doc)


@pytest.mark.parametrize("function,factory", [
    (capture_approval_hash, inspection), (code_proposal_hash, proposal),
    (code_manifest_hash, lambda: inspected()[0]),
])
def test_hash_helpers_refuse_cycles(function, factory):
    doc = factory()
    cyclic = {}
    cyclic["cycle"] = cyclic
    doc["payload"] = cyclic
    assert_error("CANONICAL_JSON_INVALID", function, doc)


@pytest.mark.parametrize("field", [
    "schema", "route", "media_type", "payload", "source_path", "proposal_sha256", "stored_path",
    "source_identity", "siblings", "would_change", "operation_id", "upstream_plan_sha256",
])
def test_every_approval_material_field_is_bound(field):
    doc = inspection(reuse=True, manual=True)
    expected = capture_approval_hash(doc)
    doc[field] = {"changed": True}
    assert capture_approval_hash(doc) != expected


def test_fixture_documents_and_rejections():
    for title in (CAPTURE_SCHEMA, CODE_SCHEMA):
        validate_document(load_json(VALID / f"{title}.json"))
    for name, code in [("invalid-pdf-create-suffix.json", "CAPTURE_BINDING_MISMATCH"),
                       ("invalid-proposal-capture.json", "SCHEMA_INVALID")]:
        assert_error(code, validate_document, load_json(FIXTURES / "capture" / name))


def locator_for(doc, raw=b"a\r\nb\n"):
    return {"kind": "code", **doc["origin"], "source_id": doc["capture"]["source_id"],
            "lines": {"start": 1, "end": 2}, "snippet_sha256": code_snippet_sha256(raw, 1, 2)}


def test_locator_origin_case_symbol_and_input_stability():
    doc, _ = inspected()
    locator = locator_for(doc)
    locator["repository"] = "owner/repo"
    locator["symbol"] = "not-resolved"
    before = copy.deepcopy((locator, doc))
    validate_code_locator(locator, doc, b"a\r\nb\n")
    assert (locator, doc) == before


@pytest.mark.parametrize("field,value,code", [
    ("path", "Src/model.py", "CODE_LOCATOR_MISMATCH"),
    ("commit", "b" * 40, "CODE_LOCATOR_MISMATCH"),
    ("source_id", "src-other", "CODE_LOCATOR_MISMATCH"),
    ("snippet_sha256", "c" * 64, "CODE_LOCATOR_MISMATCH"),
    ("lines", {"start": 0, "end": 1}, "SCHEMA_INVALID"),
    ("lines", {"start": True, "end": 1}, "SCHEMA_INVALID"),
    ("lines", {"start": 1.0, "end": 2}, "SCHEMA_INVALID"),
    ("lines", {"start": 2, "end": 1}, "CODE_LINE_RANGE_INVALID"),
    ("lines", {"start": 1, "end": 3}, "CODE_LINE_RANGE_INVALID"),
])
def test_locator_refusals(field, value, code):
    doc, _ = inspected()
    locator = locator_for(doc)
    locator[field] = value
    assert_error(code, validate_code_locator, locator, doc, b"a\r\nb\n")
