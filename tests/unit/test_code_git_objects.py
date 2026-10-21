from __future__ import annotations

import builtins
import copy
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from types import MappingProxyType

import pytest

from video_paper_wiki.code_git_objects import (
    CODE_GIT_PROFILE_LIMITS,
    CODE_PROOF_COMMIT_INVALID,
    CODE_PROOF_CONSUMED_SET_MISMATCH,
    CODE_PROOF_INPUT_INVALID,
    CODE_PROOF_LIMIT_EXCEEDED,
    CODE_PROOF_OBJECT_EXTRA,
    CODE_PROOF_OBJECT_HASH_MISMATCH,
    CODE_PROOF_OBJECT_SIZE_MISMATCH,
    CODE_PROOF_OBJECT_TYPE_MISMATCH,
    CODE_PROOF_OBJECT_UNAVAILABLE,
    CODE_PROOF_TREE_INVALID,
    CodeGitProofError,
    frame_git_object,
    git_object_ids,
    verify_code_git_objects,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "code-git-objects-v1.json"
)
FIXTURE_SHA256 = "b8936db0a65d58d533016840e3d7cfbc686f819b240c812207e73638165955f0"
FIXTURE_SIZE = 52532
EMPTY_SHA1_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

_SUCCESS_KEYS = (
    "object_format",
    "commit_oid",
    "root_tree_oid",
    "object_records",
    "consumed_oids",
    "budget",
    "targets",
)
_RECORD_KEYS = (
    "oid",
    "object_type",
    "body_size_bytes",
    "body_sha256",
    "framed_sha256",
)
_BUDGET_KEYS = (
    "object_count",
    "declared_body_bytes",
    "actual_body_bytes",
    "parsed_tree_entries",
    "target_count",
    "walk_edges",
)
_TARGET_KEYS = ("path", "outcome", "reason", "walk", "stopped_at", "blob")
_EDGE_KEYS = ("tree_oid", "name_hex", "mode", "oid")
_STOPPED_KEYS = ("component_index", "tree_oid", "name_hex", "mode", "oid")
_BLOB_KEYS = ("oid", "body_size_bytes", "body_sha256", "framed_sha256")
_PUBLIC_CODES = {
    CODE_PROOF_INPUT_INVALID,
    CODE_PROOF_LIMIT_EXCEEDED,
    CODE_PROOF_OBJECT_EXTRA,
    CODE_PROOF_OBJECT_UNAVAILABLE,
    CODE_PROOF_OBJECT_SIZE_MISMATCH,
    CODE_PROOF_OBJECT_HASH_MISMATCH,
    CODE_PROOF_OBJECT_TYPE_MISMATCH,
    CODE_PROOF_COMMIT_INVALID,
    CODE_PROOF_TREE_INVALID,
    CODE_PROOF_CONSUMED_SET_MISMATCH,
}


def _load_fixture() -> dict:
    payload = FIXTURE_PATH.read_bytes()
    assert len(payload) == FIXTURE_SIZE
    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    return json.loads(payload.decode("utf-8"))


FIXTURE = _load_fixture()


def _limits(**overrides: int) -> dict[str, int]:
    values = dict(CODE_GIT_PROFILE_LIMITS)
    values.update(overrides)
    return values


def _records_and_bodies(fmt: dict, oids: list[str]) -> tuple[list[dict], dict[str, bytes]]:
    wanted = set(oids)
    records = []
    bodies: dict[str, bytes] = {}
    for item in fmt["all_objects"]:
        if item["oid"] not in wanted:
            continue
        records.append(
            {
                "oid": item["oid"],
                "object_type": item["type"],
                "body_size_bytes": item["size"],
                "body_sha256": item["body_sha256"],
                "framed_sha256": item["framed_sha256"],
            }
        )
        bodies[item["oid"]] = bytes.fromhex(item["body_hex"])
    records.sort(key=lambda rec: rec["oid"])
    return records, bodies


def _verify_case(fmt: dict, case_name: str) -> dict:
    case = fmt["cases"][case_name]
    records, bodies = _records_and_bodies(fmt, case["required_object_oids"])
    return verify_code_git_objects(
        object_format=fmt["object_format"],
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=copy.deepcopy(case["targets"]),
        limits=_limits(),
    )


def _assert_error(exc: CodeGitProofError, code: str, **details: object) -> None:
    assert isinstance(exc, CodeGitProofError)
    assert exc.code == code
    assert exc.exit_code == 2
    assert type(exc.details) is dict
    for key, value in details.items():
        assert exc.details[key] == value
    dumped = json.dumps(exc.details)
    assert "blob " not in dumped


def _tree_bytes(object_format: str, entries: list[tuple[str, bytes, str]]) -> bytes:
    raw_len = 20 if object_format == "sha1" else 32
    chunks = []
    for mode, name, oid in entries:
        raw = bytes.fromhex(oid)
        assert len(raw) == raw_len
        chunks.append(mode.encode("ascii") + b" " + name + b"\0" + raw)
    return b"".join(chunks)


def _commit_bytes(tree_oid: str, parents: tuple[str, ...] = (), extra: tuple[bytes, ...] = (), message: bytes = b"m\n") -> bytes:
    lines = [f"tree {tree_oid}".encode("ascii")]
    for parent in parents:
        lines.append(f"parent {parent}".encode("ascii"))
    lines.append(b"author A <a@example.invalid> 1 +0000")
    lines.append(b"committer C <c@example.invalid> 1 +0000")
    lines.extend(extra)
    return b"\n".join(lines) + b"\n\n" + message


def _record(object_format: str, object_type: str, body: bytes) -> tuple[dict, bytes]:
    oid, body_sha256, framed_sha256 = git_object_ids(object_format, object_type, body)
    return (
        {
            "oid": oid,
            "object_type": object_type,
            "body_size_bytes": len(body),
            "body_sha256": body_sha256,
            "framed_sha256": framed_sha256,
        },
        body,
    )


def _minimal_graph(object_format: str, tree_body: bytes = b"", targets: list[dict] | None = None, extra_objects: list[tuple[dict, bytes]] | None = None):
    tree_rec, tree_body = _record(object_format, "tree", tree_body)
    commit_body = _commit_bytes(tree_rec["oid"])
    commit_rec, commit_body = _record(object_format, "commit", commit_body)
    records = [commit_rec, tree_rec]
    bodies = {commit_rec["oid"]: commit_body, tree_rec["oid"]: tree_body}
    if extra_objects:
        for rec, body in extra_objects:
            records.append(rec)
            bodies[rec["oid"]] = body
    records.sort(key=lambda rec: rec["oid"])
    if targets is None:
        targets = [{"path": "missing.txt", "allow_executable_source": False}]
    return {
        "object_format": object_format,
        "commit_oid": commit_rec["oid"],
        "root_tree_oid": tree_rec["oid"],
        "objects": records,
        "bodies": bodies,
        "targets": targets,
        "limits": _limits(),
    }


def test_fixture_bytes_are_frozen() -> None:
    payload = FIXTURE_PATH.read_bytes()
    assert len(payload) == FIXTURE_SIZE
    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    assert FIXTURE["schema"] == "video-paper-wiki.code-git-objects-fixture.v1"


def test_profile_limits_are_immutable_mapping_proxy() -> None:
    assert type(CODE_GIT_PROFILE_LIMITS) is MappingProxyType
    assert list(CODE_GIT_PROFILE_LIMITS.items()) == [
        ("max_targets", 32),
        ("max_objects", 2048),
        ("max_tree_entries", 32768),
        ("max_object_bytes", 8388608),
        ("max_total_object_bytes", 33554432),
    ]
    with pytest.raises(TypeError):
        CODE_GIT_PROFILE_LIMITS["max_targets"] = 1  # type: ignore[index]
    copied = dict(CODE_GIT_PROFILE_LIMITS)
    copied["max_targets"] = 1
    assert CODE_GIT_PROFILE_LIMITS["max_targets"] == 32
    assert len(_PUBLIC_CODES) == 10


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_helpers_empty_blob_and_raw_versus_framed(object_format: str) -> None:
    gold = FIXTURE["formats"][object_format]["helper_goldens"]
    oid, body_sha256, framed_sha256 = git_object_ids(object_format, "blob", b"")
    assert oid == gold["empty_blob_oid"]
    assert body_sha256 == gold["empty_blob_body_sha256"]
    assert framed_sha256 == gold["empty_blob_framed_sha256"]
    assert frame_git_object("blob", b"") == b"blob 0\0"
    if object_format == "sha1":
        assert oid == EMPTY_SHA1_BLOB
        assert oid != framed_sha256
    else:
        assert oid == framed_sha256
    nonempty = b"abc"
    oid2, raw2, framed2 = git_object_ids(object_format, "blob", nonempty)
    assert raw2 != framed2
    if object_format == "sha256":
        assert oid2 == framed2
    assert frame_git_object("blob", nonempty) == b"blob 3\0abc"


def test_helper_validation_order_and_body_cap() -> None:
    with pytest.raises(CodeGitProofError) as exc:
        git_object_ids("SHA1", "blob", b"x")
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/object_format")
    with pytest.raises(CodeGitProofError) as exc:
        git_object_ids("sha1", "BLOB", b"x")
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/object_type")
    with pytest.raises(CodeGitProofError) as exc:
        git_object_ids("sha1", "blob", bytearray(b"x"))
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/body")
    with pytest.raises(CodeGitProofError) as exc:
        frame_git_object("tree", memoryview(b"x"))
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/body")
    huge = b"a" * 8388609
    with pytest.raises(CodeGitProofError) as exc:
        frame_git_object("blob", huge)
    _assert_error(
        exc.value,
        CODE_PROOF_LIMIT_EXCEEDED,
        instance_pointer="/body",
        limit_name="max_object_bytes",
        limit=8388608,
        observed=8388609,
    )
    with pytest.raises(CodeGitProofError) as exc:
        git_object_ids("sha1", "blob", huge)
    _assert_error(
        exc.value,
        CODE_PROOF_LIMIT_EXCEEDED,
        instance_pointer="/body",
        limit=8388608,
        observed=8388609,
    )


def test_blob_starting_with_frame_prefix_is_ordinary_body() -> None:
    body = b"blob 07\0abcdefg"
    oid, raw_h, framed_h = git_object_ids("sha1", "blob", body)
    assert oid != raw_h
    assert framed_h == hashlib.sha256(b"blob 15\0" + body).hexdigest()
    assert frame_git_object("blob", body).startswith(b"blob 15\0blob 07\0")


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
@pytest.mark.parametrize(
    "case_name",
    [
        "all_safe",
        "mixed_missing_unsafe",
        "exec_opt_in",
        "exec_refusal",
        "missing_nested",
        "non_directory_intermediate",
        "shared_subtree",
    ],
)
def test_fixture_cases(object_format: str, case_name: str) -> None:
    fmt = FIXTURE["formats"][object_format]
    result = _verify_case(fmt, case_name)
    expected = fmt["cases"][case_name]["expected"]
    assert list(result) == list(_SUCCESS_KEYS)
    assert result["object_format"] == object_format
    assert result["commit_oid"] == fmt["commit_oid"]
    assert result["root_tree_oid"] == fmt["root_tree_oid"]
    assert [item["path"] for item in result["targets"]] == [item["path"] for item in expected]
    for got, exp in zip(result["targets"], expected, strict=True):
        assert got["outcome"] == exp["outcome"]
        assert got["reason"] == exp["reason"]
        if got["outcome"] == "permitted_regular_blob":
            assert got["blob"] is not None
            assert list(got["blob"]) == list(_BLOB_KEYS)
        else:
            assert got["blob"] is None
    records, bodies = _records_and_bodies(fmt, fmt["cases"][case_name]["required_object_oids"])
    assert result["consumed_oids"] == sorted(rec["oid"] for rec in records)
    assert result["budget"]["object_count"] == len(records)
    assert result["budget"]["target_count"] == len(expected)
    assert result["budget"]["walk_edges"] == sum(len(item["walk"]) for item in result["targets"])
    assert result["budget"]["declared_body_bytes"] == sum(rec["body_size_bytes"] for rec in records)
    assert result["budget"]["actual_body_bytes"] == sum(len(bodies[rec["oid"]]) for rec in records)
    for rec in result["object_records"]:
        assert list(rec) == list(_RECORD_KEYS)
        assert not any(type(value) is bytes for value in rec.values())


def test_all_safe_shape_shared_blob_and_hidden_path() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    result = _verify_case(fmt, "all_safe")
    assert list(result["budget"]) == list(_BUDGET_KEYS)
    readme = next(item for item in result["targets"] if item["path"] == "README.md")
    copy_readme = next(item for item in result["targets"] if item["path"] == "README-copy.md")
    assert readme["blob"]["oid"] == copy_readme["blob"]["oid"]
    assert result["consumed_oids"].count(readme["blob"]["oid"]) == 1
    hidden = next(item for item in result["targets"] if item["path"] == ".github/source.yml")
    assert hidden["outcome"] == "permitted_regular_blob"
    assert hidden["walk"][0]["name_hex"] == b".github".hex()
    empty = next(item for item in result["targets"] if item["path"] == "empty-helper.py")
    assert empty["blob"]["oid"] == EMPTY_SHA1_BLOB
    helpers = next(item for item in result["targets"] if item["path"] == "helpers/empty.py")
    assert helpers["blob"]["oid"] == EMPTY_SHA1_BLOB
    foo = next(item for item in result["targets"] if item["path"] == "foo/dir")
    src = next(item for item in result["targets"] if item["path"] == "src/dir")
    assert foo["blob"]["oid"] == src["blob"]["oid"]
    assert foo["walk"][0]["oid"] == src["walk"][0]["oid"]
    for target in result["targets"]:
        assert list(target) == list(_TARGET_KEYS)
        for edge in target["walk"]:
            assert list(edge) == list(_EDGE_KEYS)
        assert list(target["stopped_at"]) == list(_STOPPED_KEYS)
        assert not any(type(value) is bytes for value in target.values())


def test_missing_component_keeps_name_hex_and_matched_walk() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    records, bodies = _records_and_bodies(
        fmt,
        [
            fmt["commit_oid"],
            fmt["root_tree_oid"],
            "7ed790ce84b21ea4449f99a909748cb1265b1649",
        ],
    )
    result = verify_code_git_objects(
        object_format="sha1",
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=[{"path": "src/no.py", "allow_executable_source": False}],
        limits=_limits(),
    )
    target = result["targets"][0]
    assert target["outcome"] == "missing"
    assert target["reason"] == "absent_entry"
    assert len(target["walk"]) == 1
    assert target["walk"][0]["name_hex"] == b"src".hex()
    assert target["walk"][0]["mode"] == "40000"
    stopped = target["stopped_at"]
    assert stopped["component_index"] == 1
    assert stopped["tree_oid"] == "7ed790ce84b21ea4449f99a909748cb1265b1649"
    assert stopped["name_hex"] == "6e6f2e7079"
    assert stopped["mode"] is None
    assert stopped["oid"] is None


def test_mixed_unsafe_outcomes_do_not_consume_child_objects() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    result = _verify_case(fmt, "mixed_missing_unsafe")
    by_path = {item["path"]: item for item in result["targets"]}
    assert by_path["foo"]["reason"] == "directory"
    assert by_path["link"]["reason"] == "symlink"
    assert by_path["script.sh"]["reason"] == "executable_without_permission"
    assert by_path["submodule"]["reason"] == "gitlink"
    assert by_path["missing.txt"]["stopped_at"]["name_hex"] == b"missing.txt".hex()
    assert "1111111111111111111111111111111111111111" not in result["consumed_oids"]
    assert fmt["path_facts"]["link"]["blob_oid"] not in result["consumed_oids"]
    assert fmt["path_facts"]["script.sh"]["blob_oid"] not in result["consumed_oids"]


def test_inputs_unchanged_outputs_unaliased_and_repeatable() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    case = fmt["cases"]["all_safe"]
    records, bodies = _records_and_bodies(fmt, case["required_object_oids"])
    targets = copy.deepcopy(case["targets"])
    limits = _limits()
    snap_records = copy.deepcopy(records)
    snap_bodies = dict(bodies)
    snap_targets = copy.deepcopy(targets)
    snap_limits = dict(limits)
    first = verify_code_git_objects(
        object_format="sha1",
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=targets,
        limits=limits,
    )
    second = verify_code_git_objects(
        object_format="sha1",
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=targets,
        limits=limits,
    )
    assert first == second
    assert records == snap_records
    assert bodies == snap_bodies
    assert targets == snap_targets
    assert limits == snap_limits
    first["object_records"][0]["oid"] = "0" * 40
    first["targets"][0]["path"] = "mutated"
    assert records == snap_records
    assert first["object_records"] is not records
    assert first["targets"] is not targets
    encoded = json.dumps(first)
    assert json.loads(encoded) == first
    def _walk(value: object) -> None:
        assert type(value) is not bytes
        if type(value) is dict:
            for inner in value.values():
                _walk(inner)
        elif type(value) is list:
            for inner in value:
                _walk(inner)
    _walk(second)


def test_strict_bool_and_int_and_path_conflicts() -> None:
    args = _minimal_graph("sha1")
    args["limits"]["max_targets"] = True  # type: ignore[assignment]
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/limits/max_targets")
    args = _minimal_graph("sha1")
    args["objects"][0]["body_size_bytes"] = True  # type: ignore[assignment]
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID)
    args = _minimal_graph(
        "sha1",
        targets=[{"path": "A/x", "allow_executable_source": 1}],  # type: ignore[dict-item]
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID)
    args = _minimal_graph(
        "sha1",
        targets=[
            {"path": "A/x", "allow_executable_source": False},
            {"path": "a/y", "allow_executable_source": False},
        ],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, reason="casefold_conflict")
    args = _minimal_graph(
        "sha1",
        targets=[
            {"path": "src", "allow_executable_source": False},
            {"path": "src/a.py", "allow_executable_source": False},
        ],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, reason="ancestor_conflict")
    for bad in (".git", ".GIT", "..", ".", "/abs", "a//b", "a\\b", "a%b", "a*b"):
        args = _minimal_graph(
            "sha1",
            targets=[{"path": bad, "allow_executable_source": False}],
        )
        with pytest.raises(CodeGitProofError) as exc:
            verify_code_git_objects(**args)
        _assert_error(exc.value, CODE_PROOF_INPUT_INVALID)


def test_all_five_lowerable_limits() -> None:
    args = _minimal_graph(
        "sha1",
        targets=[
            {"path": "a", "allow_executable_source": False},
            {"path": "b", "allow_executable_source": False},
        ],
    )
    args["limits"]["max_targets"] = 1
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_targets", observed=2)

    blob_rec, blob_body = _record("sha1", "blob", b"x")
    args = _minimal_graph("sha1", extra_objects=[(blob_rec, blob_body)])
    args["limits"]["max_objects"] = 1
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_objects")

    blob_rec, blob_body = _record("sha1", "blob", b"x")
    tree_body = _tree_bytes(
        "sha1",
        [
            ("100644", b"a", blob_rec["oid"]),
            ("100644", b"b", blob_rec["oid"]),
        ],
    )
    args = _minimal_graph("sha1", tree_body=tree_body, extra_objects=[(blob_rec, blob_body)])
    args["limits"]["max_tree_entries"] = 1
    args["targets"] = [{"path": "a", "allow_executable_source": False}]
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_tree_entries", observed=2)

    args = _minimal_graph("sha1")
    args["objects"][0]["body_size_bytes"] = 8
    args["limits"]["max_object_bytes"] = 4
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_object_bytes")

    args = _minimal_graph("sha1")
    total = sum(rec["body_size_bytes"] for rec in args["objects"])
    args["limits"]["max_total_object_bytes"] = 1
    assert total > 1
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_total_object_bytes")


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_declared_and_actual_caps_precede_hashing(
    object_format: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    hash_calls = {"n": 0}
    real_sha1 = hashlib.sha1
    real_sha256 = hashlib.sha256

    def wrapped_sha1(*args: object, **kwargs: object):
        hash_calls["n"] += 1
        return real_sha1(*args, **kwargs)

    def wrapped_sha256(*args: object, **kwargs: object):
        hash_calls["n"] += 1
        return real_sha256(*args, **kwargs)

    def expect_limit(
        args: dict,
        limit_name: str,
        limit_count: int,
        observed_count: int,
        instance_pointer: str,
    ) -> None:
        hash_calls["n"] = 0
        with pytest.raises(CodeGitProofError) as exc:
            verify_code_git_objects(**args)
        _assert_error(
            exc.value,
            CODE_PROOF_LIMIT_EXCEEDED,
            limit_name=limit_name,
            limit=limit_count,
            observed=observed_count,
            instance_pointer=instance_pointer,
        )
        assert hash_calls["n"] == 0

    declared_object_args = _minimal_graph(object_format)
    declared_total_args = _minimal_graph(object_format)
    actual_object_args = _minimal_graph(object_format)
    actual_total_args = _minimal_graph(object_format)

    sibling_sizes = [rec["body_size_bytes"] for rec in declared_object_args["objects"][1:]]
    declared_object_cap = max(sibling_sizes) if sibling_sizes else 1
    if declared_object_cap < 1:
        declared_object_cap = 1
    declared_object_observed = declared_object_cap + 1
    declared_object_args["objects"][0]["body_size_bytes"] = declared_object_observed
    declared_object_sum = sum(rec["body_size_bytes"] for rec in declared_object_args["objects"])
    declared_object_args["limits"] = _limits(
        max_object_bytes=declared_object_cap,
        max_total_object_bytes=declared_object_sum,
    )

    declared_sizes = [rec["body_size_bytes"] for rec in declared_total_args["objects"]]
    declared_per_object_cap = max(1, max(declared_sizes))
    declared_total_cap = 1
    running = 0
    declared_total_observed = 0
    for size in declared_sizes:
        running += size
        if running > declared_total_cap:
            declared_total_observed = running
            break
    assert declared_total_observed > declared_total_cap
    declared_total_args["limits"] = _limits(
        max_object_bytes=declared_per_object_cap,
        max_total_object_bytes=declared_total_cap,
    )

    actual_declared_sizes = [rec["body_size_bytes"] for rec in actual_object_args["objects"]]
    actual_object_cap = max(1, max(actual_declared_sizes))
    actual_first_oid = sorted(actual_object_args["bodies"])[0]
    actual_object_observed = actual_object_cap + 1
    actual_object_args["bodies"][actual_first_oid] = b"\xab" * actual_object_observed
    actual_object_sum = sum(len(body) for body in actual_object_args["bodies"].values())
    actual_object_args["limits"] = _limits(
        max_object_bytes=actual_object_cap,
        max_total_object_bytes=actual_object_sum,
    )

    actual_total_declared_sizes = [rec["body_size_bytes"] for rec in actual_total_args["objects"]]
    actual_total_declared_max = max(1, max(actual_total_declared_sizes))
    actual_total_declared_sum = sum(actual_total_declared_sizes)
    actual_total_first_oid = sorted(actual_total_args["bodies"])[0]
    padded_size = actual_total_declared_max + 10
    actual_total_args["bodies"][actual_total_first_oid] = b"\xcd" * padded_size
    actual_per_object_cap = max(len(body) for body in actual_total_args["bodies"].values())
    actual_total_cap = actual_total_declared_sum
    running = 0
    actual_total_observed = 0
    for oid in sorted(actual_total_args["bodies"]):
        running += len(actual_total_args["bodies"][oid])
        if running > actual_total_cap:
            actual_total_observed = running
            break
    assert actual_total_observed > actual_total_cap
    actual_total_args["limits"] = _limits(
        max_object_bytes=actual_per_object_cap,
        max_total_object_bytes=actual_total_cap,
    )

    monkeypatch.setattr(hashlib, "sha1", wrapped_sha1)
    monkeypatch.setattr(hashlib, "sha256", wrapped_sha256)

    expect_limit(
        declared_object_args,
        "max_object_bytes",
        declared_object_cap,
        declared_object_observed,
        "/objects/0/body_size_bytes",
    )
    expect_limit(
        declared_total_args,
        "max_total_object_bytes",
        declared_total_cap,
        declared_total_observed,
        "/objects",
    )
    expect_limit(
        actual_object_args,
        "max_object_bytes",
        actual_object_cap,
        actual_object_observed,
        "/bodies/" + actual_first_oid,
    )
    expect_limit(
        actual_total_args,
        "max_total_object_bytes",
        actual_total_cap,
        actual_total_observed,
        "/bodies",
    )


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
@pytest.mark.parametrize("site", ["limits", "object_record", "target", "body_map"])
def test_hostile_str_subclass_keys_rejected_before_methods(
    object_format: str, site: str
) -> None:
    trap = {"n": 0}
    armed = {"on": False}

    class HostileStr(str):
        def __hash__(self) -> int:
            if armed["on"]:
                trap["n"] += 1
            return super().__hash__()

        def __eq__(self, other: object) -> bool:
            if armed["on"]:
                trap["n"] += 1
            return super().__eq__(other)

        def __ne__(self, other: object) -> bool:
            if armed["on"]:
                trap["n"] += 1
            return super().__ne__(other)

        def __str__(self) -> str:
            if armed["on"]:
                trap["n"] += 1
            return super().__str__()

        def __format__(self, spec: str) -> str:
            if armed["on"]:
                trap["n"] += 1
            return super().__format__(spec)

        def __repr__(self) -> str:
            if armed["on"]:
                trap["n"] += 1
            return super().__repr__()

    args = _minimal_graph(object_format)
    if site == "limits":
        args["limits"] = {HostileStr(key): value for key, value in args["limits"].items()}
        pointer = "/limits"
        reason = "limits_key_set"
    elif site == "object_record":
        args["objects"][0] = {
            HostileStr(key): value for key, value in args["objects"][0].items()
        }
        pointer = "/objects/0"
        reason = "not_closed_record"
    elif site == "target":
        args["targets"][0] = {
            HostileStr(key): value for key, value in args["targets"][0].items()
        }
        pointer = "/targets/0"
        reason = "not_closed_record"
    else:
        args["bodies"] = {HostileStr(key): value for key, value in args["bodies"].items()}
        pointer = "/bodies"
        reason = "invalid_oid_key"

    blob_rec, blob_body = _record(object_format, "blob", b"x = 1\n")
    safe = _minimal_graph(
        object_format,
        tree_body=_tree_bytes(object_format, [("100644", b"file.py", blob_rec["oid"])]),
        extra_objects=[(blob_rec, blob_body)],
        targets=[{"path": "file.py", "allow_executable_source": False}],
    )

    armed["on"] = True
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_INPUT_INVALID,
        instance_pointer=pointer,
        reason=reason,
    )
    assert trap["n"] == 0
    armed["on"] = False
    verify_code_git_objects(**safe)


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_ordinary_closed_shape_and_strict_key_types(object_format: str) -> None:
    args = _minimal_graph(object_format)
    args["limits"] = {**args["limits"], "extra": 1}
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_INPUT_INVALID,
        instance_pointer="/limits",
        reason="limits_key_set",
    )

    args = _minimal_graph(object_format)
    args["limits"] = {index: 1 for index in range(5)}
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_INPUT_INVALID,
        instance_pointer="/limits",
        reason="limits_key_set",
    )

    args = _minimal_graph(object_format)
    args["objects"][0] = {**args["objects"][0], "extra": "x"}
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_INPUT_INVALID,
        instance_pointer="/objects/0",
        reason="not_closed_record",
    )

    args = _minimal_graph(object_format)
    args["objects"][0] = {index: index for index in range(5)}
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_INPUT_INVALID,
        instance_pointer="/objects/0",
        reason="not_closed_record",
    )

    args = _minimal_graph(object_format)
    args["targets"][0] = {**args["targets"][0], "extra": False}
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_INPUT_INVALID,
        instance_pointer="/targets/0",
        reason="not_closed_record",
    )

    args = _minimal_graph(object_format)
    args["targets"][0] = {index: False for index in range(2)}
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_INPUT_INVALID,
        instance_pointer="/targets/0",
        reason="not_closed_record",
    )

    args = _minimal_graph(object_format)
    args["bodies"] = {index: value for index, value in enumerate(args["bodies"].values())}
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_INPUT_INVALID,
        instance_pointer="/bodies",
        reason="invalid_oid_key",
    )


def test_size_and_hash_mismatch_and_body_key_set() -> None:
    args = _minimal_graph("sha1")
    oid = args["objects"][0]["oid"]
    args["objects"][0]["body_size_bytes"] = args["objects"][0]["body_size_bytes"] + 1
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_SIZE_MISMATCH, oid=oid)

    args = _minimal_graph("sha1")
    args["objects"][0]["oid"] = "a" * 40
    args["objects"].sort(key=lambda rec: rec["oid"])
    args["bodies"]["a" * 40] = args["bodies"].pop(oid)
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_HASH_MISMATCH, field="oid")

    args = _minimal_graph("sha1")
    args["objects"][0]["body_sha256"] = "b" * 64
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_HASH_MISMATCH, field="body_sha256")

    args = _minimal_graph("sha1")
    args["objects"][0]["framed_sha256"] = "c" * 64
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_HASH_MISMATCH, field="framed_sha256")

    args = _minimal_graph("sha1")
    extra = "d" * 40
    args["bodies"][extra] = b"x"
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_EXTRA, extra_oids=[extra])

    args = _minimal_graph("sha1")
    missing = args["objects"][0]["oid"]
    del args["bodies"][missing]
    args["bodies"][extra] = b"x"
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_EXTRA, extra_oids=[extra])

    args = _minimal_graph("sha1")
    del args["bodies"][args["objects"][0]["oid"]]
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_UNAVAILABLE)


def test_type_mismatch_omitted_object_and_unused_set() -> None:
    blob_rec, blob_body = _record("sha1", "blob", b"hello\n")
    tree_body = _tree_bytes("sha1", [("40000", b"src", blob_rec["oid"])])
    args = _minimal_graph(
        "sha1",
        tree_body=tree_body,
        extra_objects=[(blob_rec, blob_body)],
        targets=[{"path": "src/x", "allow_executable_source": False}],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_OBJECT_TYPE_MISMATCH,
        oid=blob_rec["oid"],
        expected_type="tree",
        actual_type="blob",
    )

    args = _minimal_graph(
        "sha1",
        tree_body=_tree_bytes("sha1", [("100644", b"file.py", blob_rec["oid"])]),
        targets=[{"path": "file.py", "allow_executable_source": False}],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_UNAVAILABLE, missing_oids=[blob_rec["oid"]])

    unused_tree, unused_body = _record(
        "sha1",
        "tree",
        _tree_bytes("sha1", [("100644", b"orphan.py", blob_rec["oid"])]),
    )
    args = _minimal_graph("sha1", extra_objects=[(unused_tree, unused_body)])
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_CONSUMED_SET_MISMATCH,
        unused_oids=[unused_tree["oid"]],
    )


def test_commit_grammar_and_limits() -> None:
    tree_rec, tree_body = _record("sha1", "tree", b"")
    good = _commit_bytes(
        tree_rec["oid"],
        parents=("a" * 40, "b" * 40),
        extra=(
            b"gpgsig -----BEGIN PGP SIGNATURE-----",
            b" synthetic",
            b" -----END PGP SIGNATURE-----",
        ),
    )
    commit_rec, commit_body = _record("sha1", "commit", good)
    result = verify_code_git_objects(
        object_format="sha1",
        commit_oid=commit_rec["oid"],
        root_tree_oid=tree_rec["oid"],
        objects=sorted([commit_rec, tree_rec], key=lambda rec: rec["oid"]),
        bodies={commit_rec["oid"]: commit_body, tree_rec["oid"]: tree_body},
        targets=[{"path": "x", "allow_executable_source": False}],
        limits=_limits(),
    )
    assert result["targets"][0]["outcome"] == "missing"

    def _commit_error(body: bytes, root: str | None = None) -> CodeGitProofError:
        rec, owned = _record("sha1", "commit", body)
        tree_oid = root if root is not None else tree_rec["oid"]
        if root is None:
            objects = sorted([rec, tree_rec], key=lambda item: item["oid"])
            bodies = {rec["oid"]: owned, tree_rec["oid"]: tree_body}
        else:
            objects = [rec]
            bodies = {rec["oid"]: owned}
        with pytest.raises(CodeGitProofError) as exc:
            verify_code_git_objects(
                object_format="sha1",
                commit_oid=rec["oid"],
                root_tree_oid=tree_oid,
                objects=objects,
                bodies=bodies,
                targets=[{"path": "x", "allow_executable_source": False}],
                limits=_limits(),
            )
        return exc.value

    mismatch = _commit_bytes("c" * 40)
    err = _commit_error(mismatch)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="root_tree_mismatch")

    duplicate_tree = b"tree " + tree_rec["oid"].encode() + b"\ntree " + tree_rec["oid"].encode() + b"\n\n"
    err = _commit_error(duplicate_tree)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="duplicate_tree_header")

    bad_parent = b"tree " + tree_rec["oid"].encode() + b"\nparent not-an-oid\n\n"
    err = _commit_error(bad_parent)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="invalid_parent_header")

    cr = b"tree " + tree_rec["oid"].encode() + b"\r\n\n"
    err = _commit_error(cr)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="header_contains_cr")

    nul = b"tree " + tree_rec["oid"].encode() + b"\0\n\n"
    err = _commit_error(nul)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="header_contains_nul")

    err = _commit_error(b"tree " + tree_rec["oid"].encode() + b"\n")
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="missing_header_terminator")

    tab = b"tree " + tree_rec["oid"].encode() + b"\n\tcontinued\n\n"
    err = _commit_error(tab)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="tab_prefixed_header")

    cont_tree = b"tree " + tree_rec["oid"].encode() + b"\n continued\n\n"
    err = _commit_error(cont_tree)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="invalid_continuation")

    huge = b"tree " + tree_rec["oid"].encode() + b"\n" + (b"x" * 65536) + b"\n\n"
    err = _commit_error(huge)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="header_too_large")

    many = [f"tree {tree_rec['oid']}".encode()]
    many.extend([b"note " + str(i).encode() for i in range(1024)])
    err = _commit_error(b"\n".join(many) + b"\n\n")
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="too_many_header_lines")


def test_tree_syntax_order_modes_and_opaque_names() -> None:
    blob_rec, blob_body = _record("sha1", "blob", b"n")
    fmt = FIXTURE["formats"]["sha1"]
    result = _verify_case(fmt, "all_safe")
    root_entries = None
    # Parsing succeeded, including foo.bar / foo / foo0 and non-UTF-8 sibling.
    assert result["budget"]["parsed_tree_entries"] > 0
    assert fmt["tree_entry_order_checks"]["non_utf8_sibling_name_hex"] == "ff73696465636172"

    def _tree_error(entries: list[tuple[str, bytes, str]]) -> CodeGitProofError:
        body = _tree_bytes("sha1", entries)
        args = _minimal_graph("sha1", tree_body=body)
        with pytest.raises(CodeGitProofError) as exc:
            verify_code_git_objects(**args)
        return exc.value

    err = _tree_error([("100664", b"file", blob_rec["oid"])])
    _assert_error(err, CODE_PROOF_TREE_INVALID, reason="invalid_mode", byte_offset=0)

    err = _tree_error(
        [
            ("100644", b"foo0", blob_rec["oid"]),
            ("100644", b"foo.bar", blob_rec["oid"]),
        ]
    )
    _assert_error(err, CODE_PROOF_TREE_INVALID, reason="invalid_order")

    err = _tree_error(
        [
            ("100644", b"aa", blob_rec["oid"]),
            ("100644", b"aa", "1" * 40),
        ]
    )
    _assert_error(err, CODE_PROOF_TREE_INVALID, reason="duplicate_name")

    truncated = b"100644 file"
    rec, _ = _record("sha1", "tree", truncated)
    commit_body = _commit_bytes(rec["oid"])
    commit_rec, commit_body = _record("sha1", "commit", commit_body)
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(
            object_format="sha1",
            commit_oid=commit_rec["oid"],
            root_tree_oid=rec["oid"],
            objects=sorted([commit_rec, rec], key=lambda item: item["oid"]),
            bodies={commit_rec["oid"]: commit_body, rec["oid"]: truncated},
            targets=[{"path": "file", "allow_executable_source": False}],
            limits=_limits(),
        )
    _assert_error(exc.value, CODE_PROOF_TREE_INVALID, reason="truncated_name")

    bad_name = _tree_bytes("sha1", [("100644", b".", blob_rec["oid"])])
    args = _minimal_graph("sha1", tree_body=bad_name)
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_TREE_INVALID, reason="invalid_name")

    opaque = _tree_bytes(
        "sha1",
        [
            ("100644", b"ascii", blob_rec["oid"]),
            ("100644", b"\xffsidecar", blob_rec["oid"]),
        ],
    )
    args = _minimal_graph(
        "sha1",
        tree_body=opaque,
        extra_objects=[(blob_rec, blob_body)],
        targets=[{"path": "ascii", "allow_executable_source": False}],
    )
    result = verify_code_git_objects(**args)
    assert result["targets"][0]["outcome"] == "permitted_regular_blob"


def test_second_commit_and_uppercase_oid_rejected() -> None:
    args = _minimal_graph("sha1")
    parent, parent_body = _record("sha1", "commit", _commit_bytes(args["root_tree_oid"], message=b"p\n"))
    args["objects"].append(parent)
    args["objects"].sort(key=lambda rec: rec["oid"])
    args["bodies"][parent["oid"]] = parent_body
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID)

    args = _minimal_graph("sha1")
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(
            object_format="sha1",
            commit_oid=args["commit_oid"].upper(),
            root_tree_oid=args["root_tree_oid"],
            objects=args["objects"],
            bodies=args["bodies"],
            targets=args["targets"],
            limits=args["limits"],
        )
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/commit_oid")


def _guard_side_effects(monkeypatch: pytest.MonkeyPatch):
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("kernel invoked a forbidden side effect")

    real_import = builtins.__import__
    forbidden = {
        "os",
        "sys",
        "io",
        "pathlib",
        "subprocess",
        "socket",
        "ssl",
        "urllib",
        "http",
        "shutil",
        "tempfile",
        "mmap",
        "json",
        "pkgutil",
        "importlib",
        "posixpath",
        "ntpath",
    }

    def guarded_import(name: str, *args: object, **kwargs: object):
        root = name.split(".", 1)[0]
        if root in forbidden or name.startswith("video_paper_wiki."):
            raise AssertionError(f"kernel imported {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(builtins, "open", boom)
    monkeypatch.setattr(os, "open", boom, raising=False)
    monkeypatch.setattr(os, "stat", boom, raising=False)
    monkeypatch.setattr(socket, "socket", boom, raising=False)
    monkeypatch.setattr(subprocess, "Popen", boom, raising=False)
    monkeypatch.setattr(subprocess, "run", boom, raising=False)


def test_kernel_has_no_io_imports() -> None:
    import video_paper_wiki.code_git_objects as module

    forbidden = {
        "os",
        "sys",
        "io",
        "pathlib",
        "subprocess",
        "socket",
        "json",
        "urllib",
        "resources",
    }
    for name, value in vars(module).items():
        if getattr(value, "__name__", None) in forbidden:
            raise AssertionError(name)


def test_kernel_call_does_not_use_io_or_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _guard_side_effects(monkeypatch)
    fmt = FIXTURE["formats"]["sha1"]
    _verify_case(fmt, "exec_opt_in")
    args = _minimal_graph("sha1")
    args["objects"][0]["body_sha256"] = "e" * 64
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_HASH_MISMATCH)


def test_unused_trees_are_still_syntax_checked() -> None:
    blob_rec, blob_body = _record("sha1", "blob", b"ok\n")
    good_tree = _tree_bytes("sha1", [("100644", b"ok.py", blob_rec["oid"])])
    bad_tree_body = b"not-a-tree"
    bad_tree, bad_body = _record("sha1", "tree", bad_tree_body)
    args = _minimal_graph(
        "sha1",
        tree_body=good_tree,
        extra_objects=[(blob_rec, blob_body), (bad_tree, bad_body)],
        targets=[{"path": "ok.py", "allow_executable_source": False}],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_TREE_INVALID)
