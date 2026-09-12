# Terminal 4 integration review — lightweight-r08-fix-parallel-v1

Role: Builder (Grok Build, Terminal 4). Task materials for Architect review. **Not** Architect acceptance, GitHub approval, or publication.

Source root: `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`  
HEAD (unchanged): `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`  
Branch (local linked worktree): `integrate/manual-pdf-pipeline`  
Baseline.json SHA-256: `a616c8e5ff3db04a72df65f043b88634c33f02d31448f7a150910e005a80de28`

`git_mutations_executed=false`. `remote_ci_executed=false`. `architect_accepted=false`. `stopped_writing=true` after `ready.json`.

This-round ready SHAs (re-checked at stop, unchanged vs first receipt):

| Terminal | ready SHA-256 | files |
|---|---|---|
| 1 | `5075faa05c8d14c066467a38e851262a8be55ace1c864153c90df457520ebe5c` | `[]` |
| 2 | `b9a849f52ffeee41b4439104723e48d036166b746fc0c46d2da054957d344f05` | `[]` |
| 3 | `00e6f52097ea8c65c1881fe47bf35b442293fdb940058fc71d35fa42c6c76ebe` | quickstart only |

OLD `lightweight-release-parallel-v1` ready files were **not** used as this-round input.

## R08-1 mixed-link verifier

T1 froze `verify_links.py` `1ca5f342517294c1d5ed3ed3974585bc6ede410a15b08d78f84f6ae285120197`. T2 `tested_verifier_sha256` equals that exact file. Independent T4 replay of the **frozen** T2 suite against that CLI (`--verifier`, not an imported OLD module): **7 passed in 0.18s**. Mixed query / Markdown title / unquoted HTML cases refuse (nonzero, `ok=false`, nonempty errors, report written). Valid-only, missing-source-without-query, and ignore-nonsource controls pass. T1 implementation tests independently: **19 passed in 0.14s**. T2 files were not edited.

## R08-2 Bash/zsh quickstart

Copied one file after guards: integration quickstart was still `6c02145f…`, README still `f8395276…`, T3 draft SHA equalled the freeze. Final integration bytes `0c66d84539417e7d902925f1144e558b54fe481b79fd8b77258e562a9c74910e`. README unchanged. No src/tests/lock/workflow drift.

T3 `run-quickstart.sh` `2c1c7cb3…` was executed as `/bin/bash --noprofile --norc` and `/bin/zsh -f` with **T4** workspace/output/PDF/python (not T3 freeze dirs). Wheel interpreter reused; `PYTHONPATH` unset; `-I -B`. Both shells: help via documented `CLI=(python …)` (`paste-help.sh`, `python` on PATH = wheel venv) exit 0; walkthrough pdf add → index → qa/writing export/import all step exit 0. Source-mode `--help` and read-only export also exit 0. Protocol JSON used this-export `chunk_id`s; not T2 quality evidence.

## R08-3 freeze identity

Each this-round ready was hashed against every listed artifact; `stopped_writing=true`; handoff equals ready. Receipts saved. Ready files were hashed again at stop and still match the first receipt. Historical OLD T3/T4 inconsistency is left labelled as history and was not rewritten.

## Link check (frozen verifier)

All this-round T3 (bash/zsh) and T4 doc Markdown plus labelled OLD T2 (13 unique historical links across 5 files) and OLD T3 (5 links) passed. See `evidence/linkcheck.json`. Historical checks are existing-output verification, not a new content trial.

## Candidate count

Starting 70 paths remain **70**. Quickstart was already in that set; only its bytes changed. Do **not** label the old R07 17/413/857 mappings, or the pre-copy R08 18-file snapshot `b8b644b0…`, as the current match. Current 18-file mapping after copy drifts only `docs/lightweight-pdf-quickstart.md`.

## Wheel

Reused `9e1861d92a3b5fc63159a0d0e6e1aca63eb50e283fb6e008f579ef70fce13b21`. Identity-checked (`-I -B`, cwd outside src): installed `cli` / `light_index` under that prefix, SHA match product, `source_tree_in_path=false`. **Not rebuilt.** README/quickstart are **not** claimed inside the wheel.

## Unfinished

- No Git commit/PR/remote four-job Tests. CI IDs remain null.
- Local Python 3.12 still skipped.
- Catalog 67, real Vault, `vpwiki-admin`, human gates untouched.
- Main-worktree `publication.py` diffs not auto-included.

No blocking product defect was independently reproduced in this R08 Terminal 4 round. Product `src/` and repo `tests/` were not edited.
