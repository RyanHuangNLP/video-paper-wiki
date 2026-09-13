# SOURCE-PUBLICATION revision 1 — review draft

Owner: local Codex root. Git/CI owner: cursor_cli_preflight. Two existing
independent reviewers review the contract and stopped candidate. This consumes
the exact SOURCE-SEMANTICS R2 + legacy-bbox R3 implementation and accepted SOURCE
capture/preview bytes. The worktree baseline is recorded after the semantic
increment is committed. No implementation starts before the final freeze.

This increment connects the source semantics to retained Vault reads, real pinned
transaction inspection, historical preservation, typed integrity audit and backup
coverage. Research claim conversion and the explicit version-aware search catalog
are the following increments; SOURCE is not complete at this boundary.

## Authority and transport

Keep every existing v1 schema, identity, receipt and transaction format. The
existing public publication entrypoints retain valid v1 behavior. Add an explicit
source publication entrypoint; do not disguise its request as a v1 publication
request and do not inject a callable that skips prospective validation.

Extract only the existing receipt/transaction construction and pinned inspection
block into a shared internal helper in publication.py. Its inputs are the already
validated payload bytes, claimed paths, retained read bytes, audited head,
operation identity, retained Vault snapshot and retained batch session. It creates
the unchanged transaction, receipt/head and transport and returns transaction,
transaction_staging and upstream_authority. Both typed front ends perform their
own mandatory prospective validation before entering it. Existing v1 authority
envelopes and outputs remain byte-identical for unchanged requests. Existing
staging, audit, transaction and pinned adapter validators are not weakened.

The new caller retains all named ancestors of vault_root and upstream_root with
the accepted RetainedDirectory helper. One _Snapshot and audit_integrity provide
all current bytes, present/absent fixed slots and the complete managed inventory.
Every success and exception checks the staged input, transport lineage, snapshot
and named ancestors before releasing them. Python remains zero-egress; only the
existing isolated pinned read-only adapter runs a subprocess. Generated files
are written under .work/<batch>/source-publication/** and transaction-inspect/**.

## Closed request and authority

New schema `video-paper-wiki.source-publication-request.v1` has exactly:

- schema, batch_id and operation_id using the existing bounded portable names;
- kind: knowledge | registration;
- basis: {operation_head_sha256, inventory_sha256}; both SHA-256 values bind the
  current canonical head bytes and complete audited path/hash/size/mode inventory;
- payloads: sorted unique {path, content_file, sha256, size_bytes}; content_file
  equals `source-publication/content/<sha256>`;
- registration: null for knowledge, otherwise {authority, capture_result,
  ingested_at} with the exact accepted Markdown capture authority and bound
  operation-result authority, plus an actual whole-second UTC timestamp.

The request is exact canonical JSON, at most 8 MiB. It lives at the single fixed
slot `.work/<batch>/source-publication/request.json`. Content has the complete
unique digest set named by payloads; reject unsafe entries, unknown files and
directories, symlinks, hardlinks, replacement, noncanonical requests and partial
input sets. Prepare installs content before request, reuses only identical bytes,
and never overwrites a conflicting slot. All declared slots are retained before
reading or installing them; absence becomes an explicit retained precondition.
Use one retained batch session for each operation and retain it through transport
staging. No chmod/replace of an existing foreign entry.

New schema `video-paper-wiki.source-publication-authority.v1` has exactly schema,
request_sha256, request, prospective_inventory_sha256, transaction,
transaction_staging and upstream_authority. The child transaction must be
inspected, ingest, have the same operation and exact payload write descriptors,
and be identical to upstream_authority.transaction. Staging batch, operation and
bundle hash must bind the same transaction. Claimed inputs are empty for knowledge
and exactly the registered raw Markdown path/hash for registration. Request basis
must equal the authority used to construct expected hashes and read preconditions.
The authority is an inspect result, never an applied or published status.

`prepare_source_publication(*, batch_id, operation_id, vault_root, payloads,
registration=None)` audits current state, computes basis, validates the complete
prospective state, and stages the closed request. `inspect_source_publication(*,
prepared, operation_id, vault_root, upstream_root)` reopens only the fixed staged
request/content through retained descriptors, re-audits and requires the exact
basis before validation and pinned inspect. A changed basis returns
SOURCE_PUBLICATION_STALE / exit75. No caller-supplied rows or digests substitute
for current authority. The caller may provide proposed bytes only.

The receipt helper gives every existing write a before-hash, every new write an
absence expected hash, and every other audited current file a read precondition.
The head is a write precondition, never also a read. Exclude write paths from
read paths to preserve the transaction's disjoint-path invariant. The complete
receipt inventory and all unchanged source/claim/record/event/raw/derived/page
bytes used for validation are included. No-op proposals return a stable explicit
no-change result from preparation without inventing a transaction.

## One typed canonical-state collector

`source_state.collect_source_state(snapshot, audit, *, overlay=None,
require_rendered=True)` consumes the same retained _Snapshot already audited by
its caller. An overlay is a validated exact path-to-bytes proposed write map;
deletion is not supported by the current transaction format. Collect actual
bytes before overlaying in memory. This function does not read paths outside
the snapshot or open a second Vault. A returned internal state includes current
inventory, byte map, complete paper/repo/claim/event/association/decision objects,
derived assessment/display heads, compiler material and compiled pages.

Classify every entry in these exact semantic namespaces, rejecting unknown
filenames or schema versions within them:

| Role | Path |
| --- | --- |
| Source and claim ledger | `wiki/meta/ledgers/{source,claim}-ledger.json` |
| Paper record, schema v1 or v2 | `wiki/meta/records/papers/<portable-name>.json` |
| Repo record v1 | `wiki/meta/records/repos/<portable-name>.json` |
| Assessment event v1 or v2 | `wiki/meta/reviews/<clm-20hex>/<ase-20hex>.json` |
| Source association | `wiki/meta/records/source-versions/<sva-64hex>.json` |
| Display decision | `wiki/meta/reviews/source-display/<svd-64hex>.json` |
| Display heads | `wiki/meta/records/source-display-heads.json` |
| Assessment heads | `wiki/meta/records/assessment-heads.json` |
| Registration ledger snapshot | `.raw/derived/source-ledgers/<sha256>.json` |
| Markdown extraction observation | `.raw/derived/markdown-source/<raw-sha>/<observation-sha>.json` |
| Existing code/alignment manifests | unchanged projection_input v1 branches |

Association, decision, event and content-addressed derived filenames must bind
their parsed identities or byte digests. Existing v1 event bytes need not be
rewritten into a new spelling. Every new event, association, decision, head and
Markdown observation is canonical JSON. Other recognized legacy artifacts retain
their existing parsing/validation branch, including finite Docling document
coordinates. Receipt-replayed unrelated legacy paths remain opaque and immutable
in this packet, but still enter the complete inventory/basis/read preconditions.
They cannot be written through the new source request. Unknown files under the
new semantic namespaces refuse even if a generic receipt previously claimed them.

The source ledger uses the existing bounded historical projection and then the
pinned inspector's full prospective ledger validation. Validate claim ledger
against the pinned closed wire schema without changing it: schema, generated_at,
claims and each existing row's exact fields/enums. Decode each evidence wire with
the explicit v1/v2 union. Derive the stable subject from complete paper/repo
references, require one owner per claim and exact claim ID/text binding, and
require every ledger claim and assessment event to have an owner. No unreferenced
claim, duplicate primary owner, canonical alias conflict or hidden source version.
Source IDs in claim evidence must exist in the source ledger.

New `video-paper-wiki.assessment-heads.v2` is exactly {schema, heads}, where heads
is a sorted claim-ID map to {event_id, event_sha256, evidence_profile}. It is the
complete derivation from current claims and all retained events, including v1
histories (implied legacy-v1 profile), not a second assessment system. Versioned
state requires this registry and source-display-heads in the same prospective
transaction as record/claim changes. Empty maps are valid. Pure legacy state
may lack these new registries until explicitly published through this profile.

Build exact raw/extraction/registration-ledger byte maps for all associations and
call the frozen validate_source_inventory against the actual complete receipt
chain. Every stored association belongs to exactly one v2 record and appears in
that record's complete references; every display decision belongs to a stored
association. New schema namespaces cannot be silently skipped because their
parent paper is missing. Multiple version associations may share the same raw
and extraction maps according to the frozen semantics.

Historical registration snapshots may outlive current association use and are
validated by their content-addressed filenames, ledger projection and a matching
source-ledger write in the actual receipt chain. Each association's required
snapshot is mandatory. A registration operation also creates the exact ledger
snapshot of its new source-ledger write. Before any source-ledger replacement,
preserve the current ledger bytes under their content-addressed snapshot path if
that snapshot is absent. This preserves legacy registration history still
available in the current ledger. It does not manufacture missing earlier bytes;
if an association's old ledger is unavailable, publication refuses and reports
the missing digest. No substitution with a different current ledger.

Compile the complete mixed paper/code/concept set with canonical_compiler_v2.
Legacy-only groups delegate unchanged and current Markdown spans are resolved
against actual raw bytes. Code/alignment manifests remain v1 in this increment;
official Markdown-to-code evidence is the explicit CODE successor. Current
paper and code pages must have complete expected path sets and exact compiler
bytes. When require_rendered=False, return the deterministic expected pages for
proposal assembly; inspect always requires exact rendered bytes. Unchanged old
records/events/claims with unchanged related sets retain byte-identical pages.
Removal of a last taxonomy use that would require deleting a concept page is a
stable unsupported operation in this additive publisher; PRODUCT must supply a
separate retirement/recovery contract before offering such destructive changes.

## Prospective constraints and registration

All stored association, display-decision, assessment-event and derived artifact
bytes are immutable prefixes. Existing paper IDs, claim IDs/text ownership and
record paths cannot be reassigned. Retiring claims retains their record refs and
ledger/history; no current claim/event/association disappears. V1-to-v2 record
migration is explicit, preserves identity/aliases/current claim ownership and
all event bytes, and adds a real registered Markdown association. A v2 record
cannot revert to v1. Modified evidence uses the frozen v2 invalidation grammar;
display-only changes do not modify evidence or assessment state.

Knowledge requests may create/replace the source/claim ledgers, paper records,
derived heads and compiler pages, and create immutable associations/decisions/
events/Markdown observations/historical ledger snapshots. They cannot create raw
capture bytes, create a repo/code mapping, write gates, or alter receipt history.
All references are resolved from the current plus proposed complete state.
Existing source rows cannot disappear or change origin/hash identity. Source
registration is a distinct request kind, rather than an arbitrary source-ledger
patch disguised as a knowledge proposal.

Registration requires the exact generic capture result already bound by
markdown_source._capture_proof and actual retained raw bytes/mode. The capture
transaction has receipt=null, head=null and no claims. It introduces exactly one
new source ledger row with the accepted Markdown admission fields and no edits
to other rows. It claims exactly the previously unclaimed raw path, writes the
source ledger and its new immutable snapshot, and preserves the previous ledger
snapshot if absent. It never creates associations, display choices, claims or
pages. Registration into an existing version-aware Vault must use this explicit
profile and validate the current complete typed state as well.

Add `publication_profile="legacy-v1"|"source-v1"` to the existing Markdown
admission API and `--publication-profile` to its CLI, default legacy-v1. The
source-v1 branch delegates the exact validated capture material to the new
registration front end while retaining the original caller/source guards.
Existing legacy calls keep valid behavior; their publication inspect now refuses
recognized version-aware state with SOURCE_PROFILE_REQUIRED / exit75. Direct
legacy publication payloads introducing v2 records/new namespaces also refuse.
The legacy catalog collector must likewise return SOURCE_PROFILE_REQUIRED before
filtering new namespaces. Do not modify frozen base-catalog schemas or resources.

## Entry points, errors and validation

Engine CLI: `vpwiki source-publication prepare --proposal <file> --batch-id
<id> --operation-id <id> --vault-root <path>` and `inspect --prepared <file>
--operation-id <id> --vault-root <path> --upstream-root <path>`. Proposal is a
closed {schema: video-paper-wiki.source-publication-proposal.v1, payloads,
registration}, with payloads as sorted {path, content_file} entries pointing to
digest-named sibling content files. It is an external-input transport only,
retained with its complete content set; prepare computes hashes, basis and
identity. Keep the same fixed source-publication input directory grammar and
never follow caller paths outside it. Audit is `vpwiki source-publication audit
--vault-root <path>` and returns derived state/basis/heads/coverage counts only.

New public wrappers convert parser and filesystem failures into ContractError
with an instance_pointer. Stable failures: SOURCE_PUBLICATION_INVALID / exit2
(shape, paths, payload or mirror mismatch), SOURCE_PUBLICATION_STALE / exit75
(changed basis), SOURCE_PROFILE_REQUIRED / exit75 (legacy entrypoint),
SOURCE_HISTORY_CONFLICT / exit75 (immutable prefix/identity reassignment),
SOURCE_PUBLICATION_UNSUPPORTED_CHANGE / exit75 (unsupported deletion), and
WORK_PATH_UNSAFE / exit2 (retained named lineage or staged set changed). Preserve
specific SOURCE-SEMANTICS, audit, transaction and pinned adapter codes. Shape
and calendar validation precedes identity/graph binding; all exits recheck I/O.
Bounds: at most 1022 payload paths, 64 MiB per business file, 128 MiB total proposed
bytes, 8192 receipt history entries, and the existing transaction transport
read/bundle limits. Reject before allocation/staging when declared bounds fail.

Required evidence: actual capture -> generic fixture apply -> source registration
inspect -> fixture apply -> association/knowledge proposal -> inspect -> fixture
apply -> typed audit; subsequent import with unchanged display; supplied fixture
choice and rollback; immutable prefix and missing historical bytes refusals;
legacy-only and mixed paper/code cases; stale request/head/basis, hidden names,
case aliases, symlink/hardlink and ancestor/content replacement at success and
exception barriers; installed CLI entrypoints and packaged schemas. Use existing
fixture operator helpers, never real Vault/admin. Backup/isolated restore must
cover all new namespaces byte-for-byte and typed audit must agree after restore.
Run appropriate focused suites, both locked full suites, wheel byte checks and
fresh four-job exact-head CI. No human provenance, review or operator gate is
closed by synthetic evidence.
