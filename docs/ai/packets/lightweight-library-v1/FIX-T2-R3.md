# T2 revision 3 — exact recovery ownership and bounded backup verification

Architect-authorized corrections within original contract SHA-256
`7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12`, baseline
`3368c6435db166a285b4b0e2df00f5d6a7491956`, and the same nine T2 owner paths.
The input is stopped R2 snapshot
`2a3ba59afb2a23cfa11c14b6f1e1ecf60bb161d591d675c9eed2964202c36355`.
Preserve R1/R2 work packages, frozen sources and all evidence byte-for-byte.

R2 passes all 23 original Architect checks, but additional independent checks
reproduce 23 failures with two positive controls. Controller R2 review separately
confirms recovery, cleanup, manifest, publication-race and ZIP defects. Read the
new Architect decision and both controller reviews bound in this revision freeze.
Read only the SOURCE of `architect_t2_r2_additional.py` and the original
`architect_t2_regressions.py`; port triggers to owned synthetic tests. Raw paper
corpus text, exported real evidence and raw real-paper assertion logs are outside
this Cursor task's input scope. Architect runs those local acceptance variants.

## 1. Validate typed journals without uncaught input exceptions

Object/array `kind`, `phase` and `outcome` cause unhashable TypeError before shape
validation. Validate exact types before enum membership. Apply the same principle
to every caller/persisted JSON field in these new modules; booleans are not an
integer schema version. Malformed journals remain unchanged and cause the
documented closed result, including list/backup paths consuming journal state.
Do not mask programming errors with a blanket exception catch.

## 2. Prove complete stage ownership before any cleanup

R2 drops directory inventories and treats any matching filename pattern as owned.
Consequently recovery deletes an unknown empty `workspace/user-folder/`, a foreign
`workspace/papers/<other digest>/source.md`, and an edited workspace.lock. A valid
top-level owner marker alone cannot authorize those bytes.

Validate the exact allowed directory and file set, owner shape/version/operation,
native producer identities and exact contents/hashes for the current operation
and phase BEFORE deleting any part of the stage. Bind the expected new digest,
native transaction/owner fields and lock bytes; accept no arbitrary digest/name
merely because it fits a regular expression. If cleanup needs a persisted native
artifact inventory, record it while ownership is known and validate it later;
never obtain deletion authority by freshly hashing unknown files during recovery.
This is a bounded internal journal/owner evidence-field addition if needed.

The untouched pre-staging shape is exactly the marker and only directories that
this phase created. Safe aborted-before-staging remains a distinct settled
outcome, with the old live paper unchanged. Unknown empty directories, user
additions, changed producer files, foreign owners and incomplete/unsafe sets
cause conflict with ALL bytes preserved. Validate the full set before unlinking
the first file; an eventual leftover-directory failure cannot undo partial loss.
Reject symlinks and hardlinks in owner markers, locks and generated files, and
unsafe parent edges; regular-looking basenames do not confer ownership.
Preserve successful ordinary replacement and all existing recovery points.

## 3. Validate completed operation state and legitimate successor history

R2 reports complete/reused for an archive/restore with neither payload location,
or a replacement with missing/edited new live content. A complete journal is
historical evidence, not sufficient proof of current successful reuse.

Without a validated successor, archive completion requires its exact archived
payload and absent live old slot; restore completion requires absent archive
payload and exact restored live inventory; replacement requires exact old archive
and exact new live inventory, with no unrecognized leftover stage. Use original
frozen inventories, including notes and directory sets. Exact public retry must
continue to enforce those exact-result requirements.

Legitimate recognized successor operations may move these payloads. In particular
archive -> restore -> recover and archive -> restore -> archive -> recover must
remain valid. Replacement followed by a recognized archive of its new paper must
also remain explainable. Validate the unambiguous successor's shape, shared paper
and archive identities, inventories and actual terminal payload. Do not assume
all old archives must retain their payload forever, use a journal's presence alone
as authority, or guess ordering from arbitrary directory iteration. A validated
superseded historical event may return ok with an explicit historical/superseded
state and `reused=false`; reserve `reused=true` for the verified exact result.
Missing/both/foreign/ambiguous terminal states and unexplained edits need attention
and preserve bytes. No new public command, synthetic success or human gate.

Validate retained `event.json` records as well as payload manifests: exact
persisted shape and matching schema/archive_id/paper_id/operation_id/state for
the corresponding archive or restore event, including when its payload moved
away. An event with changed owner/state is not a historical successor proof.
Build successor edges from explicit operation identity or a unique exact
inventory/identity match. Reject missing or multiple successors when a move needs
explanation; never infer order from directory iteration, mtime or sorted random
IDs. Include positive replacement -> archive history and archive -> restore ->
archive histories in addition to negative ambiguous/forged-event checks.

## 4. Complete manifest identity and policy checks

Recomputing workspace_id and manifest hash must not bless a relative, traversing
or nonnormalized workspace_root. Validate original path syntax lexically without
touching the old filesystem: absolute POSIX path, no empty/dot/dot-dot components,
no backslash/NUL, and the original required `.work` component. The same absolute
normalized syntax applies to original extra paths, except explicitly selected
read-only extras do not themselves require a `.work` component.

Validate exclusion rows against the exact documented producer policy, including
safe paths and the corresponding known rule. Reject arbitrary strings, included
files mislabelled excluded, and overlapping contradictory rows. Derive the
accepted path/rule pairs from recognized captured index/lock/empty-stage state;
the verifier checks their lexical/policy consistency without consulting old paths.

An extra row must refer to an original regular `.md` path outside the original
workspace, whose basename exactly matches its mapped
`exports/external/<sha256>/<basename>.md`, with matching inventory hash and unique
path mapping. The old external file need not exist during verification/restore.
Every current explicit external mapping must be accounted for. Preserve previously
restored exports already inside the workspace as ordinary included historical
files on later backups; do not demand a new external mapping for those bytes.

Clarification shared with T3: only generated workspace/output/restore paths must
be under `.work`. Explicit caller-selected read-only extra Markdown inputs may
be outside `.work`, as JSON inputs may, with full parent-chain/regular-file/no
symlink/no-hardlink checks, strict UTF-8 and the 8 MiB cap. Do not follow stored
receipt/model paths or scan external directories. Add an outside-.work positive
test using a synthetic explicitly selected extra.

## 5. Atomic create-only publication

The existing `exists()` then `os.rename(tmp, output)` can overwrite an output
that appears in between. Publish the generated backup file with an atomic
create-if-absent primitive. Preserve any newly appearing output; exact pre-existing
reuse remains allowed only after full byte/snapshot validation. Do not replace
another file, symlink or hardlink. Keep exclusive temporary-file ownership and
clean only verified owned bytes. Retain the final source snapshot recheck.

Restore has an analogous final destination race: an existing empty directory
must not be replaced simply because rename would allow it. Use safe no-replace
directory publication on supported Linux/macOS or a documented closed fallback
that preserves both destination and staged bytes. Add an actual race regression
beside normal successful publication; do not claim protection from exists alone.

## 6. Bounded deterministic ZIP parsing and closed corrupt-input failures

R2 reads the full archive before applying its 136 MiB cap, a truncated EOCD marker
raises struct.error, and a changed local CRC with unchanged central CRC verifies
successfully. Check file size/identity before allocation and use a bounded read
with a cap+1 overflow check so growth does not bypass the limit. Verify input
chain and file identity consistently for the bytes actually parsed; avoid parsing
one snapshot and then reopening unrelated bytes for member validation.

Check every structural boundary before unpacking. Enforce exact deterministic
local/central metadata and their consistency: names/order/offsets/entry counts,
stored sizes, CRC, flags, versions, fixed timestamp, private regular attributes,
empty comments/extras and no encryption/multi-disk/ZIP64/data-descriptor variants.
The supported writer format is the authority; arbitrary otherwise valid ZIP
variants are not automatically this backup format. Reject unaccounted gaps,
overlaps, prepended/trailing bytes or contradictory directory metadata.

Expected corrupt-input conditions, including bad member CRC/truncation and
zipfile read errors, return LIGHT_BACKUP_INVALID or the existing ResearchError
boundary. No raw struct.error/BadZipFile traceback or unbounded read. Catch known
parsing/I/O failures in their proper scope, without swallowing arbitrary errors.
Add positive writer->verify->restore and repeated history/extra roundtrips.

## 7. Restore staging cleanup also preserves unexpected additions

The restore helper recursively unlinks every regular stage file in finally.
Validate a complete owner-bound known generated inventory before cleanup. If a
publication failure leaves unknown additions or edited generated files, preserve
the stage and report the actual failure with its recoverable location, rather
than deleting those bytes. No age-based cleanup and no unowned recursive delete.
The optional restoration-record parent collision was not reproduced as a valid
archive under the text policy; it is not a counted defect or required new feature.

## Delivery and stop

Run all three owned tests plus relevant existing light PDF, recovery, index,
workspace and workflow suites with the locked Python 3.13 source-local setup and
short real temporary paths. Keep positive normal-operation/history tests alongside
the refusal tests. Do not weaken tests, remove assertions, skip coverage, add a
dependency, download models or claim integrated/full-suite/wheel acceptance.

Freeze new terminal-2/r3 files/checks/report/handoff/ready, binding this revision
freeze, original contract and the exact R2 snapshot. A normal evidence-location
denial permits a complete source-local r3 bundle and a location report, never a
second-method copy bypass. Stop source writes after the handoff. No T3 import,
Git mutations, merge, model change, new worker or fabricated approval.
