# T3 R2 bounded writing repair draft

Stopped R1 snapshot is
0e005388e60f104da964d534219148819b4f6c24161b6cf3259eb632428771f2.
The Builder's 42 scoped passes remain history. Architect's exact-source
probes/t3_acceptance.py run is bound in terminal-3/architect-probes-r1.json:
11 of 12 targeted checks fail. R1 is not accepted. Preserve every R1 byte.
This draft is not a dispatch; Root freezes reviewed bytes and issues a prompt
under the user's already recorded informed authorization and normal approval.

Same two owned paths only: src/video_paper_wiki_research/light_writing_project.py
and tests/research/test_light_writing_project.py. No CLI, other lane or shared
helper edits. Keep CONTRACT and its public wire/storage schemas unchanged.
The following implement existing semantics; private validation/publication
helpers may change within the owned module.

1. Ordinary multiline Markdown and revision instructions must work. The broad
   Unicode control-category check currently rejects LF, so paragraphs, lists
   and section edit instructions fail. Allow ordinary Markdown whitespace
   (LF, CR and tab) for body/instructions, preserve exact accepted body bytes
   in state, require nonblank provisional body, and retain strict one-line
   titles/goals, length caps and citation rules. Reject malformed UTF-8,
   surrogates and non-text unsafe control values with a closed result. Test
   multisection paragraphs, lists and exact reimports, not just one-line prose.

2. Publication must support exact interruption retry without inventing HEAD
   authority. After a complete child revision but before HEAD, R1 re-enters
   _export_section_unlocked and rejects its own expected child as an extra
   revision before computing the retry identity. Compute and validate the
   expected child, complete parent ancestry and exact original wrapper, then
   allow only that owned retry bundle alongside the parent chain. An unrelated
   orphan stays a conflict. Conversely, deleting an existing HEAD after section
   export currently permits import to recreate it; reject missing or edited
   preexisting HEAD. Do not infer publication ownership merely from a plausible
   content-addressed directory. An initial no-HEAD project can be pending only
   with validated owned incomplete publication. Keep enough owned publication
   intent through interruption so a legitimate initial retry is distinguishable
   from arbitrary HEAD deletion. An existing valid parent HEAD or an already
   published exact child remains the only normal section authority. Test before
   revision publication, after revision/before HEAD, after HEAD/before cleanup,
   exact reuse, different-document retry, missing HEAD, and foreign/edited
   staging. Expected filesystem publication failures return a conflict result,
   not an unhandled OSError. Preserve prior revisions, HEAD and unrelated files.

3. Enforce supplied workspace/output path edges before lexical normalization.
   The output raw symlink/../file case currently exports to another normalized
   file. Also an output inside .light-index/new-parent/draft.md is accepted when
   new-parent does not exist because managed-root detection is conditional on
   parent existence. Reject raw parent-traversal components on the new writing
   APIs if necessary, preserve ordinary absolute/relative .work paths, check
   all source/state ancestors for symlinks and hardlinked files, and protect
   every existing managed root regardless of whether the target parent exists.
   Apply a local writing guard before calling shared require_product_workspace;
   T2 owns that helper and this lane may not change it. Backup helper remains
   read-only and acquires no nested lock. Invalid/refused paths must not create
   directories or alter output/state. Test public entrypoints, safe outside
   reports output, raw symlink/.. and fresh nested managed output parents.

4. Replay stored history semantics, not only caller-supplied hashes. R1 accepts
   a draft edited together with its manifest hash, although draft is required
   to be deterministic from validated context/document. R1 also accepts a
   self-consistent child marked target=s1 that changes s2 with an invented
   citation, and declares its history/export/backup valid. Validate the original
   writing context shape/evidence without requiring currentness for historical
   replay; validate exact original outline and computed project_id; validate
   initial section states; validate each child target, instructions and cited
   section document against the original evidence; ensure only the named target
   may change and all other section values equal its exact parent. Recompute
   revision identity, all manifest duplicates and deterministic draft bytes.
   Apply the same complete replay to history, live export/import/retry and
   backup. Preserve relocation semantics: valid moved history is historical
   and includable, while live reuse remains workspace mismatch. Detect malformed
   nested objects and unhashable enums as conflict diagnostics instead of
   allowing KeyError/TypeError/UnicodeError to escape. Extra files, directories,
   cycles and foreign or skipped parents stay conflicts; never repair them.

Add meaningful same-scope regressions for all groups, including the exact
Architect reproductions and normal success/history/relocation behavior. Re-run
the supplied Architect harness unchanged for a fresh report outside R1, plus
COMMON's scoped writing-project/legacy-writing/context tests with explicit
exact-source pytest override. No full dual-Python or CLI work in this repair.
Return fresh terminal-3/r2 files/checks/report/handoff/ready with source hashes,
test origin/results, architect_accepted=false and stopped_writing=true; then
stop writing. Integration, real-model paper trials and final acceptance follow.
