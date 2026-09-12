"""Apply one frozen declarative Grok repair to fresh evidence copies only."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


BASES = {
    "generate_code_proof_resources.py": "df798bf22b08d385c1b2de712d950e7978f5d89836486beb703d8bb1d8e749b2",
    "test_code_proof_resources.py": "19c8d6355bfe8db22c37ec7abce96409bf9d8cef989443ef560ece1af1def74f",
}
BEGIN = "BEGIN_PATCH code-resource-r2"
END = "END_PATCH code-resource-r2"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pairs(items):
    value = {}
    for key, child in items:
        require(key not in value, "duplicate JSON key")
        value[key] = child
    return value


def reject_number(value):
    raise ValueError("noninteger JSON number")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular_bytes(path):
    require(path.is_file() and not path.is_symlink(), "expected regular nonsymlink input")
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--response-file", type=Path, required=True)
    parser.add_argument("--base-directory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    require(args.base_directory.is_dir() and not args.base_directory.is_symlink(), "invalid base directory")
    require(args.output_dir.parent.is_dir() and not args.output_dir.parent.is_symlink(), "fresh owned parent required")
    require(not args.output_dir.exists() and not args.output_dir.is_symlink(), "output must be absent")
    raw = regular_bytes(args.response_file)
    require(len(raw) <= 1048576, "response too large")
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    begin = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == BEGIN]
    end = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == END]
    require(len(begin) == len(end) == 1 and begin[0] < end[0], "one ordered patch block required")
    block = lines[begin[0] + 1:end[0]]
    require(len(block) >= 3, "missing JSON fence")
    require(block[0].rstrip("\r\n") == "```json" and block[-1].rstrip("\r\n") == "```", "exact JSON fence required")
    payload = json.loads("".join(block[1:-1]), object_pairs_hook=pairs,
                         parse_float=reject_number, parse_constant=reject_number)
    require(type(payload) is dict and set(payload) == {"schema", "base_files", "edits", "brief"}, "invalid patch root")
    require(payload["schema"] == "full-todo.code-resource-exact-text-patch.v1", "invalid patch schema")
    require(type(payload["base_files"]) is dict and payload["base_files"] == BASES, "base hashes differ")
    edits = payload["edits"]
    require(type(edits) is list and 1 <= len(edits) <= 64, "invalid edit list")
    brief = payload["brief"]
    require(type(brief) is dict and set(brief) == {"changes", "tests_run", "unresolved_questions"}, "invalid brief")
    require(brief["tests_run"] is False, "model may not claim test execution")
    for key in ("changes", "unresolved_questions"):
        require(type(brief[key]) is list and all(type(v) is str and v for v in brief[key]), "invalid brief strings")
    require(bool(brief["changes"]), "empty change brief")
    originals, current = {}, {}
    for name, expected in BASES.items():
        blob = regular_bytes(args.base_directory / name)
        require(digest(blob) == expected, "base content changed")
        originals[name] = blob
        current[name] = blob.decode("utf-8")
    touched, changes = set(), []
    for index, edit in enumerate(edits):
        require(type(edit) is dict and set(edit) == {"file", "old", "new"}, "invalid edit shape")
        name, old, new = edit["file"], edit["old"], edit["new"]
        require(type(name) is str and name in BASES, "unowned edit path")
        require(type(old) is str and old and type(new) is str and old != new, "invalid edit text")
        first = current[name].find(old)
        require(first >= 0 and current[name].find(old, first + 1) < 0,
                "old text must match exactly once, including overlapping occurrences")
        current[name] = current[name].replace(old, new, 1)
        touched.add(name)
        changes.append({"index": index, "file": name,
                        "old_sha256": digest(old.encode("utf-8")),
                        "new_sha256": digest(new.encode("utf-8"))})
    require(touched == set(BASES), "both owned files must be repaired")
    encoded = {}
    for name, value in current.items():
        blob = value.encode("utf-8")
        require(blob.endswith(b"\n") and not blob.endswith(b"\n\n"), "one final LF required")
        require(blob != originals[name] and len(blob) <= 262144, "invalid resulting file")
        ast.parse(value, filename=name)
        encoded[name] = blob
    for name, blob in originals.items():
        require(regular_bytes(args.base_directory / name) == blob, "base changed while applying")
    require(regular_bytes(args.response_file) == raw, "response changed while applying")
    args.output_dir.mkdir()
    rows = []
    for name, blob in encoded.items():
        with (args.output_dir / name).open("xb") as stream:
            stream.write(blob)
        rows.append({"filename": name, "size_bytes": len(blob), "sha256": digest(blob)})
    record = {"schema": "full-todo.code-resource-applied-patch.v1",
              "response_file": str(args.response_file), "response_sha256": digest(raw),
              "base_directory": str(args.base_directory), "base_files": BASES,
              "edits": changes, "files": rows, "brief": brief,
              "python_syntax": "PASS", "returned_code_executed": False,
              "source_installation": False, "resource_acceptance": False}
    with (args.output_dir / "applied-patch-manifest.json").open("x") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
