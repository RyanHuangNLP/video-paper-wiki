# T1 — original/English query fusion

Read README, COMMON, CONTRACT and freeze. Controller: cursor_cli_preflight,
existing Luna/xhigh. Builder: pinned Cursor Grok. Source is
ROOT/.work/parallel/lightweight-research-v1/terminal-1/source at BASE.

Implement CONTRACT shared rules and T1 only. Owned paths (changes are optional
where described as integration support; no change outside this set):

- src/video_paper_wiki_research/light_query.py
- src/video_paper_wiki_research/light_context.py
- src/video_paper_wiki_research/light_index.py
- tests/research/test_light_query.py
- tests/research/test_light_context.py
- tests/research/test_light_index.py

Preserve legacy search and context behavior. light_context ownership includes
the small .light-writing managed-output protection needed by T3; no other
writing-module changes. CLI/docs are T3's later integration responsibility.
Do not introduce a workflow request/schema change or comparison rewrite API.

Exercise the actual backend for original-only/rewrite-only/both/no hits,
selection-before-search, deterministic RRF scores/order/deduplication, limits,
malformed rewrite/trace, source change between routes and import, and foreign
citations. No network/model dependency, no false success from malformed index.
Test the managed-root protection without overwriting a user artifact.

Use scoped T1 and existing context/index/QA/writing tests with exact SOURCE
pytest provenance. Return r1 evidence and stop writing. A missing contract
decision is a bounded question to Architect, not a license to redefine it.
