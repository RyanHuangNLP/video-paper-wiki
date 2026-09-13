# SOURCE conversion — concrete decisions for final review

This draft supersedes draft R1 for design discussion only. It is not an
implementation freeze. Root owns implementation under LOCAL-CODEX-OWNERSHIP-R2.
The source-publication R2 candidate remains frozen while delivery is checked.

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
or process-global reader override. Freeze the exact mirror/session mechanism
after the dependency-read review. No global light index is required merely for
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
Supplied proposed_at must be calendar-valid and cannot precede existing event
heads or a changed record's updated_at. Only meaningful changes advance dates.

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
