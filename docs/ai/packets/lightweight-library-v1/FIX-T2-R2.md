# T2 revision 2 — preservation, recovery and backup verification

Architect-authorized corrections within unchanged CONTRACT revision 1 SHA-256
`7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12` and the original
nine T2 owner paths. Public APIs, other lane ownership, baseline, dependencies,
workflow kinds, storage roots and product scope remain unchanged.

Input is stopped r1 snapshot
`f8b2808ed47394434af430de74c499ab541b66ac859610c5ad550c19f191fb02` at baseline
`3368c6435db166a285b4b0e2df00f5d6a7491956`. Preserve r1 and all original evidence.
Architect replay independently reproduced **23 failures**. Read:

- E/architect-t2-r1-decision.json
- E/architect-t2-r1-replay/checks.json, stdout.log, junit.xml
- ROOT/.work/acceptance/lightweight-library-v1/architect_t2_regressions.py
  (test source SHA `aa94f8337a6c6cec8312a0d2d6328a8e18722160abc74708eaf7a45437f26e03`)

E is ROOT/artifacts/verification/manual-pdf-v1/lightweight-library-v1;
ROOT is /Users/huangzhanpeng/python_code/video-paper-wiki. Read the test source for
triggers and add equivalent meaningful regressions to the three owned test files
using synthetic fixtures. Do not read/print raw real-paper text or run the
Architect's real-corpus variants through Cursor; Architect replays them locally.

## Required fixes

1. **Owned atomic temporary files.** Metadata currently writes through an
   existing `source.json.tmp`, overwriting/removing unrelated bytes and modifying
   a hardlink referent. The shared JSON helper has the same pattern. Use exclusive
   creation of owned temporary files and only clean files created/verified by the
   current operation. Existing unrelated regular files, symlinks and hardlinks
   must remain untouched. A safe alternative temp name may allow the operation;
   otherwise return a closed conflict. Check full chains and destination identity.

2. **Take workspace lock before managed paper layout.** Native extract_pdf
   currently creates `papers/` in `_prepare_workspace` before trying the lock.
   Establish/validate only the workspace root before the shared lock; create
   managed paper/transaction state after it. Keep existing add compatibility,
   workspace -> paper lock order and separate replacement stage-local lock.

3. **Validate journals and every actual transition.** Recovery currently marks
   an edited moved archive or edited restored live paper complete, publishes an
   altered staged replacement and accepts changed owned_relative_paths. Validate
   the full versioned journal shape, operation ID/filename, kind-specific phase,
   exact intended safe paths, old/new IDs and complete file/directory inventories.
   Validate actual payloads against those frozen inventories before each move,
   after a recognized crash move and before claiming completion/reuse. A source
   pair being parseable is insufficient when notes/extras changed. Neither-side,
   both-side, foreign, hash/set mismatch and malformed journal states preserve all
   bytes and require attention. Do not replace the expected inventory with a fresh
   scan of modified content to make recovery pass. Completed journal records also
   require validated shape/identity; do not short-circuit arbitrary fields merely
   because phase equals complete.
   Archive manifests require their exact versioned shape, archive directory ID,
   original/transport paths and complete directory inventory too. Unknown
   top-level fields, mismatched IDs, omitted existing directories and duplicate
   entries are invalid. See controller-review-r1.json for independent triggers.

4. **Safe recovery cleanup.** `_discard_owned_stage` currently recursively
   removes unknown nested text in a stage-local workspace. Validate the complete
   owner marker, intended target, version and exact known native producer layout,
   locks/markers/payload inventories before removing generated partial state.
   Unknown additions or user edits must remain untouched and cause conflict.
   If an untouched failed pre-staging operation is safely abandoned, record that
   terminal outcome explicitly while keeping the old live paper unchanged; do
   not leave a permanently pending journal after deleting its only recoverable
   state, or claim a replacement occurred. An explicitly validated `complete`
   operation may carry outcome=aborted-before-staging and an explanatory result;
   this is a settled recovery event, not a successful replacement. Validate that
   outcome's exact allowed state, and keep it out of pending backup blockers.

5. **Exact replace retry.** Repeating the same completed replacement currently
   fails because the old active slot is absent. Resolve a unique matching
   recognized old/new/title event and validate old archive plus exact new live
   payload before safe reuse. Pending exact retry/recover must advance only its
   owned validated steps. Different input, changed content, duplicate events,
   separately recreated live old paper or unrelated new active slot conflict.
   Never merge notes between active papers or create duplicate pending events.

6. **Snapshot check immediately before backup publication.** The two scans
   happen before ZIP construction; an edit in `before_backup_publish` is accepted.
   Recheck the complete captured source/file sets, hashes and recognized state
   after ZIP construction and immediately before create/reuse. Detected changes
   leave output absent or preserve the pre-existing output. Keep the fixed bytes
   deterministic and create-only; do not replace another backup during a race.

7. **Restore every archived byte without overwriting prior records.** Restore
   currently overwrites an included `.light-library/restoration.json`, including
   a legitimate record from a previous restore. Optional generated restoration
   metadata must never overwrite an archived member; it may be omitted or written
   into a collision-free owned location after validation. Validate the final
   complete restored inventory against the archive before publication. Repeated
   backup -> restore cycles preserve all existing historical files and every
   included file's exact bytes. Existing final destination still conflicts.

8. **Full manifest validation.** A recomputed manifest hash currently permits
   invalid workspace identity, non-string workspace_root, arbitrary extra-output
   rows, malformed exclusions and a trailing non-object file entry. Validate all
   types/shapes/bounds, every inventory row/count, workspace_id against canonical
   {workspace_root}, safe original root syntax without following it, exact session
   remap, exclusions and explicit .md extra mappings. Cross-check each extra's
   content hash/path/namespace against a real inventory member, reject aliases,
   collisions and unaccounted mappings. Do not follow old external paths. Check
   allowed text/media policy on every member, including exports/external; that
   namespace is not an extension-policy exemption. Prefix/file-directory
   collisions must close before extraction, not raise an uncaught OS exception.

9. **Fixed ZIP and input-chain verification.** Refuse symlink member mode,
   non-private/nonregular attributes, wrong timestamp on the manifest too,
   unexpected extra fields and ZIP64 metadata even for small files. Verify the
   complete deterministic format: local/central member metadata, ordering,
   comments/extra entries, no encryption/multidisk/ZIP64 and bounded actual sizes.
   Do not infer no-ZIP64 solely from small file_size values. All archive input
   parent chains must reject symlink traversal; verification remains read-only
   and does not require the old workspace or original PDF to exist. Expected
   malformed containers return a closed result/ResearchError, not traceback.

## Scope and evidence

These fixes implement already frozen invariants. The pre-staging aborted outcome
above is a narrow internal journal clarification resolving a failed operation
without fabricating replacement; no new public command or destructive action.
Record its validated shape in the module documentation/tests. All other schema
and API semantics remain the original contract.

Run all three owned tests plus relevant full existing PDF, recovery, index,
workspace and workflow suites, using the locked Python 3.13 source-local setup
and short real temporary paths. Add positive exact retry/recovery/roundtrip tests
alongside refusals; do not turn normal operations into unconditional conflicts.
No test weakening, skips, broad exception swallowing or special casing the
Architect test names. No full-suite/integration/wheel claims on active mixed code.

Publish a new E/terminal-2/r2 immutable files/checks/report/handoff/ready bundle
with actual hashes, previous snapshot, original contract and this revision freeze.
If the ordinary Cursor sandbox disallows E, retain a complete source-local
`.work/verification/lightweight-library-v1/terminal-2/r2` bundle, report its exact
hashes/location and stop; do not retry through alternate filesystem methods.
Architect can reference that local bundle without bypassing the denied copy.
Then stop writing. No T3 import/Git/merge/human acceptance until separately issued.
