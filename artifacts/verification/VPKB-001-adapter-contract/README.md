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
Repo Steward reviews both record GO. The exact 21-path architecture delivery is
accepted at head `62f3063fb612024179125bc7d842abdd3de0a4ee`, tree
`37dfbba09e9f73656af4bb5510f7586bb5d4223e`. Fresh run `33481415882`
tested merge preview `910e272879b728aef8d1da1db2ba88d70feba5b0`; all four
Linux/macOS × Python 3.12/3.13 jobs passed 1838 tests. The three post-CI records
remain byte-fixed successor-carried evidence.

Implementation R1 froze ten source/test paths at snapshot
`dbdc7f617c1bddaa8bb25169a779c8a5ad264d555d6ca25066c86e0b886b635d`
and passed 428 focused plus 1888 complete tests on both local Python versions.
Repo Steward nevertheless returned `CHANGES_REQUIRED`: the complete-set check
accepted FIFO, symlink, directory and non-digest content extras plus a transport
root extra. The R1 work package, Builder candidate and Steward review are kept
byte-for-byte.

Revision-2 work package
`transaction-inspect-staging/implementation/implementation-work-package.json`,
SHA-256 `c79ade9aa3b9c70c77250ef3f5a3aa7743c60652b3c4725d5d4e0995a5a67633`,
authorizes only that correction and new R2 evidence. Builder still owns exactly
three production and seven test paths; public `stage_bytes` stays unchanged.
Builder froze the corrected ten-path snapshot
`75179e9d0a66b3d528a14d6cc48be7139d350380be9b945b61eeb18eb6cb4ab2` in
`builder-candidate-r2.json`. Independent `steward-review-r2.json` records `GO`
after 435 focused and 24 adversarial checks plus eight direct probes, including
proof that an unrelated safe digest orphan is not read. Architect then replayed
435 focused checks, 24 lineage/complete-set checks, all four real pinned
operation vectors, 1895 tests on each locked Python version and an installed
wheel containing 24 schemas. The local decision
`PASSED_LOCAL_R2_IMPLEMENTATION_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI` is in
`architect-local-acceptance.json`, SHA-256
`98ec4d0c3a7571fc46e271bed260191f0bbae6b89230bbd69734a5c132126d9b`.
The exact temporary-index delivery review then found one nonsemantic blocker:
`tests/contract/test_transaction_staging.py` ended with two LF bytes, so cached
diff-check returned `new blank line at EOF`. The R2 work package is archived as
`implementation-work-package-r2.json`; its candidate/review, local acceptance,
manifest and `CHANGES_REQUIRED` delivery review remain byte-for-byte history.
Active revision 3, SHA-256
`1ba273bd9ae25f00583a4dac4c881b5eeb0d3796faf8b7cc10fffa34e918ac67`,
authorizes only deletion of that one final LF plus R3 evidence. The corrected
test must have SHA-256
`a24970e839051c43719996ab519b9e1405f1938aa201238d8681fd31c01dc797`;
all other source/test bytes remain fixed. At that gate exact R3 review,
delivery, fresh four-job CI and a separate exact-head Architect acceptance
remained pending.
Builder froze the precomputed R3 snapshot; independent
`steward-review-r3.json` records `GO` at SHA-256
`6c174fa4bfc16c22f4708716937ae2561e67e11defc6b3ddc1a357e838d6d641`.
Architect independently passed 435 focused, 24 adversarial, four pinned-vector
and both 1895-test full suites; the rebuilt installed wheel stayed byte-equal to
R2. `architect-local-acceptance-r3.json` records
`PASSED_LOCAL_R3_IMPLEMENTATION_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI`, SHA-256
`a4ce61b1035960131d7e6484e637464ee0c302ce8242212dc449287ebc86c8a8`.
That local decision permitted only the final R3 exact-path delivery audit before
Git delivery.

The corrected R3 implementation was committed at exact head
`fb2cbcb565195a232f22d02c0474ac1b1b34f7d3`, tree
`4a28ee53f71a0f2971f23b87e1f4c06d3bdf5b79`. Fresh run `33491834331`
tested merge preview `12bc7925140352fad516405b7eafaa8923d106e7`; all four jobs passed
1895 tests. Separate decision
`ACCEPTED_VPKB_001_TRANSACTION_INSPECT_STAGING_IMPLEMENTATION_AT_EXACT_HEAD`
is recorded by the three successor-carried post-CI files in its implementation
directory.

The `staged-pdf-capture-inspect/` subdirectory contains the fourth bounded
subrelease's architecture candidate. Its contract SHA-256 is
`8f9624c98ebbc9ae7eba51e61645291f11bc482f2fde1353e2ec4187f6c9d21f`;
its architecture work-package SHA-256 is
`298ae880c5013c79a3db94dbc05c0d6d1c77eb0af3e507a55d5a2a2752c02421`.
The two closed schemas describe one canonical prepared request with its parsed
desensitized approval-ref and one create/reuse authority. Independent Builder
and Repo Steward reviews returned GO after all retained-lineage, Vault snapshot,
hash graph, encoder compatibility and branch-binding blockers were closed. The
Architect local verification passed Python 3.12/3.13 with 1901 tests each and
an isolated 26-schema wheel. The freeze authorizes exact architecture delivery
only; Builder implementation remains blocked until fresh architecture CI and
separate exact-head acceptance.

Local, wheel, independent review and remote CI observations remain distinct.
Accepting any bounded subrelease will not complete the later `integrity-runtime`
slice or all of VPKB-001. No record here authorizes apply/recover/admin, a real
Vault, network/models, PR readiness, merge, auto-merge or a human gate.
