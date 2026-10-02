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
