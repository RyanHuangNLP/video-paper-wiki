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

This freeze contains no production adapter module. Once the exact freeze commit
passes fresh four-job merge-ref CI, Architect writes a separate exact-head
acceptance. That post-CI record will be persisted with the next implementation
delivery. Until then Builder production work remains blocked.

Later implementation evidence belongs under `implementation/` and must keep
local, wheel, independent review and remote CI observations distinct. No record
here authorizes apply/recover/admin, a real Vault, network/models, PR readiness,
merge, auto-merge or a human gate.
