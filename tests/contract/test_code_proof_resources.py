"""Contract tests for the CODE-PROOF schema set and installed profile."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

import pytest
from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource
from referencing.jsonschema import DRAFT202012

import video_paper_wiki
from video_paper_wiki.code_config_parser import CODE_CONFIG_PROFILE_LIMITS
from video_paper_wiki.code_git_objects import CODE_GIT_PROFILE_LIMITS


DRAFT = "https://json-schema.org/draft/2020-12/schema"
ID_PREFIX = "https://video-paper-wiki.dev/schemas/"
COMMON_FILENAME = "video-paper-wiki.code-proof-common.v1.schema.json"
COMMON_ID = ID_PREFIX + COMMON_FILENAME
PROFILE_SCHEMA = "video-paper-wiki.code-proof-profile.v1"
FIXTURE_SCHEMA = "video-paper-wiki.code-proof-resource-fixtures.v1"

SCHEMA_FILENAMES: tuple[str, ...] = (
    "video-paper-wiki.code-proof-common.v1.schema.json",
    "video-paper-wiki.code-proof-request-input.v1.schema.json",
    "video-paper-wiki.code-proof-observe-input.v1.schema.json",
    "video-paper-wiki.code-proof-command-result.v1.schema.json",
    "video-paper-wiki.code-proof-request.v1.schema.json",
    "video-paper-wiki.code-git-bundle.v1.schema.json",
    "video-paper-wiki.code-acquisition-intent.v1.schema.json",
    "video-paper-wiki.code-proof-observation.v1.schema.json",
    "video-paper-wiki.code-config-evidence.v1.schema.json",
    "video-paper-wiki.code-source-handoff.v1.schema.json",
)
INSTANCE_TITLES: tuple[str, ...] = tuple(
    name[: -len(".schema.json")]
    for name in SCHEMA_FILENAMES
    if name != COMMON_FILENAME
)
SAVED_KINDS: tuple[str, ...] = (
    "code-proof-request",
    "code-git-bundle",
    "code-acquisition-intent",
    "code-proof-observation",
    "code-config-evidence",
    "code-source-handoff",
)
COMMAND_BRANCHES: tuple[str, ...] = (
    "request",
    "observe",
    "status",
    "config",
    "handoff",
)
STATUS_STATES: tuple[str, ...] = (
    "empty",
    "requested",
    "pending_normalized",
    "pending_raw_bundle",
    "pending_raw_bodies",
    "observed",
)
TYPED_MARKERS: tuple[str, ...] = (
    "json-nested-lf",
    "json-pointer-escaping",
    "json-unicode-crlf-tabs",
    "toml-dotted-promotion",
    "toml-nested-lf",
    "toml-numeric-boundaries",
    "toml-unicode-crlf-inline",
)
LINE_SEPARATORS: tuple[str, ...] = ("\n", "\r", "\r\n", "\u2028", "\u2029")
FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "$anchor",
    "$dynamicAnchor",
    "$dynamicRef",
    "$recursiveAnchor",
    "$recursiveRef",
)
GIT_LIMITS = {
    "max_targets": 32,
    "max_objects": 2048,
    "max_tree_entries": 32768,
    "max_object_bytes": 8388608,
    "max_total_object_bytes": 33554432,
}
CONFIG_LIMITS = {
    "max_source_bytes": 262144,
    "max_depth": 32,
    "max_nodes": 1024,
    "max_array_items": 256,
    "max_object_keys": 1024,
    "max_key_bytes": 256,
    "max_string_codepoints": 16384,
    "max_scalars": 512,
    "max_numeric_lexeme_bytes": 128,
    "max_numeric_coefficient_digits": 64,
    "max_numeric_abs_exponent": 128,
    "max_numeric_canonical_bytes": 256,
    "max_declarations": 4096,
}
PUBLIC_LIMITS = {
    "max_bundle_bytes": 1048576,
    "max_inline_normalized_bytes": 16384,
    "max_request_bytes": 65536,
    "max_intent_bytes": 1048576,
    "max_observation_bytes": 2097152,
    "max_config_document_bytes": 2097152,
    "max_handoff_bytes": 131072,
    "max_output_peak_bytes": 134217728,
}


class IntSubclass(int):
    """Integer subclass rejected by the exact-int type checker."""


def _is_exact_int(_checker: object, instance: object) -> bool:
    return type(instance) is int


ExactDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", _is_exact_int
    ),
)


def _package_dir() -> Path:
    return Path(video_paper_wiki.__file__).resolve().parent


def _profile_path() -> Path:
    return _package_dir() / "profiles" / "code-proof-v1.json"


def _schemas_dir() -> Path:
    package_dir = _package_dir()
    src_dir = package_dir.parent
    if src_dir.name == "src":
        return src_dir.parent / "schemas"
    return package_dir / "schemas"


def _fixture_path() -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures" / "code-proof-resource-v1.json"


def _title_of(filename: str) -> str:
    return filename[: -len(".schema.json")]


def _schema_id(filename: str) -> str:
    return ID_PREFIX + filename


def _dump(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _load_json(path: Path) -> tuple[bytes, Any]:
    raw = path.read_bytes()
    return raw, json.loads(raw.decode("utf-8"))


def _deny_retrieve(uri: str) -> Resource:
    raise NoSuchResource(ref=uri)


def _pointer_escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer in ("", "#"):
        return document
    if pointer.startswith("#"):
        pointer = pointer[1:]
    if not pointer:
        return document
    if not pointer.startswith("/"):
        raise AssertionError(f"invalid JSON Pointer {pointer!r}")
    node = document
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if part not in node:
                raise AssertionError(f"missing pointer part {part!r} in {pointer!r}")
            node = node[part]
        elif isinstance(node, list):
            node = node[int(part)]
        else:
            raise AssertionError(f"cannot descend into {type(node)!r} at {pointer!r}")
    return node


def _walk(value: Any, pointer: str = "") -> Iterator[tuple[str, Any]]:
    yield pointer, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, pointer + "/" + _pointer_escape(str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, pointer + "/" + str(index))


def _get_path(obj: Any, path: tuple[Any, ...]) -> Any:
    node = obj
    for part in path:
        node = node[part]
    return node


def _set_path(obj: Any, path: tuple[Any, ...], value: Any) -> None:
    node = obj
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value


def _del_path(obj: Any, path: tuple[Any, ...]) -> None:
    node = obj
    for part in path[:-1]:
        node = node[part]
    del node[path[-1]]


def _add_key(obj: Any, path: tuple[Any, ...], key: str, value: Any) -> None:
    node = _get_path(obj, path) if path else obj
    node[key] = value


def _command_branch(instance: dict) -> str:
    if "acquisition_targets" in instance:
        return "request"
    if "config" in instance and "stored_path" in instance:
        return "config"
    if "handoffs" in instance and "state" not in instance and "status" not in instance:
        return "handoff"
    if "state" in instance:
        return "status"
    if "observation" in instance and "status" in instance:
        return "observe"
    raise AssertionError(f"unrecognized command-result keys {sorted(instance)}")


@pytest.fixture(scope="session")
def schema_documents() -> dict[str, dict]:
    directory = _schemas_dir()
    documents = {}
    for filename in SCHEMA_FILENAMES:
        path = directory / filename
        _raw, document = _load_json(path)
        documents[filename] = document
    return documents


@pytest.fixture(scope="session")
def schema_bytes() -> dict[str, bytes]:
    directory = _schemas_dir()
    return {
        filename: (directory / filename).read_bytes()
        for filename in SCHEMA_FILENAMES
    }


@pytest.fixture(scope="session")
def profile_bytes() -> bytes:
    return _profile_path().read_bytes()


@pytest.fixture(scope="session")
def profile(profile_bytes: bytes) -> dict:
    return json.loads(profile_bytes.decode("utf-8"))


@pytest.fixture(scope="session")
def registry(schema_documents: dict[str, dict]) -> Registry:
    pairs = []
    for filename, document in schema_documents.items():
        resource = Resource.from_contents(
            document, default_specification=DRAFT202012
        )
        pairs.append((_schema_id(filename), resource))
    return Registry(retrieve=_deny_retrieve).with_resources(pairs)


@pytest.fixture(scope="session")
def validators_by_title(
    schema_documents: dict[str, dict], registry: Registry
) -> dict[str, Any]:
    mapping = {}
    for filename, document in schema_documents.items():
        mapping[_title_of(filename)] = ExactDraft202012Validator(
            document, registry=registry
        )
    return mapping


@pytest.fixture(scope='session')
def fixture_bundle(validators_by_title):
    _, bundle = _load_json(_fixture_path())
    for case in bundle['cases']:
        _validate(validators_by_title, case['title'], case['instance'])
    return bundle


def _validate(validators_by_title: dict[str, Any], title: str, instance: Any) -> None:
    validators_by_title[title].validate(instance)


def _is_valid(validators_by_title: dict[str, Any], title: str, instance: Any) -> bool:
    return validators_by_title[title].is_valid(instance)


def _validate_def(registry: Registry, def_name: str, instance: Any) -> None:
    schema = {"$schema": DRAFT, "$ref": f"{COMMON_ID}#/$defs/{def_name}"}
    ExactDraft202012Validator(schema, registry=registry).validate(instance)


def _def_is_valid(registry: Registry, def_name: str, instance: Any) -> bool:
    schema = {"$schema": DRAFT, "$ref": f"{COMMON_ID}#/$defs/{def_name}"}
    return ExactDraft202012Validator(schema, registry=registry).is_valid(instance)


def test_schema_root_metadata(schema_documents: dict[str, dict]) -> None:
    assert list(schema_documents) == list(SCHEMA_FILENAMES)
    for filename, document in schema_documents.items():
        assert document["$schema"] == DRAFT
        assert document["$id"] == _schema_id(filename)
        assert document["title"] == _title_of(filename)


def test_draft_2020_12_validity(schema_documents: dict[str, dict]) -> None:
    for document in schema_documents.values():
        Draft202012Validator.check_schema(document)


def test_no_nested_ids_anchors_or_dynamic_refs(
    schema_documents: dict[str, dict],
) -> None:
    for filename, document in schema_documents.items():
        for pointer, node in _walk(document):
            if not isinstance(node, dict):
                continue
            for keyword in FORBIDDEN_KEYWORDS:
                assert keyword not in node, f"{filename} {pointer} {keyword}"
            if "$id" in node:
                assert pointer == "", f"nested $id at {filename} {pointer}"


def test_all_refs_resolve(schema_documents: dict[str, dict]) -> None:
    known_ids = {_schema_id(name) for name in SCHEMA_FILENAMES}
    for filename, document in schema_documents.items():
        base = _schema_id(filename)
        for pointer, node in _walk(document):
            if not isinstance(node, dict) or "$ref" not in node:
                continue
            ref = node["$ref"]
            assert isinstance(ref, str)
            if ref.startswith("#"):
                target_id = base
                fragment = ref
            else:
                if "#" in ref:
                    target_id, fragment = ref.split("#", 1)
                    fragment = "#" + fragment
                else:
                    target_id, fragment = ref, ""
            assert target_id in known_ids, f"{filename} {pointer} {ref}"
            target_name = target_id[len(ID_PREFIX) :]
            _resolve_pointer(schema_documents[target_name], fragment)


def test_undeclared_retrieval_denied(registry: Registry) -> None:
    with pytest.raises(NoSuchResource):
        registry["https://video-paper-wiki.dev/schemas/not-declared.schema.json"]


def test_exact_integer_type_checker(registry: Registry) -> None:
    valid = {
        "max_targets": 1,
        "max_objects": 1,
        "max_tree_entries": 1,
        "max_object_bytes": 1,
        "max_total_object_bytes": 1,
    }
    _validate_def(registry, "git_limits", valid)
    for bad in (True, False, 1.0, IntSubclass(1)):
        mutated = dict(valid)
        mutated["max_targets"] = bad
        assert not _def_is_valid(registry, "git_limits", mutated)
    assert not _def_is_valid(registry, "profile", {"revision": True})
    profile_revision = {
        "schema": PROFILE_SCHEMA,
        "profile": "code-proof-v1",
        "revision": 1.0,
        "limits": {
            "git": GIT_LIMITS,
            "config": CONFIG_LIMITS,
            "public": PUBLIC_LIMITS,
        },
        "admission": {
            "max_request_input_bytes": 65536,
            "max_observe_input_bytes": 1048576,
        },
        "schemas": [],
    }
    assert not _def_is_valid(registry, "profile", profile_revision)


def test_profile_constants_and_inventory(
    profile: dict, schema_bytes: dict[str, bytes], registry: Registry
) -> None:
    _validate_def(registry, "profile", profile)
    assert profile["schema"] == PROFILE_SCHEMA
    assert profile["profile"] == "code-proof-v1"
    assert type(profile["revision"]) is int
    assert profile["revision"] == 1
    assert profile["limits"]["git"] == GIT_LIMITS
    assert profile["limits"]["config"] == CONFIG_LIMITS
    assert profile["limits"]["public"] == PUBLIC_LIMITS
    assert profile["admission"] == {
        "max_request_input_bytes": 65536,
        "max_observe_input_bytes": 1048576,
    }
    rows = profile["schemas"]
    assert len(rows) == 10
    filenames = [row["filename"] for row in rows]
    assert filenames == sorted(filenames)
    assert filenames == sorted(SCHEMA_FILENAMES)
    titles = [row["title"] for row in rows]
    assert titles == [_title_of(name) for name in filenames]
    assert len(set(titles)) == 10
    assert len(set(filenames)) == 10
    for row in rows:
        raw = schema_bytes[row["filename"]]
        assert type(row["size_bytes"]) is int
        assert row["size_bytes"] > 0
        assert row["size_bytes"] == len(raw)
        assert row["sha256"] == hashlib.sha256(raw).hexdigest()
        assert row["title"] == _title_of(row["filename"])


def test_kernel_profile_limit_maps(profile: dict) -> None:
    assert dict(CODE_GIT_PROFILE_LIMITS) == profile["limits"]["git"]
    assert dict(CODE_CONFIG_PROFILE_LIMITS) == profile["limits"]["config"]
    assert dict(CODE_GIT_PROFILE_LIMITS) == GIT_LIMITS
    assert dict(CODE_CONFIG_PROFILE_LIMITS) == CONFIG_LIMITS


def test_serialization_one_lf(
    schema_bytes: dict[str, bytes],
    schema_documents: dict[str, dict],
    profile_bytes: bytes,
    profile: dict,
) -> None:
    for filename, raw in schema_bytes.items():
        assert raw.endswith(b"\n")
        assert not raw.endswith(b"\n\n")
        assert _dump(schema_documents[filename]) == raw
    assert profile_bytes.endswith(b"\n")
    assert not profile_bytes.endswith(b"\n\n")
    assert _dump(profile) == profile_bytes


def test_profile_definition_validates_installed_profile(
    profile: dict, registry: Registry
) -> None:
    _validate_def(registry, "profile", profile)
    mutated = copy.deepcopy(profile)
    mutated["limits"]["git"]["extra"] = 1
    assert not _def_is_valid(registry, "profile", mutated)
    mutated = copy.deepcopy(profile)
    del mutated["limits"]["config"]["max_nodes"]
    assert not _def_is_valid(registry, "profile", mutated)
    mutated = copy.deepcopy(profile)
    mutated["limits"]["git"]["max_targets"] = 33
    assert not _def_is_valid(registry, "profile", mutated)
    mutated = copy.deepcopy(profile)
    mutated["admission"]["max_observe_input_bytes"] = 1048577
    assert not _def_is_valid(registry, "profile", mutated)
    swapped = copy.deepcopy(profile)
    swapped["schemas"][0], swapped["schemas"][1] = (
        swapped["schemas"][1],
        swapped["schemas"][0],
    )
    assert _def_is_valid(registry, "profile", swapped)
    hashed = copy.deepcopy(profile)
    hashed["schemas"][0]["sha256"] = "a" * 63 + "b"
    if hashed["schemas"][0]["sha256"] != profile["schemas"][0]["sha256"]:
        assert _def_is_valid(registry, "profile", hashed)


def test_fixture_transport_and_all_cases_validate(
    fixture_bundle: dict,
    profile_bytes: bytes,
    validators_by_title: dict[str, Any],
) -> None:
    assert set(fixture_bundle) == {"schema", "profile_sha256", "cases"}
    assert fixture_bundle["schema"] == FIXTURE_SCHEMA
    assert fixture_bundle["profile_sha256"] == hashlib.sha256(profile_bytes).hexdigest()
    cases = fixture_bundle["cases"]
    names = [case["name"] for case in cases]
    assert names == sorted(names)
    assert len(names) == len(set(names))
    for name in names:
        assert name.isascii()
    for case in cases:
        assert set(case) == {"name", "title", "instance"}
        assert case["title"] in INSTANCE_TITLES
        _validate(validators_by_title, case["title"], case["instance"])


def test_positive_coverage(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    cases = fixture_bundle["cases"]
    titles = {case["title"] for case in cases}
    for title in INSTANCE_TITLES:
        assert title in titles
    kinds = set()
    branches = set()
    states = set()
    formats = set()
    object_formats = set()
    pending_raw_body_kinds = set()
    normalized_other = set()
    input_other = set()
    mixed = False
    source_only = False
    typed_seen = set()
    for case in cases:
        instance = case["instance"]
        title = case["title"]
        if title.endswith(
            (
                ".code-proof-request.v1",
                ".code-git-bundle.v1",
                ".code-acquisition-intent.v1",
                ".code-proof-observation.v1",
                ".code-config-evidence.v1",
                ".code-source-handoff.v1",
            )
        ) or (
            isinstance(instance, dict) and instance.get("kind") in SAVED_KINDS
        ):
            if isinstance(instance, dict) and "kind" in instance:
                kinds.add(instance["kind"])
        if title == "video-paper-wiki.code-proof-command-result.v1":
            branch = _command_branch(instance)
            branches.add(branch)
            if branch == "status":
                states.add(instance["state"])
                if instance["state"] == "pending_raw_bodies":
                    if any(
                        item.startswith("objects/") for item in instance["missing"]
                    ):
                        pending_raw_body_kinds.add("missing_bodies")
                    else:
                        pending_raw_body_kinds.add("bodies_complete")
            if branch == "observe":
                states.add(instance["status"]["state"])
        if isinstance(instance, dict):
            data = instance.get("data", instance)
            if isinstance(data, dict):
                if data.get("object_format") in ("sha1", "sha256"):
                    object_formats.add(data["object_format"])
                if data.get("format") in ("json", "toml", "source-only"):
                    formats.add(data["format"])
                    if data.get("format") == "source-only":
                        source_only = True
                if data.get("mode") in ("git_objects", "normalized_text"):
                    pass
                targets = data.get("targets")
                if isinstance(targets, list):
                    statuses = {
                        row.get("status")
                        for row in targets
                        if isinstance(row, dict)
                    }
                    normalized_other.update(
                        statuses
                        & {"host_missing", "host_inaccessible", "host_unavailable"}
                    )
                    if "source_text" in statuses and (
                        "missing" in statuses or "unsafe" in statuses
                    ):
                        mixed = True
                if title == "video-paper-wiki.code-proof-observe-input.v1":
                    for row in data.get("targets") or []:
                        if isinstance(row, dict) and row.get("status") in {
                            "missing",
                            "inaccessible",
                            "unavailable",
                        }:
                            input_other.add(row["status"])
        for marker in TYPED_MARKERS:
            if marker in case["name"] and title.endswith("code-config-evidence.v1"):
                typed_seen.add(marker)
                _validate(validators_by_title, title, instance)
    assert kinds == set(SAVED_KINDS)
    assert branches == set(COMMAND_BRANCHES)
    assert states == set(STATUS_STATES)
    assert pending_raw_body_kinds == {"missing_bodies", "bodies_complete"}
    assert normalized_other == {
        "host_missing",
        "host_inaccessible",
        "host_unavailable",
    }
    assert input_other == {"missing", "inaccessible", "unavailable"}
    assert mixed
    assert object_formats == {"sha1", "sha256"}
    assert source_only
    assert "json" in formats
    assert "toml" in formats
    assert typed_seen == set(TYPED_MARKERS)


def test_lexical_line_separators_rejected(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    seed = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request-input.v1"
    )
    fields = ("paper_id", "repository", "commit_oid")
    for field in fields:
        original = seed["instance"][field]
        for separator in LINE_SEPARATORS:
            mutated = copy.deepcopy(seed["instance"])
            mutated[field] = original + separator
            assert not _is_valid(
                validators_by_title, seed["title"], mutated
            ), f"{field} {separator!r}"
    envelope = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request.v1"
    )
    for separator in LINE_SEPARATORS:
        mutated = copy.deepcopy(envelope["instance"])
        mutated["id"] = mutated["id"] + separator
        assert not _is_valid(validators_by_title, envelope["title"], mutated)
        mutated = copy.deepcopy(envelope["instance"])
        mutated["data"]["profile_sha256"] = mutated["data"]["profile_sha256"] + separator
        assert not _is_valid(validators_by_title, envelope["title"], mutated)
    status = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-command-result.v1"
        and "state" in case["instance"]
        and case["instance"]["state"] == "empty"
    )
    for separator in LINE_SEPARATORS:
        mutated = copy.deepcopy(status["instance"])
        mutated["batch_id"] = mutated["batch_id"] + separator
        assert not _is_valid(validators_by_title, status["title"], mutated)
    observe = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-observe-input.v1"
    )
    for separator in LINE_SEPARATORS:
        mutated = copy.deepcopy(observe["instance"])
        mutated["observed_at"] = mutated["observed_at"] + separator
        assert not _is_valid(validators_by_title, observe["title"], mutated)


def test_unknown_and_missing_fields(fixture_bundle, validators_by_title):
    allowed_optional = ('video-paper-wiki.code-proof-request-input.v1', '', 'limits')
    for case in fixture_bundle['cases']:
        title = case['title']
        instance = case['instance']
        for pointer, node in _walk(instance):
            if type(node) is not dict:
                continue
            mutated = copy.deepcopy(instance)
            target = _resolve_pointer(mutated, '#' + pointer)
            target['__unknown_field__'] = True
            assert not _is_valid(validators_by_title, title, mutated)
            for key in list(node.keys()):
                mutated = copy.deepcopy(instance)
                target = _resolve_pointer(mutated, '#' + pointer)
                del target[key]
                if (title, pointer, key) == allowed_optional:
                    _validate(validators_by_title, title, mutated)
                else:
                    assert not _is_valid(validators_by_title, title, mutated)


def test_strict_integers_in_instances(fixture_bundle, validators_by_title):
    found_int = False
    for case in fixture_bundle['cases']:
        title = case['title']
        instance = case['instance']
        for path, value in _walk_typed(instance):
            if type(value) is not int:
                continue
            found_int = True
            for bad in (True, False, float(value), IntSubclass(value)):
                mutated = copy.deepcopy(instance)
                _set_path(mutated, path, bad)
                assert not _is_valid(validators_by_title, title, mutated)
    assert found_int


def test_wrong_ref_kinds(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    observation = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-observation.v1"
        and case["instance"]["data"]["mode"] == "git_objects"
    )
    mutated = copy.deepcopy(observation["instance"])
    original = mutated["data"]["intent"]["id"]
    mutated["data"]["intent"]["id"] = original.replace(
        "ce1:code-acquisition-intent:", "ce1:code-proof-request:", 1
    )
    assert not _is_valid(validators_by_title, observation["title"], mutated)
    config = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-config-evidence.v1"
    )
    mutated = copy.deepcopy(config["instance"])
    mutated["data"]["request"]["id"] = mutated["data"]["request"]["id"].replace(
        "ce1:code-proof-request:", "ce1:code-git-bundle:", 1
    )
    assert not _is_valid(validators_by_title, config["title"], mutated)


def test_invalid_enums(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    observe = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-observe-input.v1"
    )
    mutated = copy.deepcopy(observe["instance"])
    mutated["mode"] = "other"
    assert not _is_valid(validators_by_title, observe["title"], mutated)
    status = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-command-result.v1"
        and case["instance"].get("state") == "observed"
    )
    mutated = copy.deepcopy(status["instance"])
    mutated["state"] = "complete"
    assert not _is_valid(validators_by_title, status["title"], mutated)
    request = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request-input.v1"
    )
    mutated = copy.deepcopy(request["instance"])
    mutated["object_format"] = "sha512"
    assert not _is_valid(validators_by_title, request["title"], mutated)
    mutated = copy.deepcopy(request["instance"])
    mutated["targets"][0]["roles"] = ["documentation"]
    assert not _is_valid(validators_by_title, request["title"], mutated)


def test_excess_arrays(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    request = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request-input.v1"
    )
    mutated = copy.deepcopy(request["instance"])
    seed = mutated["targets"][0]
    mutated["targets"] = []
    for index in range(33):
        item = copy.deepcopy(seed)
        item["path"] = f"p{index}.json" if index else seed["path"]
        mutated["targets"].append(item)
    assert not _is_valid(validators_by_title, request["title"], mutated)
    bundle = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-git-bundle.v1"
    )
    mutated = copy.deepcopy(bundle["instance"])
    record = copy.deepcopy(mutated["data"]["objects"][0])
    mutated["data"]["objects"] = [copy.deepcopy(record) for _ in range(2049)]
    assert not _is_valid(validators_by_title, bundle["title"], mutated)
    observation = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-observation.v1"
        and case["instance"]["data"].get("git_proof")
    )
    mutated = copy.deepcopy(observation["instance"])
    edge = mutated["data"]["git_proof"]["targets"][0]["walk"][0]
    mutated["data"]["git_proof"]["targets"][0]["walk"] = [copy.deepcopy(edge) for _ in range(33)]
    assert not _is_valid(validators_by_title, observation["title"], mutated)
    typed = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-config-evidence.v1"
        and case["instance"]["data"]["format"] in ("json", "toml")
    )
    mutated = copy.deepcopy(typed["instance"])
    node = copy.deepcopy(mutated["data"]["result"]["nodes"][0])
    mutated["data"]["result"]["nodes"] = [copy.deepcopy(node) for _ in range(1025)]
    assert not _is_valid(validators_by_title, typed["title"], mutated)


def test_impossible_nulls(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    present = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-observe-input.v1"
        and case["instance"].get("mode") == "normalized_text"
        and case["instance"]["targets"][0]["status"] == "present"
    )
    mutated = copy.deepcopy(present["instance"])
    mutated["targets"][0]["text"] = None
    assert not _is_valid(validators_by_title, present["title"], mutated)
    raw_intent = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-acquisition-intent.v1"
        and case["instance"]["data"]["mode"] == "git_objects"
    )
    mutated = copy.deepcopy(raw_intent["instance"])
    mutated["data"]["bundle"] = None
    assert not _is_valid(validators_by_title, raw_intent["title"], mutated)
    normalized_intent = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-acquisition-intent.v1"
        and case["instance"]["data"]["mode"] == "normalized_text"
    )
    mutated = copy.deepcopy(normalized_intent["instance"])
    mutated["data"]["bundle"] = copy.deepcopy(raw_intent["instance"]["data"]["bundle"])
    assert not _is_valid(validators_by_title, normalized_intent["title"], mutated)
    observation = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-observation.v1"
        and case["instance"]["data"]["mode"] == "git_objects"
        and case["instance"]["data"]["targets"][0]["status"] == "source_text"
    )
    mutated = copy.deepcopy(observation["instance"])
    mutated["data"]["targets"][0]["text"] = None
    assert not _is_valid(validators_by_title, observation["title"], mutated)
    source_only = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-config-evidence.v1"
        and case["instance"]["data"]["format"] == "source-only"
    )
    typed = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-config-evidence.v1"
        and case["instance"]["data"]["format"] in ("json", "toml")
    )
    mutated = copy.deepcopy(source_only["instance"])
    mutated["data"]["result"] = copy.deepcopy(typed["instance"]["data"]["result"])
    assert not _is_valid(validators_by_title, source_only["title"], mutated)
    mutated = copy.deepcopy(typed["instance"])
    mutated["data"]["result"] = None
    assert not _is_valid(validators_by_title, typed["title"], mutated)
    git_objects = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-observe-input.v1"
        and case["instance"]["mode"] == "git_objects"
    )
    mutated = copy.deepcopy(git_objects["instance"])
    mutated["targets"] = copy.deepcopy(present["instance"]["targets"])
    assert not _is_valid(validators_by_title, git_objects["title"], mutated)
    mutated = copy.deepcopy(present["instance"])
    del mutated["targets"]
    assert not _is_valid(validators_by_title, present["title"], mutated)


def test_malformed_typed_config_results(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    typed = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-config-evidence.v1"
        and case["instance"]["data"]["format"] in ("json", "toml")
    )
    mutated = copy.deepcopy(typed["instance"])
    mutated["data"]["result"]["nodes"][0]["kind"] = "float"
    assert not _is_valid(validators_by_title, typed["title"], mutated)
    integer_index = next(
        index
        for index, node in enumerate(typed["instance"]["data"]["result"]["nodes"])
        if node["kind"] == "integer"
    )
    mutated = copy.deepcopy(typed["instance"])
    mutated["data"]["result"]["nodes"][integer_index]["value"] = 1
    assert not _is_valid(validators_by_title, typed["title"], mutated)
    mutated = copy.deepcopy(typed["instance"])
    mutated["data"]["result"]["nodes"][integer_index]["value_span"] = None
    assert not _is_valid(validators_by_title, typed["title"], mutated)
    mutated = copy.deepcopy(typed["instance"])
    del mutated["data"]["result"]["nodes"][0]["path"]
    assert not _is_valid(validators_by_title, typed["title"], mutated)
    mutated = copy.deepcopy(typed["instance"])
    del mutated["data"]["result"]["source"]["body_sha256"]
    assert not _is_valid(validators_by_title, typed["title"], mutated)
    scalar = next(
        node
        for node in typed["instance"]["data"]["result"]["nodes"]
        if node["kind"] in ("integer", "decimal", "string", "boolean", "null")
    )
    mutated = copy.deepcopy(typed["instance"])
    span_index = typed["instance"]["data"]["result"]["nodes"].index(scalar)
    del mutated["data"]["result"]["nodes"][span_index]["value_span"]["byte_start"]
    assert not _is_valid(validators_by_title, typed["title"], mutated)


def test_request_input_omits_limits_and_forbids_profile_hash(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    request = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request-input.v1"
    )
    omitted = copy.deepcopy(request["instance"])
    omitted.pop("limits", None)
    _validate(validators_by_title, request["title"], omitted)
    mutated = copy.deepcopy(omitted)
    mutated["profile_sha256"] = "a" * 64
    assert not _is_valid(validators_by_title, request["title"], mutated)
    saved = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request.v1"
    )
    mutated = copy.deepcopy(saved["instance"])
    del mutated["data"]["profile_sha256"]
    assert not _is_valid(validators_by_title, saved["title"], mutated)
    mutated = copy.deepcopy(saved["instance"])
    del mutated["data"]["limits"]
    assert not _is_valid(validators_by_title, saved["title"], mutated)
    mutated = copy.deepcopy(request["instance"])
    mutated["limits"]["public"]["max_request_bytes"] = 65537
    assert not _is_valid(validators_by_title, request["title"], mutated)


def test_structurally_valid_semantic_forgeries(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    request = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request-input.v1"
        and case["instance"]["object_format"] == "sha1"
    )
    mutated = copy.deepcopy(request["instance"])
    mutated["commit_oid"] = "b" * 64
    _validate(validators_by_title, request["title"], mutated)
    envelope = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request.v1"
    )
    mutated = copy.deepcopy(envelope["instance"])
    mutated["id"] = "ce1:code-proof-request:" + ("a" * 64)
    _validate(validators_by_title, envelope["title"], mutated)
    config = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-config-evidence.v1"
    )
    mutated = copy.deepcopy(config["instance"])
    mutated["data"]["request"]["sha256"] = "c" * 64
    _validate(validators_by_title, config["title"], mutated)
    sha256_request = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-request-input.v1"
        and case["instance"]["object_format"] == "sha256"
    )
    mutated = copy.deepcopy(sha256_request["instance"])
    mutated["commit_oid"] = "a" * 40
    _validate(validators_by_title, sha256_request["title"], mutated)


def test_unicode_source_keys_not_nfc_forced(
    fixture_bundle: dict, validators_by_title: dict[str, Any], registry: Registry
) -> None:
    unicode_case = next(
        case
        for case in fixture_bundle["cases"]
        if "json-unicode-crlf-tabs" in case["name"]
        and case["title"] == "video-paper-wiki.code-config-evidence.v1"
    )
    _validate(validators_by_title, unicode_case["title"], unicode_case["instance"])
    paths = {
        node["path"] for node in unicode_case["instance"]["data"]["result"]["nodes"]
    }
    assert "/备注" in paths
    assert "/学习率" in paths
    pointer_case = next(
        case
        for case in fixture_bundle["cases"]
        if "json-pointer-escaping" in case["name"]
        and case["title"] == "video-paper-wiki.code-config-evidence.v1"
    )
    pointer_paths = {
        node["path"] for node in pointer_case["instance"]["data"]["result"]["nodes"]
    }
    assert "/a~1b" in pointer_paths
    assert "/a~1b/~0key" in pointer_paths
    _validate_def(registry, "json_pointer", "/A\u0301")
    _validate_def(registry, "json_pointer", "/\u00c1")


def test_mixed_config_remains_valid_with_missing_sibling(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    config = next(
        case
        for case in fixture_bundle["cases"]
        if "raw-mixed-incomplete" in case["name"]
        and case["title"] == "video-paper-wiki.code-config-evidence.v1"
    )
    observation = next(
        case
        for case in fixture_bundle["cases"]
        if "raw-mixed-incomplete" in case["name"]
        and case["title"] == "video-paper-wiki.code-proof-observation.v1"
    )
    statuses = {row["status"] for row in observation["instance"]["data"]["targets"]}
    assert "source_text" in statuses
    assert "missing" in statuses
    _validate(validators_by_title, config["title"], config["instance"])
    _validate(validators_by_title, observation["title"], observation["instance"])


def test_schema_does_not_claim_byte_budget_or_oid_format_agreement(
    fixture_bundle: dict, validators_by_title: dict[str, Any]
) -> None:
    observe = next(
        case
        for case in fixture_bundle["cases"]
        if case["title"] == "video-paper-wiki.code-proof-observe-input.v1"
        and case["instance"].get("mode") == "normalized_text"
        and case["instance"]["targets"][0]["status"] == "present"
    )
    mutated = copy.deepcopy(observe["instance"])
    mutated["targets"][0]["text"] = "a" * 16384
    _validate(validators_by_title, observe["title"], mutated)
    mutated["targets"][0]["text"] = "a" * 16385
    assert not _is_valid(validators_by_title, observe["title"], mutated)


def _walk_typed(node: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], Any]]:
    yield path, node
    if isinstance(node, dict):
        for key, child in node.items():
            yield from _walk_typed(child, path + (key,))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _walk_typed(child, path + (index,))

def test_walk_typed_preserves_numeric_string_keys_and_list_indices():
    sample = {'0': [1]}
    items = list(_walk_typed(sample))
    paths = [path for path, _ in items]
    assert paths == [(), ('0',), ('0', 0)]
    assert type(paths[1][0]) is str
    assert type(paths[2][0]) is str
    assert type(paths[2][1]) is int
    assert items[0][1] is sample
    assert items[1][1] == [1]
    assert items[2][1] == 1
    assert type(items[2][1]) is int

_OID40 = 'a' * 40

_HEX64 = 'ab' * 32

_PTR_LAYER = '/' + ('~1' * 256)

_PTR_16416 = _PTR_LAYER * 32

_PTR_16417 = _PTR_16416 + 'a'

def test_repository_identifier_and_embedded_url_boundaries(registry):
    _validate_def(registry, 'repository_input', 'owner/repo')
    _validate_def(registry, 'repository_input', 'Owner/Repo')
    _validate_def(registry, 'repository_input', '.owner./.repo.')
    _validate_def(registry, 'repository_input', '-owner_/-repo_')
    _validate_def(registry, 'repository_input', '.../...')
    _validate_def(registry, 'repository_input', 'owner/.github')
    _validate_def(registry, 'repository_input', 'owner/repo.gitkeep')
    _validate_def(registry, 'repository_input', 'owner/my.gitrepo')
    _validate_def(registry, 'repository_input', 'A' * 100 + '/' + 'B' * 100)
    for bad in (
        './repo',
        '../repo',
        'owner/.',
        'owner/..',
        'owner/repo.git',
        'owner/repo.GIT',
        'owner/repo.Git',
        'owner/repo.gIt',
        'owner/.git',
        'owner/.GIT',
        'owner/repo.git/extra',
        'A' * 101 + '/repo',
        'owner/' + 'B' * 101,
        'owner/repo.gitfoo.git',
        '',
        'owner',
        'owner/',
        '/repo',
        'ow ner/repo',
        'owner/re/po',
    ):
        assert not _def_is_valid(registry, 'repository_input', bad)

    _validate_def(registry, 'repository_saved', 'owner/repo')
    _validate_def(registry, 'repository_saved', '.owner./.repo.')
    _validate_def(registry, 'repository_saved', 'a' * 100 + '/' + 'b' * 100)
    _validate_def(registry, 'repository_saved', 'owner/my.gitrepo')
    for bad in (
        'Owner/repo',
        'owner/Repo',
        './repo',
        'owner/..',
        'owner/repo.git',
        'owner/repo.GIT',
        'owner/.git',
        'A' * 100 + '/' + 'b' * 100,
        'owner/' + 'b' * 101,
    ):
        assert not _def_is_valid(registry, 'repository_saved', bad)

    def commit_url(owner, name, oid=_OID40):
        return f'https://github.com/{owner}/{name}/commit/{oid}'

    def blob_url(owner, name, oid=_OID40):
        return f'https://github.com/{owner}/{name}/blob/{oid}/config.json'

    def raw_url(owner, name, oid=_OID40):
        return f'https://raw.githubusercontent.com/{owner}/{name}/{oid}/config.json'

    url_defs = (
        ('github_commit_url', commit_url),
        ('github_blob_url', blob_url),
        ('github_raw_url', raw_url),
    )
    valid_pairs = (
        ('owner', 'repo'),
        ('.owner.', '.repo.'),
        ('-owner_', '-repo_'),
        ('ow.ner', 're.po'),
        ('owner', '...'),
        ('owner', '.github'),
        ('owner', 'repo.gitkeep'),
        ('owner', 'my.gitrepo'),
        ('a' * 100, 'b' * 100),
    )
    for def_name, make in url_defs:
        for owner, name in valid_pairs:
            _validate_def(registry, def_name, make(owner, name))
        for owner, name in (
            ('.', 'repo'),
            ('..', 'repo'),
            ('owner', '.'),
            ('owner', '..'),
            ('owner', 'repo.git'),
            ('owner', 'repo.GIT'),
            ('owner', 'repo.Git'),
            ('owner', '.git'),
            ('owner', '.GIT'),
            ('Owner', 'repo'),
            ('owner', 'Repo'),
            ('a' * 101, 'repo'),
            ('owner', 'b' * 101),
        ):
            assert not _def_is_valid(registry, def_name, make(owner, name))
        assert not _def_is_valid(registry, def_name, make('owner', 'repo', oid='A' * 40))
        assert not _def_is_valid(registry, def_name, make('owner', 'repo', oid='a' * 39))
        assert not _def_is_valid(registry, def_name, make('owner', 'repo', oid='a' * 41))
        assert not _def_is_valid(registry, def_name, make('owner', 'repo', oid='g' * 40))

def test_json_pointer_length_boundaries(registry):
    assert len(_PTR_16416) == 16416
    assert len(_PTR_16417) == 16417
    _validate_def(registry, 'json_pointer', '')
    _validate_def(registry, 'json_pointer', '/foo')
    _validate_def(registry, 'json_pointer', _PTR_16416)
    assert not _def_is_valid(registry, 'json_pointer', _PTR_16417)

def test_span_column_end_boundary(registry):
    span = {
        'byte_start': 0,
        'byte_end': 262144,
        'codepoint_start': 0,
        'codepoint_end': 262144,
        'line_start': 1,
        'column_start': 1,
        'line_end': 1,
        'column_end': 262145,
        'raw_sha256': _HEX64,
        'snippet_sha256': _HEX64,
    }
    _validate_def(registry, 'span', span)
    span['column_end'] = 262146
    assert not _def_is_valid(registry, 'span', span)

def test_bundle_directory_boundaries(registry):
    _validate_def(registry, 'bundle_directory', '.work/a')
    _validate_def(registry, 'bundle_directory', '.work/foo bar')
    _validate_def(registry, 'bundle_directory', '.work/.git')
    _validate_def(registry, 'bundle_directory', '.work/foo.git')
    _validate_def(registry, 'bundle_directory', '.work/.hidden')
    _validate_def(registry, 'bundle_directory', '.work/' + 'a' * 129)
    _validate_def(registry, 'bundle_directory', '.work/中文目录')
    _validate_def(registry, 'bundle_directory', '.work/foo.bar-baz_qux/a')
    max_ok = '.work/' + 'a' * (4096 - 6)
    assert len(max_ok) == 4096
    _validate_def(registry, 'bundle_directory', max_ok)
    for bad in (
        '.work/',
        '.work',
        'work/a',
        '.WORK/a',
        '.work/a/',
        '.work//a',
        '.work/a//b',
        '.work/.',
        '.work/..',
        '.work/a/.',
        '.work/a/..',
        '.work/a/./b',
        '.work/a/../b',
        '.work\\a',
        '.work/a\\b',
        '.work/\x00',
        '.work/\x01a',
        '.work/a\x1f',
        '.work/\x7f',
        '.work/\x80',
        '.work/\x9f',
        '.work/\u2028',
        '.work/\u2029',
        '.work/a\u2028b',
        '.work/a\u2029b',
        max_ok + 'a',
        '',
        '/.work/a',
        'a' * 7,
    ):
        assert not _def_is_valid(registry, 'bundle_directory', bad)

def test_config_evidence_single_field_result_and_reason(fixture_bundle, validators_by_title):
    title = 'video-paper-wiki.code-config-evidence.v1'
    seen = False
    for case in fixture_bundle['cases']:
        if case['title'] != title:
            continue
        data = case['instance']['data']
        if data.get('format') not in ('json', 'toml'):
            continue
        if type(data.get('result')) is not dict:
            continue
        if data.get('source_only_reason') is not None:
            continue
        seen = True
        mutated = copy.deepcopy(case['instance'])
        mutated['data']['result'] = None
        assert not _is_valid(validators_by_title, title, mutated)
        mutated = copy.deepcopy(case['instance'])
        mutated['data']['source_only_reason'] = 'explicit_source_only'
        assert not _is_valid(validators_by_title, title, mutated)
    assert seen

def test_config_declaration_kind_and_span_malformed(fixture_bundle, validators_by_title):
    title = 'video-paper-wiki.code-config-evidence.v1'
    seen = False
    for case in fixture_bundle['cases']:
        if case['title'] != title:
            continue
        instance = case['instance']
        data = instance.get('data')
        if type(data) is not dict:
            continue
        result = data.get('result')
        if type(result) is not dict:
            continue
        nodes = result.get('nodes')
        if type(nodes) is not list:
            continue
        for ni, node in enumerate(nodes):
            if type(node) is not dict:
                continue
            declarations = node.get('declarations')
            if type(declarations) is not list:
                continue
            for di, decl in enumerate(declarations):
                if type(decl) is not dict:
                    continue
                if 'kind' not in decl or 'span' not in decl:
                    continue
                seen = True
                mutated = copy.deepcopy(instance)
                mutated['data']['result']['nodes'][ni]['declarations'][di]['kind'] = 'not_a_kind'
                assert not _is_valid(validators_by_title, title, mutated)
                mutated = copy.deepcopy(instance)
                mutated['data']['result']['nodes'][ni]['declarations'][di]['span'] = None
                assert not _is_valid(validators_by_title, title, mutated)
                span = decl['span']
                if type(span) is dict and span:
                    field = next(iter(span))
                    mutated = copy.deepcopy(instance)
                    del mutated['data']['result']['nodes'][ni]['declarations'][di]['span'][field]
                    assert not _is_valid(validators_by_title, title, mutated)
    assert seen

def test_git_objects_target_outcome_reason_and_walk(fixture_bundle, validators_by_title, registry):
    title = 'video-paper-wiki.code-proof-observation.v1'
    seen_permitted = False
    seen_missing = False
    seen_walk = False
    permitted_blob = None
    legal_target = None
    for case in fixture_bundle['cases']:
        if case['title'] != title:
            continue
        data = case['instance'].get('data')
        if type(data) is not dict or data.get('mode') != 'git_objects':
            continue
        git_proof = data.get('git_proof')
        if type(git_proof) is not dict:
            continue
        targets = git_proof.get('targets')
        if type(targets) is not list:
            continue
        for ti, target in enumerate(targets):
            if type(target) is not dict:
                continue
            legal_target = target
            mutated = copy.deepcopy(case['instance'])
            mutated['data']['git_proof']['targets'][ti]['outcome'] = 'not_an_outcome'
            assert not _is_valid(validators_by_title, title, mutated)
            mutated = copy.deepcopy(case['instance'])
            mutated['data']['git_proof']['targets'][ti]['reason'] = 'not_a_reason'
            assert not _is_valid(validators_by_title, title, mutated)
            outcome = target.get('outcome')
            if outcome == 'permitted_regular_blob':
                seen_permitted = True
                permitted_blob = copy.deepcopy(target.get('blob'))
                mutated = copy.deepcopy(case['instance'])
                mutated['data']['git_proof']['targets'][ti]['blob'] = None
                assert not _is_valid(validators_by_title, title, mutated)
            elif outcome == 'missing':
                seen_missing = True
                if permitted_blob is not None:
                    mutated = copy.deepcopy(case['instance'])
                    mutated['data']['git_proof']['targets'][ti]['blob'] = copy.deepcopy(permitted_blob)
                    assert not _is_valid(validators_by_title, title, mutated)
            walk = target.get('walk')
            if type(walk) is not list:
                continue
            for wi, step in enumerate(walk):
                if type(step) is not dict:
                    continue
                seen_walk = True
                mutated = copy.deepcopy(case['instance'])
                mutated['data']['git_proof']['targets'][ti]['walk'][wi]['mode'] = 'not_a_mode'
                assert not _is_valid(validators_by_title, title, mutated)
                for field in ('tree_oid', 'name_hex', 'oid', 'mode'):
                    mutated = copy.deepcopy(case['instance'])
                    del mutated['data']['git_proof']['targets'][ti]['walk'][wi][field]
                    assert not _is_valid(validators_by_title, title, mutated)
                for field in ('tree_oid', 'oid'):
                    mutated = copy.deepcopy(case['instance'])
                    mutated['data']['git_proof']['targets'][ti]['walk'][wi][field] = 'g' * 40
                    assert not _is_valid(validators_by_title, title, mutated)
                    mutated = copy.deepcopy(case['instance'])
                    mutated['data']['git_proof']['targets'][ti]['walk'][wi][field] = 'a' * 39
                    assert not _is_valid(validators_by_title, title, mutated)
                mutated = copy.deepcopy(case['instance'])
                mutated['data']['git_proof']['targets'][ti]['walk'][wi]['name_hex'] = 'zz'
                assert not _is_valid(validators_by_title, title, mutated)
                mutated = copy.deepcopy(case['instance'])
                mutated['data']['git_proof']['targets'][ti]['walk'][wi]['extra_walk_field'] = True
                assert not _is_valid(validators_by_title, title, mutated)
    assert seen_permitted
    assert seen_missing
    assert seen_walk
    assert legal_target is not None
    unsafe = copy.deepcopy(legal_target)
    unsafe['outcome'] = 'unsafe'
    unsafe['reason'] = 'symlink'
    unsafe['blob'] = None
    _validate_def(registry, 'git_target', unsafe)
    bad = copy.deepcopy(unsafe)
    bad['outcome'] = 'not_an_outcome'
    assert not _def_is_valid(registry, 'git_target', bad)
    bad = copy.deepcopy(unsafe)
    bad['reason'] = 'not_a_reason'
    assert not _def_is_valid(registry, 'git_target', bad)
    if type(unsafe.get('walk')) is list and unsafe['walk'] and type(unsafe['walk'][0]) is dict:
        bad = copy.deepcopy(unsafe)
        bad['walk'][0]['mode'] = 'not_a_mode'
        assert not _def_is_valid(registry, 'git_target', bad)

def test_saved_document_id_and_reference_hex_syntax(fixture_bundle, validators_by_title):
    seen_id = False
    seen_ref = False
    seen_semantic = False
    for case in fixture_bundle['cases']:
        title = case['title']
        instance = case['instance']
        if type(instance) is not dict:
            continue
        root_id = instance.get('id')
        if type(root_id) is str and root_id.startswith('ce1:'):
            parts = root_id.split(':', 2)
            if len(parts) == 3 and len(parts[2]) == 64:
                seen_id = True
                kind, digest = parts[1], parts[2]
                mutated = copy.deepcopy(instance)
                mutated['id'] = f'ce1:{kind}:{"g" * 64}'
                assert not _is_valid(validators_by_title, title, mutated)
                mutated = copy.deepcopy(instance)
                mutated['id'] = f'ce1:{kind}:{"a" * 63}'
                assert not _is_valid(validators_by_title, title, mutated)
                mutated = copy.deepcopy(instance)
                mutated['id'] = f'ce1:{kind}:{"a" * 65}'
                assert not _is_valid(validators_by_title, title, mutated)
                mutated = copy.deepcopy(instance)
                mutated['id'] = f'ce1:{kind}:{digest.upper()}'
                assert not _is_valid(validators_by_title, title, mutated)
                alt = ('0' if digest[0] != '0' else '1') + digest[1:]
                mutated = copy.deepcopy(instance)
                mutated['id'] = f'ce1:{kind}:{alt}'
                _validate(validators_by_title, title, mutated)
                seen_semantic = True
        for path, node in _walk_typed(instance):
            if type(node) is not dict or 'id' not in node or 'sha256' not in node:
                continue
            sha = node['sha256']
            ident = node['id']
            if type(sha) is not str:
                continue
            seen_ref = True
            mutated = copy.deepcopy(instance)
            _set_path(mutated, path + ('sha256',), 'g' * 64)
            assert not _is_valid(validators_by_title, title, mutated)
            mutated = copy.deepcopy(instance)
            _set_path(mutated, path + ('sha256',), 'a' * 63)
            assert not _is_valid(validators_by_title, title, mutated)
            mutated = copy.deepcopy(instance)
            _set_path(mutated, path + ('sha256',), 'a' * 65)
            assert not _is_valid(validators_by_title, title, mutated)
            if len(sha) == 64 and sha.lower() == sha and all(c in '0123456789abcdef' for c in sha):
                alt = ('0' if sha[0] != '0' else '1') + sha[1:]
                mutated = copy.deepcopy(instance)
                _set_path(mutated, path + ('sha256',), alt)
                _validate(validators_by_title, title, mutated)
                seen_semantic = True
            if type(ident) is str and ident.startswith('ce1:'):
                parts = ident.split(':', 2)
                if len(parts) == 3:
                    mutated = copy.deepcopy(instance)
                    _set_path(mutated, path + ('id',), f'ce1:{parts[1]}:{"G" * 64}')
                    assert not _is_valid(validators_by_title, title, mutated)
    assert seen_id
    assert seen_ref
    assert seen_semantic
