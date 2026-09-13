# VPKB-000 base freeze revision 2 — Builder independent review

Date: 2026-09-01
Role: Builder, read-only architecture review
Verdict: **GO for Architect freeze**
Architecture blockers: **none**

This verdict applies only to the exact eight-file candidate identified by
`/private/tmp/vpkb-base-freeze-revision2-candidate.md` SHA-256
`ee7ccb4b86e9af7df2eff0a7adadc3746a663e11d82a002ce3c800bcbda284d9`.
The supplied delta evidence independently retained SHA-256
`870b14f3a45f2618ea75d704ff37d0cbad42f48fe5091b14e8a76dead67cf96e`.

## Exact candidate hashes

All eight recomputed hashes match the authority list:

| Repository path | SHA-256 |
|---|---|
| `docs/ai/contracts/projection-input-v1.md` | `209e052c8692af13fae1d0d932a21b98e61cc707ab83091b71b5bb5d88c533fd` |
| `docs/ai/contracts/projection-catalog-v1.md` | `e08e781b1e4deefdd1300f4123a1581ac3e1f48ea9283da8428b55f10e57776b` |
| `catalog/base-catalog-v1.sql` | `3459beb249e348c869070220fda658cfd95c0f092fc12a18978baf19651a5c8c` |
| `catalog/base-catalog-v1.columns.json` | `439024fa2eed6695725c8fdfbe8d03e982e776160f5548f6201d99caaa0ee50c` |
| `catalog/base-catalog-v1.generation-profile.json` | `7b4e95e7b1ad89e492bab98486de359fe125854215fd2de5e7aaab3f4b8e333a` |
| `schemas/video-paper-wiki.projection-input.v1.schema.json` | `e2788477088eb8e5110c8c2d8e2c160c4c33cb26258da68c72897ddfcaa4169c` |
| `schemas/video-paper-wiki.projection-generation.v1.schema.json` | `38e962a184b9048932103c0b710f98f41e2ed2686c4079628870e8fe98a4c255` |
| `schemas/video-paper-wiki.catalog-rows.v1.schema.json` | `085e76c2b0f4b1f0cf546aa2ebbc44c548456adb2e180c93c5e3b190231373b6` |

## Independent findings

1. **Strict regular expressions pass.** All 38 `pattern` values in the three new schemas end in `$(?![\s\S])`. Under `jsonschema` 4.26.0 on CPython 3.12.14 and 3.13.13, and under Node 26.8.1 ECMA `RegExp`, each representative valid value passes and each value suffixed by LF, CR, CRLF, U+2028 or U+2029 fails: 38 positive and 190 negative checks per engine. The construction therefore closes Python `$`'s final-newline behavior without relying on a Python-only `\Z`. Its portability claim is limited to the frozen Python/jsonschema path and the checked ECMA implementation.

2. **Dependencies and format profile are closed enough for this pure base.** Generation requires the exact closed `dependencies = {profile, distributions}` object. The profile fixes `vpwiki-jsonschema-date-utc-v1`, strict ordered sets of five distributions for admitted CPython 3.13 tuples and six for CPython 3.12.14, with `typing-extensions==4.16.0` only on 3.12. The two locked environments exactly match those sets and have no `rfc3339-validator`. The prose requires explicit Gregorian `date` and project UTC validation and prohibits success from auto-discovered `FormatChecker` providers. Whole `uv.lock`, unrelated packages and SQLite versions can remain excluded because their behavior cannot enter the frozen pure validators under that rule.

3. **Pure rows and SQLite have a clear authority boundary.** The row API phase order explicitly performs runtime preflight, immutable resource integrity, generation validation, typed table/cell checks, relational checks, the 25 ordered semantic checks, then sorting/JCS. It explicitly never opens SQLite and admits only exact built-in `str`, signed 64-bit `int`, or permitted `None`. SQLite >=3.37 is a writer/probe defense only. The in-memory SQLite 3.51.2 probe repeated 752/752 checks and also demonstrates the intentional gap: STRICT SQL accepts lossless bool/float/string integer coercions and some cross-table semantic disagreement that the pure API must reject.

4. **The code byte boundary no longer overclaims.** The input contract and semantic check `code-origin-manifest` limit base validation to reconstructed closed manifests, proposal/self identities, declared source identity and declared payload/hash/size/newline/line metadata associations. They state that the row validator does not inspect payload bytes and that actual payload, newline, normalization, line/snippet truth and byte-to-row derivation remain VPKB-001. `validate_projection_bytes` binds only each inventory entry to its supplied complete raw bytes, not arbitrary projected rows to those bytes.

5. **Claim and alignment locator domains are distinct.** `claim_evidence` reconstructs the outer evidence wrapper and requires outer source/relation equality with the decoded canonical locator. Alignment officiality/capability rows hold direct locators, have no invented outer relation, and instead bind decoded source/kind/domain and owner membership. Actual PDF text/ref/page/span/bbox and inspected payload truth remain later adapter/mapper work.

6. **Phases and errors are implementable without choosing architecture.** Inventory fixes preflight and full byte-map scanning before hashing and distinguishes `SCHEMA_INVALID`, `PROJECTION_LIMIT_EXCEEDED`, `PROJECTION_INPUT_INVALID`, and `PROJECTION_INPUT_MISMATCH`. Generation fixes seven ordered phases and its remapping/preservation rules. Rows fix eight ordered phases and distinguish resource, generation, limit and row failures. Stable traversal is stated for fields, arrays, manifest tables, input row ordinals and semantic-check order.

7. **Machine closure agrees.** The input schema has 13 unique kind/path branches. The generation profile has 13 implementation names, 25 resource names (exactly 21 schemas plus taxonomy and three catalog resources), and 8 upstream names. The generation profile names itself once but carries no expected self-hash. The column manifest and loaded DDL agree on 34 STRICT tables and 230 columns and list 25 unique semantic-check IDs. The schema directory contains 21 schemas and the seed catalog contains 67 papers.

## Required implementation condition

`tests/contract/test_schemas.py` currently produces **1 failed, 30 passed** because line 30 asserts 18 while the exact candidate contains 21 schemas. This is **not an architecture-freeze blocker**: the intended count, new titles/resources, schema dialect and strict pattern behavior are unambiguous and independently validate now. It **does block final implementation acceptance**. The released implementation packet must own that test, update 18 to 21, and add the promised title, offline-reference and terminal-suffix regressions; final acceptance cannot waive or relabel the current failure.

Other final acceptance conditions already stated by the candidate remain operative: implement the pure APIs and registry/packaging changes, exercise coercion/adversarial cases and both supported Python lines, verify the installed wheel contains all 21 schemas and exact resources, and keep mapper/collector/writer/renderer/VPKB-001+ work outside this freeze.

## Evidence produced

- `/private/tmp/vpkb-base-freeze-r2-builder-machine-py312.json` and `...py313.json`: both pass and reproduce the expected 21/38/190/34/230/25/67 counts.
- `/private/tmp/vpkb-base-freeze-r2-builder-regex-node.json`: Node ECMA regex pass, 38/190.
- `/private/tmp/vpkb-base-freeze-r2-builder-contract-assertions.json`: independent structural and prose-boundary assertions.
- `/private/tmp/vpkb-base-freeze-r2-builder-ddl-probes.json`: 752 passed under SQLite 3.51.2.
- `/private/tmp/vpkb-base-freeze-r2-builder-test-schemas.log`: exact known debt, 1 failed/30 passed.

No repository, Git, Vault or network state was modified by this review.
