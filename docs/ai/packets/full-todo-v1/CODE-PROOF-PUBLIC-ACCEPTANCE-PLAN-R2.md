# Public CODE acceptance preparation — R2 supplement

Read with `CODE-PROOF-PUBLIC-ACCEPTANCE-PLAN-R1.md`. This supplement addresses
the seven findings in `public-acceptance-plan-review-r1.json` without changing
the current resource repair packet or authorizing public implementation. The
future source allowlist, interface freeze and exact resource baseline remain
separate prerequisites. Preserve the R1 plan and review unchanged.

## Exact errors and precedence

Exercise each public semantic code and its applicable closed reason/context
shapes from R7/R9, separately from success schemas. Assert the existing outer
envelope and exit status 2 for refusals. Include bounded instance pointers,
path-sorted target blockers, exact conflict contexts and distinctions among
state-invalid, not-ready, target-ineligible and conflict outcomes.

Limit cases cover `/input`, `/request`, `/bundle`, `/intent`, `/observation`,
`/config`, `/handoffs/<index>` and `/output`, with exactly the specified
`instance_pointer`, `limit_name`, `limit` and `observed` fields. Check R8's
complete phase/group/reason/operation/errno/prior/failed-groups context, including
nullable members, without raw paths, parser messages or syscall exception text.
Persistent lineage failure overrides semantic, operation and cleanup errors;
when lineage remains valid, preserve R8 cleanup-versus-operation precedence.

## Admission and canonical bundle caps

For request (65536 bytes) and observe (1048576 bytes), cover cap-minus-one,
equal and cap-plus-one raw inputs, whitespace-heavy valid inputs and oversized
malformed JSON. Read at most the fixed cap-plus-one prefix, report the bounded
observed count and select the admission error before decoding oversized data.
Within the fixed admission bound, separately fail lowered serialized request,
intent and observation limits before any output installation.

The input bundle is exactly `manifest.json` plus `objects/`. The manifest is a
canonical saved `code-git-bundle` envelope; copy those exact bytes, including LF,
to output `bundle.json`. Copy only the declared validated object bodies into
the output objects family. This is never an archive, whole-directory copy or
directory-hash substitute. Test the canonical manifest's `max_bundle_bytes`
boundary at `/bundle`, including malformed hard-cap overflow and no-mutation
assertions. Preserve the R10/R11 distinction between raw admission and saved
canonical byte limits.

## Observable raw prefixes and order

Assert raw installation order: existing request, new intent, exact bundle,
OID-sorted bodies, then observation. Before bundle installation, request plus
intent reports `pending_raw_bundle`; after bundle installation, absent bodies
report `pending_raw_bodies`. Cover empty, partial and complete valid object
prefixes, including every body present with observation still absent. Assert
the exact missing-list order and next action in each state. Repeat observe
using the identical bound inputs and install only the missing valid suffix.

Unknown entries, incorrect bodies, non-prefix sets and observation without
dependencies are refused according to their exact R5/R7 classifications. Never
repair or adopt corrupt/non-prefix content. Retain the separate config-subset
and handoff-prefix rules from the R1 plan.

## Installer failures on every exit

Enumerate the actual R8 event rows, rather than using one generic failure case:
one-byte short writes; zero-progress writes; link failure with final absent;
link failure with a distinct final appearing; successful link followed by
failed identity verification; and EEXIST with even byte-identical late data.

Exercise disappearance/replacement of the owned temporary inode, mode/link-count
changes, temporary unlink failure, file fsync failure, directory fsync failure
after a verified cleaned prefix, and close failure while remaining descriptors
are still closed once. Exercise mkdir failure with name absent/present,
post-create stat/open failure before ownership, parent fsync failure after
verified creation, KeyboardInterrupt and SystemExit.

For each event, assert the recorded phase, retained valid prefix, exact error
and final lineage precedence, no foreign deletion/adoption, no rollback of an
unverified final, and reverse-order close behavior. A syscall raising after an
observable effect never becomes a fabricated successful syscall result. Keep
the distinct-live-inode replacement method for portable adversarial fixtures.

## Resource origin and path grammar

Test exact source and wheel origins, missing/changed/undeclared schemas,
profile shape/hash mismatches, non-filesystem origins and external resolver
denial. Test resource/output overlap, resource ancestor and inode changes,
symlink/type/mode/link-count changes and changed bytes during final rereads.
Run those checks after successful, semantic-failure and installer-failure paths.
Unchanged initially invalid resources use the specified resource error; changed
or uncheckable retained resources use the R8 lineage error and group precedence.

Apply the resource R2 input-directory clarification in real admission tests:
valid `.work/a`, dotted and leading/trailing punctuation components, `.git`,
components longer than 128 characters, and nested Unicode/space names. Reject
bare `.work`, empty or dot/dot-dot components, repeated/trailing slashes,
backslashes, C0/C1/DEL and U+2028/U+2029, aliases and symlinks. Preserve the
4096-character total schema bound and separate semantic byte/NFC checks. The
output batch identifier grammar must remain unchanged.

## Evidence strength and existing CLI behavior

Normalized evidence cannot satisfy raw-only config/handoff derivation. Assert
the prescribed not-ready/raw-evidence-required outcome and exact normalized
missing/inaccessible/unavailable eligibility. Source association remains
explicitly unverified; it is not a hosting or provenance attestation.

Cover required hosting assertion, incomplete target sets, missing/unsafe and
unsupported-source blockers with exact path ordering and no unbound selector
echo. Preserve the independently eligible selected-config case within a mixed
raw target set and whole-set handoff requirements. Finally exercise the real
installed entry point, existing legacy commands/help/errors and zero-egress
instrumentation. No acceptance claim follows until the future frozen public
implementation passes these cases and its required regression/wheel checks.
