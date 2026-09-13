# Ledger locator wire contract v1

Revision: 1. Status: frozen. Architect: Codex, `gpt-5.6-sol / ultra`.
Builder and Repo Steward independently reviewed the complete specification;
Architect released this bounded codec on 2026-09-01.
Part of VPKB-000-projection-contracts; baseline
`208c206801214bb8f6e2f58f995ad7755ce87332`.

This isolates the locator wire section previously reviewed in the unfinished
projection-input draft. Its implementation release does not release the whole
canonical inventory, assessment graph, SQLite, generation or production adapter.
The existing common schema and identity/JCS behavior remain unchanged.

## Public API and authority

Module: `video_paper_wiki.ledger_locator`.

```python
encode_ledger_locator(locator: object) -> str
decode_ledger_locator(wire: str) -> dict
encode_ledger_evidence(evidence: object) -> dict
decode_ledger_evidence(evidence: object) -> dict
```

All four APIs validate their supplied value. They are pure supplied-data
operations: no caller paths are opened, enumerated or executed; no filesystem,
network, process, database or Vault operations. Existing immutable packaged
schema loading is the sole I/O exception; isolation checks warm that registry
first. No upstream private import, new ledger or model is introduced.

The domain locator is a complete common.v1 PDF or code locator. Domain evidence
is that flat locator plus exactly one `relation` field, as in the identity API.
The wire evidence is a closed object with exactly `source_id,relation,locator`.
The locator field is the tagged string below. Outer source_id must equal the
decoded locator source_id. Return fresh independent built-in dictionaries/lists;
do not mutate inputs or preserve mutable aliases. Strings and numeric immutable
values may be shared. Dictionary insertion order is not business material.

The codec validates spelling/shape/relationships, not source-ID authenticity,
captured bytes, PDF ref/page/text correctness, code snippet contents, complete
artifact inventory, actual upstream execution, receipt approval or assessment.
Existing common/identity APIs must not silently adopt this stricter profile.

## Exact wire and numeric coordinates

The wire is the ASCII prefix `vpwiki-locator-v1:` followed immediately by
existing integer-only RFC8785 JCS UTF-8, without LF, of a closed object with
required `schema,locator` and optional `bbox_rationals`:

```json
{"schema":"video-paper-wiki.ledger-locator.v1","locator":{},"bbox_rationals":[[41,4],[41,2],[801,8],[163,4]]}
```

The empty locator in this structural example is not valid input. Actual locator
is the complete original common locator, except PDF bbox is removed when present.
Only that case adds bbox_rationals. Preserve charspan, code symbol and every
other declared field exactly. Neither relation nor a second bbox may occur in
the envelope. Code locators never allow bbox_rationals.

bbox_rationals is an exact built-in list of four exact built-in two-element
lists. Each pair is `[n,d]`: an integer coordinate becomes `[n,1]`; a finite
float uses its reduced `as_integer_ratio()`. Both members are exact ints,
never bool or float, each at most 2048 magnitude bits. Require d>0 and
gcd(abs(n),d)=1. Zero has only `[0,1]`. For d=1, decode to int. For d>1 require
d to be a power of two and n/d to represent a finite binary64 whose exact
`as_integer_ratio()` is the original pair. Reject underflow, overflow and
rounding; do not approximate a rational. Negative finite bbox values remain
allowed by common.v1; do not infer a coordinate system or impose bbox ordering.

Integer 1 and float 1.0, and positive/negative zero, intentionally share wire
material. Fractional finite floats round-trip exactly. The codec does not
preserve integral-float type or zero sign. This numeric equality does not
broaden existing identity JCS or change the evidence fingerprint, which excludes
bbox/charspan. Tests must compare the entire locator; a matching evidence
fingerprint alone cannot show that optional display coordinates survived.

## Closed domain validation

Use common.v1 pdf_locator/code_locator shape with exact built-in JSON values:
dict, list, scalar str, int, finite float, bool and null only as their fields
allow. All integer fields reject bool and float. PDF bbox alone permits finite
int/float coordinates. Reject unsupported subclasses, custom objects, tuples,
non-string keys, surrogates and ancestor cycles before copying/recursive schema
validation. Shared acyclic references are allowed but count per occurrence.

Required/optional fields, enum/minimum/maximum and nonempty rules are exactly
common.v1 plus these explicit profile restrictions:

- Source ID must match `src-[A-Za-z0-9][A-Za-z0-9._-]*` in full. This is the
  pinned upstream safe-ID subset, not recomputation of an upstream identity.
- All common patterned strings match the complete value: source_id, repository,
  commit, every SHA and both path kinds. Use fullmatch semantics, not regex `$`
  accepting a trailing LF. Keep the common portable grammar and original case;
  do not normalize repository/path/ref/symbol spelling or strip whitespace.
- PDF artifact_path is a common derived path under `.raw/derived/`, never
  `.raw/captured/`. Page is an exact integer 1..300. Optional charspan contains
  exactly two exact integers with 0<=start<=end. Optional bbox is exactly four
  finite coordinates, never null.
- Code lines contains exactly start/end, each exact integer >=1 and start<=end.
  Commit is exactly 40 lowercase hex; hashes are exactly 64 lowercase hex.
  Optional symbol is nonempty and not null. Whitespace inside an otherwise
  valid free-text ref/symbol is data; do not treat it as structural whitespace.

The entire domain must obey projection-runtime-v1 revision 1 preflight budgets:
container depth 64, original values plus object keys 1,000,000 occurrences,
2048-bit integers, and 64 MiB scalar token/ratio material. The existing runtime
helpers may be reused internally without changing their public semantics.
An empty/invalid locator is not an invitation to supply defaults.

## Strict decoding and size

A wire is an exact built-in scalar string, at most 65,536 UTF-8 bytes including
prefix. Both encode and decode enforce this bound and never truncate. On decode,
check character length before allocating UTF-8 bytes, then validate scalar UTF-8
and byte length before parsing. Encoding runs domain preflight before copying.
No resource setting is caller-controlled in this API.

Decode the payload with duplicate-key rejection and the frozen runtime parser's
pre-allocation depth/occurrence/integer guards. The envelope must contain only
the declared fields and exact built-in integers in every numeric position.
Reject floating/exponent numeric spellings, NaN/Infinity, BOM, bad UTF-8 scalar
values, unknown fields, wrong discriminator, missing prefix, legacy free text
and null. Whitespace inside string values is retained.

Re-encode the validated result and require the identical whole wire. Thus
structural whitespace, LF, reordered keys, alternate escapes, noncanonical
integer spelling such as -0, and unreduced ratios are refused. Do not normalize
them into an accepted wire. Successful decode followed by encode is byte exact.

## Evidence relation transport

| Domain relation | Existing upstream wire relation |
| --- | --- |
| supports | supports |
| contradicts | contradicts |
| uncertain | context |

This mapping applies only to evidence using the validated tagged locator.
It does not assign project meaning to arbitrary upstream context evidence.
Encoding never emits wire uncertain; decoding never emits domain context.
Unknown relations, bare/null locators, extra outer fields and mismatched
source IDs are refused. No operation changes review state or judges a claim.

Encode evidence validates the flat object's relation, then its locator fields.
Decode evidence validates outer keys/types/relation, then decodes locator, then
checks source-ID equality. The source-ID spelling within the locator follows
the locator profile above; outer source_id is an exact scalar string matching
the same safe-ID subset. Inputs and outputs retain no mutable alias.

## Errors and order

Use ContractError, exit 2. Codes:

- `LEDGER_LOCATOR_INVALID`: bad locator domain, wire, envelope, ratio, schema
  or canonical spelling.
- `LEDGER_EVIDENCE_INVALID`: bad outer evidence shape/relation/source-ID field
  or outer/inner source mismatch. Missing/unknown locator fields within a flat
  encode-evidence object remain locator errors after relation validation.
- `PROJECTION_LIMIT_EXCEEDED`: original-tree or wire size/depth/count/integer
  resource refusals; retain this code when sharing runtime helpers.

Order: argument/resource/value preflight before copying; structural shape and
field validation; relationships and numeric exactness; canonical re-encoding.
For evidence APIs run preflight on the entire supplied object first, before
the outer/locator phases above. Other shared parser/value/schema/JCS failures
are translated into the appropriate locator/evidence error, never leaked as
raw exceptions. Diagnostics must not invoke custom-object formatting or leak
RecursionError, UnicodeError, OverflowError or integer-formatting ValueError.

Include scalar-safe RFC6901 `details.instance_pointer`. It is relative to the
logical value being validated: domain locator on encode, decoded envelope on
decode, or outer evidence for outer errors. Forwarded locator errors retain
their original pointer without inventing character offsets within a string.
Raw wire/canonical-spelling errors use the empty pointer. Error messages are
descriptive, not a frozen byte protocol; a multiple-fault input has no promised
ordering among independent failures within the same validation phase.

## Required verification and release boundaries

- Independent exact wire/SHA vectors for PDF/code, optional bbox/charspan/symbol,
  fractional and signed-zero/integral-float cases, whitespace/Unicode free text,
  and all three relations. Preserve all existing identity goldens.
- Round trips/copy isolation, unknown/missing fields and relation/source mismatch,
  noncanonical JSON/duplicate/escape/ratio adversaries, strict types, integer
  limits, boundary wire length, deep/cyclic/custom inputs and safe typed errors.
- Exact rational representability cases including smallest binary64 subnormal,
  largest finite float, rounded/underflow/overflow ratios, and valid large ints.
- Pure supplied-data isolation after registry warmup. No new production CLI,
  input inventory, source-ID algorithm, parser model, database or Vault adapter.
- Replay the pinned public-CLI supports/context success and wire-uncertain
  refusal with a disposable fixture, proving unchanged tagged locator transport.
  Its synthetic artifacts do not establish genuine PDF coordinates or closure.
- Independent review, full supported-Python suites, installed-wheel smoke and
  candidate-bound CI before accepting the implementation slice. Acceptance
  does not close the complete projection packet, VPKB-000, or any human gate.
