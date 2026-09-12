"""Unit tests for the private code-proof resource foundation."""

from __future__ import annotations

import builtins
import copy
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from video_paper_wiki import code_proof_resources as cpr
from video_paper_wiki.code_proof_resources import (
    CodeProofResourceError,
    CodeProofStructureError,
    compile_code_proof_resources,
    resource_origin_plan,
    _parse_resource_bytes,
    _validate_profile_inventory,
    _validate_schema_references,
)

_CHECKOUT_ROOT = Path(__file__).parents[2]
_SCHEMAS_DIR = _CHECKOUT_ROOT / "schemas"
_PROFILE_PATH = (
    _CHECKOUT_ROOT / "src" / "video_paper_wiki" / "profiles" / "code-proof-v1.json"
)
_FIXTURE_PATH = _CHECKOUT_ROOT / "tests" / "fixtures" / "code-proof-resource-v1.json"
_COMMON_TITLE = "video-paper-wiki.code-proof-common.v1"
_COMMON_SCHEMA_ID = (
    "https://video-paper-wiki.dev/schemas/"
    "video-paper-wiki.code-proof-common.v1.schema.json"
)
_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
_MARKER = "MARKER_SECRET_9f3a_do_not_leak"
_SCHEMA_STEMS = (
    "code-acquisition-intent",
    "code-config-evidence",
    "code-git-bundle",
    "code-proof-command-result",
    "code-proof-common",
    "code-proof-observation",
    "code-proof-observe-input",
    "code-proof-request-input",
    "code-proof-request",
    "code-source-handoff",
)
_RESOURCE_KEYS = tuple(
    [f"schemas/video-paper-wiki.{stem}.v1.schema.json" for stem in _SCHEMA_STEMS]
    + ["profiles/code-proof-v1.json"]
)
_FORBIDDEN_KEYWORDS = (
    "$anchor",
    "$dynamicAnchor",
    "$dynamicRef",
    "$recursiveAnchor",
    "$recursiveRef",
)
_LIMIT_FIELDS = (
    [("git", name) for name in (
        "max_targets",
        "max_objects",
        "max_tree_entries",
        "max_object_bytes",
        "max_total_object_bytes",
    )]
    + [("config", name) for name in (
        "max_source_bytes",
        "max_depth",
        "max_nodes",
        "max_array_items",
        "max_object_keys",
        "max_key_bytes",
        "max_string_codepoints",
        "max_scalars",
        "max_numeric_lexeme_bytes",
        "max_numeric_coefficient_digits",
        "max_numeric_abs_exponent",
        "max_numeric_canonical_bytes",
        "max_declarations",
    )]
    + [("public", name) for name in (
        "max_bundle_bytes",
        "max_inline_normalized_bytes",
        "max_request_bytes",
        "max_intent_bytes",
        "max_observation_bytes",
        "max_config_document_bytes",
        "max_handoff_bytes",
        "max_output_peak_bytes",
    )]
)
_LIMIT_MODES = (
    "one",
    "max",
    "max+1",
    "zero",
    "bool",
    "float",
    "missing",
    "extra",
)


def _canon_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _load_retained_bytes() -> dict[str, bytes]:
    retained: dict[str, bytes] = {}
    for stem in _SCHEMA_STEMS:
        filename = f"video-paper-wiki.{stem}.v1.schema.json"
        retained[f"schemas/{filename}"] = (_SCHEMAS_DIR / filename).read_bytes()
    retained["profiles/code-proof-v1.json"] = _PROFILE_PATH.read_bytes()
    return retained


@pytest.fixture(scope="module")
def retained_bytes() -> dict[str, bytes]:
    return _load_retained_bytes()


@pytest.fixture(scope="module")
def resources(retained_bytes: dict[str, bytes]) -> cpr.CodeProofResources:
    return compile_code_proof_resources(dict(retained_bytes))


@pytest.fixture
def schema_map(retained_bytes: dict[str, bytes]) -> dict[str, dict]:
    parsed: dict[str, dict] = {}
    for key, blob in retained_bytes.items():
        if not key.startswith("schemas/"):
            continue
        filename = key.removeprefix("schemas/")
        schema_id = "https://video-paper-wiki.dev/schemas/" + filename
        parsed[schema_id] = _parse_resource_bytes(blob)
    return parsed


@pytest.fixture
def profile_document(retained_bytes: dict[str, bytes]) -> dict:
    return _parse_resource_bytes(retained_bytes["profiles/code-proof-v1.json"])


def _assert_resource(exc: BaseException, reason: str) -> None:
    assert type(exc) is CodeProofResourceError
    assert exc.reason == reason
    assert str(exc) == f"CODE proof resource: {reason}"
    assert exc.__cause__ is None
    assert _MARKER not in str(exc)
    assert _MARKER not in repr(exc)
    assert _MARKER not in exc.reason


def _assert_structure(exc: BaseException, reason: str) -> None:
    assert type(exc) is CodeProofStructureError
    assert exc.reason == reason
    assert str(exc) == f"CODE proof structure: {reason}"
    assert exc.__cause__ is None
    assert _MARKER not in str(exc)
    assert _MARKER not in repr(exc)
    assert _MARKER not in exc.reason


def _full_limits(resources: cpr.CodeProofResources) -> dict[str, dict[str, int]]:
    return resources.materialize_limits(None)


def _with_limit(
    hards: dict[str, dict[str, int]],
    group: str,
    name: str,
    value: object,
) -> dict[str, object]:
    payload: dict[str, object] = {item: dict(values) for item, values in hards.items()}
    inner = dict(payload[group])  # type: ignore[arg-type]
    inner[name] = value
    payload[group] = inner
    return payload


class _Str(str):
    pass


class _Dict(dict):
    pass


class _List(list):
    pass


class _Int(int):
    pass


class _Bytes(bytes):
    pass


def test_checkout_bytes_match_production_pins(retained_bytes: dict[str, bytes]) -> None:
    pins = resource_origin_plan().resources
    paths = tuple(pin.relative_path for pin in pins)
    assert paths == tuple(sorted(paths))
    for pin in pins:
        blob = retained_bytes[pin.relative_path]
        assert type(blob) is bytes
        assert len(blob) == pin.size_bytes
        assert hashlib.sha256(blob).hexdigest() == pin.sha256


def test_immutable_pins_and_context_independence(
    retained_bytes: dict[str, bytes],
) -> None:
    payload = dict(retained_bytes)
    first = compile_code_proof_resources(payload)
    second = compile_code_proof_resources(payload)
    assert first is not second
    assert first.resource_pins == resource_origin_plan().resources
    assert first.profile_sha256 == (
        "650a6a51a1f08651d659262424577a90233649e4949bfc0cc4850d7a7777ee32"
    )
    payload.clear()
    assert first.validate_structure(_COMMON_TITLE, {}) is None
    mutated = first.materialize_limits(None)
    mutated["git"]["max_targets"] = 1
    assert second.materialize_limits(None)["git"]["max_targets"] == 32
    with pytest.raises(AttributeError):
        first.resource_pins[0].size_bytes = 0  # type: ignore[misc]
    with pytest.raises(AttributeError):
        resource_origin_plan().layout = "installed"  # type: ignore[misc]


def test_source_and_installed_lexical_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cpr,
        "__file__",
        "/repo/src/video_paper_wiki/code_proof_resources.py",
    )
    source = cpr.resource_origin_plan()
    assert source.layout == "source"
    assert source.package_directory == "/repo/src/video_paper_wiki"
    assert source.schemas_directory == "/repo/schemas"
    assert source.profiles_directory == "/repo/src/video_paper_wiki/profiles"
    monkeypatch.setattr(
        cpr,
        "__file__",
        "/site-packages/video_paper_wiki/code_proof_resources.py",
    )
    installed = cpr.resource_origin_plan()
    assert installed.layout == "installed"
    assert installed.package_directory == "/site-packages/video_paper_wiki"
    assert installed.schemas_directory == "/site-packages/video_paper_wiki/schemas"
    assert installed.profiles_directory == "/site-packages/video_paper_wiki/profiles"
    assert source.resources == installed.resources
    # Mocked origin tests do not claim that an installed-wheel check has run.


def test_installed_path_under_src_uses_source_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cpr,
        "__file__",
        "/opt/src/video_paper_wiki/code_proof_resources.py",
    )
    plan = cpr.resource_origin_plan()
    assert plan.layout == "source"
    assert plan.schemas_directory == "/opt/schemas"
    assert plan.profiles_directory == "/opt/src/video_paper_wiki/profiles"


def test_origin_independent_of_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = resource_origin_plan()
    monkeypatch.chdir(tmp_path)
    after = resource_origin_plan()
    assert after == before
    assert after.package_directory == before.package_directory


@pytest.mark.parametrize(
    "raw",
    [
        "video_paper_wiki/code_proof_resources.py",
        "/tmp/video_paper_wiki/./code_proof_resources.py",
        "/tmp/src/../src/video_paper_wiki/code_proof_resources.py",
        "/tmp/src/./video_paper_wiki/code_proof_resources.py",
        "/tmp/not_the_package/code_proof_resources.py",
        "/video_paper_wiki",
        "/tmp/video_paper_wiki/\0code_proof_resources.py",
        "//src/video_paper_wiki/code_proof_resources.py",
        f"/tmp/{_MARKER}/not_wiki/code_proof_resources.py",
    ],
)
def test_missing_origin_has_no_fallback(
    raw: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cpr, "__file__", raw)
    with pytest.raises(CodeProofResourceError) as caught:
        cpr.resource_origin_plan()
    _assert_resource(caught.value, "resource_origin")


def test_relative_origin_does_not_use_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "src" / "video_paper_wiki"
    package.mkdir(parents=True)
    monkeypatch.chdir(package)
    monkeypatch.setattr(cpr, "__file__", "code_proof_resources.py")
    with pytest.raises(CodeProofResourceError) as caught:
        cpr.resource_origin_plan()
    _assert_resource(caught.value, "resource_origin")


@pytest.mark.parametrize("key", _RESOURCE_KEYS)
def test_each_pin_byte_mutation_is_resource_hash(
    retained_bytes: dict[str, bytes],
    key: str,
) -> None:
    payload = dict(retained_bytes)
    mutated = bytearray(payload[key])
    mutated[-1] ^= 0x01
    payload[key] = bytes(mutated)
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(payload)
    _assert_resource(caught.value, "resource_hash")


@pytest.mark.parametrize("key", _RESOURCE_KEYS)
def test_each_pin_size_mutation_is_resource_hash(
    retained_bytes: dict[str, bytes],
    key: str,
) -> None:
    payload = dict(retained_bytes)
    payload[key] = retained_bytes[key] + b"\n"
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(payload)
    _assert_resource(caught.value, "resource_hash")


def test_mapping_type_and_membership_failures(
    retained_bytes: dict[str, bytes],
) -> None:
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources([retained_bytes])  # type: ignore[arg-type]
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(_Dict(retained_bytes))
    _assert_resource(caught.value, "resource_shape")

    missing = dict(retained_bytes)
    missing.pop("profiles/code-proof-v1.json")
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(missing)
    _assert_resource(caught.value, "resource_shape")

    extra = dict(retained_bytes)
    extra[f"schemas/{_MARKER}.json"] = extra["profiles/code-proof-v1.json"]
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(extra)
    _assert_resource(caught.value, "resource_shape")

    int_keys = {index: blob for index, blob in enumerate(retained_bytes.values())}
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(int_keys)  # type: ignore[arg-type]
    _assert_resource(caught.value, "resource_shape")

    subclass_keys = {_Str(key): value for key, value in retained_bytes.items()}
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(subclass_keys)
    _assert_resource(caught.value, "resource_shape")

    bytearray_values = {key: bytearray(value) for key, value in retained_bytes.items()}
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(bytearray_values)  # type: ignore[arg-type]
    _assert_resource(caught.value, "resource_shape")

    subclass_values = {key: _Bytes(value) for key, value in retained_bytes.items()}
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(subclass_values)
    _assert_resource(caught.value, "resource_shape")

    extra_and_mutated = dict(retained_bytes)
    extra_and_mutated["schemas/extra.v1.schema.json"] = b"{}"
    mutated = bytearray(extra_and_mutated["profiles/code-proof-v1.json"])
    mutated[-1] ^= 0x01
    extra_and_mutated["profiles/code-proof-v1.json"] = bytes(mutated)
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(extra_and_mutated)
    _assert_resource(caught.value, "resource_shape")


def test_self_consistent_forged_resources_are_not_trusted(
    resources: cpr.CodeProofResources,
) -> None:
    hards = resources.materialize_limits(None)
    forged: dict[str, bytes] = {}
    rows = []
    for stem in _SCHEMA_STEMS:
        filename = f"video-paper-wiki.{stem}.v1.schema.json"
        document = {
            "$schema": _DRAFT_2020_12,
            "$id": "https://video-paper-wiki.dev/schemas/" + filename,
            "title": f"video-paper-wiki.{stem}.v1",
            "type": "object",
        }
        blob = _canon_bytes(document)
        forged[f"schemas/{filename}"] = blob
        rows.append(
            {
                "title": f"video-paper-wiki.{stem}.v1",
                "filename": filename,
                "size_bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
    profile = {
        "schema": "video-paper-wiki.code-proof-profile.v1",
        "profile": "code-proof-v1",
        "revision": 1,
        "limits": {
            "git": dict(hards["git"]),
            "config": dict(hards["config"]),
            "public": dict(hards["public"]),
        },
        "admission": {
            "max_request_input_bytes": 65536,
            "max_observe_input_bytes": 1048576,
        },
        "schemas": rows,
    }
    forged["profiles/code-proof-v1.json"] = _canon_bytes(profile)
    with pytest.raises(CodeProofResourceError) as caught:
        compile_code_proof_resources(forged)
    _assert_resource(caught.value, "resource_hash")
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_profile_inventory(
            _parse_resource_bytes(forged["profiles/code-proof-v1.json"])
        )
    _assert_resource(caught.value, "resource_shape")


def test_strict_resource_parsing() -> None:
    good = {"title": "ok", "count": 1}
    blob = _canon_bytes(good)
    assert _parse_resource_bytes(blob) == good

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(b"\xef\xbb\xbf" + blob)
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(_canon_bytes(["not", "an", "object"]))
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(b'{\n  "a": 1,\n  "a": 2\n}\n')
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(_canon_bytes({"a": 1.5}))
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(b'{\n  "a": NaN\n}\n')
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(b'{\n  "a": Infinity\n}\n')
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(b'{\n  "a": "\\ud800"\n}\n')
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(blob + b"{}")
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(blob[:-1])
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(blob + b"\n")
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(
            json.dumps(good, ensure_ascii=False, indent=4).encode("utf-8") + b"\n"
        )
    _assert_resource(caught.value, "resource_shape")

    with pytest.raises(CodeProofResourceError) as caught:
        _parse_resource_bytes(b"not json")
    _assert_resource(caught.value, "resource_shape")
    assert "not json" not in str(caught.value)


def test_schema_reference_helpers(schema_map: dict[str, dict]) -> None:
    untouched = copy.deepcopy(schema_map)
    assert _validate_schema_references(schema_map) is None
    assert schema_map == untouched

    empty_fragment = copy.deepcopy(schema_map)
    empty_fragment[_COMMON_SCHEMA_ID]["$ref"] = _COMMON_SCHEMA_ID + "#"
    assert _validate_schema_references(empty_fragment) is None

    missing = copy.deepcopy(schema_map)
    missing.pop(_COMMON_SCHEMA_ID)
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(missing)
    _assert_resource(caught.value, "resource_shape")

    extra = copy.deepcopy(schema_map)
    extra["https://example.invalid/extra"] = {
        "$id": "https://example.invalid/extra",
        "$schema": _DRAFT_2020_12,
        "title": "extra",
    }
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(extra)
    _assert_resource(caught.value, "resource_shape")

    nested = copy.deepcopy(schema_map)
    nested[_COMMON_SCHEMA_ID]["__nested"] = {"$id": "https://example.invalid/nested"}
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(nested)
    _assert_resource(caught.value, "resource_shape")

    missing_pointer = copy.deepcopy(schema_map)
    missing_pointer[_COMMON_SCHEMA_ID]["$ref"] = "#/does/not/exist"
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(missing_pointer)
    _assert_resource(caught.value, "resource_shape")

    relative = copy.deepcopy(schema_map)
    relative[_COMMON_SCHEMA_ID]["$ref"] = (
        "video-paper-wiki.code-proof-common.v1.schema.json"
    )
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(relative)
    _assert_resource(caught.value, "resource_shape")

    percent = copy.deepcopy(schema_map)
    percent[_COMMON_SCHEMA_ID]["$ref"] = _COMMON_SCHEMA_ID.replace(
        "schemas/",
        "schemas/%73",
    )
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(percent)
    _assert_resource(caught.value, "resource_shape")

    dialect = copy.deepcopy(schema_map)
    dialect[_COMMON_SCHEMA_ID]["$ref"] = _DRAFT_2020_12
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(dialect)
    _assert_resource(caught.value, "resource_shape")

    bad_index = copy.deepcopy(schema_map)
    bad_index[_COMMON_SCHEMA_ID]["__arr"] = [{}]
    bad_index[_COMMON_SCHEMA_ID]["$ref"] = "#/__arr/00"
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(bad_index)
    _assert_resource(caught.value, "resource_shape")

    missing_index = copy.deepcopy(schema_map)
    missing_index[_COMMON_SCHEMA_ID]["__arr"] = [{}]
    missing_index[_COMMON_SCHEMA_ID]["$ref"] = "#/__arr/1"
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(missing_index)
    _assert_resource(caught.value, "resource_shape")

    bad_escape = copy.deepcopy(schema_map)
    bad_escape[_COMMON_SCHEMA_ID]["$ref"] = "#/foo~2bar"
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(bad_escape)
    _assert_resource(caught.value, "resource_shape")

    anchor_fragment = copy.deepcopy(schema_map)
    anchor_fragment[_COMMON_SCHEMA_ID]["$ref"] = "#defs"
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(anchor_fragment)
    _assert_resource(caught.value, "resource_shape")


@pytest.mark.parametrize("keyword", _FORBIDDEN_KEYWORDS)
def test_forbidden_schema_keywords(
    schema_map: dict[str, dict],
    keyword: str,
) -> None:
    mutated = copy.deepcopy(schema_map)
    mutated[_COMMON_SCHEMA_ID][keyword] = "#x"
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_schema_references(mutated)
    _assert_resource(caught.value, "resource_shape")


def test_denied_retrieval_callback() -> None:
    with pytest.raises(CodeProofResourceError) as caught:
        cpr._deny_registry_retrieve(_DRAFT_2020_12)
    _assert_resource(caught.value, "resource_shape")
    with pytest.raises(CodeProofResourceError) as caught:
        cpr._deny_registry_retrieve(f"https://example.invalid/{_MARKER}")
    _assert_resource(caught.value, "resource_shape")


def test_profile_inventory_helper(
    profile_document: dict,
    resources: cpr.CodeProofResources,
) -> None:
    assert _validate_profile_inventory(copy.deepcopy(profile_document)) is None
    mutated = copy.deepcopy(profile_document)
    mutated["revision"] = 2
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_profile_inventory(mutated)
    _assert_resource(caught.value, "resource_shape")
    mutated = copy.deepcopy(profile_document)
    mutated["revision"] = True
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_profile_inventory(mutated)
    _assert_resource(caught.value, "resource_shape")
    mutated = copy.deepcopy(profile_document)
    mutated["schemas"][0]["sha256"] = "0" * 64
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_profile_inventory(mutated)
    _assert_resource(caught.value, "resource_shape")
    mutated = copy.deepcopy(profile_document)
    mutated["extra"] = 1
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_profile_inventory(mutated)
    _assert_resource(caught.value, "resource_shape")
    mutated = copy.deepcopy(profile_document)
    mutated["limits"]["git"]["max_targets"] = 1
    with pytest.raises(CodeProofResourceError) as caught:
        _validate_profile_inventory(mutated)
    _assert_resource(caught.value, "resource_shape")
    assert resources.profile_sha256 == (
        "650a6a51a1f08651d659262424577a90233649e4949bfc0cc4850d7a7777ee32"
    )


def test_common_root_structural_probe(resources: cpr.CodeProofResources) -> None:
    instance: dict[str, object] = {}
    before = copy.deepcopy(instance)
    assert resources.validate_structure(_COMMON_TITLE, instance) is None
    assert instance == before
    # Structural success is not semantic authentication of evidence.


def test_fixture_structural_rows(resources: cpr.CodeProofResources) -> None:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["profile_sha256"] == resources.profile_sha256
    cases = payload["cases"]
    assert len(cases) == 264
    for row in cases:
        assert type(row) is dict
        assert set(row) == {"name", "title", "instance"}
        probe = copy.deepcopy(row["instance"])
        before = copy.deepcopy(probe)
        assert resources.validate_structure(row["title"], probe) is None
        assert probe == before


def test_structure_preflight_and_titles(resources):
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_SCHEMA_ID, [])
    _assert_structure(exc, "shape")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure("video-paper-wiki.code-proof-noninventory.v1", [])
    _assert_structure(exc, "shape")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure("video-paper-wiki.code-proof-profile.v1", [])
    _assert_structure(exc, "shape")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE + "#/$defs/profile", [])
    _assert_structure(exc, "shape")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_Str(_COMMON_TITLE), [])
    _assert_structure(exc, "shape")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, _Dict())
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, _List())
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, _Str("ok"))
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, _Int(0))
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, 0.0)
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, 1.5)
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, float("nan"))
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, float("inf"))
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, float("-inf"))
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, {"\ud800": 1})
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, "\ud800")
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, {"k": "\ud800"})
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, {1: "a"})
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, {None: "a"})
    _assert_structure(exc, "type")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, {_Str("a"): 1})
    _assert_structure(exc, "type")
    dict_cycle = {}
    dict_cycle["loop"] = dict_cycle
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, dict_cycle)
    _assert_structure(exc, "type")
    list_cycle = []
    list_cycle.append(list_cycle)
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, list_cycle)
    _assert_structure(exc, "type")
    mixed = {}
    nested = [mixed]
    mixed["child"] = nested
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_COMMON_TITLE, mixed)
    _assert_structure(exc, "type")
    nfd = "e\u0301"
    shared_map = {"k": nfd}
    shared_seq = [shared_map]
    shared_instance = {"a": shared_seq, "b": shared_seq, "c": shared_map}
    resources.validate_structure(_COMMON_TITLE, shared_instance)
    resources.validate_structure(_COMMON_TITLE, [shared_seq, shared_seq, shared_map, shared_map])
    assert shared_instance["a"] is shared_instance["b"]
    assert shared_map["k"] == nfd
    assert shared_map["k"] == "e\u0301"
    assert len(shared_map["k"]) == 2
    resources.validate_structure(_COMMON_TITLE, [])
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure("video-paper-wiki.code-proof-request.v1", {})
    _assert_structure(exc, "shape")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.validate_structure(_MARKER, [])
    _assert_structure(exc, "shape")


@pytest.mark.parametrize("group,name", _LIMIT_FIELDS)
@pytest.mark.parametrize("mode", _LIMIT_MODES)
def test_limit_field_boundaries(
    resources: cpr.CodeProofResources,
    group: str,
    name: str,
    mode: str,
) -> None:
    hards = _full_limits(resources)
    hard = hards[group][name]
    if mode == "one":
        assert resources.materialize_limits(_with_limit(hards, group, name, 1))[group][name] == 1
        return
    if mode == "max":
        assert resources.materialize_limits(_with_limit(hards, group, name, hard))[group][name] == hard
        return
    if mode == "max+1":
        invalid: object = hard + 1
    elif mode == "zero":
        invalid = 0
    elif mode == "bool":
        invalid = True
    elif mode == "float":
        invalid = 1.0
    elif mode == "missing":
        payload = _with_limit(hards, group, name, 1)
        del payload[group][name]  # type: ignore[attr-defined]
        with pytest.raises(CodeProofStructureError) as caught:
            resources.materialize_limits(payload)
        _assert_structure(caught.value, "limits")
        return
    else:
        payload = _with_limit(hards, group, name, 1)
        payload[group]["max_unexpected"] = 1  # type: ignore[index]
        with pytest.raises(CodeProofStructureError) as caught:
            resources.materialize_limits(payload)
        _assert_structure(caught.value, "limits")
        return
    with pytest.raises(CodeProofStructureError) as caught:
        resources.materialize_limits(_with_limit(hards, group, name, invalid))
    _assert_structure(caught.value, "limits")


def test_limit_group_and_copy_boundaries(resources: cpr.CodeProofResources) -> None:
    hards = _full_limits(resources)
    first = resources.materialize_limits(None)
    second = resources.materialize_limits(None)
    first["git"]["max_targets"] = 1
    assert second["git"]["max_targets"] == 32
    supplied = _full_limits(resources)
    copied = resources.materialize_limits(supplied)
    supplied["git"]["max_targets"] = 1
    assert copied["git"]["max_targets"] == 32
    extra_group = _full_limits(resources)
    extra_group["other"] = {"max_targets": 1}
    with pytest.raises(CodeProofStructureError) as caught:
        resources.materialize_limits(extra_group)
    _assert_structure(caught.value, "limits")
    missing_group = _full_limits(resources)
    del missing_group["git"]
    with pytest.raises(CodeProofStructureError) as caught:
        resources.materialize_limits(missing_group)
    _assert_structure(caught.value, "limits")
    with pytest.raises(CodeProofStructureError) as caught:
        resources.materialize_limits({})
    _assert_structure(caught.value, "limits")
    with pytest.raises(CodeProofStructureError) as caught:
        resources.materialize_limits(_Dict(hards))
    _assert_structure(caught.value, "limits")
    with pytest.raises(CodeProofStructureError) as caught:
        resources.materialize_limits([])
    _assert_structure(caught.value, "limits")


def test_error_constructors_reject_invalid_reasons() -> None:
    with pytest.raises(ValueError) as caught:
        CodeProofResourceError("nope")
    assert str(caught.value) == "Invalid CODE proof error reason"
    with pytest.raises(ValueError) as caught:
        CodeProofStructureError(_MARKER)
    assert str(caught.value) == "Invalid CODE proof error reason"
    assert _MARKER not in str(caught.value)


def _install_io_guards(monkeypatch: pytest.MonkeyPatch, blocked) -> None:
    monkeypatch.setattr(builtins, "open", blocked)
    monkeypatch.setattr(os, "open", blocked)
    monkeypatch.setattr(os, "listdir", blocked)
    monkeypatch.setattr(os, "scandir", blocked)
    monkeypatch.setattr(os, "walk", blocked)
    monkeypatch.setattr(os, "stat", blocked)
    monkeypatch.setattr(os, "lstat", blocked)
    monkeypatch.setattr(os, "getcwd", blocked)
    monkeypatch.setattr(os, "system", blocked)
    monkeypatch.setattr(os.path, "exists", blocked)
    monkeypatch.setattr(Path, "read_bytes", blocked)
    monkeypatch.setattr(Path, "read_text", blocked)
    monkeypatch.setattr(Path, "open", blocked)
    monkeypatch.setattr(Path, "iterdir", blocked)
    monkeypatch.setattr(Path, "stat", blocked)
    monkeypatch.setattr(Path, "exists", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "call", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(http.client.HTTPConnection, "request", blocked)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", blocked)


def test_production_methods_do_not_perform_io(
    retained_bytes: dict[str, bytes],
    resources: cpr.CodeProofResources,
    schema_map: dict[str, dict],
    profile_document: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def blocked(*_args: object, **_kwargs: object) -> None:
        calls.append(1)
        raise RuntimeError("unexpected I/O")

    before_modules = set(sys.modules)
    _install_io_guards(monkeypatch, blocked)
    compiled = compile_code_proof_resources(dict(retained_bytes))
    assert compiled.validate_structure(_COMMON_TITLE, {}) is None
    compiled.materialize_limits(None)
    compiled.materialize_limits(_full_limits(compiled))
    resource_origin_plan()
    _parse_resource_bytes(retained_bytes["profiles/code-proof-v1.json"])
    _validate_schema_references(copy.deepcopy(schema_map))
    _validate_profile_inventory(copy.deepcopy(profile_document))
    assert resources.validate_structure(_COMMON_TITLE, {}) is None
    assert calls == []
    new_modules = set(sys.modules) - before_modules
    assert not any(
        name.startswith("video_paper_wiki.")
        and name not in {"video_paper_wiki", "video_paper_wiki.code_proof_resources"}
        for name in new_modules
    )


def test_context_rejects_external_configuration(retained_bytes):
    def _external(*args, **kwargs):
        raise AssertionError(_MARKER)

    with pytest.raises(CodeProofResourceError) as exc:
        cpr.CodeProofResources()
    _assert_resource(exc, "resource_shape")
    with pytest.raises(TypeError):
        cpr.CodeProofResources(_MARKER, (), _external, {})
    with pytest.raises(TypeError):
        cpr.CodeProofResources(
            digest=_MARKER,
            pins=(),
            validators={_COMMON_TITLE: _external},
            hard_limits={},
        )
    with pytest.raises(TypeError):
        cpr.CodeProofResources(
            _profile_sha256=_MARKER,
            _resource_pins=(),
            _validators={_COMMON_TITLE: _external},
            _hard_limits={},
        )
    first = compile_code_proof_resources(retained_bytes)
    second = compile_code_proof_resources(retained_bytes)
    assert type(first) is cpr.CodeProofResources
    assert type(second) is cpr.CodeProofResources
    assert first is not second
    assert type(first.profile_sha256) is str
    assert type(first.resource_pins) is tuple
    assert first.profile_sha256 == second.profile_sha256
    assert first.resource_pins == second.resource_pins
    with pytest.raises(AttributeError):
        first.profile_sha256 = first.profile_sha256
    with pytest.raises(AttributeError):
        first.resource_pins = first.resource_pins


def test_limit_exact_key_and_value_types(resources):
    class _Armed:
        def __init__(self):
            self._live = False

        def arm(self):
            self._live = True

        def __hash__(self):
            if self._live:
                raise RuntimeError(_MARKER)
            return id(self)

        def __eq__(self, other):
            if self._live:
                raise RuntimeError(_MARKER)
            return self is other

    full = _full_limits(resources)
    omitted = resources.materialize_limits(None)
    assert omitted == full
    got = resources.materialize_limits(full)
    assert got == full
    assert got is not full
    for group in full:
        assert got[group] is not full[group]
    bad = _full_limits(resources)
    group = next(iter(bad))
    bad[_Str(group)] = bad.pop(group)
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(bad)
    _assert_structure(exc, "limits")
    bad = _full_limits(resources)
    group = next(iter(bad))
    inner = dict(bad[group])
    field = next(iter(inner))
    inner[_Str(field)] = inner.pop(field)
    bad[group] = inner
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(bad)
    _assert_structure(exc, "limits")
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(_Dict(_full_limits(resources)))
    _assert_structure(exc, "limits")
    bad = _full_limits(resources)
    group = next(iter(bad))
    bad[group] = _Dict(bad[group])
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(bad)
    _assert_structure(exc, "limits")
    bad = _full_limits(resources)
    group = next(iter(bad))
    field = next(iter(bad[group]))
    bad[group][field] = _Int(1)
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(bad)
    _assert_structure(exc, "limits")
    items = list(_full_limits(resources).items())
    probe = _Armed()
    outer = {probe: dict(items[0][1])}
    for group, inner in items[1:]:
        outer[group] = dict(inner)
    probe.arm()
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(outer)
    _assert_structure(exc, "limits")
    full = _full_limits(resources)
    group = next(iter(full))
    inner_items = list(full[group].items())
    probe = _Armed()
    new_inner = {probe: inner_items[0][1]}
    for key, raw in inner_items[1:]:
        new_inner[key] = raw
    outer = {}
    for name, inner in full.items():
        outer[name] = dict(inner)
    outer[group] = new_inner
    probe.arm()
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(outer)
    _assert_structure(exc, "limits")
    bad = _full_limits(resources)
    bad["not-a-limit-group"] = dict(next(iter(bad.values())))
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(bad)
    _assert_structure(exc, "limits")
    bad = _full_limits(resources)
    bad.pop(next(iter(bad)))
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(bad)
    _assert_structure(exc, "limits")
    bad = _full_limits(resources)
    group = next(iter(bad))
    inner = dict(bad[group])
    inner["not-a-limit-key"] = 1
    bad[group] = inner
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(bad)
    _assert_structure(exc, "limits")
    bad = _full_limits(resources)
    group = next(iter(bad))
    inner = dict(bad[group])
    inner.pop(next(iter(inner)))
    bad[group] = inner
    with pytest.raises(CodeProofStructureError) as exc:
        resources.materialize_limits(bad)
    _assert_structure(exc, "limits")


def test_profile_exact_builtin_keys(profile_document):
    _validate_profile_inventory(profile_document)
    mutated = copy.deepcopy(profile_document)
    key = next(iter(mutated))
    mutated[_Str(key)] = mutated.pop(key)
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_profile_inventory(mutated)
    _assert_resource(exc, "resource_shape")
    mutated = copy.deepcopy(profile_document)
    limits = mutated["limits"]
    key = next(iter(limits))
    limits[_Str(key)] = limits.pop(key)
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_profile_inventory(mutated)
    _assert_resource(exc, "resource_shape")
    mutated = copy.deepcopy(profile_document)
    limits = mutated["limits"]
    group = next(iter(limits))
    subgroup = limits[group]
    key = next(iter(subgroup))
    subgroup[_Str(key)] = subgroup.pop(key)
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_profile_inventory(mutated)
    _assert_resource(exc, "resource_shape")
    mutated = copy.deepcopy(profile_document)
    admission = mutated["admission"]
    key = next(iter(admission))
    admission[_Str(key)] = admission.pop(key)
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_profile_inventory(mutated)
    _assert_resource(exc, "resource_shape")
    mutated = copy.deepcopy(profile_document)
    row = mutated["inventory"][0]
    key = next(iter(row))
    row[_Str(key)] = row.pop(key)
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_profile_inventory(mutated)
    _assert_resource(exc, "resource_shape")


def test_schema_reference_malformed_graphs(schema_map):
    _validate_schema_references(copy.deepcopy(schema_map))
    shared = copy.deepcopy(schema_map)
    shared_node = {"description": "shared"}
    shared_list = [shared_node]
    shared[_COMMON_SCHEMA_ID]["codeProofSharedA"] = shared_node
    shared[_COMMON_SCHEMA_ID]["codeProofSharedB"] = shared_node
    shared[_COMMON_SCHEMA_ID]["codeProofSharedC"] = shared_list
    shared[_COMMON_SCHEMA_ID]["codeProofSharedD"] = shared_list
    _validate_schema_references(shared)
    escaped = copy.deepcopy(schema_map)
    escaped[_COMMON_SCHEMA_ID]["~"] = {"a/b": {"type": "null"}}
    escaped[_COMMON_SCHEMA_ID]["codeProofEscapedRef"] = {"$ref": "#/~0/a~1b"}
    _validate_schema_references(escaped)
    huge = copy.deepcopy(schema_map)
    huge[_COMMON_SCHEMA_ID]["codeProofList"] = [{"type": "null"}]
    huge[_COMMON_SCHEMA_ID]["codeProofHugeRef"] = {"$ref": "#/codeProofList/" + ("1" * 4301)}
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_schema_references(huge)
    _assert_resource(exc, "resource_shape")
    dict_cycle = copy.deepcopy(schema_map)
    loop_dict = {}
    loop_dict["loop"] = loop_dict
    dict_cycle[_COMMON_SCHEMA_ID]["codeProofCycleDict"] = loop_dict
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_schema_references(dict_cycle)
    _assert_resource(exc, "resource_shape")
    list_cycle = copy.deepcopy(schema_map)
    loop_list = []
    loop_list.append(loop_list)
    list_cycle[_COMMON_SCHEMA_ID]["codeProofCycleList"] = loop_list
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_schema_references(list_cycle)
    _assert_resource(exc, "resource_shape")
    subclass_key = copy.deepcopy(schema_map)
    subclass_key[_COMMON_SCHEMA_ID]["codeProofSubclassKey"] = {_Str("child"): True}
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_schema_references(subclass_key)
    _assert_resource(exc, "resource_shape")
    surrogate_key = copy.deepcopy(schema_map)
    surrogate_key[_COMMON_SCHEMA_ID]["codeProofSurrogateKey"] = {"\ud800": True}
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_schema_references(surrogate_key)
    _assert_resource(exc, "resource_shape")
    surrogate_str = copy.deepcopy(schema_map)
    surrogate_str[_COMMON_SCHEMA_ID]["codeProofSurrogateStr"] = {"k": "\ud800"}
    with pytest.raises(CodeProofResourceError) as exc:
        _validate_schema_references(surrogate_str)
    _assert_resource(exc, "resource_shape")
