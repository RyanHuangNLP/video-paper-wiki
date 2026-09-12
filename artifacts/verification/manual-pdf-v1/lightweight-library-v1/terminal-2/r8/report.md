# TERMINAL-2 r8 — writer UTF-8 filename flags

## Functionality
Surgical deterministic ZIP verifier correction on unchanged CONTRACT revision 1. Input is stopped R7 snapshot `a3d06ca1aeee2673d6057a7bd619562e4a32d9569dba9ee2f50dd41ea81d7f34`.

The raw parser now accepts exactly the existing stdlib writer's filename encoding convention: flag 0 for ASCII names and exactly 0x0800 for non-ASCII UTF-8 names, in both local and central headers, with local/central consistency. Other flag bits, mismatched flags, missing UTF-8 bits, malformed UTF-8 names, and ASCII names marked 0x0800 remain refused. Writer, archive schema, text policy, size limits and the other seven owner files are unchanged.

Only `light_backup.py` and `test_light_backup.py` changed relative to R7.

## Files
Nine owned paths inventoried. See `handoff.json` files manifest and `snapshot_sha256`.

## Tests
- Focused: 109 passed, exit 0, `/private/tmp/t2-r8-final.KEied5/focused`
- Related existing PDF/index/workspace/workflow: 95 passed, exit 0, `/private/tmp/t2-r8-final.KEied5/related`
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. No copied venv, no installs, no Git mutation.
- Architect real-corpus variants were not run. Chinese/Greek create/verify/restore/reuse and header-mutation refusals were ported to synthetic fixtures.

## Unresolved issues
- Shared artifacts `terminal-2/r8` write status is recorded in `checks.json`.
- T3 CLI/Skill/docs are not in this lane and were not edited. No T3 import.
- Dual Python 3.12, installed-wheel, full-suite and Architect real-corpus replay remain Architect work.
- No commit, push, CI, real Vault, or human-gate action was taken.

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
