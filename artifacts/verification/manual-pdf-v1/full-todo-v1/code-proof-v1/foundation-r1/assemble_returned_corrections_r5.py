"""Mechanically compose reviewed Grok definitions into preserved source previews.

This writes only new verification previews, never the product checkout. It does
not execute returned Python. The original R4 output and all other definitions
remain immutable inputs.
"""
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).parent
PRODUCTION = {
    "_require_plain_json_tree", "_canonical_list_index",
    "_validate_schema_references", "_require_exact_mapping",
    "CodeProofResources", "compile_code_proof_resources",
    "_walk_schema_document",
}
TESTS = {
    "test_structure_preflight_and_titles", "test_limit_exact_key_and_value_types",
    "test_profile_exact_builtin_keys", "test_schema_reference_malformed_graphs",
    "test_context_rejects_external_configuration",
}


def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def definitions(text, expected):
    tree = ast.parse(text)
    assert all(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in tree.body)
    assert all(not node.decorator_list for node in tree.body)
    assert len(tree.body) == len(expected)
    assert {node.name for node in tree.body} == expected
    lines = text.splitlines(keepends=True)
    return {node.name: (node, "".join(lines[node.lineno - 1:node.end_lineno])) for node in tree.body}


def compose(original, replacements, allowed_new):
    original_tree = ast.parse(original)
    original_lines = original.splitlines(keepends=True)
    original_defs = {node.name: node for node in original_tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    assert set(replacements) - set(original_defs) == allowed_new
    result = list(original_lines)
    changes = []
    existing = [original_defs[name] for name in replacements if name in original_defs]
    for node in sorted(existing, key=lambda item: item.lineno, reverse=True):
        assert not node.decorator_list
        replacement = replacements[node.name][1]
        assert replacement.endswith("\n")
        old = "".join(original_lines[node.lineno - 1:node.end_lineno])
        result[node.lineno - 1:node.end_lineno] = replacement.splitlines(keepends=True)
        changes.append({"name": node.name, "original_start_line": node.lineno, "original_end_line": node.end_lineno, "old_sha256": hashlib.sha256(old.encode()).hexdigest(), "new_sha256": hashlib.sha256(replacement.encode()).hexdigest()})
    merged = "".join(result)
    for name in sorted(allowed_new):
        merged += "\n\n" + replacements[name][1]
        changes.append({"name": name, "operation": "append_new_test_definition", "new_sha256": hashlib.sha256(replacements[name][1].encode()).hexdigest()})
    assert merged.endswith("\n") and not merged.endswith("\n\n")
    ast.parse(merged)
    return merged, changes


def main():
    stdout = HERE / "grok-foundation-r5.stdout.log"
    result_path = HERE / "grok-foundation-r5-result.json"
    call_result = json.loads(result_path.read_text())
    assert call_result["actual_exit_code"] == 0
    assert call_result["stdout"] == pin(stdout)
    response = stdout.read_text(encoding="utf-8")
    blocks = [match.group(1) for match in re.finditer(r"^```python\n(.*?)^```[ \t]*$", response, re.M | re.S)]
    assert len(blocks) == 2, "Expected exactly the two instructed Python code blocks"
    production = definitions(blocks[0], PRODUCTION)
    tests = definitions(blocks[1], TESTS)
    inputs = [
        ("code_proof_resources.py", "3baa70b3867a71611215dc51a303ff63d2fe8c0c564247fe69d72cead7aae21f", production, set()),
        ("test_code_proof_resources.py", "a38b8b81b5ec3f1877b7a01a97fe457136eb7b0e704edd58e6e8e6779fd07a71", tests, TESTS - {"test_structure_preflight_and_titles"}),
    ]
    output_paths = [HERE / ("assembled-r5-" + item[0]) for item in inputs]
    record_path = HERE / "assembly-r5.json"
    assert not any(path.exists() for path in output_paths + [record_path])
    rows = []
    for (filename, digest, replacements, allowed_new), destination in zip(inputs, output_paths):
        source = HERE / ("returned-r4-" + filename)
        assert pin(source)["sha256"] == digest
        merged, changes = compose(source.read_text(encoding="utf-8"), replacements, allowed_new)
        with destination.open("xb") as stream:
            stream.write(merged.encode("utf-8"))
        rows.append({"input": pin(source), "output": pin(destination), "changes": changes})
    record = {"schema": "full-todo.foundation-mechanical-correction-assembly.v1", "call_result": pin(result_path), "stdout": pin(stdout), "assembler": pin(Path(__file__)), "files": rows, "product_source_written": False, "accepted": False, "tests_executed": False}
    with record_path.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
