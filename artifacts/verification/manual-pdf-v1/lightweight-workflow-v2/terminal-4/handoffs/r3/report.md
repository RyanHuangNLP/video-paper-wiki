# T4 r3 final — Builder candidate after accepted T3 r4

Builder candidate only. Not Architect acceptance. Not a commit, PR, or merge.

## Inputs

- Architect `lane3-r4-acceptance.json` decision `ACCEPTED_LANE3_R4_FOR_FINAL_DOWNSTREAM_INTEGRATION`, SHA-256 `e38415480a548de17f76e6648207cbc14d87d856d75763c589f4606915e7ccd9`.
- T3 r4 handoff==ready SHA-256 `4ffcb15a61fefd22dbdb8e88fe29c19bcec805ce7b87454dd61548309e0b263f`.
- T1 r3 `ac1aadc2e57b28db5359b655a2ac6ac1d4b5db1ca5dd114a414a0f143daaca89` and T2 r4 `e04bab0e3f2f441443b3034ab34f3a536feac236d5519a2bd8cadaecfb9f9ca6` unchanged.
- Historical T3 r3 and T4 r1/r2 needs_input left unmodified. Did not wait for `lane3-r3-acceptance.json`.

## Import

Copied all nine T3 r4 files from immutable `files/`. Versus T3 r3, only `light_workflow.py` and `test_light_workflow.py` changed; the other seven T3 paths and all ten T1/T2 paths kept their accepted bytes.

## Live CLI and publication windows

Two earlier CLI assertion mistakes (kept, contract-consistent):
1. Conflict case used an illegal writing-shaped document on a QA session, so the backend returned `CITATION_MISMATCH` instead of `LIGHT_SESSION_CONFLICT`. Fixed by using a valid different QA document with `[@chunk_id]`.
2. Stale-source case treated `markdown_path` as a process-cwd path. It is workspace-relative; resolve as `workspace / markdown_path`.

After T3 r4 import, publication-edge replay: control `awaiting_model` + 1 session; `last_staged_file_move` and `before_publish_hook` return `ok=false`, `INDEX_STALE`, `session_id=null`, 0 new sessions. Live CLI + T3 tests: **79 passed, 0 skipped**.

## Official verification on frozen 25-path bytes

- One new offline wheel: `video_paper_wiki-0.1.0-py3-none-any.whl` SHA-256 `3b3f08e1e903b1abdfd21a9b141b557ffa237753670739b0e70877044aa08522`.
- First full pytest without `uv` on PATH: 2349 passed, 33 closure setup errors (`pinned uv on PATH`). Historical only; not the official result.
- Official locked Python 3.13 full suite with `uv 0.12.7` on PATH and `LW2_INSTALLED_WHEEL` pointing at that unique wheel: **2382 passed** in 216.92s. No skip from missing light_workflow.
- Isolated venv created by the installed test was copied to scratch `r3-isolated`. Outside-source `-I` smoke: module and `vpwiki-research` console both expose workflow; six new modules match source SHA; 53 schemas match checkout (>=26).

Owned-only extra this revision: `test_light_workflow_installed.py` may copy the isolate to `LW2_INSTALLED_KEEP` so the suite's venv survives pytest tmp cleanup.

## Current-session real PDF trial (trial, not human fact check)

Fresh workspace `real-pdf-trial-r4` on `inbox/arxiv-2204.03458.pdf` (not copied). Evidence rows were byte-identical to the prior session, so the same current-session QA/writing documents were reused as input. Complete/status ran on T3 r4 `light_workflow.py` `e4f7f8880ab41d388ede82f4672e4b969f6ee147e794d02d59359bfa8ee57595`:
- QA session `813d35b2ffa07ce0f49ad7d5bdedf962aac35b361d60148f7fc933a271eb15fb` → `real trial r4 (notes)/qa answer.md`
- Writing session `d11341eb7444bbf15ed1f78aa7ffa15ab8adc22ae026fb3eed439e8a20df6fa1` → `real trial r4 (notes)/writing draft.md`
- Joint href/page-anchor/slice/hash checks passed. Bad complete: `INVALID_CITATION`, no output file.

## Bash/zsh

Both shells: `CLI=(python -B -m video_paper_wiki_research)` substitutions recorded; inspect/add/prepare/complete exit 0 into a spaced output directory.

## Not claimed

No Git/PR/merge. This ready is a Builder candidate for Astra independent review.
