# T1 revision 3 — comparison output and validated prior references

Architect-authorized corrections within original contract SHA-256
`7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12`, baseline
`3368c6435db166a285b4b0e2df00f5d6a7491956`, and the same six owner paths.
Input stopped R2 snapshot:
`d9aebbe770a36863f6186ef9b57536dc9f6f4f2b747f0f54c86794b896944293`.
R1 and R2 remain immutable. R2 passed all 14 original Architect regressions,
but new independent review reproduced nine failures and one positive pass.

Read the new Architect decision, additional checks.json and test SOURCE
`.work/acceptance/lightweight-library-v1/architect_t1_r2_additional.py`.
Do NOT read the additional stdout.log or junit.xml through Cursor: one assertion
contains raw real-paper export text. The decision and this packet summarize the
failures sufficiently; port the test triggers to owned synthetic fixtures.

## 1. Preserve exact explicit paper selections

`[A,A,B]` silently becomes `[A,B]`. Reject duplicate IDs as
LIGHT_SELECTION_INVALID before deduplication or retrieval; validate the original
2–8 element selection and every ID. `[A,A]` already closes due to the final
minimum-size check; preserve its refusal and add `[A,A,B]`/over-limit duplicate
cases so duplicates cannot mask the requested count. Invalid selection types
should consistently use LIGHT_SELECTION_INVALID. Do not change the legacy index
normalizer's semantics or another owner's file.

## 2. Render usable cited Markdown tables

R2 appends citation markers and escapes the entire cell, leaving literal
`\[@chunk\]` text; the generated reference section alone does not attach the
claim to its cell. Conditions are escaped twice and the generated `<br>` becomes
escaped text. Escape caller text/condition values exactly once, then compose the
trusted citation markers/links and line-break markup. Do not re-escape generated
Markdown. Each provisional cell must contain a linked source citation with the
correct paper/page; links must resolve relative to the actual output path.

Test real Markdown output with pipes, newlines, square brackets, angle brackets,
Unicode and backslashes in user text/conditions/title/dimension/reason, checking
cell boundaries and link destinations. Prevent raw caller markup from breaking
the table while retaining its literal content. Keep the existing shared pure
renderer and light_context changes confined to the original allowed tiny scope;
solve composition within the new modules. Preserve create-only refusal and
current-source/cross-paper checks.

## 3. Validate enum types before membership checks

`comparability={}` or `[]` currently escapes as TypeError because set membership
is evaluated before a string check. Validate types before enum lookup and return
the documented closed result/ResearchError. Audit the same pattern in new
knowledge/comparison typed documents for expected malformed JSON values; do not
hide implementation errors with a blanket catch. Add malformed-type regressions
alongside successful valid documents.

## 4. Validate prior pointers' own referenced bundles

Schema-correct CURRENT pointing to a nonexistent `f*64` view is overwritten by
build; schema-correct HEADS pointing to a nonexistent record is overwritten by
import. Validate the prior pointer's own reference identity and referenced bundle
before replacing it. Missing, unsafe, foreign or malformed references must be
preserved and reported as conflict. Validation includes schema, exact file and
directory set, file sizes/hashes, IDs, relative paths and ownership consistency.
Read-only listing may report conflict entries, but must never present an absent
or invalid record as current or quietly clear its head.

The existing prior target does NOT have to equal the NEW target: normal import of
a new valid record and build of a new view must advance a valid older pointer.
Valid historical records/views can remain referenced after source edits or
archival. Distinguish immutable bundle integrity from current source status so
that legitimate updates after such changes still work. Retain old artifacts.

If validating a historical view ID needs its original fingerprint, persist and
fully validate that fingerprint in the new module's internal view manifest. This
is a bounded internal evidence-field addition; public APIs, context/document
schemas, dependency pins and storage roots stay unchanged. Never reconstruct an
old fingerprint from changed current heads to make a bad reference pass. Preserve
the interrupted publication/retry behavior from R2 and test both missing/foreign
prior reference refusal and valid old-to-new pointer advancement.

## 5. Enforce exact record metadata shapes

Adding an unknown top-level field to manifest.json leaves the record current.
Adding an unknown identity.json field and updating only its declared file hash
also leaves it current. Validate the exact versioned shapes for record manifest,
identity, source snapshot, inventory rows and view manifest, not only selected
keys and hashes. Unknown/malformed structures are preserved/conflict and cannot
contribute current concepts. Keep valid stale/missing-source classification after
the integrity checks, and preserve normal relocation behavior.

## Evidence and stop

Run the same three owned tests plus full test_light_context.py, with new synthetic
regressions and explicit positive pointer advancement/rendered-link tests.
Architect will replay the original 14 and additional 10 checks locally on your
stopped candidate. Do not claim raw real-paper or full integrated acceptance.

Publish a fresh immutable terminal-1/r3 files/checks/report/handoff/ready bundle,
binding original contract, this revision freeze and previous R2 snapshot. If its
ordinary location is denied, keep a complete source-local r3 bundle and report
the location without another-method copy retry. Stop writing. No T3 import, Git,
merge, additional agent, credential/config inspection or model/dependency change.
