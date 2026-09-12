# CI plan (R08, local draft, not executed)

No fetch, push, PR create/update, `workflow_dispatch`, or merge was performed.

Do **not** treat historical R07 17/413/857 mapping hashes, or the pre-copy R08 18-file snapshot `b8b644b0fed9fd0d116a8a427625d468558e3c949fd73258a01d3783a3843569`, as the current post-documentation-integration match.

## Workflow

- File: `.github/workflows/tests.yml` (frozen this round; not edited)
- Four jobs: `ubuntu-24.04`/`macos-15` × Python `3.12`/`3.13`; `fail-fast: false`
- Submodule pin `vendor/claude-obsidian` = `9f8c1199047eac2c3828496279fbb7ba9540b90b`
- `uv sync --locked` then offline doctor + pytest
- No Docling extra, no parser models

## Current local inputs (after T3 quickstart copy)

| Input | Value |
|---|---|
| worktree HEAD | `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f` |
| candidate path count | 70 (same as start; quickstart bytes replaced) |
| README (frozen) | `f8395276775c930cf87d0e5a427663083e7a25ae55b1eb577b6383091da6458b` |
| integration quickstart | `0c66d84539417e7d902925f1144e558b54fe481b79fd8b77258e562a9c74910e` |
| reused wheel | `9e1861d92a3b5fc63159a0d0e6e1aca63eb50e283fb6e008f579ef70fce13b21` (not rebuilt; docs not inside) |
| Python 3.12 local | skipped |
| 2246 Python 3.13 | historical R06 label; not rerun |

## Fields still pending

candidate commit, PR number, live PR base/head, merge preview, Tests run/attempt/jobs, actual CI checkout SHA: all `null`. Historical PR base `08709894adfb20ec07e976783f0ba436d975b74f` is **not** live-verified. `remote_ci_executed=false`.

## Later sequence (Repo Steward, after Architect instruction)

Stage only delivery-manifest paths. Draft PR → `integration` (not `main`). Fresh four-job Tests. Do not relabel historical VPKB/R06/R07 counts as this candidate's CI.

`git_mutations_executed=false`. `architect_accepted=false`.
