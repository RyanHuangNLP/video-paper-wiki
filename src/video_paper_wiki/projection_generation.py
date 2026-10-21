"""Pure generation-material validation and fingerprinting."""
from __future__ import annotations

import hashlib
import json

from jsonschema import Draft202012Validator, validators

from video_paper_wiki.contracts import ContractError, _registry, schema_by_title
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.projection_input import validate_projection_inventory
from video_paper_wiki.projection_runtime import _preflight
from video_paper_wiki.resources import read_projection_resource_bytes

_TITLE = "video-paper-wiki.projection-generation.v1"
_PROFILE_NAME = "base-catalog-v1.generation-profile.json"
_PROFILE_SHA = "7b4e95e7b1ad89e492bab98486de359fe125854215fd2de5e7aaab3f4b8e333a"
_SCHEMA_NAME = "video-paper-wiki.projection-generation.v1.schema.json"
_SCHEMA_SHA = "38e962a184b9048932103c0b710f98f41e2ed2686c4079628870e8fe98a4c255"
_TYPES = Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda _c, v: type(v) is int)
_Validator = validators.extend(Draft202012Validator, type_checker=_TYPES)


def _fail(code: str, pointer: str, message: str) -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _preflight_generation(value: object) -> None:
    try:
        _preflight(value)
    except ContractError as exc:
        if exc.code == "PROJECTION_LIMIT_EXCEEDED":
            raise
        raise ContractError("PROJECTION_GENERATION_INVALID", "invalid generation value", exc.details) from None


def _resource(kind: str, name: str, digest: str | None = None) -> bytes:
    payload = read_projection_resource_bytes(kind, name)
    if payload is None or (digest is not None and hashlib.sha256(payload).hexdigest() != digest):
        _fail("CATALOG_RESOURCE_MISMATCH", "", "immutable projection resource mismatch")
    return payload


def _profile() -> dict:
    raw = _resource("catalog", _PROFILE_NAME, _PROFILE_SHA)
    _resource("schema", _SCHEMA_NAME, _SCHEMA_SHA)
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        _fail("CATALOG_RESOURCE_MISMATCH", "", "immutable projection profile is invalid")
    if type(value) is not dict:
        _fail("CATALOG_RESOURCE_MISMATCH", "", "immutable projection profile is invalid")
    return value


def _paths(items: list) -> list[str]:
    return [item["path"] for item in items]


def _validated(material: object, *, preflight: bool = True) -> dict:
    if preflight:
        _preflight_generation(material)
    profile = _profile()
    validator = _Validator(schema_by_title(_TITLE), registry=_registry()[0])
    shape_value = material
    if type(material) is dict and "inventory" in material:
        shape_value = dict(material)
        shape_value["inventory"] = {
            "schema": "video-paper-wiki.projection-input.v1",
            "entries": [
                {"path": "taxonomy/v1.json", "kind": "taxonomy", "sha256": "0" * 64, "size_bytes": 0},
                {"path": "wiki/meta/ledgers/claim-ledger.json", "kind": "claim-ledger", "sha256": "0" * 64, "size_bytes": 0},
                {"path": "wiki/meta/ledgers/source-ledger.json", "kind": "source-ledger", "sha256": "0" * 64, "size_bytes": 0},
            ],
        }
    error = next(iter(validator.iter_errors(shape_value)), None)
    if error is not None:
        pointer = "".join("/" + str(x).replace("~", "~0").replace("/", "~1") for x in error.absolute_path)
        _fail("PROJECTION_GENERATION_INVALID", pointer, "generation material shape is invalid")
    assert type(material) is dict
    expected_runtime = profile["runtime"]
    runtime = material["runtime"]
    pair = {"python_version": runtime["python_version"], "unicode_version": runtime["unicode_version"]}
    if (runtime["python_implementation"] != expected_runtime["python_implementation"]
            or pair not in expected_runtime["accepted_exact_pairs"]
            or runtime["prefix_mode"] != expected_runtime["prefix_mode"]
            or runtime["chunk_profile"] != expected_runtime["chunk_profile"]
            or runtime["bm25_profile"] != expected_runtime["bm25_profile"]):
        _fail("PROJECTION_GENERATION_INVALID", "/runtime", "runtime tuple is not admitted")
    if material["dependencies"]["profile"] != profile["dependencies"]["profile"]:
        _fail("PROJECTION_GENERATION_INVALID", "/dependencies/profile", "format profile differs")
    accepted = next((x for x in profile["dependencies"]["accepted_exact_sets"]
                     if x["python_version"] == runtime["python_version"]), None)
    if accepted is None or material["dependencies"]["distributions"] != accepted["distributions"]:
        _fail("PROJECTION_GENERATION_INVALID", "/dependencies/distributions", "dependency set differs")
    if (material["implementation"]["package_version"] != profile["implementation"]["package_version"]
            or _paths(material["implementation"]["files"]) != profile["implementation"]["files"]):
        _fail("PROJECTION_GENERATION_INVALID", "/implementation", "implementation inventory differs")
    if _paths(material["resources"]["files"]) != profile["resources"]["files"]:
        _fail("PROJECTION_GENERATION_INVALID", "/resources/files", "resource inventory differs")
    upstream = material["upstream"]
    if (upstream["commit"] != profile["upstream"]["commit"]
            or upstream["version"] != profile["upstream"]["version"]
            or _paths(upstream["files"]) != profile["upstream"]["files"]):
        _fail("PROJECTION_GENERATION_INVALID", "/upstream", "upstream inventory differs")
    try:
        validate_projection_inventory(material["inventory"])
    except ContractError as exc:
        if exc.code == "PROJECTION_LIMIT_EXCEEDED":
            raise
        details = dict(exc.details)
        pointer = details.get("instance_pointer", "")
        details["instance_pointer"] = "/inventory" + pointer
        raise ContractError("PROJECTION_GENERATION_INVALID", "embedded inventory is invalid", details) from None
    taxonomy = next((x for x in material["inventory"]["entries"] if x["kind"] == "taxonomy"), None)
    taxonomy_resource = next((x for x in material["resources"]["files"]
                              if x["path"] == profile["bindings"]["taxonomy_resource_path"]), None)
    if taxonomy is None or taxonomy_resource is None or taxonomy["sha256"] != taxonomy_resource["sha256"]:
        _fail("PROJECTION_GENERATION_INVALID", "/resources/files", "taxonomy input/resource digest differs")
    return material


def projection_generation_sha256(material: object) -> str:
    value = _validated(material)
    try:
        raw = canonicalize(value)
    except Exception as exc:  # preflight and schema make this an invariant failure
        raise RuntimeError("validated generation material is not canonicalizable") from exc
    return hashlib.sha256(raw).hexdigest()


def projection_is_stale(*, current: object, stored: object) -> bool:
    current_hash = projection_generation_sha256(current)
    if stored is None:
        return True
    return current_hash != projection_generation_sha256(stored)


__all__ = ["projection_generation_sha256", "projection_is_stale"]
