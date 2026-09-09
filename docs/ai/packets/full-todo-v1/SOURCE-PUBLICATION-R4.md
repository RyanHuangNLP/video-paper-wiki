# SOURCE-PUBLICATION R4 — operation policy and exact registry paths

This clarification is read with immutable R2 (908c94b376f5e130883acd332c7d9c12378daf2cd37b21507a16185dd58d5628)
and R3 (67f3e8b0b287eb20e144de9f9300e97fd78adff6f785979a9dc9559a636310f6).
It addresses the second review without changing either prior revision.

Both NEW source publication kinds deterministically use `operation_type=ingest`.
Knowledge creates `.raw/derived/markdown-source/**` observations and
`.raw/derived/source-ledgers/**` historical snapshots. The unchanged transaction
policy in transaction_contracts._business permits derived creates only for
ingest; generic cannot carry these writes. Thus the review suggestion
knowledge->generic is rejected. Generic remains the existing wiki-only v1
publication/bootstrap path, with no change to its behavior. The new authority
validator requires ingest in transaction, receipt, staging and upstream children
for both kinds. Registration has the exact capture proof and one claimed raw
input; knowledge has null registration and no claimed inputs. These independent
constraints determine the kind, and cross-kind mutations fail. The head format
has no operation_type field; its bound receipt carries that value.

The registry paths, fully qualified without prose shorthand, are exactly:

* `wiki/meta/records/source-display-heads.json`
* `wiki/meta/records/assessment-heads.json`

Use these exact paths in dispatch, overlays, profile detection, head comparison,
read/write conditions and backup tests. Root-level `records/` aliases are not
authorized source publication paths. The source inventory/audit domain remains
the existing managed namespaces; an unrelated root directory is not silently
promoted into managed authority.

No additional schema or writable production path is added. Implementation follows
R2 with the precise R3 legacy field profiles and this clarification. All earlier
review findings remain preserved as observations rather than rewritten GO records.
