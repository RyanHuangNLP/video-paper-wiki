# SOURCE canonical continuation — design R1 (not a Builder dispatch)

This design records the next interfaces after SOURCE-CAPTURE-R1. It is not an
accepted implementation or a frozen file allowlist. The existing source capture
packet remains independently frozen. Full SOURCE closes only after publication,
version-aware catalog/query and their continuous validation, not after pure
schema helpers. Legacy PDF/code v1 contracts keep their exact semantics.

## One canonical source of truth

Keep the pinned source ledger and claim ledger. A Markdown claim uses the existing
upstream evidence string field with a new tagged locator; it does not gain a
second claim identity or an independent research assessment. Engine-owned immutable
source associations and display decisions extend the canonical metadata. Research
submits proposals and consumes the engine's validated result.

Paper ID remains version-independent. Claim ID remains the existing
`claim_id(stable_subject_id, nfkc_collapse(text))`; neither a version label nor a
locator is added to this formula. Original PDF hashes in the lightweight source
observation remain provenance only; no PDF, Docling output or false byte-exact
network observation is manufactured.

## SOURCE-SEMANTICS proposed boundary

A bounded pure-engine packet can define and exercise these interfaces without
writing a Vault or waiting for a real operator. It must consume the exact frozen
`markdown-source-observation.v1` semantics, not redefine that object. Source
association proposals must remain visibly unregistered until publication.

1. Immutable `source-version-association.v1`: schema, association ID, paper ID,
   source ID, version descriptor, raw path/hash/size, exact source observation,
   source-registration receipt reference, and extraction descriptor. Association
   ID/content hash must be specified separately from the same-version conflict key.
   A source ID is the existing pinned content/path identity. Distinct version
   associations may share it and its raw bytes. A new association never invents a
   capture receipt; generic capture has none. Registration is established by the
   receipt that first claims the raw path and writes the matching source ledger.

   Initial version descriptors preserve `unknown` and `declared` from source
   capture. `unknown` is not the label v1 and does not assert arXiv provenance.
   Explicit arXiv/version-observation plus manual-file acquisition binding is a
   distinct future validated branch, not a reinterpretation of a declared label.
   Same explicit version + same bytes reuses the existing valid association;
   same explicit version + different bytes is a conflict. Unknown versions are
   separated by content identity rather than pretending all unknown inputs are
   one conflicting release. New observation metadata cannot overwrite an existing
   association. Additional provenance can remain separately referenced history.

2. Append-only display decision and one materialized display-head registry per
   paper. Decisions carry previous decision ID, exact association reference,
   externally supplied actor/choice record, time and reason. Validate no missing
   predecessor, branch, cycle or multiple genesis. The head is derived from the
   complete decision chain and published in the same transaction as its paper
   record mirror. A new import alone does not select itself; default view before
   any decision is legacy/unknown or explicitly unselected. A later decision may
   select an older association (rollback) without rewriting history.

3. `paper-record.v2` preserves stable identity, metadata, taxonomy v1, section
   references and ownership. It adds the complete sorted association references
   and the derived display-head reference. Its active extraction mirror must
   exactly equal the selected association's extraction. No independently set
   active source is accepted. A legacy v1 record is adapted in memory as a legacy
   view and is never relabeled as v2 or as an observed v1 source. Converting a
   legacy record to v2 requires an explicit transaction with unchanged identities
   and an evidence-bound association; old clients must fail closed on v2.

4. A new Markdown locator is an exact locator, not an estimated PDF coordinate:
   source ID, association reference, `.raw/captured/<sha>.md`, complete raw hash,
   half-open Unicode span, page anchor when backed by the source observation,
   and excerpt hash. Spans index the exact decoded UTF-8 bytes; do not normalize
   line endings or Unicode before slicing. Reject out-of-range/empty spans and
   excerpt/hash/anchor mismatches. Heading labels are display data, not sole
   location authority. The source-version ID is part of the evidence identity.
   A new `vpwiki-locator-v2:` closed envelope handles Markdown. Legacy v1 PDF/code
   wire decoding remains byte-identical and rejects a v2 wire through v1 APIs.

5. Evidence fingerprint v2 is domain-separated and hashes all required Markdown
   identity fields plus relation, in canonical order. Legacy-only v1 evidence
   keeps the old fingerprint through the legacy branch. Mixed/v2 evidence uses
   an explicit profile, never an unmarked change to `evidence_fingerprint` v1.
   Duplicate identity handling and ordering are specified in the frozen packet.
   Assessment v2 records the evidence profile. The engine derives the one current
   assessment head; changing evidence or switching fingerprint profile requires
   a system evidence-invalidation event to provisional before any human review.
   A display switch alone does not mutate a claim or its evidence/history.
   Existing v1 events remain historical bytes and may precede an explicit v2
   invalidation; a v2 human event cannot silently reinterpret its v1 predecessor.

6. Compiler v2 handles a complete prospective mix of legacy and v2 papers. Legacy
   pages stay byte-identical if their inputs and related set are unchanged. V2
   pages show imported versions, selection state, explicit evidence references
   and assessment status. A provisional page may have no accepted core conclusion
   and must say so; accepted/contested core summary eligibility remains unchanged.
   This is an explicit v2 behavior, not weakening the v1 1–3 core requirement.
   All generated links and frontmatter escape hostile source/model text.

Pure APIs must take closed bytes/material and return deterministic objects or
stable ContractError codes. No global monkey-patching of v1 validators, no copying
records to fake PDF/Docling fields, and no current-head cache maintained by research.
All new schemas are exposed through the installed package with exact resource
bytes. Tests include prior v1 outputs and IDs, unknown/declared versions, same-byte
multi-version reuse, conflicting labels, selection/rollback, malformed chains,
Markdown Unicode spans, profile change invalidation and mixed-source histories.

## SOURCE-PUBLICATION proposed boundary

The next I/O packet consumes accepted SOURCE-CAPTURE and SOURCE-SEMANTICS bytes.
It creates a versioned publication request with a complete prospective inventory:
source ledger, claim ledger, paper records, associations, display decisions/head,
assessment events/head and all generated pages. One retained snapshot provides
named path and content authority. Every success and exceptional exit rechecks
retained edges; missing fixed slots are retained as absence preconditions. The
complete file set rejects unknown or unsafe orphan entries.

Existing generic transaction and receipt formats remain unchanged where they
already accept these business paths. New namespaces must be explicit in the
prospective validator and audit, not merely tolerated as arbitrary JSON. One
transaction updates all canonical mirrors, includes complete read preconditions,
claims any newly admitted inputs and writes one receipt/head. The agent prepares
and inspects; only test fixtures apply. Public helpers may bind actual external
operation results but cannot fabricate an applied status.

The legacy publication path must explicitly refuse a version-aware managed
snapshot. Its current `_existing_bindings` skips unknown paper records; leaving
that behavior for a recognized v2 record could miss a conflicting primary owner.
This targeted compatibility refusal is required while preserving valid v1 paths.

A source-to-canonical research adapter consumes current lightweight claims and
citations, constructs exact proposed locators, and creates only provisional system
assessment genesis/invalidation. It never converts model prose into human review.
Title/metadata identity choice and source label remain declared unless their
explicit observation/acquisition chain is supplied and validated. Full SOURCE
requires exercise of the real capture → registration → canonical proposal →
prepare/inspect → isolated fixture apply → receipt audit chain.

## SOURCE-CATALOG and status proposed boundary

Use a separate explicit version-aware catalog profile, resource manifest and
collector. Do not add fields or tables to closed base/search catalog v1 resources.
The new collector consumes the single canonical record/head/ledger inventory,
including legacy records, and rejects incomplete/mixed authority. Legacy clients
must report unsupported/current-state refusal when new canonical namespaces exist;
an old partial catalog must not report current merely because it ignored them.

Generation material binds complete association/decision/head/assessment/ledger/
source bytes, schemas, compiler and query profiles. Exact Markdown excerpts are
joined to source version and span. Queries and citations expose selected version
and actual referenced version separately; an older version is not automatically
stale. Current-view queries become stale if their declared head/generation changes.
Status is derived by engine from validated evidence, including source registration,
canonical publication and catalog coverage. Research maps this to next actions;
it does not maintain a parallel mutable ingest-state ledger.

Backup/restore handling for each new canonical namespace belongs to the producing
packet; full cross-namespace session recovery remains PRODUCT. Unknown legacy
profiles must fail visibly. Required continuous cases: empty/legacy/Markdown/mixed
catalogs, explicit version switching and rollback, same source across versions,
claim invalidation and human review fixtures, stale generation, exact citation
resolution, isolated snapshot backup/restore, and no real-Vault writes or egress.

## Dependencies to settle at freeze

- Exact schemas/module/function names and the registry handoff use actual accepted
  SOURCE-CAPTURE code. The pure packet is not permitted to alter its observation.
- Explicit official-version acquisition binding joins accepted W1 preview/decision
  to user-provided local source hash; neither preview nor a label proves file origin.
- Choose one evidence-profile migration representation and test v1→v2 history
  without changing old fingerprint/ID output. No second assessment ledger.
- Publish and collect each namespace before describing it as canonical/current.
- Each later implementation has its own stopped candidate and exact evidence;
  this design is not authorization to write files outside a frozen allowlist.
