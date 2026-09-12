# MANUAL-PDF-8H-DEVELOPMENT

2026-09-06 · active, user-authorized development management packet.

## Goal and time

Active user goal: “按照之前的计划进行开发吧”. The immediately preceding approved plan is the manually supplied PDF first version, using Astra / two Luna assistants / Grok Build. Preserve the complete user flow: **manual PDF → parsing and knowledge organization → retrieval/Q&A → simple LLM drafting**, including existing audit/backup/restore usability. A single parser packet is progress, not completion of this goal.

The 8-hour run starts at the goal creation time `2026-09-05T19:43:50Z` and ends at `2026-09-06T03:43:50Z` (Asia/Shanghai 2026-09-06 03:43:50–11:43:50). Save progress and evidence throughout. Stop launching new work at the deadline, safely stop/checkpoint remaining processes, and report unfinished requirements; elapsed time is not a successful product acceptance. Do not purchase quota, change models, merge, or close human gates to meet the clock.

Baseline: `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`, existing branch `repair/vpkb000-plan-approval-prepare-follow2`; current delivery is draft PR94 → integration. Recheck live base/head for each candidate. Read task-index.yaml, codex-team.md, manual-PDF scope/addendum and each assigned frozen packet before work.

## Owners and control loop

- Architect: main `gpt-6-astra / ultra`; requirements, packet/contract freeze, code and test review, acceptance, next instruction. Owns coordination/design/acceptance files and narrowly scoped integration fixes only, with independent review.
- Progress Monitor: `gpt-5.6-luna / high`, task `grok_monitor_probe`; sole Grok process owner. Read the grok-build-cli Skill; invoke exact model/effort; retain prompts, process/session IDs and raw logs; poll in at most 30-second waits and send meaningful progress/completion/failure messages to Architect. No implementation or Git writes.
- Builder: external Grok Build, `grok-4.6 / xhigh`; only assigned production/test/README/Skill paths and its brief/evidence. No Git, additional workers, admin/Vault operation, model download or changes to frozen contracts. On completion or a contract gap, return a brief and stop relevant writes.
- Repo Steward: `gpt-5.6-luna / high`, task `git_steward_probe`; independent scope review, exact candidate snapshots and serialized Git/PR/CI on Architect handoff. No main implementation or self-approved delivery.

Each iteration: Architect freezes a bounded task → Monitor runs Grok → Grok writes a brief → Monitor relays it → Architect reviews actual changes and tests → request repairs or hand the exact candidate to Steward → inspect fresh CI and record exact-head acceptance → next task. Do not queue the next coding packet before the current review decision. A CLI turn limit or empty response is incomplete work, not acceptance; inspect the live process before restarting after observation timeouts.

Grok briefs include packet/contract hash, session ID, changed files and hashes, commands and test counts, unresolved gaps, known unrun lanes and a clear stopped-writing state. Report files/logs stay in the assigned packet's verification folder or a named temporary run folder. Briefs never supply human approval or claim a fabricated real-data result.

## Implementation sequence and evidence

1. Freeze and implement [manual PDF extraction](RESEARCH-WIKI-MANUAL-PDF-EXTRACTION.md): safe intake/profile/offline staged exporter, true locators, nonempty provisional knowledge proposal and installed entrypoints. The pre-capture stage must remain visibly untrusted.
2. Freeze the next bounded source-admission/publication packet from actual code interfaces: pristine genesis → capture result → raw admission/receipt → artifact package → canonical paper/concept views and status. Test the actual transition without planting authority records. Agent commands only prepare/inspect; real operator mutation remains outside agent execution.
3. Add the bounded evidence context and current-model answer handoff over existing exact/BM25/current-generation queries. Explicit stale/unknown outcomes and real citations are required.
4. Add topic/requirements/selected-paper context → current-model draft validation → editable Markdown and basic references. Do not make advanced writing Skills, graph retrieval or full comparison benchmarks prerequisites.
5. Verify the continuous first-version flow and existing audit/backup/restore entrypoints. Preserve engineering fixture/CI versus real PDF/parser/operator/human evidence distinctions. Record all unfinished real lanes and product requirements.

The interface details for steps 2–5 are frozen when their dependencies can be inspected; these are implementation work packages, not new PRD review rounds. Preserve the original PRDs and Fable discussion. User choices FABLE-002/008 and all human gates remain open unless explicit evidence is provided; their deferred optional scope must not block the authorized core.

## Permissions and delivery

User authorization covers bounded implementation, tests, fixes and continued draft PR → integration. It does not cover real Vault changes, vpwiki-admin execution, model downloads/default dependency changes, unrelated source upload, Feishu messages, destructive Git operations or merging. Respect filesystem/tool approval boundaries; prepare exact allowed changes before requesting normal escalation where needed.

Keep 67 seed/overlay entries, locked default environment, existing untracked plans/inbox/tools and all historical evidence. Source/Git paths have one writer. Steward stages only an exact manifest, never blanket add. Freeze source during final review; record baseline, contract revision/hash, source hashes, candidate head, current base, actual CI checkout SHA, run/attempt/jobs and blockers. Success at an old revision is not acceptance of a new one.

## Initial checkpoint

Grok invocation preflight is complete and recorded in [team preflight](../grok-build-team-preflight-2026-09-06.md). The two Luna assistants are assigned and current main model is verified. Manual extraction R2 contract is awaiting the final bounded check/freeze; no implementation source existed at the start. The prior R2 contract/packet bytes are preserved under `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/reviews/r2/` before any coordination/status successor.
