# SOURCE-CLAIM ledger projection, revision 1

**Purpose.** This note freezes the boundary between the pinned upstream
`claude-obsidian` ledger validators, the local closed projection used by the
catalog/compiler, and the prospective source-publication state. It is a
projection contract for the later implementation; it does not authorize
Vault reads, ledger mutation, publication, or a real source registration.

The pinned validator remains authoritative for authentic source and claim
semantics. The local projection is deliberately narrower and closed so that a
catalog row cannot acquire fields from permissive vendor mappings or from
rendered Markdown. A later inspect operation must validate the raw ledger bytes
with the pinned adapter before accepting this projection.

## Two validation layers

The pinned source validator accepts a root containing `schema`, `generated_at`,
and `sources`, and source rows with the required `origin`, `content_kind`,
`title`, `authority`, `review_status`, and `pages` fields. It also recognizes
the optional `content_sha256`, `ingested_at`, `retrieved_at`, `refresh_due`,
`independence_key`, and `supersedes` fields, and applies URL/file/current-byte,
freshness, independence, and supersession rules. Its mapping parser permits
unknown fields. The pinned claim validator similarly accepts the required
claim fields (`text`, `risk`, `assessment`, `confidence`, `location`,
`reviewed_at`, `evidence`) plus optional `notes` and `supersedes`; evidence
uses the wire relations `supports`, `contradicts`, and `context`.

That permissiveness is not a license for the catalog projection. The local
collector must first validate the complete raw bytes with the pinned adapter,
then emit only the exact closed rows below. A malformed raw row, unknown
schema/version, missing source FK, or noncanonical evidence wire is a stable
failure; it must not become an omitted row or an opaque catalog entry.

## Closed source projection

The source ledger root is projected as:

```text
ledger_meta: {schema, generated_at}
sources: sorted rows
source_pages: rows preserving page order and duplicates
source_artifacts: rows for file-source capture linkage
```

Each `sources` row has exactly the following fields:

```text
source_id, origin_kind, origin_locator, content_kind, title,
authority, review_status, pages,
has_content_sha256, content_sha256,
has_ingested_at, ingested_at,
has_retrieved_at, retrieved_at,
has_refresh_due, refresh_due,
has_independence_key, independence_key,
has_supersedes, supersedes
```

The `has_*` flags preserve the distinction between an omitted optional key and
an explicit JSON `null`; the value field is null when absent or null. Source
IDs must be the frozen `src-[0-9a-f]{20}` identity, with the identity recomputed
from the complete source row according to the accepted projection contract.
`origin_kind` is `file`, `url`, or `manual`; `content_kind`, authority, and
review status retain the pinned enum values. Pages retain input order and
duplicates. A file source must have a non-null content hash and exactly one
captured-artifact linkage whose path and bytes match that hash. URL/manual
sources have no artifact row; their locator remains subject to the pinned URL
or manual admission rules. The local projection must not implement a second
URL canonicalizer.

`source_artifacts` binds a source ID to the exact captured path, raw SHA-256,
size, and artifact kind required by the accepted source capture contract. It
is a linkage row, not a second source identity. Multiple logical source IDs
may point to the same captured artifact only where the pinned association rules
permit it.

## Closed claim projection

The claim ledger root is projected as:

```text
ledger_meta: {schema, generated_at}
claims: sorted rows
claim_evidence: ordered evidence rows
```

Each `claims` row has exactly:

```text
claim_id, text, risk, assessment, confidence,
location_path, has_location_anchor, location_anchor,
reviewed_at, has_notes, notes, has_supersedes, supersedes
```

Claim IDs use the frozen `clm-[0-9a-f]{20}` identity. Optional presence flags
again preserve omitted versus null. Evidence is not flattened into an
unordered set: `claim_evidence` stores claim ID, ordinal, source ID, domain
relation, and the canonical tagged locator wire. The collector decodes the
wire with the frozen `decode_ledger_evidence`, checks that the outer source and
relation equal the decoded locator, and preserves the original wire for
round-trip identity. `context` maps to the local domain relation `uncertain`;
it must not be silently changed to `supports`.

The raw claim map is the sole source of claim text, assessment, confidence,
risk, location, and review date. Notes and supersession are retained with
presence. Claim IDs, source FKs, evidence locator identity, accepted/high-risk
support, contradiction, freshness, and independence rules are checked against
the complete ledgers, never against a selected row subset.

## Owner and history binding

Every claim, including deprecated claims, is referenced exactly once by one
paper or repository record. The owner supplies the stable subject and location
binding; the collector recomputes the claim ID from that owner and the exact
raw claim text. Duplicate owners, aliases that collide after canonical
normalization, missing owners, and claims referenced by neither record are
refusals. Source IDs in evidence must resolve in the complete source ledger.

Assessment events are collected from the managed review namespace and remain
the history authority. The compiler derives a head from a complete connected
chain, not from a mutable head hint or timestamp maximum. It checks the exact
claim text, evidence fingerprint, review date, predecessor links, and event
identity. Existing v1 event bytes and locator wires are immutable prefixes;
version-aware successors must link the actual stored terminal event. The
prospective `assessment-heads.v2` map is a derived registry over all retained
v1/v2 events, not a second assessment ledger.

## Collector mapping

The current local collector (`src/video_paper_wiki/catalog_collector.py`)
already follows this shape: `_ledgers` emits ledger metadata, source rows,
presence bits, pages, artifact links, claim rows, and ordered decoded evidence;
`_paper` emits owner and claim references; event/code/alignment branches retain
their existing projections. The continuation must extend that collector over
the source-version associations, display decisions/heads, historical
registration snapshots, and Markdown observations named by the source
publication contract. It must use the same retained `_Snapshot` and audited
complete inventory as publication/catalog collection, and must read every
recognized byte through that snapshot.

The collector returns both parsed projection rows and a deterministic semantic
digest over canonical path/hash/size records plus the validated semantic
projection. The digest is an authority input to publication and catalog
freshness. A source-semantic file outside the accepted namespace, an unsafe
filename, a missing historical ledger snapshot, or a path discovered after
collection invalidates the retained state; the base 13-branch projection must
not silently filter it away.

## Mutation profiles

Knowledge publication may replace the complete source/claim ledgers and
derived compiler material only after validating the merged current-plus-
proposed state. Existing source origin/hash identity, claim identity/text
ownership, assessment-event bytes, source associations, display decisions, and
historical snapshots are immutable prefixes. No claim or event disappears;
unsupported removal of the last taxonomy use remains a separate retirement
contract.

Registration is a separate profile. It may add exactly one admitted source row,
write the new source ledger and its content-addressed snapshot, and claim the
previously unclaimed captured raw path/hash. It does not create claims,
associations, display decisions, assessment events, or pages. The old
source-ledger bytes are a write preimage whose expected hash binds the
replacement; they must not be duplicated as a read precondition. The receipt
may read the old ledger only through its existing write descriptor and must
claim only the authorized raw input. If a required historical snapshot is
missing, registration refuses rather than substituting current ledger bytes.

For a knowledge operation, unchanged ledger bytes may remain audited read
preconditions while within the transaction bundle limit. Receipt/head paths
remain publisher-owned and are never claimed as business inputs. The
transaction helper must preserve disjoint read/write paths, expected hashes,
claimed-input policy, and append-last receipt/head ordering.

## Acceptance vectors

The later implementation review must demonstrate at least these vectors:

1. Pinned-valid rows containing an unknown field are rejected by the closed
   projection rather than copied into catalog output.
2. Omitted optional source/claim fields and explicit null produce different
   presence bits and different canonical projection bytes.
3. A file source with absent/null content hash, an artifact hash mismatch, or
   a missing historical registration snapshot refuses.
4. Evidence with a mismatched outer source/relation, noncanonical locator, or
   reordered duplicate occurrence refuses while valid `context` remains
   `uncertain`.
5. A claim with zero owners, two owners, duplicate primary ownership, or an
   unresolved evidence source refuses; deprecated claims remain required in the
   owner/history graph.
6. Replacing a stored v1 event with semantically equivalent regenerated bytes
   before a v2 successor refuses; a successor linked to the exact terminal
   event is accepted.
7. A source-semantic file added between audit and collection, or hidden by the
   base collector's `_kind` filter, is caught by retained-snapshot verification
   and semantic-digest mismatch.
8. Registration with an unrelated ledger write, extra claimed input, or an
   invented capture receipt refuses; knowledge and registration produce distinct
   stable profiles.

The relevant frozen inputs are `docs/ai/contracts/projection-input-v1.md`,
`SOURCE-SEMANTICS-R2.md`, `SOURCE-PUBLICATION-R1.md`, and the accepted staged
capture/transaction-inspect architecture. Implementation must record exact
input hashes and keep local tests, remote CI, and human approval as separate
evidence.
