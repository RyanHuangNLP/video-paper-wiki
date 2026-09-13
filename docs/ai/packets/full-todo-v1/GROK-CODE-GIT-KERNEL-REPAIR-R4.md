# Bounded Git kernel repair R4

Architect instruction to the current Grok Build session, model `grok-4.6`,
reasoning `xhigh`, normal permission mode. Do not switch model, spawn workers,
change Git, or broaden the package. This repairs the stopped R3 implementation;
the frozen CODE-GIT-KERNEL-R1.md and CODE-GIT-KERNEL-CLARIFICATIONS-R2.md contracts
remain unchanged. Start only after Progress Monitor receives Architect dispatch.

Source checkout:
`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source`.
Baseline head `8728aafc9aa7af5caf90d60bfa6ab2ba89419f75`, tree
`cefcd1be9797d1f4202153d7b9dc4ee1d8423f14`.

The exact preimage is bound by
`artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/kernel-r1/architect-stopped-failing-handoff-r3.json`
in the outer repository, SHA-256
`6c999a3f776928614efc5b2aa760173849d6719a4da6b2201a3b0aaa7f2853b0`.
Its source snapshot is
`27a35de34fd0e05c1e90e8ea0853845c483d532195efcc51715c81b19ea77e59`.
All original source bytes are archived alongside that record in stopped-r3-source.
Verify all three actual preimage hashes before changing anything. Copy hashes
from computed file bytes, never from abbreviated terminal labels.

## Ownership

Only these two existing source paths may change:

- `src/video_paper_wiki/code_git_objects.py`
- `tests/unit/test_code_git_objects.py`

The third path `tests/fixtures/code-git-objects-v1.json` remains byte-identical to
the frozen fixture. No other production, test, resource, schema, dependency,
documentation or Git path may change. Do not overwrite prior briefs, logs or
evidence. The new development brief is the sole new evidence path you may write:
`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/kernel-r1/builder-development-brief-r4.json`.

## Required repairs

1. Strict dictionary keys: current `_validate_limits` performs membership and
   indexing before checking exact key types; `_validate_targets` and
   `_validate_objects` compare `set(item)` before checking exact key types.
   Exact builtin dictionaries can contain str-subclass or arbitrary object keys
   with custom hash/equality callbacks. Reject every non-exact-str key using
   CODE_PROOF_INPUT_INVALID before any lookup, membership, set construction,
   equality, formatting or other operation that could invoke such callbacks.
   Iterate the already exact builtin dict's keys and check `type(key) is str`
   first. Preserve closed key sets, size/count limits, validation order, and
   the existing already-safe bodies-key validation. No coercion, repr or
   exception suppression is a substitute. Add regression cases for limits,
   object records, targets and bodies with callback traps, proving rejection
   without a callback and normal valid proof behavior afterward. Do not use
   mocked cryptographic identities to construct positive proofs.

2. Fix `test_declared_and_actual_caps_precede_hashing`. Its current instrumentation
   counts the calls made while `_minimal_graph` constructs its valid fixture,
   producing six calls before verification starts. Construct data before arming
   the trap, or reset the counter immediately before the function under test.
   Prove both declared and actual per-object/aggregate caps with meaningful
   independent instrumentation. The actual-size case must pass every declared
   size cap, then make an actual body exceed its cap. The current choice based
   solely on the first sorted record can accidentally reject a different
   record's declared size first. Assert structured context including a `/bodies`
   pointer for actual-size failures, correct limit/observed values, and zero
   hashing during the rejected verification. Preserve hash-before-type ordering.

3. Fix the unused-tree branch in
   `test_type_mismatch_omitted_object_and_unused_set`. The extra empty tree has
   exactly the same Git OID as the existing empty root tree, so this is currently
   a duplicate-record failure. Supply a distinct, syntactically valid,
   hash-correct unused tree and require the same CONSUMED_SET_MISMATCH with that
   exact unused OID. Keep the working wrong-type and omitted-blob branches.
   No weakening to generic refusal, skipping, xfail or hash monkeypatching.

4. Remove the unconditional `or True` assertion in
   `test_exact_result_shape_determinism_and_no_input_mutation` (locate the actual
   function containing `assert "\\u0000" not in encoded or True`). Replace it
   with a meaningful assertion for JSON-compatible primitive output, retaining
   the existing exact-shape, no-bytes and alias/mutation checks. This does not
   authorize unrelated refactors.

Architect independently observed 128 generated valid DAGs passing on R3, but
the 42-vector strict-input harness stopped at the first object-key callback.
These are diagnostic results, not acceptance. Earlier 33-pass/2-fail results
remain failed historical evidence.

## Execution and completion

Use actual editing tools immediately after the bounded preimage check. Do not
replace edits with repeated plans or placeholder development briefs. If an edit
tool fails, report the actual failure promptly and stop affected writes.

Run the complete focused test module on both existing locked Python 3.12 and
3.13 runtimes with PYTHONDONTWRITEBYTECODE=1, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1,
PYTHONPATH pointing to this checkout's src, and a short real /private/tmp
basetemp/cache per README. Do not install dependencies or use network. Do not
run the full repository suite for this isolated kernel; complete CODE integration
will own that later check. Do not edit Architect/Steward independent harnesses.

Compute SHA-256 and size for all three source paths from disk after testing.
Write the new brief with actual model/session, contracts and repair prompt,
all changes, command lines, exit codes, counts, remaining gaps and explicit
`source_writes_stopped: true`. Include failed attempts honestly. All paths and
hashes must be real; missing results remain missing. Stop all source writes
after the brief and return its absolute path. Architect and Repo Steward will
replay independent verification before any acceptance or Git delivery.
