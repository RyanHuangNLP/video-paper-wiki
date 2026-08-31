# Canonical projection inputs — review draft 2

Status: NOT FROZEN. Architect design for VPKB-000-projection-contracts at
`208c206801214bb8f6e2f58f995ad7755ce87332`; no implementation release. The
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

The sole normative codec specification is now the separately frozen
[ledger locator wire contract revision 1](ledger-locator-v1.md), SHA-256
`493fc3d135141512c7956f3729726ae72febbb1a34cc8cd5669add96af16e191`.
Its four pure APIs are in `video_paper_wiki.ledger_locator`. It uses the existing
upstream evidence locator string, preserves full common PDF/code locator fields
through integer-only canonical wire, and maps project uncertain to wire context.
No second ledger, source-ID implementation or upstream property is introduced.

That bounded codec release does not freeze this document's canonical inventory,
artifact closure, history, source application profile or generation design. The
previous duplicate draft wire text is superseded by the standalone contract;
future edits here cannot silently alter its frozen semantics. Public transport
proof is not validation of genuine coordinates, complete artifacts or approval.

## Whole-snapshot input boundary to freeze

The proposed root is `video-paper-wiki.projection-input.v1` with exactly
`schema,entries`. Each entry has exactly `path,kind,sha256`, in canonical path
order, unique and collision-safe. A separate exact built-in `bytes_map` has
exactly the same keys and supplies immutable bytes matching every entry SHA.
Documents are parsed only from those bytes; a caller cannot supply a different
parsed document next to an honest hash. Raw byte hashes remain distinct from
semantic runtime comparison hashes.

Kinds include source/claim ledger, paper/repo record, assessment event,
taxonomy, immutable run/code/alignment manifests and referenced artifact bytes.
The exact path/cardinality/closure table and limits are pending review. There
must be exactly one of each fixed ledger and taxonomy. Do not invent an active
alignment version: repo-record
currently has no canonical selector; retain manifest-qualified versions.
Event files remain `wiki/meta/reviews/<claim_id>/<event_id>.json`.

### Input namespaces and filename direction

The proposed path key is a logical input address, not an instruction to read
every key relative to a Vault. Reserve `taxonomy/v1.json` solely for kind
`taxonomy`, supplied from the deployed project configuration/package. All
Vault input kinds instead have `.raw/` or `wiki/meta/` paths under their released
families. These domains are disjoint; do not install another live taxonomy
under the Vault or treat taxonomy YAML as an independent machine authority.
The later adapter must obtain the right provider's exact bytes; the pure API
only verifies the supplied bytes/hash. Current packaging does not include
taxonomy, so deployment/resource binding still needs its explicit implementation
release and installed-wheel test. This draft does not silently add a resource.

Source and claim ledger paths are the pinned upstream exact constants:
`wiki/meta/ledgers/source-ledger.json` and
`wiki/meta/ledgers/claim-ledger.json`. Paper/repo record files use the respective
`wiki/meta/records/papers/` and `wiki/meta/records/repos/` families. Their
canonical IDs are embedded fields, not filename identities. A final input
profile may admit an opaque portable JSON basename while requiring exactly
one document per embedded ID; it need not create a new hash-based paper ID
or accept a duplicate record under another name. Generated page naming and
rename/publication behavior must be explicit in the later compiler contract.

Assessment events already have an exact content-bound filename and remain
the exception to opaque record names: directory claim_id and basename event_id
must agree with validated event fields. Immutable code/alignment/run artifacts
still need exact path families and association rules. A document placed under
replaceable `records/` is not immutable just because its schema says manifest;
its publication constraints must be established before release.

Revision 2 withdraws draft 1's proposed mutable `wiki/meta/reviews/heads.json`.
Architect, Builder and Steward verified that the existing requirements call
for a unique event-chain head, not a separate persisted assessment registry.
The frozen facade makes all review files create-only; membership in its managed
prefix never authorized replacing a head file. No facade exception or new
registry is introduced. Derive each head from the complete validated event
graph below. `assessment_heads` is a derived catalog relation, not an inventory
kind or a new authority. Operation and human-gate registries remain separate
and unchanged; do not borrow their schemas or publication permissions.

Cross-object rules to freeze include all source/owner/ref FKs; canonical claim
ID re-computation from owner subject and actual ledger text; no duplicate
ownership or supersedes cycle; taxonomy membership; full tagged locator/source
bindings; current and historical manifest/artifact path/hash closure; active
extraction binding. Raw source identity recomputation and source freshness
remain pinned-upstream adapter checks, not a copied private implementation.

### Manifest hashes are different kinds of evidence

The inventory entry SHA always hashes exact complete file bytes. It is not a
runtime comparison hash or a self-excluding identity hash. Keep these separate
from all embedded hashes and preserve optional field presence without defaulting.

| Existing run-manifest field | Snapshot treatment direction |
| --- | --- |
| input_hashes.source_sha256 | Must resolve to captured raw bytes for a supported extraction binding |
| input_hashes.parser_config_sha256 | Must resolve to exact immutable config bytes in that binding |
| input_hashes.model_manifest_sha256 | Must resolve to the small immutable model-manifest bytes; not a claim that model weight files were fetched or authenticated |
| output_hashes.document_json_sha256 | Must resolve to exact immutable document bytes before that run can support an active extraction or PDF locator |
| input_hashes.ingest_plan_sha256, input_hashes.prepared_sha256 | Retain existing canonical-object hashes as provenance; do not import staging documents as business-fact inputs |
| output_hashes.draft_sha256, output_hashes.receipt_sha256 | Retain existing canonical-object hashes as provenance; do not derive facts from drafts or claim receipt-chain authentication |
| pipeline_fingerprint | Recompute the existing bound engine/version/core/config/model identity when required material is present; it is neither raw run-file SHA nor projection generation |

Current run-manifest schema permits empty input/output hash maps and optional
pipeline_fingerprint. A successful-extraction application profile must explicitly
require all needed bindings; the base schema alone cannot prove them. Failed or
unbound historical run policy, precise config/model/document path association,
and deterministic selection remain open. Do not pick a run by timestamp or use
the first file with a matching digest. All canonical timestamps stay material.

An inspected code manifest has three distinct digests: its complete file SHA,
proposal_sha256 for proposal material, and manifest_sha256 excluding its own
field. Its capture/source/payload association must use the frozen supplied-byte
code checks. Multiple logical repository/commit/path origins may share raw
bytes; never collapse them to one origin keyed only by source_id. An inspection
approval hash or nullable capture operation_id is preserved provenance, not
permission or proof of a successfully authenticated capture.

## Immutable extraction layout and acyclic publication proposal

This section records the next Architect proposal, NOT a frozen release. The
independent path/source review confirmed that broad existing schemas permit the
layout but do not already enforce it. Old prepared fixtures with a literal `fp`
directory are not proof of the new directory-to-fingerprint relationship.

Use the existing planned source/pipeline organization, with exact names to review:
`.raw/derived/<raw-pdf-sha256>/docling/<pipeline-fingerprint>/document.json`,
`parser-config.json` and `model-manifest.json`; put timestamped run records in
`.raw/derived/<raw-pdf-sha256>/runs/<run-id>.json`. Run IDs are filenames, not a
selection order. Every qualifying run's source/config/model/document hashes and
pipeline fingerprint must resolve within that source/pipeline binding. Preserve
all runs and extraction versions; paper.active_extraction selects a document,
not a latest run. Multiple qualifying runs for identical bound bytes do not
collapse run facts. Exact immutable path reuse requires identical bytes; different
document bytes for one source/pipeline must be refused as nondeterministic, never
overwritten. These are new application constraints, leaving old schema/identity
and prospective API admission unchanged.

Keep the already-frozen five-field pipeline identity. Bind the vpwiki canonicalizer
and document schema versions, exact serializer settings and relevant implementation
identity inside the versioned canonical parser-config bytes; their raw SHA already
participates in the existing pipeline tuple. The complete config/model manifest
schemas and byte serialization still need release. Do not add undocumented keys
to the old identity tuple or assert that package version 0.1.0 alone identifies a
canonicalizer implementation. Actual software/resource collection and model-weight
verification remain future adapter responsibilities.

A canonical successful-extraction run profile should contain only its forward
source/config/model/document bindings, required pinned parser versions, pipeline
fingerprint, timestamps and error_code=null. An explicit narrow input/output-key
profile can omit the optional staging/provenance hashes; this is preferable to
inventing zero hashes or rehashing an already immutable run. In particular:

- A prepared object may list the run_record's complete-file SHA. That same run
  cannot also require the SHA of that prepared object: doing so creates a hash
  cycle. Construct the extraction run before the prepared wrapper and omit
  run.input_hashes.prepared_sha256 in this profile.
- A publication receipt hashes the full run file among business writes. The run
  cannot contain the hash of that same publication receipt. Omit its
  output_hashes.receipt_sha256; the separate receipt/audit chain binds publication.
- A draft that depends on that prepared object must not feed a draft hash back
  into the already referenced extraction run. A later immutable provenance
  record may refer to already existing artifacts only after its own acyclic
  publication profile is defined; this draft does not authorize that extra type.

The existing base run schema remains broader. Whether canonical historical
failure/provenance runs receive a separate input kind/profile, or are explicitly
outside the first closed corpus, must be decided before inventory freeze; never
silently drop them or claim all schema-valid runs satisfy this extraction profile.
No run under create-only `.raw/derived/**` may be retroactively edited to attach an
apply result; frozen facade publication there remains ingest-only.

Code and alignment manifests also need immutable derived families, qualified by
their full stored-file SHA to avoid collapsing distinct origins or versions.
That filename digest must not be confused with a code manifest's self-excluding
manifest_sha256/proposal_sha256, raw payload hash, normalized whole-text hash or
snippet hash. A parent publication receipt can hash the completed manifest file;
feeding that file's self hash back into its capture approval graph is a different,
forbidden dependency. Exact families and current-alignment selection remain open.
The existing single-current prospective slots must not be used to reject all
historical extraction/commit versions in this complete inventory.

## Ledger application-profile design notes

The pinned `claude_obsidian/ledgers.py` validates more than field shapes and
permits some omitted optional values and additional fields. Do not call a new
closed project profile an equivalent replacement for its public validator.
Root has read source revision 9f8c119, including generated timestamps, source
identity/date/freshness checks and claim risk/contradiction/anchor checks. A pure
snapshot profile must explicitly separate the following concerns:

- Preserve both ledgers' `generated_at` as canonical input, even for empty
  ledgers; it is not a runtime volatile timestamp. Pinned ledger generation uses
  whole-second UTC, whereas project assessment events allow 1..9 fractional
  digits. These grammars must not be conflated.
- Source rows contain origin kind/locator, content_kind, title, authority,
  review_status and ordered pages. Existing optional nullable values include
  content_sha256, ingested_at, retrieved_at, refresh_due, independence_key and
  supersedes. A final profile must explicitly require or preserve presence for
  each; `record.get` in upstream is not permission for the catalog to collapse
  absence and null. Unknown extension fields must be preserved under an exact
  released encoding or refused, never silently dropped.
- Claim rows contain text, risk, assessment, confidence, location and evidence.
  Existing location.anchor, reviewed_at, notes and supersedes may be omitted
  or nullable under the upstream implementation. The new history binding
  deliberately requires reviewed_at explicitly; whole-input admission must
  state whether this closes the ledger profile to explicit presence rather
  than inventing null. Generated page/anchor existence is a later comparison
  against compiler output, not an invitation to read Markdown as canonical facts.
- Source supersedes and claim supersedes need complete FKs and acyclic graphs;
  source identity recomputation still belongs to the pinned public adapter.
  Retention does not follow solely from current claim references: all declared
  historical immutable artifacts and events must remain in the full inventory.
- Source freshness, future-dated source observations and accepted high-risk
  independent-support requirements involve an audit date and upstream policy.
  A clock-free catalog digest does not certify them. Do not inject today's date
  into generation, silently re-implement source grouping, or infer scientific
  claim assessment from this structural validator. The later public validation
  result must name its explicit audit context separately from the timeless
  canonical row export.

The closed corpus's raw-file policy remains a decision to freeze: file-origin
sources need supplied bytes even when unreviewed/superseded/rejected, while
URL/manual metadata may not have captured bytes. A PDF/code locator can qualify
only through an explicit source/artifact binding; an HTTPS URL, source title,
manual origin or matching file basename cannot prove captured PDF/code content.
Do not narrow all legacy source origins implicitly merely to make current
fixtures pass, or claim this draft establishes migration compatibility.

## Historical assessment validation direction

The pure complete-event-graph behavior is now separately frozen in
[assessment-history revision 1](assessment-history-v1.md), SHA-256
`ff7e7830d9931c52c447a2a95818dca091cb6d5bc97184d1be1103072ecf44cb`.
Its transient claim bindings do not replace the inventory/owner/byte adapter
still required here. The following historical design direction is subordinate
to that frozen API; the complete input contract remains NOT FROZEN.

Whole-snapshot history cannot reuse the current prospective helper unchanged:
it compares every event fingerprint with the current evidence. Historical
events before a legitimate invalidation must retain their historical value.
Reuse the existing event schema and ID algorithm, then validate the whole
graph separately, without changing the old per-proposal API silently.

For each owned claim, including retired claims, require one genesis, one
connected acyclic nonforking chain, no dangling/cross-claim predecessor and
exactly one terminal head. Traversal from genesis must visit every supplied
event for that claim; a unique visible terminal alone does not exclude a
disconnected cycle. Reject events for unknown claims and claims without events.
Derive the terminal from the graph, never directory order, event-ID sorting,
timestamps, a caller-selected head or the ledger's asserted assessment.
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

The snapshot can prove the supplied chain state, not complete Vault enumeration
or that a missing tail plus an older matching ledger is not a rollback. VPKB-001
must authenticate event membership/current bytes through receipt and managed
content auditing. The snapshot also cannot prove that invalidation and human review
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
