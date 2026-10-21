# Capture and code evidence contracts v1

Revision: 2. Architect: Codex (`gpt-5.6-sol`, `ultra`). Status: frozen.
Reviewed by Builder and Repo Steward; their reference/text/error-order questions
were resolved before implementation release on 2026-09-01.
Packet baseline: `65c279f3dac280f1046c08536f59887b0dc613c7`.

This is a normative in-memory contract, not permission to capture, fetch, read a
Vault, import upstream code, or apply a transaction. The only permitted I/O is
the existing registry's loading of immutable packaged schemas; no function reads
caller-supplied paths, enumerates files, writes files, or starts network/process I/O.
Objects describe observations supplied by a future trusted adapter. Validation
does not prove complete filesystem enumeration, stable files, genuine upstream
plans, an approved operation, or a verified source ID. VPKB-001 must prove those
separately before production consumption.

Revision 2 clarifies that packaged-schema loading is allowed; the field/hash/
byte semantics of revision 1 are unchanged. Cold registry loads are not evidence
of pure no-I/O execution. Isolation tests warm the schema registry explicitly and
then forbid filesystem/network/process access for all supplied-data operations.

## Shared representation

Use existing JCS and SHA-256, lowercase hex digests, common repository/full_commit/
source_id/portable_vault_relative_path definitions, and ContractError (exit code 2).
All objects, including nested objects, reject unknown fields. No floats, bools
in integer fields, coercion, trimming, mutation, or implicit defaults. Required
nullable fields remain present. Schema identifiers are the filenames without
`.schema.json`, under the existing schema URL prefix. Register both root schemas.
Do not change common, existing identities, receipts, locators, or CLI behavior.

`payload` is a closed object with required `sha256` (common sha256) and
`size_bytes` (integer, 0..67108864). Zero bytes are legal only for code text;
PDF size must be >=5. A supplied PDF byte string must start with ASCII `%PDF-`.
These checks do not claim full PDF validity. Supplied bytes must match BOTH
declared size and raw SHA. Python byte APIs accept bytes only, not str, bytearray,
memoryview, or arbitrary coercible objects. Enforce length before decoding.

Operation IDs match the existing receipt grammar
`[A-Za-z0-9][A-Za-z0-9._-]*` with full-string matching, and are opaque declarations;
never derive them from source IDs. All path/ID/digest regex checks reject trailing
newlines as well as traversal. Logical paths keep case and existing portable
grammar; dot-prefixed segments, spaces, and Unicode paths remain unsupported.
Repository case is preserved in serialized objects; comparisons use casefold.
There is no whitespace stripping or repository alias expansion in this contract.

A captured path is exactly `.raw/captured/<64-lowercase-hex>.<suffix>` where
suffix matches `[A-Za-z0-9][A-Za-z0-9._-]*` in full; no nested paths. Its digest
must equal payload SHA. This narrower new field does not change common paths.

## Capture inspection schema

Title: `video-paper-wiki.capture-inspection.v1`. All following fields required:

| Field | Type / value |
| --- | --- |
| schema | exact title |
| route | `manual-inbox` or `staged-capture` |
| media_type | `application/pdf` or `text/plain` |
| payload | payload object above |
| source_path | portable `inbox/...` path ending in lowercase `.pdf`, or null |
| proposal_sha256 | sha256 or null |
| stored_path | captured path above |
| source_identity | sha256, exactly payload.sha256 |
| siblings | array of closed sibling objects (0..1024 items) |
| would_change | boolean |
| operation_id | operation ID or null |
| upstream_plan_sha256 | sha256 or null |
| approval_hash | sha256 |

Each sibling has exactly `path` (captured path), `kind` (`regular`, `symlink`,
`special`), `sha256` (sha256 or null), and `mode` (integer 0..4095, permission bits
only, not file type). The adapter supplies lstat type separately as kind. Regular
entries require a non-null byte digest; non-regular entries cannot be accepted,
whether or not a digest is supplied. The list records ALL observed digest siblings;
sort by path's ASCII bytes ascending, without duplicates. Every path digest equals
the inspected payload digest. No truncation or selection from multiple entries.
The array format can describe a rejected observation; successful validation only
admits zero or one regular matching sibling. It is not a runtime enumerator API.

Cross-field rules, checked before approval digest:

1. Manual route is PDF only and requires source_path; staged route requires null
   source_path. Both routes bind the eventual captured target, not the inbox path.
2. PDF requires null proposal_sha256. Code text requires staged route and a
   non-null proposal_sha256 of a code manifest proposal.
3. No siblings: would_change=true; stored_path is exactly
   `.raw/captured/<sha>.pdf` for PDF or `<sha>.bin` for code; operation_id and
   upstream_plan_sha256 are non-null. This is a create-only declaration.
4. One sibling: regular, digest matches payload; stored_path equals that exact
   sibling path (retain legacy suffix); would_change=false; operation_id and
   upstream_plan_sha256 are both null. No upstream transaction/receipt is created
   for reuse. A later publication transaction remains separate.
5. Multiple, duplicate, unsorted, wrong-digest, symlink, special, or foreign-prefix
   siblings are refused. Permission bits are approved observation material, not
   proof of access; changes to bits require a new approval digest.

`capture_approval_hash(doc)` = SHA256(JCS(all inspection fields except
`approval_hash`)). This low-level hash helper does not validate or attest the
document; it must support computing a candidate without that self-hash field.
`upstream_plan_sha256` is an opaque digest supplied by a future adapter and binds
its inspected upstream plan/bundle. This packet neither invents nor verifies the
upstream plan's hash algorithm. Real operation/plan/bundle consistency is blocked
on the pinned upstream fixture and transaction facade. Do not label this field
as a plan already executed or approved by a human.

## Code manifest schema

Title: `video-paper-wiki.code-evidence-manifest.v1`. Required in both states:

| Field | Type / value |
| --- | --- |
| schema | exact title |
| state | `proposal` or `inspected` |
| origin | closed object: repository (common repository), commit (full_commit), path (portable_vault_relative_path) |
| payload | payload object above |
| media_type | `text/plain` |
| encoding | `utf-8` |
| line_canonicalization | `utf8-lf-v1` |
| newline_style | `none`, `lf`, `crlf`, or `mixed` |
| ends_with_newline | boolean |
| line_count | integer 0..67108864 |
| normalized_sha256 | sha256 of normalized full text bytes |
| proposal_sha256 | sha256 of proposal material below |

Proposal forbids `capture` and `manifest_sha256` (including null). Inspected
requires both. `capture` is closed and requires: stored_path (captured path),
source_identity (payload SHA), source_id (common declaration syntax),
inspection_approval_hash (sha256), operation_id (operation ID or null).
`manifest_sha256` is a sha256. There are no other fields or optional metadata.

Proposal material is exactly the above required fields EXCEPT proposal_sha256,
with state fixed to `proposal`, even when reconstructed from an inspected manifest.
`code_proposal_hash(doc)` hashes that material using JCS. `code_manifest_hash(doc)`
hashes all fields of the inspected document except manifest_sha256. Hash helpers
do not validate/attest objects; missing material fields raise SCHEMA_INVALID,
unserializable canonical material raises CANONICAL_JSON_INVALID.

Hash graph (arrows mean depends on): raw digest <- bytes;
proposal digest <- logical origin + raw digest/size + text metadata;
inspection approval <- proposal digest + captured target + complete snapshot +
route + operation + upstream plan declaration; inspected manifest digest <-
proposal material/digest + capture binding (including inspection approval).
Never put inspected manifest digest into inspection, upstream plan, or receipt.
The acyclic proposal digest is the code source declaration that upstream plan
may bind. Existing receipt intent excludes all these approval/bundle hashes.

Object-only checks enforce captured digest/source_identity equality; line_count
cannot exceed size_bytes; empty bytes require line_count=0, newline_style=none,
ends_with_newline=false, and both raw/normalized SHA equal SHA256(empty). Nonempty
requires line_count>=1. newline_style=none requires no final newline and, when
nonempty, exactly one line. No further claims about text bytes without payload.

One manifest contains exactly one logical origin. Multiple origins are represented
by separate manifests, never an array, a merged locator, or deduplication by raw
SHA. Equal bytes can share stored_path/source_identity/source_id across manifests,
but each locator keeps its own repository/commit/path. Repository case changes
affect approval/proposal hashes because approvals bind exact declarations; locator
origin comparison remains case-insensitive for repository and case-sensitive for
path. No global origin-count limit is introduced by this per-file contract.

## UTF-8 and lines

`utf8-lf-v1` strictly decodes UTF-8 (no replacement), rejects initial UTF-8 BOM,
NUL, C0 control characters except TAB/LF/CR, and DEL/C1 U+007F..U+009F. Reject
U+2028/U+2029 as alternate line separators. Reject bare CR; LF and CRLF, including
mixed LF/CRLF in one file, are accepted. Replace every CRLF with LF and make NO
other transformation: no NFKC, casefold, stripping, tab expansion, or whitespace
collapse. An internal U+FEFF remains a literal character, not an initial BOM.

newline_style describes raw terminators: none if none, lf or crlf if exclusively
one style, mixed otherwise. Full normalized bytes preserve the final LF when
present. ends_with_newline describes that final LF. Split normalized text ONLY
on LF, dropping exactly the final empty split sentinel if the text ends in LF.
Empty bytes have zero lines; `b'\n'` has one empty line; `b'a\n\n'` has two lines.
Line numbers are inclusive and 1-based; reject bools/non-integers, start<1,
start>end, or end>line_count. A snippet is selected logical lines joined with LF
and encoded UTF-8, WITHOUT an added final LF. Thus line 1 of `b'a'` and `b'a\n'`
both hashes b'a', while selecting lines 1..2 of b'a\n\n' hashes b'a\n'. Empty
files cannot satisfy any code locator. No platform text-mode I/O is involved.

## Pure Python API and errors

In `capture_contracts.py`:

- `capture_approval_hash(document) -> str` as above.
- `validate_capture_inspection(document, *, payload: bytes | None = None) -> dict`:
  standard schema + cross-fields + approval hash, then optional raw-byte/media
  verification. For text/plain, run the same utf8-lf-v1 policy after raw size/hash
  verification (normalize_code_bytes), even without a manifest. Return the original
  validated dict; never mutate inputs.
- An internal post-schema check callable from contracts.validate_document;
  avoid recursive public validation calls and import cycles.

In `code_evidence_contracts.py`:

- `code_proposal_hash(document) -> str`, `code_manifest_hash(document) -> str`.
- `normalize_code_bytes(payload: bytes) -> bytes`: raw bound/type and text policy.
- `code_text_metadata(payload: bytes) -> dict`: exactly newline_style,
  ends_with_newline, line_count, normalized_sha256 (no raw fields).
- `code_snippet_sha256(payload: bytes, start: int, end: int) -> str`.
- `validate_code_evidence_manifest(document, *, payload: bytes | None = None)
  -> dict`: schema, semantic/hash checks, optionally compare ALL byte-derived
  payload/text metadata. Return original document; do not mutate.
- `validate_code_capture_binding(manifest, inspection) -> None`: validate both
  objects; require inspected code manifest + staged text inspection, matching
  proposal_sha256, payload, and capture's stored_path/source_identity/
  inspection_approval_hash/operation_id. Cannot verify source_id's upstream
  derivation; do not accept source-id verifier callbacks in this packet.
- `validate_code_locator(locator, manifest, payload: bytes) -> None`: schema-check
  against existing common code_locator, validate inspected manifest with bytes,
  compare repository (casefold), commit/path/source_id (exact), line bounds and
  snippet digest. Optional symbol has no identity/hash role; do not resolve it.

contracts.validate_document dispatches object-only checks for both schemas. It
cannot replace the explicit byte/binding checks. Pure helper error codes:

| Code | Cause |
| --- | --- |
| SCHEMA_INVALID | shape, type, unknown field, invalid path/ID grammar |
| CANONICAL_JSON_INVALID | hash material not representable by existing JCS |
| CAPTURE_SNAPSHOT_INVALID | sibling count/order/type/digest or selection mismatch |
| CAPTURE_BINDING_MISMATCH | route/media/nullability/source identity/operation or cross-object binding inconsistency |
| CAPTURE_APPROVAL_MISMATCH | inspection approval hash differs |
| CODE_MANIFEST_MISMATCH | proposal/manifest hash or declared text metadata inconsistency |
| PAYLOAD_MISMATCH | provided byte size/hash/media differs from declaration |
| CODE_TEXT_INVALID | invalid UTF-8, BOM/control/newline policy |
| CODE_LINE_RANGE_INVALID | invalid integer line range or out of bounds |
| CODE_LOCATOR_MISMATCH | locator origin/source ID/snippet differs |

Oversize bytes use PAYLOAD_MISMATCH before decoding. Byte API type errors use
SCHEMA_INVALID. All errors include a useful instance_pointer (empty for raw
bytes, `/lines` for range) and schema where an object is involved; never echo raw
payload. Schema validation precedes semantic checks, which precede self-hash
checks, then supplied bytes. Tests isolating a semantic rule repair unrelated
self-hashes first. Multiple-invalid-field error ordering is not a v1 API promise.

JSON Schema's mathematical integer may accept 1.0; the Python v1 boundary does
not. Explicitly require type(value) is int for all size/mode/line-count fields
and locator start/end, returning SCHEMA_INVALID otherwise. Schema-first locator
validation returns SCHEMA_INVALID for start=0 or bool; direct snippet API uses
CODE_LINE_RANGE_INVALID for those inputs. Validly typed positive but reversed or
out-of-bounds locator ranges use CODE_LINE_RANGE_INVALID. Shared `$`-anchored
regex refs alone are insufficient for Python's trailing-newline behavior; add
strict full-string checks in these new APIs without changing common or old APIs.

## Implementation and acceptance

Builder owns only the two new schema files/modules, contracts.py registration/
dispatch, tests/contract/test_schemas.py enumeration, and new packet-specific
tests/fixtures under tests/contract, tests/unit, tests/fixtures/contracts. Common,
CLI, identity.py, JCS, dependency lock, existing business fixtures and catalog are
unchanged. Steward may add independent tests in a separate named file after
Architect assigns it. Architect alone edits this freeze document and packet/index.

Required meaningful tests cover each branch/refusal above, exact known byte/hash
vectors (not just helper-vs-helper), hash sensitivity to every approval field,
no input mutation, no I/O/upstream dependency, two origins sharing bytes, recursive
unknown fields, schema resource registration and installed-wheel use. Replay the
full baseline plus new tests on Python 3.12/3.13 and the existing macOS/Linux CI
matrix. Preserve prior 667-test evidence. This packet's acceptance cannot close
VPKB-000 or a human gate and does not authorize merging PR #94.
