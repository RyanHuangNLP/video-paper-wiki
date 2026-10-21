# Complete assessment history — frozen revision 1

Status: FROZEN by Architect, 2026-09-01, after independent Builder and Steward
review. Released bounded pure slice of VPKB-000-projection-contracts, based on
accepted locator commit `3e2bebb1d50928a7af95e07b4868bdbe8113cd0b`.
This is a whole-history application profile, not a new persisted event schema,
ledger, review command, approval mechanism or mutable assessment-head registry.
The existing prospective validator and identity/event formats remain unchanged.

## Purpose and authority

Validate the supplied complete assessment graph for an explicitly bound set of
claims and derive its heads. Current evidence may differ from evidence at an
older event after a legitimate invalidation; only the terminal event binds the
current evidence fingerprint. Every historical event still binds the current
canonical claim text, because changing identity text requires a different claim.

Inputs are transient bindings assembled from canonical owner records and claim
ledgers, plus complete immutable event documents. This slice checks those values,
not where they came from. It cannot establish complete Vault enumeration, owner
record existence, retained artifact/source bytes, event filenames, raw byte hashes,
receipt authentication, human identity/authorization, rollback resistance, or
transaction co-publication. No supplied boolean or actor string attests approval.
The future canonical-input adapter must enforce those separate bindings.

Both active and retired claims must be supplied by that adapter; this API has no
lifecycle filter and never discards a binding or event. A caller omitting both a
claim and its history is outside what a pure supplied-value check can discover.
A removed tail plus a matching older ledger similarly needs an external integrity
check. Core replacement/deprecation co-publication and invalidation followed by a
separate human transaction remain future prospective/publication checks.

## Public API and data shapes

One function in `video_paper_wiki.assessment_history`:

```python
def derive_assessment_heads(*, claims: object, events: object) -> dict[str, str]: ...
```

Both arguments must be exact built-in lists. No optional parameter, designated
head, fallback, clock, callback, filesystem path or implicit validation context.
The result is a newly allocated dict from each claim ID to its unique head event
ID, inserted in ascending ASCII claim-ID order. It has no extra fields. Strings
are immutable; no mutable input container is returned or retained. Nothing is
written. Empty claims with empty events returns `{}`; a nonempty side must satisfy
all coverage rules below. Claim/event input order does not affect valid results.

Each claim binding is an exact built-in dict with exactly these required keys:

| Field | Supported value |
| --- | --- |
| claim_id | Complete `clm-[0-9a-f]{20}` string |
| stable_subject_id | Exact canonical paper or repo stable subject accepted by the existing identity grammar; concept subjects are outside this owner profile |
| canonical_claim_text | Nonempty scalar string, at most 65536 UTF-8 bytes; exact persisted text, not a normalized or reworded substitute |
| evidence | Exact built-in list of complete flat domain evidence objects accepted by frozen ledger-locator revision 1 |
| assessment | `provisional`, `accepted`, `contested`, `unsupported` or `deprecated` |
| reviewed_at | Required explicit null or a real Gregorian `YYYY-MM-DD` date in years 0001..9999 |

There is no `schema` in this transient binding, no lifecycle or supplied fingerprint
field, and no claim metadata default. The adapter must decode actual tagged ledger
evidence using the accepted codec before assembling this object; passing existing
free-text wire as if it were decoded evidence must fail. This API revalidates full
evidence shape through the codec; it must not assume callers already did so.
The extra text-size limit is this bounded application profile, not a change to the
old claim identity algorithm or a claim that longer legacy text has no identity.

Each event is the full existing `video-paper-wiki.assessment-event.v1` document,
including all required keys and no extensions. The existing event schema and
transition matrix apply. Require exact built-in containers/scalars and complete
matching of every patterned ID/hash/timestamp; `$` matching a trailing newline
is not sufficient. Gate-decision objects are never assessment events.
`decided_by` and `reason` retain the schema's nonempty-string rule; they are opaque
values and cannot authenticate a human. Do not trim or normalize them.

`decided_at` is precisely real Gregorian `YYYY-MM-DDTHH:MM:SS[.f{1,9}]Z`, year
0001..9999, hour 00..23 and minute/second 00..59. No offset, leap-second 60,
trailing newline, lower-case z or auto-normalization. Fractional precision and
trailing fractional zeroes are preserved and participate in event identity.
Do not order events by time or require strictly increasing timestamps: the
predecessor graph is the ordering authority. Equal or decreasing valid timestamps
do not override the graph. A human head's date is its first ten characters after
validation, never a local-time conversion or wall-clock date.

## Resource and isolation boundary

Before schema validation, normalization, copying, sorting or identity hashing,
preflight the virtual tree `{"claims": claims, "events": events}` using the frozen
projection-runtime limits and type rules. The virtual root and its two keys count:
maximum container depth 64, one million node/key occurrences, 64 MiB encoded
scalar/ratio budget and 2048-bit integer magnitude. Acyclic aliases are allowed
and charged at every occurrence; ancestor cycles, custom classes/subclasses,
non-string keys, non-finite numbers and surrogate strings are invalid. No coercion
from tuple, Mapping, bytes, Decimal, numpy or stringified numbers. Finite floats
are allowed only where full evidence permits them; bool never substitutes for
integer coordinates/lines/span. The text UTF-8 cap is checked before normalizing
or hashing that text, with a character-count bound before encoding it.
Each evidence item must also meet the existing 65536-byte locator wire cap.

Reuse the existing preflight and immutable packaged schema resources; warming the
schema cache is allowed before no-I/O probes. Do not import upstream scripts,
load Docling, resolve user paths, access a Vault, consult a clock/environment,
spawn a process, use the network or write persistent state. The input graph is
not a command. No new schema-resource registration or dependency is needed.

## Claim binding and identity

Each claim ID has exactly one binding. Duplicate bindings are never deduplicated.
For duplicate IDs, compare the existing identity material
`(stable_subject_id, NFKC-and-whitespace-collapsed canonical_claim_text)`:
different material is `CLAIM_ID_COLLISION` with exit 75; equal material is
`PRIMARY_OWNER_INVALID` with exit 2, including byte-identical duplicate entries.
Check this after all claim shapes, before rejecting an individual stated claim
ID for hash mismatch, so the supplied collision is not silently downgraded.
This detects conflicting supplied bindings, not arbitrary unknown hash collisions.

Recompute every claim ID using the unchanged existing identity implementation.
Preserve the exact input text; do not require it to already equal normalized text.
Claim identity normalization is distinct from an event's text hash: for every
event, `claim_text_sha256` equals SHA-256 of exact UTF-8 canonical_claim_text
bytes. A canonically equivalent spelling can share claim identity while changing
that raw text hash; old events then cannot silently bind a different stored text.

Compute current evidence fingerprint with the unchanged existing identity helper,
after complete codec validation of all flat items. Order is irrelevant to that
fingerprint but multiplicity is preserved; do not turn evidence into a set.
Existing excluded display fields remain excluded (PDF bbox/charspan and code
symbol); adding them to the fingerprint would change frozen identity semantics.
Full locator validation remains necessary even for fields excluded from identity.
Empty evidence is supported and has the existing empty-list fingerprint.

## Complete graph rules

Validate all events against the existing schema and recompute each event ID with
the unchanged integer-only JCS algorithm excluding only `event_id`. Do not use a
runtime comparison digest or remove timestamps/reason/actor. Repeated event IDs
are errors even for identical event objects. Every event belongs to a supplied
claim; every supplied claim has at least one event. Missing or unknown claims
are errors, not empty chains.

For each claim, require exactly one genesis, no dangling or cross-claim parent,
no fork, no cycle, one connected chain and exactly one terminal head. Genesis
has no parent. Every other event has one existing same-claim parent. Each event
has at most one child. Traverse the chain and prove that every event in the claim's
supplied set was visited; a unique terminal plus a separate cyclic component is
not sufficient. Use an iterative traversal rather than Python recursion over a
potentially long valid chain. Event arrays and IDs are not chronological sorting
keys. Derive heads only after validation; never use the ledger's asserted state
or a caller-selected head to repair an invalid graph.

For every child, parent.to_assessment equals child.from_assessment. In addition
to the existing event schema's transition matrix:

- Genesis is system `null -> provisional`. Its fingerprint may be historical.
- Human assessment preserves the parent's fingerprint and changes assessment;
  a human same-state transition is refused. Human `to_assessment` is one of
  accepted/contested/unsupported/deprecated, never provisional.
- System evidence_invalidation changes the parent's fingerprint and transitions
  to provisional. `provisional -> provisional` is allowed only here with a changed
  fingerprint. A fabricated invalidation with unchanged fingerprint is refused.

Every event binds the same exact canonical text hash. Only the head must equal
the current evidence fingerprint; do not compare all historical fingerprints to
current evidence. A later fingerprint may equal one seen farther back in history:
returning to prior evidence is allowed when it differs from the immediate parent
and follows the same invalidation/review rules.

For every claim binding, assessment equals head.to_assessment. reviewed_at equals
the head's UTC date if its actor_kind is human, otherwise null for system genesis
or invalidation. Do not repair ledger fields, silently convert a date, or create
an event. A retired claim can have any graph-valid assessment; lifecycle alone
must not synthesize deprecated. No heuristic about evidence count automatically
accepts/contests a claim: evidence scientific meaning and upstream risk/source
policies are separate checks.

This closed application profile deliberately rejects historical human no-op events
allowed by the broader per-event schema. It does not rewrite legacy events or
silently broaden their compatibility. Existing `validate_document` and
`validate_prospective` APIs and their tests keep their current behavior.

## Errors and deterministic failure boundaries

All failures are `ContractError`. Resource excess preserves
`PROJECTION_LIMIT_EXCEEDED`; all ordinary failures exit 2 except the existing
claim identity collision exit 75. The virtual tree preflight runs first and maps
non-resource value errors to `SCHEMA_INVALID`. Later errors use:

| Failure | Code |
| --- | --- |
| Binding/event shapes, types, enum/grammar/date failure, unsupported subject | SCHEMA_INVALID |
| Full evidence invalid under the frozen locator codec | Preserve LEDGER_LOCATOR_INVALID or LEDGER_EVIDENCE_INVALID |
| Claim ID hash mismatch | CLAIM_ID_MISMATCH |
| Duplicate equal-material claim binding | PRIMARY_OWNER_INVALID |
| Duplicate different-material claim binding | CLAIM_ID_COLLISION (75) |
| Event ID hash mismatch | EVENT_ID_MISMATCH |
| Event exact text hash mismatch | CROSS_OBJECT_IDENTITY_MISMATCH |
| Missing/unknown claim history, duplicate event, malformed graph, state-edge/no-op transition | ASSESSMENT_CHAIN_INVALID |
| Human changes fingerprint, invalidation retains fingerprint, head/current fingerprint mismatch | EVIDENCE_FINGERPRINT_MISMATCH |
| Ledger assessment or reviewed_at differs from derived head | CROSS_OBJECT_IDENTITY_MISMATCH |

Errors include a safe JSON `instance_pointer` into the virtual input tree, with
RFC6901 escaping. For a relationship failure point at the implicated child field
or claim binding; a missing chain points to that binding's claim_id. Prepend
`/claims/<i>/evidence/<j>` to inner codec pointers without changing their meaning.
Do not include claim text, reason, arbitrary object repr or whole documents in
messages/details. Unknown keys can be represented by safely escaped pointers.
Input order may determine which of several unrelated failures is reported; no
cross-permutation error priority is promised. Resource preflight and the explicit
claim-collision precedence above are mandatory. No untyped RecursionError,
UnicodeError or serialization traceback may escape for supported-size bad data.

## Required verification before release/acceptance

Both Builder and Steward must independently review this draft before Architect
freezes it. Proposed implementation ownership after release: one new production
module, one test module and a narrow fixture family; no edits to existing identity,
prospective/schema dispatch, source schemas, codec/runtime, dependencies or CLI.

Required fixtures include independently computed complete event IDs, raw text
hashes and evidence fingerprints; multi-claim paper/repo chains with genesis,
human assessment, invalidation and later review; historical fingerprints distinct
from current; empty evidence; valid equal/decreasing/fractional UTC times; all
valid transition edges; evidence permutation versus duplicate and relation/content
changes; optional display changes; all bad coverage/graph/identity/state/date/type
cases; near-limit/over-limit data; long chains, aliases and no mutation/I/O.

Adversarial cycles cannot reasonably be assigned genuine self-consistent truncated
hash IDs without solving hash fixed points. End-to-end malformed cyclic objects
must be refused, but may fail event identity first. Separately test the actual
graph routine with explicitly synthetic IDs or a narrowly isolated identity stub
and label that evidence honestly; it is not a valid-hash persisted-cycle fixture.
Use the same distinction for an injected claim hash collision. Do not bypass
identity checks in production or weaken a golden to reach a later failure.

Keep all prior identity/prospective tests unchanged. Run targeted fixtures, full
Python 3.12/3.13 suites and an isolated installed-wheel smoke, then bind fresh CI
to the resulting commit. Local synthetic values prove this API's consistency
rules, not real human review, complete history retention or publication integrity.
The entire input/SQLite/generation packet and VPKB-000 remain open.
