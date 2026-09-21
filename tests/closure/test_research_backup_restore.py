from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from video_paper_wiki.backup_archive import create_backup_archive, restore_backup_archive
from video_paper_wiki.catalog_store import build_current_catalog
from video_paper_wiki.cli import main
from video_paper_wiki.code_proof_public import status_code_proof
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.restore_verification import verify_restored_research
from video_paper_wiki.staging import resolve_checkout_root

from tests.closure._p3_recovery_fixture import prepare_research_sources

ROOT = Path(__file__).resolve().parents[2]
DRILL_LOG = Path("/tmp/p3-r1-drill.json")


def _git(restore: Path, *args: str, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "safe.directory=*", *args],
        cwd=restore,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def test_rootless_research_restore_keeps_bytes_and_code_status(tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    prepared = prepare_research_sources(tmp_path, monkeypatch)
    vault = prepared["vault"]
    checkout = prepared["checkout"]
    monkeypatch.chdir(tmp_path)
    assert main(["backup", "manifest", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout)]) == 0
    envelope = json.loads(capsys.readouterr().out)
    manifest = envelope["data"]
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    manifest_path = outside / "manifest.json"
    manifest_path.write_bytes(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode())
    archive = outside / "backup.zip"
    created = create_backup_archive(
        vault_root=vault, checkout_root=checkout, manifest=manifest, destination=archive, profile="research-r1"
    )
    assert created["research_validation"] == "pending"
    archived = {row["path"]: row["sha256"] for row in manifest["files"]}
    combined = {**prepared["vault_files"], **prepared["checkout_files"]}
    wanted = (
        ".raw/",
        "wiki/",
        ".work/d1/code-evidence-v1/",
        ".work/d1/draft/",
        ".work/d1/review/",
        ".work/d1/plan/",
        ".work/b2/draft/",
    )
    for relative, digest in combined.items():
        if any(relative.startswith(prefix) for prefix in wanted):
            assert archived[relative] == digest
    for relative, digest in archived.items():
        assert combined[relative] == digest
        assert not relative.startswith((".git/", ".work/raw/", ".work/blobs/"))
        assert "/source-catalog/" not in relative
    included = {(row["batch_id"], row["rule_id"]): row for row in manifest["coverage"]}
    assert included[("d1", "code-evidence")]["state"] == "included"
    assert included[("d1", "code-evidence")]["file_count"] > 0
    for rule in ("draft", "review", "plan"):
        assert included[("d1", rule)]["state"] == "included"
        assert included[("d1", rule)]["file_count"] == 1
    for rule in ("flow", "domain", "experiments", "articles"):
        assert included[("d1", rule)]["state"] == "absent"
    assert included[("b2", "draft")]["state"] == "included"
    digest = manifest["manifest_sha256"]
    original_vault = vault
    original_checkout = checkout
    original_bundle = prepared["bundle"]
    vault.rename(tmp_path / "gone-vault")
    checkout.rename(tmp_path / "gone-checkout")
    original_bundle.rename(tmp_path / "gone-bundle")
    assert not original_vault.exists()
    assert not original_checkout.exists()
    assert not original_bundle.exists()
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    assert not (restore / ".git").exists()
    restored = restore_backup_archive(
        archive=archive,
        restore_root=restore,
        manifest=manifest,
        profile="research-r1",
        expected_manifest_sha256=digest,
    )
    assert restored["research_validation"] == "pending"
    assert restored["verification"]["valid"] is True
    for row in manifest["files"]:
        target = restore / row["path"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == row["sha256"]
        assert stat.S_IMODE(target.stat().st_mode) == row["mode"]
    assert audit_integrity(restore)["classification"] == "receipt_backed"
    assert not (restore / ".work" / "raw").exists()
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    _git(restore, "init", "-q", env=env)
    _git(restore, "fetch", "-q", str(ROOT), "HEAD", env=env)
    revision = _git(restore, "rev-parse", "FETCH_HEAD", env=env).strip()
    tracked = _git(restore, "ls-tree", "-r", "--name-only", revision, env=env)
    blocked = [
        line
        for line in tracked.splitlines()
        if line in {".raw", "wiki", ".work"} or line.startswith((".raw/", "wiki/", ".work/"))
    ]
    assert blocked == []
    _git(restore, "checkout", "-q", "--detach", revision, env=env)
    monkeypatch.chdir(restore)
    assert os.path.samefile(resolve_checkout_root(), restore)
    after = status_code_proof(batch_id="d1")
    assert after == prepared["code_status"]
    assert after["handoffs"] and after["configs"]
    policy = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.retrieval-policy.v1.json"
    upstream = ROOT / "vendor/claude-obsidian"
    meta = restore / ".vault-meta"
    meta.mkdir(mode=0o700)
    with pytest.raises(ContractError) as caught:
        build_current_catalog(vault_root=restore, upstream_root=upstream, retrieval_config=policy)
    assert caught.value.code == "SOURCE_PROFILE_REQUIRED", caught.value.message
    with pytest.raises(ContractError) as caught:
        verify_restored_research(
            restore_root=restore,
            manifest=manifest,
            expected_manifest_sha256=digest,
            upstream_root=upstream,
            config=policy,
            research_reads=True,
        )
    assert caught.value.code == "RESTORE_VERIFICATION_FAILED"
    DRILL_LOG.write_text(
        json.dumps(
            {
                "manifest_sha256": digest,
                "archive_sha256": created["archive_sha256"],
                "source_anchor": manifest["source_anchor"],
                "vault_manifest_sha256": manifest["vault_manifest_sha256"],
                "receipt_sha256": prepared["receipt_sha256"],
                "batch_ids": manifest["scope"]["batch_ids"],
                "coverage": manifest["coverage"],
                "file_count": len(manifest["files"]),
                "code_state": after["state"],
                "config_count": len(after["configs"]),
                "handoff_count": len(after["handoffs"]),
                "candidate_revision": revision,
                "catalog_code": "SOURCE_PROFILE_REQUIRED",
                "verify_code": "RESTORE_VERIFICATION_FAILED",
                "original_roots_exist": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
