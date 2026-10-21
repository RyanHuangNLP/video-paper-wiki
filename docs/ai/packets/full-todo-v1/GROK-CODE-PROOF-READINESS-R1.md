# Bounded CODE-PROOF implementation-readiness review

You are Grok Build, selected by the user as `grok-4.6` with `xhigh` reasoning.
Architect is the coordinating Codex root. This is a fresh, bounded prerequisite
review for your next implementation packet. Do not implement or mutate files yet.

Read these exact project files, which are task-authorized source/design inputs:

1. `/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/full-todo-v1/GROK-CLI-OWNERSHIP-R3.json`.
2. `/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/full-todo-v1/CODE-PROOF-DESIGN-R2.md`, SHA-256 `eb1dc42ac1012f51f6c645880002ee5b87c9149689705ea70551849210966a57`.
3. `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/full-todo-v1/E/code-proof-design-review-r2.json`.
4. `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/full-todo-v1/E/code-config-span-advice-r3.json`.

The current working directory is the current production source checkout at
`.work/parallel/discovery-expansion-v1/terminal-1/source`, baseline
`ef2ff13e9f90135161ef5ec112750c96392c6cd5` plus a frozen 31-path Discovery R3
candidate. Read production code only if needed to validate reuse of a concrete
interface; the legacy root checkout has older production files. Nothing here may
be edited. No other local files, credentials, PDF inputs or private trial handles
are needed. Do not invoke Git, providers, subprocess code from supplied source,
additional agents, a model download, an operator command or any remote mutation.

Review the nine independent R2 findings and give concise concrete closure
recommendations. In particular, check whether the pure Git-object verification
kernel can be implemented first as a bounded independent packet while Architect
freezes the public envelope/configuration/retained-I/O contracts. Recommend an
exact in-memory function input/output and explicit error surface for that kernel:
framed SHA-1/SHA-256 IDs, strict commit/tree syntax, target traversal and modes,
exact consumed object set, declared/per-object/aggregate budget accounting, and
raw bytes retained without interpreting code. The kernel must do no filesystem,
network, subprocess or Git operation. Normalized text/configuration derivation and
all public command/storage semantics stay in later packets.

Report any additional correctness blocker, with concrete counterexample and
recommended rule. Do not claim an unresolved design is frozen. Return your review
in final stdout, including files read, blockers, proposed kernel API and tests,
and an explicit no-files-written statement. Stop after the review. Architect will
send a new frozen implementation packet; do not start that work autonomously.
