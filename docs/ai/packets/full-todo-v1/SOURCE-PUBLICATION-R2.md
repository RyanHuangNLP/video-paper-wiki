# SOURCE-PUBLICATION revision 2 — implementation contract review

This supersedes the R1 review draft without altering it or either independent
review. Local root owns implementation, cursor_cli_preflight owns serialized Git
and CI, and the two existing independent reviewers review stopped source. Use the
exact SOURCE-SEMANTICS integrated candidate after its delivery as the recorded
baseline. Freeze this revision and its allowlist before implementation. SOURCE
also requires the later research conversion and source catalog increments.

## Shared authority boundary

Keep existing v1 receipt, head, transaction, pinned adapter, publication authority
and schema bytes. Extract only publication.py's existing receipt/transaction
construction and pinned inspection block into a shared internal helper. Inputs
are validated payload bytes, claim paths, retained read bytes, audited head,
operation identity/type, retained snapshot and retained batch session. The helper
returns transaction, transaction_staging and upstream_authority. Both front ends
must validate their full prospective state before calling it; no optional
validation callback or global replacement. Old valid v1 requests retain their
existing output semantics and bytes.

All new Vault entrypoints retain every named ancestor using RetainedDirectory,
then use one _Snapshot for audit, inventory, current bytes and absent write slots.
Inspection also retains upstream ancestors. One retained batch session spans
source input reads and transaction staging. On success and every exception,
verify the input complete set, held file contents/identities, named ancestor
edges, batch lineage and snapshot before releasing descriptors. Outer guards
also cover failures during initial/repeated enumeration. Agent execution remains
zero-egress; only the existing isolated pinned inspector subprocess is allowed.
No real Vault mutation, vpwiki-admin, human gate closure or PDF Git artifact.

Require an existing receipt-backed generic genesis. Missing/headless state
returns RECEIPT_BOOTSTRAP_REQUIRED, never a null-head source request. Public typed
audit proves local receipt replay and typed consistency; it does not claim a
fresh upstream ledger validation or operator apply.

## Exact inventory binding

Let I be `_walk_inventory(snapshot, read_bytes=True)`, after audit_integrity using
that same snapshot. It includes all selected current business files, captured
raw bytes including unclaimed captures, all receipts, operation head and gate
head. It excludes directories, ephemeral/projection files and packaged taxonomy.
Directories and absent slots remain independently retained I/O preconditions.
For each I path produce `{path, sha256, size_bytes, mode}` with integer permission
mode from stat.S_IMODE, and sort paths by UTF-8 bytes. `inventory_sha256` is SHA-256
of canonicalize(the resulting array), with no terminal LF. The basis is exactly
`{operation_head_sha256: SHA256(actual head bytes), inventory_sha256}`; both are
nonnull lowercase SHA-256 strings. It is computed from actual bytes, not caller
descriptors or projection caches.

The prospective inventory uses that same array domain, overlaid with all
effective business writes: retain mode on replacement and use 0600 on creation.
Existing head/receipt entries remain unchanged in this calculation; it describes
business state immediately before the new receipt/head advance, avoiding any
circular request hash. New receipt/head bytes are bound separately by the
transaction. This formula is used in prepare, durable request and inspect.
Every source request field and prospective byte digest must be rederived in
inspection. A different current basis returns SOURCE_PUBLICATION_STALE/75.

Every existing business write has exact original bytes/hash/mode, every new write
has a retained absence precondition. Every other I file is a read precondition,
including all old receipts. Exclude ALL transaction write paths (including head)
from read paths. Old source-ledger bytes are bound by its write expected hash,
never by a colliding read. Claimed inputs are a separate subset of read paths:
empty for knowledge, exactly the admitted raw Markdown for registration. Reject
over-limit complete read/bundle sets with TRANSACTION_LIMIT_EXCEEDED; never drop
entries to fit. After shared-helper construction, independently compare its
business write descriptors to the exact request payload set and the computed
prospective map. The pinned transaction and upstream_authority.transaction must
be identical and bind the same ledger bytes.

## Four closed schema resources

Add exactly these packaged schemas and valid fixtures, with semantic dispatch
in contracts.validate_document and runtime schema enumeration/wheel parity:

* `video-paper-wiki.source-publication-request.v1`
* `video-paper-wiki.source-publication-authority.v1`
* `video-paper-wiki.source-publication-proposal.v1`
* `video-paper-wiki.assessment-heads.v2`

Request has exactly schema, batch_id, operation_id, kind, basis,
prospective_inventory_sha256, payloads and registration. IDs use existing batch
and operation portable grammar. kind is knowledge or registration. payloads are
strictly UTF-8-path-sorted unique `{path, content_file, sha256, size_bytes}` entries;
content_file is exactly `source-publication/content/<sha256>`. registration is
null iff kind is knowledge, otherwise exactly `{authority, capture_result,
ingested_at}`. The two authorities use existing Markdown-capture and generic
operation-result contracts; ingested_at is an actual whole-second UTC timestamp.
Request bytes must equal canonicalize(request).

Authority has exactly schema, request_sha256, request,
prospective_inventory_sha256, transaction, transaction_staging,
upstream_authority. Both prospective hashes agree. Request hash binds its exact
canonical bytes. The transaction is inspected ingest with the request operation,
the exact business payload set, matching claims and unchanged receipt/head
grammar. Staging batch/operation/bundle and upstream authority bind that same
transaction. No applied or published flag is added to authority.

External proposal has exactly schema, kind, payloads, registration, with the same
kind/registration union. It uses the fixed external layout
`<caller-root>/source-publication/proposal.json` and sibling `content/<sha256>`.
Each payload is exactly `{path, content_file}`, where content_file is the relative
`content/<sha256>` spelling. Digest comes from this name and actual bytes; no
arbitrary caller file paths. Payload paths are sorted unique, and the content
directory has exactly their unique digest filenames, including zero entries for
empty payloads. Parent has exactly proposal.json and content. Retain original
caller spelling and every named ancestor; reject dot/dotdot, links, unsafe names,
hardlinks, case aliases and excess entries before normalization can hide them.
External proposal JSON is canonical. It is input only and never authority.

Assessment heads is exactly `{schema, heads}`, with a claim-ID-keyed object.
Each value is `{event_id, event_sha256, evidence_profile}`. Derive from the full
current claim/event inventory using assessment_history_v2; event_sha256 is the
hash of actual stored event bytes, preserving legacy spelling. V1 events imply
legacy-v1; v2 uses its declared profile. No orphan/missing head. Empty map is valid.

## Public API and staging

`prepare_source_publication(*, batch_id, operation_id, vault_root, payloads,
registration=None)` accepts only a path-to-exact-bytes payload map and supplied
registration metadata. Derive kind from registration, audit current state,
validate proposal shape/calendar/byte limits, calculate the effective writes and
complete prospective state, then stage. It does not run the upstream inspector.
`prepare_source_publication_source(*, proposal_path, batch_id, operation_id,
vault_root)` retains the exact external layout and delegates with parsed bytes.
`inspect_source_publication(*, prepared, operation_id, vault_root, upstream_root)`
accepts only the fixed staged request path, validates it and all retained content,
re-audits basis, fully revalidates prospective state, then invokes the helper.
No-change envelopes cannot be passed as prepared paths.

Stage at `.work/<batch>/source-publication/{request.json,content/<sha256>}`.
Retain present OR absent fixed request/content slots before first read/install.
Only request.json and content are permitted under source-publication. Complete
content set equals the request digest set; each file is private, regular, single
linked and digest-correct. Install content before request using the accepted
retained-session create/reuse protocol, never overwrite conflict or chmod foreign
files. Retain all generated and input edges through final/exception verification.

Successful preparation returns exactly `{state: "source_publication_prepared",
kind, batch_id, operation_id, basis, prospective_inventory_sha256, request_path,
request_sha256, changed_paths, published: false, applied: false,
next_action: "inspect_source_publication"}`. request_path is the fixed absolute
path, changed_paths sorted business writes. It is a nondurable CLI/API envelope;
the staged request is the durable schema document.

Drop supplied writes whose bytes are already identical only after validating
their allowed roles and immutable-prefix constraints. Validate the entire final
state before deciding no-op. For an empty effective knowledge map return exactly
the same envelope with state and next_action `no_change`, request_path and
request_sha256 null, changed_paths [], both status booleans false. Do not stage,
invent transaction authority or advance a timestamp. Identical input on unchanged
state returns identical envelope. Registration cannot use this knowledge no-op;
already-registered admission retains its existing explicit result below.

CLI adds `vpwiki source-publication prepare --proposal --batch-id --operation-id
--vault-root`, `inspect --prepared --operation-id --vault-root --upstream-root`,
and `audit --vault-root`. Audit returns exactly `{state: "source_state_audited",
basis, profile, counts, assessment_heads, display_heads,
receipt_backed: true, upstream_validated: false}`. profile is legacy-v1 or
source-v1. counts is `{files, papers, repos, claims, events, associations,
display_decisions, ledger_snapshots, compiled_pages}` with nonnegative integers.

## Complete retained typed collector

`collect_source_state(snapshot, audit, *, overlay=None, require_rendered=True,
pending_registration=None, allow_legacy_structural=False)` is internal, using
only that audited snapshot and a validated exact write map. No second Vault read
authority. It returns current/prospective inventory and bytes, all typed records,
claim owners, events, associations/decisions, derived heads and compiler pages.

Recognize and validate every path in these namespaces, including all filenames:
source/claim ledgers; `wiki/meta/records/papers/<portable>.json` (v1 or v2),
`.../repos/<portable>.json` (v1); `wiki/meta/reviews/clm-<20hex>/ase-<20hex>.json`
(v1 or v2); `wiki/meta/records/source-versions/sva-<64hex>.json`;
`wiki/meta/reviews/source-display/svd-<64hex>.json`; records/source-display-heads.json;
records/assessment-heads.json; `.raw/derived/source-ledgers/<sha256>.json`;
`.raw/derived/markdown-source/<raw-sha>/<observation-sha>.json`; and recognized
legacy code/alignment/run/parser artifacts via their existing contracts.
Association/decision/event filename IDs bind parsed IDs. New JSON artifacts must
be canonical. Legacy event bytes remain unchanged, including their old spelling.
Existing legacy locator branches admit finite bbox coordinates only in the
accepted contextual slots. Unknown schema/version/filename in these semantic
namespaces refuses. Receipt-replayed unrelated legacy namespaces remain opaque,
immutable and fully included in basis/read conditions. They are not writable.

Use historical_source_ledger for the closed local source-ledger projection. For
claims define a closed local projection (not an upstream JSON schema): root is
schema/generated_at/claims, discriminator claude-obsidian.claim-ledger.v1.
Each row has text/risk/assessment/confidence/location/evidence, with optional
reviewed_at/notes/supersedes. Exact fields and enum/calendar/null semantics must
match the existing pinned field validators; new local closure rejects extras.
Risk is normal|high, assessment accepted|provisional|contested|unsupported|
deprecated, confidence high|medium|low|unknown. reviewed_at is absent/null or an
actual ISO date (accepted requires a date), notes absent/null or text, supersedes
absent/null or a safe clm identifier. Location is `{path, anchor}` in this local
profile for paper claims (upstream allows omitted anchor). Require `clm-<20hex>`
ID = claim_id(stable owner, exact canonical text), path the owner's canonical
page and paper anchor `^<claim-id>`. Existing v1 repository claims retain the
pinned optional/null/text anchor spelling: the unchanged v1 code renderer has
no claim block anchors. Knowledge cannot add repository refs or claims, and the
CODE successor will own new capability rendering. The pinned inspector still
checks any declared nonempty repo anchor against actual prospective code bytes.
Decode each evidence entry with the accepted v1/v2 union; relation is preserved.
Paper section_claim_refs and repo capability_claim_refs establish exactly one primary owner for
every ledger claim. Every event has that owner; every evidence source is in the
ledger. Stable subject is `paper:<paper_id>` or `repo:<repo_id>` accordingly.
No primary/alias conflict, orphan claim/event or hidden association/decision.
Pinned validation is a separate mandatory inspect step with its full source
freshness, active-review and accepted/high-risk rules; local typed audit does not
claim it ran that subprocess.

Build all legacy code groups using exact manifest/repository/commit/alignment
links; reject ambiguous/orphan records, not select the first match. Full mixed
compiler input comes from actual paper records, claims, events, association and
decision groups, code groups, and packaged taxonomy concept_items_for_papers.
Compile with canonical_compiler_v2 using exact raw/extraction/ledger maps for
associations. Pass only association-required subsets to validate_source_inventory;
it demands exact map sets, and for zero associations takes null head/empty
receipts. Separately replay and validate the actual complete receipt chain and
all historical snapshot extras. Code officiality remains the existing v1 branch.

All stored associations appear exactly once in the owning v2 record; all stored
display decisions resolve a stored association. Derived display heads and
assessment-heads.v2 must exactly equal stored registries in source-v1 state.
Current generated paper/code/concept path sets and bytes exactly match complete
compiler output. require_rendered=False allows the internal assembler to return
expected pages/heads before those mirror writes exist, but does not skip identity,
history, locator, source or claim validation. Inspection requires rendered true.

An actual v2 paper, v2 assessment event, association, display decision, or either
new derived-head registry triggers source-v1 full validation. Registration ledger
snapshots and Markdown observations alone do not trigger it. For pure legacy
state, allow_legacy_structural=True validates all shapes, source/claim ownership,
receipt replay and immutable objects but permits existing provisional v1 record
material that cannot yet compile. Only current-state inspection for explicit
knowledge migration and source registration can use that internal mode. Knowledge
prospective state must fully compile and contain both new heads (including empty
maps); registration validates the unchanged legacy structural graph. Typed public
audit requires full rendered state and refuses incomplete legacy projections.
Already version-aware current state must be fully valid before any overlay.

## History preservation and prospective restrictions

Stored event/association/decision/observation/ledger-snapshot bytes are immutable
prefixes. Preserve existing paper/claim identities, claim text, ownership, record
paths, refs (including retired), aliases and prior history. A paper v1->v2
migration preserves identity/aliases/refs and adds an actual registered Markdown
association. No v2->v1. Claim evidence changes must obey v2 invalidation; display
changes cannot silently rewrite evidence. New human decisions/events must be
explicit supplied material; no default selection or automatic human acceptance.

Historical source-ledger snapshots use their exact byte-hash filename and closed
projection. A snapshot is valid when its digest matches a source-ledger write in
the actual chain OR a pristine source-ledger claim in the sequence-1 generic
genesis. Arbitrary later read claims are insufficient. Association registration
continues to require the frozen first ingest write proof; a genesis snapshot
does not manufacture a registration. Before replacing source ledger, preserve
its actual current bytes under their snapshot path if absent. Each registration
also writes its exact new ledger snapshot. During registration prospective
validation only, this one new digest may lack an actual-chain write: the internal
pending_registration context must bind the independently validated capture proof,
raw bytes, sole added source row, proposed ledger bytes and matching snapshot.
No new association may use this exception. After fixture/operator apply, ordinary
typed audit requires actual-chain proof. Never substitute a later current ledger
for missing historical bytes; refuse and name the unavailable digest.

Knowledge may write source/claim ledgers, paper records, derived heads and exact
compiler pages, and create immutable associations/decisions/events/observations/
ledger snapshots. No raw capture/repo/code mapping/gate/receipt mutation. Source
row IDs cannot be added or removed. Preserve each row's origin/content_kind/
content_sha256/ingested_at identity; other existing allowed metadata may change
only as explicit proposed bytes, without automatically promoting review status.
New or changed source pages are an explicit unique sorted set of existing
canonical paper/code pages; each new/changed record/evidence owner using a source
must occur in that source's pages. Unchanged legacy row page order and existing
links retain their prior validated spelling. Unused source rows can retain
existing page links. All changed source
ledger bytes require preserving the old snapshot. Other rows/fields continue
through local and pinned validation. This supports an explicit reviewed proposal
without conflating new registration with knowledge editing.

Registration requires actual raw bytes/mode plus markdown_source._capture_proof;
capture transaction is capture with null receipt/head and no claims. Distinct
batch/operation from capture are mandatory. Add exactly one accepted admission
row, change only generated_at and that added row, claim exactly its previously
unclaimed raw path, write new source ledger/snapshot and preserve old snapshot
if absent. No associations, choices, claims or pages. Recompute expected ledger
and exact effective payload set; caller-provided registration payloads must equal
it. Prepare automatically adds the required old/new ledger snapshots from actual
and proposed bytes; if a caller also supplied that path, its bytes must be exact.
Inspect requires this complete snapshot set explicitly in the durable request;
it never repairs a deficient request. Knowledge prepare likewise automatically
adds the old ledger snapshot before a proposed source-ledger replacement.
A source profile registration works in both legacy and fully valid source
state without changing the existing typed graph.

Add publication_profile legacy-v1|source-v1 to Markdown admission and its CLI,
default legacy-v1. Source branch keeps all original caller/capture/ancestor
guards and delegates validated material to prepare+inspect registration. It
returns the existing source_registration_prepared envelope plus
publication_profile:source-v1, with publication_request and publication_authority
holding the new envelope/authority. Already-registered source branch audits typed
current state and returns existing source_already_registered fields plus profile;
it needs no new capture result. Existing legacy output fields stay unchanged.

Before legacy publication validation or catalog filtering, detect actual v2
records/events and all new source namespaces (including snapshots/observations)
and return SOURCE_PROFILE_REQUIRED/75. Legacy publication also rejects payloads
introducing them. Do not mutate base-catalog schema or silently return a partial
catalog. A source-aware catalog is the next explicit increment.

Deletion remains unsupported. Complete page-set comparison detects a last
taxonomy use removal requiring concept deletion and returns
SOURCE_PUBLICATION_UNSUPPORTED_CHANGE/75 before staging. PRODUCT must supply a
separate retirement/recovery path; do not silently leave stale pages.

## Errors, limits and acceptance

All wrappers translate malformed JSON/UTF-8, calendar and filesystem failures to
structured ContractError with instance_pointer. Precedence: input type/shape and
declared limits, calendar, identity binding, actual audit/basis, immutable history,
complete graph/locators/mirrors, staging, pinned inspection. At every exit, final
I/O checks override with the observed race error when lineage changed. Preserve
existing specific semantics/audit/pinned codes. New codes are
SOURCE_PUBLICATION_INVALID/2, SOURCE_PUBLICATION_STALE/75,
SOURCE_PROFILE_REQUIRED/75, SOURCE_HISTORY_CONFLICT/75,
SOURCE_PUBLICATION_UNSUPPORTED_CHANGE/75 and WORK_PATH_UNSAFE/2.

Request/proposal max 8 MiB; max 1022 effective business paths; each max 64 MiB and
total proposed bytes max 128 MiB; history max 8192 receipts; existing transaction
read/write/bundle limits also apply. Apply bounds to declared AND actual content
before staging. Retain source-semantics contextual parser bounds and canonical
JSON without admitting floats in unrelated fields.

Required tests cover actual generic fixture genesis -> capture -> fixture apply
-> source registration inspect -> fixture apply -> full association/knowledge
publication -> fixture apply -> typed audit, plus later registration with display
unchanged and explicit fixture selection/rollback. Test snapshot genesis/write/
pending branches, absent-history refusal, immutable prefix, old/new record
migration, legacy mixed code, no-op retry, stale basis, exact write/read sets,
unknown/alias/link paths and success/exception replacement barriers. Validate
backup/isolated restore byte coverage of every new namespace and rerun typed
audit after restore using existing synthetic operator helpers. No real gate is
closed. Finish focused independent probes, both locked full suites, installed
modules/69-schema byte checks and fresh four-job exact-head CI.
