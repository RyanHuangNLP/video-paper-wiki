# TERMINAL-2 r7 — replacement as a restored paper's successor

## Functionality
Surgical successor-selector correction on unchanged CONTRACT revision 1. Input is stopped R6 snapshot `968f1ef3f4cf319d828c2100b482b9f33144af5e71b14d6727120fdf1e1fceda`.

`_unique_archive_successor` now considers completed `archive`/`archived` or completed `replace`/`replaced` with the same paper ID and exact old file/directory inventory. Archive-ID exclusion, unique-candidate, outcome, recursive event/payload/live-state verification and cycle/duplicate refusal are unchanged. Missing live paper is not treated as completion without this retained proof. No journal/schema change.

Only `light_library.py` and `test_light_library_recovery.py` changed relative to R6. The R6 native classifier and the other seven owner files remain byte-identical.

## Files
Nine owned paths inventoried. See `handoff.json` files manifest and `snapshot_sha256`.

## Tests
- Focused: 106 passed, exit 0, `/private/tmp/t2-r7-final.U08W7H/focused`
- Related existing PDF/index/workspace/workflow: 95 passed, exit 0, `/private/tmp/t2-r7-final.U08W7H/related`
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. No copied venv, no installs, no Git mutation.
- Architect real-corpus variants were not run. Six restore-then-replace history cases were ported to synthetic fixtures.

## Unresolved issues
- Shared artifacts `terminal-2/r7` write succeeded; this complete bundle is the evidence location. No source-local copy was written.
- T3 CLI/Skill/docs are not in this lane and were not edited. No T3 import.
- Dual Python 3.12, installed-wheel, full-suite and Architect real-corpus replay remain Architect work.
- No commit, push, CI, real Vault, or human-gate action was taken.

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
