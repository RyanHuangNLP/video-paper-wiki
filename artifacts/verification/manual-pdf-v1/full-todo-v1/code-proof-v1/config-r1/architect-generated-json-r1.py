"""Independent JSON emission oracle, executed only against a stopped candidate."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import random
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pointer(base, key):
    return base + "/" + str(key).replace("~", "~0").replace("/", "~1")


def make_case(seed, text_metadata, snippet_hash):
    rng = random.Random(87501 + seed)
    newline = "\r\n" if seed % 2 else "\n"
    parts, marks, declarations = [], {}, {}
    position = 0

    def emit(text):
        nonlocal position
        parts.append(text)
        position += len(text)

    # Typed declarative inputs supply the oracle before source is emitted.
    scalars = [("null", None), ("boolean", True), ("boolean", False),
               ("string", "训练 😀 e\u0301 /~\n\t\u0000"), ("string", ""),
               ("integer", ("120", "120")), ("integer", ("-7", "-7")),
               ("decimal", ("1.250e-2", "0.0125")),
               ("decimal", ("1e0", "1")), ("decimal", ("0.000", "0"))]

    def subtree(depth):
        if depth == 0 or rng.randrange(4) == 0:
            return rng.choice(scalars)
        if rng.randrange(2):
            return ("array", [subtree(depth - 1) for _ in range(rng.randrange(5))])
        keys = rng.sample(["a", "z", "a/b", "~key", "中文", "😀", "", "e\u0301"], rng.randrange(5))
        return ("object", [(key, subtree(depth - 1)) for key in keys])

    root = ("object", [("source", subtree(3)), ("betas", ("array", [
        ("decimal", ("0.9", "0.9")), ("decimal", ("0.999", "0.999"))])),
        ("nested", ("object", [("empty", ("array", [])), ("对象", ("object", []))]))])

    def dump(node, path="", depth=0):
        start = position
        kind, value = node
        children = []
        if kind == "object":
            emit("{")
            for index, (key, child) in enumerate(value):
                emit(("," if index else "") + newline + "\t" * (depth + 1))
                key_start = position
                emit(json.dumps(key, ensure_ascii=bool((seed + index) % 2)))
                child_path = pointer(path, key)
                declarations[child_path] = (key_start, position)
                emit(" : ")
                dump(child, child_path, depth + 1)
                children.append((key, child_path))
            if value:
                emit(newline + "\t" * depth)
            emit("}")
            child_paths = [p for _, p in sorted(children, key=lambda row: row[0].encode())]
            output_value, lexeme = None, None
        elif kind == "array":
            emit("[ ")
            for index, child in enumerate(value):
                if index:
                    emit(", ")
                child_path = pointer(path, index)
                dump(child, child_path, depth + 1)
                children.append(child_path)
            emit(" ]")
            child_paths, output_value, lexeme = children, None, None
        elif kind in ("integer", "decimal"):
            lexeme, output_value = value
            emit(lexeme)
            child_paths = []
        else:
            emit(json.dumps(value, ensure_ascii=bool(seed % 3)))
            child_paths, output_value, lexeme = [], value, None
        marks[path] = (start, position, kind, output_value, lexeme, child_paths, depth)

    emit(" \t" + newline)
    dump(root)
    if seed % 3:
        emit(newline)
    source = "".join(parts)
    body = source.encode()

    def span(bounds):
        start, end = bounds
        line_start = source[:start].count("\n") + 1
        line_end = source[:end].count("\n") + 1
        col_start = start - source.rfind("\n", 0, start)
        col_end = end - source.rfind("\n", 0, end)
        last_line = line_end - (col_end == 1 and line_end > line_start)
        return dict(byte_start=len(source[:start].encode()), byte_end=len(source[:end].encode()),
                    codepoint_start=start, codepoint_end=end, line_start=line_start,
                    column_start=col_start, line_end=line_end, column_end=col_end,
                    raw_sha256=sha(source[start:end].encode()),
                    snippet_sha256=snippet_hash(body, line_start, last_line))

    nodes = []

    def visit(path):
        start, end, kind, value, lexeme, children, _ = marks[path]
        decls = ([dict(kind="json_key", span=span(declarations[path]))]
                 if path in declarations else [])
        nodes.append(dict(path=path, kind=kind, value=value, numeric_lexeme=lexeme,
                          children=children, value_span=span((start, end)), declarations=decls))
        for child in children:
            visit(child)

    visit("")
    budget = dict(node_count=len(nodes), scalar_count=sum(n[2] not in ("object", "array") for n in marks.values()),
                  max_depth_observed=max(n[6] for n in marks.values()), declaration_count=len(declarations),
                  max_array_items_observed=max((len(n[5]) for n in marks.values() if n[2] == "array"), default=0),
                  max_object_keys_observed=max((len(n[5]) for n in marks.values() if n[2] == "object"), default=0))
    expected = dict(config_format="json", source=dict(body_size_bytes=len(body), body_sha256=sha(body), **text_metadata(body)),
                    budget=budget, nodes=nodes)
    return body, expected


def run(handoff_path, output):
    handoff = json.loads(handoff_path.read_bytes())
    assert handoff["source_writes_stopped"] is True
    source = Path(handoff["source_root"])
    for row in handoff["candidate_files"]:
        raw = (source / row["path"]).read_bytes()
        assert len(raw) == row["size_bytes"] and sha(raw) == row["sha256"]
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / "src"))
    module = importlib.import_module("video_paper_wiki.code_config_parser")
    legacy = importlib.import_module("video_paper_wiki.code_evidence_contracts")
    rows = []
    for seed in range(64):
        body, expected = make_case(seed, legacy.code_text_metadata, legacy.code_snippet_sha256)
        limits = dict(module.CODE_CONFIG_PROFILE_LIMITS)
        actual = module.parse_code_config_bytes(payload=body, config_format="json", limits=limits)
        assert actual == expected, (seed, "complete result mismatch")
        # JSON equality alone would hide bool/int differences and key ordering.
        assert json.dumps(actual, ensure_ascii=True) == json.dumps(expected, ensure_ascii=True), seed
        actual["nodes"][0]["children"].clear()
        again = module.parse_code_config_bytes(payload=body, config_format="json", limits=limits)
        assert again == expected and limits == dict(module.CODE_CONFIG_PROFILE_LIMITS)
        rows.append(dict(seed=seed, source_sha256=sha(body), nodes=len(expected["nodes"]), status="PASS"))
    for row in handoff["candidate_files"]:
        assert sha((source / row["path"]).read_bytes()) == row["sha256"]
    result = dict(status="PASS", runtime=sys.version, candidate_snapshot_sha256=handoff["candidate_snapshot_sha256"],
                  handoff_sha256=sha(handoff_path.read_bytes()), cases=len(rows), rows=rows)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("handoff", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.handoff, args.output)
