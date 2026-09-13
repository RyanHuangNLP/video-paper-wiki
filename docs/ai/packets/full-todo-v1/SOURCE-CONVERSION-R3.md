# SOURCE-CONVERSION R3 — complete legacy migration and summary semantics

Read with immutable R1 and R2. This closes the independent semantic review without
adding writable paths or changing accepted source/publication schemas.

After applying all newly converted sections, every claim owned by an upgraded v2
paper must have nonempty evidence. If a preserved legacy claim still has an empty
evidence array, return SOURCE_CONVERSION_UNSUPPORTED_CHANGE before staging. Do
not invent citations, retire the claim, delete it or drop its ref. A formerly empty
claim that receives valid new cited evidence through the explicit section mapping
may proceed through the ordinary v2 evidence_invalidation chain.

Preserving a legacy active extraction means preserving its actual raw/parser/run
and source inventory bytes. The original v1 record's active-extraction pointer is
not a new v2 history field or association: v2's display_head and active-extraction
mirrors are null without an explicit display decision. Do not claim a new pointer
history carrier exists. Existing event/association/snapshot bytes remain exact.

Preserve unrelated paper/repository records and their claim rows/history. The
complete compiler may regenerate an unrelated rendered page to reflect changed
cross-paper concept links. Those generated-page changes are explicit payloads
and remain subject to full prospective validation and page-retirement refusal.
No old paper or code record is rewritten merely to force page consistency.

`created_claim_ids`, `invalidated_claim_ids` and `unchanged_claim_ids` are pairwise
disjoint sorted sets whose union is the IDs produced by the provisional sections
of the selected light record. Created means absent from the current claim ledger;
invalidated means an existing claim's evidence profile/fingerprint changes;
unchanged means exact existing text, evidence fingerprint, assessment and event
history survive. Preserve the old evidence wire spelling/order in the latter case.
`location_migrated_claim_ids` independently names all old claims of the selected
upgraded paper whose location anchor is changed to the required v2 block anchor.
It may overlap invalidated/unchanged and include preserved claims not present in
the light record. It never contains a newly created claim. Missing reviewed_at
keys gain only null as already specified, without implying human review.

System event actor/decided_by is exactly `source-conversion-v1`. The exact genesis
reason is `Created from lightweight record <record_id>; source association <association_id>.`
The exact invalidation reason is `Evidence changed by lightweight record <record_id>; source association <association_id>.`
Substitute the validated IDs without extra whitespace or prose. No event is made
when the fingerprint/profile is unchanged, even if the light record ID differs.

Use associate_source with the complete existing association inventory. Selection
is by the full frozen observation/version key and exact raw/registration proof,
not by the source ID alone and not by display_head. Multiple declared versions
may share raw bytes; do not choose the first association. Existing association
inventory, version conflict and provenance-variant refusals remain unchanged.
Supplied DOI/arXiv identifiers must normalize to the canonical paper ID or an
already present canonical alias because existing aliases are immutable.
