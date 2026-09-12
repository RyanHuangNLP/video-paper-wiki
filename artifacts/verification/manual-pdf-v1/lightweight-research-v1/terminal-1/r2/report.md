# T1 r2 — bounded rewritten-query safety repair

Lane 1 Builder candidate against R2 freeze `b86f08cde78cd67a2b25336105e624e3638ba3b691f0c89866a0508dd8738ebf`, repair specification `2f27c1c5ae06b5628dd08ef76ccc805be28cfa50f6135650813c21a3f02efcca`, and unchanged contract `d1d1ddef4273e37b5f8e30a14ad22f3cb3e6c6fa9782763ed5544d20479f2fab`. Baseline remains `6963292a93ae322eaf9bb563b7b1170dee6a6fc6`. Stopped R1 snapshot `b7554d0e8542d779de1a2b0fa4ed4b113fc2c1853627648d5873dcf4b53f39e0` and its 63 focused passes remain historical. Architect has not accepted this candidate.

## Functionality

All seven FIX-T1-R2 repair groups are applied to the new rewritten export and to live traced-context validation/render/import. Untraced legacy search/export/import keep their established behavior, including silent duplicate selection and workspaces outside `.work`.

1. Non-string route enums (`status`, `name`) are type-checked before set membership. A list or object returns `LIGHT_CONTEXT_INVALID`, never `TypeError`.
2. Oversized numeric values are rejected before float conversion. Candidate score `10**400` returns `LIGHT_CONTEXT_INVALID`, never `OverflowError`. Boolean and nonfinite scores remain invalid; rank and live-score equality checks are unchanged.
3. Duplicate `paper_ids` on `export_rewritten_context` return `LIGHT_SELECTION_INVALID` before the legacy normalizer can drop them. `_normalize_paper_ids` and untraced `export_context` still silently deduplicate.
4. Traced workspaces require `.work` in the given absolute path and the resolved path, with no symlink on any parent or final component. A symlink parent and a workspace entirely outside `.work` raise `WORKSPACE_INVALID`. Legacy `_require_workspace` is used only when `query_plan` is absent.
5. `export_rewritten_context` acquires `try_workspace_lock`. Occupied state returns `LIGHT_WORKSPACE_BUSY` without a `query_plan`. The lock is released on every exit. `_retrieve_fused_plan` / `query_plan_shape_error` / `validate_live_query_plan` do not reacquire it.
6. Live source edges `papers/`, `papers/<digest>/`, `source.md`, and `source.json` are checked on the new route and on live use of a traced context. Symlinked papers roots or paper directories and hardlinked source files return `SOURCE_INVALID` instead of a valid empty `NO_RESULTS` trace. `_paper_dirs` still skips those edges for legacy `build_index`/`search`. Regular empty `papers/` can still emit a valid no-results trace.
7. Strings that cannot encode as strict UTF-8 are rejected before query-plan hashing. Lone surrogates in `query` / `rewritten_query` return `QUERY_REWRITE_INVALID`; the same class of trace strings on import return `LIGHT_CONTEXT_INVALID`. Valid Chinese text is preserved.

## Public result shapes

Unchanged from R1 except the closed refusals above. Successful rewritten export still returns `light-context.v1` plus `query_plan`. Other closed errors omit `query_plan`. Legacy contexts without `query_plan` stay compatible.

## Files

Owned changed paths only:

- `src/video_paper_wiki_research/light_query.py`
- `src/video_paper_wiki_research/light_context.py`
- `src/video_paper_wiki_research/light_index.py`
- `tests/research/test_light_query.py`
- `tests/research/test_light_context.py`
- `tests/research/test_light_index.py`

Canonical six-path snapshot `7c2aea0be5b74eb394670625d4839381c444c471ccb9a8188fcad702ebee1992`.

## Tests

Pinned interpreter `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` (3.13.13) with `PYTHONPATH` set to this worktree `src`. Official focused command exit 0: **66 passed in 0.38s**. Modules resolved to this SOURCE, not the old root checkout. No dependency install, no Git mutation, no Vault write, no model/network client.

## Unresolved issues

T1 R2 is not Architect-accepted. Independent review remains open. T3 still owns CLI/Skill/docs and `--rewrite` wiring. Dual-Python full suites, installed-wheel CLI, and real-paper/current-model trials remain later integrated gates.
