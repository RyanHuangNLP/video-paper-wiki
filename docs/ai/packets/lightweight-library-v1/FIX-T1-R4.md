# T1 revision 4 — record ownership, snapshot consistency and citation labels

Same original contract SHA-256
`7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12`, baseline
`3368c6435db166a285b4b0e2df00f5d6a7491956`, and six T1 owner paths.
The exact stopped R3 snapshot is
`0267502300995cce09fc72fd4a1f3dbfc8fb2f6bcdf2cf2fd34dcce9d38355e5`.
Keep every previous revision and evidence file immutable.

R3 passes all original 24 root regression cases and its 72 focused tests.
Independent controller review and Architect replay then reproduce four failures;
the complete-workspace relocation positive control passes. This packet corrects
those four remaining ownership/integrity/rendering defects in the original scope.

Read the bound Architect decision and controller-review-r3.json. Read the SOURCE
of `.work/acceptance/lightweight-library-v1/architect_t1_r3_additional.py` for the
exact triggers, together with the earlier test sources. Port them to owned
synthetic fixtures. Do not execute the root real-corpus variants through Cursor,
read raw real-paper data or read raw real-corpus assertion logs.

## 1. HEADS binds each paper key to its actual record

`{paper_B: record_A}` passes prior validation because only record values are
validated. Importing B then overwrites the forged pointer. Validate every key/value
pair against the referenced record's immutable manifest/document/wrapper paper ID.
The record must be present, safe and internally valid and belong to that key.
The same rule applies to read-only listing diagnostics and both import/build
paths consuming HEADS; a wrong-key entry must appear as conflict or close,
never silently disappear or become valid through pointer replacement.

Preserve bytes on invalid references. Valid prior records can be stale or have
missing source after archival; source currentness is separate from immutable
record ownership. A correct old record can advance to a different valid new one.

## 2. A prior view must have its referenced records in this workspace

Copying just a valid view bundle and CURRENT from workspace A to workspace B
currently authorizes replacing B's CURRENT even when its referenced records do
not exist. Validate the fingerprint/heads and their paper-to-record identities
against the local retained immutable record bundles. Validate every record
reference that the view claims as current or historical. Missing, wrong-paper,
unsafe or internally inconsistent references are foreign/conflict and cannot
authorize pointer replacement. Do not treat a self-consistent view hash alone
as sufficient ownership evidence.

This is relative workspace membership, NOT an absolute original-root lock.
Copying/restoring the complete workspace with byte-identical paper, record and
view bundles must remain valid after index rebuilding; normal old-to-new view
advancement must work. A record may be stale or missing-source today while its
immutable bundle remains valid. Do not compare a saved historical fingerprint
to changed live sources or current HEADS to manufacture/reject its old identity.
If an invalid historical record cannot safely support building a new view, return
a clear conflict; read-only listing can still report it without deleting data.

## 3. Bind all redundant snapshots to the original record identity

After editing source metadata, changing manifest/identity snapshots and the
declared identity hash currently makes the old record current even though its
original wrapper snapshot and record ID remain unchanged. Cross-check
manifest.paper_snapshot, identity.paper_snapshot, identity.wrapper.paper_snapshot,
manifest.source fields, identity.markdown_path and the context/wrapper source
identity consistently. They must describe the same paper, exact relative source
path and original byte hashes. A declared identity file hash is not authority to
change the original record's source binding.

Validate these relationships as immutable bundle integrity before classifying
current/stale/missing-source. Unknown shapes and contradictory metadata are
conflict even if some source happens to match. Preserve ordinary unchanged-source
records, valid metadata-change staleness and complete relocation. Keep the
existing record ID derived from the actual original document/wrapper; no fresh
hashes reconstructed from edited live files to bless a contradictory record.

## 4. Render citation titles safely inside a table cell

Actual source metadata permits a newline in a title. The inline comparison
citation uses escape_md(title), so its newline splits the row even though the
column header is safely escaped. Apply table-cell-safe escaping to the untrusted
citation label exactly once before composing the trusted link. Preserve literal
pipes/brackets/angle brackets/backslashes/Unicode, source-relative links and page
anchors; do not re-escape generated Markdown or alter the shared pure renderer.
Test both header and inline citation titles, and assert the full row remains one
physical Markdown row with valid delimiters and linked citations.

## Evidence and stop

Run the same three owned tests plus full test_light_context.py, with four new
meaningful synthetic regressions and positive complete-workspace relocation,
stale-history advancement and normal linked table output. Architect will replay
all 29 accumulated root cases on stopped source. No test weakening, skip, blanket
catch, other-owner file edit, dependency/model change, Git or new worker.

Freeze a new immutable terminal-1/r4 files/checks/report/handoff/ready bundle,
binding this revision freeze, original contract and previous R3 snapshot. If the
normal evidence location is denied, keep a complete source-local r4 bundle and
report it; do not retry a denied copy via another method. Stop all source writes.
No T3 import or acceptance claim until separately instructed by Architect.
