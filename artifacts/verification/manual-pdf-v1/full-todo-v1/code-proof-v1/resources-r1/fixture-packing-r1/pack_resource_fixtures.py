#!/usr/bin/env python3
"""Pack accepted CODE resource examples into the closed fixture transport.

The packer reads only manifest-listed JSON files from the accepted R3 base and
typed R2 fixture directories.  It validates every listed size/hash and the
complete data file set, then writes one fresh JSON bundle.  Raw Git bodies may
be read solely for their manifest pin check; they are never parsed as cases or
included in the output.  No product modules, schemas, providers, Git commands,
or ce1 re-sealing helpers are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


FIXTURE_SCHEMA = "video-paper-wiki.code-proof-resource-fixtures.v1"
BASE_MANIFEST_SCHEMA = "video-paper-wiki.code-proof-resource-fixture-manifest.v1"
TYPED_MANIFEST_SCHEMA = "video-paper-wiki.code-proof-typed-fixture-manifest.v1"
REQUEST_INPUT_TITLE = "video-paper-wiki.code-proof-request-input.v1"
OBSERVE_INPUT_TITLE = "video-paper-wiki.code-proof-observe-input.v1"
COMMAND_RESULT_TITLE = "video-paper-wiki.code-proof-command-result.v1"
PROFILE_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_BASE_JSON_CASES = 82
EXPECTED_TYPED_JSON_CASES = 182
ENVELOPE_KINDS = {
    "request": "code-proof-request",
    "bundle": "code-git-bundle",
    "intent": "code-acquisition-intent",
    "observation": "code-proof-observation",
    "config": "code-config-evidence",
    "handoff": "code-source-handoff",
}
ENVELOPE_SCHEMAS = {f"video-paper-wiki.{kind}.v1" for kind in ENVELOPE_KINDS.values()}


class PackingError(ValueError):
    """Raised when an input pin or closed fixture rule is violated."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject_constant(value: str) -> None:
    raise PackingError(f"non-finite JSON constant is forbidden: {value}")


def pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackingError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_bytes(),
            object_pairs_hook=pairs_no_duplicates,
            parse_constant=reject_constant,
        )
    except PackingError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackingError(f"invalid JSON input: {path}") from exc


def check_sha(value: object, pointer: str) -> str:
    if type(value) is not str or PROFILE_RE.fullmatch(value) is None:
        raise PackingError(f"{pointer} must be 64 lowercase hex characters")
    return value


def safe_relative(value: object, pointer: str) -> str:
    if type(value) is not str or not value or "\\" in value:
        raise PackingError(f"{pointer} must be a nonempty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise PackingError(f"{pointer} is not a canonical relative path")
    return value


def regular_file(root: Path, relative: str) -> Path:
    safe_relative(relative, "/file/path")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise PackingError(f"manifest-listed file is not a regular file: {relative}")
    return path


def verify_file_pin(root: Path, entry: dict[str, Any]) -> tuple[str, bytes]:
    if type(entry) is not dict:
        raise PackingError("file manifest entry must be an object")
    relative = safe_relative(entry.get("path"), "/file/path")
    if type(entry.get("size_bytes")) is not int or entry["size_bytes"] < 0:
        raise PackingError(f"invalid size pin for {relative}")
    expected_hash = check_sha(entry.get("sha256"), f"/files/{relative}/sha256")
    path = regular_file(root, relative)
    raw = path.read_bytes()
    if len(raw) != entry["size_bytes"] or digest(raw) != expected_hash:
        raise PackingError(f"file pin mismatch: {relative}")
    return relative, raw


def iter_case_file_entries(manifest: dict[str, Any]) -> Iterable[dict[str, Any]]:
    cases = manifest.get("cases")
    if type(cases) is dict:
        values = cases.values()
    elif type(cases) is list:
        values = cases
    else:
        raise PackingError("manifest cases must be an object or array")
    for case in values:
        if type(case) is not dict:
            raise PackingError("manifest case must be an object")
        found = False
        for key in ("files", "saved_files", "saved_and_success_files"):
            value = case.get(key)
            if value is None:
                continue
            if type(value) is not list:
                raise PackingError(f"manifest {key} must be an array")
            found = True
            yield from value
        if not found:
            raise PackingError("manifest case has no file list")
    ordinary = manifest.get("ordinary_inputs", [])
    if type(ordinary) is not list:
        raise PackingError("manifest ordinary_inputs must be an array")
    yield from ordinary


def expected_data_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for family in ("saved", "success-data", "inputs"):
        family_root = root / family
        if not family_root.exists():
            continue
        for path in family_root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                continue
            if path.is_symlink() or not path.is_file():
                raise PackingError(f"fixture data entry is not a regular file: {relative}")
            paths.add(relative)
    return paths


def validate_manifest_and_collect(
    *,
    root: Path,
    expected_manifest_sha256: str,
    expected_profile_sha256: str,
    prefix: str,
    expected_manifest_schema: str,
    expected_json_count: int,
) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise PackingError(f"fixture root is not a directory: {root}")
    manifest_path = regular_file(root, "manifest.json")
    manifest_raw = manifest_path.read_bytes()
    if digest(manifest_raw) != expected_manifest_sha256:
        raise PackingError(f"manifest hash mismatch: {root}")
    manifest = load_json(manifest_path)
    if type(manifest) is not dict or manifest.get("schema") != expected_manifest_schema:
        raise PackingError(f"unexpected fixture manifest schema: {root}")
    if check_sha(manifest.get("profile_sha256"), "/profile_sha256") != expected_profile_sha256:
        raise PackingError(f"profile hash mismatch in manifest: {root}")
    entries: list[tuple[str, dict[str, Any], bytes]] = []
    seen_paths: set[str] = set()
    for entry in iter_case_file_entries(manifest):
        relative, raw = verify_file_pin(root, entry)
        if relative in seen_paths:
            raise PackingError(f"duplicate manifest file pin: {relative}")
        seen_paths.add(relative)
        if relative == "manifest.json":
            raise PackingError("manifest cannot be a positive fixture instance")
        if relative.endswith(".body"):
            continue
        if not relative.endswith(".json") or not relative.startswith(("saved/", "success-data/", "inputs/")):
            raise PackingError(f"unexpected positive fixture path: {relative}")
        entries.append((relative, entry, raw))
    actual_data_paths = expected_data_paths(root)
    if actual_data_paths != seen_paths:
        missing = sorted(seen_paths - actual_data_paths)
        extra = sorted(actual_data_paths - seen_paths)
        raise PackingError(f"complete data file pin mismatch missing={missing} extra={extra}")
    if len(entries) != expected_json_count:
        raise PackingError(f"unexpected JSON case count for {prefix}: {len(entries)} != {expected_json_count}")
    result: list[dict[str, Any]] = []
    titles: set[str] = set()
    for relative, entry, raw in entries:
        instance = load_json(root / relative)
        if type(instance) is not dict:
            raise PackingError(f"fixture instance must be an object: {relative}")
        if relative.startswith("saved/"):
            kind = entry.get("kind")
            expected_kind = ENVELOPE_KINDS.get(kind) if type(kind) is str else None
            if expected_kind is None:
                raise PackingError(f"unknown saved envelope kind for {relative}")
            if instance.get("kind") != expected_kind or instance.get("schema") not in ENVELOPE_SCHEMAS:
                raise PackingError(f"saved envelope kind/schema mismatch: {relative}")
            title = instance.get("schema")
            if type(title) is not str:
                raise PackingError(f"saved envelope has no schema title: {relative}")
            titles.add(title)
        elif relative.startswith("inputs/"):
            basename = PurePosixPath(relative).name
            if "request-input" in basename:
                title = REQUEST_INPUT_TITLE
                if "profile_sha256" in instance:
                    raise PackingError(f"ordinary request unexpectedly carries profile hash: {relative}")
            elif "observe-input" in basename:
                title = OBSERVE_INPUT_TITLE
            else:
                raise PackingError(f"unknown ordinary input path: {relative}")
        elif relative.startswith("success-data/"):
            title = COMMAND_RESULT_TITLE
        else:
            raise PackingError(f"unexpected fixture path: {relative}")
        if not all(ord(char) < 128 for char in f"{prefix}/{relative}"):
            raise PackingError(f"case name is not ASCII: {relative}")
        result.append({"name": f"{prefix}/{relative}", "title": title, "instance": instance})
    if titles != ENVELOPE_SCHEMAS:
        raise PackingError(f"saved envelope inventory mismatch for {prefix}: {sorted(titles)}")
    saved_requests = [
        item for item in result
        if item["name"].startswith(f"{prefix}/saved/") and item["instance"].get("kind") == "code-proof-request"
    ]
    if not saved_requests:
        raise PackingError(f"no saved request envelopes found for {prefix}")
    for item in saved_requests:
        data = item["instance"].get("data")
        if type(data) is not dict or data.get("profile_sha256") != expected_profile_sha256:
            raise PackingError(f"saved request profile hash mismatch: {item['name']}")
    return result


def write_bundle(output: Path, profile_sha256: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    if output.exists():
        raise PackingError(f"refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    cases.sort(key=lambda item: item["name"])
    if [item["name"] for item in cases] != sorted({item["name"] for item in cases}):
        raise PackingError("case names are not unique ASCII sorted names")
    bundle = {"schema": FIXTURE_SCHEMA, "profile_sha256": profile_sha256, "cases": cases}
    raw = (json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    output.write_bytes(raw)
    os.chmod(output, 0o600)
    return {"path": output.as_posix(), "size_bytes": len(raw), "sha256": digest(raw), "case_count": len(cases)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--typed-dir", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    parser.add_argument("--base-manifest-sha256", required=True)
    parser.add_argument("--typed-manifest-sha256", required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    args = parser.parse_args()
    profile = check_sha(args.profile_sha256, "--profile-sha256")
    base_pin = check_sha(args.base_manifest_sha256, "--base-manifest-sha256")
    typed_pin = check_sha(args.typed_manifest_sha256, "--typed-manifest-sha256")
    base_cases = validate_manifest_and_collect(
        root=args.base_dir.resolve(),
        expected_manifest_sha256=base_pin,
        expected_profile_sha256=profile,
        prefix="base",
        expected_manifest_schema=BASE_MANIFEST_SCHEMA,
        expected_json_count=EXPECTED_BASE_JSON_CASES,
    )
    typed_cases = validate_manifest_and_collect(
        root=args.typed_dir.resolve(),
        expected_manifest_sha256=typed_pin,
        expected_profile_sha256=profile,
        prefix="typed",
        expected_manifest_schema=TYPED_MANIFEST_SCHEMA,
        expected_json_count=EXPECTED_TYPED_JSON_CASES,
    )
    result = write_bundle(args.output_file.resolve(), profile, base_cases + typed_cases)
    result.update({"profile_sha256": profile, "base_json_cases": len(base_cases), "typed_json_cases": len(typed_cases)})
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
