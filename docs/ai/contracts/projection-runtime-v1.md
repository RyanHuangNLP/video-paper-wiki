# Projection runtime comparison — frozen revision 1

Status: FROZEN by Architect after independent Builder and Steward review. Part of
VPKB-000-projection-contracts, baseline
`5f4c186566c15ab5ee8df10c587e4709d6223f32`. This document covers the numeric
comparison substrate and fixed upstream runtime objects. The same packet must
also freeze the canonical input/locator, SQLite and generation contracts; this
document alone cannot complete it. Existing identity/JCS/receipt contracts and
upstream objects remain unchanged. No production index writer is authorized.

## Authority and APIs

All functions are pure and accept supplied Python values or bytes. They never
read a caller-supplied path, enumerate a Vault, launch an upstream command,
perform network I/O, render a page or write a database. Reading immutable
packaged schema resources is allowed. Upstream execution belongs only in the
explicit disposable public-CLI compatibility tests and later VPKB-001 adapters.

Public functions in `video_paper_wiki.projection_runtime`:

- `parse_projection_json(payload: bytes) -> object`: strict JSON parsing below.
- `projection_value_bytes(value: object, *, profile: str) -> bytes`: encode the
  complete supplied value in the versioned comparison domain below. It does
  not validate a business schema or remove volatile fields. Profile is an exact
  built-in string matching `[a-z][a-z0-9._-]{0,127}`; no caller normalization.
- `projection_value_sha256(value, *, profile) -> str`: lowercase SHA-256 of
  those exact bytes, without a newline or other prefix.
- `validate_runtime_record(kind, document) -> dict`: kind is exactly `chunk`
  or `bm25`; validate all fields/relations below and return an independent deep
  copy. It does not authenticate the source page or attest execution.
- `runtime_projection_bytes(kind, document) -> bytes`: validate first, remove
  exactly the allowed root timestamp on the independent copy, then call the
  value codec using profile `claude-obsidian.chunk.v1` or
  `claude-obsidian.bm25.v2`. The whole remaining document is material.
- `runtime_projection_sha256(kind, document) -> str`: SHA-256 of those bytes.
- `runtime_projection_equal(kind, left, right) -> bool`: validate both values;
  equality of their canonical comparison bytes. Invalid input raises, never
  returns true/false as though it were a valid unequal projection.
- `markdown_projection_equal(left: bytes, right: bytes) -> bool`: exact built-in
  bytes only; compare every byte. No decoding, normalization, newline conversion,
  frontmatter parsing or volatile exclusion. Empty bytes are valid. No size
  limit is imposed by this byte comparison; JSON limits do not apply to it.

Errors use existing `ContractError`, exit code 2, with scalar-safe details
including `instance_pointer` where applicable. Codes:
`PROJECTION_JSON_INVALID` (raw JSON syntax/encoding/duplicate keys/nonfinite
number), `PROJECTION_VALUE_INVALID` (non-JSON Python value/cycle/surrogate or
invalid profile/kind/bytes argument), `PROJECTION_LIMIT_EXCEEDED` (limits below),
`RUNTIME_PROFILE_INVALID` (shape/type/version/path/timestamp violation), and
`RUNTIME_CONTENT_MISMATCH` (hash/count/identity/content relationships).
Do not leak TypeError, OverflowError, UnicodeError, RecursionError or errors
caused by formatting an adversarial integer. Other existing APIs keep their
error and return semantics.

Validation order is argument types/allowed kind or profile, complete value
preflight and budgets, closed profile shape/field constraints, then content
relationships. Within one phase use a deterministic traversal; multiple errors
in that phase need not have a separately ranked precedence. Runtime preflight
runs before schema recursion or deepcopy and before removal of any timestamp.
Equality validates left then right before comparing; neither object identity
nor an early unequal field may bypass validation of an otherwise valid side.
The central `validate_document(..., expected_schema=...)` entry for these two
new profiles dispatches to this same validation and returns its independent
copy, with these same error codes/order. This does not change old schemas.

## Strict JSON and traversal

`parse_projection_json` accepts only built-in bytes, at most 64 MiB. Decode
strict UTF-8, reject BOM and duplicate object keys at every depth (including
different escape spellings of the same decoded key). Use JSON's standard
integer parsing and binary64 parsing for decimal/exponent tokens; reject
NaN/Infinity extensions and any float overflow to infinity. Trailing JSON
whitespace is allowed, trailing non-whitespace is not. Run the value preflight
after parsing. Decoder recursion, oversized integer conversion and resource
budget refusals use PROJECTION_LIMIT_EXCEEDED. Syntax, malformed UTF-8, BOM,
duplicate keys, nonfinite tokens and floating overflow use PROJECTION_JSON_INVALID.
A parsed lone surrogate uses PROJECTION_VALUE_INVALID during value preflight.

The comparison is of parsed binary64 values, not exact decimal tokens or raw
JSON bytes. Binary64 rounding, including underflow to zero, follows Python's
finite float parser. The raw input SHA remains separate wherever exact source
bytes matter; this codec may not replace a raw input/content/receipt hash.

Value preflight permits only exact built-in dict/list/str/int/float/bool and
None. Dict keys must be exact strings; strings contain only Unicode scalar
values. Floats must be finite. Reject subclasses/custom Mapping/Sequence,
tuples, Decimal/Fraction, bytes in a value tree, sets, non-string keys and
ancestor cycles. Shared acyclic subobjects are allowed and encoded separately
at each occurrence. No lossy NFC/NFKC/case/whitespace cleanup occurs.

Application resource limits (not assertions about upstream limits): container
depth at most 64, counting a root dict/list as depth 1; at most 1,000,000 tree
occurrences, counting each scalar/container and each object key once. Depth and
occurrences count the original input tree, not the generated tagged tree; shared
acyclic objects count again at each use. Integer
magnitude at most 2048 bits. All finite binary64 values fit the corresponding
ratio integer bound. Aggregate scalar encoding budget is 64 MiB: sum the UTF-8
lengths of JCS-escaped string/key tokens and decimal integer tokens that occur
in the encoded tree, excluding fixed tags, structural punctuation and the
wrapper/profile. Charge each original string/key's complete escaped token,
including quotes, and both decimal ratio tokens for every original number
(including an integer's denominator 1). Null/bool add no scalar-budget bytes.
Examples: input `1` costs 2 bytes; `"x"` costs 3; `{"a":1}` costs 5. Timestamp
strings are counted in the full runtime object before their later exclusion.
Check these budgets before building an unbounded encoded tree. Reject excessive
input instead of truncating, skipping entries or returning a partial digest.
The depth bound includes parsed JSON; decoder recursion failures are also typed.

## Exact number and type encoding

The value codec emits the existing integer-only JCS of this wrapper, no LF:

`{"codec":"vpwiki.runtime-tree.v1","profile":profile,"tree":T(value)}`

Every node is tagged. This prevents a user array/object imitating a numeric
representation from colliding with an actual number.

| Input | T(input) |
| --- | --- |
| null | `["null"]` |
| boolean | `["bool", value]` |
| string | `["string", value]` |
| integer n | `["number", n, 1]` |
| finite binary64 | `["number", numerator, denominator]` from exact reduced `as_integer_ratio()` |
| list | `["array", [T(item), ...]]`, preserving all order and duplicates |
| object | `["object", [[key,T(value)], ...]]`, sorting keys by UTF-16BE bytes |

No Unicode normalization. Both zero signs encode as 0/1. Integer 1 and float
1.0 have equal numeric material, but true and 1 do not. Integer-only schema
positions must reject 1.0 before this numeric equivalence can apply. In
particular, JSON Schema's mathematical interpretation of `integer` is not
sufficient to implement strict type checks in this contract.

There is no tolerance, decimal rounding or `math.isclose` in comparison. For
example 0.1 is exactly 3602879701896397/36028797018963968 and a one-ULP change
must change material. All finite values including the smallest subnormal and
largest binary64 are supported. Existing `video_paper_wiki.jcs` still rejects
floats; no existing identity/event/receipt golden changes.

## Fixed upstream profiles

These are **closed project validation profiles**, compatible with the pinned
emitter on the project's supported inputs, not a claim to accept every legacy
object the upstream validator permits. In particular c/l addresses use the
ASCII allocator subset; upstream's frontmatter regex uses the broader Unicode
`\d`. The upstream commit is
`9f8c1199047eac2c3828496279fbb7ba9540b90b`, version 2.1.1.
Objects retain exactly their upstream fields; they gain no schema discriminator,
generation, evidence-unit or extension fields. Packaged schemas may be named
`video-paper-wiki.upstream-chunk-profile.v1.schema.json` and
`video-paper-wiki.upstream-bm25-profile.v1.schema.json`, with those titles and
normal project $ids. Validation via the central registry uses explicit
`expected_schema`; callers must not insert a `schema` field into an upstream
record. Central validation must enforce the same profile checks.

Both profiles reject extra fields at every fixed object position. Dynamic map
keys are data, never interpreted as schema property names. All declared integer
positions are exact ints, not bool or float. All strings are Unicode scalars.
Only the complete profiles below authorize timestamp removal.

Common runtime lexical paths: nonempty relative slash-separated strings; no
leading slash, backslash, drive prefix, empty/dot/dot-dot component, C0 control,
DEL or surrogate. Keep original spelling; do not apply case/NFC normalization.
Runtime comparison performs no filesystem/symlink checks. Hash strings match
the entire `sha256:[0-9a-f]{64}`. Timestamps are real UTC calendar datetimes
matching the entire `YYYY-MM-DDTHH:MM:SSZ`, no fractional seconds/offset/leap
second. Invalid timestamps must be rejected before removing them.

### Chunk profile

Exactly these required fields:
`schema_version, page_path, page_address, chunk_index, raw_text,
contextualized_text, prefix, prefix_source, char_count, body_hash,
page_body_hash, created_at`.

- schema_version is integer 1. page_path is a common runtime lexical path
  starting `wiki/` and ending `.md`, with a component after `wiki`.
- page_address matches `[cl]-[0-9]{6}` or `syn-[0-9a-f]{64}` in full. Synthetic
  address must equal `syn-` plus SHA-256 of exact page_path UTF-8 bytes.
- chunk_index is integer 0..2147483647. raw_text is 1..4000 Unicode code points;
  char_count is its exact code-point length. prefix is 0..1000 code points and
  equals its stripped form. contextualized_text equals raw_text for empty
  prefix, otherwise exactly `prefix + "\n\n" + raw_text`.
- prefix_source is `synthetic`, `anthropic-api` or `claude-cli` (actual emitter
  values). Production project fixtures force synthetic with `--no-llm`; merely
  validating another recorded value does not authorize egress or nondeterminism.
- body_hash equals `sha256:` plus SHA-256 of exact raw_text UTF-8. page_body_hash
  has the hash shape; verifying the full source page is a separate byte-binding
  responsibility, never inferred from the record alone.
- created_at has the common timestamp format. **Only `/created_at` at this
  chunk root is excluded.** All text, hashes, prefix and identity remain material.

### BM25 profile

Exactly required root fields:
`schema_version, params, doc_count, avg_dl, updated_at, vocab, docs`.
schema_version is integer 2. params has exactly required `k1,b`; finite numbers
(ints or floats, not bool), `0 < k1 <= 100` and `0 <= b <= 1` as in the pinned
validator. The current emitter produces 1.5 and 0.75, but comparison retains
other valid values and detects drift rather than dropping or rounding them.

doc_count is integer 0..2147483647, equals len(docs). avg_dl is a finite number
in [0,2147483647]. updated_at is a common timestamp. **Only `/updated_at` at this
root is excluded.** A similarly named vocabulary term is ordinary material.

docs is a dynamic map from chunk_id to objects containing exactly required
`path,dl,body_hash,page_body_hash` (no missing/null legacy hashes). chunk_id is
`<page_address>:<chunk_index>` with the same address grammar and canonical
nonnegative decimal index (no extra leading zeros); index <=2147483647. path is
exactly `.vault-meta/chunks/<page_address>/chunk-<index formatted to minimum
three decimal digits>.json`. dl is integer 0..2147483647; both hashes have the
common hash shape. Paths must be unique. No lookup into page/chunk files occurs.

avg_dl must equal the actual binary64 value of `sum(dl) / doc_count`, or 0 for
an empty index. This is a stricter, explicitly chosen emitted-value integrity
check than the upstream validator's 1e-12 tolerance. Do not carry its tolerance
into canonical comparison. Distinct valid documents with changed lengths and
their recomputed mean must compare unequal. A mean-only ULP mutation is invalid.

vocab is a dynamic map with nonempty string keys. Each value has exactly
required `df,postings`: df integer 1..doc_count; postings a list of two-element
lists `[chunk_id, count]`. chunk_id names an existing doc, count integer
1..2147483647; no repeated doc within one term. df equals posting-list length.
Keep posting order; never sort it during comparison. Additionally the sum of
all posting counts for each doc equals its dl, matching actual build output.
For an empty index docs/vocab are both empty and avg_dl is zero. Do not implement
or invoke a second tokenizer to verify these algebraic relations.

## Required acceptance

- Independent complete numeric byte/hash vectors, including type/tag collision,
  UTF-16 key order, zero signs, one/one-point-zero, 0.1, nextafter, subnormal and
  maximum float; current identity/JCS goldens unchanged.
- Invalid JSON, duplicate escaped keys, unsupported Python values, malformed
  scalar types, finite overflow, cycles and each budget boundary refuse safely.
- Both profiles reject unknown fields/malformed timestamps and validate before
  exclusion. All non-equivalent nonvolatile changes under this codec affect
  comparison (numeric equivalence and object insertion order are intentional);
  nested
  names matching volatile root keys remain material or fail closed.
- Rebuild real disposable pinned-upstream pages twice via public commands,
  synthetic prefix only, then compare all chunk/BM25 objects and exact Markdown.
  Verify raw source inventory is unchanged. Use actual emitter fields, not
  introductory examples that omit prefix or hashes.
- A public build/query CJK fixture proves the nine terms of 全文检索 and NFKC
  variant consistency. Preserve legal overlap chunks and actual identities;
  do not add evidence-unit IDs, choose query policy/gold or implement a tokenizer.
- CI/local/wheel evidence is tied to the final frozen source and actual tested
  checkout. This runtime slice does not close the full projection packet,
  VPKB-000, VPKB-001, or any human gate.
