from __future__ import annotations

import copy
import json
import os
import stat
from pathlib import Path

import pytest

from tests.markdown_source_fixture import prepared_source
from tests.research.conftest import UPSTREAM
from tests.research.test_source_admission import _apply_bundle, apply_publication, bootstrap_genesis
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.markdown_source import admit_markdown_source, bind_markdown_capture_result, inspect_markdown_capture
from video_paper_wiki.markdown_source_contracts import AUTHORITY, sha, validate
from video_paper_wiki.receipt_audit import audit_integrity


def _snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
            for path in root.rglob("*") if path.is_file()}


def _captured_fixture(checkout, *, bootstrap=True):
    vault = checkout / "fixture-vault"
    if bootstrap:
        bootstrap_genesis(checkout, vault, checkout)
    else:
        from tests.upstream._transaction_fixture import Runner, init
        runner_root = checkout / "runner"
        runner_root.mkdir()
        init(Runner(runner_root), vault, "markdown-pristine-init")
    planned, prepared, payload = prepared_source(checkout)
    before = _snapshot(vault)
    inspected = inspect_markdown_capture(prepared=prepared["request_path"], operation_id="capture-md",
                                         vault_root=vault, upstream_root=UPSTREAM)
    assert before == _snapshot(vault)
    assert inspected["state"] == "awaiting_operator_capture"
    authority = inspected["authority"]
    assert authority["disposition"] == "create"
    bundle = checkout / ".work/md-capture" / authority["transaction_staging"]["bundle_file"]
    actual = _apply_bundle(vault, bundle, authority["upstream_authority"]["transaction"]["inspection"]["approval_sha256"])
    target = authority["stored_path"]
    assert (vault / target).read_bytes() == payload
    before_descriptors = {target: None}
    after_descriptors = {target: {"sha256": sha((vault / target).read_bytes()),
                                  "mode": stat.S_IMODE((vault / target).stat().st_mode)}}
    bound = bind_markdown_capture_result(authority, actual, before=before_descriptors, after=after_descriptors)
    return vault, prepared, authority, bound


def _admit(vault, authority, bound=None, **kwargs):
    options = {"batch_id": "admit-md", "operation_id": "admit-md", "ingested_at": "2026-09-09T00:00:00Z"}
    options.update(kwargs)
    return admit_markdown_source(authority=authority, capture_result=bound, vault_root=vault,
                                 upstream_root=UPSTREAM, **options)


def test_real_generic_capture_and_ingest_chain(checkout):
    vault, prepared, authority, bound = _captured_fixture(checkout)
    before = _snapshot(vault)
    admitted = _admit(vault, authority, bound)
    assert before == _snapshot(vault)
    assert admitted["state"] == "source_registration_prepared"
    assert admitted["published"] is False and admitted["receipt_backed"] is False
    assert admitted["publication_authority"]["transaction"]["operation_id"] == "admit-md"
    assert admitted["publication_authority"]["request"]["batch_id"] == "admit-md"
    apply_publication(checkout, vault, admitted["publication_authority"])
    audit = audit_integrity(vault)
    assert audit["classification"] == "receipt_backed"
    assert authority["stored_path"] in audit["ever_claimed_raw"]
    ledger = json.loads((vault / "wiki/meta/ledgers/source-ledger.json").read_bytes())
    assert ledger["sources"][authority["source_id"]]["origin"] == {"kind": "file", "locator": authority["stored_path"]}
    from video_paper_wiki.catalog_collector import _ledgers, _row_tables
    rows = _row_tables()
    claims = json.loads((vault / "wiki/meta/ledgers/claim-ledger.json").read_bytes())
    _ledgers(rows, ledger, claims)
    assert rows["source_artifacts"] == [{"source_id": authority["source_id"], "artifact_path": authority["stored_path"]}]
    assert rows["sources"][0]["content_kind"] == "document"
    assert not list(vault.rglob("*.pdf")) and not (vault / ".raw/derived").exists()
    before = _snapshot(vault)
    already = _admit(vault, authority, batch_id="admit-again", operation_id="admit-again")
    assert already["state"] == "source_already_registered" and already["receipt_backed"]
    assert not (checkout / ".work/admit-again").exists()
    assert before == _snapshot(vault)


def test_exact_capture_reuse_has_no_child_operation_and_accepts_prior_proof(checkout):
    vault, prepared, authority, bound = _captured_fixture(checkout)
    before = _snapshot(vault)
    reused = inspect_markdown_capture(prepared=prepared["request_path"], operation_id="reuse-label",
                                      vault_root=vault, upstream_root=UPSTREAM)
    assert reused["state"] == "capture_reused"
    value = reused["authority"]
    assert value["disposition"] == "reuse" and value["transaction_staging"] is value["upstream_authority"] is None
    with pytest.raises(ContractError):
        bind_markdown_capture_result(value, bound["result"], before=bound["vault_before"], after=bound["vault_after"])
    admitted = _admit(vault, value, bound)
    assert admitted["state"] == "source_registration_prepared"
    assert before == _snapshot(vault)


def test_captured_orphan_without_actual_result_refuses(checkout):
    vault, _, authority, _ = _captured_fixture(checkout)
    with pytest.raises(ContractError) as err:
        _admit(vault, authority)
    assert err.value.code == "MARKDOWN_AUTHORITY_MISMATCH"
    assert not (checkout / ".work/admit-md").exists()


def test_source_admission_requires_genesis_before_canonical_registration(checkout):
    vault, _, authority, bound = _captured_fixture(checkout, bootstrap=False)
    with pytest.raises(ContractError) as err:
        _admit(vault, authority, bound)
    assert err.value.code == "RECEIPT_BOOTSTRAP_REQUIRED"
    assert not (checkout / ".work/admit-md").exists()


@pytest.mark.parametrize("during_inspection", [False, True])
def test_hardlinked_capture_cannot_produce_reuse_authority(checkout, monkeypatch, during_inspection):
    import video_paper_wiki.markdown_source as module
    vault, prepared, authority, _ = _captured_fixture(checkout)
    target = vault / authority["stored_path"]
    if during_inspection:
        original = module.verify_pinned_source_id

        def add_link(*args, **kwargs):
            value = original(*args, **kwargs)
            os.link(target, checkout / "external-link")
            return value

        monkeypatch.setattr(module, "verify_pinned_source_id", add_link)
    else:
        os.link(target, checkout / "external-link")
    with pytest.raises(ContractError) as err:
        module.inspect_markdown_capture(prepared=prepared["request_path"], operation_id="reuse",
                                         upstream_root=UPSTREAM, vault_root=vault)
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("field,value", [("ingested_at", "2026-02-30T00:00:00Z"),
                                         ("ingested_at", "2026-01-01T25:00:00Z"),
                                         ("batch_id", "md-capture"), ("operation_id", "capture-md")])
def test_admission_validates_date_and_distinct_transaction_identity(checkout, field, value):
    vault, _, authority, bound = _captured_fixture(checkout)
    with pytest.raises(ContractError) as err:
        _admit(vault, authority, bound, **{field: value})
    assert err.value.code in {"MARKDOWN_SOURCE_INVALID", "MARKDOWN_SOURCE_CONFLICT"}


@pytest.mark.parametrize("extension", ["pdf", "bin"])
def test_same_digest_other_extension_cannot_be_reused(checkout, extension):
    vault, prepared, authority, _ = _captured_fixture(checkout)
    (vault / authority["stored_path"]).rename((vault / authority["stored_path"]).with_suffix("." + extension))
    with pytest.raises(ContractError) as err:
        inspect_markdown_capture(prepared=prepared["request_path"], operation_id="reuse",
                                  vault_root=vault, upstream_root=UPSTREAM)
    assert err.value.code == "MARKDOWN_CAPTURE_CONFLICT"


@pytest.mark.parametrize("field", ["mode", "operation", "business"])
def test_result_proof_cannot_change_current_mode_or_capture_transaction(checkout, field):
    vault, _, authority, bound = _captured_fixture(checkout)
    tampered = copy.deepcopy(bound)
    if field == "mode":
        path = vault / authority["stored_path"]
        path.chmod(0o600 if stat.S_IMODE(path.stat().st_mode) != 0o600 else 0o644)
    elif field == "operation":
        tampered["transaction"]["operation_id"] = "other"
    else:
        tampered["transaction"]["writes"][0]["path"] = ".raw/captured/" + "b" * 64 + ".md"
    with pytest.raises(ContractError):
        _admit(vault, authority, tampered)


def test_create_authority_closes_all_transaction_layer_bindings(checkout):
    _, _, authority, _ = _captured_fixture(checkout)
    for keys, replacement in [(("transaction_staging", "operation_id"), "wrong"),
                               (("transaction_staging", "batch_id"), "wrong"),
                               (("transaction_staging", "bundle_sha256"), "b" * 64),
                               (("upstream_authority", "transaction", "read_preconditions"), {"wiki/x.md": None}),
                               (("upstream_authority", "transaction", "writes", 0, "size_bytes"), 1)]:
        bad = copy.deepcopy(authority)
        leaf = bad
        for key in keys[:-1]:
            leaf = leaf[key]
        leaf[keys[-1]] = replacement
        with pytest.raises(ContractError):
            validate(bad, AUTHORITY)
