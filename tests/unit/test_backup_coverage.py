from __future__ import annotations

import os
from pathlib import Path

import pytest

from video_paper_wiki.backup_coverage import (
    MAX_BATCHES,
    MAX_CANDIDATES,
    RULES,
    assert_distinct_or_same,
    fixed_excluded,
    scan_research_coverage,
)
from video_paper_wiki.contracts import ContractError


def _chmod(root: Path) -> None:
    for path in root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _batch(root: Path, name: str = "b1") -> Path:
    batch = root / ".work" / name
    batch.mkdir(parents=True)
    _chmod(root)
    return batch


def test_missing_work_is_absent_and_records_fixed_exclusions(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    snap = scan_research_coverage(tmp_path)
    try:
        assert snap.report["batches"] == []
        assert snap.report["coverage"] == []
        assert snap.report["files"] == []
        assert fixed_excluded() == [row for row in snap.report["excluded"] if row in fixed_excluded()]
    finally:
        snap.close()


def test_each_rule_has_an_included_or_absent_row(tmp_path: Path) -> None:
    batch = _batch(tmp_path)
    (batch / "draft").mkdir()
    (batch / "draft" / "paper-analysis-draft.v1.json").write_bytes(b"draft")
    (batch / "draft" / "paper-analysis-draft.v1.json").chmod(0o600)
    (batch / "review").mkdir()
    (batch / "plan").mkdir()
    _chmod(tmp_path)
    snap = scan_research_coverage(tmp_path)
    try:
        rows = {(row["rule_id"], row["state"], row["file_count"]) for row in snap.report["coverage"]}
        assert ("draft", "included", 1) in rows
        assert ("review", "included", 0) in rows
        assert ("plan", "included", 0) in rows
        for rule in RULES:
            if rule in {"draft", "review", "plan"}:
                continue
            assert (rule, "absent", 0) in rows
        assert [row["path"] for row in snap.report["files"]] == [".work/b1/draft/paper-analysis-draft.v1.json"]
    finally:
        snap.close()


def test_out_of_scope_and_rebuildable_are_not_archived(tmp_path: Path) -> None:
    batch = _batch(tmp_path)
    (tmp_path / ".work" / "blobs").mkdir()
    (tmp_path / ".work" / "blobs" / "secret").write_bytes(b"secret")
    (batch / "source-catalog").mkdir()
    (batch / "source-catalog" / "cache.json").write_bytes(b"cache")
    _chmod(tmp_path)
    snap = scan_research_coverage(tmp_path)
    try:
        paths = [row["path"] for row in snap.report["files"]]
        assert paths == []
        discovered = {(row["path"], row["reason"]) for row in snap.report["excluded"]}
        assert (".work/blobs", "out_of_scope") in discovered
        assert (".work/b1/source-catalog", "rebuildable") in discovered
    finally:
        snap.close()


def test_unknown_name_inside_a_rule_is_rejected(tmp_path: Path) -> None:
    batch = _batch(tmp_path)
    (batch / "draft").mkdir()
    (batch / "draft" / "notes.txt").write_bytes(b"no")
    _chmod(tmp_path)
    with pytest.raises(ContractError) as caught:
        scan_research_coverage(tmp_path)
    assert caught.value.code == "BACKUP_COVERAGE_INVALID"
    assert "notes.txt" in str(caught.value.details)


def test_empty_id_directory_is_rejected(tmp_path: Path) -> None:
    batch = _batch(tmp_path)
    (batch / "domain" / "annotations" / ("dln-" + "ab" * 10)).mkdir(parents=True)
    _chmod(tmp_path)
    with pytest.raises(ContractError) as caught:
        scan_research_coverage(tmp_path)
    assert caught.value.code == "BACKUP_COVERAGE_INVALID"


def test_symlink_and_hardlink_are_rejected(tmp_path: Path) -> None:
    batch = _batch(tmp_path)
    target = batch / "draft"
    target.mkdir()
    file = target / "paper-analysis-draft.v1.json"
    file.write_bytes(b"draft")
    file.chmod(0o600)
    linked = tmp_path / ".work" / "b1" / "review"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(ContractError) as caught:
        scan_research_coverage(tmp_path)
    assert caught.value.code == "BACKUP_COVERAGE_INVALID"
    linked.unlink()
    (batch / "review").mkdir()
    os.link(file, batch / "review" / "paper.md")
    with pytest.raises(ContractError) as caught:
        scan_research_coverage(tmp_path)
    assert caught.value.code == "BACKUP_COVERAGE_INVALID"


def test_batch_and_candidate_limits_fail_closed(tmp_path: Path) -> None:
    work = tmp_path / ".work"
    work.mkdir()
    for index in range(MAX_BATCHES + 1):
        (work / f"b{index}").mkdir()
    tmp_path.chmod(0o700)
    with pytest.raises(ContractError) as caught:
        scan_research_coverage(tmp_path)
    assert caught.value.code == "BACKUP_COVERAGE_INVALID"
    for index in range(MAX_BATCHES + 1):
        (work / f"b{index}").rmdir()
    for index in range(MAX_CANDIDATES + 1):
        (work / f".extra-{index}").mkdir()
    with pytest.raises(ContractError) as caught:
        scan_research_coverage(tmp_path)
    assert caught.value.code == "BACKUP_COVERAGE_INVALID"


def test_nested_roots_are_rejected_and_same_inode_is_allowed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    vault.mkdir()
    checkout.mkdir()
    nested = checkout / "vault"
    nested.mkdir()
    with pytest.raises(ContractError) as caught:
        assert_distinct_or_same(nested, checkout)
    assert "overlap" in caught.value.message
    same = assert_distinct_or_same(vault, vault)
    assert same[0] == same[1]
