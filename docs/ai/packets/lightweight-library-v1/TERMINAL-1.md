# T1 — knowledge organization and comparison

Own production:
- src/video_paper_wiki_research/light_knowledge.py (new)
- src/video_paper_wiki_research/light_compare.py (new)
- src/video_paper_wiki_research/light_context.py (only managed-root protections in CONTRACT)

Own tests:
- tests/research/test_light_knowledge.py (new)
- tests/research/test_light_compare.py (new)
- tests/research/test_light_library_citations.py (new)

Implement CONTRACT T1/common fully: checked source-backed structured sections and concepts; immutable records and versioned useful paper/concept/related-paper views; current/stale visibility; balanced multi-paper contexts; typed conditions-aware comparison table; exact citation/live-source validation and preservation on refusal.

Do not extend old workflow kinds or change pure renderers. Reuse existing kind=writing contexts and citation functions. Protected roots prevent generic QA/writing output from corrupting new state; your own safe immutable knowledge publication uses validated rendering with correct relative links. Keep current sessions and user notes intact. Existing T2/T3 files read-only.

Focused checks must use actual source and cover normal two-paper records/views, unknown sections, false/mixed/missing citations, context/source drift, exact reuse versus edited bundle conflict, concept label/path escaping, view history/current state, comparison cell completeness and paper ownership, conditions/comparability, table formatting, stale output refusal and managed aliases. Malformed fields and unsafe paths fail without writing final outputs.

Publish stopped r1 snapshot/handoff per COMMON. No CLI edits or Git actions. Candidate semantics/status fields must match CONTRACT so T3 can integrate without reinterpretation.
