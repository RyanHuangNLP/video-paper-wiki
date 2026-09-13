# VPKB-000 base-foundation correction 1 work package

Authority: Root Architect (`gpt-5.6-sol`, ultra)

Implementer: `/root/builder_medium` (`gpt-5.6-sol`, medium), sole repository
writer for this correction.

Independent reviewer after handoff: `/root/repo_steward_medium`
(`gpt-5.6-sol`, medium), read-only until the Builder declares a new stable
candidate.

## Bound candidate and review

- Original implementation work package:
  `/private/tmp/vpkb-base-foundation-implementation-work-package.md`, SHA-256
  `5037f5c011583504627fad0849b22ed9b7c4a572968599ecbc4f100fe417d6bc`.
- Addendum 1 SHA-256
  `6428e7f9f6d34c1183729c3cb0a5c47c6c792618c2d80f406e5d25110b98efb9`.
- Addendum 2 SHA-256
  `6a1887883c9de14b02d0201c8899817a6474bd6c1703e03d3d431751c5f5301e`.
- Builder candidate manifest:
  `/private/tmp/vpkb-base-foundation-builder-candidate.json`, SHA-256
  `afe88f3437898ca3eb4641d18e367be20717fca45386c53abb64542560aa57ce`.
- Bound 18-file source snapshot SHA-256:
  `b28a1e3d441c6d089477bdce9efabbafbacaceae278969d208132bd5cc4625f8`.
- Superseding independent review:
  `/private/tmp/vpkb-base-foundation-steward-review-final-amended.json`, SHA-256
  `3accab5273b006556a9fe3404a244639ad28d037a1fb037111ad6d842e0791b0`;
  Markdown SHA-256
  `0ae8b4155f1d1b8a75f2a53f6ca38b86e54a298b88a9a4339fc41882ed6c30c4`.

The amended review supersedes the earlier final report. Its five blockers are
normative for this correction. The independent claim-evidence permutation check
disproved that proposed issue; do not change evidence ordering for it.

## Frozen read-only inputs

Do not edit either normative contract, the DDL, the column manifest, the generation
profile, or any of the three new schemas. Their frozen hashes remain:

- projection-input contract: `79a500abca2406f060b9363b4675bd07b9fedbbccf78e2aac058763de13892c8`
- projection-catalog contract: `c0628175053da604267005a643020f03de9018b93132fd378b9ac57e8e8366bc`
- DDL: `3459beb249e348c869070220fda658cfd95c0f092fc12a18978baf19651a5c8c`
- column manifest: `439024fa2eed6695725c8fdfbe8d03e982e776160f5548f6201d99caaa0ee50c`
- generation profile: `7b4e95e7b1ad89e492bab98486de359fe125854215fd2de5e7aaab3f4b8e333a`
- projection-input schema: `e2788477088eb8e5110c8c2d8e2c160c4c33cb26258da68c72897ddfcaa4169c`
- projection-generation schema: `38e962a184b9048932103c0b710f98f41e2ed2686c4079628870e8fe98a4c255`
- catalog-rows schema: `085e76c2b0f4b1f0cf546aa2ebbc44c548456adb2e180c93c5e3b190231373b6`

## Exact write scope

Builder may modify only:

- `src/video_paper_wiki/projection_catalog.py`
- `src/video_paper_wiki/resources.py`
- `tests/test_projection_catalog.py`
- `tests/contract/test_schemas.py`
- `tests/contract/test_additional_properties.py`
- `tests/fixtures/projection-catalog/**`, only if a static regression fixture is
  materially clearer than an in-test construction

All other source/test files in the original candidate are read-only. Root-owned
packet/task/evidence documents are out of Builder scope. Do not stage, commit, push,
change PR state, use the network, run SQLite, touch a real Vault, or modify the five
user documents, `.DS_Store`, `inbox/`, or `tools/`.

## Required corrections

1. **Separate complete-file SHA from manifest self hash.** Remove the equality
   between `canonical_inputs[input_path].file_sha256` and
   `code_manifests.manifest_sha256`. The inventory/path SHA continues to identify the
   complete file. Reconstructed code manifests must still pass the frozen
   `validate_code_evidence_manifest` self-excluding hash and all existing declared
   source/capture/payload relations. Do not inspect payload bytes or add VPKB-001
   byte-to-row authority. Counterexample JSON SHA-256:
   `dcfc1c1508a09af2b51645667b13d26c5d0743bfecdde665c5dbd6a9f83ef794`.

2. **Classify catalog-wrapper preflight by subtree.** Preserve
   `PROJECTION_LIMIT_EXCEEDED` from the phase-1 virtual-root preflight. For other
   preflight errors, a pointer under `/generation_material` maps to
   `PROJECTION_GENERATION_INVALID`; a pointer under `/tables` maps to
   `CATALOG_ROWS_INVALID`. Do not run another traversal or change which failure wins.
   Counterexample SHA-256:
   `c6c070a32262fd5708428a6efe24019d555f1d903284c987f78677cc84f3a3d5`.

3. **Do not leak a semantic local limit.** Once generation validation has completed,
   any row semantic/history/locator failure, including the ledger locator's local
   65,536-byte limit, maps to `CATALOG_ROWS_INVALID`. Phase-1 limits and limits raised
   during phase-3 generation/inventory validation remain
   `PROJECTION_LIMIT_EXCEEDED`. Counterexample SHA-256:
   `185f7b48e2630f9471d48082cf5163c13fdc58e49e8cf7e23dfd510d43070d20`.

4. **Implement the frozen row phases, not a sorted mixed loop.** Use distinct passes:
   complete collection/name/column/row-shape validation first; then exact scalar,
   null/range/enum/table-CHECK/presence validation in manifest table order, input row
   ordinal and manifest column order; then PK, UQ, FK and ordinal closure with the
   same stable discipline. Only after those passes run the 25 semantics in their
   frozen order. Preserve original caller row ordinals for diagnostic pointers and
   preserve canonical row/table sorting behavior. Counterexample SHA-256:
   `22d43a24b4f81fdafcc936e223babeb8ebb988f14358b3e94a633e79a3a8ba6e`.

5. **Bound source-checkout resource fallback.** Package resources remain first. A
   repository fallback is allowed only when this module itself is in the exact
   `<repo>/src/video_paper_wiki/resources.py` source layout. Apply the same bounded
   source-root decision to projection bytes, registry schema loading, and schema
   enumeration. An installed-package miss must return missing even if its CWD or an
   arbitrary ancestor contains `catalog/`, `taxonomy/`, or `schemas/`. Preserve old
   seed/public behavior outside these new projection/registry paths unless the narrow
   helper can be shared without changing it. Counterexample SHA-256:
   `4becf4ca827ba25473bc1fa0938385e1e293bc3e96cd3e0635f46e0bdd6aa8e9`.

6. **Correct the generic closure test, not the frozen schema.** The `runtime` parent
   is already a closed six-field object. Its three `oneOf` children are conditional
   overlays. Add a path-exact exception for only those three fragments while keeping
   the existing broad closure test, and add assertions that the parent remains
   closed and each branch has only `properties` containing the exact
   `python_version`/`unicode_version` const pair. Do not edit the schema.

## Required regression evidence

- A valid catalog whose code complete-file SHA differs from the self hash accepts;
  a wrong self hash still refuses.
- The three generation preflight cases (cycle, surrogate, dict subclass) report
  `PROJECTION_GENERATION_INVALID` through the catalog API; analogous table-subtree
  errors report `CATALOG_ROWS_INVALID`; phase-1 and phase-3 limit preservation is
  regressed.
- A row locator below the 64 MiB phase-1 budget but above the ledger local limit
  reports `CATALOG_ROWS_INVALID`.
- All three phase-order counterexamples report the frozen winner, including identical
  winner under caller table reversal. Valid table/row permutations still produce
  byte-identical canonical output.
- Installed-package simulations reject missing projection resources and schema
  enumeration despite ancestor decoys; exact source-layout fallback still works; CWD
  never qualifies an installed build.
- The generic additional-properties suite passes without weakening its existing open
  envelope assertions.
- The independent contract-valid catalog baseline
  `/private/tmp/vpkb-base-foundation-steward-review-complete-baseline.json` (SHA-256
  `3ec24475b08de892682968f2616b3aa0d95e977ace55a54814288664dc8d4199`)
  must accept with catalog SHA-256
  `bf9194056f58ff6b9160f752138c3071c8eef8a1de36b2e26492f1a282b43d02`.

Run the focused owned tests, the complete security/source guard, `git diff --check`,
and a full Python 3.13 suite with cache disabled and a short `/private/tmp` basetemp.
AF_UNIX `bind` failures caused solely by the managed sandbox must be reported
separately, never relabeled as candidate failures. Do not mutate the project to work
around the sandbox.

## Handoff

When done, stop all writes and produce a new machine-readable candidate manifest in
`/private/tmp`. It must list every file in the complete base-foundation candidate,
not just changed correction files, with lowercase SHA-256 and the same snapshot
formula used by the first candidate:

`path UTF-8 + NUL + 64 lowercase ASCII file SHA hex + LF`, paths sorted by
repo-relative ASCII bytes; SHA-256 the concatenation.

Report the manifest path/hash, complete snapshot hash, exact changed paths, test
commands/results, frozen-hash replay, `git diff --check`, index state, and all
unrun/environment-limited checks. Steward receives write authority only after Root
accepts that handoff as a stable candidate.
