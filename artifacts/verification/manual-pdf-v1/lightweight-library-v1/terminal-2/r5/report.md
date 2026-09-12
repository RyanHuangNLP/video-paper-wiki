# TERMINAL-2 r5 — last pre-move stage check

## Functionality
Surgical correction to stopped R4 snapshot `e11be2214f411547295c8947245e56cbb05d9fe8600f94c9994244b5219ed2bf` on unchanged CONTRACT revision 1. R4 validators, hook points and recovery paths are unchanged.

The three remaining before_old_archive failures happened because complete stage/producer and old-paper checks ran before archive metadata and the hook, then `os.rename` moved the live paper with no post-hook recheck. The same R4 complete-set, native-producer and old-payload inventory checks now run again after `before_old_archive` and immediately before rename. A mismatch returns the existing closed conflict/recovery result with extras intact and the old paper still live. Late old-paper edits at this boundary are also refused. Ordinary replacement and interruption/recovery remain passing. No new public interfaces.

Only `light_library.py` and `test_light_library_recovery.py` changed relative to R4. The other seven owner files are byte-identical R4.

## Files
Nine owned paths inventoried. See `handoff.json` files manifest and `snapshot_sha256`. r1-r4 source/evidence remain byte-identical history.

## Tests
- Focused: 90 passed, exit 0, `/private/tmp/t2-r5-final.bdmhvY/focused`
- Related existing PDF/index/workspace/workflow: 95 passed, exit 0, `/private/tmp/t2-r5-final.bdmhvY/related`
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. No copied venv, no installs, no Git mutation.
- Architect real-corpus variants were not run through Cursor. The six premove triggers plus a late old-paper edit were ported into owned synthetic tests.

## Unresolved issues
- Shared artifacts `terminal-2/r5` write succeeded; this complete bundle is the evidence location. No source-local copy was written.
- T3 CLI/Skill/docs are not in this lane and were not edited. No T3 import.
- Dual Python 3.12, installed-wheel, full-suite and Architect real-corpus replay remain Architect work.
- No commit, push, CI, real Vault, or human-gate action was taken.

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
