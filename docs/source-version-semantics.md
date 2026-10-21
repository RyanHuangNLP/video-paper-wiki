# Sources, display versions and exact evidence

The source semantics API keeps imported Markdown versions, the user's display
choice, and each claim's evidence separate. Importing another version creates a
source association proposal. It does not select a display version or transfer an
old assessment to different evidence.

These are pure in-memory APIs. They take explicit documents and bytes, return
validated proposals or compiled page bytes, and do not publish or read a Vault.
Their checks prove consistency of supplied material. A retained publication
adapter must establish the complete actual inventory, preserve already-published
history, and run the pinned prospective ledger inspection before publication.

## Registration and versions

`source_versions.associate_source` takes the accepted Markdown observation and
its original UTF-8 bytes, the complete operation head and receipt byte map, the
exact historical source-ledger bytes, and the existing association list. It
returns `proposed` or an exact `reused` association. The first receipt touching
the captured Markdown must be the source registration ingest that reads those
bytes and writes that historical ledger. A generic capture has no receipt; its
raw file alone cannot provide registration proof.

Each association binds the paper identity, declared or unknown version, raw
content, complete observation, immutable registration receipt, historical ledger
snapshot, and observation extraction bytes. The extraction is native Markdown
source metadata. It does not claim Docling output or infer a PDF release number.

The same explicit label cannot identify different bytes. Two explicit labels
may refer to the same raw bytes while retaining distinct observations. Unknown
versions remain unknown. Reusing the same label and bytes with changed metadata
returns `SOURCE_PROVENANCE_VARIANT`, including the prior association reference
and the proposed observation hash. Callers can preserve and resolve the variant
without silently replacing its provenance.

`validate_source_inventory` checks exact raw, extraction and historical ledger
map sets, each source's first-registration proof, and all association references.
Missing and orphan byte-map entries refuse. Historical source-ledger JSON need
not have canonical spelling: its exact original bytes are hashed. Heads and
receipts must use canonical JSON without a terminal newline.

## Display choice and rollback

`make_display_decision` requires the caller's explicit human actor, choice source,
reference, text, timestamp and reason. It creates no automatic selection.
`derive_display_heads` derives the terminal event for each complete, consecutive,
nonbranching paper history. A rollback appends a decision selecting an older
association. It does not erase the intervening decisions.

These functions cannot authenticate the human named in a supplied document.
`fixture` choices in tests are synthetic, and do not close a real human gate.
The future publisher must atomically store decisions, the complete display-head
registry, and paper record mirrors. A paper without a selection has a null
display head and null active extraction path/hash.

## Markdown evidence and assessment migration

`markdown_locator` adds the `vpwiki-locator-v2:` transport for Markdown evidence.
Its half-open character span indexes the decoded original UTF-8 string. Newline
and Unicode normalization are not performed. A non-null page anchor must contain
the entire span; a null anchor can represent an exact cross-page span. The
excerpt hash binds precisely the UTF-8 bytes of that slice. Whitespace-only
excerpts and estimated PDF boxes cannot represent Markdown evidence.

`encode_evidence` and `decode_evidence` preserve the existing upstream three-field
transport, dispatching PDF/code to the unchanged v1 codec. A Markdown locator
also binds the actual association. Selecting a newer display version leaves a
claim's old association reference intact.

`evidence_fingerprint_versioned` uses the unchanged v1 fingerprint for lists with
no Markdown. Mixed lists use a separate domain, retain complete Markdown identity,
and sort and deduplicate exact identity objects. Optional legacy display metadata
does not change evidence identity. Claim IDs continue to depend only on stable
subject and normalized claim text.

`assessment_history_v2.derive_assessment_heads` accepts complete mixed v1/v2 event
histories. The first v2 successor of an old chain must explicitly invalidate
evidence and return the claim to provisional. A subsequent human review keeps
the predecessor's evidence profile and fingerprint. It cannot substitute new
evidence while asserting an old approval. The caller must provide the actual
unchanged v1 predecessor events; the future retained publisher must compare them
with the existing stored event bytes as an immutable prefix.

Existing PDF evidence may retain finite floating-point display coordinates in
its optional four-value bbox. Only the declared legacy evidence positions receive
this compatibility treatment, including code alignment officiality evidence.
The v1 codec retains exact rational wire representation. New Markdown spans and
source identity metadata remain integer-only; a `kind: pdf` object placed in an
unrelated field cannot bypass validation.

## Compilation

`canonical_compiler_v2.compile_pages` takes `compile-input.v2` plus explicit source
byte maps. It accepts legacy and versioned paper groups, complete pinned taxonomy
concepts, and unchanged code groups. It validates owners, complete source material,
display mirrors, assessment histories and locator resolution before rendering.
Legacy-only material delegates to the existing compiler and preserves its bytes.
In mixed output, legacy paper/code bytes stay unchanged when their related link
set stays unchanged. Concept pages receive the complete prospective paper links.

Versioned pages show every imported version, the display choice, ten established
paper sections, and exact evidence source/association/span/hash details. A page
without an eligible reviewed core conclusion says `暂无已审核的核心结论。`.
Unreviewed or noncore conclusion claims remain visible under evidence status;
retired claims also remain visible there. At most three active accepted or
contested core conclusions can appear in the conclusion section.

All output paths are derived from canonical identities. Untrusted frontmatter
uses JSON escaping and page prose uses Markdown/HTML escaping. The result is a
deterministically sorted path-to-bytes map; it does not assert publication.

## Validation evidence

The seven new engine schemas have explicitly synthetic valid fixtures. Tests
cover complete golden v2 and mixed legacy/concept/code pages, unchanged legacy
identity/wire/fingerprint behavior, Unicode combining characters and CRLF spans,
selection and rollback, provenance variants, receipt and ledger tampering,
assessment migration and malformed inputs. A pinned synthetic integration test
executes the existing generic capture and source ingest helpers, then verifies
the association against their actual resulting receipt bytes. It does not create
or use a real Vault, submit PDF files, or treat fixture actors as real reviewers.
