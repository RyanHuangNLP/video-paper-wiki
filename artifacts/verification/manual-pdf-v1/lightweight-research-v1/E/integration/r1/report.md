# lightweight-research-v1 integration r1

## Functionality
T3 integration r1 wired the frozen CLI routes, secure workspace handoffs, mutually exclusive required apply choices, optional workspace-only `--rewrite`, and writing-aware backup under the existing workspace lock. Intact unwritten or partial writing drafts remain valid backup history; pending publication still blocks backup. Skill/docs tell the current model the exact section fields including `project_id`. Users never author internal JSON. Workflow kinds remain `qa|writing` only.

Owner T1/T2/T3 R3 implementation modules stayed read-only. The two backup paths transferred from T2 at the recorded import point and were edited only for writing-state recognition plus tests. 14 other imported owner files still match `integration-input-import-r1.json`.

## Files
Twelve owned paths. See `handoff.json` `files` and `snapshot_sha256`
`b35aed34d120cb45d932c421448e0322a4a161d25428e016ac264f64deda63e7`.
Imported accepted owner bytes are listed separately in `inputs` and bind snapshot
`9b600ec6fcbdab98e4dae0e91cb8ec6973d2fc885f0030ae0ebe05ab8cb3bcef`.

## Tests
- COMMON exact source scoped pytest: 309 passed, exit 0, `/private/tmp/integration-r1-final`
- Isolated installed-wheel research check is included in that 309
- skill-creator `quick_validate.py`: Skill is valid!
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. Not a root editable import.
- uv uv 0.12.7 (61291a8ca 2026-08-27 aarch64-apple-darwin) at `/Users/huangzhanpeng/.hermes/bin`; no copied venv, no installs, no Git mutation.
- Observed at `2026-09-08T14:29:45.606870+00:00` via `datetime.now(timezone.utc)`.

## Unresolved issues
- Architect dual Python 3.12/3.13, official installed-wheel replay, real three-PDF current-model trials, and exact-head PR95 CI were not run by this Builder and are not claimed passed.
- This Builder wrote evidence only under `SOURCE/.work/integration-r1-evidence`. Official root evidence transfer remains the controller's later authorized action.
- No commit, push, merge, real Vault/admin, or human-gate action was taken. `architect_accepted` remains false.
- terminal-3/r3 writing-project evidence remains history and was not overwritten.

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
