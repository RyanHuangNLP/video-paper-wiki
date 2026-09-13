# SOURCE-CONVERSION R1 — lightweight record to canonical publication

This contract is effective only with SOURCE-CONVERSION-freeze-r1.json, which
binds its exact bytes, allowed paths and the delivered source-publication base.
Root owns local implementation under LOCAL-CODEX-OWNERSHIP-R2. Existing
assistants independently review code and handle serialized delivery. No external
Builder, real Vault/operator, committed PDF, seed/overlay change or human gate.

The public research leaf is `formal-source convert`: required workspace_root, light
paper_id, record_id, capture_authority, batch_id, operation_id, vault_root and
proposed_at; optional metadata path. It returns the ordinary source-publication
prepared/no_change result plus conversion metadata (record ID, association ID,
new/updated/unchanged claim IDs and unmapped lightweight concept suggestions).
Inspection uses the existing `vpwiki source-publication inspect` leaf. Input
registration must already exist in the audited Vault. There is no registration,
operator apply, source promotion or display selection in this command.

Metadata has a new closed `video-paper-wiki.source-conversion-metadata.v1`
object. Required fields: schema, paper_id, title, title_zh, authors, published_at,
aliases, taxonomy and code_urls. Optional arxiv_id and doi retain the existing
paper-record field semantics. Paper ID must equal the capture observation's
canonical paper ID; it need not equal the lightweight SHA-256 paper ID. Title is
nonblank; explicitly empty authors/title_zh/taxonomy/code_urls are permitted to
represent missing optional information. published_at is an explicit valid date
or UTC timestamp, preserving the existing union; the current date is never a
fallback. Fields have the same canonical schema constraints as paper-record.v2,
plus finite input bounds. Metadata is required for a new paper. Existing papers
may omit it to preserve all bibliographic fields; a supplied complete document
updates those fields, except aliases must retain exact existing spelling/order.
Existing omitted optional DOI/arXiv keys remain present with their old values;
an explicitly supplied key is subject to canonical identity consistency checks.

The selected lightweight head must be a fully validated completed record,
including batch completion and refresh ancestry where applicable. Retain the
whole bounded `.light-knowledge` input tree and selected `source.md`/`source.json`
plus capture authority and metadata input for the duration. The bounds are 8192
files/directories combined, depth 16, 16 MiB per JSON/Markdown managed file and
128 MiB aggregate, while existing narrower source/metadata limits still apply.
Refuse symlinks, hardlinks, special files, path aliases and complete-set/identity
changes. Validation must consume the captured bytes and compare final named
lineages on success and exception. A private generated snapshot mirror beneath
this checkout's `.work` is permitted if existing validators have no live-path
escape; the mirror must also be retained and verified. No global monkeypatching
or process-global reader override. The concrete retained mirror/session mechanism is defined below. No global light index is required merely for
conversion: validate the selected record's source binding and recompute its
chunks with `_load_paper`/`_derived_chunks` from the same captured source. The
existing `_record_source_status` result must be `current`.

Recompute formal_source._observe using the authority's canonical ID/version;
require full observation equality and raw capture byte equality. The optional
original_pdf_sha256 remains the accepted declared provenance from source.json;
this feature neither reads an original PDF nor upgrades that field's authority.
Use the earliest actual raw-registration receipt and its exact historical source
ledger snapshot. If that snapshot is absent, the unchanged current ledger may
supply it only when its hash is exactly the first registration write's hash.
Reuse associate_source and preserve all existing association bytes. A current
ledger from a later write cannot replace missing history.

A provisional lightweight section maps to exactly one canonical claim using its
exact text and the R1 section mapping. Derive claim_id from canonical subject and
text, and each evidence locator from the cited recomputed current chunk's exact
Unicode span/hash/page anchor and the registered association. Resolve every
locator before assembling a ledger row. Preserve citation order. Unknown
sections add no claim. Reject normalization collisions, duplicate incompatible
section/core ownership and existing retired refs. Existing claims retain exact
text, owner, ref and unrelated row fields. An unchanged evidence fingerprint
preserves existing evidence spelling/order, assessment and all event bytes.
Changed evidence uses an explicit v2 system evidence_invalidation successor,
sets provisional and reviewed_at null. New claims use a v2 system genesis event.
System actor is `source-conversion-v1`; reason identifies the selected light
record and exact source association. No human actor or review is synthesized.
Supplied proposed_at must be calendar-valid. When an event is appended it must
not precede that claim's current head; when a record changes it must not precede
that record's updated_at. An unchanged no-op may use any valid proposed_at, which
is not persisted. Only meaningful changes advance dates.

A v1 paper can be upgraded in place to v2 while retaining its ID, aliases,
source IDs, existing refs, old claim evidence and event bytes. Its old active
extraction remains stored as historical evidence. In the absence of any explicit
display decision, v2 display_head and active extraction pointers are null. All
v2 claim rows use the required canonical block anchor; this explicit migration
updates only location anchor for an otherwise unchanged old row. Other papers,
repositories and claims remain unchanged. Source row page links are updated for
every source attached to a changed paper or claim, without removing old links.

Assemble row/record/event/association/observation/snapshot payloads from one
retained audited Vault `_vault` session. Use collect_source_state with the
proposed overlay and require_rendered=False to derive the complete prospective
pages and both registries; do not duplicate the code/concept compiler assembly.
Add those exact pages and registries, then reuse the existing publication
preparation body extracted into one private retained-session helper. The public
prepare wrapper retains its signature/behavior and opens that same helper with
its own audited snapshot. Conversion passes its existing snapshot/audit/current
state directly, so assembly and staging never cross a second live Vault read.
The existing publication validator still enforces every history and unsupported
page-retirement rule. The existing shared transaction/receipt constructor and
inspect step are unchanged. A no-op returns no_change with no new events,
metadata timestamp changes, receipts or staged request.

Required evidence remains the R1 end-to-end chain and adversarial cases, adding
both legacy and extended/refresh lightweight records, two actual source versions,
legacy-to-v2 claim migration, accepted unchanged evidence, explicit publication
date timestamp metadata, complete mixed paper/code pages, historical registration
snapshot lookup, ordinary CLI errors and the public prepare compatibility delta.

## Concrete retained-input session

Use a dedicated source_conversion_io module. Retain the named original
`.light-knowledge` root and all ancestors; recursively capture every directory
entry set and each regular file's identity/mode/size/hash/exact bytes before
running any record validator. No selected-closure filtering: unrelated managed
records, jobs, staging and view/ownership entries are copied and verified too.
Capture empty directories as part of the complete set. Validate path spelling
before Path normalization, prohibit control characters/backslashes, dot aliases,
non-NFC or casefold-colliding sibling names, and refuse special/link entries.
Track observed sets and named edges during acquisition so an early read/parse
failure still verifies all acquired safety invariants before returning.

Use existing no-follow descriptor-relative secure I/O and identity stamps. A
single retained root descriptor with tracked descendant directory/file identities
and exact rereads (the established _Snapshot pattern) is permitted; retaining
one redundant ancestor descriptor chain per file is unnecessary. Reopen/check
named edges and full observed directory sets and re-read every retained file on
all exits. WORK_PATH_UNSAFE from failed final safety verification takes precedence
over an otherwise ordinary validation/staleness error. Preserve detailed semantic
ContractError codes, instance pointers and exit codes when safety is unchanged.

Materialize this exact captured tree plus the selected `papers/<digest>/source.md`
and `source.json` into a newly created private nonce directory under
`.work/<batch>/source-conversion/inputs-<32-lowercase-hex>/`. Use a retained batch
session and no-follow private parent creation; never reuse a foreign nonce slot.
The mirror has no live-root fallback, symlink or absolute source-root pointer.
Its complete directory/file set and bytes are captured immediately after creation
and retained through every validator call, assembly and request staging. Verify
both original inputs and mirror on every exit, including acquisition failure.
The original two source files, authority and optional metadata have their own
retained fixed-file lifetime starting before any typed JSON is consumed.
Mirror bytes may remain as generated `.work` diagnostic material; their presence
is neither publication nor durable transaction authority. A no-op creates no
prepared source-publication request, event or receipt.

Call only the path-independent read-only validator branch:
`current_head_record_id`, `_owned_record_bundle`, `_record_bundle_ok` with its
ordinary completed-job/ancestry checks, `_record_source_status`, `_load_paper`
and `_derived_chunks`. All use the mirror workspace path. No import, finalize,
resume, current-plan-binding, workspace identity regeneration, index rebuild or
search call is allowed. Existing completed plan.workspace_id is validated as
stored data and must not be rewritten to the mirror path. Validate the selected
head/record ID against the captured HEADS.json before and after these calls.

## Exact assembly and compatible refusals

Expose `convert_source_knowledge` in the research source_conversion module as a
keyword-only API with the public inputs above. Put pure metadata/claim/ledger
assembly in source_conversion_model to make source proof and history behavior
independently testable. Register the one convert leaf in formal_source.py;
existing research CLI/agent CLI leaves and defaults remain unchanged.

The returned object adds a closed `conversion` object to the existing publication
envelope: light_paper_id, record_id, canonical_paper_id, association_id,
association_state (proposed|reused), created_claim_ids, invalidated_claim_ids,
unchanged_claim_ids, location_migrated_claim_ids, unmapped_concepts. ID lists are
sorted unique arrays. Unmapped concepts preserve exactly the validated light
record's name and citation IDs, as suggestions only. No generation or source ID
is derived from model prose. New row defaults are risk=normal, confidence=unknown,
notes=null, supersedes=null; existing row values and optional presence survive.

All new evidence has relation supports because the light document does not encode
contradiction/context polarity. The provisional status is retained. This means
conversion proposes cited supporting evidence; it does not independently judge
whether the source actually supports the model's wording. Human semantic review
remains open. All citations must nevertheless resolve exactly to registered text.

Use the current raw ledger object, preserving row order/presence where untouched,
to update selected rows. If a historical nonaccepted row lacks reviewed_at, the
explicit v2 publication migration may add reviewed_at:null; all other optional
field presence survives. Existing source IDs are retained. Since v2 compiler
source_ids must exactly equal its association/current-evidence union, a v1 upgrade
with an uncited extra source ID that cannot be represented under that invariant
returns SOURCE_CONVERSION_UNSUPPORTED_CHANGE without modifying anything.
Explicit metadata changes that require page retirement retain the publication
SOURCE_PUBLICATION_UNSUPPORTED_CHANGE refusal; this package has no deletion path.
No current file, old event, association or snapshot is dropped to force acceptance.

The metadata schema is the single new public resource
`schemas/video-paper-wiki.source-conversion-metadata.v1.schema.json`. It has a
valid fixture and ordinary valid/invalid contract checks. New public title/author
strings and arrays use their existing paper field shapes, with overall metadata
file maximum 1 MiB, at most 256 authors/aliases/taxonomy/code URLs and 16384 Unicode
characters per text field. title must contain non-whitespace text. Calendar and
pinned taxonomy/DOI/arXiv identity checks run before staging. JSON is strict
UTF-8, no duplicate keys/nonfinite numbers/unsupported primitives.

New conversion-specific refusal codes are SOURCE_CONVERSION_INVALID (malformed
metadata/selection/mapping), SOURCE_CONVERSION_STALE (light current head/source
changed or selected record no longer current), SOURCE_CONVERSION_UNSUPPORTED_CHANGE
(unrepresentable preserved source IDs). They carry structured pointers and exit
code2 except stale/unsupported use75. Lower-level schema/identity/registration/
publication errors retain their original codes; safety uses WORK_PATH_UNSAFE.

The retained publication helper is private and requires the already validated
batch/operation, current state, audit and retained snapshot. Move the existing
prepare body without changing its operation kind, prospective checks, payload
limits, request schema, staging bytes, no-op or error behavior. Both callers use
this one implementation; no duplicate receipt or transaction construction.

## Acceptance and delivery

Freeze all owned paths before final acceptance. Verify legacy public preparation
behavior after the helper extraction; actual light import plus capture/register/
convert/inspect and synthetic isolated apply/audit; batch and refresh records;
legacy/v2 migration and complete mixed code pages; accepted unchanged evidence;
changed evidence invalidation; two registered versions and earliest snapshot
lookup; no-op; Unicode/CRLF and foreign citation refusals; collisions/retired refs;
metadata identities/date union; source/mirror/Vault named-lineage and complete-set
races on success and exception; byte/file/depth bounds and installed wheel.
Run both locked Python suites after the candidate is frozen. Deliver through the
existing draft PR95 to integration, fresh four-job exact-head CI and independent
Architect acceptance. Do not claim SOURCE complete: source-aware catalog remains
its next required increment, followed by the remaining full-TODO packages.
