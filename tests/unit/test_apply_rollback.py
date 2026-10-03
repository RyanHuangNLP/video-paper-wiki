"""Competing apply attempts must preserve the successful writer's store."""

import errno
import json
import os

import pytest

from tests.unit import test_article_apply as article
from tests.unit import test_domain_apply as domain
from tests.unit import test_experiment_apply as experiment
from tests.unit.test_domain_proposal import _snapshot, make_world, valid_proposal


@pytest.fixture(params=["domain", "experiment", "article"])
def apply_case(request, tmp_path, monkeypatch):
    world = make_world(tmp_path, monkeypatch)
    family = request.param
    if family == "domain":
        domain._record(world, valid_proposal(world), name="genesis.json", batch="genesis")
        module, apply, compile = domain.domain_apply, domain._apply, domain._compile
        status = domain.status_domain_store
    elif family == "experiment":
        experiment._record_exp(world, batch="genesis")
        module, apply, compile = experiment.experiment_apply_mod, experiment._apply_exp, experiment._compile
        status = article.status_experiment_store
    else:
        article._stage_complete(world, batch="genesis")
        module, apply, compile = article.article_apply_mod, article._apply_art, article._compile
        status = article.status_article_store
    compile(world, "genesis")
    return world, module, lambda **kw: apply(world, "genesis", **kw), status


def test_failed_genesis_preserves_other_writer_head(apply_case, monkeypatch):
    world, module, apply, status = apply_case
    winner = {}
    def competing_writer(phase):
        if phase == "before-create":
            # Model a writer outside our advisory-lock protocol.
            with monkeypatch.context() as patch:
                patch.setattr(module, "flock", lambda *args: None, raising=False)
                assert apply()["applied"] is True
            winner.update(_snapshot(world["vault"]))
    with pytest.raises(Exception) as exc:
        apply(_fault=competing_writer)
    assert exc.value.code.endswith(("APPLY_VAULT_INVALID", "APPLY_WRITE_FAILED"))
    assert winner
    assert _snapshot(world["vault"]) == winner
    status(vault_root=str(world["vault"]))


def test_apply_serializes_competing_genesis(apply_case):
    world, module, apply, status = apply_case
    attempts = []
    def competing_writer(phase):
        if phase == "before-create":
            before = _snapshot(world["vault"])
            with pytest.raises(Exception) as exc:
                apply()
            assert exc.value.code.endswith("APPLY_CHANGED")
            assert exc.value.details["reason"] == "busy"
            assert _snapshot(world["vault"]) == before
            attempts.append(True)
    assert apply(_fault=competing_writer)["applied"] is True
    assert attempts == [True]
    status(vault_root=str(world["vault"]))


def test_rollback_preserves_replaced_created_file(apply_case):
    world, module, apply, status = apply_case
    replaced = []
    def replace_created(phase):
        if phase == "before-commit":
            root = world["vault"] / module.HEADS_PATH.rsplit("/", 1)[0]
            path = next(p for p in root.rglob("*.json") if p.name != "heads.json")
            sibling = path.with_suffix(".replacement")
            sibling.write_bytes(b"foreign writer bytes\n")
            os.chmod(sibling, 0o600)
            sibling.replace(path)
            replaced.append(path)
            raise OSError(errno.EIO, "injected failure")
    with pytest.raises(Exception) as exc:
        apply(_fault=replace_created)
    assert exc.value.code.endswith("APPLY_WRITE_FAILED")
    assert exc.value.details["rollback_complete"] is False
    assert replaced[0].read_bytes() == b"foreign writer bytes\n"


@pytest.mark.parametrize("fail_at", [1, 2], ids=["parent-dup", "file-dup"])
@pytest.mark.parametrize("replace_created", [False, True], ids=["owned", "replaced"])
def test_dup_failure_cleans_only_owned_file_and_closes_fds(apply_case, monkeypatch, fail_at, replace_created):
    world, module, apply, status = apply_case
    assert apply()["applied"] is True
    winner = _snapshot(world["vault"])
    store = world["vault"] / module.HEADS_PATH.rsplit("/", 1)[0]
    lineage = next(path.parent for path in store.rglob("*.json") if path.name != "heads.json")
    created = lineage / "failed-attempt.json"
    relative = str(created.relative_to(world["vault"]))
    replacement = world["vault"].parent / "replacement.json"
    replacement.write_bytes(b"another writer's file\n")
    os.chmod(replacement, 0o600)
    root_fd = os.open(world["vault"], module.dir_open_flags())
    parent_fd = os.open(lineage, module.dir_open_flags())
    created_files = []
    live_fds = set()
    real_open, real_dup, real_close = os.open, os.dup, os.close
    dup_calls = 0

    def track_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        live_fds.add(fd)
        return fd

    def fail_dup(fd):
        nonlocal dup_calls
        dup_calls += 1
        if dup_calls == fail_at:
            assert created.read_bytes() == b""
            if replace_created:
                replacement.replace(created)
            raise OSError(errno.EMFILE, "injected dup failure")
        owned = real_dup(fd)
        live_fds.add(owned)
        return owned

    def track_close(fd):
        real_close(fd)
        live_fds.discard(fd)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(module.os, "open", track_open)
            patch.setattr(module.os, "dup", fail_dup)
            patch.setattr(module.os, "close", track_close)
            try:
                with pytest.raises(OSError, match="injected dup failure"):
                    module._write_excl(parent_fd, created.name, b"attempt bytes\n", created_files, relative)
                rolled, complete = module._rollback(
                    root_fd, None, created_files, [], heads_mode="create", heads_existed=False,
                )
            finally:
                for _relative, owned_parent, owned_file in reversed(created_files):
                    module.close_fd(owned_file)
                    module.close_fd(owned_parent)
            assert dup_calls == fail_at
            assert not live_fds, f"leaked descriptors: {live_fds}"
        after = _snapshot(world["vault"])
        assert after[module.HEADS_PATH] == winner[module.HEADS_PATH]
        if replace_created:
            assert created.read_bytes() == b"another writer's file\n"
            assert rolled == []
            assert complete is False
            del after[relative]
        else:
            assert not created.exists()
            assert rolled == [relative]
            assert complete is True
        assert after == winner
        if not replace_created:
            status(vault_root=str(world["vault"]))
    finally:
        for fd in live_fds:
            real_close(fd)
        real_close(parent_fd)
        real_close(root_fd)


@pytest.mark.parametrize("fail_at", [1, 2], ids=["parent-dup", "file-dup"])
@pytest.mark.parametrize(
    "cleanup_failure",
    [None, "unlink", "ancestor-open", "leaf-stat"],
    ids=["cleaned", "unlink-denied", "rollback-open-emfile", "rollback-stat-denied"],
)
def test_public_apply_dup_failure_rollback(apply_case, monkeypatch, fail_at, cleanup_failure):
    world, module, apply, _status = apply_case
    before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    live_fds = set()
    real_open, real_dup, real_close = os.open, os.dup, os.close
    real_unlink, real_stat = os.unlink, os.stat
    dup_error = OSError(errno.EMFILE, "injected public apply dup failure")
    unlink_error = OSError(errno.EACCES, "injected cleanup unlink failure")
    armed = False
    dup_calls = 0
    unlink_calls = 0
    probe_failures = 0
    created_fd = None
    relative = None

    def confirm(summary):
        nonlocal relative
        relative = min(path for path in summary["changed_paths"] if path != module.HEADS_PATH)
        assert not (world["vault"] / relative).exists()
        return True

    def arm_failure(phase):
        nonlocal armed
        if phase == "before-create":
            armed = True

    def track_open(name, flags, *args, **kwargs):
        nonlocal created_fd, probe_failures
        if cleanup_failure == "ancestor-open" and unlink_calls and name == "meta":
            # Fail after the first ancestor fd was acquired, exercising its close.
            probe_failures += 1
            raise OSError(errno.EMFILE, "injected rollback ancestor open failure")
        fd = real_open(name, flags, *args, **kwargs)
        live_fds.add(fd)
        if armed and flags & os.O_EXCL:
            assert name == relative.rsplit("/", 1)[1]
            created_fd = fd
        return fd

    def fail_dup(fd):
        nonlocal dup_calls
        if armed:
            dup_calls += 1
            if dup_calls == fail_at:
                assert created_fd is not None
                assert os.fstat(created_fd).st_size == 0
                raise dup_error
        owned = real_dup(fd)
        live_fds.add(owned)
        return owned

    def track_close(fd):
        real_close(fd)
        live_fds.discard(fd)

    def fail_unlink(name, *args, **kwargs):
        nonlocal unlink_calls
        if armed and name == relative.rsplit("/", 1)[1]:
            unlink_calls += 1
            if cleanup_failure is not None:
                raise unlink_error
        return real_unlink(name, *args, **kwargs)

    def fail_stat(name, *args, **kwargs):
        nonlocal probe_failures
        if (cleanup_failure == "leaf-stat" and unlink_calls
                and name == relative.rsplit("/", 1)[1]):
            probe_failures += 1
            raise OSError(errno.EACCES, "injected rollback leaf stat failure")
        return real_stat(name, *args, **kwargs)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "open", track_open)
            patch.setattr(os, "dup", fail_dup)
            patch.setattr(os, "close", track_close)
            patch.setattr(os, "unlink", fail_unlink)
            patch.setattr(os, "stat", fail_stat)
            with pytest.raises((domain.DomainApplyError, experiment.ExperimentApplyError, article.ArticleApplyError)) as exc:
                apply(confirm=confirm, _fault=arm_failure)
        assert armed
        assert dup_calls == fail_at
        assert unlink_calls == 1
        assert not live_fds, f"leaked descriptors: {live_fds}"
        family = module.__name__.rsplit(".", 1)[1].removesuffix("_apply").upper()
        assert exc.value.code == family + "_APPLY_WRITE_FAILED"
        assert exc.value.details["phase"] == "write"
        after = _snapshot(world["vault"])
        if cleanup_failure is None:
            assert not (world["vault"] / relative).exists()
            assert relative in exc.value.details["rolled_back"]
            assert exc.value.details["rollback_complete"] is True
        else:
            assert after.pop(relative)[0] == b""
            assert exc.value.details["rollback_complete"] is False
            assert relative not in exc.value.details["rolled_back"]
        assert after == before
        assert _snapshot(world["checkout"] / ".work") == work_before
        if cleanup_failure in {"ancestor-open", "leaf-stat"}:
            assert probe_failures > 0
        else:
            assert probe_failures == 0
        assert exc.value.details["errno"] == errno.EMFILE
        assert exc.value.__context__ is dup_error
        if cleanup_failure is not None:
            assert dup_error.__cause__ is unlink_error
    finally:
        for fd in live_fds:
            real_close(fd)
