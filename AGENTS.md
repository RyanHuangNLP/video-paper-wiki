# Current cloud development handoff — 2026-09-13

Read [the group development brief](docs/ai/GROK-BOT-GROUP-DEVELOPMENT-BRIEF.md),
[remaining development plan](docs/ai/remaining-development-plan-2026-09-13.md),
and [BOOT-01 handoff](docs/ai/CLOUD-BOOT-01-HANDOFF.md) first.
The user's current roles supersede the historical coordination below:
ChatGPT/Codex designs, dispatches and reviews; Grok implements all product and
test code; agy handles Git/PR/CI delivery; Grok Bot only relays tasks and results.
Use existing Herdr agents as instructed by the user; do not rediscover or install
the runtime for this handoff. One owner per task; parallelize only separable work.

Develop from the published codex/code-proof-v1 handoff HEAD containing product
baseline d440c7aaebb4dcc2c52cab719b0d73347a41493f and startup documents. Preserve
historical evidence; old running states, dispatches and PR numbers are not current
instructions. ChatGPT must prepare the current C1 task before Grok starts it.
Keep draft PR delivery to integration, no automatic merge or main changes, and
leave real Vault operations and human acceptance gates outside this handoff.

# Preserved lightweight research enhancements — 2026-09-08

This increment adds Chinese/English lexical retrieval handoffs, complete bounded
long-paper processing, selective knowledge refresh, and outline/section writing
revisions. See [the release record](docs/ai/lightweight-research-release-2026-09-08.md)
and its linked frozen contract and source validation record. Exact-head CI is
recorded separately after delivery; source validation alone does not establish it.

Astra coordinates and accepts exact candidates; three existing Luna/xhigh
controllers manage pinned Cursor Grok Builders. Builders are stopped for
acceptance. Only an explicitly authorized unfinished packet may start new work.
Keep serialized delivery to draft PR #95 targeting integration. No merge, main
change, automatic merge, real Vault operation or human-gate closure is authorized.
The continuation heartbeat remains paused. Preserve inbox, tools, local plans,
raw documents, model trial material, rejected evidence and previous acceptance.
The contract's dispatch preconditions describe this historical development run.

The preceding library increment is complete at 6963292a93ae322eaf9bb563b7b1170dee6a6fc6,
with Tests run 34197658919. Its records below remain bound to that earlier revision.

## Preserved earlier coordination and product evidence

# Lightweight library increment — 2026-09-08

The current increment adds cited structured knowledge, paper maintenance,
lightweight backup/restore and basic multi-paper comparison. See
[the release record](docs/ai/lightweight-library-release-2026-09-08.md) and its
linked frozen contract and source validation record for this increment's scope.
The earlier 25-path workflow completion below keeps its original revision.

Astra coordinates and accepts exact candidates; the three existing Luna/xhigh
controllers manage the pinned Cursor Grok Builders. Only an explicitly frozen,
authorized unfinished packet may run. Keep serialized delivery to draft PR #95
and its integration target. New source changes require fresh validation and CI;
local source acceptance does not authorize merge or close any human gate.
The continuation heartbeat stays paused. Preserve inbox, tools, local plans,
raw input documents, original run evidence and all prior acceptance records.
The contract's dispatch preconditions describe the completed development run;
this delivery header itself does not restart it.

## Preserved earlier coordination and product evidence

# Current four-agent Cursor CLI coordination

On 2026-09-08 the user accepted FOUR TOTAL Codex agents in this runtime:
one GPT-6 Astra / ultra / Fast primary and three GPT-5.6 Luna / xhigh controllers.
Each controller manages at most ONE active Builder (CLI by default, or the
GUI fallback below), at most three concurrently; Astra schedules the four existing logical lane packets as
processes complete. All Builders use
account-verified cursor-grok-4.6-xhigh-fast. Preserve the user default model.
Read docs/ai/packets/four-agent-cursor-cli-v1/README.md and CONTROLLER.md first.
This replaces the uninstalled five-agent proposal and historical execution
restrictions, not product scope, original 25 paths, evidence or approval rules.

Astra autonomously coordinates development, review and in-scope fixes.
Each controller must explicitly use gpt-5.6-luna / xhigh; no extra agents.
Use per-lane atomic leases and immutable attempt logs. Grok alone writes its
original product paths; Luna verifies handoffs; Astra accepts exact candidates.
After builders stop and exact acceptance, an existing Luna may be reassigned
to serialized Repo Steward duties. No extra standing role, automatic merge,
main changes, fabricated review or closure of human gates. Preserve untracked
plans, inbox, tools and old evidence. Login and exact model catalog are verified.

For technical CLI failures, follow
docs/ai/packets/four-agent-cursor-cli-v1/GUI-FALLBACK.md to use Computer Use
with Cursor App for the same authorized packet. One Builder per controller
means CLI or GUI, never both for one lane; GUI retains the shared lane lease
and one desktop owner. Do not reroute permission, security, automatic-approval,
content, authentication or quota refusals through the UI. This fallback does
not restart accepted work or paused automations.

The lightweight-workflow-v2 product scope is complete at accepted head
809627bfa0deb8c1b1393f731bf3cb9a3c21ee66 and its continuation heartbeat is paused.
A future run requires an authorized unfinished packet. Machine-local historical
packets and raw run evidence are not bundled with this coordination update.

## Preserved earlier agreement and product evidence

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
  26 schemas with byte-exact new resources. The architecture was delivered at
  exact head `4168e151c332cdcf89227bf086d4a6bc5308e649`, tree
  `78d43e20f8937a96c6cc86357729c72d295658cb`; fresh run `33497663181`
  passed four jobs with 1901 tests each at merge preview `f48d3cc3323958270f2e249d8e6a71f853df2150`.
  Architect issued
  `ACCEPTED_VPKB_001_STAGED_PDF_CAPTURE_INSPECT_ARCHITECTURE_AT_EXACT_HEAD`.
  Builder's R2 candidate SHA-256
  `20f9df83117bf296e9ef4ef6fb6ce78222b17f92cadb774c7fc15df31af11437`
  passed 1938 tests on both Python 3.12/3.13 but Architect rejected its
  missing-fixed-slot identity window. R3 candidate SHA-256
  `920b126b602cb17b1727223df0698a88bded0f3d4787a07ce23e2edf941246b8`
  closed that window and passed 1940 tests on both Python 3.12/3.13, but an
  independent review then reproduced request-before-plan failure-order and
  exception-path named-lineage gaps in `_inputs`. R4 candidate SHA-256
  `77e2657ce77918e55763f729a86d4453ba9bdb925587d0df4c48d9aa2d43c652`
  closed those gaps, froze snapshot
  `ae6cd5b9fa93f00894d7a2f6ad484fb9bb066d07617d1572afb9b792125cbc02`,
  and passed 1948 tests on both Python 3.12/3.13. Independent review then
  found two remaining all-exits lineage failures: staging conflicts could
  escape after persistent named transport/content replacement, and initial or
  repeated captured-snapshot scans could escape without a final named-edge
  check. Revision-5 work-package SHA-256
  `71e5af783fbb5410bc4e0fae91fec775dd92a5334aeacdb197af0e7ed76dccd5`
  produced candidate
  `e4fb96af7b0eeb62d3c3cd3aa8a3c492c2ea9f1dae7a765fb4cf53f3b233435f`,
  18-path snapshot
  `c3634d7b575e25f1221f3a566014f688c90544b3d215edb1cd2b7d2b10102b8d`,
  dual-Python 1962-test local passes and the verified 26-schema wheel. It was
  delivered at exact head `39d279fa8b357d63ef282cbc9dee35a93773e4d4`, tree
  `e740f43de6c39922cfe3f799c6574183d406d2a6`. Fresh run `33554650002`
  tested merge preview `49e987c4228406fde3b33ab7cf73966b31c73f59`: both macOS jobs
  passed 1962 tests, while both Ubuntu jobs passed the required
  `WORK_PATH_UNSAFE` assertions and then failed only because the fixture assumed
  unlink/recreate must change `st_ino`. Failure observation SHA-256
  `a6baa458dfce401272ead3cc8085fa491684eb6bf60e6ad25a59b0f26388fb34`
  is immutable; no R5 exact-head acceptance was issued. Active revision-6
  work-package SHA-256
  `8843af7b2ac29a737dd47c367fc019579510e7a398fe7fd371b79df83853e842`
  (12,933 bytes) archives R5 byte-for-byte and permits only
  `tests/unit/test_prepare.py` plus R6 candidate evidence. R6 candidate
  `e94de4bebb2a1094e910bdfeb2651728c2746fc0d38ca0e1942f57fa615667aa`
  binds snapshot
  `da6c2472cd1a6714ce9a3ba03b7851006cf8a3292d3a77e734ae17ef51a6171c`;
  it creates the distinct replacement while the original inode is still live,
  then atomically installs it without weakening the refusal assertions. Builder
  and Architect each passed 1962 tests on Python 3.12/3.13. Repo Steward review
  `736c4e4296f611b2c4cd5f012498cc24c97cc3790dff56643626c372d4f9722a`
  returned `GO_FOR_ARCHITECT_R6_LOCAL_ACCEPTANCE`; Architect local acceptance
  `2398948e939b3d09e52eb5672acde0d9f7f19f6a98ec77823c0e0ed560c4a5ed`
  passed. R6 was delivered at exact head
  `ed6c83865b51e8f512ab22d7c6c7113a15e26837`, tree
  `3aea2d6cc12c7634b6e7c253a39f92771aedb591`, as the exact 14-path snapshot
  `179f2a069f002a501ce93c5548a216aac2256ecaa17de13a40192e4b02ddf3b7`.
  Fresh run `33558215519` checked merge preview
  `6c4e8539f187ce8171a50f79086ef8eccda9f05c`; all four Linux/macOS x
  Python 3.12/3.13 jobs passed 1962 tests. Post-CI records
  `ci-observation.json` and `merge-parents.json` have SHA-256
  `8f9dbca1332ea5465584025e896d15f30425dc357ffb6f279e30329d0bec4a18`
  and `695c6ad179d17f4feac1eb48e2e4138e0981184bf2e1fbc0dc569029cf059429`.
  Architect decision
  `ACCEPTED_VPKB_001_STAGED_PDF_CAPTURE_INSPECT_IMPLEMENTATION_AT_EXACT_HEAD`
  is bound by acceptance SHA-256
  `461c7de89c6fdcd9a611901f7928a7e4168c9d066de4e34be91e49810717e0af`.
  These three post-CI records were generated after the tested commit and remain
  local untracked protected material; their hashes identify historical external
  evidence, but this successor does not stage or claim to repository-carry them.
  R1-R5 work packages and all rejected/failed evidence remain history. The
  current roadmap-closure candidate adds staged code capture, operation results,
  integrity audit, publication, catalog/query, retrieval and backup/restore.
  Its signed 74-case run and both 2152-test Python suites pass locally; fresh
  exact-head CI is still required, and all real-data and human gates stay open.
- Agent-facing `vpwiki` remains zero-egress and writes generated staging only
  under the approved `.work/**` boundary. Do not install/run `vpwiki-admin`,
  mutate a real Vault, or treat test approval fixtures as real authorization.
- Use the locked default Python environment without Docling extras/models.
  Replay tests using the short real temporary-directory recipe in `README.md`.
  Keep local unit/fixture results distinct from remote CI and human acceptance.
