# TERMINAL-2 r1 — paper maintenance and lightweight backup

## Functionality
T2 implements the frozen library maintenance and backup lane:

- `list_papers`, `update_paper_metadata`, `archive_paper`, `restore_paper`, `replace_paper`, `recover_library` in `light_library.py`
- `create_backup`, `verify_backup`, `restore_backup` in `light_backup.py`
- Shared `.work` / text / lock / journal policy in `light_library_state.py`
- `extract_pdf` now takes workspace.lock then the per-paper lock. Replacement extracts into `.light-library/staging/<operation_id>/workspace/` so it acquires only that stage-local lock, not the live workspace lock.
- Archive manifests bind `papers/<digest>` original paths to transport `paper/` without rewriting `source.json.document.path` or calling `_load_paper` on the transport directory.
- Replacement keeps old notes byte-exact in the archive and writes `prior-paper-notes.md` on the new paper.
- Backup ZIP is deterministic ZIP_STORED with `LIGHT-LIBRARY-MANIFEST.json` first. Current workflow sessions remap to `.light-workflow/history/<workspace_id>/sessions/` and are not active after restore.

## Files
Nine owned paths only. See `handoff.json` files manifest and `snapshot_sha256`.

## Tests
- Focused: 16 passed, exit 0, `/private/tmp/t2-r1-final.Z0xXs3/focused`
- Related existing PDF/index/workspace/workflow: 95 passed, exit 0, `/private/tmp/t2-r1-final.Z0xXs3/related`
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. No copied venv, no installs, no Git mutation.

## Unresolved issues
- T3 CLI/Skill/docs are not in this lane and were not edited. T3 should import this snapshot only.
- Knowledge staging refusal is implemented structurally; T1 has not published knowledge records in this worktree.
- Dual Python 3.12 and installed-wheel checks remain Architect/T3 integration work.
- Real inbox PDF / current-model trials remain T3 after both owner snapshots stop.
- No commit, push, CI, real Vault, or human-gate action was taken.

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
