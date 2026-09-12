# Agent 2 r2 review → bounded r3 repair

Architect decision: `CHANGES_REQUIRED_AGENT_2_R2`. This is a repair of existing contract B, not additional product scope or a requirement to spend a fixed number of hours. The 50 submitted tests independently replayed successfully, but the extra probes below reproduced three missing contract behaviors.

## Candidate and ownership

Worktree: `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-2/source`.

Baseline remains `0fcae592acb977c6b422e7de3b2c3e0cf79df5a0`; product contract SHA `559e2b339c192837fa5d6c47f15ea7688f484155b95b2492f28eeee6d940e5dc`; Cursor dispatch SHA `0f1f3f2ff3f20cded965eb88ecb17c56b92a4ac8b5e28683b44cf196043b62d6`.

Rejected r2 production: light_context.py SHA `ef8e41eefb00a66542ec0882e7710c4684e77dd4f6378d10fc8d7b7164b53cc3`; light_index.py SHA `c05abaa47217ca4007c38ecf1072d60479eb1f0c424ec2eebbcdf4e10ee26ac1`. Verify the complete five-file r2 handoff before changing it. Architect authorizes Agent 2 to resume writing only its existing five allowed paths and its own new evidence. Keep every r1/r2 frozen snapshot/ready/report/log and this review immutable. Do not alter another lane, original contract, runtime settings, dependencies, Git, PR or canonical Vault.

## Required repairs

1. **Revalidate after output staging, immediately before installation.** In r2 the final live check is before `_install_bytes`; directory creation and temporary-file writing happen afterward. The Architect probe changes synthetic source.md immediately after `.light-out.tmp` is written, before replace/link. Import still returns OK and overwrites existing user output, while a subsequent live check returns INDEX_STALE. Move/add the decisive live check after staging and before either atomic installation branch. Refusal must clean up only owned temporary output and preserve an existing target or leave a new target absent. Add regressions for both overwrite=True and create-only, with deterministic injection at the actual staging boundary. A check only before staging does not close this case. Do not claim protection against arbitrary edits after the final check; the original bounded-race contract remains.

2. **Handle malformed input with defined closed results.** `context.kind=[]` currently escapes as TypeError from set membership. A current-shaped index whose paper row lacks markdown_sha256 escapes as KeyError through validate_live_context and import_document, although search catches its own path. Validate necessary types/fields before indexing/concatenation; shared freshness helpers must safely reject damaged records for every caller. A bad context returns LIGHT_CONTEXT_INVALID; a malformed index returns INDEX_STALE, with no new output and no change to existing output. Cover missing/null/wrong-type hash fields, non-string kind and malformed lexical records. Do not hide all failures as OK or rely only on a CLI exception wrapper.

3. **Apply selection rules to public `light_index.search`.** export_context normalizes selections, but the underlying public search keeps the old behavior: [] yields NO_RESULTS, blanks are silently removed, and [valid_id,unknown_id] succeeds. Contract B explicitly strengthens the existing search API too. None/[] must mean all; blank/malformed/unknown IDs must return LIGHT_SELECTION_INVALID and empty evidence; duplicates normalize in first-seen order and filtering occurs before top-k. Preserve deterministic ranking and the wrapper/pure-renderer compatibility. Add tests calling search directly, including a selected-paper hit beyond the unfiltered top-k; testing only the export wrapper is insufficient.

## Evidence and acceptance

Read sibling `probe.py` and `probe-results.json` for the exact r2 observations. The original observation script writes its adjacent result file, so do not execute it in this immutable review directory. Copy it to your own new scratch/revision and redirect only its output location before using it as a diagnostic. Add actual assertions to the appropriate owned repository tests for the required corrected outcomes.

Replay the existing six-file 50-test selection plus the new focused regressions using COMMON's short temporary directory and shared Python. Bind actual before/after source SHA to commands, cwd, exit and results. No full suite, wheel or CLI scope expansion on this lane; T4 retains those duties. Full/human/remote verification remain unclaimed.

Publish a new `phase=final` r3 handoff/ready with identical bytes, all five frozen file copies, this repair packet SHA in inputs, the original freeze/dispatch bindings and precise changed-from-r2 list. List source/hash changes for Agent 3/4 to re-import and revalidate. Their existing r2-based work remains historical input, not approval of r2. Stop writing after r3 and return it to Architect; do not label self-checks as Architect acceptance.
