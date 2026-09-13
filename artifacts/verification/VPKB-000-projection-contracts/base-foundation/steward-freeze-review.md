# VPKB-000 base projection revision-2 independent freeze review

**Verdict: GO for Architect architecture freeze of the exact eight reviewed files.**

This is not implementation acceptance, delivery approval, Git authorization, PR
approval or merge authorization. The exact current checkout still has one known test
failure and therefore is **NO-GO for implementation delivery** until condition C1 is
completed and the final implementation candidate passes its full acceptance sequence.

## Exact authority and hashes

The two temporary authority files match the supplied digests:

- `/private/tmp/vpkb-base-freeze-revision2-candidate.md`:
  `ee7ccb4b86e9af7df2eff0a7adadc3746a663e11d82a002ce3c800bcbda284d9`
- `/private/tmp/vpkb-base-freeze-delta-check.json`:
  `870b14f3a45f2618ea75d704ff37d0cbad42f48fe5091b14e8a76dead67cf96e`

I independently recomputed all eight reviewed worktree hashes; each equals the
candidate table:

| Path | SHA-256 |
| --- | --- |
| `docs/ai/contracts/projection-input-v1.md` | `209e052c8692af13fae1d0d932a21b98e61cc707ab83091b71b5bb5d88c533fd` |
| `docs/ai/contracts/projection-catalog-v1.md` | `e08e781b1e4deefdd1300f4123a1581ac3e1f48ea9283da8428b55f10e57776b` |
| `catalog/base-catalog-v1.sql` | `3459beb249e348c869070220fda658cfd95c0f092fc12a18978baf19651a5c8c` |
| `catalog/base-catalog-v1.columns.json` | `439024fa2eed6695725c8fdfbe8d03e982e776160f5548f6201d99caaa0ee50c` |
| `catalog/base-catalog-v1.generation-profile.json` | `7b4e95e7b1ad89e492bab98486de359fe125854215fd2de5e7aaab3f4b8e333a` |
| `schemas/video-paper-wiki.projection-input.v1.schema.json` | `e2788477088eb8e5110c8c2d8e2c160c4c33cb26258da68c72897ddfcaa4169c` |
| `schemas/video-paper-wiki.projection-generation.v1.schema.json` | `38e962a184b9048932103c0b710f98f41e2ed2686c4079628870e8fe98a4c255` |
| `schemas/video-paper-wiki.catalog-rows.v1.schema.json` | `085e76c2b0f4b1f0cf546aa2ebbc44c548456adb2e180c93c5e3b190231373b6` |

Any change to these normative bytes requires renewed review.

## Independent findings

### Schemas and strict patterns

- Exactly 21 registry schemas are present. All pass Draft 2020-12 metaschema checks.
  The existing production offline registry loads the three new titles, and a complete
  generation-shaped object resolves the generation-to-input `$ref` without network.
- The three new schemas contain exactly 38 `pattern` keywords. Using JSON Schema's
  search semantics, 38 independently chosen positive witnesses matched and all 190
  positive-plus-suffix variants (`LF`, `CR`, `CRLF`, `U+2028`, `U+2029`) failed.
  Every pattern ends in the same ECMA/Python-compatible strict terminal construction.
- The generation root is closed with exact key order
  `schema,profile,inventory,implementation,resources,dependencies,upstream,runtime`.
  `dependencies` is closed as `{profile,distributions}` and every distribution item is
  closed as `{name,version}`. Application/profile validation, rather than schema shape
  alone, owns the conditional exact array.

### Dependency and format closure

- The format profile is exactly `vpwiki-jsonschema-date-utc-v1`. The contract fixes
  real Gregorian `date`, project UTC grammar, one-to-nine fractional digits where
  admitted, literal `Z`, and no leap seconds; it forbids success from depending on
  auto-discovered optional `FormatChecker` providers.
- CPython 3.12.14 maps to the five common distributions plus
  `typing-extensions==4.16.0`; CPython 3.13.13 and 3.13.15 map to exactly the five
  common distributions. Names, versions and ASCII order match the machine profile.
- The whole `uv.lock`, SQLite runtime/library version and unrelated installed
  distributions do not enter generation. The exact DDL/column/profile resource names
  remain material, as intended. This removes environment-wide staleness while retaining
  the resources that define canonical output.

### DDL, manifest and row boundary

- Independent in-memory PRAGMA comparison found exactly 34 STRICT tables and 230
  columns. Column order/type/nullability/PK position, UQ keys, complete FK
  columns/targets/actions and strict flags all match the manifest. All 54 declared FKs
  have 54 `DEFERRABLE INITIALLY DEFERRED` clauses.
- The 25 semantic IDs are unique and in the frozen manifest order. A separate replay
  of the prior independent design probe produced 752/752 passes on SQLite 3.51.2.
- Canonical row acceptance is now explicitly pure Python. SQLite affinity, runtime
  version, diagnostics and writer failures cannot decide row-API success or generation.
  SQLite remains a hash-bound DDL/writer compatibility backstop.

### Code, locator, phases and guarantees

- Claim evidence reconstructs the outer `{source_id,relation,locator}` wrapper and
  checks outer/nested source and relation. Alignment rows instead contain direct
  PDF/code locators and cannot invent an outer relation.
- Code rows reconstruct frozen manifest identity and declared capture/source/artifact
  relations. They do not claim payload/newline/normalization/line/snippet byte truth;
  actual byte-to-row proof remains VPKB-001 mapper authority.
- Both public APIs now state total phase order, earlier-phase precedence and the typed
  error surface: limits, generation invalidity, packaged-resource mismatch and row
  invalidity remain distinguishable. No SQLite error is part of the row surface.
- The 67-entry seed remains 67. Machine resources contain no local absolute path or
  review-state marker. Domain values such as `unverified_candidate`,
  `evidence_status`, and the existing `paper-analysis-draft` schema name are business
  fields, not candidate-status leakage.

## Known test debt and freeze decision

The exact focused command

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q \
  tests/contract/test_schemas.py --basetemp=/private/tmp/vpkb-r2-schema-test
```

returns exit 1 with **30 passed, 1 failed**. The sole failure is the pre-existing
`tests/contract/test_schemas.py:30` assertion that schema count is 18; the reviewed
registry contains 21.

This does **not** block architecture freeze because it neither changes nor exposes an
unresolved normative decision: the three exact schemas are valid, strict, and resolve
offline, while the candidate explicitly assigns the count/title/reference regression
to the subsequent implementation work package. It does block implementation acceptance
and delivery. No final worktree, wheel or CI result may be called green until Builder:

1. changes the count to 21 and adds explicit new-title/offline-reference/terminal tests;
2. implements the exact dependency/format and phase/error rules without changing the
   frozen contract bytes;
3. packages all 21 schemas and three catalog resources; and
4. passes focused, full two-Python, isolated-wheel and fresh PR merge-ref CI acceptance.

## Scope and process boundary

Local HEAD remained `951131d7b9cfd59a56abce430b5d5ceb3fe331c1` on
`repair/vpkb000-plan-approval-prepare-follow2`; the index was empty and
`git diff --check` passed. The existing `.DS_Store`, five user documents, `inbox/` and
`tools/` remained untracked. This review performed no repository/Git/PR mutation and,
under the explicit no-network constraint, did not refresh remote PR state. Remote PR
state is not evidence for this architecture-freeze verdict.

Independent evidence:

- `/private/tmp/vpkb-base-freeze-r2-independent.py`, SHA-256
  `cb6c94ef754d4c20ec0e3a96519fbef2b9f808e5b6c2a2d4685f783ef4d3ac48`
- `/private/tmp/vpkb-base-freeze-r2-independent.json`, SHA-256
  `b0fed72b9117cc41f93546e803ec527c8da1e2a14033f6cf3e230603054c55fe`
- `/private/tmp/vpkb-base-freeze-r2-schema-test.log`, SHA-256
  `dcc50d29c41d349527412b2839aa9113ff3c0aca0460e735d14e0c21cb719fdd`
- `/private/tmp/vpkb-base-freeze-r2-ddl-probes.log`, SHA-256
  `465bb4d4a974d59951e270e7c7e5a15889298e458d6d4f0d3c6bf543741c744b`
- `/private/tmp/vpkb-base-freeze-r2-steward-review.json`, SHA-256
  `41a938a6cbff124c100986e1d8417486a779312d7794cdbe6f2cfa64f31672e3`
