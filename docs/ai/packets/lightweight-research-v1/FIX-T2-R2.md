# T2 R2 bounded repair specification

This is the concrete repair specification for stopped T2 R1. It grants no new
external invocation: Root must record the pending informed user confirmation,
freeze the reviewed inputs and explicitly dispatch before Builder resumes.

Baseline is 6963292a93ae322eaf9bb563b7b1170dee6a6fc6; stopped R1 snapshot is
5abc88dac56fc77f4ecbb9858f1f9c82950266a10558ee4a64842515a26a6181. The eight
owned paths and CONTRACT SHA-256
d1d1ddef4273e37b5f8e30a14ad22f3cb3e6c6fa9782763ed5544d20479f2fab are unchanged.
Preserve the R1 files, 94-test result, earlier draft and every review/erratum.
R1 is not accepted or eligible for T3 integration.

## Evidence and scope

The formal Architect stopped-source review is
terminal-2/architect-review-r1.json under this packet's evidence root, SHA-256
0ced884e765d50065a0253da2db923b77b4a055b5174d6b1880169ef947722c9. All eight
source/copy hashes were verified before and after four public-reader/publication
reproductions. Earlier active-source probes retain only their actual old hashes.

Independent-preliminary-review-r1.json binds the same stopped snapshot and
separates one executed full-plan truncation reproduction from four static code
findings. Its dynamic case kept all 50 live chunks intact but successfully
finalized a rehashed one-chunk full plan. The other independent review and its
required metadata erratum identify remaining final-merge specification detail.
Do not label the static findings as executed tests or copy inaccurate old
source-match claims into new evidence.

## Required repairs under the existing contract

1. **Complete live plan binding.** Recompute the full inventory and deterministic
   bounded partition from actual current derived chunks before state-sensitive
   export/import/finalize. Match exact IDs, pages, Unicode offsets, hashes,
   counts, order and text totals. Full plans must cover every chunk exactly once.
   Refresh plans must carry the full current inventory and the exact delta
   partition derived from their validated base. A self-consistent subset plan,
   wrong text total, wrong order or caller-only rehash must refuse.
2. **Refresh seeds and zero batches.** Recompute the safely remapped seed from
   the actual same-paper base and current chunks. Validate its complete document
   shape, bounded size and citation ownership even when there are zero batches.
   Metadata-only/removal cases remain supported. An arbitrary stored seed or
   truncated inventory is not an authorized base summary. Preserve all-unknown
   terminal closure without advancing HEAD.
3. **Persisted batch ownership.** Revalidate every accepted batch document and
   its actual binding to its own partition before reuse, merge or finalization.
   Validate shape, size, source/context hash and actual allowed citations; a
   chunk merely appearing in a different accepted batch grants no authority.
   Rehashing stored document JSON must not circumvent that check.
4. **Contiguous rolling merge.** Validate all required batch/merge files, exact
   step order, previous-step hash, next-batch document hash, bounded document
   shape and allowed citations from only the prior accumulator plus next batch.
   Missing/reordered/extra steps or resurrection of discarded citations refuse.
   For every nonzero completed job, the record's merge_sha256 must equal the
   canonical hash of exactly merges/<batch_count-1>.json. Validate that final
   step's whole chain and canonical document, not any matching earlier hash.
   Only the specified zero-batch refresh may use a null final merge hash.
5. **Record and ancestry semantics.** Bind extended-record document, context,
   inventory/counts, snapshot and provenance to the actual final job result.
   Refresh records bind the same-paper base; selection records bind the exact
   base/candidate relation and explicitly chosen sections/concepts. Validate
   same-paper and mode-specific ancestry, real referenced bytes and bounded
   acyclic traversal while permitting valid shared-base DAGs. A rehashed record
   with unrelated prose, parent, candidate, source or coverage must refuse.
   Public processing-complete records may not certify a pending/incomplete job.
   A private validated candidate used during owned publication is a distinct
   transient state, not a bypass granting public current/complete status.
6. **Completion and retry integrity.** Completion must identify the actual
   expected final document/record and complete immutable bundle. Refuse missing,
   edited, unrelated or nonexistent record IDs rather than returning a page
   path that does not exist. Exact retry must recover interruptions after
   record publication, after HEAD changes and around completion publication.
   Distinguish a head produced by this exact operation from a different
   intervening head. Never leave a recognized successful own publication
   permanently pending or report adopted/current success when adoption has not
   happened. Validate the complete object graph without recursive dependency
   loops between record and completion checks. Preserve old HEAD on refusals
   before adoption, and report/recover actual state after an injected interruption.
7. **Complete owned layout.** Validate both directory and file sets for pending,
   completed and zero-batch jobs. Unknown empty directories, extra files,
   symlinks, hardlinks and ambiguous stages must be preserved and rejected.
   Safe completion must precede cleaning only its exact owned publication
   stage. Pending/unknown state continues to block backup with a useful reason.
8. **Closed malformed-input handling and historical compatibility.** Keep
   exact schema/type/key/UTF-8/numeric/size checks at every newly strengthened
   persisted boundary; malformed enums or nested documents must not raise an
   unhandled Python exception. Preserve legacy one-shot import and stored
   records. Validate completed-history integrity after backup relocation without
   following old absolute paths or requiring a live resumption in the new root.
   Live operations still recheck actual current workspace/index/source identity.

These repairs complete the already frozen behavior. They do not change CLI
flags, public APIs, legacy workflow schemas, allowed models, source producers,
or any other lane's contract. If an actual storage/contract contradiction is
found, report the narrow contradiction to Architect before redefining it.

## Owned paths and acceptance

- src/video_paper_wiki_research/light_knowledge_batch.py
- src/video_paper_wiki_research/light_knowledge_refresh.py
- src/video_paper_wiki_research/light_knowledge.py
- src/video_paper_wiki_research/light_backup.py
- tests/research/test_light_knowledge_batch.py
- tests/research/test_light_knowledge_refresh.py
- tests/research/test_light_knowledge.py
- tests/research/test_light_backup.py

Add real-backend regressions for the five executed R1 failures and the static
boundary gaps. Check public results, unchanged notes/user files, exact source
coverage and successful normal/zero-batch/selection/retry flows. Include completed
backup/verify/restore history and interrupted/unknown-state backup refusal.
Do not weaken tests, classify corrupt state as historical success, or replace
missing owner code with mocks/skips. Follow COMMON's exact source/interpreter
and bounded scoped test recipe; full integrated suites belong to later acceptance.

Return NEW terminal-2/r2 immutable files/checks/report/handoff/ready. Bind R1,
this specification/freeze and actual review inputs; report tests and unresolved
issues honestly. Stop all writing after handoff. Root and controllers do not
implement these fixes; no Git, T3 transfer, PR update or acceptance occurs here.
