# T1 r2 -- integrity and publication corrections

Lane 1 Builder revision 2 against current freeze fa20f3cecf755d1866d249695a9e07c2cfcb065ad3a90701634970b787e026f5 and original contract 7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12. Baseline remains 3368c6435db166a285b4b0e2df00f5d6a7491956. Previous rejected r1 snapshot e27e0670b658cdd9e5aebbcfe148b22eb1ab84dfceca9675484630bdb9606c35 is preserved byte-for-byte. Architect has not accepted this candidate.

## Functionality

R2 keeps the same public APIs and storage roots. Shared helpers now:

1. Finish owned pointer/record/view staging after successful publication and on identical retry of an already-published validated stage. Empty payload/ plus ownership.json is removed only when the leftover is the validated owned infrastructure.
2. Inventory every directory entry. Symlink directories, extra empty directories, hardlinked files and any path outside the exact parents implied by the generated file set refuse reuse, listing-as-current, and staging recovery.
3. Validate saved records before calling them current or using their concepts. Complete file set, sizes/hashes, record ID/directory/path identity, document/context/identity consistency, wrapper identity, and citation ownership against current derived source bytes are required. Edited or malformed records are conflict and do not contribute concepts. Old bytes are left untouched. Relative source identities are checked locally after relocation.
4. Related-paper Markdown links from knowledge/views/<id>/papers/<paper>.md are sibling links. Concept-page links remain ../papers/<other>.md.
5. Required wrapper fields and types are validated before indexing. Missing coverage, paper_snapshot or prompt on knowledge, or coverage on comparison, close as ResearchError or ok=false with no partial publication.
6. source.md/source.json and their path chains are refused when hardlinked, symlinked, or otherwise unsafe, before export/import/status decisions. This does not depend on an unaccepted T2 index change.
7. Recovery/cleanup requires the full ownership shape (kind/ID/target/allowed set) and every existing generated file to match the operation expected bytes. Edited payload bytes or a mismatched intended target remain and close as conflict. Untouched validated partial stages still recover.
8. Live source/wrapper identity is rechecked after rendering and immediately before record publication and head change. Views recheck heads and source/record snapshots before publishing the view and before switching CURRENT. A schema-matching object is not treated as owned unless the complete pointer identity, including target ID and intended relative target, is valid.

Unknown-CURRENT-schema refusal is preserved.

## Public result shapes for T3

Unchanged from r1. T3 must not import this snapshot until Architect accepts it.

- export_knowledge_context(workspace_root, *, paper_id)
- import_knowledge(workspace_root, context, document)
- list_knowledge(workspace_root)
- build_knowledge_views(workspace_root)
- export_comparison_context(workspace_root, *, query, paper_ids, dimensions=None)
- import_comparison(workspace_root, context, document, *, output=None)

## Files

Owned six-path allowlist only:

- src/video_paper_wiki_research/light_knowledge.py
- src/video_paper_wiki_research/light_compare.py
- src/video_paper_wiki_research/light_context.py (unchanged from r1)
- tests/research/test_light_knowledge.py
- tests/research/test_light_compare.py
- tests/research/test_light_library_citations.py (unchanged from r1)

## Tests

Pinned interpreter /Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python (3.13.13) with PYTHONPATH set to this worktree src. Official focused command exit 0: 58 passed in 0.63s. Scope was the three owned test files plus all of tests/research/test_light_context.py. Equivalent synthetic regressions cover the eight Architect correction groups. The Architect real-corpus reproducer was not executed through Cursor. No dependency install, no Git mutation, no Vault write.

## Unresolved issues

None that block this lane. Architect must independently replay .work/acceptance/lightweight-library-v1/architect_t1_regressions.py locally, including real-corpus variants. T3 still owns CLI/Skill/docs and must not import this snapshot yet. T2 lock/archive/backup modules were not imported.
