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
  Its three post-CI records remain successor-carried evidence. The current
  Architect-owned work is the bounded `deterministic-transaction-inspect-staging-v1`
  architecture at baseline `57c2519`. Independent R1 reviews rejected repeated
  single-file staging calls because directory replacement between calls could
  split one transport across lineages. Revision 2 preserves those reports and
  freezes one retained-descriptor multi-file session with named identity and
  complete-set checks; the public `stage_bytes` behavior remains unchanged.
  Builder and Repo Steward independently returned R2 GO. Local Python 3.12 and
  3.13 each passed all 1838 tests and the isolated wheel contains all 24 schemas.
  Builder implementation remains blocked until this exact 21-path architecture
  delivery is committed, passes fresh four-job CI, and receives separate
  exact-head Architect acceptance. Proposal mapping, operation results,
  integrity runtime and retrieval remain outside this subrelease.
- Agent-facing `vpwiki` remains zero-egress and writes generated staging only
  under the approved `.work/**` boundary. Do not install/run `vpwiki-admin`,
  mutate a real Vault, or treat test approval fixtures as real authorization.
- Use the locked default Python environment without Docling extras/models.
  Replay tests using the short real temporary-directory recipe in `README.md`.
  Keep local unit/fixture results distinct from remote CI and human acceptance.
