# T2 revision 7 — prove replacement as a restored paper's successor

Dispatch only with the exact R7 freeze and Architect instruction. Preserve R6
and all earlier source/evidence. Original contract, baseline and nine-path T2
owner manifest are unchanged. Only two paths may change relative to R6:

- `src/video_paper_wiki_research/light_library.py`
- `tests/research/test_light_library_recovery.py`

T3 and Architect independently reproduced a valid sequence on stopped T2 R6:
archive alpha, restore alpha, replace that SAME alpha with a distinct beta PDF,
then recover. Replacement completed and preserved the old archive, but recovery
reports that the earlier restore has no unique archive successor. Root's six
new checks produce two positive failures and four negative preservation passes.

`_unique_archive_successor` currently considers only completed archive/archived
operations. A completed replace/replaced operation also carries the old paper's
archive, complete file/directory inventories and archive event. The existing
recursive `_explain_completed_replace` already validates those bytes/event and
the successor new live/archive state. Reuse that proof instead of adding state.

Extend the successor selection to completed `archive`/`archived` OR completed
`replace`/`replaced` with the same paper ID and exact old file/directory inventory.
Keep archive-ID exclusion, exactly-one matching candidate, outcome validation,
recursive event/payload/live-state verification and cycle/duplicate refusal.
Do not treat a missing live paper as completion without this retained proof.
No journal/schema changes, broad recovery rewrite or fixture weakening.

Add synthetic repository regressions for the exact same-paper sequence and
repeat recovery/replacement; a subsequent archive/restore of beta; and refusal
with duplicate valid-shaped successor journal, wrong event identity, changed
retained note, or missing old payload. Verify successful recovery is read-only
for settled state and failures preserve all surviving user bytes. Source-only
Architect expectations are in `architect_t2_restore_replace_history.py`; do not
read/run its protected real-PDF corpus. Prior history, nested notes, all R5
ownership and unsafe native staging tests remain unchanged and active.

Run all three owned suites and related native/index/workspace/workflow suites
using the locked default Python, exact source provenance, offline flags and
short real temporary roots. Publish fresh `terminal-2/r7` evidence with all nine
owner files, R6 input, R7 freeze/contract, actual checks and byte-identical
handoff/ready. Only the two allowed paths may differ from R6. Stop afterward,
`architect_accepted=false`; no T3, Git/PR/CI, Vault or merge. A denied official
evidence write allows only a complete source-local bundle/location report, not
a retry through another copying method.
