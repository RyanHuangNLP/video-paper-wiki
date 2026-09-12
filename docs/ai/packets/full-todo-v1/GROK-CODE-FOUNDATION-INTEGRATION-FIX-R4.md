Provide a very small integration correction to your previously authored private
Python resource validator and pytest tests. Use only this natural-language
instruction: no files, tools, commands, browsing, delegation, Git or test runs.
Do not rewrite the modules or repeat their full definitions. Return exactly one
JSON fenced block containing the declarative edit recipe described below, then
one Python fenced block containing the single new test function, then the exact
sentence "Tests not run." The local integrator will verify and apply only that
recipe to the preserved source, retaining all other bytes.

The assembled code closes the original key-type, huge-index, constructor and
schema-cycle defects. Three small integration errors remain:

- New production direct raises of CodeProofResourceError or
  CodeProofStructureError omit `from None`. If called while another exception is
  active, Python may print that unrelated exception and its sensitive message.
  Every explicitly raised private boundary error must suppress that context.
- The new tests use `with pytest.raises(...) as exc`, then pass `exc` to helpers
  that require the actual exception. Those calls must pass `exc.value`.
- The profile's inventory array is named `schemas`, not `inventory`.

The first JSON block must be an object with exactly `schema` and `edits`.
Schema is `foundation.integration-correction.v1`. Edits is these three
declarative operations, without an executable script or regular expressions:

1. An object with `kind` = `suppress_private_raise_context`, `path` =
   `src/video_paper_wiki/code_proof_resources.py`, `symbols` listing exactly
   `_require_plain_json_tree`, `_canonical_list_index`, `_require_exact_mapping`,
   `_walk_schema_document`, `_validate_schema_references`, `CodeProofResources`,
   `compile_code_proof_resources`, and `exceptions` listing exactly
   `CodeProofResourceError`, `CodeProofStructureError`. Meaning: only inside
   those top-level definitions, add `from None` to direct raises of these classes
   whose AST cause is absent. Leave already explicit causes and bare re-raises
   unchanged. No behavioral rewrite or other source changes.
2. An object with `kind` = `pytest_exception_value`, `path` =
   `tests/unit/test_code_proof_resources.py`, `symbols` listing exactly
   `test_structure_preflight_and_titles`, `test_limit_exact_key_and_value_types`,
   `test_profile_exact_builtin_keys`, `test_schema_reference_malformed_graphs`,
   `test_context_rejects_external_configuration`, `helpers` listing exactly
   `_assert_resource`, `_assert_structure`, and `variable` = `exc`. Meaning:
   inside only these five tests, change the first argument `exc` of a named
   helper call to `exc.value`. Do not change helper definitions, pytest context
   managers, unrelated names or real exception values in older tests.
3. An object with `kind` = `profile_inventory_key`, `path` =
   `tests/unit/test_code_proof_resources.py`, `symbol` =
   `test_profile_exact_builtin_keys`, `old_key` = `inventory`, `new_key` =
   `schemas`. Meaning: change the single `mutated["inventory"][0]` lookup in that
   test to `mutated["schemas"][0]`. Keep all actual fixture/profile bytes intact.

The Python block must contain exactly one complete top-level function:
`test_private_errors_suppress_outer_exception_context(resources)`. No other
top-level definitions or imports. A local `import traceback` inside the test is
permitted. Existing module globals available are pytest, cpr (the production
module), CodeProofResourceError, CodeProofStructureError,
compile_code_proof_resources, _parse_resource_bytes,
_validate_schema_references, _validate_profile_inventory, _COMMON_TITLE,
_MARKER, _assert_resource(exception, reason) and
_assert_structure(exception, reason). `resources` is a genuine compiled fixture.

The new regression test must invoke multiple actual boundary failures while
handling a separate RuntimeError with a marker-containing message. Cover an
unknown title (structure/shape), malformed limit map (structure/limits), direct
context construction (resource/resource_shape), malformed retained byte mapping,
private parser, profile inventory helper and schema reference helper (all
resource/resource_shape). Existing APIs: resources.validate_structure(title,
instance), resources.materialize_limits(value), cpr.CodeProofResources(),
compile_code_proof_resources(retained_bytes), _parse_resource_bytes(bytes),
_validate_profile_inventory(dict), _validate_schema_references(dict).

For each case, raise RuntimeError with a dynamically composed outer marker and,
inside its except block, capture the expected private exception with pytest.
Pass caught.value to the matching existing assertion helper. Assert the
captured exception has __suppress_context__ is True and __cause__ is None, and
that ''.join(traceback.format_exception(caught.value)) does not contain the
actual dynamic outer marker. Keep the original outer exception active during
the failing call; a call made after leaving that handler would not test the bug.
Use invalid primitive values to reach these branches, no pin overrides or I/O.
The error reason/message checks must remain strict; do not weaken the helpers.
