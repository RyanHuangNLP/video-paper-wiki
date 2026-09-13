# VPKB-000 base projection freeze candidate revision 2

Status: exact candidate for independent Builder and Steward freeze review, 2026-09-01. This file is temporary review evidence, not a repository contract and not implementation authorization.

## Exact review set

| File | SHA-256 |
|---|---|
| `docs/ai/contracts/projection-input-v1.md` | `209e052c8692af13fae1d0d932a21b98e61cc707ab83091b71b5bb5d88c533fd` |
| `docs/ai/contracts/projection-catalog-v1.md` | `e08e781b1e4deefdd1300f4123a1581ac3e1f48ea9283da8428b55f10e57776b` |
| `catalog/base-catalog-v1.sql` | `3459beb249e348c869070220fda658cfd95c0f092fc12a18978baf19651a5c8c` |
| `catalog/base-catalog-v1.columns.json` | `439024fa2eed6695725c8fdfbe8d03e982e776160f5548f6201d99caaa0ee50c` |
| `catalog/base-catalog-v1.generation-profile.json` | `7b4e95e7b1ad89e492bab98486de359fe125854215fd2de5e7aaab3f4b8e333a` |
| `schemas/video-paper-wiki.projection-input.v1.schema.json` | `e2788477088eb8e5110c8c2d8e2c160c4c33cb26258da68c72897ddfcaa4169c` |
| `schemas/video-paper-wiki.projection-generation.v1.schema.json` | `38e962a184b9048932103c0b710f98f41e2ed2686c4079628870e8fe98a4c255` |
| `schemas/video-paper-wiki.catalog-rows.v1.schema.json` | `085e76c2b0f4b1f0cf546aa2ebbc44c548456adb2e180c93c5e3b190231373b6` |

## Review deltas

- All 38 patterns in the three new schemas use an ECMA/Python-compatible strict terminal construction and reject LF, CR, CRLF, U+2028 and U+2029 suffixes.
- Generation material now has exact root key `dependencies`, closed `{profile,distributions}` shape, `vpwiki-jsonschema-date-utc-v1`, and profile-owned 5-item CPython 3.13 / 6-item CPython 3.12 exact distribution sets. Whole `uv.lock`, SQLite versions and unrelated installed distributions remain excluded.
- The format profile makes `date` and project UTC validation explicit and forbids success from depending on auto-discovered optional `FormatChecker` providers.
- Canonical row acceptance is pure Python. SQLite >=3.37 remains only the hash-bound writer DDL and independent probe backstop; no SQLite patch, diagnostic or refusal affects row API success or generation.
- Code-manifest rows prove reconstructed identities and declared source/artifact relations. Actual payload/newline/normalization/line/snippet byte truth and byte-to-row derivation remain VPKB-001.
- Claim evidence uses the outer evidence wrapper and outer/nested source/relation equality. Alignment rows contain direct locators and never invent an outer relation.
- Generation and catalog API phase/error/traversal order is explicitly frozen in the candidate docs.
- DDL comment is status-neutral. Structural SQL is unchanged: 34 STRICT tables, 230 columns, 25 semantic checks.

## Evidence

- `/private/tmp/vpkb-base-freeze-delta-check.py`, SHA-256 `ecd1ef9ad9865d9900231c2c757748b2d849f605beea28051cf9938e8eca3109`.
- `/private/tmp/vpkb-base-freeze-delta-check.json`: both CPython 3.12.14 and 3.13.13 passed 21-schema metaschema/ref samples, 38 positive and 190 strict-terminal negative pattern vectors, 34/230 DDL agreement, 25 semantic IDs and catalog count 67.
- `/private/tmp/vpkb-base-freeze-ddl-probes.py`: 752/752 passed under SQLite 3.51.2.
- `git diff --check`: passed.
- Existing `tests/contract/test_schemas.py`: expected pre-implementation state is 1 failed / 30 passed solely because the old test hardcodes 18 while the candidate registry has 21. The implementation work package must change this to 21 and add title/offline-ref/terminal regressions before the final worktree can qualify. This known test debt is not waived.

Review the exact hashes above. Return GO only if the contract can be frozen for the pure foundation implementation without reopening architecture. Do not treat the known schema-count implementation update as already complete, and do not edit the repository or Git state.
