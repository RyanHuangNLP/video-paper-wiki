"""Read-only independent R12 probes against an externally frozen resource root."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, validators
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource


FILENAMES = (
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
COMMON = "https://video-paper-wiki.dev/schemas/" + FILENAMES[0]


def ref(path):
    raw = path.read_bytes()
    return {"path": str(path), "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def deny(uri):
    raise NoSuchResource(ref=uri)


def leaf_errors(error):
    if error.context:
        for child in error.context:
            yield from leaf_errors(child)
    else:
        yield {"validator": error.validator, "instance_path": list(error.absolute_path),
               "schema_path": list(error.absolute_schema_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources-root", type=Path, required=True)
    parser.add_argument("--oracle-directory", type=Path, required=True)
    args = parser.parse_args()
    assert args.resources_root.is_dir() and not args.resources_root.is_symlink()
    resources = []
    pins = []
    for filename in FILENAMES:
        path = args.resources_root / "schemas" / filename
        assert path.is_file() and not path.is_symlink()
        pins.append(ref(path))
        value = json.loads(path.read_bytes())
        resources.append((value["$id"], Resource.from_contents(value)))
    registry = Registry(retrieve=deny).with_resources(resources)
    strict = validators.extend(Draft202012Validator, type_checker=
        Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda checker, value: type(value) is int))
    checks = []

    def check(identifier, definition, instance, expected, basis):
        validator = strict({"$ref": COMMON + "#/$defs/" + definition}, registry=registry)
        errors = list(validator.iter_errors(instance))
        leaves = [item for error in errors for item in leaf_errors(error)]
        checks.append({"id": identifier, "definition": definition, "expected_valid": expected,
                       "actual_valid": not errors, "pass": (not errors) == expected,
                       "basis": basis, "error_leaf_count": len(leaves), "error_leaves_first_8": leaves[:8]})

    for definition in ("repository_input", "repository_saved"):
        for value in ("./repo", "../repo", "owner/.", "owner/..", "owner/name.git"):
            check(definition + ":" + value, definition, value, False,
                  "R9 excludes exact dot/dot-dot owner and repository components and a repository .git suffix.")
        for value in ("_owner/.github", "-/_repo", "o/r"):
            check(definition + ":" + value, definition, value, True,
                  "R9 permits leading dot/underscore/hyphen and one-character bounded components.")
    check("uppercase-input", "repository_input", "OWNER/Repo", True,
          "Ordinary R9 input permits ASCII case; request preparation lowercases it once.")
    check("uppercase-saved", "repository_saved", "OWNER/Repo", False,
          "Saved R9 repository spelling is lowercase.")
    oid = "a" * 40
    for definition, prefix, suffix in (
        ("github_commit_url", "https://github.com/", "/commit/" + oid),
        ("github_blob_url", "https://github.com/", "/blob/" + oid + "/config.json"),
        ("github_raw_url", "https://raw.githubusercontent.com/", "/" + oid + "/config.json"),
    ):
        check(definition + ":valid", definition, prefix + "owner/repo" + suffix, True,
              "R7 exact permitted host locator syntax with a valid R9 origin.")
        for repository in ("./repo", "../repo", "owner/name.git", "owner/.", "owner/.."):
            check(definition + ":" + repository, definition, prefix + repository + suffix, False,
                  "R7 locator embeds the same R9-bounded repository grammar; slash suffixes cannot disable a component exclusion.")
    check("minimum-bundle-directory", "bundle_directory", ".work/a", True,
          "R3 allows canonical relative raw bundle roots below .work; this one-character directory is disjoint from a separate batch output.")
    check("ordinary-bundle-directory", "bundle_directory", ".work/raw-bundle", True,
          "Ordinary valid canonical relative input bundle directory.")
    for value in (".work/input.v1", ".work/_input", ".work/-input", ".work/input_", ".work/input-", ".work/.input", ".work/.git", ".work/输入/源 文件", ".work/" + "a" * 129):
        check("bundle-canonical:" + value, "bundle_directory", value, True,
              "R2 Architect clarification: input directory components are not output batch identifiers.")
    for value in (".work", ".work/", ".work//a", ".work/a/", ".work/./a", ".work/a/../b", ".work/a\\b", ".work/a\n", ".work/a\u2028"):
        check("bundle-noncanonical:" + repr(value), "bundle_directory", value, False,
              "R2 canonical input spelling excludes aliases, empty/dot components, backslash and controls.")
    check("pointer-maximum-direct", "json_pointer", ("/" + "~1" * 256) * 32, True,
          "32 times (one separator plus 512 escaped characters) equals 16416.")
    check("pointer-overmaximum-direct", "json_pointer", ("/" + "~1" * 256) * 32 + "x", False,
          "16417 exceeds the maximum reachable accepted CONFIG pointer bound.")
    oracles = []
    for name in ("architect-config-pointer-boundary-oracle-r1.json", "architect-config-column-boundary-oracle-r1.json"):
        path = args.oracle_directory / name
        oracles.append(ref(path))
        value = json.loads(path.read_bytes())
        assert value["source_head"] == "4ab1830939cd41981983909763434d5612df6070"
        check(value["case"], "config_result", value["result"], True,
              "Actual complete accepted CONFIG kernel output under all fixed profile maxima; resource schemas must admit it.")
    assert pins == [ref(args.resources_root / "schemas" / name) for name in FILENAMES]
    result = {"schema": "full-todo.code-resource-independent-boundary-probes.v2",
              "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "checks": checks, "check_count": len(checks),
              "mismatch_count": sum(not row["pass"] for row in checks),
              "resource_pins_before_and_after_equal": pins, "oracle_pins": oracles,
              "scope": "Schema-only independent probes; no public runtime, saved-byte identity, filesystem workflow, or resource acceptance claim."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["mismatch_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
