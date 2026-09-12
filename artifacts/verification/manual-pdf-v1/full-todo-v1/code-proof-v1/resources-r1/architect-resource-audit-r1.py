"""Independent, read-only R12 resource acceptance checks. No product writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urldefrag

from jsonschema import Draft202012Validator, validators
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource


TITLES = tuple("video-paper-wiki." + kind + ".v1" for kind in (
    "code-proof-common", "code-proof-request-input", "code-proof-observe-input",
    "code-proof-command-result", "code-proof-request", "code-git-bundle",
    "code-acquisition-intent", "code-proof-observation", "code-config-evidence",
    "code-source-handoff",
))
FILENAMES = tuple(title + ".schema.json" for title in TITLES)
ORIGIN = "https://video-paper-wiki.dev/schemas/"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
PROFILE_PATH = "src/video_paper_wiki/profiles/code-proof-v1.json"
LIMITS = {
    "git": {
        "max_targets": 32, "max_objects": 2048, "max_tree_entries": 32768,
        "max_object_bytes": 8388608, "max_total_object_bytes": 33554432,
    },
    "config": {
        "max_source_bytes": 262144, "max_depth": 32, "max_nodes": 1024,
        "max_array_items": 256, "max_object_keys": 1024, "max_key_bytes": 256,
        "max_string_codepoints": 16384, "max_scalars": 512,
        "max_numeric_lexeme_bytes": 128, "max_numeric_coefficient_digits": 64,
        "max_numeric_abs_exponent": 128, "max_numeric_canonical_bytes": 256,
        "max_declarations": 4096,
    },
    "public": {
        "max_bundle_bytes": 1048576, "max_inline_normalized_bytes": 16384,
        "max_request_bytes": 65536, "max_intent_bytes": 1048576,
        "max_observation_bytes": 2097152, "max_config_document_bytes": 2097152,
        "max_handoff_bytes": 131072, "max_output_peak_bytes": 134217728,
    },
}
ADMISSION = {"max_request_input_bytes": 65536, "max_observe_input_bytes": 1048576}


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def reject_number(value):
    raise ValueError("Noninteger resource number: " + value)


def decode(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_float=reject_number, parse_constant=reject_number)


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def nodes(value, pointer=""):
    yield pointer, value
    if type(value) is dict:
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from nodes(child, pointer + "/" + escaped)
    elif type(value) is list:
        for index, child in enumerate(value):
            yield from nodes(child, pointer + "/" + str(index))


def pointer_lookup(document, fragment):
    assert fragment.startswith("/"), fragment
    current = document
    for encoded in fragment[1:].split("/"):
        index = 0
        while index < len(encoded):
            if encoded[index] == "~":
                assert index + 1 < len(encoded) and encoded[index + 1] in "01", fragment
                index += 1
            index += 1
        key = encoded.replace("~1", "/").replace("~0", "~")
        if type(current) is list:
            assert key == "0" or (key.isascii() and key.isdigit() and not key.startswith("0")), fragment
            current = current[int(key)]
        else:
            assert type(current) is dict, fragment
            current = current[key]
    return current


def deny_retrieval(uri):
    raise NoSuchResource(ref=uri)


def run(root, fixture):
    expected_paths = {"schemas/" + filename for filename in FILENAMES} | {PROFILE_PATH}
    expected_dirs = {str(parent) for path in expected_paths for parent in Path(path).parents if str(parent) != "."}
    actual_paths, actual_dirs = set(), set()
    for path in root.rglob("*"):
        assert not path.is_symlink(), str(path)
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            actual_dirs.add(relative)
        else:
            assert path.is_file(), relative
            actual_paths.add(relative)
    assert actual_paths == expected_paths, (actual_paths, expected_paths)
    assert actual_dirs == expected_dirs, (actual_dirs, expected_dirs)
    documents, byte_map, manifest = {}, {}, []
    for title, filename in zip(TITLES, FILENAMES):
        relative = "schemas/" + filename
        raw = (root / relative).read_bytes()
        value = decode(raw)
        assert raw == encode(value), relative
        assert value["$schema"] == DIALECT and value["$id"] == ORIGIN + filename
        assert value["title"] == title
        Draft202012Validator.check_schema(value)
        documents[value["$id"]] = value
        byte_map[filename] = raw
        manifest.append({"path": relative, "size_bytes": len(raw), "sha256": sha(raw)})
    references = 0
    for uri, document in documents.items():
        for pointer, value in nodes(document):
            if type(value) is not dict:
                continue
            assert not {"$anchor", "$dynamicAnchor", "$dynamicRef", "$recursiveRef", "$recursiveAnchor"}.intersection(value), (uri, pointer)
            if pointer:
                assert "$id" not in value, (uri, pointer)
            if "$ref" in value:
                ref = value["$ref"]
                assert type(ref) is str
                address, fragment = urldefrag(ref)
                if not address:
                    assert ref.startswith("#/"), ref
                    target = document
                else:
                    assert address in documents, ref
                    target = documents[address]
                if fragment:
                    pointer_lookup(target, fragment)
                else:
                    assert "#" not in ref, ref
                references += 1
    registry = Registry(retrieve=deny_retrieval).with_resources(
        (uri, Resource.from_contents(value)) for uri, value in documents.items()
    )
    strict = validators.extend(Draft202012Validator, type_checker=
        Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda checker, value: type(value) is int))
    for invalid in (True, 1.0, type("IntegerSubclass", (int,), {})(1)):
        assert not strict({"type": "integer"}).is_valid(invalid)
    profile_raw = (root / PROFILE_PATH).read_bytes()
    profile = decode(profile_raw)
    assert profile_raw == encode(profile)
    expected_inventory = [
        {"title": filename.removesuffix(".schema.json"), "filename": filename,
         "size_bytes": len(byte_map[filename]), "sha256": sha(byte_map[filename])}
        for filename in sorted(FILENAMES)
    ]
    assert profile == {
        "schema": "video-paper-wiki.code-proof-profile.v1", "profile": "code-proof-v1",
        "revision": 1, "limits": LIMITS, "admission": ADMISSION, "schemas": expected_inventory,
    }
    assert type(profile["revision"]) is int
    for group in profile["limits"].values():
        assert all(type(value) is int for value in group.values())
    assert all(type(value) is int for value in profile["admission"].values())
    for row in profile["schemas"]:
        assert type(row["size_bytes"]) is int and row["size_bytes"] > 0
    common_uri = ORIGIN + FILENAMES[0]
    strict({"$ref": common_uri + "#/$defs/profile"}, registry=registry).validate(profile)
    manifest.append({"path": PROFILE_PATH, "size_bytes": len(profile_raw), "sha256": sha(profile_raw)})
    case_count = 0
    if fixture is not None:
        bundle = decode(fixture.read_bytes())
        assert set(bundle) == {"schema", "profile_sha256", "cases"}
        assert bundle["schema"] == "video-paper-wiki.code-proof-resource-fixtures.v1"
        assert bundle["profile_sha256"] == sha(profile_raw)
        names = [case["name"] for case in bundle["cases"]]
        assert len(names) == len(set(names)) == 264
        assert names == sorted(names) and all(type(name) is str and name.isascii() for name in names)
        assert {case["title"] for case in bundle["cases"]} == set(TITLES[1:])
        for case in bundle["cases"]:
            assert set(case) == {"name", "title", "instance"}
            validator = strict(documents[ORIGIN + case["title"] + ".schema.json"], registry=registry)
            errors = list(validator.iter_errors(case["instance"]))
            assert not errors, (case["name"], [(list(error.path), error.message) for error in errors[:3]])
            case_count += 1
    return {"decision": "PASSED_RESOURCE_BYTES_REFERENCES_PROFILE" + ("_AND_264_POSITIVES" if fixture else ""),
            "resource_root": str(root), "resolved_references": references,
            "fixture_cases": case_count, "profile_sha256": sha(profile_raw),
            "manifest": sorted(manifest, key=lambda row: row["path"]),
            "limits": "Does not establish all nested shape negatives or later public semantic/I/O behavior."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources-root", required=True, type=Path)
    parser.add_argument("--fixture", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.resources_root, arguments.fixture), ensure_ascii=False, indent=2))
