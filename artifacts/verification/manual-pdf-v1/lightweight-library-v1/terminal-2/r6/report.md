# TERMINAL-2 r6 — retain regular nested paper notes

## Functionality
Correction to the existing complete-paper requirement on unchanged CONTRACT revision 1. Input is stopped R5 snapshot `69fdc89a2f90226602aef198f6d5c4d599c2d1959ecffc2ea5522c3836dcd108`.

The shared live-paper classifier `classify_paper_dir` now inspects regular nested files and directories, including empty directories, without following symlinks. Source-pair identity/content checks and returned field meaning are unchanged. Symlinks, hardlinks, non-regular entries and inspection failures are not complete live papers. Archive's existing scan still owns UTF-8/extension/size policy. Native `_validate_payload` remains exactly two generated source files. R5 ownership checks and the other six owner files are byte-identical R5.

Listing, workspace inspect, metadata updates, same-PDF reuse, archive/restore/retry, replace and interrupted recovery keep the complete regular inventory. Replacement keeps nested old notes only in the old archive with existing prior-note attribution.

## Files
Nine owned paths inventoried. Only `light_pdf.py`, `test_light_library.py` and `test_light_library_recovery.py` changed relative to R5.

## Tests
- Focused: 100 passed, exit 0, `/private/tmp/t2-r6-final.gIJycb/focused`
- Related existing PDF/index/workspace/workflow: 95 passed, exit 0, `/private/tmp/t2-r6-final.gIJycb/related`
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. No copied venv, no installs, no Git mutation.
- Architect real-corpus and inbox PDFs were not read or run. Nested-note cases were ported to synthetic fixtures.

## Unresolved issues
- Shared artifacts `terminal-2/r6` write succeeded; this complete bundle is the evidence location. No source-local copy was written.
- T3 CLI/Skill/docs are not in this lane and were not edited. No T3 import.
- Dual Python 3.12, installed-wheel, full-suite and Architect real-corpus replay remain Architect work.
- No commit, push, CI, real Vault, or human-gate action was taken.

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
