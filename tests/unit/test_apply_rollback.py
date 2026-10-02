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
