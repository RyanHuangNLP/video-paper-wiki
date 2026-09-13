# SOURCE publication bridge boundaries R1

Status: boundary review and implementation handoff contract. This document
does not accept a publication implementation, apply a transaction, register a
source, or close a human review gate.

The review was performed against the accepted SOURCE-CANONICAL-DESIGN-R1
(`e46211baa9bba40f52746748757257ed49dbc3cb5c5801668824a486d900e5af`),
SOURCE-CAPTURE-R1 (`5bf912cc2aec0fec951168779d6336c95733c25be3e4377a611adb55296cacf8`),
and SOURCE-SEMANTICS-R2
(`ad21572558bf1053a248f07d5bb3e950780765aecb8ed4ef4da29025047366f9`).
The inspected compatibility modules were the current
`publication_bridge.py`, `source_admission.py`, and generic `publication.py`.

## Review decision

The next implementation may be frozen as a separate SOURCE-PUBLICATION packet
provided it preserves the boundaries below. The existing research bridge is a
useful legacy precursor, but it is not the SOURCE-PUBLICATION implementation:

* `source_admission.admit_source` stages a receipt-backed source-ledger
  admission for a captured PDF and correctly stops before operator apply.
* `publication_bridge.package_extraction_run` packages a receipt-backed PDF
  and Docling run, and `prepare_paper_concept_publication` prepares v1 paper,
  claim-ledger, and v1 assessment-event material.
* Those functions do not consume a Markdown source observation or a v2 source
  association, do not derive display heads, and do not create v2 assessment
  history. Their PDF/Docling outputs must remain on the legacy path.

The current generic publication inspector also has a compatibility boundary
that must be repaired in the future packet: `_existing_bindings` validates
recognized `paper-record.v1` objects and skips records it does not understand.
Once a recognized version-aware record namespace exists, the old publisher must
refuse that snapshot before binding existing primary owners. Skipping it could
miss an owner conflict and falsely make a partial legacy publication appear
safe.

## Authority flow

The bridge consumes exact, already validated bytes from the preceding stages.
It may bind consistency and construct a prospective request; it may not create
authority in the process.

1. Capture supplies the exact Markdown observation, raw `.md` bytes, pinned
   source identity, capture authority, and (for a first registration) a bound
   external capture result. The capture result is evidence of an external
   operation; the bridge must not infer it from the desired after-state.
2. Source semantics validates the association, historical registration proof,
   extraction reference, complete source inventory, display decision chain,
   paper record, Markdown locator, evidence profile, and assessment history.
   A proposed association remains visibly unregistered until publication.
3. The bridge creates one complete prospective publication request. Its named
   inventory includes the source and claim ledgers, v2 paper records, source
   associations, display decisions and derived heads, assessment events and
   derived heads, and every generated paper/concept/code page.
4. Existing prepare/inspect machinery may turn that request into a transaction
   inspection authority. The agent stops at the inspected request. Only the
   operator-owned apply path can create the receipt, update the current head,
   and make the source receipt-backed.
5. A later binding helper may accept an externally supplied operation result
   only when its inspected transaction and before/after snapshots match the
   request and actual bytes. It must return a bound result or refuse; it must
   not apply, synthesize, or label an unobserved result complete.

The source ledger admission and canonical paper publication are separate
business decisions, even when they are prepared in one user flow. The bridge
must preserve the distinction between a captured raw file, a proposed
association, an inspected transaction, and an operator-applied receipt.

## Retained snapshot requirement

Every compound prepare/inspect operation uses one retained snapshot with named
path and content authority. It retains the complete fixed-slot set, including
the absence of slots that must remain absent. At minimum this covers the
request, every content blob, source and claim ledgers, association and paper
record paths, display and assessment paths, generated pages, current heads, and
the relevant parent directories.

The bridge rechecks the retained snapshot on every successful and exceptional
exit. A replacement directory, symlink, hardlink, special file, changed byte,
changed inode identity, unexpected entry, or changed absence slot overrides a
child validation error with the path-safety error. One multi-file retained
session is required; independent staging calls cannot establish one lineage.
The dedicated publication-input directory must have the exact expected set at
each phase and must reject orphan content or unknown entries.

The prospective validator must require complete cross-namespace coverage. A
request that writes a paper or concept page without the corresponding complete
record/claim/event/association material, or that supplies an unreferenced
managed file, is refused. Missing existing snapshots are read preconditions,
not permission to silently create a partial current view.

## Version and evidence rules

The bridge must pass the exact Markdown observation through the semantics APIs;
it must not reparse `source.md`, manufacture page coordinates, or copy the
source into PDF/Docling fields. The Markdown locator is an exact UTF-8
half-open span bound to its source association and raw hash. A page anchor is
optional only where the observation proves it; heading text is not location
authority.

Legacy-only evidence keeps the byte-exact v1 fingerprint and wire behavior.
Any Markdown or mixed evidence uses the explicit mixed-v2 profile. Changing a
source association, locator, or evidence profile changes the derived v2
identity. A display switch by itself does not mutate a claim or assessment.
Evidence changes require a system evidence-invalidation event to provisional
before a human assessment successor. Existing v1 events remain historical;
the first v2 successor to a v1 chain cannot silently reinterpret its parent,
and a v2 human event cannot bypass the required invalidation.

Version labels remain the accepted `unknown` or `declared` values. A declared
label is not proof of official provenance. The adapter must not claim an
official version, source registration, human review, or canonical publication
without the corresponding supplied observation/acquisition or applied receipt.

## Legacy compatibility boundary

The existing v1 publication path remains available for an entirely legacy
snapshot and must preserve its prior bytes, IDs, fingerprints, and refusal
behavior. It must explicitly refuse a recognized v2/version-aware managed
snapshot before `_existing_bindings` can ignore its records. The refusal should
name the unsupported current namespace and leave the snapshot untouched.

The legacy research bridge currently emits:

* `paper-record.v1` with Docling extraction mirrors;
* v1 PDF evidence made from Docling locators;
* v1 provisional system genesis events; and
* an ordinary v1 publication request.

These outputs are valid only for the legacy PDF/Docling route. They must not be
relabeled as Markdown observations, v2 records, source-version associations,
display-head material, or accepted research claims. A new bridge should use
explicit v2 prospective groups and the semantics compiler, while retaining the
old adapter unchanged for legacy inputs.

## Research adapter boundary

The research-side adapter may read the existing lightweight paper observation
and draft claims, then propose exact locators and compiler claims. It may create
only provisional system genesis or evidence-invalidation events required by
the evidence transition. It must never turn model prose into a human review,
invent an approval reference, issue a source-registration receipt, select a
display head without the supplied choice record, or write a current-head cache.

Title, metadata, taxonomy, and version labels remain declared observations
unless their explicit acquisition/observation chain is supplied and validated.
Synthetic fixtures may exercise the bridge, but fixture authority is not a real
approval or source admission.

## Required acceptance vectors for the next packet

The bounded implementation review should exercise the actual interfaces and
retain exact outputs for:

1. legacy-only input byte parity, including v1 IDs/fingerprints and the old
   compiler output;
2. Markdown create, same-content reuse, conflicting-content refusal, unknown
   and declared versions, and first-registration historical receipt proof;
3. display selection, rollback, malformed-chain refusal, and complete head
   materialization;
4. exact Unicode spans, page-anchor and cross-page locators, mixed evidence
   fingerprinting, and v1/v2 wire refusal in the wrong API;
5. v1-to-v2 assessment migration, required invalidation, human-profile bypass,
   v1 re-entry, same-fingerprint invalidation, and changed-association cases;
6. complete mixed compiler output with hostile text escaping, provisional pages,
   source-map completeness, duplicate owners, unknown taxonomy, and orphan
   rejection;
7. old publisher refusal for a recognized v2 snapshot and unchanged valid v1
   publication; and
8. success and exception-path retained-lineage races for every fixed slot,
   including parent replacement and unexpected entries.

The evidence must identify the exact candidate snapshot, focused tests, both
locked Python full suites, installed-wheel resource parity, and fresh CI
separately. No local fixture result, inspected authority, or engineering
acceptance closes the real source, operator, or human gates.

## Files inspected

* `src/video_paper_wiki_research/source_admission.py`
  (`5a8072312909ab2ee1705f592a4e38688f5328cdf9bbeb148cb19c6eaf67209e`)
* `src/video_paper_wiki_research/publication_bridge.py`
  (`3e70591da0130ed4f4f3d85fda4d2b49b8840b44412ad6c76a9e42bd1ad21a28`)
* `src/video_paper_wiki/publication.py`
  (`154bb3d1f0cdd39cd07a4a18597652068a590abefe6b705a1dc5f6461d83feb3`)

This review is read-only with respect to production source and Vault state.
