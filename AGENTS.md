# Codex team working agreement

The current team uses Codex for all three roles. Do not dispatch work to Grok
Build or activate the historical Grok/Feishu loop. Later explicit user directions
take precedence over this agreement.

Read `docs/ai/task-index.yaml`, `docs/ai/codex-team.md`, and the assigned work
packet before acting. Preserve existing untracked plans, `inbox/`, and `tools/`.
These role instructions coordinate work; they do not provide an OS permission
boundary or authorize remote actions outside the user's task.

## Roles

- Model policy: Architect uses `gpt-5.6-sol` with `ultra`; Builder and Repo
  Steward each use `gpt-5.6-sol` with `medium` (the user's GPT-5.6 selection).
  Set both model and effort explicitly when spawning either child. Do not let
  them inherit Architect's Ultra, silently substitute another model, or spawn
  additional workers without a new coordinated scope. Keep at most two active
  child agents for this team. These preferences do not hot-switch a running
  parent session; confirm its actual setting separately.
- **Architect**: the main coordinating session. Own requirements, work packets,
  dependencies, interface/schema semantics and freeze decisions. Delegate the
  main implementation to Builder, review changes, run final acceptance, and
  record the result against the exact candidate revision. Only do small
  integration or critical fixes directly; have another agent review them.
- **Builder**: implement the assigned, architect-approved contract, including
  schemas, production code, tests, and fixes. Stay within the packet's allowed
  files. Report contract gaps to Architect and pause only the affected work;
  do not silently redefine interfaces, weaken tests, or self-approve delivery.
- **Repo Steward**: own serialized Git/Issue/PR/CI operations within the task's
  authorization. Check scope and diffs independently, collect CI and test
  evidence, and maintain delivery status. Do not write the main implementation
  or substitute your approval for Architect's final acceptance.

An unassigned main session is Architect. Delegated agents keep the role given in
their task; being another Codex agent does not confer Architect authority.

## Collaboration and delivery

- Use one main coordinator and two bounded subagents. Each writable path has
  one owner at a time; name shared-file handoffs explicitly. Child agents in a
  shared checkout must not switch branches or run Git mutations concurrently.
- When parallel writers need overlapping paths, use separate branches/worktrees
  and integrate serially. Worktrees isolate working files, not credentials,
  GitHub permissions, network access, or the shared Git object store.
- Builder returns changed files, tests/results, unresolved questions, and the
  candidate commit or working-tree source hashes. Steward records the commit
  before final review; no one may alter reviewed source during acceptance.
- Record packet baseline, reviewed head, current PR base, actual CI checkout
  SHA, contract revision, CI run/attempt/jobs, and remaining blockers. Head
  changes invalidate approval for the new head; base changes require renewed
  integration checks. Preserve old evidence instead of relabelling it.
- Passing tests or Architect acceptance does not itself authorize merging.
  Steward may merge only after an explicit Architect merge instruction naming
  the PR, current head, base, and target, within existing user authorization and
  repository protections. Do not enable auto-merge or bypass required reviews.
- The current delivery remains draft PR -> `integration`; do not merge into
  `main`. Human gates remain the user's responsibility. No agent may invent or
  close a human gate, impersonate a human reviewer, or fabricate GitHub approval.

## Project invariants

- Keep the catalog and overlays at 67 entries until explicitly re-scoped.
- VPKB-000 is complete at exact head
  `acd3821b15e62bce13fa07b82c1665d501f27f67`, bound to Tests run
  `33456016766`. VPKB-001's first pinned transaction-inspect adapter is accepted
  at exact head `17c13f6317416f47d2610240aaf905598131e5bc`, bound to Tests run
  `33465872376` and its separate Architect acceptance. The manual-PDF capture
  dry-run architecture is separately accepted at exact head
  `3ab19eda4f417b96d89a0a50b2ce2c05233a8478`, bound to Tests run
  `33469912314`. A cached diff-check rejected the first implementation delivery
  for one blank line at EOF; that 22-path attempt and its empty-index rollback
  are preserved. The corrected seven-file R3 snapshot
  `c275904d2865cb1560408e1d3ba3894ed172e3a9ecf51c44d5c392e2d5b3a50d`
  was committed at exact head `57c2519425dbccd6bb48a0f82e77699e17afcfb6`,
  tree `c77a7c6ccc8bae3292611c2b24c33255f248710c`, passed four-job Tests run
  `33477484577` at merge preview `058ae19131cc418edc42dd8d311354503a0e515b`
  with 1835 tests per job, and received separate post-CI Architect acceptance.
  Its three post-CI records were carried by the successor architecture delivery.
  The bounded `deterministic-transaction-inspect-staging-v1` architecture began
  at baseline `57c2519`. Independent R1 reviews rejected repeated
  single-file staging calls because directory replacement between calls could
  split one transport across lineages. Revision 2 preserves those reports and
  freezes one retained-descriptor multi-file session with named identity and
  complete-set checks; the public `stage_bytes` behavior remains unchanged.
  Builder and Repo Steward independently returned R2 GO. The exact 21-path
  architecture was committed at head `62f3063fb612024179125bc7d842abdd3de0a4ee`,
  tree `37dfbba09e9f73656af4bb5510f7586bb5d4223e`; Tests run `33481415882`
  checked merge preview `910e272879b728aef8d1da1db2ba88d70feba5b0`, with 1838
  tests in each of four jobs. Architect then issued
  `ACCEPTED_VPKB_001_TRANSACTION_INSPECT_STAGING_ARCHITECTURE_AT_EXACT_HEAD`.
  Implementation R1 passed 1888 tests on both local Python versions, but Repo
  Steward rejected it because its complete-set check accepted unsafe or
  non-layout orphan entries. The R1 work package, candidate and review remain
  immutable history. Revision-2 work package SHA-256
  `c79ade9aa3b9c70c77250ef3f5a3aa7743c60652b3c4725d5d4e0995a5a67633`
  authorized Builder alone to close that one blocker and re-freeze the same ten
  production/test paths. The corrected snapshot
  `75179e9d0a66b3d528a14d6cc48be7139d350380be9b945b61eeb18eb6cb4ab2`
  passed independent Repo Steward review, 435 focused checks, 24 lineage and
  complete-set adversarial checks, four real pinned operation vectors, both
  1895-test local Python suites and the installed-wheel check. Architect local
  decision `PASSED_LOCAL_R2_IMPLEMENTATION_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI`
  is bound to acceptance record SHA-256
  `98ec4d0c3a7571fc46e271bed260191f0bbae6b89230bbd69734a5c132126d9b`.
  Its exact temporary-index delivery audit was nevertheless rejected by
  `git diff --cached --check`: one new test ended in two LF bytes. The R2 work
  package, candidate/review, local acceptance, manifest and delivery rejection
  remain immutable. Revision-3 work package SHA-256
  `1ba273bd9ae25f00583a4dac4c881b5eeb0d3796faf8b7cc10fffa34e918ac67`
  authorizes only removal of that final one-byte LF and new R3 evidence; the
  expected corrected ten-path snapshot is
  `e5f9f9b8e8686023183c5871ebb55b4d5ac8c6a9494646f91bb614fab1cedc76`.
  Builder froze that exact snapshot; Repo Steward independently returned `GO`,
  and Architect replayed 435 focused, 24 adversarial, four pinned-vector and
  both 1895-test full suites plus the byte-identical installed wheel. Architect
  local R3 decision `PASSED_LOCAL_R3_IMPLEMENTATION_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI`
  is bound to acceptance SHA-256
  `a4ce61b1035960131d7e6484e637464ee0c302ce8242212dc449287ebc86c8a8`.
  The exact R3 implementation was delivered at head
  `fb2cbcb565195a232f22d02c0474ac1b1b34f7d3`, tree
  `4a28ee53f71a0f2971f23b87e1f4c06d3bdf5b79`. Fresh Tests run
  `33491834331` checked merge preview
  `12bc7925140352fad516405b7eafaa8923d106e7`; all four jobs passed 1895
  tests. Architect then issued
  `ACCEPTED_VPKB_001_TRANSACTION_INSPECT_STAGING_IMPLEMENTATION_AT_EXACT_HEAD`.
  Its three post-CI records are immutable successor-carried inputs. The next
  bounded architecture is `staged-pdf-capture-inspect-v1` at baseline `fb2cbcb`.
  It freezes a canonical prepared request carrying the parsed desensitized
  approval-ref, one retained prepare/inspect batch lineage, complete staged
  Vault sibling snapshots, create/reuse authority branches and one shared
  compact bundle encoder. Builder and Repo Steward independently returned GO
  for contract SHA-256
  `8f9624c98ebbc9ae7eba51e61645291f11bc482f2fde1353e2ec4187f6c9d21f`
  and architecture work-package SHA-256
  `298ae880c5013c79a3db94dbc05c0d6d1c77eb0af3e507a55d5a2a2752c02421`.
  Python 3.12/3.13 each passed 1901 tests, and the isolated wheel exposes all
  26 schemas with byte-exact new resources. Implementation is not authorized
  until this architecture passes exact delivery, fresh CI and separate
  exact-head acceptance. Staged code capture,
  operation results, integrity runtime and retrieval remain outside this
  subrelease.
- Agent-facing `vpwiki` remains zero-egress and writes generated staging only
  under the approved `.work/**` boundary. Do not install/run `vpwiki-admin`,
  mutate a real Vault, or treat test approval fixtures as real authorization.
- Use the locked default Python environment without Docling extras/models.
  Replay tests using the short real temporary-directory recipe in `README.md`.
  Keep local unit/fixture results distinct from remote CI and human acceptance.
