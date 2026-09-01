# Base foundation architecture freeze and implementation evidence

This directory records the 2026-09-01 architecture freeze for projection input
revision 1, catalog/generation revision 1, the 34-table/230-column structural DDL,
its 25 semantic checks, the closed generation profile and three new schemas.

Builder and Repo Steward independently reviewed the exact eight-file candidate and
returned GO with zero architecture blockers. The Architect then changed only the two
contract status headers/headings to `FROZEN`; all six machine-resource files stayed
byte-identical. `architect-freeze.json` binds the reviewed and frozen hashes.
Before the first delivery staging, three Markdown hard-break trailing-space pairs in
the Builder review were removed so cached `diff --check` remained clean;
`architect-freeze.json` records both the original and normalized report hashes. The
semantic review text and every frozen authority byte are unchanged.

`freeze-check.py` is a normalized replay of the dual-Python architecture check. It
meta-validates all 21 schemas, runs 38 positive and 190 strict-terminal negative
pattern vectors, resolves the generation schema offline, compares the DDL/manifest
at 34 tables and 230 columns, checks all 25 semantic IDs, the 13/25/8 generation
profile counts, conditional dependencies and the catalog count of 67. Independent
SQLite design evidence also passed 752 probes; SQLite remains writer/DDL evidence and
is not part of canonical row API acceptance or the generation runtime fingerprint.

At architecture-freeze time, `tests/contract/test_schemas.py` still asserted 18 and
therefore gave 30 passes and one failure against the frozen 21-schema tree. Both
reviewers judged that this left no architecture decision open, but it remained an
implementation gate. The later implementation changes the count to 21 and adds the
required title, offline-reference and strict-terminal regressions.

This freeze authorizes only pure supplied-data foundation implementation and tests.
It does not authorize a Vault/filesystem collector, authenticated byte-to-row mapper,
SQLite writer, renderer, search build, real parser/model run, publication, merge or
human-gate transition. VPKB-000 remains in progress until implementation, local/wheel
verification, exact candidate delivery and fresh merge-ref CI are separately accepted.

## Correction-1 local implementation acceptance

The first 18-file Builder candidate is retained as
`vpkb-base-foundation-builder-candidate.json`. Independent review found five blocker
groups and issued the superseding report
`vpkb-base-foundation-steward-review-final-amended.json`: code complete-file/self-hash
conflation, semantic locator-limit error leakage, installed resource ancestor
fallback, row phase/traversal order, and catalog-wrapper generation preflight
classification. The exact counterexamples and correction work package are retained
in this directory.

Builder delivered correction-1 as a 20-file candidate with manifest SHA-256
`6e6e17a6aee81d8e3cb58e476f089c735b70f0861703d924da955f11ceca6c0e`
and snapshot SHA-256
`4cb20593b27df1d09859e54fd3fcbde84fccbe1ce440bd9a370a964bd326a287`.
Only the six authorized correction paths differ from the first candidate. Steward's
independent real-candidate oracle passed 148 checks with zero failures, including 30
vectors and every one of the 25 semantic IDs, and replayed all five blocker groups.
Its GO report is `vpkb-base-foundation-steward-review-correction-1-final.json`, SHA-256
`3afe960fb96e0dc597db44970b09eec603a46b7f7ff67a180412913a1f53c371`.

Architect then ran the complete suite under CPython 3.12.14 and 3.13.13: each passed
1658 tests with zero failures, errors or skips. A fresh offline wheel has SHA-256
`71ff3b1bba686c261921c070826a24ce655e4b7d722164e4a79286288eb2e876`.
Its isolated install ran outside the source checkout, exposed exactly 21 schemas and
the 25 required schema/taxonomy/catalog resources byte-equal to the checkout, and
accepted the independent complete catalog at SHA-256
`bf9194056f58ff6b9160f752138c3071c8eef8a1de36b2e26492f1a282b43d02`.
`architect-local-acceptance-correction-1.json` binds the commands, JUnit hashes,
wheel evidence and limitations.

This is local candidate acceptance only. A candidate commit and fresh four-job PR
merge-ref CI are still required. PR readiness, merge, VPKB-001 byte-to-row mapping,
writers, real Vault/parser/model work and all human gates remain unauthorized.
