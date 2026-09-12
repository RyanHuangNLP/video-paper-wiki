# Draft PR description (not published)

Status of this file: local Terminal 4 draft. No GitHub PR was created or updated. Target remains **draft PR → `integration`**, not `main`.

## Title (proposed)

Light PDF workspace path: native-text extract, index, current-session QA/writing, and user docs

## Summary

This candidate adds the first-version light PDF path on the existing locked default environment:

- `python -m video_paper_wiki_research`: `pdf add`, `index build`, `qa`/`writing` export and import
- pypdf native text only; workspace under `.work/**`; no OCR/Docling models
- Rebuild relocates page Unicode ranges from current Markdown anchors; self-consistent misplaced indexes are `INDEX_STALE`
- QA/writing Markdown rewrites `papers/<sha>/source.md#page-N` relative to the output file's parent; export JSON carries `workspace_root`
- User docs: README light-path lead-in plus `docs/lightweight-pdf-quickstart.md`

Light product/tests for this path were Architect r07 snapshot `ea67d3b857a23ff721f5a53c8b730c78662e014a8dcac9e78816eda1efaab0dd` except README, which Terminal 4 copied from Terminal 3 after freeze (`f8395276775c930cf87d0e5a427663083e7a25ae55b1eb577b6383091da6458b`). New file `docs/lightweight-pdf-quickstart.md` (`6c02145f0627020cf717048162f363a470d64d62fc41f2f71f0ce4b8d8569178`). That 17-file snapshot is **not** the entire uncommitted integration worktree; see `delivery-manifest.json`.

## Local evidence (labels preserved)

- Architect r07: 38 focused light tests; independent SANA replay; `INDEX_STALE` recovery — historical, not this round's full-suite rerun
- R06 Terminal 4: 2246 Python 3.13 tests — historical
- This round: T1 verifier 15 tests + independent negatives; T2 four-paper trial; T3 installed-wheel walkthrough; T4 exclusive wheel SHA-256 `9e1861d92a3b5fc63159a0d0e6e1aca63eb50e283fb6e008f579ef70fce13b21` and isolated smoke

## Still open after Terminal 4 materials-ready

- Serialized Git commit / draft PR → `integration` (Repo Steward, after Architect instruction)
- Fresh four-job Tests (Linux/macOS × Python 3.12/3.13); local 3.12 skipped
- Human gates, real Vault, `vpwiki-admin`, catalog 67-entry changes: out of scope

## CI

See `ci-plan.md`. Run/attempt/jobs/merge-preview: pending. `remote_ci_executed=false`.

## Explicit non-claims

- `git_mutations_executed=false`
- `remote_ci_executed=false`
- `architect_accepted=false`
- Materials-ready is not product publication
