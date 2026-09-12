"""Independent checks for the repaired input directory and preserved output paths."""
import argparse
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-root", type=Path, required=True)
    parser.add_argument("--new-root", type=Path, required=True)
    args = parser.parse_args()
    relative = "schemas/video-paper-wiki.code-proof-common.v1.schema.json"
    old = json.loads((args.old_root / relative).read_bytes())
    new = json.loads((args.new_root / relative).read_bytes())
    preserved = ("stored_body_path", "stored_derived_path", "batch_id")
    for key in preserved:
        assert old["$defs"][key] == new["$defs"][key], key
    changed = [key for key in old["$defs"] if old["$defs"][key] != new["$defs"][key]]
    assert set(changed) == {
        "repository_input", "repository_saved", "json_pointer", "hosting_assertion",
        "github_blob_url", "github_raw_url", "github_commit_url", "acquisition_locator",
        "span", "bundle_directory",
    }
    results = []
    for name, definition, value, expected in (
        ("directory-4096", "bundle_directory", ".work/" + "a" * 4090, True),
        ("directory-4097", "bundle_directory", ".work/" + "a" * 4091, False),
        ("directory-c1-control", "bundle_directory", ".work/a\u0085b", False),
        ("directory-del-control", "bundle_directory", ".work/a\x7fb", False),
        ("directory-line-separator", "bundle_directory", ".work/a\u2028b", False),
        ("directory-paragraph-separator", "bundle_directory", ".work/a\u2029b", False),
    ):
        validator = Draft202012Validator(new["$defs"][definition])
        actual = validator.is_valid(value)
        assert actual is expected, name
        results.append({"name": name, "expected": expected, "actual": actual})
    span = copy.deepcopy(new["$defs"]["span"]["properties"])
    assert span["column_end"]["maximum"] == 262145
    for field in ("byte_start", "byte_end", "codepoint_start", "codepoint_end",
                  "line_start", "line_end", "column_start"):
        assert span[field] == old["$defs"]["span"]["properties"][field], field
    print(json.dumps({"decision": "PASS", "checks": results,
                      "preserved_definitions": list(preserved),
                      "changed_definitions": changed, "other_span_bounds_preserved": True},
                     indent=2))


if __name__ == "__main__":
    main()
