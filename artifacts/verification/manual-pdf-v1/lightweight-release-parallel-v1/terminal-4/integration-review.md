# Terminal 4 integration review — lightweight-release-parallel-v1

Role: Builder (Grok Build, Terminal 4). This file is task materials for Architect review. It is **not** Architect acceptance, GitHub approval, or publication.

Source root: `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`  
HEAD (unchanged): `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`  
Branch (local linked worktree): `integrate/manual-pdf-pipeline`  
Baseline.json SHA-256: `06b0c1ac60885e7dd59485a863542fbf8bce0e6f9a2ad41eaab02021798f8357`

`git_mutations_executed=false`. `remote_ci_executed=false`. `architect_accepted=false`. `stopped_writing=true` after `ready.json`.

## Independent preparation

- Packets match `preparation.json`. R07 17-file snapshot `ea67d3b857a23ff721f5a53c8b730c78662e014a8dcac9e78816eda1efaab0dd` matched **before** the Terminal 3 documentation copy. `light_index.py` remains `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8`. 413 product/test/build hashes and 857 source hashes matched the baseline mapping; four original PDFs and protected r07/r06 evidence were unchanged.
- Read-only Git: same HEAD as the starting Repo Steward observation; integration still 10 tracked modifications plus untracked research/parser files (59 then, 60 after the new quickstart). Indexes empty. Historical PR base `08709894adfb20ec07e976783f0ba436d975b74f` was **not** live-verified.
- Local Python 3.12 six-light tests were **not** run. The only starting 3.12.14 interpreter lacks `pytest` and `jsonschema`. The shared `.venv` is 3.13.13 and was not used as a substitute. See `evidence/py312-skip.json`. Historical R06 **2246** Python 3.13 tests remain labelled as that run.

## Terminal handoffs (all `stopped_writing=true`, `status=ready`, `files` rules held)

| Terminal | ready SHA-256 | Product files | Independent check |
|---|---|---|---|
| 1 | `a5148386e518c7fa1be369306e1f756abffd2f1a33d3d98966cd219753cdb906` | `[]` | Artifact hashes match ready; `verify_links.py` `51d67390e22dc3c21f2f4f85b12a9ab78d8c583eb3242f4c8e7c81248661f743`; pytest **15 passed in 0.11s** |
| 2 | `d0b8a6cd0756a69fd029ab4b7a2b58e0d404fc98e014d7347415edde795e0b58` | `[]` | Artifact hashes match ready; four real PDFs ingested; 5 Markdown outputs |
| 3 | `3d53b6ec04ff3730514b0fb04b16eae6c10456d2f685f629779c6083cda506f7` | README + quickstart only | Artifact and draft hashes match; whitelist copy allowed |

Blocking findings reported by T1–T3: none.

## Documentation copy

Guards: integration `README.md` still R07 `ec42b686…` before copy; `docs/lightweight-pdf-quickstart.md` absent; T3 `files` exactly those two paths.

Copied onto the integration worktree (not Git):

- `README.md` → `f8395276775c930cf87d0e5a427663083e7a25ae55b1eb577b6383091da6458b`
- `docs/lightweight-pdf-quickstart.md` → `6c02145f0627020cf717048162f363a470d64d62fc41f2f71f0ce4b8d8569178`

After this copy the R07 17-file snapshot no longer describes the worktree: **only README changed** among those 17. That is expected. Do not relabel the r07 snapshot as this documentation revision.

## Verifier replay (frozen T1 script, not modified)

| Case | exit | ok | notes |
|---|---|---|---|
| T1 pytest `test_verify_links.py` | 0 | 15 passed | independent rerun |
| r07 false-positive sample | 1 | false | workspace file exists; full href does not resolve to it |
| extra wrong relative depth | 1 | false | workspace `source.md` exists; `../../workspace/...` misses |
| T2 five Markdown files | 0 | true | 13 source links; resolved under declared workspace |
| T3 `qa answer.md` + `writing draft.md` | 0 | true | 5 source links; output directories contain a space |

T2 `outputs.json` SHA-256 `d14232880a722626583146aa4eeb003cc59401589c5298ccde6594459bbec4aa`. T3 `outputs.json` SHA-256 `db792f355e46b91f907deb83d3eb41f4f9ca9c4ef20a992a3919d535495d644d`.

## Trial conclusions (T2, not human peer review)

Four native-text PDFs succeeded (30+15+28+31 pages). Repeat add did not duplicate paper directories. Index `paper_count=4`. Three single-paper QA imports succeeded. Comparison required a labelled rewrite after a SANA-only first retrieval. Unrelated lexical query was `NO_RESULTS`. Chinese writing topic was `NO_RESULTS` until an English-topic rewrite; the imported draft cites two papers. Claim review: 15 supported, 0 unsupported, 0 uncertain — source correspondence plus this session's self-check.

T3 walkthrough used inbox `arxiv-2204.03458.pdf` on the existing R06 installed wheel: INDEX_STALE after editing `source.md`, then rebuild OK; legacy restore quasar page 1 / nebula page 2. Chinese question against that English PDF was `NO_RESULTS` (ready.json `exit_code=2`). Session JSON is protocol, not T2 quality evidence.

## Exclusive wheel

Built offline after the documentation copy, into `.work/parallel/lightweight-release-parallel-v1/terminal-4/wheel/` (not the R06 prefix). Wheel SHA-256 `9e1861d92a3b5fc63159a0d0e6e1aca63eb50e283fb6e008f579ef70fce13b21`. Isolated install used locked jsonschema/pypdf overlay **excluding** `_editable_impl_video_paper_wiki.pth` and product trees, then `uv pip install --offline --no-deps`. Installed `cli` / `light_*` SHA match the integration tree; `source_tree_in_path=false`. `-I -B` smoke from `/private/tmp/vp.rel4.wheel`: empty argv exit 2 with usage; pdf add 15 pages; index; QA/writing export/import with protocol JSON; T1 verifier 2+2 source links OK. No PDF copied into the smoke workspace. This wheel is a new documentation-bearing artifact, not the r07 17-file snapshot.

## Unfinished / out of scope

- No Git commit, fetch, push, PR create/update, or remote Tests run. CI IDs remain null in `ci-plan.md`.
- No local Python 3.12 light/entry pass.
- Did not rerun 2246 Python 3.13 tests.
- Catalog remains 67 entries. No real Vault mutation. No `vpwiki-admin`. Human gates remain open.
- T2 comparison/Chinese writing first-pass misses and T3 Chinese `NO_RESULTS` are recorded limits, not silent product hot-fixes.
- Main worktree modifications (`publication.py` and related tests, `AGENTS.md`, etc.) were **not** auto-included.

No blocking product defect was independently reproduced in this Terminal 4 round.
