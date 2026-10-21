# SOURCE-SEMANTICS revision 1

Implementation owner: local Codex root, under LOCAL-CODEX-OWNERSHIP-R2.json.
Baseline: b973f840ff57702db31d89c198a3bffc74ff8fcf, tree
a12faeba7c34cfc07dc305e2aca13bfc153db041. Source checkout:
`.work/parallel/source-semantics-v1/terminal-1/source`.
This packet implements pure source-version, locator, assessment and compiler
semantics. SOURCE remains incomplete until its publication/catalog continuation.
No network, subprocess, Vault access, staging or operator execution in new modules.
Packaging may read pinned schema/taxonomy resources as existing pure compilers do.

## Shared rules

Existing closed v1 schemas, IDs, locator wire, fingerprints and compiler behavior
are immutable. Dispatch only the seven named new schemas in contracts.py. Add
strict JSON preflight for those schemas: exact built-in dict/list/scalar types,
no float, surrogate, NUL, cycles or integer outside +/-9007199254740991; depth 48,
100000 nodes and at most 8 MiB per string. APIs do not mutate caller containers.
All durable objects and byte references use the existing canonicalize() bytes
(no terminal LF). Full SHA-256 is lowercase hex. Dates are real Gregorian UTC
timestamps, not regex-only dates. Pure validation proves supplied consistency;
it never authenticates a human, operator, remote source or inventory completeness.
The later retained-I/O adapter establishes the supplied inventory's authority.

The exact allowlist is SOURCE-SEMANTICS-allowed-paths-r1.json. Existing source
capture and preview candidates stay unchanged. Additional implementation paths
require a recorded scope amendment before editing. Tests/fixtures are explicitly
synthetic and generate PDF fixtures only at runtime if needed.

## Source associations and registration

`video-paper-wiki.source-version-association.v1` is a closed object with schema,
association_id, paper_id, source_id, version, raw, observation, registration and
extraction. association_id is `sva-` plus SHA256(JCS(object without association_id));
an association reference is {association_id, sha256}, with sha256 binding JCS of
the complete object. Its managed path is
`wiki/meta/records/source-versions/<association_id>.json`.

paper_id, version and observation are exact accepted Markdown observation values.
version remains {status: unknown, label: null} or {status: declared, label: text}.
No official arXiv observation/acquisition branch is invented in this packet.
raw is {path, sha256, size_bytes}, exactly `.raw/captured/<sha256>.md`, and matches
observation.markdown. source_id is the accepted pinned file identity
`src-` + SHA256(UTF8('file\0' + raw.path + '\0' + raw.sha256))[:20].
extraction is {path, sha256, size_bytes}; its bytes are exactly JCS(observation),
path `.raw/derived/markdown-source/<raw-sha>/<observation-sha>.json`.
This represents native extracted source metadata, never PDF/Docling authority.

registration is {receipt_path, receipt_sha256, source_ledger_path,
source_ledger_sha256}. The ledger snapshot path is
`.raw/derived/source-ledgers/<source_ledger_sha256>.json`. Its bytes must exactly
match a source-ledger write by the FIRST receipt that claims this captured path.
That receipt must have operation_type ingest and contain precisely one matching
read claim for the path/hash plus one source-ledger write. Earlier receipt claims
or writes of the raw path prohibit relabeling a later receipt as registration.
The exact ledger parses as the pinned closed source-ledger profile and contains
one matching file/document row with this source ID, path, content hash and primary
authority; no second row may claim this path or hash under a different source ID.

`source_registration.registration_proof(raw, source_id, *, head_bytes,
receipt_bytes, ledger_bytes)` verifies canonical head/receipt spelling, all
hashes/intent IDs, canonical receipt filenames, full sequence 1..head, complete
reachable receipt set, no branch/cycle/orphan and receipt replay preconditions.
It returns only the derived registration descriptor. Bytes are explicit arguments,
never paths to read. This is a consistency proof over supplied historical bytes;
SOURCE-PUBLICATION must correlate it with one retained audited Vault and preserve
the ledger snapshot. Missing historical bytes fail; current ledger bytes are not
silently substituted. Generic capture produces no registration receipt.

`source_versions.associate_source(observation, *, raw_bytes, head_bytes,
receipt_bytes, ledger_bytes, existing)` validates all supplied material and returns
{state: proposed|reused, association}. New association proposals are unregistered
until canonical publication. The conflict key is (paper_id, status, exact label)
for declared versions, or (paper_id, unknown, raw.sha256) for unknown versions.
Same key + same raw bytes returns the immutable prior association, even if new
observation metadata differs; same explicit key + different bytes refuses with
SOURCE_VERSION_CONFLICT / exit75. Different explicit labels may share raw bytes
and source ID. Unknown is neither v1 nor an official release. Duplicate association
IDs or duplicate keys in a supplied inventory refuse even when bytes match.
Observation source paper identity must equal association paper identity.

`validate_source_inventory(associations, *, raw_sources, extraction_artifacts,
head_bytes, receipt_bytes, registration_ledgers)` checks every association against
its exact raw, observation, extraction and registration proof. Maps are keyed by
the declared raw/extraction/ledger snapshot paths and must have exactly the needed
sets, rejecting missing or orphan material. Aliased versions share one map entry.
All raw sources retain exact UTF-8 bytes and accepted page-interval validation.

## Display choices and paper records

`video-paper-wiki.source-display-decision.v1` is closed: schema, decision_id,
paper_id, sequence (1..8192), previous_decision_id (null or svd-64hex), association
(exact association reference), actor {kind: human, identity: nonempty text},
choice {source: user_message|user_file|fixture, reference: nonempty text,
text: nonempty text}, decided_at and reason. decision_id is `svd-` plus SHA256
of JCS(object without decision_id). Path:
`wiki/meta/reviews/source-display/<decision_id>.json`. No API invents actor/choice
records; tests label their input fixture. Consistency is not human authentication.

`make_display_decision(... supplied fields ...)` seals one proposal;
`derive_display_heads(associations, decisions)` validates the complete supplied
chains: one genesis per selected paper, same-paper edges, consecutive sequence,
strictly nondecreasing UTC time, no branch/cycle/missing/duplicate/unreachable
event, exact association references and paper ownership. A rollback selects an
older known association by appending a new event. Import alone adds no decision.
The result is `video-paper-wiki.source-display-heads.v1`, with schema and a sorted
heads list of {paper_id, decision_id, decision_sha256, association, sequence}.
The registry contains only papers with a choice, at
`wiki/meta/records/source-display-heads.json`; the producing publication must
atomically update it with paper record mirrors. A supplied materialization must
exactly equal this derivation, including the complete selected-paper set.

`video-paper-wiki.paper-record.v2` copies v1 metadata and section fields without
changing their definitions, adds sorted unique source_associations refs and a
display_head of null or {decision_id, sha256}, and allows null active_extraction
path/hash only together. No selected head => both active mirrors null. A selected
head must refer to the derived terminal decision and mirror its association's
extraction exactly. source_ids must equal the sorted union of association source
IDs and current claim evidence source IDs. V2 may be unselected and provisional.
Legacy v1 records are validated in memory and kept as legacy views; no API silently
converts them or claims that an unversioned PDF was observed release v1.
Same primary paper/claim owner twice in prospective compile material is rejected.

## Exact Markdown locators and profile migration

`video-paper-wiki.ledger-locator.v2` is a closed envelope {schema, locator}.
locator is closed {kind: markdown, source_id, association, path, sha256,
charspan: [start,end], page_anchor: null|string, excerpt_sha256}. The association
reference binds the exact source-version object. The raw path/hash/source ID
must match that association. 0 <= start < end <= decoded Unicode character count;
slice exact decoded UTF-8 without newline or Unicode normalization. Non-null
page_anchor must be present in observation.pages and contain the complete span;
null supports an exact cross-page/general source span. excerpt_sha256 is SHA256
of exact UTF-8 slice. Empty/whitespace-only excerpts refuse. No estimated PDF box.

`markdown_locator.encode_markdown_locator` / `decode_markdown_locator` use
`vpwiki-locator-v2:` + canonical envelope JSON, maximum wire65536 UTF-8 bytes.
Wrong prefixes, extra fields, noncanonical spelling, bad types/spans or hashes
refuse. `resolve_markdown_locator(locator, association, raw_bytes)` additionally
revalidates exact source observation/page material and returns exact excerpt.
`encode_evidence` / `decode_evidence` dispatch v1 PDF/code through unchanged v1
functions and v2 Markdown through new functions, with unchanged outer upstream
{source_id, relation, locator} transport and uncertain<->context mapping.
Legacy v1 APIs continue to reject the v2 wire.

`evidence_profile(evidence)` yields legacy-v1 if no Markdown, else mixed-v2.
`evidence_fingerprint_versioned` returns the untouched v1 fingerprint for legacy
lists. For mixed-v2 it hashes UTF8('video-paper-wiki.evidence.mixed.v2\0') plus
JCS of sorted unique identity objects: complete Markdown locator plus relation;
for PDF/code use unchanged v1 identity fields/casefold rule. Canonical identity
bytes determine ordering and duplicate collapse; optional display fields never
create identity. Every evidence item is fully validated before fingerprinting.
Changing association alone therefore changes mixed evidence identity. Claim ID
remains existing claim_id(subject, nfkc_collapse(text)), without source/version.

`video-paper-wiki.assessment-event.v2` copies v1 fields and transition grammar,
adds evidence_profile: legacy-v1|mixed-v2. Its event_id uses the existing ase-
20hex formula over all fields except event_id; schema/profile domain-separate it.
`assessment_history_v2.derive_assessment_heads(claims, events)` accepts complete
mixed histories and the unchanged six-field claim material. Validate each v1
event with v1 rules and assign its implied profile legacy-v1. A v2 genesis must
be system/provisional; a human successor retains BOTH predecessor profile and
fingerprint and must change state. Evidence/profile changes require system
evidence_invalidation -> provisional; either profile or fingerprint must differ.
After entering schema v2, reverting to a v1 event is refused. A first v2 successor
to a v1 chain must be explicit evidence_invalidation; it cannot reinterpret its
predecessor as v2 human approval. Final profile/fingerprint equals current claim
evidence, assessment/reviewed_at mirror terminal state, exact claim text hash and
identity bind every event. Validate one connected complete chain per claim,
duplicates/branches/cycles/unknown claims, and monotonic event time. A display
choice by itself does not change claims or assessment events.

## Prospective compiler v2

`video-paper-wiki.compile-input.v2` retains schema, operation_id, papers, code,
concepts; code/concept shapes are exact v1. Papers is a closed union of legacy v1
groups and v2 groups. V2 groups have record, claims, events, associations,
display_decisions and optional assessment_heads; claims retain six fields and
evidence is the union of v1 evidence and new Markdown evidence. Events are v1/v2.
V2 group association set exactly equals its record's references; every decision
belongs to this paper and a supplied association. All claims exactly match record
references and stable paper owner. Each Markdown locator must point to a supplied
association; exact raw resolution is mandatory, including refs to older versions.

`canonical_compiler_v2.compile_pages(material, *, raw_sources,
extraction_artifacts, head_bytes, receipt_bytes, registration_ledgers)` validates
the complete union of association material with validate_source_inventory.
When no v2 papers, require empty source maps and delegate exact complete v1
compile material, preserving bytes. For mixed papers, render legacy groups with
the unchanged v1 renderer and apply the same complete-set related links to all
paper/concept/code pages. Unchanged legacy inputs plus unchanged related set
produce byte-identical pages. Reject duplicate paper/code paths, case collisions,
primary-owner/claim conflicts, undeclared or unsafe output paths and unknown
taxonomy. Derive the full concept term set from prospective paper taxonomy; it
must equal supplied concepts, using pinned canonical labels.

V2 pages include all imported version refs, selected/unselected state, active
extraction mirror, all ten established sections and exact claim evidence links
with actual referenced association and assessment state. They use existing JSON
frontmatter escaping and safe Markdown escaping for every untrusted text field;
only derived safe filenames/IDs construct Wiki links and anchors. A provisional
page with no eligible core conclusion explicitly says it has no reviewed core
conclusion. Eligible means active core in one_sentence_conclusion with assessment
accepted/contested. At most three; a record with eligible conclusions must render
them. An accepted paper claim in some other section does not invent a conclusion.
Retired claims stay visible in evidence_status. Compiler outputs deterministic
sorted path->bytes; it produces no applied/published authority and no files.

## Validation and delivery

New schemas appear through installed engine registry (58 -> 65), each with a
valid labeled synthetic fixture. Required tests include all v1 IDs/fingerprints/
wire/compiler bytes unchanged, unknown vs explicit labels, same-byte reuse and
multi-version links, first-registration/historical-ledger proof tampering,
duplicate/conflicting inventory, selection/rollback and malformed chains,
non-ASCII and combining-character exact spans, anchor/cross-page behavior,
v1->v2 invalidation, human-profile bypass rejection, old/new mixed histories,
unselected/provisional rendering, hostile frontmatter/link text, complete mixed
compiler links, empty/legacy cases and source-map orphans. Independent reviews
must examine actual new pure semantics, not only fixture assertions. Run focused,
both locked Python full suites, installed-wheel resource/module byte checks,
and final exact candidate delivery + fresh four-job CI. No human gate is closed.
