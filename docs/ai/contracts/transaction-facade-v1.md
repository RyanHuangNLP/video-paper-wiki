# Non-persistent transaction facade v1

Status: **frozen, revision 1; pure implementation released**.
Owner: Architect. Packet: VPKB-000-transaction-facade.
Baseline: `9d87dc67b949fc0cef5ac64b91a2d15aea8ec0fe`.

## Purpose and boundary

This is the one in-memory transaction declaration used by future CLI, receipt
and audit adapters. It describes intended bytes and supplied upstream evidence;
it neither executes nor authorizes anything. Validation is not proof of a safe
filesystem read, complete evidence inventory, genuine upstream response,
operator approval, ledger validity, lock ownership or a successful apply.
Those assertions require VPKB-001's pinned adapter and integrity runtime.

Freeze evidence, 2026-09-01: Builder and Steward independently reviewed the
complete draft. Builder's fixed public-CLI investigation r4 and Steward's fresh
steward1 replay each passed the positive, expansion-negative and wrong-source-ID
tracks, with unchanged pinned upstream source inventory. Reviewed runner SHA:
`194ea887de43206cf5af9ccd993e1f9252d36e139308694f9d6bb13fa44d14ed`.
These establish the engine-compatibility policy, not full domain prospective,
structured locator, production projection, race/rollback or human acceptance.
Permanent portable regression tests and final local/CI evidence are still
required for this packet's implementation acceptance.

No API in this module opens a supplied path, invokes upstream, creates staging,
fetches, installs admin, or changes a Vault. Loading immutable packaged schemas
is permitted. Existing identity/JCS, receipt, capture and record contracts stay
unchanged; new stricter facade checks do not retroactively change their APIs.

The fixed engine is claude-obsidian v2.1.1, commit
`9f8c1199047eac2c3828496279fbb7ba9540b90b`. Its source SHA and public-CLI
behavior observations are separate evidence, not fields implying trust.

## Application policy and upstream compatibility

The project reuses the public transaction/capture/lint/chunk/BM25 engines and
canonical source/claim ledgers. It does not run the entire upstream wiki-ingest
Skill workflow. In particular, canonical provenance is not the legacy
`.raw/.manifest.json` address/ingestion metadata. The pinned chunker supports
pages without `address`, generating its own synthetic address from the complete
canonical relative-path SHA. This is neither a source ID nor canonical state.

For all three facade operation types, `address_requests` is explicitly `[]` and
`source_manifest_updates` is explicitly `{}`, matching their pinned upstream
array/object types. The allowed expanded
path list is therefore exactly empty. Nonempty requests are rejected, not
ignored. Direct writes to the counter/legacy manifest or use of setup/migration
authority to simulate expansion are prohibited. The upstream raw plan's input
and expanded bundle digests must be equal under this application policy.

This restriction preserves the complete project domain workflow: canonical
ledger merging, capture identity, claim anchors and retrieval remain required.
It is not an upstream-wide claim that managed requests are unsupported. The
pinned engine injects address bytes and appends counter/manifest writes for
nonempty requests; that workflow cannot satisfy this project's head-last rule.
The positive compatibility workflow and expansion counterexamples passed real
isolated public-CLI fixtures for this freeze. The compatibility fixture uses a
fixture-only head, metadata record and two-section page, with honest synthetic
upstream string locators; it does not freeze the later domain-to-ledger mapping.

The Paper frontmatter list in development-plan section 6.1 needs an explicit
compatibility addition for strict upstream lint. In addition to its existing
fields, generated pages render `status: generated` as a constant presentation
label, `created`/`updated` as the UTC calendar-date portions of canonical record
`created_at`/`updated_at`, and `tags` as the sorted unique strings
`<axis>/<slug>` from canonical record taxonomy. Sorting is ascending Unicode
code-point order, no locale collation. This adds no field to the closed record
schema, ingestion lifecycle, assessment or human gate. These Markdown bytes are
never treated as volatile. Production rendering remains in the projection
packet; these rules constrain the compatibility fixture now.

## JSON types, paths and limits

Both new schema documents use Draft 2020-12 and close every fixed object.
Dynamic maps allow only string path keys and the value types below. Public
validators accept JSON-shaped Python `dict`/`list` values, reject cycles,
non-string keys, bool-as-integer, floats in integer positions and non-finite
numbers with `ContractError`, never an incidental Python exception. Integer
bounds are inclusive. Hashes match the entire lowercase `[0-9a-f]{64}` grammar.

Operation IDs match the entire `[A-Za-z0-9][A-Za-z0-9._-]*` grammar and are at most
128 characters. Sequences are integers 1 through 999999999999, fitting the
already-established twelve-digit receipt filename. No truncation is allowed.

Path checks reject rather than repair: no absolute path, backslash, empty,
`.` or `..` component, ASCII control character (U+0000..001F or U+007F), lone
surrogate, non-NFC spelling, or more than 1024 UTF-8 bytes. Read paths may retain
legacy Unicode/space/Windows-unportable names under these lexical rules; they
must not be subjected to the stricter new-write grammar. Paths with any component
equal to `.git`, `.obsidian` or `.vault-meta` under the portable-name comparison
below are not facade evidence inputs or destinations. This includes `.GIT/config`
and `wiki/.git/config`; it is an explicit application restriction on reads, not
a claim about all upstream lexical paths.
Each write component after its approved prefix matches
`[A-Za-z0-9][A-Za-z0-9._-]*`, has no trailing dot, and is not a Windows reserved
device basename (case-insensitive CON/PRN/AUX/NUL/COM1..9/LPT1..9 before the first
dot). Prefix spelling is exact lowercase. Upstream still rechecks actual
filesystem aliases; pure validation cannot enumerate siblings.

Compare each component using `NFC(component.casefold())`, matching the pinned
engine's portable-name key; plain casefold alone is insufficient. Check
collisions over the union of writes and read-precondition paths, including
ancestor components: `wiki/papers/A/x` with `wiki/papers/a/y` is a collision.
Two already-NFC legacy read components `\u0390.md` and `\u03aa\u0301.md` also
collide after this key even though plain casefold strings differ. A file path
may not also be an ancestor of another input/destination.
Forbidden components are compared with this same key. Exact
repeated membership in an expected-hash map is a reference, not a new
path. Writes and read preconditions themselves are disjoint.

Limits include receipt and head: 1..1024 writes, each new and original file
0..67108864 bytes, sum of new bytes <=134217728 and sum of original bytes
<=134217728. There is no artificial 1024-entry read-precondition limit.
The upstream runtime JSON/bundle encoding limits still apply in VPKB-001;
passing declaration budgets does not promise the serialized transport fits.

## Operation head

New schema/title: `video-paper-wiki.operation-head.v1`. Exact fields:

| Field | Type / rule |
| --- | --- |
| schema | literal title above |
| sequence | bounded sequence |
| receipt_path | `wiki/meta/operations/<12 digits>-<operation ID>.json` |
| receipt_sha256 | SHA-256 of the complete receipt file bytes |

The filename's sequence equals `sequence`, is nonzero, and its operation ID
uses the bounded grammar. Head path is always
`wiki/meta/registries/operation-head.json`. The schema describes an object,
not a filesystem pointer that its validator may follow.

## Transaction declaration

New schema/title: `video-paper-wiki.transaction-facade.v1`. All following fields
are required, including explicit nulls/empty collections:

| Field | Type / rule |
| --- | --- |
| schema | literal title above |
| phase | `proposal` or `inspected` |
| operation_id | bounded operation ID |
| operation_type | `capture`, `ingest` or `generic` |
| writes | ordered write descriptors below |
| expected_hashes | path -> SHA-256 or null; keys exactly the writes |
| read_preconditions | path -> SHA-256 or null; separate non-write inputs |
| claimed_inputs | existing receipt claimed-input objects, canonical path order |
| address_requests | empty array |
| source_manifest_updates | empty object |
| engine_expanded_paths | empty array |
| receipt | existing operation-receipt object, or null for capture |
| head | operation-head object, or null for capture |
| input_bundle_sha256 | caller-supplied digest of the exact upstream input bundle |
| declaration_sha256 | local declaration binding defined below |
| inspection | raw pinned upstream plan object, or null |
| runtime_result | raw pinned complete result object, or null |

`input_bundle_sha256` is opaque upstream hash evidence supplied by the adapter.
It is not JCS, capture approval, receipt intent, expanded bundle or plan approval.
This facade deliberately has no upstream-hash implementation and cannot verify
the mapping from a transport's actual bytes to that supplied digest. VPKB-001
must prove that association at the pinned public-CLI boundary, using the exact
bundle presented to inspect/apply; matching writes alone is insufficient because
read preconditions and content-file transport also affect upstream approval.

Each write has exactly `path`, `role`, `mode`, `sha256`, `size_bytes`,
`original_size_bytes`, `original_mode`. Roles are `business`, `receipt`, `head`;
mode is `create` or `replace`; sizes use the limits above. `original_mode` is
null for create, an integer 0..511 for replace. A create has expected hash=null
and original_size_bytes=0. A replace has non-null expected hash. The expected
new Unix permission bits are 384 (0600) for create and original_mode for replace,
matching the pinned engine's preserve-existing-mode behavior. No chmod feature
is introduced. These are supplied stat declarations, not evidence of real mode.

All business writes come first in ascending path order; then exactly the
receipt, then exactly the head for publication. Duplicate paths are rejected.
The input list must already have this order; validators do not silently sort.
Receipt/head writes are not included in `receipt.writes`.

Allowed business paths, stricter than the older common regex, are:

- `.raw/captured/<64 lowercase hex>.<portable extension>`: capture only,
  create only, digest in basename equals descriptor sha256.
- `.raw/derived/<portable components>`: ingest only, create only.
- `wiki/papers/**`, `wiki/code/**`, `wiki/concepts/**`,
  `wiki/meta/ledgers/**`, `wiki/meta/records/**`: ingest/generic.
- `wiki/meta/reviews/**`, `wiki/meta/gates/**`: ingest/generic, create only.
- exact `wiki/meta/registries/gate-heads.json`: ingest/generic.

All globs above mean at least one complete portable component, no empty suffix.
No other registry file, operation receipt, `wiki/index.md`, `wiki/notes/**`,
legacy raw manifest or runtime path is a business write. Generic never writes
raw, and ingest never recaptures an existing source: capture is separate.
Setup/adopt and upstream-only maintenance stay outside this publication facade;
they cannot manufacture a vpwiki receipt. Their managed-state effects are
covered by VPKB-001 bootstrap/audit policy, not silently exempted here.

For capture all writes are business captured paths, claimed_inputs=[],
receipt=head=null. It creates no publication receipt. A no-write capture reuse
belongs to capture-inspection.v1 and is not a write transaction. This facade
does not replace its sibling/route/media/source-ID checks.

For ingest/generic, receipt and head are mandatory and there must be at least
one business write. Validate the embedded receipt against the existing schema
and intent hash, then additionally require:

- operation ID/type equal the transaction, bounded sequence and ID;
- receipt.writes equals the business descriptor projection in order:
  `{path,mode,before_sha256:expected_hashes[path],after_sha256:sha256}`;
- receipt.claimed_inputs equals transaction.claimed_inputs, with unique paths
  in ascending order; every item has an equal non-null read_preconditions
  digest. They are a subset, not an alias for all read preconditions. The claim
  path whitelist is the complete business path list above **without** its
  operation-type or create/replace restrictions: generic may claim existing
  captured and derived raw as well as the listed wiki paths. The same portable
  grammar applies; a captured filename digest must equal the claimed hash.
  Only gate-heads.json is an allowed registry claim; all operation receipts,
  operation-head.json, other registries and runtime paths are excluded. Do not
  use the older, broader common business regex as this whitelist;
- sequence=1 only for generic, previous=null, head create/expected null;
- sequence>1 requires previous receipt path with sequence exactly one less,
  previous digest in read_preconditions, head replace/expected non-null;
- previous receipt cannot be a business input claim, current receipt or head;
- receipt write path is the canonical sequence/operation-ID filename and its
  mode is create; head write path is the fixed path and correct mode;
- head sequence/path/digest identify this receipt and its actual file bytes.

Receipt and head new file bytes are exactly RFC8785 JCS UTF-8, **no trailing
newline**. Their descriptor sizes/hashes must equal those canonical bytes even
in declaration-only validation. This agrees with existing canonical-object
hashes; do not pretty-print after approval. Claimed inputs, receipt intent,
receipt bytes, head bytes, bundle, and local declaration form an acyclic graph.
Genesis claiming the pristine setup allowlist, ever-claimed membership, full
ledger/owner validity and replay of the historical receipt chain remain separate
VPKB-001 prospective/audit checks; a facade object alone does not prove them.

`declaration_sha256` is SHA256(JCS(the complete declaration with exactly `phase`,
`declaration_sha256`, `inspection`, `runtime_result` removed)). It binds every
proposal field, including the opaque input bundle digest and empty-policy fields.
Its API rejects unknown fields by validation before consuming the binding; the
low-level hash helper hashes supplied material without claiming validation.
It does not include a successful inspection or runtime result, and cannot
fabricate either. There is no new persisted transaction-state database.

## Supplied upstream inspection and result

Proposal requires inspection=runtime_result=null. Inspected requires inspection
non-null and runtime_result either null or a matching complete result. Missing
runtime result is normal, not a broken receipt chain or failed transaction.

The pinned plan has exactly: schema=`claude-obsidian.transaction-plan.v1`,
operation_id, operation_type, valid=true, changed_paths, hashes, modes,
input_bundle_sha256, expanded_bundle_sha256, vault_identity, approval_sha256.
vault_identity is exactly `{state:'existing',device:<integer>,inode:<integer>}`
for these post-setup operations. Integers are non-negative, never bool/float;
the absent/setup identity variant is outside this facade's operation scope.

The complete result has exactly: schema=`claude-obsidian.transaction-result.v1`,
operation_id, operation_type, bundle_sha256, expanded_bundle_sha256,
approval_sha256, status='complete', changed_paths, hashes, modes. No synthetic
success result may be produced in place of a missing result.

For both, IDs/types match; changed_paths equals the **ordered complete** facade
write path list, including receipt/head and the fixed empty expanded set;
hashes/modes have exactly those keys and equal new SHA/mode declarations.
Plan input hash equals the declared input hash; plan expanded hash also equals
it under the empty-request policy. Result bundle/expanded/approval hashes equal
the corresponding plan fields. No hash is recomputed with project JCS.
An extra/missing/reordered path, mode/hash mutation, ID/type mismatch or digest
mismatch is a refusal. Runtime `status` other than complete is not coerced.

The supplied plan's `valid:true` is upstream data, not this module's attestation.
The adapter is responsible for its authenticity and freshness. Declaration hash
plus exact input digest matching detects mismatched supplied bindings across
the separate hash domains, but cannot authenticate a fabricated declaration.

## Public Python APIs and errors

New module: `video_paper_wiki.transaction_contracts`.

- `transaction_declaration_hash(document: object) -> str`: exact material above,
  excludes only the four listed fields. It requires a dict and every material
  field. Unknown material is included, not discarded. Cyclic/noncanonical
  material raises CANONICAL_JSON_INVALID. Does not invoke the validator.
- `validate_transaction(document: object) -> dict`: central registry schema
  plus semantic validation. Returns a deep independent JSON-shaped copy.
- `validate_operation_head(document: object) -> dict`: same for head.
  Deep-copy guarantees belong to these new wrappers; central validate_document
  retains its existing return semantics while dispatching the new checks.
- `attach_upstream_inspection(proposal: object, inspection: object) -> dict`:
  requires a valid proposal; copies it, sets phase/inspection, validates all
  correlations. Does not alter its declaration hash or synthesize evidence.
- `attach_runtime_result(inspected: object, result: object) -> dict`: requires a
  valid inspected declaration with runtime_result=null, copies/attaches supplied
  evidence and validates it. It cannot replace previously attached evidence.
- `verify_transaction_bytes(document: object, *, write_bytes: object,
  original_bytes: object, read_bytes: object) -> None`: validate first, then
  check exact map keys. write_bytes maps every write to bytes; original_bytes
  maps every write to original bytes or null matching create/replace;
  read_bytes maps every read precondition to bytes or null. Exact `bytes`, no
  coercion from path/string/memoryview. Compare lengths and SHA to declarations,
  and receipt/head bytes to canonical bytes. Original/read null means supplied
  absence, not an automatic filesystem probe. This is byte consistency, not
  no-follow/TOCTOU/stat/approval verification; it returns no execution result.

All failures use ContractError(exit_code=2) and stable `details.instance_pointer`
where applicable. Validation order: shape/JSON types; lexical paths/IDs and
policy; set/order/scope/limit/precondition invariants; embedded receipt/head
validation and correlation; declaration binding; phase/upstream correlation;
optional byte verification. In validators and attaching helpers, cycles,
non-string keys and non-JSON containers/scalar types fail the shape preflight
with SCHEMA_INVALID. The standalone declaration hash helper reports
CANONICAL_JSON_INVALID for cyclic/noncanonical material instead. It is not a
shortcut around validation. A read byte snapshot has no declared size field:
only its bytes/null and digest are compared; do not invent a per-read or
aggregate read-size limit in this API. Dedicated codes:

| Code | Meaning |
| --- | --- |
| SCHEMA_INVALID | shape, unknown field, exact scalar grammar/type |
| CANONICAL_JSON_INVALID | noncanonical/cyclic hash material |
| TRANSACTION_PATH_INVALID | lexical/new-write path rule |
| TRANSACTION_PATH_COLLISION | duplicate/casefold/ancestor collision |
| TRANSACTION_POLICY_INVALID | scope, immutable mode, nonempty expansion request |
| TRANSACTION_LIMIT_EXCEEDED | size/total/write-count limit |
| TRANSACTION_PRECONDITION_MISMATCH | expected/read/claimed maps or create/replace state |
| TRANSACTION_ORDER_INVALID | unsorted writes/claims or receipt/head position |
| TRANSACTION_RECEIPT_MISMATCH | publication/receipt/head/previous linkage |
| TRANSACTION_DECLARATION_MISMATCH | local declaration digest |
| TRANSACTION_UPSTREAM_MISMATCH | wrong supplied upstream plan/result or phase transition |
| TRANSACTION_BYTES_MISMATCH | supplied byte type/keyset/length/hash/canonical bytes |

Existing embedded receipt schema/intent errors retain their established codes.
Schema limits that preclude reaching semantic checks may report SCHEMA_INVALID;
tests should use dedicated codes for well-shaped semantic failures, not rely on
incidental jsonschema traversal order for multiply-invalid input.

## Acceptance before release

1. Independently review this exact contract, real upstream observations, and
   the domain-policy/projection additions; record frozen revision and SHA.
2. Implement both closed schemas, central registry dispatch and only the pure
   APIs above. Do not change common/identity/JCS/CLI/dependencies/catalog.
3. Positive capture, generic genesis, later generic/ingest, optional result,
   and >1024 read inputs; mutation tests for every correlation and hash domain.
4. Invalid Unicode/legacy-vs-new paths, component collisions, ancestors,
   non-string keys, cycles, bool/int, immutable raw/events, all budget edges,
   read/claim distinction, canonical receipt/head and head-last regressions.
5. Prove helpers never open supplied paths or call upstream; immutable packaged
   schema resource access remains allowed. Test input-copy isolation.
6. Run full locked Python 3.12/3.13 regressions, independent Steward probes,
   installed-wheel schema/API smoke, source-stability checks and exact-commit CI.

This packet's acceptance does not complete VPKB-000, the production adapter,
runtime audit, retrieval join, engine MVP, human gates or authorization to merge.
