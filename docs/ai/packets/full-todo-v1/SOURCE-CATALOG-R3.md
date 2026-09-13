# SOURCE-CATALOG R3 — projection closure and query input bounds

Read with immutable R1/R2 and the exact profile R1. This closes the semantic
review assertions without adding an owned production path or changing the
source-of-authority rules. Earlier advice is not an implementation contract.

## Complete projection assertions

The producer validates its derived row object against the retained source state
before installing a cache. Its paper/repository/source/association/decision/head
identity sets must exactly match that state; no duplicate, dropped or invented
rows are permitted. Each claim has exactly one canonical owner/reference and
exactly one derived assessment head, whose ID/hash/profile match its validated
terminal event. Lifecycle is the reference's required active/retired value;
assessment is the existing ledger value already checked against event history.
Missing, unknown or conflicting provenance preserves the source/history error;
there is no default lifecycle or assessment.

Each claim's evidence rows have exactly the original evidence count and ordinals
0 through count-1, with byte-equal locator/relation/source transport strings.
The three-field wire object remains encoded transport: do not replace locator
strings with decoded objects containing historical PDF bbox floats. Decoded
locators are transient inputs to exact resolution only. Original semantic
document text remains exact UTF-8 in documents.json_text as specified by R1.

All projected foreign identities resolve within their appropriate groups.
Every source and every artifact has exactly one coverage row. Derived identity
sets are sorted unique sets computed from the validated source ancestry, not
accepted as producer assertions. A source may be registered without an owning
paper/repo, and a valid historical derived artifact may be unreferenced; those
are explicit coverage states, not missing mandatory foreign keys. Legacy v1
papers have no invented modern association/display references. Null display
selection is valid and must not create a fake display-head row.

Legacy PDF/code resolution starts only after collect_source_state has validated
the complete source/capture/parser/run or code-manifest ancestry. Missing or
mismatching ancestry is a typed validation error, never an unsupported success.
The unsupported PDF states cover only an otherwise valid citation whose text
position cannot be reconstructed under R1/R2's exact legacy rules. Modern display
selection never supplies authority for either legacy citation kind.

Cache parsing applies the closed artifact schema, canonical byte spelling and
self-digest check. It does not treat an old cache's identities as current Vault
authority. A well-shaped, self-consistent old/forged cache is stale whenever it
differs from complete current reconstruction; malformed shape or bad digest is
invalid. The producer's full cross-row/state assertions run during every fresh
reconstruction, including status, so a malformed current source state cannot be
hidden by a cache that happens to have plausible rows.

## Query bounds and filters

Before any IO, validate the caller's exact string as UTF-8 and enforce both
512 Unicode code points and 4096 UTF-8 bytes. Compute NFKC then casefold, enforce
the same character/byte limits on that normalized string, then tokenize and
enforce 1000 resulting tokens. Either length-stage overflow is
SOURCE_CATALOG_LIMIT (exit 75); a blank/zero-token query or invalid UTF-8 string
is SOURCE_CATALOG_INVALID (exit 2). No truncation is permitted. This makes
compatibility-character and casefold expansion deterministic within the frozen
profile's existing limits. Document text is tokenized without the query bounds;
the existing document/cache bounds continue to constrain it.

Every source-excerpt hit inherits its owning claim's validated assessment and
lifecycle, including retired references. Paper filters use explicit paper
ownership and repository paper_ids only. Unknown well-formed paper identities
produce an empty result, not remote lookup or an invented owner. Query and
resolve never use display selection as a substitute for the cited association.

Required coverage includes malformed/missing source history; projection set,
ordinal and foreign-key mismatches; all five assessment states with both
lifecycle values; exact PDF/code ancestry; and raw/normalized expansion at the
input limits. No changes to legacy contracts, source publication, profile bytes,
human gates or merge authority are authorized by this clarification.
