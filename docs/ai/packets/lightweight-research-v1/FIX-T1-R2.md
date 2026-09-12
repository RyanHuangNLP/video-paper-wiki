# T1 R2 bounded repair specification

This specification is prepared for review. It does not start a Builder or
override the pending external-launch confirmation. A separate R2 freeze must
bind these exact bytes, reviews and stopped R1 inputs before dispatch.

Preserve R1 and the earlier FIX-T1-R2-DRAFT.md. The stopped R1 snapshot is
b7554d0e8542d779de1a2b0fa4ed4b113fc2c1853627648d5873dcf4b53f39e0 at baseline
6963292a93ae322eaf9bb563b7b1170dee6a6fc6. Its 63 focused test passes remain
historical. The contract remains unchanged at SHA-256
d1d1ddef4273e37b5f8e30a14ad22f3cb3e6c6fa9782763ed5544d20479f2fab.

Architect review is terminal-1/architect-review-r1.json in this packet's evidence
root, SHA-256 b1fcf5a42769026fc5e801c49874347df23d762e51f9b8cf402b993f140fd50f.
It binds all six stopped source/copy bytes and eight reproduced failures.
Independent review adds the Unicode and unsafe paper-directory cases below.
The original independent record has a truncated snapshot ID and an unreliable
timestamp; only its forthcoming explicit erratum can bind the corrected source
identity. Preserve the original record as evidence, not a valid exact-head claim.

## Required repairs under the unchanged contract

1. Reject non-string trace enums before set membership. A caller-supplied list
   or object as a route status returns LIGHT_CONTEXT_INVALID, never TypeError.
   Check the other optional trace fields for the same class of malformed input.
2. Reject oversized or unsupported numeric values before float conversion.
   Candidate score 10**400 returns LIGHT_CONTEXT_INVALID, never OverflowError.
   Preserve boolean, nonfinite, rank and actual-score equality checks.
3. Reject duplicate paper IDs on the new rewritten route before the legacy
   normalizer can silently deduplicate them. Ordinary legacy selection stays
   compatible.
4. Validate the original supplied workspace path before resolution discards its
   directory edges: .work must appear in given absolute and resolved paths, and
   no parent or final component may be a symlink. Both the parent-symlink case
   and a workspace entirely outside .work must refuse.
5. Use the existing nonblocking workspace lock for the new public rewritten
   export. Occupied state returns LIGHT_WORKSPACE_BUSY; release on every exit.
   Raw retrieval/trace validators must not recursively reacquire an already-held
   lock. Preserve legacy workflow session kinds and caller locking behavior.
6. Check every relevant live source edge on the new route, including papers/,
   papers/<digest>/, source.md and source.json. Symlinks must not be silently
   skipped into a valid empty NO_RESULTS trace. Reject hardlinked source files.
   Apply checks before both successful and no-results returns and on live use
   of a traced context. Byte hashes do not replace path/type/link validation.
7. Reject strings that cannot be encoded as strict UTF-8 before query-plan
   canonical hashing. Test lone surrogates in original query and rewritten_query
   as well as trace strings received on import. Expected bad input returns the
   appropriate QUERY_REWRITE_INVALID or LIGHT_CONTEXT_INVALID, never an encoding
   traceback. Preserve valid Chinese and other Unicode text verbatim.

Apply these rules across new traced-context export, validation, render and
import. In particular, a legacy entrypoint must check the caller's given path
before its old resolver discards a symlink whenever query_plan is present.
Untraced legacy contexts retain their established behavior. Use narrow helpers
and acyclic imports; no CLI, workflow-schema or other lane API redefinition.

## Ownership and verification

The same six T1 paths remain the complete owner set:

- src/video_paper_wiki_research/light_query.py
- src/video_paper_wiki_research/light_context.py
- src/video_paper_wiki_research/light_index.py
- tests/research/test_light_query.py
- tests/research/test_light_context.py
- tests/research/test_light_index.py

Add meaningful regression cases for all reproduced failures. Assert closed
statuses, preserved existing output bytes, successful normal rewritten paths,
and unchanged legacy behavior. Re-run scoped query/context/index/QA/writing
tests using exact SOURCE provenance and COMMON's interpreter/environment rules.
No skip, mock replacement of owner code, dependency, network, or Git change.

Return NEW terminal-1/r2 immutable files, checks, report, handoff and ready as
COMMON requires; cite the R1 source and both reviews as inputs. Include actual
before/after source hashes and test commands/results. Stop writing afterward.
R2 is not accepted until independent checks and Architect review succeed.
