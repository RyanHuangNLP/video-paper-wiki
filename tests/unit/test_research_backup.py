from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from video_paper_wiki.backup_archive import create_backup_archive, restore_backup_archive
from video_paper_wiki.backup_manifest import build_backup_manifest, build_research_backup_manifest
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize


def _put(root: Path, relative: str, data: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _seal(root: Path) -> None:
    for path in root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _vault(root: Path) -> None:
    raw = b"closure-pdf"
    raw_sha = hashlib.sha256(raw).hexdigest()
    raw_path = f".raw/captured/{raw_sha}.pdf"
    page = b"closure-page"
    page_path = "wiki/papers/closure.md"
    receipt = {
        "schema": "video-paper-wiki.operation-receipt.v1",
        "sequence": 1,
        "previous": None,
        "operation_id": "closure-genesis",
        "operation_type": "generic",
        "intent_sha256": "0" * 64,
        "writes": [{"path": page_path, "mode": "create", "before_sha256": None, "after_sha256": hashlib.sha256(page).hexdigest()}],
        "claimed_inputs": [{"path": raw_path, "mode": "read", "sha256": raw_sha}],
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
    for path, data in (
        (raw_path, raw),
        (page_path, page),
        (receipt_path, receipt_raw),
        ("wiki/meta/registries/operation-head.json", canonicalize(head)),
        ("wiki/reading-notes/note.md", b"note"),
    ):
        _put(root, path, data)
    _seal(root)


def _checkout(root: Path) -> None:
    root.mkdir(mode=0o700)
    draft = root / ".work" / "b1" / "draft"
    draft.mkdir(parents=True)
    (draft / "paper-analysis-draft.v1.json").write_bytes(b'{"draft":1}')
    (root / ".work" / "blobs").mkdir()
    (root / ".work" / "blobs" / "secret").write_bytes(b"secret")
    (root / ".work" / "b1" / "source-catalog").mkdir()
    (root / ".work" / "b1" / "source-catalog" / "cache.json").write_bytes(b"cache")
    _seal(root)


def test_research_archive_restores_without_original_roots(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    manifest = build_research_backup_manifest(vault, checkout)
    assert manifest["schema"] == "video-paper-wiki.backup-manifest.v2"
    assert manifest["scope"]["complete_project"] is False
    assert manifest["scope"]["batch_ids"] == ["b1"]
    assert manifest["vault_manifest_sha256"] == build_backup_manifest(vault)["manifest_sha256"]
    paths = [row["path"] for row in manifest["files"]]
    assert ".work/b1/draft/paper-analysis-draft.v1.json" in paths
    assert "wiki/reading-notes/note.md" in paths
    assert not any(path.startswith(".work/blobs") or "source-catalog" in path for path in paths)
    archive = tmp_path / "outside" / "backup.zip"
    archive.parent.mkdir()
    created = create_backup_archive(
        vault_root=vault, checkout_root=checkout, manifest=manifest, destination=archive, profile="research-r1"
    )
    assert created["research_validation"] == "pending"
    assert created["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    digest = manifest["manifest_sha256"]
    vault.rename(tmp_path / "gone-vault")
    checkout.rename(tmp_path / "gone-checkout")
    assert not vault.exists() and not checkout.exists()
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    restored = restore_backup_archive(
        archive=archive,
        restore_root=restore,
        manifest=manifest,
        profile="research-r1",
        expected_manifest_sha256=digest,
    )
    assert restored["research_validation"] == "pending"
    assert (restore / ".work" / "b1" / "draft" / "paper-analysis-draft.v1.json").read_bytes() == b'{"draft":1}'
    assert (restore / "wiki" / "reading-notes" / "note.md").read_bytes() == b"note"
    assert not (restore / ".work" / "blobs").exists()
    assert not (restore / ".work" / "b1" / "source-catalog").exists()


def test_same_root_does_not_duplicate_work(tmp_path: Path) -> None:
    root = tmp_path / "both"
    _vault(root)
    draft = root / ".work" / "b1" / "draft"
    draft.mkdir(parents=True)
    (draft / "paper-analysis-draft.v1.json").write_bytes(b"same")
    _seal(root)
    manifest = build_research_backup_manifest(root, root)
    work = [row["path"] for row in manifest["files"] if row["path"].startswith(".work/")]
    assert work == [".work/b1/draft/paper-analysis-draft.v1.json"]
    archive = tmp_path / "same.zip"
    create_backup_archive(vault_root=root, checkout_root=root, manifest=manifest, destination=archive, profile="research-r1")


def test_nested_roots_and_bad_anchor_are_rejected(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    _checkout(checkout)
    nested = checkout / "vault"
    _vault(nested)
    with pytest.raises(ContractError) as caught:
        build_research_backup_manifest(nested, checkout)
    assert caught.value.code == "BACKUP_COVERAGE_INVALID"
    vault = tmp_path / "vault"
    _vault(vault)
    manifest = build_research_backup_manifest(vault, checkout)
    archive = tmp_path / "bad.zip"
    create_backup_archive(vault_root=vault, checkout_root=checkout, manifest=manifest, destination=archive, profile="research-r1")
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(
            archive=archive,
            restore_root=restore,
            manifest=manifest,
            profile="research-r1",
            expected_manifest_sha256="ab" * 32,
        )
    assert caught.value.code == "BACKUP_MANIFEST_INVALID"
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(
            archive=archive,
            restore_root=restore,
            manifest=manifest,
            profile="vault-v1",
            expected_manifest_sha256=manifest["manifest_sha256"],
        )
    assert caught.value.code == "BACKUP_MANIFEST_INVALID"
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(archive=archive, restore_root=restore, manifest=manifest, profile="research-r1", source_root=vault)
    assert caught.value.code == "RESTORE_VERIFICATION_FAILED"
    assert list(restore.iterdir()) == []


def test_damaged_archive_and_unsafe_restore_root_do_not_succeed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    manifest = build_research_backup_manifest(vault, checkout)
    archive = tmp_path / "damage.zip"
    create_backup_archive(vault_root=vault, checkout_root=checkout, manifest=manifest, destination=archive, profile="research-r1")
    raw = bytearray(archive.read_bytes())
    raw[-8] ^= 0xFF
    archive.write_bytes(raw)
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(
            archive=archive,
            restore_root=restore,
            manifest=manifest,
            profile="research-r1",
            expected_manifest_sha256=manifest["manifest_sha256"],
        )
    assert caught.value.code == "BACKUP_ARCHIVE_INVALID"
    assert list(restore.iterdir()) == []
    archive.write_bytes(bytes(raw))
    # The damaged bytes stay rejected; a nonempty or unlocked root is a separate refusal.
    fresh = tmp_path / "fresh.zip"
    create_backup_archive(vault_root=vault, checkout_root=checkout, manifest=manifest, destination=fresh, profile="research-r1")
    (restore / "occupied").write_bytes(b"x")
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(
            archive=fresh,
            restore_root=restore,
            manifest=manifest,
            profile="research-r1",
            expected_manifest_sha256=manifest["manifest_sha256"],
        )
    assert caught.value.code == "RESTORE_ROOT_UNSAFE"
    occupied = restore / "occupied"
    assert occupied.read_bytes() == b"x"


def test_vault_profile_still_rejects_a_missing_source_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _vault(vault)
    manifest = build_backup_manifest(vault)
    archive = tmp_path / "v1.zip"
    create_backup_archive(vault_root=vault, manifest=manifest, destination=archive)
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(archive=archive, restore_root=restore, manifest=manifest)
    assert caught.value.code == "RESTORE_VERIFICATION_FAILED"
