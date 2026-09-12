#!/usr/bin/env python3
"""Offline adversarial review harness for the CODE Git kernel.

Preparation artifact only. This harness refuses to run until an explicit Builder
handoff JSON with status READY_FOR_STEWARD_REVIEW is supplied. It never runs Git,
never edits the candidate, and writes only the requested review-result path.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import copy
import hashlib
import importlib
import json
import os
import socket
import subprocess
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

FIXTURE_SHA256 = "b8936db0a65d58d533016840e3d7cfbc686f819b240c812207e73638165955f0"
FIXTURE_REL = "artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/kernel-r1/independent-git-fixture-v1.json"
ALLOWED_PATHS = {
    "src/video_paper_wiki/code_git_objects.py",
    "tests/unit/test_code_git_objects.py",
    "tests/fixtures/code-git-objects-v1.json",
}
PROFILE = {
    "max_targets": 32,
    "max_objects": 2048,
    "max_tree_entries": 32768,
    "max_object_bytes": 8388608,
    "max_total_object_bytes": 33554432,
}
ERROR_CODES = {
    "CODE_PROOF_INPUT_INVALID",
    "CODE_PROOF_LIMIT_EXCEEDED",
    "CODE_PROOF_OBJECT_EXTRA",
    "CODE_PROOF_OBJECT_UNAVAILABLE",
    "CODE_PROOF_OBJECT_SIZE_MISMATCH",
    "CODE_PROOF_OBJECT_HASH_MISMATCH",
    "CODE_PROOF_OBJECT_TYPE_MISMATCH",
    "CODE_PROOF_COMMIT_INVALID",
    "CODE_PROOF_TREE_INVALID",
    "CODE_PROOF_CONSUMED_SET_MISMATCH",
}
TOP_LEVEL_KEYS = [
    "object_format", "commit_oid", "root_tree_oid", "object_records",
    "consumed_oids", "budget", "targets",
]


class ReviewFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewFailure(message)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_handoff(candidate_root: Path, handoff_path: Path, fixture_path: Path) -> dict:
    handoff = load_json(handoff_path)
    check(type(handoff) is dict, "handoff must be an exact dict")
    check(handoff.get("status") == "READY_FOR_STEWARD_REVIEW", "exact candidate handoff is required")
    for key in ("source_root", "reviewed_head", "reviewed_tree", "candidate_snapshot_sha256", "allowed_paths", "source_writes_stopped"):
        check(key in handoff, f"handoff missing {key}")
    check(type(handoff["source_root"]) is str, "handoff source_root type")
    check(Path(handoff["source_root"]).resolve() == candidate_root.resolve(), "handoff source_root mismatch")
    check(type(handoff["allowed_paths"]) is list and set(handoff["allowed_paths"]) == ALLOWED_PATHS, "handoff path scope")
    check(handoff["source_writes_stopped"] is True, "Builder source writes must be stopped")
    check(fixture_path.is_file(), "fixture is unavailable")
    check(sha256_file(fixture_path) == FIXTURE_SHA256, "fixture hash drift")
    return handoff


def check_candidate_scope(candidate_root: Path) -> None:
    check(candidate_root.is_dir(), "candidate root is not a directory")
    expected = {candidate_root / p for p in ALLOWED_PATHS}
    check((candidate_root / "src/video_paper_wiki/code_git_objects.py").is_file(), "production candidate missing")
    check((candidate_root / "tests/unit/test_code_git_objects.py").is_file(), "candidate tests missing")
    check((candidate_root / "tests/fixtures/code-git-objects-v1.json").is_file(), "candidate fixture missing")
    actual_changed = set()
    for rel in ALLOWED_PATHS:
        actual_changed.add(candidate_root / rel)
    check(actual_changed == expected, "candidate allowlist mismatch")
    copied_fixture = candidate_root / "tests/fixtures/code-git-objects-v1.json"
    check(sha256_file(copied_fixture) == FIXTURE_SHA256, "Builder fixture is not byte-exact")


def import_candidate(candidate_root: Path) -> types.ModuleType:
    source = candidate_root / "src/video_paper_wiki/code_git_objects.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    prohibited = {"io", "os", "pathlib", "socket", "subprocess", "urllib", "requests", "http", "ftplib", "importlib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            check(all(alias.name.split(".")[0] not in prohibited for alias in node.names), "prohibited import in kernel")
        elif isinstance(node, ast.ImportFrom):
            check((node.module or "").split(".")[0] not in prohibited, "prohibited import in kernel")
    sys.path.insert(0, str(candidate_root / "src"))
    sys.dont_write_bytecode = True
    return importlib.import_module("video_paper_wiki.code_git_objects")


def variant_inputs(variant: dict, case_name: str) -> tuple[list[dict], dict[str, bytes], list[dict], str, str]:
    records = {row["oid"]: row for row in variant["all_objects"]}
    case = variant["cases"][case_name]
    selected = [records[oid] for oid in case["required_object_oids"]]
    objects = [
        {
            "oid": row["oid"],
            "object_type": row["type"],
            "body_size_bytes": row["size"],
            "body_sha256": row["body_sha256"],
            "framed_sha256": row["framed_sha256"],
        }
        for row in selected
    ]
    objects.sort(key=lambda row: row["oid"])
    bodies = {row["oid"]: bytes.fromhex(row["body_hex"]) for row in selected}
    return objects, bodies, copy.deepcopy(case["targets"]), variant["commit_oid"], variant["root_tree_oid"]


def expect_error(api: Callable[..., Any], expected_code: str, **kwargs: Any) -> dict:
    try:
        api(**kwargs)
    except Exception as exc:  # noqa: BLE001 - closed API checked below
        check(type(exc).__name__ == "CodeGitProofError", f"wrong exception type for {expected_code}")
        check(getattr(exc, "code", None) == expected_code, f"wrong code: {getattr(exc, 'code', None)}")
        check(getattr(exc, "exit_code", None) == 2, "wrong exit code")
        details = getattr(exc, "details", None)
        check(type(details) is dict, "error details must be exact dict")
        return {"code": exc.code, "details": copy.deepcopy(details)}
    raise ReviewFailure(f"expected {expected_code}")


def primitive(value: Any) -> None:
    if type(value) in (str, int, bool) or value is None:
        return
    if type(value) is bytes or type(value) is float:
        raise ReviewFailure("success output contains bytes or float")
    if type(value) is list:
        for item in value:
            primitive(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            check(type(key) is str, "success dict key is not exact str")
            primitive(item)
        return
    raise ReviewFailure(f"success output contains non-builtin {type(value).__name__}")


def assert_success_shape(result: dict, expected: list[dict]) -> None:
    check(type(result) is dict and list(result) == TOP_LEVEL_KEYS, "success top-level order/shape")
    check(type(result["object_records"]) is list and type(result["consumed_oids"]) is list, "success record containers")
    check(type(result["budget"]) is dict, "success budget")
    check(type(result["targets"]) is list, "success targets")
    check([row["path"] for row in result["targets"]] == [row["path"] for row in expected], "target order")
    for actual, wanted in zip(result["targets"], expected):
        check(actual["path"] == wanted["path"], "target path")
        check(actual["outcome"] == wanted["outcome"], "target outcome")
        check(actual["reason"] == wanted["reason"], "target reason")
        check(list(actual) == ["path", "outcome", "reason", "walk", "stopped_at", "blob"], "target key order")
    primitive(result)


def helper_vectors(mod: types.ModuleType, variant: dict) -> int:
    records = variant["all_objects"]
    checked = 0
    for row in records[:4] + [variant["all_objects"][-1]]:
        body = bytes.fromhex(row["body_hex"])
        oid, raw, framed = mod.git_object_ids(variant["object_format"], row["type"], body)
        check((oid, raw, framed) == (row["oid"], row["body_sha256"], row["framed_sha256"]), "helper identity")
        check(mod.frame_git_object(row["type"], body) == row["type"].encode() + b" " + str(len(body)).encode() + b"\0" + body, "helper frame")
        checked += 1
    return checked


@contextmanager
def hash_trap(mod: types.ModuleType):
    trap = lambda *args, **kwargs: (_ for _ in ()).throw(ReviewFailure("hash invoked before declared-cap refusal"))
    saved: list[tuple[Any, str, Any]] = []
    module_hashlib = getattr(mod, "hashlib", None)
    if module_hashlib is not None:
        for name in ("sha1", "sha256", "new"):
            if hasattr(module_hashlib, name):
                saved.append((module_hashlib, name, getattr(module_hashlib, name)))
                setattr(module_hashlib, name, trap)
    for name in ("sha1", "sha256", "new"):
        if name in vars(mod) and callable(vars(mod)[name]):
            saved.append((mod, name, vars(mod)[name]))
            setattr(mod, name, trap)
    try:
        yield
    finally:
        for owner, name, value in reversed(saved):
            setattr(owner, name, value)


def cap_precedence(mod: types.ModuleType, variant: dict, base_kwargs: dict) -> int:
    checks = 0
    huge = b"x" * (PROFILE["max_object_bytes"] + 1)
    with hash_trap(mod):
        expect_error(mod.git_object_ids, "CODE_PROOF_LIMIT_EXCEEDED", object_format="sha1", object_type="blob", body=huge)
        expect_error(mod.frame_git_object, "CODE_PROOF_LIMIT_EXCEEDED", object_type="blob", body=huge)
    checks += 2
    objects, bodies, targets, commit_oid, root_oid = variant_inputs(variant, "exec_opt_in")
    oversized = copy.deepcopy(objects)
    oversized[0]["body_size_bytes"] = PROFILE["max_object_bytes"] + 1
    with hash_trap(mod):
        expect_error(mod.verify_code_git_objects, "CODE_PROOF_LIMIT_EXCEEDED", **{
            **base_kwargs, "object_format": variant["object_format"], "commit_oid": commit_oid,
            "root_tree_oid": root_oid, "objects": oversized, "bodies": {}, "targets": targets,
        })
    checks += 1
    lowered = dict(PROFILE)
    lowered["max_total_object_bytes"] = 1
    with hash_trap(mod):
        expect_error(mod.verify_code_git_objects, "CODE_PROOF_LIMIT_EXCEEDED", **{
            **base_kwargs, "object_format": variant["object_format"], "commit_oid": commit_oid,
            "root_tree_oid": root_oid, "objects": objects, "bodies": {}, "targets": targets, "limits": lowered,
        })
    checks += 1
    # Mapping-count cap is required before body-key traversal.
    too_many_bodies = {f"{i:040x}": b"" for i in range(PROFILE["max_objects"] + 1)}
    with hash_trap(mod):
        expect_error(mod.verify_code_git_objects, "CODE_PROOF_LIMIT_EXCEEDED", **{
            **base_kwargs, "object_format": variant["object_format"], "commit_oid": commit_oid,
            "root_tree_oid": root_oid, "objects": objects, "bodies": too_many_bodies, "targets": targets,
        })
    checks += 1
    return checks


def strict_container_checks(mod: types.ModuleType, variant: dict, base_kwargs: dict) -> int:
    objects, bodies, targets, commit_oid, root_oid = variant_inputs(variant, "exec_opt_in")
    good = {**base_kwargs, "object_format": variant["object_format"], "commit_oid": commit_oid, "root_tree_oid": root_oid, "objects": objects, "bodies": bodies, "targets": targets}
    checks = 0
    for field, replacement in (("objects", tuple(objects)), ("bodies", types.MappingProxyType(bodies)), ("targets", tuple(targets)), ("limits", types.MappingProxyType(dict(PROFILE)))):
        bad = dict(good); bad[field] = replacement
        expect_error(mod.verify_code_git_objects, "CODE_PROOF_INPUT_INVALID", **bad); checks += 1
    bad = dict(good); bad["targets"] = [{"path": "script.sh", "allow_executable_source": 1}]
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_INPUT_INVALID", **bad); checks += 1
    bad = dict(good); bad["limits"] = {**PROFILE, "max_targets": True}
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_INPUT_INVALID", **bad); checks += 1
    bad = dict(good); bad["objects"] = [{**objects[0], "body_size_bytes": True}] + objects[1:]
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_INPUT_INVALID", **bad); checks += 1
    # Count checks precede list iteration/path validation.
    bad = dict(good); bad["targets"] = targets * (PROFILE["max_targets"] + 1)
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_LIMIT_EXCEEDED", **bad); checks += 1
    bad = dict(good); bad["objects"] = objects * (PROFILE["max_objects"] + 1)
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_LIMIT_EXCEEDED", **bad); checks += 1
    return checks


def record_for(fmt: str, typ: str, body: bytes) -> dict:
    framed = typ.encode() + b" " + str(len(body)).encode() + b"\0" + body
    framed_sha = hashlib.sha256(framed).hexdigest()
    oid = hashlib.sha1(framed, usedforsecurity=False).hexdigest() if fmt == "sha1" else framed_sha
    return {"oid": oid, "object_type": typ, "body_size_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest(), "framed_sha256": framed_sha}


def tree_entries(fmt: str, body: bytes) -> list[tuple[str, bytes, bytes]]:
    width = 20 if fmt == "sha1" else 32
    pos = 0; entries = []
    while pos < len(body):
        sp = body.find(b" ", pos); check(sp > pos, "fixture tree parse")
        nul = body.find(b"\0", sp + 1); check(nul > sp + 1, "fixture tree parse")
        child = body[nul + 1:nul + 1 + width]; check(len(child) == width, "fixture tree parse")
        entries.append((body[pos:sp].decode(), body[sp + 1:nul], child)); pos = nul + 1 + width
    check(pos == len(body), "fixture tree trailing bytes")
    return entries


def encode_tree(fmt: str, entries: list[tuple[str, bytes, bytes]]) -> bytes:
    width = 20 if fmt == "sha1" else 32
    return b"".join(mode.encode() + b" " + name + b"\0" + child for mode, name, child in entries if len(child) == width)


def replace_root_commit(fmt: str, objects: list[dict], bodies: dict[str, bytes], old_root: str, old_commit: str, new_root_body: bytes | None = None, new_commit_body: bytes | None = None) -> tuple[list[dict], dict[str, bytes], str, str]:
    old_root_body = bodies[old_root]
    root_body = new_root_body if new_root_body is not None else old_root_body
    root_rec = record_for(fmt, "tree", root_body); new_root = root_rec["oid"]
    old_commit_body = bodies[old_commit]
    commit_body = new_commit_body if new_commit_body is not None else old_commit_body.replace(f"tree {old_root}".encode(), f"tree {new_root}".encode(), 1)
    commit_rec = record_for(fmt, "commit", commit_body); new_commit = commit_rec["oid"]
    old_records = {row["oid"]: row for row in objects}
    old_bodies = dict(bodies)
    old_records.pop(old_root, None); old_records.pop(old_commit, None); old_bodies.pop(old_root, None); old_bodies.pop(old_commit, None)
    old_records[new_root] = root_rec; old_records[new_commit] = commit_rec
    old_bodies[new_root] = root_body; old_bodies[new_commit] = commit_body
    return sorted(old_records.values(), key=lambda row: row["oid"]), old_bodies, new_commit, new_root


def malformed_grammar_checks(mod: types.ModuleType, variant: dict, base_kwargs: dict) -> int:
    objects, bodies, targets, commit_oid, root_oid = variant_inputs(variant, "exec_refusal")
    fmt = variant["object_format"]; checks = 0
    root_body = bodies[root_oid]
    entries = tree_entries(fmt, root_body)
    # Hash-valid unsorted, duplicate-name, truncation, and invalid-mode trees.
    mutations = []
    mutations.append(("unsorted", encode_tree(fmt, entries[1:2] + entries[:1] + entries[2:])))
    mutations.append(("duplicate", encode_tree(fmt, entries + [entries[0]])))
    mutations.append(("truncated", root_body[:-1]))
    bad_mode = list(entries); mode, name, child = bad_mode[0]; bad_mode[0] = ("100640", name, child)
    mutations.append(("mode", encode_tree(fmt, bad_mode)))
    for _label, mutated in mutations:
        bad_objects, bad_bodies, bad_commit, bad_root = replace_root_commit(fmt, objects, bodies, root_oid, commit_oid, new_root_body=mutated)
        kwargs = {**base_kwargs, "object_format": fmt, "commit_oid": bad_commit, "root_tree_oid": bad_root, "objects": bad_objects, "bodies": bad_bodies, "targets": targets}
        expect_error(mod.verify_code_git_objects, "CODE_PROOF_TREE_INVALID", **kwargs); checks += 1
    # Hash-valid commit grammar failures: CR in first line and root mismatch.
    cr_body = bodies[commit_oid].replace(b"\n", b"\r\n", 1)
    bad_objects, bad_bodies, bad_commit, bad_root = replace_root_commit(fmt, objects, bodies, root_oid, commit_oid, new_commit_body=cr_body)
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_COMMIT_INVALID", **{**base_kwargs, "object_format": fmt, "commit_oid": bad_commit, "root_tree_oid": bad_root, "objects": bad_objects, "bodies": bad_bodies, "targets": targets}); checks += 1
    mismatch_body = bodies[commit_oid].replace(f"tree {root_oid}".encode(), f"tree {variant['all_objects'][0]['oid']}".encode(), 1)
    bad_objects, bad_bodies, bad_commit, bad_root = replace_root_commit(fmt, objects, bodies, root_oid, commit_oid, new_commit_body=mismatch_body)
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_COMMIT_INVALID", **{**base_kwargs, "object_format": fmt, "commit_oid": bad_commit, "root_tree_oid": bad_root, "objects": bad_objects, "bodies": bad_bodies, "targets": targets}); checks += 1
    return checks


def closure_checks(mod: types.ModuleType, variant: dict, base_kwargs: dict) -> int:
    fmt = variant["object_format"]; checks = 0
    objects, bodies, targets, commit_oid, root_oid = variant_inputs(variant, "all_safe")
    good = {**base_kwargs, "object_format": fmt, "commit_oid": commit_oid, "root_tree_oid": root_oid, "objects": objects, "bodies": bodies, "targets": targets}
    result = mod.verify_code_git_objects(**good)
    assert_success_shape(result, variant["cases"]["all_safe"]["expected"]); checks += 1
    result2 = mod.verify_code_git_objects(**good)
    check(result == result2, "repeat success differs"); checks += 1
    for case_name in ("mixed_missing_unsafe", "exec_opt_in", "exec_refusal", "missing_nested", "non_directory_intermediate", "shared_subtree"):
        o, b, t, c, r = variant_inputs(variant, case_name)
        result = mod.verify_code_git_objects(**{**base_kwargs, "object_format": fmt, "commit_oid": c, "root_tree_oid": r, "objects": o, "bodies": b, "targets": t})
        assert_success_shape(result, variant["cases"][case_name]["expected"]); checks += 1
    # Extra key takes precedence even when a declared body is also absent.
    o, b, t, c, r = variant_inputs(variant, "exec_opt_in")
    extra_oid = next(row["oid"] for row in variant["all_objects"] if row["oid"] not in b)
    with_extra = dict(b); with_extra[extra_oid] = bytes.fromhex(next(row["body_hex"] for row in variant["all_objects"] if row["oid"] == extra_oid))
    removed = next(iter(b)); with_extra.pop(removed)
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_OBJECT_EXTRA", **{**base_kwargs, "object_format": fmt, "commit_oid": c, "root_tree_oid": r, "objects": o, "bodies": with_extra, "targets": t}); checks += 1
    # Required tree/blob body absence and declared wrong type.
    o, b, t, c, r = variant_inputs(variant, "shared_subtree")
    shared_oid = variant["path_facts"]["foo/dir"]["tree_oid"]
    o_missing = [row for row in o if row["oid"] != shared_oid]; b_missing = {k:v for k,v in b.items() if k != shared_oid}
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_OBJECT_UNAVAILABLE", **{**base_kwargs, "object_format": fmt, "commit_oid": c, "root_tree_oid": r, "objects": o_missing, "bodies": b_missing, "targets": t}); checks += 1
    o, b, t, c, r = variant_inputs(variant, "exec_opt_in")
    script_oid = variant["path_facts"]["script.sh"]["blob_oid"]
    o_missing = [row for row in o if row["oid"] != script_oid]; b_missing = {k:v for k,v in b.items() if k != script_oid}
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_OBJECT_UNAVAILABLE", **{**base_kwargs, "object_format": fmt, "commit_oid": c, "root_tree_oid": r, "objects": o_missing, "bodies": b_missing, "targets": t}); checks += 1
    # An unused declared blob must be rejected after the valid walk.
    extra_row = next(row for row in variant["all_objects"] if row["oid"] == variant["path_facts"]["link"]["blob_oid"])
    o_extra = sorted(o + [{"oid": extra_row["oid"], "object_type": extra_row["type"], "body_size_bytes": extra_row["size"], "body_sha256": extra_row["body_sha256"], "framed_sha256": extra_row["framed_sha256"]}], key=lambda row: row["oid"])
    b_extra = dict(b); b_extra[extra_row["oid"]] = bytes.fromhex(extra_row["body_hex"])
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_CONSUMED_SET_MISMATCH", **{**base_kwargs, "object_format": fmt, "commit_oid": c, "root_tree_oid": r, "objects": o_extra, "bodies": b_extra, "targets": t}); checks += 1
    return checks


def type_mismatch_check(mod: types.ModuleType, variant: dict, base_kwargs: dict) -> int:
    fmt = variant["object_format"]; records = {row["oid"]: row for row in variant["all_objects"]}
    _, root_body = next((oid, bytes.fromhex(row["body_hex"])) for oid,row in records.items() if oid == variant["root_tree_oid"])
    entries = tree_entries(fmt, root_body)
    empty_tree = variant["helper_goldens"]["empty_blob_oid"]  # replaced below with an actual tree record
    empty_tree = next(row["oid"] for row in variant["all_objects"] if row["type"] == "tree" and row["size"] == 0)
    rewritten = []
    for mode, name, child in entries:
        rewritten.append((mode, name, bytes.fromhex(empty_tree) if name == b"README.md" else child))
    bad_root_body = encode_tree(fmt, rewritten)
    root_rec = record_for(fmt, "tree", bad_root_body); bad_root = root_rec["oid"]
    old_commit = variant["commit_oid"]; old_commit_body = bytes.fromhex(records[old_commit]["body_hex"])
    bad_commit_body = old_commit_body.replace(f"tree {variant['root_tree_oid']}".encode(), f"tree {bad_root}".encode(), 1)
    commit_rec = record_for(fmt, "commit", bad_commit_body); bad_commit = commit_rec["oid"]
    empty_rec = next({"oid":row["oid"],"object_type":row["type"],"body_size_bytes":row["size"],"body_sha256":row["body_sha256"],"framed_sha256":row["framed_sha256"]} for row in variant["all_objects"] if row["oid"] == empty_tree)
    objects = sorted([root_rec, commit_rec, empty_rec], key=lambda row: row["oid"])
    bodies = {bad_root: bad_root_body, bad_commit: bad_commit_body, empty_tree: b""}
    targets = [{"path":"README.md", "allow_executable_source":False}]
    expect_error(mod.verify_code_git_objects, "CODE_PROOF_OBJECT_TYPE_MISMATCH", **{**base_kwargs, "object_format":fmt, "commit_oid":bad_commit, "root_tree_oid":bad_root, "objects":objects, "bodies":bodies, "targets":targets})
    return 1


@contextmanager
def purity_guards(mod: types.ModuleType):
    def trap(*args: Any, **kwargs: Any) -> Any:
        raise ReviewFailure("forbidden I/O/network/subprocess call during pure kernel proof")
    saved = []
    for owner, name in ((builtins, "open"), (os, "open"), (os, "stat"), (os, "listdir"), (os, "scandir"), (socket, "socket"), (socket, "create_connection"), (subprocess, "run"), (subprocess, "Popen"), (subprocess, "check_output")):
        if hasattr(owner, name):
            saved.append((owner, name, getattr(owner, name))); setattr(owner, name, trap)
    try:
        yield
    finally:
        for owner, name, old in reversed(saved): setattr(owner, name, old)


def purity_and_ownership(mod: types.ModuleType, variant: dict, base_kwargs: dict) -> int:
    objects, bodies, targets, c, r = variant_inputs(variant, "exec_opt_in")
    kwargs = {**base_kwargs, "object_format": variant["object_format"], "commit_oid": c, "root_tree_oid": r, "objects": objects, "bodies": bodies, "targets": targets}
    snap = copy.deepcopy(kwargs)
    with purity_guards(mod):
        first = mod.verify_code_git_objects(**kwargs)
        second = mod.verify_code_git_objects(**kwargs)
        expect_error(mod.verify_code_git_objects, "CODE_PROOF_OBJECT_EXTRA", **{**kwargs, "bodies": {**bodies, "0" * (40 if variant["object_format"] == "sha1" else 64): b""}})
    check(first == second, "purity repeat output")
    check(kwargs == snap, "inputs mutated")
    primitive(first)
    return 3


def run(args: argparse.Namespace) -> dict:
    candidate_root = Path(args.candidate_root).resolve()
    handoff_path = Path(args.handoff).resolve()
    fixture_path = Path(args.fixture).resolve()
    handoff = require_handoff(candidate_root, handoff_path, fixture_path)
    check_candidate_scope(candidate_root)
    fixture = load_json(fixture_path)
    check(fixture.get("schema") == "video-paper-wiki.code-git-objects-fixture.v1", "fixture schema")
    mod = import_candidate(candidate_root)
    check(set(ERROR_CODES) == set(getattr(mod, "ERROR_CODES", ERROR_CODES)), "closed error surface mismatch")
    profile = getattr(mod, "CODE_GIT_PROFILE_LIMITS")
    check(type(profile).__name__ == "mappingproxy", "profile must be immutable mappingproxy")
    check(dict(profile) == PROFILE, "profile values/order")
    try:
        profile["max_targets"] = 1
        raise ReviewFailure("profile mutation unexpectedly succeeded")
    except TypeError:
        pass
    results = {"schema": "video-paper-wiki.code-git-kernel-steward-review-result.v1", "status": "PASS", "reviewed_head": handoff["reviewed_head"], "formats": {}, "implementation_review_started": True}
    base_kwargs = {"limits": dict(PROFILE)}
    for fmt, variant in fixture["formats"].items():
        helper_count = helper_vectors(mod, variant)
        cap_count = cap_precedence(mod, variant, base_kwargs)
        strict_count = strict_container_checks(mod, variant, base_kwargs)
        grammar_count = malformed_grammar_checks(mod, variant, base_kwargs)
        closure_count = closure_checks(mod, variant, base_kwargs)
        mismatch_count = type_mismatch_check(mod, variant, base_kwargs)
        purity_count = purity_and_ownership(mod, variant, base_kwargs)
        results["formats"][fmt] = {"helper_checks": helper_count, "cap_checks": cap_count, "strict_checks": strict_count, "grammar_checks": grammar_count, "closure_checks": closure_count, "type_mismatch_checks": mismatch_count, "purity_checks": purity_count}
    Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded CODE Git kernel adversarial review after explicit handoff.")
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--fixture", default=FIXTURE_REL)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({"status": result["status"], "reviewed_head": result["reviewed_head"], "formats": result["formats"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
