# TERMINAL-2 r2 — preservation, recovery and backup verification

## Functionality
Same public T2 APIs as r1 on unchanged CONTRACT revision 1. The nine correction groups from FIX-T2-R2.md are implemented centrally:

1. Metadata and shared JSON writes use exclusive-create owned temps. Pre-existing `*.tmp` files, symlinks and hardlink referents stay untouched.
2. `extract_pdf` validates/creates only the workspace root before `workspace.lock`; `papers/` and `.light-transactions` are created after the lock.
3. Journals require the documented versioned closed shape, filename/ID match, kind-specific phase, exact owned paths, and frozen file/directory inventories. Recovery compares actual payloads to those inventories and does not rescan modified content to pass. Completed journals still check identity; both-side occupancy of the same archive is a conflict.
4. Stage discard requires a complete owner marker and the known native producer layout. Unknown nested text is preserved. A clean pre-staging failure settles as `complete` + `outcome=aborted-before-staging` with no replacement claim and is not a backup blocker.
5. Repeating an exact completed replacement reuses the unique matching event after validating the old archive and new live payload.
6. Backup re-snapshots after ZIP construction and `before_backup_publish`; a change leaves the output absent.
7. Restore never overwrites archived `.light-library/restoration.json`. Optional generated metadata uses a collision-free restorations/ path. Repeated backup→restore preserves every included file's bytes.
8. Manifest verification checks types/shapes, `workspace_id == sha256(canonical({workspace_root}))` without following the old root, exclusions, extra-output mappings, and text policy on every member including `exports/external`.
9. ZIP verification refuses symlink/public modes, wrong timestamps including the manifest, extra fields, ZIP64 metadata, and symlink traversal on the archive input chain.

## Files
Nine owned paths only. See `handoff.json` files manifest and `snapshot_sha256`. r1 source/evidence remains byte-identical history.

## Tests
- Focused: 44 passed, exit 0, `/private/tmp/t2-r2-final.12691/focused`
- Related existing PDF/index/workspace/workflow: 95 passed, exit 0, `/private/tmp/t2-r2-final.12691/related`
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. No copied venv, no installs, no Git mutation.
- Architect real-corpus variants were not run through Cursor.

## Unresolved issues
- T3 CLI/Skill/docs are not in this lane and were not edited. No T3 import.
- Dual Python 3.12, installed-wheel, full-suite and Architect real-corpus replay remain Architect work.
- No commit, push, CI, real Vault, or human-gate action was taken.

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
