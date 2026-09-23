from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from video_paper_wiki.cli import main
from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize

from .paths import INVALID, VALID, load_json


def _vault(root: Path) -> None:
    raw = b"closure-pdf"
    page = b"closure-page"
    raw_path = f".raw/captured/{hashlib.sha256(raw).hexdigest()}.pdf"
    page_path = "wiki/papers/closure.md"
    receipt = {
        "schema": "video-paper-wiki.operation-receipt.v1",
        "sequence": 1,
        "previous": None,
        "operation_id": "closure-genesis",
        "operation_type": "generic",
        "intent_sha256": "0" * 64,
        "writes": [{"path": page_path, "mode": "create", "before_sha256": None, "after_sha256": hashlib.sha256(page).hexdigest()}],
        "claimed_inputs": [{"path": raw_path, "mode": "read", "sha256": hashlib.sha256(raw).hexdigest()}],
    }
    receipt["intent_sha256"] = receipt_intent_sha256(receipt)
    receipt_raw = canonicalize(receipt)
    receipt_path = "wiki/meta/operations/000000000001-closure-genesis.json"
    head = {
        "schema": "video-paper-wiki.operation-head.v1",
        "sequence": 1,
        "receipt_path": receipt_path,
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
    }
    root.mkdir(mode=0o700)
    for relative, data in (
        (raw_path, raw),
        (page_path, page),
        (receipt_path, receipt_raw),
        ("wiki/meta/registries/operation-head.json", canonicalize(head)),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for path in root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _checkout(root: Path) -> None:
    target = root / ".work" / "b1" / "draft" / "paper-analysis-draft.v1.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"draft":1}')
    for path in root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def test_v2_fixture_and_invalid_shapes() -> None:
    document = load_json(VALID / "video-paper-wiki.backup-manifest.v2.json")
    validate_document(document, expected_schema="video-paper-wiki.backup-manifest.v2")
    assert document["scope"]["complete_project"] is False
    for name in (
        "video-paper-wiki.backup-manifest.v2.extra-field.json",
        "video-paper-wiki.backup-manifest.v2.missing-exclusion.json",
    ):
        with pytest.raises(ContractError) as caught:
            bad = load_json(INVALID / name)
            validate_document(bad, expected_schema="video-paper-wiki.backup-manifest.v2")
        assert caught.value.code == "SCHEMA_INVALID"


def test_apply_results_stay_not_wired() -> None:
    for title in (
        "video-paper-wiki.domain-publication-apply-result.v1",
        "video-paper-wiki.experiment-publication-apply-result.v1",
        "video-paper-wiki.article-publication-apply-result.v1",
        "video-paper-wiki.reading-publication-apply-result.v1",
    ):
        schema = schema_by_title(title)
        assert schema["properties"]["publication"]["const"] == "unpublished"
        assert schema["properties"]["receipt_backed"]["const"] is False
        assert schema["properties"]["audit_coverage"]["const"] == "not_wired"
        assert schema["properties"]["backup_coverage"]["const"] == "not_wired"


def test_default_manifest_stays_vault_v1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault = tmp_path / "vault"
    _vault(vault)
    assert main(["backup", "manifest", "--vault-root", str(vault)]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["ok"] is True
    assert envelope["data"]["schema"] == "video-paper-wiki.backup-manifest.v1"
    assert "coverage" not in envelope["data"]


def test_research_manifest_envelope_data_is_the_operator_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    assert main(["backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "USAGE"
    assert main(["backup", "manifest", "--vault-root", str(vault), "--checkout-root", str(checkout)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "USAGE"
    assert main(["backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout)]) == 0
    envelope = json.loads(capsys.readouterr().out)
    document = envelope["data"]
    assert set(envelope) == {"ok", "command", "data"}
    assert document["schema"] == "video-paper-wiki.backup-manifest.v2"
    assert document["scope"]["batch_ids"] == ["b1"]
    validate_document(document, expected_schema=document["schema"])


def test_research_cli_rejects_a_checkout_file_past_the_shared_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import video_paper_wiki.backup_manifest as manifest_module
    from video_paper_wiki.backup_manifest import build_backup_manifest

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    vault_bytes = sum(row["size_bytes"] for row in build_backup_manifest(vault)["files"])
    draft = checkout / ".work" / "b1" / "draft" / "paper-analysis-draft.v1.json"
    draft.write_bytes(b"0123456789abcdef")
    draft.chmod(0o600)
    monkeypatch.setattr(manifest_module, "MAX_TOTAL_BYTES", vault_bytes + 8)
    assert main(["backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] in {"BACKUP_COVERAGE_INVALID", "BACKUP_MANIFEST_INVALID"}


def test_research_cli_rejects_before_reading_past_the_shared_entry_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import os

    import video_paper_wiki.backup_manifest as manifest_module
    from video_paper_wiki.backup_manifest import build_backup_manifest

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    vault_entries = len(build_backup_manifest(vault)["directories"]) + len(build_backup_manifest(vault)["files"])
    evidence = checkout / ".work" / "b1" / "code-evidence-v1"
    body = evidence / "objects" / f"{0:040x}.body"
    body.parent.mkdir(parents=True)
    body.write_bytes(b"x")
    request = evidence / "request.json"
    request.write_bytes(b"q" * 65536)
    for path in checkout.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    monkeypatch.setattr(manifest_module, "MAX_ENTRIES", vault_entries + 5)
    read_bytes = 0
    real_read = os.read

    def counting(file_fd: int, size: int) -> bytes:
        nonlocal read_bytes
        chunk = real_read(file_fd, size)
        try:
            link = os.readlink(f"/proc/self/fd/{file_fd}")
        except OSError:
            link = ""
        if link.endswith("request.json"):
            read_bytes += len(chunk)
        return chunk

    monkeypatch.setattr(os, "read", counting)
    assert main(["backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] in {"BACKUP_COVERAGE_INVALID", "BACKUP_MANIFEST_INVALID"}
    assert read_bytes == 0


def test_research_cli_rejects_a_fifo_in_a_whitelist_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import os

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    fifo = checkout / ".work" / "b1" / "draft" / "extra.fifo"
    os.mkfifo(fifo)
    assert main(["backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BACKUP_COVERAGE_INVALID"


def test_research_verify_requires_independent_hash_and_rejects_source_root(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "verify", "--profile", "research-r1", "--restore-root", "/r", "--manifest", "/m", "--upstream-root", "/u", "--config", "/c"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "USAGE"
    assert main(["backup", "verify", "--profile", "research-r1", "--restore-root", "/r", "--source-root", "/v", "--expected-manifest-sha256", "ab" * 32, "--manifest", "/m", "--upstream-root", "/u", "--config", "/c"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "USAGE"
    assert main(["backup", "verify", "--restore-root", "/r", "--manifest", "/m", "--upstream-root", "/u", "--config", "/c"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "USAGE"
    assert main(["backup", "verify", "--restore-root", "/r", "--source-root", "/v", "--expected-manifest-sha256", "ab" * 32, "--manifest", "/m", "--upstream-root", "/u", "--config", "/c"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "USAGE"
