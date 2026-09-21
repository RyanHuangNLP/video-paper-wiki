from __future__ import annotations

import hashlib
import io
import os
import struct
import unicodedata
import zipfile
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


def test_vault_change_during_checkout_scan_is_not_a_stale_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import video_paper_wiki.backup_coverage as coverage

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    real = coverage.scan_research_coverage

    def change_vault(root, *, snapshot=None, entry_base=0, byte_base=0):
        note = vault / "wiki" / "reading-notes" / "note.md"
        note.write_bytes(b"changed-during-checkout-scan")
        return real(root, snapshot=snapshot, entry_base=entry_base, byte_base=byte_base)

    monkeypatch.setattr(coverage, "scan_research_coverage", change_vault)
    with pytest.raises(ContractError) as caught:
        build_research_backup_manifest(vault, checkout)
    assert caught.value.code in {"AUDIT_RACE", "BACKUP_MANIFEST_INVALID"}


def test_vault_change_during_final_checkout_recheck_is_not_a_stale_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import video_paper_wiki.backup_coverage as coverage

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    real = coverage.CoverageSnapshot.verify

    def change_during_recheck(self):
        (vault / "wiki" / "reading-notes" / "note.md").write_bytes(b"changed-during-final-checkout-recheck")
        return real(self)

    monkeypatch.setattr(coverage.CoverageSnapshot, "verify", change_during_recheck)
    with pytest.raises(ContractError) as caught:
        build_research_backup_manifest(vault, checkout)
    assert caught.value.code in {"AUDIT_RACE", "BACKUP_MANIFEST_INVALID"}


def test_vault_change_on_failing_checkout_recheck_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import video_paper_wiki.backup_coverage as coverage

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)

    def fail_during_recheck(self):
        (vault / "wiki" / "reading-notes" / "note.md").write_bytes(b"changed-during-failing-checkout-recheck")
        raise ContractError("BACKUP_COVERAGE_INVALID", "injected checkout recheck failure", {})

    monkeypatch.setattr(coverage.CoverageSnapshot, "verify", fail_during_recheck)
    with pytest.raises(ContractError) as caught:
        build_research_backup_manifest(vault, checkout)
    assert caught.value.code in {"AUDIT_RACE", "BACKUP_MANIFEST_INVALID"}
    assert caught.value.code != "BACKUP_COVERAGE_INVALID"


def test_shared_byte_budget_stops_before_the_checkout_file_is_consumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import video_paper_wiki.backup_manifest as manifest_module

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    vault_bytes = sum(row["size_bytes"] for row in build_backup_manifest(vault)["files"])
    draft = checkout / ".work" / "b1" / "draft" / "paper-analysis-draft.v1.json"
    draft.write_bytes(b"0123456789abcdef")
    draft.chmod(0o600)
    monkeypatch.setattr(manifest_module, "MAX_TOTAL_BYTES", vault_bytes + 8)
    read_bytes = 0
    real_read = os.read

    def counting(file_fd: int, size: int) -> bytes:
        nonlocal read_bytes
        chunk = real_read(file_fd, size)
        try:
            link = os.readlink(f"/proc/self/fd/{file_fd}")
        except OSError:
            link = ""
        if link.endswith("paper-analysis-draft.v1.json"):
            read_bytes += len(chunk)
        return chunk

    monkeypatch.setattr(os, "read", counting)
    with pytest.raises(ContractError) as caught:
        build_research_backup_manifest(vault, checkout)
    assert caught.value.code in {"BACKUP_COVERAGE_INVALID", "BACKUP_MANIFEST_INVALID"}
    assert read_bytes <= 9
    assert read_bytes < 16


def test_shared_entry_budget_stops_before_sorting_checkout_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import video_paper_wiki.backup_coverage as coverage
    import video_paper_wiki.backup_manifest as manifest_module

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    vault_entries = len(build_backup_manifest(vault)["directories"]) + len(build_backup_manifest(vault)["files"])
    monkeypatch.setattr(manifest_module, "MAX_ENTRIES", vault_entries + 4)
    objects = checkout / ".work" / "b1" / "code-evidence-v1" / "objects"
    objects.mkdir(parents=True)
    for index in range(40):
        target = objects / f"{index:040x}.body"
        target.write_bytes(b"x")
        target.chmod(0o600)
    seen: list[int] = []
    real_sort = coverage._sort_names

    def spy(names: list[str]) -> tuple[str, ...]:
        seen.append(len(names))
        return real_sort(names)

    monkeypatch.setattr(coverage, "_sort_names", spy)
    with pytest.raises(ContractError) as caught:
        build_research_backup_manifest(vault, checkout)
    assert caught.value.code in {"BACKUP_COVERAGE_INVALID", "BACKUP_MANIFEST_INVALID"}
    assert 40 not in seen
    assert all(size <= 4 for size in seen)


def test_vault_change_on_checkout_failure_is_rechecked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import video_paper_wiki.backup_coverage as coverage

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)

    def fail_after_change(root, *, snapshot=None, entry_base=0, byte_base=0):
        note = vault / "wiki" / "reading-notes" / "note.md"
        note.write_bytes(b"changed-before-checkout-failure")
        raise ContractError("BACKUP_COVERAGE_INVALID", "injected checkout failure", {})

    monkeypatch.setattr(coverage, "scan_research_coverage", fail_after_change)
    with pytest.raises(ContractError) as caught:
        build_research_backup_manifest(vault, checkout)
    assert caught.value.code in {"AUDIT_RACE", "BACKUP_MANIFEST_INVALID"}
    assert caught.value.code != "BACKUP_COVERAGE_INVALID"


def test_replaced_restored_file_survives_later_fsync_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    manifest = build_research_backup_manifest(vault, checkout)
    archive = tmp_path / "owned.zip"
    create_backup_archive(
        vault_root=vault, checkout_root=checkout, manifest=manifest, destination=archive, profile="research-r1"
    )
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    real_fsync = os.fsync
    state: dict[str, object] = {"replaced": False, "failed": False, "path": None}

    def fail_after_replace(fd: int) -> None:
        files = [path for path in restore.rglob("*") if path.is_file()]
        if files and not state["replaced"]:
            target = files[0]
            replacement = target.with_name(target.name + ".foreign")
            replacement.write_bytes(b"foreign-bytes")
            os.replace(replacement, target)
            state["replaced"] = True
            state["path"] = target
            return real_fsync(fd)
        if state["replaced"] and not state["failed"]:
            state["failed"] = True
            raise OSError(5, "injected fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_after_replace)
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(
            archive=archive,
            restore_root=restore,
            manifest=manifest,
            profile="research-r1",
            expected_manifest_sha256=manifest["manifest_sha256"],
        )
    assert caught.value.code == "RESTORE_VERIFICATION_FAILED"
    kept = state["path"]
    assert isinstance(kept, Path)
    assert kept.read_bytes() == b"foreign-bytes"


def _classic_zip(entries: list[tuple[str, bytes, int, bool]]) -> bytes:
    from video_paper_wiki.backup_archive import _row

    locals_data: list[bytes] = []
    centrals: list[bytes] = []
    offset = 0
    for name, data, mode, is_dir in entries:
        local, central = _row(name, data, mode, is_dir)
        central = central[:42] + struct.pack("<I", offset) + central[46:]
        locals_data.append(local)
        centrals.append(central)
        offset += len(local)
    body = b"".join(locals_data)
    directory = b"".join(centrals)
    eocd = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(entries), len(entries), len(directory), len(body), 0)
    return body + directory + eocd


def _reject_archive(tmp_path: Path, raw: bytes, manifest: dict) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    archive = tmp_path / "forged.zip"
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


def test_v2_forged_members_and_zip_metadata_are_rejected(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    manifest = build_research_backup_manifest(vault, checkout)
    archive = tmp_path / "good.zip"
    create_backup_archive(
        vault_root=vault, checkout_root=checkout, manifest=manifest, destination=archive, profile="research-r1"
    )
    original = archive.read_bytes()
    note = b"wiki/reading-notes/note.md"
    assert original.count(note) >= 2
    _reject_archive(tmp_path / "traversal", original.replace(note, b"../i/reading-notes/note.md"), manifest)
    _reject_archive(tmp_path / "absolute", original.replace(note, b"/iki/reading-notes/note.md"), manifest)
    decomposed = "cafe\u0301.txt"
    assert unicodedata.normalize("NFC", decomposed) != decomposed
    _reject_archive(
        tmp_path / "nfc",
        _classic_zip([("VPWIKI-BACKUP-MANIFEST.json", b"{}", 0o600, False), (decomposed, b"x", 0o600, False)]),
        manifest,
    )
    _reject_archive(
        tmp_path / "casefold",
        _classic_zip(
            [
                ("VPWIKI-BACKUP-MANIFEST.json", b"{}", 0o600, False),
                ("wiki/a", b"a", 0o600, False),
                ("Wiki/a", b"b", 0o600, False),
            ]
        ),
        manifest,
    )
    _reject_archive(
        tmp_path / "duplicate",
        _classic_zip(
            [
                ("VPWIKI-BACKUP-MANIFEST.json", b"{}", 0o600, False),
                ("wiki/a", b"a", 0o600, False),
                ("wiki/a", b"b", 0o600, False),
            ]
        ),
        manifest,
    )
    _reject_archive(
        tmp_path / "missing-meta",
        _classic_zip([("wiki/a", b"a", 0o600, False)]),
        manifest,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("../evil", b"x")
        package.writestr("/tmp/abs", b"y")
        package.writestr("extra.txt", b"z")
    _reject_archive(tmp_path / "zip-metadata", buffer.getvalue(), manifest)


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
