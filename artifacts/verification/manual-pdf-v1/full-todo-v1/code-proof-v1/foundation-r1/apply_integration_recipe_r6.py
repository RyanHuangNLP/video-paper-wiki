"""Apply only the bounded, reviewed Grok recipe to immutable R5 previews."""
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).parent
PRODUCTION_NAMES = {
    "_require_plain_json_tree", "_canonical_list_index", "_require_exact_mapping",
    "_walk_schema_document", "_validate_schema_references", "CodeProofResources",
    "compile_code_proof_resources",
}
TEST_NAMES = {
    "test_structure_preflight_and_titles", "test_limit_exact_key_and_value_types",
    "test_profile_exact_builtin_keys", "test_schema_reference_malformed_graphs",
    "test_context_rejects_external_configuration",
}
ERRORS = {"CodeProofResourceError", "CodeProofStructureError"}
HELPERS = {"_assert_resource", "_assert_structure"}
NEW_TEST = "test_private_errors_suppress_outer_exception_context"


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path), "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def pairs(items):
    result = {}
    for key, value in items:
        assert key not in result, "duplicate recipe key"
        result[key] = value
    return result


def validate_recipe(document):
    assert set(document) == {"schema", "edits"}
    assert document["schema"] == "foundation.integration-correction.v1"
    edits = document["edits"]
    assert type(edits) is list and len(edits) == 3
    one, two, three = edits
    assert set(one) == {"kind", "path", "symbols", "exceptions"}
    assert one["kind"] == "suppress_private_raise_context"
    assert one["path"] == "src/video_paper_wiki/code_proof_resources.py"
    assert len(one["symbols"]) == 7 and set(one["symbols"]) == PRODUCTION_NAMES
    assert len(one["exceptions"]) == 2 and set(one["exceptions"]) == ERRORS
    assert set(two) == {"kind", "path", "symbols", "helpers", "variable"}
    assert two["kind"] == "pytest_exception_value"
    assert two["path"] == "tests/unit/test_code_proof_resources.py"
    assert len(two["symbols"]) == 5 and set(two["symbols"]) == TEST_NAMES
    assert len(two["helpers"]) == 2 and set(two["helpers"]) == HELPERS
    assert two["variable"] == "exc"
    assert three == {"kind": "profile_inventory_key", "path": "tests/unit/test_code_proof_resources.py", "symbol": "test_profile_exact_builtin_keys", "old_key": "inventory", "new_key": "schemas"}


def scoped_nodes(raw, names):
    tree = ast.parse(raw)
    tops = [node for node in tree.body if getattr(node, "name", None) in names]
    assert len(tops) == len(names)
    return [(top.name, node) for top in tops for node in ast.walk(top)]


def byte_offsets(raw):
    lines = raw.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    return starts


def apply_edits(raw, edits):
    edits = sorted(edits, key=lambda edit: (edit["start"], edit["end"]))
    cursor = 0
    chunks = []
    preserved = []
    for edit in edits:
        start, end = edit["start"], edit["end"]
        assert cursor <= start <= end <= len(raw)
        segment = raw[cursor:start]
        preserved.append({"old_start": cursor, "old_end": start, "size_bytes": len(segment), "sha256": hashlib.sha256(segment).hexdigest()})
        chunks.extend([segment, edit["replacement"]])
        edit["old_sha256"] = hashlib.sha256(raw[start:end]).hexdigest()
        edit["new_sha256"] = hashlib.sha256(edit["replacement"]).hexdigest()
        cursor = end
    segment = raw[cursor:]
    preserved.append({"old_start": cursor, "old_end": len(raw), "size_bytes": len(segment), "sha256": hashlib.sha256(segment).hexdigest()})
    chunks.append(segment)
    result = b"".join(chunks)
    ast.parse(result)
    return result, [{key: value for key, value in edit.items() if key != "replacement"} for edit in edits], preserved


def main():
    result_path = HERE / "grok-foundation-r6-result.json"
    result = json.loads(result_path.read_text())
    stdout_path = HERE / "grok-foundation-r6.stdout.log"
    assert result["actual_exit_code"] == 0 and result["stdout"] == pin(stdout_path)
    text = stdout_path.read_text(encoding="utf-8")
    assert text.rstrip().endswith("Tests not run.")
    json_blocks = re.findall(r"^```json\n(.*?)^```[ \t]*$", text, re.M | re.S)
    python_blocks = re.findall(r"^```python\n(.*?)^```[ \t]*$", text, re.M | re.S)
    assert len(json_blocks) == len(python_blocks) == 1
    recipe = json.loads(json_blocks[0], object_pairs_hook=pairs)
    validate_recipe(recipe)
    new_body = python_blocks[0].encode("utf-8")
    tree = ast.parse(new_body)
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
    node = tree.body[0]
    assert node.name == NEW_TEST and not node.decorator_list
    lines = new_body.splitlines(keepends=True)
    new_test = b"".join(lines[node.lineno - 1:node.end_lineno])
    assert new_test.endswith(b"\n")
    original_prod = HERE / "assembled-r5-code_proof_resources.py"
    original_tests = HERE / "assembled-r5-test_code_proof_resources.py"
    assert pin(original_prod)["sha256"] == "5bbace6bedafa46b16274dd1a842ee6d0e643fae042c905d9eb5a7699483d0a5"
    assert pin(original_tests)["sha256"] == "75e5d20582963324c15e70482f6f481cc1fe95dccd2b4e7250c4befee50e75c9"
    production = original_prod.read_bytes()
    tests = original_tests.read_bytes()
    starts = byte_offsets(production)
    production_edits = []
    for symbol, node in scoped_nodes(production, PRODUCTION_NAMES):
        if isinstance(node, ast.Raise) and node.cause is None and isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name) and node.exc.func.id in ERRORS:
            assert node.lineno == node.end_lineno
            offset = starts[node.end_lineno - 1] + node.end_col_offset
            production_edits.append({"symbol": symbol, "kind": "suppress_private_raise_context", "start": offset, "end": offset, "replacement": b" from None"})
    assert len(production_edits) == 29
    starts = byte_offsets(tests)
    test_edits = []
    for symbol, node in scoped_nodes(tests, TEST_NAMES):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in HELPERS and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "exc":
            arg = node.args[0]
            start = starts[arg.lineno - 1] + arg.col_offset
            end = starts[arg.end_lineno - 1] + arg.end_col_offset
            assert tests[start:end] == b"exc"
            test_edits.append({"symbol": symbol, "kind": "pytest_exception_value", "start": start, "end": end, "replacement": b"exc.value"})
    assert len(test_edits) == 48
    inventory_edits = []
    for symbol, node in scoped_nodes(tests, {"test_profile_exact_builtin_keys"}):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "mutated" and isinstance(node.slice, ast.Constant) and node.slice.value == "inventory":
            value = node.slice
            start = starts[value.lineno - 1] + value.col_offset
            end = starts[value.end_lineno - 1] + value.end_col_offset
            assert tests[start:end] == b'"inventory"'
            inventory_edits.append({"symbol": symbol, "kind": "profile_inventory_key", "start": start, "end": end, "replacement": b'"schemas"'})
    assert len(inventory_edits) == 1
    final_prod, prod_changes, prod_preserved = apply_edits(production, production_edits)
    final_tests, test_changes, test_preserved = apply_edits(tests, test_edits + inventory_edits)
    assert NEW_TEST not in {getattr(node, "name", None) for node in ast.parse(final_tests).body}
    final_tests += b"\n\n" + new_test
    ast.parse(final_tests)
    outputs = [HERE / "assembled-r6-code_proof_resources.py", HERE / "assembled-r6-test_code_proof_resources.py", HERE / "assembly-r6.json"]
    assert not any(path.exists() for path in outputs)
    for path, raw in zip(outputs, (final_prod, final_tests)):
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
        with path.open("xb") as stream:
            stream.write(raw)
    record = {"schema": "full-todo.foundation-integration-recipe-assembly.v1", "call_result": pin(result_path), "stdout": pin(stdout_path), "assembler": pin(Path(__file__)), "recipe": recipe, "inputs": [pin(original_prod), pin(original_tests)], "outputs": [pin(path) for path in outputs[:2]], "production_edits": prod_changes, "test_edits": test_changes, "preserved_segments": {"production": prod_preserved, "tests": test_preserved}, "new_test": {"name": NEW_TEST, "size_bytes": len(new_test), "sha256": hashlib.sha256(new_test).hexdigest()}, "product_source_written": False, "accepted": False}
    with outputs[2].open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"record": pin(outputs[2]), "outputs": record["outputs"], "edit_counts": [len(prod_changes), len(test_changes)]}, indent=2))


if __name__ == "__main__":
    main()
