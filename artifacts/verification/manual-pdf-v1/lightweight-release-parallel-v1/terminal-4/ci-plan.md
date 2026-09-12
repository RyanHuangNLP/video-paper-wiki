# CI plan (local draft, not executed)

This is a Terminal 4 planning record for a later serialized GitHub Actions run. No fetch, push, PR create/update, `workflow_dispatch`, or merge was performed in this round.

## Workflow

- File: `.github/workflows/tests.yml`
- SHA-256 (integration and main, unchanged vs baseline): `a46548e0649e2cb830d693a17b1d39426a95dffd5878c6cc07624fcd5be22bd2`
- Name: `Tests`
- Triggers that would apply after a real draft PR → `integration`: `pull_request` to `integration` or `main`; `push` to `integration`; `workflow_dispatch`
- Permissions: `contents: read`
- Concurrency: `tests-${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`

## Matrix (four jobs)

| Job name pattern | `runs-on` | Python | Timeout |
|---|---|---|---|
| `ubuntu-24.04 / Python 3.12` | `ubuntu-24.04` | `3.12` | 15 min |
| `ubuntu-24.04 / Python 3.13` | `ubuntu-24.04` | `3.13` | 15 min |
| `macos-15 / Python 3.12` | `macos-15` | `3.12` | 15 min |
| `macos-15 / Python 3.13` | `macos-15` | `3.13` | 15 min |

`fail-fast: false`. Each job: checkout pin `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd` (v6.0.2), uv `astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78` (v7.6.0) with uv `0.12.7`, submodule pin `vendor/claude-obsidian` = `9f8c1199047eac2c3828496279fbb7ba9540b90b`, `uv sync --locked`, then `uv run --offline --no-sync` doctor + pytest with a short real `--basetemp`. Env: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. No Docling extra, no parser models.

## Current source / dependency hashes (local integration worktree)

These are inputs, not a CI checkout SHA.

| Input | SHA-256 | vs baseline |
|---|---|---|
| R07 17-file snapshot | `ea67d3b857a23ff721f5a53c8b730c78662e014a8dcac9e78816eda1efaab0dd` | match |
| `product_and_test_files` mapping (413) | `8a017dadceda212fc195c6b86fddff1bc12ce57890ee8821be830f90beec4300` | match |
| `source_files` mapping (857) | `d4238a97af4aa8f0d79b023efa2d3bb0ac2fe7d0f351437b6836b05e6611f9b2` | match |
| `pyproject.toml` | `da3765ef066d5e431862ad1854aa018d54db0574102823502e940b89fa87c9f6` | match |
| `uv.lock` | `67e928d696ad5e73e3635a67c8b231867734a0b93ba937cbb0a58b655d64afc0` | match |
| `src/video_paper_wiki_research/light_index.py` | `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8` | match |
| worktree HEAD | `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f` | same as starting observation |

Local Python 3.12 six-light + entry checks were **not** run (see `evidence/py312-skip.json`). They remain a remote-matrix item. This round did **not** rerun the historical Python 3.13 2246-test suite. That count stays labelled as the R06 Terminal 4 / Architect r07 historical run.

## Fields still pending (no live GitHub query)

| Field | Value |
|---|---|
| candidate commit | `null` (no Git write this round) |
| current PR number | `null` (not created/updated this round) |
| current PR base | `null` (historical `08709894adfb20ec07e976783f0ba436d975b74f` is **not** live-verified) |
| current PR head | `null` |
| merge preview SHA | `null` |
| Tests run id | `null` |
| Tests attempt | `null` |
| Tests jobs | `null` |
| actual CI checkout SHA | `null` |
| remote_ci_executed | `false` |

## Intended later sequence (Repo Steward, after Architect instruction)

1. Stage only the exact delivery-manifest paths (no blanket add).
2. Commit on `integrate/manual-pdf-pipeline` (or the instructed branch) without rewriting reviewed source during acceptance.
3. Open or update the **draft** PR targeting `integration` (not `main`).
4. Observe a **fresh** four-job Tests run on the merge preview; record run/attempt/jobs and the actual checkout SHA.
5. Do not treat historical VPKB or R06 counts as this candidate's CI.

`git_mutations_executed=false`. `architect_accepted=false`.
