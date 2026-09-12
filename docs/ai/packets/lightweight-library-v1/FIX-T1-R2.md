# T1 revision 2 — close independently reproduced integrity/publication failures

This is an Architect-authorized fix within the unchanged `CONTRACT.md` revision 1
SHA-256 `7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12`.
It changes no public API, workflow kinds, dependency, writer ownership or product scope.
The six T1 allowed paths from the original freeze remain the entire source allowlist.

Input is stopped T1 r1 snapshot
`e27e0670b658cdd9e5aebbcfe148b22eb1ab84dfceca9675484630bdb9606c35`, against baseline
`3368c6435db166a285b4b0e2df00f5d6a7491956`. R1 is rejected for integration.
Its files, checks, report, handoff/ready, controller logs and the Architect replay are
immutable. R2 must write a NEW `terminal-1/r2` candidate and stop again.

Read the rejection and replay under
`ROOT/artifacts/verification/manual-pdf-v1/lightweight-library-v1/`:

- `architect-t1-r1-decision.json`
- `architect-t1-r1-replay/checks.json`, `stdout.log`, `junit.xml`
- `architect-t1-preliminary-review-r1.json` (preliminary only; final replay wins)

The independent Architect suite ran **13 failed, 1 passed** in 2.97s on the exact
stopped r1 source. Its behavioral reproducer is
`ROOT/.work/acceptance/lightweight-library-v1/architect_t1_regressions.py`, SHA-256
`c6d149ad1bcd6a248a69e68ba4b469d7a403bd8dca910ea43401da4d892687ac`.
Read this test source to understand triggers. Implement equivalent meaningful
regressions using your existing synthetic fixtures in the owned repository test
files. Do not read/print the real-paper corpus or run the Architect's real-corpus
variants through Cursor; Architect will replay them locally. No failure may be
hidden by changing assertions, skipping cases, broad exception swallowing, or
silently redefining the contract.

## Required corrections

1. **Successful publication must finish its owned staging.** A HEADS/CURRENT
   file replacement leaves an empty `payload/` and `ownership.json`; current
   cleanup retains that stage forever. Remove only the validated empty owned
   infrastructure after publication. An identical retry must also reconcile a
   validated already-published pointer/record/view stage. Normal import/build
   must leave no pending publication entry, so T2 backup is usable.

2. **Complete-set checks include every directory entry.** `_inventory_bytes`
   currently filters symlink directories out and ignores extra empty directories.
   Refuse unsafe entries and directories outside the exact parents implied by
   the expected generated file set. Apply this to record/view reuse, listing and
   staging/recovery. Do not follow or silently omit entries; preserve them.

3. **Validate saved records before calling them current or using their concepts.**
   A canonical edited document with an unknown citation currently remains
   `current` even though its bytes disagree with the manifest. Validate exact
   schemas/shapes, complete file set, sizes/hashes, record ID/directory and path
   identity, document/context/identity consistency and citation ownership against
   actual current derived source bytes. Recomputed self-hashes alone are not
   authority. Build views only from valid current heads. A malformed/edited record
   is `conflict` and must not contribute new concepts or relationships. Preserve
   old bytes. Saved original contexts remain unchanged after relocation; validate
   relative source identities locally without following their old absolute root.
   If reproducible record identity requires additional persisted internal fields,
   add and fully validate them within the new record bundle; public APIs/schema
   kinds and approved storage roots stay unchanged.

4. **Fix related-paper Markdown paths.** A link from
   `knowledge/views/<id>/papers/<paper>.md` to a related paper is a sibling link,
   not `papers/<other>.md` under that `papers/` directory. Verify every emitted
   relative link resolves at its actual page location, including concept pages.

5. **Malformed wrappers close predictably.** Removing `coverage`,
   `paper_snapshot` or `prompt` from knowledge, or `coverage` from comparison,
   currently raises `KeyError`. Validate all required fields and types before
   indexing. Expected refusal/ResearchError is acceptable; no traceback or
   partial publication. Keep the complete canonical wrapper cross-check.

6. **Reject hardlinked source inputs.** Validate source.md/source.json and their
   path chains before source reads/exports/imports/status decisions, not just
   generated bundle files. Reuse established validators and preserve source
   bytes. Do not depend on an unaccepted change in T2's shared index module.

7. **Do not discard edited or foreign partial staging.** After interruption at
   a record's document write, changing that file or the ownership marker's
   intended target currently causes retry to delete the unknown bytes and
   return success. Validate the full ownership shape, exact kind/ID/target,
   allowed payload set and every existing generated file against the operation's
   expected bytes before recovery or cleanup. Unknown or user-edited bytes and
   mismatched ownership must produce conflict and remain untouched. Validated
   untouched partial work can still recover; do not make all retries fail.

8. **Revalidate before publishing or switching the pointer.** A source edit
   during `_record_files` currently still publishes and returns current. Check
   actual source/file identities after rendering and immediately before record
   publication/head change. Views likewise recheck the heads and source/record
   snapshots they used before switching CURRENT. Detected external change must
   close and preserve the previously valid pointer/artifacts. This is the frozen
   observed-change guarantee, not a new claim about hostile concurrency.

The unknown-CURRENT-schema refusal passed and must remain. Strengthen pointer
validation to the complete expected shape/identity, including valid target ID
and matching intended relative target, before replacing a prior pointer. Do not
treat an object as owned just because its `schema` string matches.

## Completion

Run all three T1 owned test files and the complete existing `test_light_context.py`
regression using the locked Python 3.13 source-local environment and short real
temporary paths. Record actual commands, module provenance, results and unresolved
issues. Do not run full dual-version suites or isolated builds on a mixed active
candidate. Freeze only your six changed owned paths as COMMON specifies, preserve
old R1 evidence, return r2 handoff/ready and stop writing. Architect and controller
review this exact new snapshot before T3 may import it.
