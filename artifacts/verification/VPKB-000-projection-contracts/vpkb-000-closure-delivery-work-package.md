# VPKB-000 whole-packet closure delivery work package

Status: Architect-authorized integration/documentation release. This package
does not yet close VPKB-000; it prepares a new exact delivery head whose fresh
CI and separate Architect decision are required for closure.

## Fixed baseline

- Accepted implementation head: `58ddf533f7c30b66a0f80443d5108f1970365ab2`
- Parent: `951131d7b9cfd59a56abce430b5d5ceb3fe331c1`
- PR: `#94`, open/draft, head branch
  `repair/vpkb000-plan-approval-prepare-follow2`, target `integration`
- Observed base: `08709894adfb20ec07e976783f0ba436d975b74f`
- Accepted merge preview: `1ad9f4063693468454bed9b2207aad54740da2fb`
- GitHub Actions Tests run: `33453091285`, attempt 1, four jobs, each
  `1658 passed`
- Catalog count remains exactly 67.

The three base-foundation post-CI records bind that exact implementation head:

- `base-foundation/ci-observation.json`
  `2faadc8911531a0fe97407a99bfddd048b0aeb106bb6730c32ef1f63c881b95b`
- `base-foundation/merge-parents.json`
  `ebb5ca907499b444acbb7f85d04bf1dca903ace8488f371f46893be72afa2184`
- `base-foundation/architect-acceptance.json`
  `15033085d1739c6d6407c5dea2e40f4be897e688a9462975784bcabd109271af`

## Objective

Create a durable, reviewable closure-delivery candidate that:

1. commits the three exact post-CI base-foundation records without changing
   their bytes;
2. records the independent VPKB-000 completion-matrix audit;
3. updates handoff/task/packet documentation to state that all technical
   reference-head gaps now have evidence while whole-packet closure remains
   pending this new head's CI and Architect acceptance;
4. does not start VPKB-001 production work or change any frozen contract,
   schema, resource, source, test, dependency, workflow, vendor byte or catalog.

## Exact repository ownership

Architect is the only writer for this release. Allowed paths are exactly:

- `artifacts/verification/VPKB-000-projection-contracts/base-foundation/ci-observation.json`
- `artifacts/verification/VPKB-000-projection-contracts/base-foundation/merge-parents.json`
- `artifacts/verification/VPKB-000-projection-contracts/base-foundation/architect-acceptance.json`
- `artifacts/verification/VPKB-000-projection-contracts/base-foundation/README.md`
- `artifacts/verification/VPKB-000-projection-contracts/vpkb-000-closure-audit.json`
- `artifacts/verification/VPKB-000-projection-contracts/vpkb-000-closure-delivery-work-package.md`
- `artifacts/verification/VPKB-000-projection-contracts/vpkb-000-closure-candidate.json`
- `artifacts/verification/VPKB-000-projection-contracts/README.md`
- `docs/ai/packets/VPKB-000-projection-contracts.md`
- `docs/ai/task-index.yaml`
- `docs/ai/codex-team.md`

Repo Steward remains read-only until Architect declares a byte-stable candidate,
then independently reviews exact paths/hashes and alone performs serialized
Git/push/CI collection. Builder has no repository writes in this release.

## Required state wording

- `base_foundation_contract.implementation_status` becomes `complete` and its
  verification becomes `passed-locally-and-ci`, naming the exact accepted head,
  run, merge preview, jobs and evidence.
- `VPKB-000-projection-contracts` remains `in_progress`; phase becomes
  `whole_packet_closure_delivery` and clearly says the technical matrix is
  covered but the new metadata head needs fresh CI and a separate Architect
  whole-packet decision.
- Parent `VPKB-000` remains `in_progress` with the same closure condition.
- `VPKB-001` remains `not_started` and `prerequisite_status: not-satisfied`.
- `AGENTS.md` remains unchanged and therefore continues to prohibit dependent
  production work until closure is accepted.
- No record may imply merge, ready-for-review, auto-merge, review submission or
  human-gate authorization.

## Closure evidence boundary

The completion matrix must bind capture/code evidence, transaction facade,
projection runtime, pinned chunk/BM25/CJK observations, ledger locator,
assessment history, base DDL/row/generation, dependency/source/license inventory,
offline CI and durable handoff. It must preserve each source's limitations:

- dependency evidence is bounded distribution/source/license observation, not
  legal compliance, transitive/model audit or invented PyPI-to-Git provenance;
- base rows do not prove byte-to-row derivation;
- runtime fixtures do not accept retrieval config/gold or a new tokenizer;
- no real Vault, parser/model, admin, writer, mapper, apply, audit, publication,
  merge or human gate is accepted.

## Candidate validation

Before handoff, Architect must verify:

- exact allowed path set and all referenced SHA-256 values;
- the three base-foundation records remain byte-identical to the fixed hashes;
- YAML and every JSON file parse successfully;
- all cross-record head/base/merge/run/job references agree;
- `git diff --check`, no tracked changes outside the allowed list, empty index,
  and all user untracked files preserved;
- catalog count remains 67;
- complete tests pass in the available local Python environments. Any environment
  distinction or unrun check is recorded honestly.

Repo Steward then performs an independent diff/evidence review. Only a GO permits
an exact-path commit and normal push. Fresh four-job PR merge-ref CI must bind the
new closure-delivery head and current base. Architect then issues a separate
whole-VPKB-000 acceptance or returns blockers. No merge or gate action follows.
