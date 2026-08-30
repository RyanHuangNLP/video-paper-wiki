from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.support import work_draft, work_prepared, work_review
from video_paper_wiki import staging as staging_mod
from video_paper_wiki.staging import (
    CODE_INVALID_BATCH_ID,
    CODE_STAGING_CONFLICT,
    CODE_WORK_PATH_ESCAPE,
    CODE_WORK_PATH_UNSAFE,
    CODE_WORKSPACE_ROOT_INVALID,
    StagingError,
    _assert_inside_work,
    stage_bytes,
    validate_batch_id,
)


def test_validate_batch_id_accepts_legal_values() -> None:
    assert validate_batch_id("a") == "a"
    assert validate_batch_id("A9") == "A9"
    assert validate_batch_id("batch-1_id") == "batch-1_id"
    assert validate_batch_id("x" * 128) == "x" * 128


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 129,
        "/tmp/out",
        "..",
        "../x",
        "a/b",
        "a\\b",
        "-leading",
        "trailing-",
        "under_",
        " space",
        "has space",
    ],
)
def test_validate_batch_id_rejects_illegal_values(value: str) -> None:
    with pytest.raises(StagingError) as exc:
        validate_batch_id(value)
    assert exc.value.code == CODE_INVALID_BATCH_ID


def test_same_bytes_are_idempotent(checkout: Path) -> None:
    first = stage_bytes(batch_id="b1", relative=("draft", "paper-analysis-draft.v1.json"), data=b"abc")
    second = stage_bytes(batch_id="b1", relative=("draft", "paper-analysis-draft.v1.json"), data=b"abc")
    path = work_draft(checkout, "b1")
    assert first.path == path
    assert first.already_staged is False
    assert second.already_staged is True
    assert path.read_bytes() == b"abc"


def test_different_bytes_conflict(checkout: Path) -> None:
    stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"one")
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"two")
    assert exc.value.code == CODE_STAGING_CONFLICT
    assert work_review(checkout, "b1").read_bytes() == b"one"


def test_work_symlink_is_unsafe(checkout: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (checkout / ".work").symlink_to(outside)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("prepared", "aa.blob"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE
    assert list(outside.iterdir()) == []


def test_batch_symlink_is_unsafe(checkout: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    work = checkout / ".work"
    work.mkdir()
    (work / "b1").symlink_to(outside)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("prepared", "aa.blob"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE
    assert list(outside.iterdir()) == []


def test_intermediate_symlink_is_unsafe(checkout: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    prepared = checkout / ".work" / "b1" / "prepared"
    prepared.parent.mkdir(parents=True)
    prepared.symlink_to(outside)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("prepared", "aa.blob"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE
    assert list(outside.iterdir()) == []


def test_target_symlink_is_unsafe(checkout: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "secret.bin"
    sentinel.write_bytes(b"keep")
    target_dir = checkout / ".work" / "b1" / "prepared"
    target_dir.mkdir(parents=True)
    (target_dir / "aa.blob").symlink_to(sentinel)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("prepared", "aa.blob"), data=b"new")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE
    assert sentinel.read_bytes() == b"keep"


def test_fifo_target_is_unsafe(checkout: Path) -> None:
    target = work_prepared(checkout, "b1", "aa")
    target.parent.mkdir(parents=True)
    os.mkfifo(target)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("prepared", "aa.blob"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE


def test_work_as_file_is_unsafe(checkout: Path) -> None:
    (checkout / ".work").write_bytes(b"not-a-dir")
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("draft", "paper-analysis-draft.v1.json"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE


def test_paths_stay_under_same_batch(checkout: Path) -> None:
    blob = stage_bytes(batch_id="shared", relative=("prepared", "ab.blob"), data=b"blob")
    draft = stage_bytes(
        batch_id="shared",
        relative=("draft", "paper-analysis-draft.v1.json"),
        data=b"draft",
    )
    review = stage_bytes(batch_id="shared", relative=("review", "paper.md"), data=b"review")
    assert blob.path == work_prepared(checkout, "shared", "ab")
    assert draft.path == work_draft(checkout, "shared")
    assert review.path == work_review(checkout, "shared")
    work = checkout / ".work" / "shared"
    assert blob.path.is_relative_to(work)
    assert draft.path.is_relative_to(work)
    assert review.path.is_relative_to(work)


def test_missing_checkout_is_invalid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"x")
    assert exc.value.code == CODE_WORKSPACE_ROOT_INVALID


def test_wrong_project_name_is_invalid(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "other"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"x")
    assert exc.value.code == CODE_WORKSPACE_ROOT_INVALID


def test_git_symlink_is_invalid(tmp_path: Path, monkeypatch) -> None:
    real_git = tmp_path / "real-git"
    real_git.mkdir()
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").symlink_to(real_git)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "video-paper-wiki"\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"x")
    assert exc.value.code == CODE_WORKSPACE_ROOT_INVALID


def test_relative_dotdot_is_unsafe(checkout: Path) -> None:
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("..", "paper.md"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE


def test_resolved_path_outside_work_is_escape(checkout: Path) -> None:
    work = checkout / ".work"
    work.mkdir()
    target = work / "b1" / ".." / ".." / "secret.md"
    with pytest.raises(StagingError) as exc:
        _assert_inside_work(target, work)
    assert exc.value.code == CODE_WORK_PATH_ESCAPE
    assert exc.value.code != CODE_WORK_PATH_UNSAFE


def test_batch_as_file_is_unsafe(checkout: Path) -> None:
    work = checkout / ".work"
    work.mkdir()
    (work / "b1").write_bytes(b"not-a-dir")
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE


def test_intermediate_as_file_is_unsafe(checkout: Path) -> None:
    parent = checkout / ".work" / "b1"
    parent.mkdir(parents=True)
    (parent / "review").write_bytes(b"not-a-dir")
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE


def test_intermediate_fifo_is_unsafe(checkout: Path) -> None:
    parent = checkout / ".work" / "b1"
    parent.mkdir(parents=True)
    os.mkfifo(parent / "review")
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"x")
    assert exc.value.code == CODE_WORK_PATH_UNSAFE


def test_project_not_a_table_is_invalid(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text('project = "video-paper-wiki"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(StagingError) as exc:
        stage_bytes(batch_id="b1", relative=("review", "paper.md"), data=b"x")
    assert exc.value.code == CODE_WORKSPACE_ROOT_INVALID


def test_already_staged_when_install_sees_same_bytes(checkout: Path, monkeypatch) -> None:
    first = stage_bytes(
        batch_id="b1",
        relative=("draft", "paper-analysis-draft.v1.json"),
        data=b"abc",
    )
    assert first.already_staged is False
    monkeypatch.setattr(staging_mod, "_existing_same_bytes", lambda *_args, **_kwargs: False)
    second = stage_bytes(
        batch_id="b1",
        relative=("draft", "paper-analysis-draft.v1.json"),
        data=b"abc",
    )
    assert second.already_staged is True
    assert (checkout / ".work" / "b1" / "draft" / "paper-analysis-draft.v1.json").read_bytes() == b"abc"
