"""Unit tests for the private CODE evidence I/O session."""

from __future__ import annotations

import errno
import os
import stat
import traceback
import unicodedata
from pathlib import Path

import pytest

import video_paper_wiki.code_proof_io as cpio
import video_paper_wiki.code_proof_resources as resources_mod
from video_paper_wiki.code_git_objects import (
    CODE_PROOF_INPUT_INVALID,
    CODE_PROOF_OBJECT_EXTRA,
    CODE_PROOF_OBJECT_UNAVAILABLE,
    CodeGitProofError,
)
from video_paper_wiki.code_proof_io import CodeProofIOError, open_code_session
from video_paper_wiki.code_proof_resources import (
    CodeProofStructureError,
    compile_code_proof_resources,
    resource_origin_plan,
)


class _EvilStr(str):
    def __eq__(self, other):
        raise AssertionError("eq")

    def __hash__(self):
        raise AssertionError("hash")

    def __fspath__(self):
        raise AssertionError("fspath")

    def encode(self, *args, **kwargs):
        raise AssertionError("encode")

    def __len__(self):
        raise AssertionError("len")

    def __str__(self):
        raise AssertionError("str")


class _EvilBytes(bytes):
    def __len__(self):
        raise AssertionError("len")

    def __iter__(self):
        raise AssertionError("iter")

    def hex(self, *args, **kwargs):
        raise AssertionError("hex")

    def __eq__(self, other):
        raise AssertionError("eq")


class _EvilDict(dict):
    def keys(self):
        raise AssertionError("keys")

    def __getitem__(self, key):
        raise AssertionError("getitem")

    def __len__(self):
        raise AssertionError("len")


def _live_plan():
    return resource_origin_plan()


def _copy_origin(tmp_path, *, layout):
    plan = _live_plan()
    live_pkg = Path(plan.package_directory)
    live_mod = Path(resources_mod.__file__)
    schemas_rel = os.path.relpath(str(plan.schemas_directory), str(live_pkg))
    profiles_rel = os.path.relpath(str(plan.profiles_directory), str(live_pkg))
    if layout == "source":
        pkg = tmp_path / "src" / "video_paper_wiki"
    else:
        pkg = tmp_path / "site-packages" / "video_paper_wiki"
    pkg.mkdir(parents=True, exist_ok=True)
    dest_mod = pkg / live_mod.name
    dest_mod.write_bytes(live_mod.read_bytes())
    dest_schemas = Path(os.path.normpath(str(pkg / schemas_rel)))
    dest_profiles = Path(os.path.normpath(str(pkg / profiles_rel)))
    dest_schemas.mkdir(parents=True, exist_ok=True)
    dest_profiles.mkdir(parents=True, exist_ok=True)
    resources = {}
    for pin in plan.resources:
        rel = pin.relative_path.replace("\\", "/")
        filename = rel.split("/")[-1]
        if rel.startswith("schemas/"):
            src = Path(plan.schemas_directory) / filename
            dst = dest_schemas / filename
        else:
            src = Path(plan.profiles_directory) / filename
            dst = dest_profiles / filename
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        os.chmod(dst, stat.S_IMODE(src.stat().st_mode))
        resources[rel] = dst
    return dest_mod, resources


def _write_pyproject(path):
    path.write_bytes(b'[project]\nname = "video-paper-wiki"\n')
    os.chmod(path, 0o644)


def _make_checkout(root):
    root.mkdir(parents=True, exist_ok=True)
    git = root / ".git"
    git.mkdir()
    _write_pyproject(root / "pyproject.toml")
    return root


def _hard_output_limits():
    return {
        "max_request_bytes": 65536,
        "max_intent_bytes": 1048576,
        "max_bundle_bytes": 1048576,
        "max_observation_bytes": 2097152,
        "max_config_document_bytes": 2097152,
        "max_handoff_bytes": 131072,
        "max_output_peak_bytes": 134217728,
    }


def _hard_git_limits():
    return {
        "max_targets": 32,
        "max_objects": 2048,
        "max_tree_entries": 32768,
        "max_object_bytes": 8388608,
        "max_total_object_bytes": 33554432,
    }


def _make_env(tmp_path, monkeypatch, *, layout="source"):
    origin_root = tmp_path / "origin"
    checkout = _make_checkout(tmp_path / "ck")
    dest_mod, resources = _copy_origin(origin_root, layout=layout)
    monkeypatch.setattr(resources_mod, "__file__", str(dest_mod))
    monkeypatch.setattr(cpio, "_getcwd", lambda: str(checkout))
    plan = resource_origin_plan()
    assert plan.layout == layout
    return {
        "checkout": checkout,
        "origin_file": dest_mod,
        "resources": resources,
        "plan": plan,
        "batch": "batch1",
        "layout": layout,
    }


@pytest.fixture
def io_env(tmp_path, monkeypatch):
    return _make_env(tmp_path, monkeypatch, layout="source")


def _chmod_file(path, mode):
    os.chmod(path, mode)


def _write_output_file(checkout, batch, rel, data):
    ns = checkout / ".work" / batch / "code-evidence-v1"
    ns.mkdir(parents=True, exist_ok=True)
    os.chmod(ns, 0o700)
    target = ns / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent != ns:
        os.chmod(target.parent, 0o700)
    target.write_bytes(data)
    os.chmod(target, 0o600)
    return target


def test_error_table_and_independent_copies():
    err = CodeProofIOError(
        "WORK_PATH_UNSAFE",
        {
            "phase": "setup",
            "group": "checkout",
            "reason": "edge_changed",
            "operation": "stat",
            "errno": 2,
            "prior_code": None,
            "prior_operation": None,
            "prior_errno": None,
            "failed_groups": ["checkout"],
        },
    )
    assert err.code == "WORK_PATH_UNSAFE"
    assert err.message == "CODE retained path is unsafe"
    assert err.exit_code == 2
    details = err.details
    details["reason"] = "missing"
    details["failed_groups"].append("resources")
    assert err.details["reason"] == "edge_changed"
    assert err.details["failed_groups"] == ["checkout"]
    assert "ADVERSARY" not in str(err)
    assert "ADVERSARY" not in repr(err)
    limit = CodeProofIOError(
        "CODE_PROOF_LIMIT_EXCEEDED",
        {
            "instance_pointer": "/output",
            "limit_name": "max_output_peak_bytes",
            "limit": 10,
            "observed": 11,
        },
    )
    assert limit.message == "CODE evidence limit exceeded"
    conflict = CodeProofIOError(
        "CODE_PROOF_CONFLICT",
        {"instance_pointer": "/request", "reason": "artifact_changed"},
    )
    assert conflict.message == "CODE evidence artifact conflicts"


def test
