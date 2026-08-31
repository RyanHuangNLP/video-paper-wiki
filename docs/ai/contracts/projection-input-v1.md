# Canonical projection inputs — review draft 1

Status: NOT FROZEN. Architect design for VPKB-000-projection-contracts at
`5f4c186566c15ab5ee8df10c587e4709d6223f32`; no implementation release. The
runtime comparison contract is separately frozen. This document must be read
with the forthcoming SQLite/export/generation specification. It does not
authorize a filesystem adapter, second ledger or production compiler.

## Authority and supported scope

The supplied canonical input bytes are the only business-fact source. Source
and claim records remain in the two existing upstream ledgers. Page records
own metadata and ordered claim references, assessment events own decisions,
and immutable manifests/artifacts retain provenance. Markdown, frontmatter,
chunk text, BM25, SQLite, index build time and pending drafts are not substitute
facts. SQLite may contain rebuildable copies of these values, never become an
editable authority or fill in a missing value from generated prose.

The v1 profile is a closed project corpus: every supplied claim has exactly one
paper/repo owner, including retired claims. It does not silently discard
unowned legacy claims to make an existing Vault fit. Supporting migration or
a separately selected legacy scope requires an explicit later contract.
Source records may be shared across owners and logical code origins.

A pure validator proves consistency of the supplied inventory, not that a
caller enumerated every file in a Vault, obtained permission, ran upstream
validation, read without symlink/race, or authenticated a receipt. Those are
VPKB-001 responsibilities. No `valid: true` or opaque caller assertion can be
treated as a substitute for bytes, a foreign-key target or a canonical event.

## Structured locator wire profile

The fixed upstream claim ledger allows `evidence.locator` to be a string or
null. Project-owned evidence requires the following non-null tagged string;
its entire content occupies that existing field. No new upstream property or
parallel mutable locator registry is introduced.

Public pure APIs proposed in `video_paper_wiki.projection_inputs`:

- `encode_ledger_locator(locator: object) -> str`;
- `decode_ledger_locator(wire: str) -> dict`;
- `encode_ledger_evidence(evidence: object) -> dict`;
- `decode_ledger_evidence(evidence: object) -> dict`.

The domain locator is the complete existing common.v1 PDF or code locator.
The domain evidence is that flat locator plus exactly one `relation` field,
matching the existing identity API. The wire evidence has exactly
`source_id, relation, locator`; source_id equals the decoded locator source_id.
Copies are independent and no caller value is mutated. No path is opened.

The exact wire is the ASCII prefix `vpwiki-locator-v1:` followed by the
existing integer-only JCS, with no LF, of this closed envelope:

```json
{"schema":"video-paper-wiki.ledger-locator.v1","locator":{},"bbox_rationals":[[41,4],[41,2],[801,8],[163,4]]}
```

Here `locator` is the original complete locator except that PDF `bbox`, when
present, is removed and encoded in the optional `bbox_rationals`. The example
locator object is a placeholder, not a valid empty locator. The envelope has
exactly required `schema,locator` and optional `bbox_rationals`; the latter is
permitted only for a PDF and corresponds to bbox presence. Original `charspan`,
code `symbol` and every other declared locator field are preserved. There is
no relation inside this envelope and no hidden second copy of bbox.

`bbox_rationals` is an exact built-in list of exactly four exact built-in
two-element lists. Each coordinate becomes `[n,d]`: integer n becomes `[n,1]`; a finite float
uses its reduced `as_integer_ratio()`. n and d are exact ints, never bool or
float, within the frozen runtime codec's 2048-bit bound. A valid pair has d>0,
gcd(abs(n),d)=1. For d=1 decode to int. For d>1, d is a power of two and n/d
must be a finite binary64 whose exact `as_integer_ratio()` is the original
pair; do not accept an underflowed, overflowed or rounded rational. Zero is
only `[0,1]`. Integer 1/float 1.0 and either zero sign intentionally share
numeric material; Python coordinate type and zero sign are not preserved.
Fractional coordinates round-trip exactly. These choices do not alter the
existing evidence fingerprint, which deliberately excludes bbox/charspan.
Full-locator round-trip checks are necessary; fingerprint equality alone
cannot prove display-coordinate preservation.

Validate the complete decoded locator against common.v1 with exact built-in
JSON types: all integer fields reject bool/float. PDF bbox alone permits finite
int/float coordinates. Integers obey the 2048-bit runtime limit. Code lines
must satisfy start<=end; PDF charspan, if present, must satisfy
0<=start<=end. These relation checks are a stricter project profile. Existing
public common/identity validation behavior is not changed. Required paths and
hashes retain their existing common.v1 grammars, but match the entire value
with `fullmatch`, not regex `$` (which can accept a trailing LF). Apply that
full-value rule to source_id, repository, commit, all SHA fields and both path
kinds. Additionally source_id must fit the pinned upstream safe-ID subset
`src-[A-Za-z0-9][A-Za-z0-9._-]*`; this is not source-ID recomputation.
A PDF artifact_path must be
under `.raw/derived/`, never an alias for the captured PDF itself.

Wire is an exact built-in scalar string of at most 65,536 UTF-8 bytes including
prefix. Encoding checks this bound too; it must not truncate strings. Apply
the frozen runtime preflight limits before copying/recursing. Decoding rejects
duplicate JSON keys, structural whitespace/noncanonical JCS, nonfinite/floating envelope
numbers, surrogates, unknown fields, malformed ratios, cycles/custom objects
on encode, or a second discriminator/relation. Decode and re-encode must
produce the identical wire string. Neither spelling normalization nor a
legacy free-text fallback is allowed for this tagged project profile.
Whitespace inside a valid ref/symbol or other string value is data and remains
preserved; the structural whitespace rule must not strip or reject it.

The versioned relation mapping is:

| Domain relation | Existing upstream wire relation |
| --- | --- |
| supports | supports |
| contradicts | contradicts |
| uncertain | context |

Apply this mapping only when the evidence uses this validated project locator
profile. It is a transport choice for the project's `uncertain`, not a claim
that arbitrary upstream context evidence has that meaning. Encoding never
sends wire `uncertain`; decoding never passes wire `context` to the identity
API. Bare/null legacy locators and unknown relation values are refusals.
No codec operation changes an assessment or makes a scientific judgment.

Proposed errors use existing ContractError exit 2: `LEDGER_LOCATOR_INVALID`
for malformed wire/domain value/schema/ratio/canonical spelling;
`LEDGER_EVIDENCE_INVALID` for outer evidence shape/relation/source mismatch;
`PROJECTION_LIMIT_EXCEEDED` for resource bounds. Argument/preflight, shape,
then relationships is the validation order. Scalar-safe instance pointers
identify errors; hostile values must not leak recursion/encoding/int-format
exceptions. A field inside the locator retains the locator error code even
when called through the evidence API.
Decoder/parser/value failures from shared helpers are translated into these
codec error codes; resource refusals alone retain PROJECTION_LIMIT_EXCEEDED.

## Whole-snapshot input boundary to freeze

The proposed root is `video-paper-wiki.projection-input.v1` with exactly
`schema,entries`. Each entry has exactly `path,kind,sha256`, in canonical path
order, unique and collision-safe. A separate exact built-in `bytes_map` has
exactly the same keys and supplies immutable bytes matching every entry SHA.
Documents are parsed only from those bytes; a caller cannot supply a different
parsed document next to an honest hash. Raw byte hashes remain distinct from
semantic runtime comparison hashes.

Kinds include source/claim ledger, paper/repo record, assessment event/head,
taxonomy, immutable run/code/alignment manifests and referenced artifact bytes.
The exact path/cardinality/closure table and limits are pending review. There
must be exactly one of each fixed ledger and taxonomy, plus a persisted
assessment-head registry covering exactly the owned claims (an empty registry
for an empty corpus). Do not invent an active alignment version: repo-record
currently has no canonical selector; retain manifest-qualified versions.
The candidate registry path is `wiki/meta/reviews/heads.json`, within the
existing facade and managed review prefix. Do not add an unaudited
`wiki/meta/registries/assessment-heads.json` outside the current managed-prefix
contract. Event files remain `wiki/meta/reviews/<claim_id>/<event_id>.json`.

Cross-object rules to freeze include all source/owner/ref FKs; canonical claim
ID re-computation from owner subject and actual ledger text; no duplicate
ownership or supersedes cycle; taxonomy membership; full tagged locator/source
bindings; current and historical manifest/artifact path/hash closure; active
extraction binding. Raw source identity recomputation and source freshness
remain pinned-upstream adapter checks, not a copied private implementation.

## Historical assessment validation direction

Whole-snapshot history cannot reuse the current prospective helper unchanged:
it compares every event fingerprint with the current evidence. Historical
events before a legitimate invalidation must retain their historical value.
Reuse the existing event schema and ID algorithm, then validate the whole
graph separately, without changing the old per-proposal API silently.

For each claim require one genesis, one connected acyclic nonforking chain,
no dangling/cross-claim predecessor and exactly one declared terminal head.
All events bind the unchanged canonical ledger text. Parent to_assessment
equals child from_assessment. A human transition preserves the parent's
evidence fingerprint and changes assessment; system invalidation changes
fingerprint and moves to provisional, including provisional->provisional.
Only the head fingerprint equals current decoded ledger evidence. Ledger
assessment is head.to_assessment; reviewed_at is the human head's canonical
UTC date, or null for system genesis/invalidation. No wall-clock inference.

The no-op refusal follows the active development plan's section 5.4 rule 3;
the existing per-event schema is intentionally broader and cannot alone
establish whole-chain validity. This closed snapshot profile refuses historical
human same-state transitions. It does not rewrite such immutable legacy events
or claim they fit this supported corpus; any compatibility/migration policy
needs separate review. Existing per-event/prospective API behavior is unchanged.

The snapshot can prove chain state, not that invalidation and human review
were published in separate approved transactions. Core replacement review
co-publication and receipt-backed timing remain VPKB-001 prospective/integrity
checks. The snapshot must not label this limitation full workflow acceptance.

## Review/acceptance still required

- Independently review the codec, final inventory/DDL/generation linkage and
  unsupported legacy boundary before implementation release.
- Use real pinned public CLI controls for supports/context success and wire
  uncertain refusal; prove exact tagged string preservation without extensions.
  Keep fixture extraction metadata distinct from real coordinate verification.
- Preserve all current identity goldens; add complete wire bytes/hash vectors,
  canonical-reencoding adversaries, fractional/optional-field round trips,
  duplicate/cycle/resource failures and unknown-relation rejection.
- Snapshot fixtures must include historical invalidation followed by review,
  missing/replaced raw bytes, absent/unknown/duplicate inputs, ref/owner/hash
  failures, complete ordering/duplicate semantics and no Markdown-derived facts.
- No acceptance of this draft, parent packet, VPKB-000 or human gate is implied.
