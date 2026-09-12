# RESEARCH-WIKI-W1-PREVIEW coordination

2026-09-06. Architect owns W1 contract drafting and freezing. Baseline: `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`.

Read `docs/ai/task-index.yaml`, `docs/ai/codex-team.md`, this packet, R3.3 §5/§6.1/§9/§10 and R3.2 §15.3 Fable convergence before acting. Preserve both PRDs and all prior untracked plans, inbox, tools and evidence. FABLE-002/008 remain user decisions and do not block W1. CAP-WEB-OBS-001 ran first; its observed samples are in `artifacts/verification/RESEARCH-WIKI-W1-PREVIEW/CAP-WEB-OBS-001/observation-samples.json`.

Builder is initially read-only: inspect package integration, existing JCS/staging/schema helpers, Skill conventions and necessary allowed paths. Identify blockers to a zero-egress normalized arXiv page preview flow. Do not implement until Architect freezes the main W1 packet and hands off paths.

Repo Steward is initially read-only: verify Git head/base/PR94 remote state and delivery feasibility, independent scope checks, and immutable input hashes. Own all eventual serialized Git/PR/CI mutations only after explicit Architect instruction. User authorized draft PR targeting integration; no merge, auto-merge or human gate changes. Do not branch-switch a shared checkout during another writer's work. Record or report the safest same-PR continuation versus new draft delivery choice without mutating yet.

Architect alone writes the main packet, contract and CAP evidence. Two existing children retain `gpt-5.6-sol / medium`; no additional workers. Review the same exact contract and report GO or concrete gaps. Implementation and final acceptance follow codex-team.md.
