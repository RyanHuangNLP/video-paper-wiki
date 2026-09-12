# TERMINAL-2 r4 — producer-ownership correction before inventory freeze

## Functionality
Same public T2 APIs as r3 on unchanged CONTRACT revision 1. Input is stopped R3 snapshot `59a62f696bc75b5b4ff0346612dbd380ec45b68f16f73fc7f5546e407123851e`. R3 recovery/backup/history semantics remain in force.

The missing ownership boundary in `_replace_forward` intent is closed centrally:

1. The exact untouched intent-stage shape is validated before native workspace creation or extraction. `after_intent` additions (unknown file, empty directory, or pre-extraction prior-note) refuse without adopting bytes; the old paper stays live.
2. After a successful native extract, the complete producer output is checked against an explicit layout/identity allowlist bound to the intended new digest: supported files and directories, `source.json` paper/source/document bindings, and empty producer lock bytes. A fresh walk/hash is observation only and cannot confer deletion authority on extras.
3. `prior-paper-notes.md` is created only if absent via create-only `os.link` publication. An unexpected existing file, including a post-extract prior-note, is preserved and the call closes as conflict.
4. Complete ownership is validated again after adding that known prior-note file, and only then is the allowlisted inventory frozen. Complete-set plus allowlist checks also run before irreversible old-paper movement and before owned-stage cleanup.
5. Native extract failure discards only a still-clean intent stage. Unknown artifacts and modified locks are preserved on error and on retry.

Ordinary replacement, notes attribution, recognized interruption/recovery points, and successful history/backup cases remain passing. No new public interfaces.

## Files
Nine owned paths only. See `handoff.json` files manifest and `snapshot_sha256`. r1/r2/r3 source/evidence remain byte-identical history.

## Tests
- Focused: 83 passed, exit 0, `/private/tmp/t2-r4-final.bTQpBx/focused`
- Related existing PDF/index/workspace/workflow: 95 passed, exit 0, `/private/tmp/t2-r4-final.bTQpBx/related`
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. No copied venv, no installs, no Git mutation.
- Architect real-corpus variants were not run through Cursor. Precapture/postextract triggers were ported into owned synthetic tests.

## Unresolved issues
- Shared artifacts write result is recorded in `checks.json`.
- T3 CLI/Skill/docs are not in this lane and were not edited. No T3 import.
- Dual Python 3.12, installed-wheel, full-suite and Architect real-corpus replay remain Architect work.
- No commit, push, CI, real Vault, or human-gate action was taken.

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
