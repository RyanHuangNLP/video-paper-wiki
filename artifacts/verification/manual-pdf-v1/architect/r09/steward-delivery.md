# Architect instruction: serialized delivery of the accepted local PDF candidate

This is the next step in the user's approved flow: four manual terminals → Architect review → Repo Steward commit/draft PR targeting integration → fresh four-matrix CI. The four-terminal task packet has ended; its frozen files stay immutable. This instruction grants Repo Steward the following serialized Git/PR/CI operations, not merge authority.

## Frozen inputs

- Source root: `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`.
- Current branch: `integrate/manual-pdf-pipeline`.
- Expected starting HEAD: `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`; index empty.
- Local Architect acceptance: this directory's `result.json`, SHA-256 `3eb74d7678ab6be87a225f8f7b6173a32426ec1b4f526cbf7e6a8c7f80b7024b`.
- Exact delivery manifest: `artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1/terminal-4/delivery-manifest.json` in the main repository, SHA-256 `495bfac22c41b04e6adea61e3bb5653a8e0e5c718eae209f3775ff1f52e0d5e4`.
- Exactly 70 modified/untracked paths. Canonical path-to-SHA mapping: `bb64af4cc4152a21c2c5d20ecf33441b9bcb30ce7198ae1ccdb2a466d06f5d03` using sorted compact UTF-8 JSON. The mapping is also in `input-check.json` → `current_70_candidate_paths.current_files`.
- Quickstart: `0c66d84539417e7d902925f1144e558b54fe481b79fd8b77258e562a9c74910e`; README `f8395276775c930cf87d0e5a427663083e7a25ae55b1eb577b6383091da6458b`.

## Allowed operations, in order

1. Recheck the exact branch, HEAD, empty index, manifest paths and all SHA values. Read configured Git remotes and live matching PRs/base state. Fetch only the task repository refs needed for accurate head/base and CI identity. Do not switch the shared checkout or alter source. Keep old PR #94 and historical base observations distinct from this branch's actual PR.
2. Save a corrected PR title/body in this directory's new `delivery/` output. Describe the actual local PDF ingestion/research workspace, retrieval and cited QA/writing workflow, publication bridge checks and usable Bash/zsh quickstart. The standalone verifier is local acceptance evidence outside the 70 shipped paths; do not imply it is included. Separate past full-suite results, this round's 19+7 regression/literal-shell checks, and fresh remote CI.
3. Stage only the exact manifest paths, inspect the resulting staged path set/diff/stat, verify staged bytes against all 70 accepted file hashes and run `git diff --cached --check`. Record checks and tree identity. If the staged audit fails, do not commit or edit source: preserve failure evidence, unstage only paths introduced by this operation if needed, and report the precise blocker to Architect.
4. Commit the exact accepted candidate on the current branch. Capture full commit/tree IDs and recheck bytes. No broad add, amend of older commits, reset/clean, force push, rebase, merge, branch switch, submodule change, or edits to reviewed implementation.
5. Push this branch without force to the task repository. If an open PR already exists for this exact head branch targeting integration, preserve its draft status and update the scoped description; otherwise create a new draft PR targeting `integration`. Do not change another PR's source/base or mark a PR ready. Never target main, enable auto-merge, approve, merge, or bypass reviews/protections.
6. Observe the fresh Tests run triggered for the delivered commit. Collect run/attempt, PR head and live base, actual merge-preview checkout SHA and both parents, each of the four Linux/macOS × Python 3.12/3.13 jobs, commands/test counts/conclusions. Do not infer checkout identity from run head alone. Poll at bounded intervals and relay meaningful state. If CI fails, report logs and stop implementation changes for Architect review; do not weaken tests or rerun unchanged failures without cause.

All Git mutations remain serialized under Repo Steward. No other agent writes the candidate. Preserve main-worktree differences, inbox/tools/plans, local full-text trial material, post-CI evidence and all prior frozen artifacts. No files from `.work`, virtual environments or external acceptance directories are included in the commit. Output new delivery records only under this `r09/delivery/` directory (temporary CLI files may use /private/tmp). Never export credentials in logs. Use structured PR body arguments or `--body-file` with a literal file.

Use the environment's standard permissions. If a required action needs sandbox escalation, request it with a precise task-scoped justification. If automatic review rejects it, stop that action, retain unaffected evidence, and report the exact stated reason; do not bypass the restriction.

Report the final commit, PR URL/base/head, four-matrix results, actual checkout identity, exact manifest match and remaining gates. Architect will then decide exact-commit acceptance separately. Merge remains unauthorized.
