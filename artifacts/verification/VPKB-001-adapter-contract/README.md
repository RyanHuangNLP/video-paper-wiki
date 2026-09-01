# VPKB-001 adapter-contract verification

This directory begins with the accepted architecture/contract freeze for the
first bounded VPKB-001 subrelease: pinned read-only transaction inspection and
isolated captured-file source-ID verification. It also contains the accepted
manual-PDF capture dry-run subrelease and the successor architecture work for
deterministic transaction-inspect staging.

Baseline `acd3821b15e62bce13fa07b82c1665d501f27f67` is the separately accepted
whole-VPKB-000 closure head. Its post-CI records are persisted alongside this
architecture delivery without claiming they were present in that historical
commit. The VPKB-000 decision permits this freeze work only.

Architecture files in this directory:

- `builder-architecture-preparation.json`: Builder's upstream/API archaeology;
- `steward-transition-audit.json`: Repo Steward's VPKB-000 → 001 boundary audit;
- `architect-freeze.json`: Architect's pre-commit scope and contract decision;
- `builder-spec-review-r1.json` and `steward-spec-review-r1.json`: preserved
  pre-freeze blocker reports for the live-checkout ignored-bytecode gap;
- `builder-spec-review-r2.json` and `steward-spec-review-r2.json`: preserved GO
  reviews superseded by the later exact child-environment hardening;
- `builder-spec-review.json`: independent Builder review of exact core bytes;
- `steward-spec-review.json`: independent repository/scope review;
- `freeze-candidate.json`: exact-path manifest, self-excluding its own hash.

The static upstream source profile is
`catalog/claude-obsidian-transaction-inspect-9f8c119-v1.profile.json`. It binds
the public CLI import surface and isolated source-ID dependency to upstream
commit `9f8c119`, tree `b00665e`, version `2.1.1`, and a 21-file snapshot. The
profile also requires each child to execute from a fresh private tree containing
only those verified source bytes, so ignored checkout bytecode is never an
import input. The authority schema records per-inspection transport and facade
evidence without host paths.

The exact architecture freeze was committed as
`be7ecf303af2879459036ed8e6831291f168fac4`. Its four-job merge-ref CI and
separate exact-head Architect acceptance are persisted here as
`vpkb-001-architecture-freeze-ci-observation.json`,
`vpkb-001-architecture-freeze-merge-parents.json` and
`vpkb-001-architecture-freeze-architect-acceptance.json`.

The bounded production adapter implementation now belongs under
`implementation/`:

- `builder-candidate.json` preserves the rejected R1 implementation evidence;
- `steward-review-r1.json` preserves the independent eight-blocker review;
- `builder-candidate-r2.json` binds the corrected seven-file source snapshot;
- `steward-review-r2.json` records independent B1-B8 replay and
  `GO_FOR_ARCHITECT_ACCEPTANCE`;
- `architect-local-acceptance.json` records Python 3.12/3.13 full suites and the
  isolated installed-wheel check;
- `delivery-candidate.json` is the final self-excluding exact-path manifest for
  the implementation commit.

The seven-file implementation snapshot
`2303b5a9919eabc63545e2800411879bf17f36585c3e428c0657b8740945445f` is
accepted at exact head `17c13f6317416f47d2610240aaf905598131e5bc`, fresh run
`33465872376`, merge preview `dd6954f1c2368d83cd6d5f1d5057ed4d20acb327`
and a separate post-CI Architect decision. Its three post-CI records are carried
unchanged by the next architecture delivery.

The `manual-pdf-capture-dry-run/` subdirectory contains the second bounded
subrelease's architecture and implementation evidence. Its revision-3
architecture work package, preserved blocker/GO reviews, freeze manifest and
post-CI records bind the accepted architecture head
`3ab19eda4f417b96d89a0a50b2ce2c05233a8478`, merge preview
`ea86e96fbbbcaf6fbda360679c6e6d209a6151b7` and run `33469912314`. Its
contract is
`docs/ai/contracts/vpkb-001-manual-pdf-capture-dry-run-v1.md`; its schema and
profile are `video-paper-wiki.upstream-capture-authority.v1` and
`claude-obsidian-capture-apply-dry-run-9f8c119-v1`.

Its `implementation/` directory preserves the rejected R1 candidate/review and
the R2 candidate/review. The first exact 22-path R2 delivery was also rejected
when cached diff-check found one blank line at EOF; its revision-1 work package,
local acceptance, manifest, Steward rejection and empty-index rollback are kept
as history. Revision 2 authorizes only that one-byte normalization plus new R3
reviews. The corrected seven-file source snapshot
`c275904d2865cb1560408e1d3ba3894ed172e3a9ecf51c44d5c392e2d5b3a50d`
passed 342 focused checks and 1835 complete tests on both local Python 3.12 and
3.13, four real-child identity-replacement attacks, real pinned create/noop
controls, independent Repo Steward R3 review and an isolated offline
installed-wheel smoke. The final self-excluding manifest covers 28 exact paths.
It was committed at `57c2519425dbccd6bb48a0f82e77699e17afcfb6`; fresh run
`33477484577` tested merge preview
`058ae19131cc418edc42dd8d311354503a0e515b`, with 1835 tests passing in
each of four jobs, and a separate Architect accepted the exact head. The three
implementation post-CI records are carried unchanged by the next architecture
delivery.

The `transaction-inspect-staging/` subdirectory contains the third bounded
subrelease's architecture evidence. Its contract is
`docs/ai/contracts/vpkb-001-transaction-inspect-staging-v1.md`, and its closed
portable result schema is `video-paper-wiki.transaction-staging.v1`. This slice
generates only `.work/<batch>/transaction-inspect/{content/**,bundle.json}`
from a previously validated facade proposal and exact caller-supplied bytes.
R1 Builder and Repo Steward reviews rejected repeated single-file `stage_bytes`
calls because batch/transport replacement between calls could split one logical
transport across directory lineages. Revision 2 preserves those blocker reports
and freezes one retained-descriptor multi-file staging session with named
device/inode rechecks and complete-set verification. It keeps the existing
single-file API unchanged and still uses the accepted read-only transaction
inspect adapter; it does not create business proposals, invoke upstream code,
mutate a Vault, or authorize apply.

The preserved R1 reviews record `CHANGES_REQUIRED`; the exact R2 Builder and
Repo Steward reviews both record GO. Architect verification then passed 44
focused schema checks and all 1838 tests on both Python 3.12 and 3.13. The
isolated installed wheel contains 24 schemas and the staging schema bytes match
the checkout. These results permit only the exact 21-path architecture delivery;
implementation remains blocked pending fresh four-job CI and separate exact-head
Architect acceptance.

Local, wheel, independent review and remote CI observations remain distinct.
Accepting either completed subrelease or the staging architecture will not complete the later
`integrity-runtime` slice or all of VPKB-001. No record here authorizes
apply/recover/admin, a real Vault, network/models, PR readiness, merge,
auto-merge or a human gate.
