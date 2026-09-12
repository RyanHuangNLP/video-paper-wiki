# T2 revision 4 — validate producer ownership before freezing an inventory

This bounded correction continues original contract
`7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12`
at baseline `3368c6435db166a285b4b0e2df00f5d6a7491956`. Input is stopped R3
snapshot `59a62f696bc75b5b4ff0346612dbd380ec45b68f16f73fc7f5546e407123851e`.
Preserve every prior packet, source bundle and review unchanged.

R3 passes the 55 accumulated Architect recovery/manifest/history checks and
21 independent synthetic backup checks, plus its 76 focused and 95 related
checks. It remains rejected because six new controlled cases reproduce a
single missing ownership boundary before the stage inventory is captured.

## Confirmed failure and required behavior

In `_replace_forward`, phase `intent` currently starts the native producer
without checking the exact initial stage. After the producer returns it writes
prior notes with overwrite semantics and then inventories every encountered
regular file and directory as owned. Subsequent exact cleanup faithfully deletes
those newly adopted foreign bytes.

Two failing cases add `workspace/user-note.md` or an empty `workspace/user-empty`
at `after_intent` without throwing. Four failing cases wrap the native extraction
return and introduce an unknown file, empty directory, pre-existing
`prior-paper-notes.md`, or modified `.light-workflow/locks/workspace.lock`.
Replacement reports success in all six cases. The old paper must instead remain
live, all introduced bytes/directories must remain intact, and the operation
must return a closed conflict/recovery result before old-payload movement.
The earlier before-extraction prior-note case already refuses; preserve it.

Validate the exact known untouched intent-stage shape before creating the native
workspace or invoking extraction. Then independently validate the complete
native producer output against its supported layout, expected new paper digest,
producer identity/manifest/source bindings, fixed lock contents and exact
directories before accepting or freezing any inventory. A fresh recursive hash
is an observation, never proof that unknown content was produced by this call.
Reject arbitrary extra files/directories, foreign producer artifacts, modified
locks, symlinks/hardlinks and unsafe edges. Keep the R3 complete-set validation
before cleanup, and apply it before irreversible old-paper movement as well.

Create the attributed prior-note file only if absent with a create-only
primitive. An unexpected existing file must be preserved, even if it appears
after the earlier scan. Validate complete ownership again after adding this
known owned file. Preserve safe native extraction failure and abort semantics;
do not delete unknown artifacts on error or silently adopt them on retry.
Do not solve this by special-casing only the test hook or always refusing
replacement. Ordinary replacement, source/notes attribution, every recognized
interruption/recovery point, and the successful history/backup cases must pass.

## Bounded ownership and validation

Use the same nine T2 owner paths, only as necessary for this correction and its
synthetic regressions. The approved R3 ZIP/backup/history semantics remain fixed;
there are no new features or public interfaces. Builder alone edits production
and repository tests. Do not edit T1/T3, dependencies, core Vault or schemas.

Architect test SOURCE under `.work/acceptance/lightweight-library-v1/` is readable:
`architect_t2_r3_precapture.py`, `architect_t2_r3_postextract.py`, and the original
regression/additional/corrected-history scripts bound in the R4 freeze. Port the
meaningful cases into the owned synthetic tests. Do not read or run raw real-PDF
corpus variants in Cursor; Architect handles that local replay. No weakening,
removed assertions or skip substitutes. Run all three owned tests plus related
PDF/recovery/index/workspace/workflow suites with the locked source-local Python
3.13 setup and short real temporary paths from COMMON.

Freeze a new `terminal-2/r4` bundle with exact files/checks/report/handoff/ready,
binding this freeze, original contract and previous R3 snapshot. Use the normal
evidence location once; a denial permits a complete source-local R4 bundle and
location report, never an alternate-method copy retry. Stop source writes after
the handoff. No T3 import, Git mutation, merge or final product acceptance claim.
