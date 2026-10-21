# SOURCE state implementation checklist R1

Status: read-only implementation handoff for the retained source-state loader.
This checklist is based on the accepted SOURCE-SEMANTICS R2 interfaces and the
current source checkout at `.work/parallel/source-semantics-v1/terminal-1/source`.
It does not change production code, the Vault, the four new schema count, or the
SOURCE-PUBLICATION R2 no-op contract.

## Boundary and invariants

The loader must establish one retained, named snapshot before it parses source
state. All managed bytes used below come from that snapshot or from the pinned
taxonomy resource. Reads through the retained snapshot API are expected; an
independent path read after retention, or a read of a path that was not retained
as a slot, is a potential race and must not authorize state. The loader reports a
consistency result; it does not authenticate a human, operator, remote source, or
test fixture as real authority.

The existing `projection-input.v1` is the base inventory contract. Its validator
is intentionally closed and contains the portability rules for this state:

* `validate_projection_inventory()` in `projection_input.py:99-138` requires a
  closed `{schema, entries}` root, at least one source ledger, claim ledger and
  taxonomy entry, strictly UTF-8-byte-sorted paths, NFC spelling, case/NFC and
  Windows-device collision rejection, per-entry size and total-byte limits, and
  digest-bearing filenames whose digest matches the entry hash.
* `validate_projection_bytes()` in `projection_input.py:141-160` requires the
  byte-map keys to equal the inventory paths exactly, every value to be `bytes`,
  and every declared size and SHA-256 to match. Missing, extra, mutable-looking,
  or orphan map entries are input mismatch errors.
* The v1 inventory kinds remain the existing set: source/claim ledgers and
  taxonomy; paper and repository records; v1 assessment events; captured
  artifacts; Docling document/parser/model/run manifests; code-evidence
  manifests; and alignment manifests. A source-version association, display
  decision/head, v2 paper record, v2 locator, or v2 assessment event must be
  parsed through its explicit semantics contract and named publication slot. It
  must not be silently reclassified as an arbitrary v1 projection kind.

The retained collector must preserve the existing four new schemas and use the
pure source semantics as validators. It may add typed state handling in the
publication/catalog continuation, but it must not add a second claim identity,
source ledger, assessment ledger, or durable no-op schema.

## Loader order

Use this order so that failures are deterministic and no parser observes a
different directory lineage:

1. Retain the vault root, the approved upstream root, and all fixed input slots
   with named path, inode/device identity, bytes or absence, size and mode. The
   retained set includes current head, receipt directory, both ledgers, all
   `.raw/captured` files, derived extraction/manifests, records, reviews, pages,
   and expected publication paths. Keep absent slots as absence preconditions.
2. Run `receipt_audit.audit_integrity()` on the same `_Snapshot`. It checks the
   mutation lock, safe regular files and private modes, symlink/hardlink and
   portable-path rejection, complete receipt reachability and sequence, receipt
   intent/filename identity, claimed-input and write replay, the current managed
   set, immutable captured bytes and raw orphans, and optional runtime-result
   correlation. Re-run snapshot verification on success and in every exception
   path.
3. Enumerate the retained audited bytes with the same managed namespaces used by
   `receipt_audit._walk_inventory()`. Add pinned `taxonomy/v1.json`, construct
   the sorted `projection-input.v1` inventory, and call both projection validators
   before dispatching any typed record parser. A zero-head empty state is a
   valid `empty` audit result for audit only; SOURCE-PUBLICATION entrypoints
   still require an existing receipt-backed generic genesis. Pristine ledgers
   without a real genesis receipt are `RECEIPT_BOOTSTRAP_REQUIRED`.
4. Parse the two ledgers and each typed root from the retained byte map. Use
   closed v1 contracts for existing records and the accepted source semantics
   contracts for version-aware records. Keep source ledger snapshots used by a
   registration proof separate from the current ledger bytes.
5. Build exact maps for raw captured bytes, extraction artifacts, receipt bytes,
   registration-ledger snapshots, records, decisions, heads, events and page
   outputs. Validate key sets before validating values. Every generated or
   referenced path must be represented exactly once in the expected role.
6. Validate the source graph and prospective compiler input. For v2 sources use
   `source_versions.validate_source_inventory()` and
   `canonical_compiler_v2.compile_pages()`; for a legacy-only input delegate to
   the unchanged v1 compiler after proving that all v2 source maps are empty.
7. Materialize catalog/query rows only after the complete graph is valid. The
   row projection must preserve the source and claim owner relationships,
   extraction/run bindings, evidence locators, assessment heads, taxonomy and
   page coverage. A successful parse does not by itself make the state current;
   current status still depends on receipt-backed managed bytes and the named
   catalog generation.
8. Verify every retained file and absence slot again, including the complete
   expected set and every named edge used by the graph. A child validation error
   cannot hide a snapshot race or out-of-band write.

## Path and graph mapping

| Retained path or input | Kind/validator | Required cross-check |
| --- | --- | --- |
| `wiki/meta/ledgers/source-ledger.json` | v1 historical source-ledger projection through `source_registration.historical_source_ledger()` | Closed root, exact source IDs and row fields, valid dates/enums/locators, target path/hash/primary/document row, no duplicate path or hash owner |
| `wiki/meta/ledgers/claim-ledger.json` | Existing claim-ledger parser and claim-owner reconstruction | Claim IDs, owner subjects, evidence transport, assessment state and event heads agree; do not treat the upstream ledger validator as a closed projection unless its bounded fields are explicitly frozen |
| `taxonomy/v1.json` | Pinned resource | `canonical_compiler_v2.concept_items_for_papers()` derives the allowed `(axis, slug)` set and labels; unknown terms refuse and are never silently created |
| `wiki/meta/records/papers/<id>.json` | Legacy paper-record v1 or version-aware paper-record v2, selected by the document discriminator | Canonical identity/aliases, complete claim refs, source association refs, display head, active extraction pair and source IDs; v2 records must be checked by `_versioned()` |
| `wiki/meta/records/repos/<id>.json` | Existing repository record v1 | Canonical repository identity, paper ownership and code claim refs; output path and code-manifest joins remain v1-compatible |
| `wiki/meta/reviews/clm-<20hex>/ase-<20hex>.json` | v1 or v2 assessment event | Claim ownership, connected history, exact transition/profile/fingerprint and one derived head from `derive_assessment_heads()`; no branch, cycle, stale claim mirror or human bypass |
| `.raw/captured/<sha>.<ext>` | Captured artifact; digest in filename is mandatory | `projection_input` enforces filename/hash identity and uniqueness; source v2 Markdown additionally requires `.md`, exact UTF-8 observation/page spans and the pinned `source_id` formula |
| `.raw/derived/<sha>/docling/...` and `runs/...` | Legacy Docling document/parser/model/run manifests | Path digest, schema, parser/model/run relationship, source artifact binding, successful run, and paper active-extraction mirror. These remain PDF/Docling evidence and are not Markdown associations |
| `.raw/derived/code-manifests/<sha>.json` and `alignment-manifests/<sha>.json` | Existing code-evidence/alignment manifests | Filename digest, repository/commit agreement, paper/repository joins, and generated code page coverage |
| `.raw/derived/markdown-source/<raw-sha>/<observation-sha>.json` | v2 extraction descriptor | Bytes equal `canonicalize(observation)`; path/hash/size equal `source_semantics_contracts.extraction_descriptor()` |
| `.raw/derived/source-ledgers/<ledger-sha>.json` | v2 historical registration snapshot | Bytes equal the ledger hash named by the association registration descriptor and the first qualifying receipt write; never substitute the mutable current ledger |
| `wiki/meta/records/source-versions/<association-id>.json` | v2 source-version association | `association_id`, `source_id`, raw identity, observation, registration and extraction all bind one exact source; association inventory rejects duplicate keys, duplicate IDs and cross-paper source/hash ownership |
| `wiki/meta/reviews/source-display/<decision-id>.json` and `source-display-heads.json` | v2 display history/head | One complete per-paper chain, exact association references, consecutive sequence, no forks/cycles, and head materialization equal to `derive_display_heads()` |
| `wiki/papers/*.md`, `wiki/code/*.md`, `wiki/concepts/*.md` | Compiler outputs | Safe deterministic paths, no case/NFC collisions or orphans, complete related links, escaped untrusted text, and paper/concept/code coverage for all prospective records |

The source graph is keyed by immutable edges rather than by path names alone:

* A source association binds `paper_id`, `source_id`, version descriptor, raw
  `{path, sha256, size_bytes}`, exact observation, registration descriptor and
  extraction descriptor. `association_inventory()` rejects a duplicate version
  key and any raw/source identity owned by another paper.
* `validate_source_inventory()` requires the raw, extraction and registration
  maps to have exactly the path sets declared by the associations. It validates
  Markdown payloads, requires extraction bytes to equal the canonical
  observation, caches `registration_proof()` by raw path plus ledger hash, and
  compares the derived proof byte-for-byte with each association descriptor.
* A v2 paper record's association refs must equal its complete association set.
  `_versioned()` derives the display head, checks the active extraction mirror,
  derives assessment heads, resolves every Markdown locator against retained raw
  bytes, and requires `record.source_ids` to equal the union of association and
  evidence source IDs.
* `_owners()` in `canonical_compiler_v2.py` reserves each canonical paper ID and
  canonical alias, validates explicit arXiv/DOI identity bindings, requires
  claim refs and supplied claims to be the same complete set, disallows duplicate
  claim owners, and requires each claim subject to be its paper owner. The
  compiler then derives the complete pinned concept set and rejects mismatched
  supplied concepts or output paths.

## Registration and pending source state

`source_registration.receipt_chain()` is the historical chain proof. It requires
canonical head and receipt bytes, canonical receipt filenames and intent IDs,
the complete reachable sequence from one through the head, no cycles/gaps/orphans,
and replay-safe claimed-input/write preconditions. Its replay has a deliberately
bounded pristine exception: sequence 1 may introduce the source and claim ledger
roots as genesis read claims. A captured raw path is otherwise introduced only by
a claim whose filename digest equals its claimed hash.

`registration_proof()` then requires the raw descriptor to be exactly
`.raw/captured/<sha256>.md` with the source identity derived from that path/hash.
The first receipt that mentions this path must contain exactly one matching read
claim, no raw write, operation type `ingest`, and exactly one source-ledger write.
The supplied historical ledger bytes must hash to that write's after-hash. Its
target row must use the exact file locator, content hash, `document` kind,
`primary` authority and ingestion date, and no other row may claim the same path
or hash. A later ledger snapshot is not evidence of the first registration.

For a new registration, validate the current audited receipt-backed state first,
then construct the pending source-ledger bytes by copying the validated current
ledger and adding exactly the target row. Keep that pending overlay in the
prospective publication request; do not feed it to `registration_proof()` as if
it were already historical. The overlay can become a registration snapshot only
after the operator-applied receipt writes it and the next retained audit binds
the resulting receipt. A pending ledger write is valid only after the exact
registration branch has been selected and its path/hash/ID, write precondition,
and complete expected-set checks have passed.

`markdown_source.admit_markdown_source()` enforces the branch ordering: the
capture result is first bound to the inspected capture transaction, a distinct
admission batch and operation are required, current audit must be receipt-backed,
the captured raw bytes and source ledger are retained together, and existing
source ID/path/hash matches are compared before staging the ledger write. A
matching registration plus an already claimed raw path is the reuse branch. A
matching ledger row without the raw claim, or a raw claim without the matching
row, is a conflict.

The reuse result is an exact nondurable envelope, currently shaped as:

```json
{
  "state": "source_already_registered",
  "source_id": "src-...",
  "stored_path": ".raw/captured/<sha256>.md",
  "paper_id": "...",
  "published": true,
  "receipt_backed": true
}
```

It creates no publication request, receipt, head, ledger snapshot, or new
schema. Preserve this envelope and its field meanings; do not add a durable
no-op object. A differing path, digest, source ID, observation, or registration
proof must remain `MARKDOWN_SOURCE_CONFLICT` or the relevant source semantics
error.

## Legacy and migration dispatch

`canonical_compiler_v2.compile_pages()` performs the common preflight and owner
checks, separates modern v2 groups, validates their complete source inventory,
and delegates to the unchanged legacy compiler only when no modern group exists.
The implementation must preserve these branches:

* For a legacy-only material set, pass `head_bytes=None`, empty receipt bytes,
  empty raw/extraction/registration maps, and preserve the old compiler bytes,
  IDs, fingerprints, page paths, and refusal behavior. Legacy Docling and code
  manifests remain valid in their existing groups.
* For a mixed set, validate all v2 maps and groups as one complete prospective
  inventory, while rendering legacy groups through the old renderer. Apply the
  complete related-link set to both generations. A v1 group cannot borrow a v2
  association or locator without an explicit v2 prospective record.
* A partially populated legacy record is first checked as the current v1
  structural record. It may be migrated only through an explicit prospective v2
  group that supplies the complete association, registration, extraction,
  display, claim, event/head and output material. Do not require v2 fields from a
  record while it is still on the legacy branch, and do not let a partial record
  bypass prospective completeness once migration is selected.
* The old publication binding path must refuse a recognized version-aware record
  namespace before it skips unknown records. Otherwise a v2 primary owner can be
  missed and a partial legacy publication can appear safe. Valid v1 snapshots
  continue unchanged.

## Focused test matrix

| Area | Cases | Expected evidence or refusal |
| --- | --- | --- |
| Inventory shape | Missing/duplicate singleton; unordered entries; duplicate captured digest; filename digest mismatch; absolute, traversal, control, NFD, case-fold, Windows-device, `.git`/`.obsidian` paths; size/node/depth limits | `PROJECTION_INPUT_INVALID`, `PROJECTION_LIMIT_EXCEEDED`, or `SCHEMA_INVALID`; exact instance pointer |
| Byte map | Missing or extra path; non-`bytes` value; wrong size/hash; actual per-file/total budget overflow | `PROJECTION_INPUT_MISMATCH` or `PROJECTION_LIMIT_EXCEEDED`; no partial typed parse |
| Audit and snapshot | Empty root (audit-only); pristine ledgers with no genesis; missing head; lock, symlink, hardlink, nonregular/private-mode violation, portable collision, out-of-band file, raw orphan, directory/file replacement, changed absence slot, race during success and exception | `empty`, `RECEIPT_BOOTSTRAP_REQUIRED`, `OUT_OF_BAND_WRITE`, `AUDIT_RACE`, or `RECEIPT_CHAIN_INVALID`; retained snapshot is reverified |
| Legacy-only state | Valid v1 paper/claim/source/repo records; Docling document/parser/model/run; code and alignment manifests; no modern groups; unchanged related links | Empty v2 maps are required; `canonical_compiler_v2` output equals the unchanged v1 compiler byte-for-byte |
| Source registration | Pristine sequence-1 genesis read claims followed by the first qualifying Markdown ingest; tampered head/receipt hash, filename, intent, sequence, previous edge, claim, raw write, ledger write or target row; wrong current-vs-historical ledger snapshot | Valid proof descriptor, or `SOURCE_REGISTRATION_INVALID`; genesis read-claim exception is accepted only in its bounded sequence-1 role |
| Source inventory | Multiple associations; same source across declared labels; unknown-version same-byte reuse; changed observation; cross-paper raw/source collision; missing/orphan raw, extraction or ledger map; extraction bytes not canonical observation | Reuse/proposal, `SOURCE_PROVENANCE_VARIANT`, `SOURCE_VERSION_CONFLICT`, `SOURCE_ASSOCIATION_INVALID`, or `SOURCE_INVENTORY_INVALID` |
| Pending registration | Valid current receipt-backed state plus one exact target overlay; existing row/raw match; row-only, raw-only, path conflict, hash conflict, source-ID conflict, stale current ledger, capture transaction reuse | Prepared publication or exact `source_already_registered` envelope; conflicts remain `MARKDOWN_SOURCE_CONFLICT`; no durable no-op schema |
| Display history | Genesis, append, rollback to older association, missing predecessor, fork, cycle, wrong paper/reference, nonconsecutive sequence, stale materialized head | `derive_display_heads()` result equals supplied head; otherwise `SOURCE_DISPLAY_INVALID` |
| Claims and assessment | Complete refs/claims; duplicate primary owner/alias; unknown taxonomy; v1 chain into explicit v2 invalidation; human v2 bypass; changed evidence fingerprint without invalidation; stale/wrong assessment heads | `canonical_compiler_v2`/`derive_assessment_heads()` succeeds only for one complete connected history |
| Markdown evidence | Unicode combining characters; exact half-open spans; page-contained and cross-page spans; wrong source/association/hash/excerpt/page anchor; v1 API receiving v2 wire | Exact excerpt and mixed-v2 identity, or `MARKDOWN_LOCATOR_INVALID`; legacy v1 wire remains byte-compatible and refuses v2 |
| Mixed compiler | Legacy plus v2 groups; aliases and explicit arXiv/DOI identity; complete associations/decisions/events; source-map orphans; output path case collision; hostile frontmatter/link text; provisional page with no eligible core conclusion | Deterministic complete pages, escaped text and related links, or refusal before files are applied |
| Migration compatibility | Existing partial legacy record inspected structurally; explicit complete v2 migration; legacy-only replay; old publisher sees recognized v2 namespace | Legacy branch remains valid; migration requires complete prospective v2 material; old publisher refuses version-aware state without mutating it |

The focused tests should cover the existing fixtures and modules rather than
introduce a parallel validator: `tests/test_projection_input.py`,
`tests/unit/test_source_versions.py`, `tests/unit/test_canonical_compiler_v2.py`,
`tests/unit/test_markdown_source.py`, receipt-audit security/closure tests, and
the installed-wheel resource/module checks. Record focused results separately
from the two locked Python full suites, fresh CI, and the still-open operator,
real-source and human gates.

## Handoff completion criteria

The implementation is ready for review when it can show, against one exact
candidate snapshot:

1. the audited retained inventory and exact byte-map projection;
2. typed path dispatch with no unknown/orphan entries;
3. a valid legacy-only replay and a complete mixed v1/v2 prospective compile;
4. first-registration proof over the immutable historical snapshot and a
   separately validated pending ledger overlay;
5. exact reuse envelope behavior with no durable no-op artifact;
6. exception-path retained-lineage checks for every fixed slot; and
7. focused tests, both locked Python suites, installed-wheel parity and fresh CI
   recorded as independent evidence.

This checklist provides implementation guidance only. It does not authorize a
Vault apply, a human review decision, a real source registration, a merge, or a
claim that a local fixture is externally authoritative.
