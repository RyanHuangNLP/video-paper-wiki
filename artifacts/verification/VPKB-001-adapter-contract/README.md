# VPKB-001 adapter-contract verification

This directory begins with the architecture/contract freeze for the first
bounded VPKB-001 subrelease: pinned read-only transaction inspection and
isolated captured-file source-ID verification.

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

Local implementation acceptance applies only to seven-file snapshot
`2303b5a9919eabc63545e2800411879bf17f36585c3e428c0657b8740945445f`.
An exact commit, fresh Linux/macOS x Python 3.12/3.13 merge-ref CI and a separate
post-CI exact-head Architect acceptance are still required.

Local, wheel, independent review and remote CI observations remain distinct.
Passing this first bounded subrelease will not complete the later
`integrity-runtime` slice or all of VPKB-001. No record here authorizes
apply/recover/admin, a real Vault, network/models, PR readiness, merge,
auto-merge or a human gate.
