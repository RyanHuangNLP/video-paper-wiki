# T1 r1 — structured knowledge and comparison

Lane 1 Builder candidate against freeze `3598ba577da3bbb13334cf5ed5fcc13d41a7c868c5b4486c9b1e1983ce13eeed` and contract `7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12`. Baseline remains `3368c6435db166a285b4b0e2df00f5d6a7491956`. Architect has not accepted this candidate.

## Functionality

`light_knowledge.py` exports a current-index, single-paper `kind=writing` light-context with deterministic page-spread coverage (at most 48 chunks / 80,000 characters). The wrapper schema is `video-paper-wiki.light-knowledge-context.v1` and carries `context`, `context_sha256`, `coverage`, `paper_snapshot`, and the frozen prompt. Import cross-checks the wrapper against a fresh export, requires at least one provisional section, rejects all-unknown documents as `INSUFFICIENT_EVIDENCE`, and publishes an immutable record under `.light-knowledge/records/<record_id>/` with document, context, identity, manifest, and `knowledge.md`. Identical import reuses exact bytes; a same-id different bundle is `LIGHT_KNOWLEDGE_CONFLICT`. Heads live in `.light-knowledge/HEADS.json`. Views are versioned under `knowledge/views/<view_id>/` with `knowledge/CURRENT.json`. Staging uses `.light-knowledge/staging/<kind>-<id>-<token>/` with `ownership.json` first and a `payload/` child. Mutations take the existing workspace lock.

`light_compare.py` selects 2–8 present papers, searches each paper before retrieval (top 6 lexical chunks), and keeps zero-hit papers visible. Wrapper schema is `video-paper-wiki.light-comparison-context.v1`. Import validates cell ownership, conditions, and comparability, then writes create-only Markdown under an explicit `.work` `.md` path (default `workspace/reports/comparison-<id>.md`). Existing output is `LIGHT_OUTPUT_CONFLICT`.

`light_context.py` only adds `.light-knowledge`, `.light-library`, and `knowledge` to `_MANAGED_ROOTS`. QA/writing kinds are unchanged.

## Public result shapes for T3

- `export_knowledge_context(workspace_root, *, paper_id) -> {ok,status,message,schema,paper_id,context,context_sha256,coverage,paper_snapshot,prompt}`
- `import_knowledge(workspace_root, context, document) -> {ok,status,message,record_id,paper_id,page_path,source_status,reused}`
- `list_knowledge(workspace_root) -> {ok,status,message,records,heads,staging}`
- `build_knowledge_views(workspace_root) -> {ok,status,message,view_id,index_path,reused}`
- `export_comparison_context(workspace_root, *, query, paper_ids, dimensions=None) -> {ok,status,message,schema,query,paper_ids,dimensions,context,context_sha256,coverage,prompt}`
- `import_comparison(workspace_root, context, document, *, output=None) -> {ok,status,message,path,output_sha256,citations,workspace_root,index_id}`

`coverage` for knowledge is `{total_chunks,exported_chunks,omitted_pages,truncated}`. Comparison coverage is `[{paper_id,exported_chunks}, ...]` in selection order. `record_id` / `view_id` are 64 lowercase hex. Closed refusals use `ok=false` with `INSUFFICIENT_EVIDENCE`, `INDEX_STALE`, `LIGHT_SELECTION_INVALID`, `LIGHT_KNOWLEDGE_INVALID`, `LIGHT_KNOWLEDGE_CONFLICT`, `LIGHT_COMPARISON_INVALID`, `LIGHT_OUTPUT_CONFLICT`, or `LIGHT_WORKSPACE_BUSY`. Unsafe workspace/output paths raise `WORKSPACE_INVALID`.

T3 should import those six callables only. Do not edit T1 files.

## Files

Owned changed paths only:

- `src/video_paper_wiki_research/light_knowledge.py`
- `src/video_paper_wiki_research/light_compare.py`
- `src/video_paper_wiki_research/light_context.py`
- `tests/research/test_light_knowledge.py`
- `tests/research/test_light_compare.py`
- `tests/research/test_light_library_citations.py`

## Tests

Pinned interpreter `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` (3.13.13) with `PYTHONPATH` set to this worktree `src`. Official focused command exit 0: **19 passed in 0.32s**. No dependency install, no Git mutation, no Vault write.

## Unresolved issues

None that block this lane. T3 still owns CLI/Skill/docs and integrated real-PDF trials. T2 lock/archive/backup modules were not imported.
