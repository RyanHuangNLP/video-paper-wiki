# T1 r3 -- comparison output and validated prior references

Lane 1 Builder revision 3 against current freeze c06ae0f53412464425e1a83afc247dfd9f6dc70e66584889aa4ba37e4c1610da and original contract 7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12. Baseline remains 3368c6435db166a285b4b0e2df00f5d6a7491956. Previous rejected r2 snapshot d9aebbe770a36863f6186ef9b57536dc9f6f4f2b747f0f54c86794b896944293 is preserved byte-for-byte. Architect has not accepted this candidate.

## Functionality

R3 keeps the same public APIs, storage roots, R1/R2 success/retry behavior, and all 14 earlier Architect fixes. Shared helpers now:

1. Reject duplicate paper selections as LIGHT_SELECTION_INVALID before the legacy index normalizer can rewrite [A,A,B] into [A,B]. The original list, every ID, and invalid selection types are checked. [A] and [A,A] remain refused. Over-limit lists that hide a duplicate also refuse. The legacy index normalizer is unchanged.
2. Comparison table cells escape caller text and conditions exactly once, then compose trusted inline source.md#page-N links and br markup. Generated Markdown is not re-escaped. Links resolve relative to the actual output path. Pipes, newlines, brackets, angle brackets, Unicode and backslashes stay inside cell boundaries.
3. Typed enum validation checks type is str before membership. Unhashable comparability and knowledge status close as the documented result without TypeError or blanket exception swallowing.
4. Prior CURRENT/HEADS pointers are replaceable only after their own referenced view/record bundles pass schema, exact file/directory set, size/hash, ID, relative path and ownership checks. Missing or malformed references are preserved and reported as conflict. Valid old pointers advance to a different new target, including after source staleness or archival. Historical view IDs keep their original fingerprint as a fully validated internal view-manifest field. Interrupted publication/retry behavior from R2 is unchanged.
5. Record and view metadata use exact versioned shapes. Unknown top-level manifest or identity fields are conflict and cannot contribute current concepts. Stale and missing-source classification still runs after integrity checks.

## Public result shapes for T3

Unchanged from r1/r2. T3 must not import this snapshot until Architect accepts it.

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
- src/video_paper_wiki_research/light_context.py (unchanged from r1/r2)
- tests/research/test_light_knowledge.py
- tests/research/test_light_compare.py
- tests/research/test_light_library_citations.py (unchanged from r1/r2)

## Tests

Pinned interpreter /Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python (3.13.13) with PYTHONPATH set to this worktree src. Official focused command exit 0: 72 passed in 0.78s. Scope was the three owned test files plus all of tests/research/test_light_context.py. New synthetic regressions cover exact nonduplicate selected IDs, rendered inline citation links, single escaping, typed enums, missing prior CURRENT/HEADS preservation, exact record/view metadata shapes, and valid old-to-new pointer advancement after staleness/archival. The Architect real-corpus reproducer was not executed through Cursor. No dependency install, no Git mutation, no Vault write.

## Unresolved issues

None that block this lane. Architect must independently replay the original 14 and additional 10 checks locally on this stopped candidate. T3 still owns CLI/Skill/docs and must not import this snapshot yet. T2 lock/archive/backup modules were not imported.
