# T2 — complete batch knowledge and selective refresh

Read README, COMMON, CONTRACT and freeze. Controller:
cursor_lanes34_controller, existing Luna/xhigh. Builder: pinned Cursor Grok.
Source: ROOT/.work/parallel/lightweight-research-v1/terminal-2/source at BASE.

Implement shared rules and both T2 sections. Complete batching first, then
selective refresh using its checked persistence. Owned paths:

- src/video_paper_wiki_research/light_knowledge_batch.py
- src/video_paper_wiki_research/light_knowledge_refresh.py
- src/video_paper_wiki_research/light_knowledge.py
- src/video_paper_wiki_research/light_backup.py
- tests/research/test_light_knowledge_batch.py
- tests/research/test_light_knowledge_refresh.py
- tests/research/test_light_knowledge.py
- tests/research/test_light_backup.py

Do not edit CLI/Skill/docs, light_context, library maintenance, workflow or
source/index producers. Use the existing helpers read-only. Extend legacy
knowledge record validation with explicit supported wrappers, never a generic
caller-controlled bypass. Existing knowledge export/import remains compatible.

light_backup changes are narrowly for recognized pending/completed batch jobs
and new owned publication state. It transfers to T3 for writing recognition
ONLY after this Builder stops, immutable review passes, and Architect explicitly
hands off the exact file. No overlapping writers.

Prioritize exact complete partition and bounded rolling merge, actual live
chunk identity, contiguous immutable steps, no partial HEAD, safe exact retry,
all-unknown closure and visible missing progress. Then source-delta inventory,
safe unique citation remapping, conservative legacy fallback, candidate-only
refresh finalization and explicit per-section/concept acceptance. Preserve
notes and all old records; invalid unaccepted old claims become visibly unknown.

Run scoped new tests plus existing knowledge/backup tests. Include real backend
backup round trips, injected process-interruption retries, unknown extra-state
refusal, source/head drift and complete-file-set validation. Root handles full
dual-version suites and real current-model trials after integration. Return r1
exact files/checks/report/handoff/ready and stop writing.
