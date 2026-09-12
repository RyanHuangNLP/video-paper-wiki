# T4 r3 findings

No new upstream defect on accepted T3 r4. Publication-order windows now return `INDEX_STALE` / `session_id=null` / no new session.

Preserved T4-owned CLI assertion history (not upstream):
- Illegal QA complete document produced `CITATION_MISMATCH` rather than `LIGHT_SESSION_CONFLICT`.
- Relative `markdown_path` must be resolved against the workspace.

Do not create or wait for `lane3-r3-acceptance.json`. T3 r3 remains historically rejected.
