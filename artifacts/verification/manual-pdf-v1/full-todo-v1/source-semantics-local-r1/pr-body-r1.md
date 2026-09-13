## Summary

Add the frozen SOURCE-SEMANTICS implementation and tests across its exact 29-path allowlist. The change adds version-aware source association, assessment history, canonical compilation, Markdown location handling, and the v2 schemas while preserving the legacy v1 delegation and byte behavior required by `SOURCE-SEMANTICS-R2.md` and the R3 legacy PDF `bbox` amendment.

The candidate is prepared from accepted combined head `97a533a08222d59d46a8de5dfd4047050cd945c5` and retains the accepted 23-path source/preview integration at snapshot `f8efad4bdc8ebeb32809d8ba3a5d4266b6ce77a03a8dd03cac40077427b9cdd7`. The 29-path SOURCE-SEMANTICS snapshot is `b06328417faaf1abac4ae39b8fa5521a72a8c58297d6194a5dd48c91c4c526c5`.

## Validation

- Python 3.12: `3107 passed`.
- Python 3.13: `3107 passed`.
- The pinned `vendor/claude-obsidian` checkout is populated, clean, detached, and exactly at `9f8c1199047eac2c3828496279fbb7ba9540b90b`.
- The bounded installed-wheel audit passes across Python 3.12 and 3.13: 232 package files and 236 wheel entries are byte-consistent, all 14 selected SOURCE-SEMANTICS package files match, isolated imports succeed, and the packaged top-level schema registry contains exactly 65 schemas.
- The temporary-index `git diff --cached --check` passes for the exact 29 delivery paths.
- No tracked case-insensitive PDF paths are present.

The earlier integrated replay with an empty vendor checkout remains immutable historical evidence. Its result was 68 failed, 3008 passed, and 31 errors. The repaired preparation, corrected evidence labels, and fresh full-suite results are recorded separately. The R2 registration result is retained as fresh proof; its bad prior-review link is corrected by the R3 evidence correction, while the separate current registration review remains the GO review.

## Scope and delivery state

The final delivery manifest is `artifacts/verification/manual-pdf-v1/full-todo-v1/source-semantics-local-r1/delivery-manifest-r1.json`. It contains only the frozen SOURCE-SEMANTICS 29 paths and bounded evidence for their contract, candidate, reviews, vendor correction, local acceptance, full suites, wheel audit, and the previously accepted 97a533a combined head. Future SOURCE-PUBLICATION schemas, bridge notes, and unrelated source-ownership work are outside this delivery.

Architect local acceptance passed for this exact working-tree snapshot (`architect-local-acceptance-r1.json`, SHA-256 `c050d999fb3c9444dae6b1086eea5beedd96dbf3a20261d7537276483f0a21bd`). Exact commit creation, fresh remote CI, merge, and human gates remain pending.
