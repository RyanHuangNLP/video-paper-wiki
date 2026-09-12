# Lightweight research v1 — contract revision 1

This contract implements the user's 2026-09-08 “安排开发吧” instruction following
the four-feature recommendation. BASE is
6963292a93ae322eaf9bb563b7b1170dee6a6fc6. It is a review draft until freeze.json
binds its bytes and the lane packets. Existing features and historical evidence
remain valid at their own revisions; new code needs new acceptance and CI.

## Shared behavior

Public APIs return JSON objects with ok/status/message, preserving existing
closed statuses and ResearchError CLI handling. No expected bad input causes a
traceback. New invalid/conflict statuses are QUERY_REWRITE_INVALID,
LIGHT_BATCH_INVALID/CONFLICT/INCOMPLETE, LIGHT_REFRESH_INVALID/CONFLICT and
LIGHT_WRITING_PROJECT_INVALID/CONFLICT. Preserve INDEX_STALE, SOURCE_INVALID,
LIGHT_SELECTION_INVALID, LIGHT_CONTEXT_INVALID and LIGHT_WORKSPACE_BUSY.

All new product workspace/generated paths contain .work in both given absolute
and resolved paths, without symlink traversal. Preserve regular-file, hardlink,
UTF-8, duplicate-key, finite-number and size checks. Generated immutable data is
canonical sorted-key compact JSON, ensure_ascii=False, allow_nan=False, one LF;
content hashes omit LF, file hashes include it. Reject unknown identity/schema
fields, malformed IDs, duplicate selections and unsupported bounds. Caller
rehashing never substitutes for checking actual referenced records/source.

Use the existing nonblocking workspace lock for mutations and state-sensitive
exports. Publish create-only immutable files/bundles atomically, after validating
complete byte sets; replace only a managed validated expected-head pointer.
Concurrent stale parent/head changes are conflicts. Preserve external edits,
unknown entries and prior records. A refused operation cannot overwrite user
artifacts. Exact retry can reuse validated identical bytes. Recognized interrupted
owned publication must be recoverable by exact retry; unknown/ambiguous state
requires attention and is never age-deleted. Existing process-interruption
scope applies; do not claim arbitrary hostile races or power-loss durability.

Python remains zero-egress and dependency-free beyond the locked environment.
The current conversation model authors rewrites, summaries, outlines and draft
sections. These remain model suggestions, not scientifically reviewed facts.
Only validated source chunk IDs authorize citations; translations, earlier
model prose and a self-hash are not new source evidence. Preserve Unicode slice
offsets, actual page anchors and source byte identity. No original PDF copy,
real Vault/admin/receipt authority, seed/overlay changes or online discovery.

Keep legacy light-context kinds qa|writing, legacy workflow request/session
schemas, knowledge export/import and writing export/import compatible. New
raw handoff flows save their JSON under .work and are driven by the Skill;
they do not claim that the old workflow supports new session kinds.

## T1 — Chinese questions over English evidence

Add light_query.py with public
export_rewritten_context(workspace_root, *, kind, query, rewrite,
requirements="", paper_ids=None) -> dict. kind is qa|writing. The original query
must be a nonblank string of at most 2,000 Unicode characters. requirements
retains existing semantics. rewrite is exactly:

    {"schema":"video-paper-wiki.light-query-rewrite.v1",
     "original_query":"the exact original question",
     "rewritten_query":"English lexical search terms","language":"en"}

The rewrite is supplied by the current model, not by a fixed translation
dictionary. rewritten_query is nonblank, at most 2,000 characters, contains a
Latin letter and no control characters; language is exactly en. original_query
must equal query byte-for-byte. Reject other keys, types, languages and limits.
Preserve model/user wording; do not fabricate a translation-quality guarantee.

Always search original plus rewritten_query with the existing BM25 algorithm
and the same explicit paper selection. Deduplicate identical query strings.
Each route returns at most 24 candidates. Fuse by exact chunk_id with equal
weight reciprocal ranks sum(1/(60+one_based_rank)), sort descending then by
chunk_id, and keep at most 8 final chunks. Evidence text/identity stays byte
exact; only the finite score becomes the fused rank. All routes must bind one
current index/source snapshot. A matching index_id alone is insufficient:
perform final live evidence/source validation. No stale route can be treated
as an empty route. Original-only or rewrite-only hits can succeed; both empty
returns NO_RESULTS without invented evidence.

Return the usual light-context.v1 of the requested kind, with query remaining
the original question. Add query_plan metadata binding the exact rewrite object
and its canonical hash, fixed fusion version/limits and per-route status/ranks.
This trace is diagnostic retrieval provenance; citations still come only from
the evidence array. On import, validate query_plan when present against its
shape, original query, selection, fixed algorithm and live recomputed retrieval.
Legacy contexts lacking query_plan remain unchanged. Avoid circular imports by
using a pure trace validator or a narrow local import in live validation.

T1 owns light_context.py for this optional validation and adds .light-writing
to its managed-output roots. It may add a private batch-search helper to
light_index.py if needed; do not change legacy search ranking/return values.
T3 exposes optional --rewrite JSON only for workspace qa export and writing
export. Parse with the existing secure handoff JSON reader. Reject the flag on
the legacy Vault/catalog route. Existing qa/writing import accepts the resulting
context and checks the trace. Skill creates the rewrite internally and uses
direct export/import for this route; no new workflow kind/request fields.

### Frozen query trace

query_plan has exactly schema, original_query, rewrite, rewrite_sha256,
workspace_id, index_id, selected_paper_ids, paper_snapshots, fusion, routes,
fused, plan_sha256. schema is video-paper-wiki.light-query-plan.v1. workspace_id
hashes canonical {workspace_root: resolved_absolute_workspace}; rewrite is the
exact checked four-field object and rewrite_sha256 hashes its canonical bytes.
plan_sha256 hashes canonical query_plan excluding only plan_sha256. It provides
content identity, not authority to invent evidence. original_query equals the
context query and rewrite.original_query. selected_paper_ids is the exact
normalized explicit selection (empty means all present), with no duplicates.
paper_snapshots is sorted by paper_id and contains exactly paper_id,
markdown_sha256,source_json_sha256 for every selected paper, or all current
papers when selection is empty. index_id binds the actual complete index/source
snapshot; recheck its currentness and these actual paper bytes at the end.

fusion is exactly {algorithm:"rrf-v1",rank_constant:60,candidate_k:24,top_k:8}.
routes is ordered original then rewrite; when the two query strings are exactly
equal it contains only original. Each route is exactly name,query,status,
index_id,candidates. name is original|rewrite with those corresponding strings;
status is OK|NO_RESULTS only. A stale/invalid/unsafe route aborts with its closed
backend status, never an OK/NO_RESULTS route. All route index_id values equal
the plan index_id. OK candidates are 1–24 exact backend-rank rows with keys
chunk_id,rank,score; rank is consecutive one-based integer, score is the finite
original BM25 score, chunk IDs are unique per route. NO_RESULTS candidates=[].

fused contains at most eight rows, exactly chunk_id,score,route_names.
route_names lists the routes containing that chunk in original/rewrite order;
score is the prescribed sum of reciprocal ranks in that order. Sort by
descending fused score and chunk_id. Fused rows and context evidence must have
exactly the same ordered IDs and scores; all evidence identity/text remains
that of the checked live backend candidates. Import recomputes routes, selected
source snapshots, fusion and the whole trace from the live index and exact
rewrite; compare all fields and final evidence, rejecting unknown keys/types,
invalid ranks, boolean numeric impostors or caller-only recomputed hashes.

Both routes missing returns the usual unsuccessful empty light-context.v1
status=NO_RESULTS, with this valid diagnostic trace and fused=[], evidence=[].
It is not an importable successful context. Recheck index/source snapshot even
on this empty path. Other closed errors need no query_plan and never emit a
successful context. Avoid recursive validation by separating raw retrieval/
trace construction from the public context-export/live-validation functions.

## T2 — complete long-paper batch knowledge

Add light_knowledge_batch.py; preserve the legacy one-shot protocol. Public APIs:

- plan_knowledge_batches(workspace_root, *, paper_id) -> dict
- export_knowledge_batch(workspace_root, *, plan_id, batch_index) -> dict
- import_knowledge_batch(workspace_root, context, document) -> dict
- knowledge_batch_status(workspace_root, *, plan_id=None) -> dict (read-only)
- export_knowledge_merge_context(workspace_root, *, plan_id) -> dict
- import_knowledge_merge(workspace_root, context, document) -> dict
- finalize_knowledge_batches(workspace_root, *, plan_id) -> dict

Plans bind workspace, exact current index, paper snapshot and the complete
derived-chunk inventory. Sort by page/text_start/text_end/chunk_id and greedily
partition without splitting chunks: at most 48 chunks and 80,000 sum(len(text))
per batch. Every eligible chunk occurs exactly once. At most 128 batches;
oversized single chunks or paper/plan limits return an explicit unsupported
gap/size result before creating an active job. Never silently skip content.
No derived evidence in full mode returns INSUFFICIENT_EVIDENCE without a job.
plan_id hashes the canonical plan identity, including partition, inventory,
mode, expected base head and resolved workspace identity. workspace_id is the
hash of canonical {workspace_root: resolved_absolute_workspace}. Inventory rows
are identity-only, exactly chunk_id, paper_id, page, text_start, text_end and
text_sha256; never put source text in the plan. Batch indices are zero-based;
booleans are not integers. Export/import may not resume a copied job under a
different workspace identity, including a restored historical job.

Durable jobs live at .light-knowledge/batch-jobs/<plan_id>/. A validated canonical
plan.json, immutable batches/<index>.json, merges/<step>.json and completion.json
are a versioned producer-owned layout. Each batch/step is one atomic JSON file
binding context/document/parent/source hashes; actual file sets and types must
be checked. Use a separately owned short publication stage, with explicit
identity/retry validation, under .light-knowledge/staging. Do not reinterpret
legacy unknown stages as new owned work. A pending batch job or partial stage
blocks backup with an actionable finish/retry message. The blocker scans all
batch-jobs: missing completion is pending; unknown/tampered jobs conflict; a
completed job with a remaining publication stage still blocks. Return plan ID,
missing batches/next step where safely known. Only valid completed jobs without
pending stages are included byte-exact as history. Extend backup recognition
narrowly and test it. Completion bytes must publish before cleaning only an
exact verified owned stage; retain the completed job's provenance permanently.
Distinguish historical integrity from live resumability: a valid completed job
after backup relocation remains includable/readable history, although its old
absolute model contexts cannot resume as a job in the new workspace.

Batch export returns a versioned wrapper with plan_id, plan hash, batch_index,
batch_count, coverage, paper_snapshot, existing writing context and prompt.
Only that batch's actual chunks go to the model. On import recompute the
expected export against actual current source and exact plan. Batch documents
use light-knowledge-document.v1 and existing cited block/concept checks, plus a
32,000-character canonical-JSON cap. All-unknown batch documents are allowed as
processed evidence; they do not create a knowledge record or advance HEAD.
Exact duplicate imports reuse; different document bytes in an accepted batch
slot conflict. Missing batches, extras, changed source or malformed jobs remain
visible as incomplete/stale/conflict. Status reports total/accepted/missing
batches and planned/processed chunks, with no full source prose.

Merge is a deterministic rolling accumulator, consumed in batch order. Each
model-facing merge context includes only the prior checked accumulator and the
next checked batch document, compact identity/coverage and prompt. It must fit
80,000 canonical JSON Unicode characters; each document is capped at 32,000.
The first context has no accumulator and batch zero. Each immutable merge step
binds exact plan, zero-based step, parent step hash and next batch document hash.
Skip/reorder/duplicate-different steps refuse. The next export automatically
finds the first missing step from a validated contiguous chain.

Merge document shape is the same cited knowledge document, with the same 32k
cap and provisional/unknown rules. Permitted citations are the union of IDs
actually cited by the preceding accumulator and the next batch document; a
discarded earlier citation cannot be silently resurrected. Locally verify those
IDs against the original accepted batch evidence and live derived chunks.
All-unknown accumulators are allowed internally. No raw whole-paper context is
sent again to the model, and no silent text truncation is allowed.

Finalize requires the exact complete batch partition, complete contiguous merge
chain and unchanged source/index. Full-mode finalization publishes one normal
immutable knowledge record and advances the expected head only then. The record
must work with existing list/views/backup and preserve earlier records/notes.
It may store only the final document's actually cited raw evidence, plus full
compact chunk inventory/processing coverage and batch-chain provenance in its
validated wrapper. Retain a known versioned wrapper discriminator; do not
weaken legacy import into accepting arbitrary custom evidence. New record
validation must distinguish legacy and batch/refresh wrappers explicitly.

New stored identity wrappers have exactly the existing six identity keys:
schema, paper_id, context, coverage, paper_snapshot and prompt. The schema is
video-paper-wiki.light-knowledge-batch-record-context.v1 or
video-paper-wiki.light-knowledge-refresh-record-context.v1. coverage has exactly
mode (full|refresh|selection), processing_complete (true), inventory (the complete
sorted identity rows), planned_chunks, processed_chunks, batch_count,
gap_chunk_ids (empty), and provenance. Counts are bounded nonnegative integers,
never booleans; processed_chunks equals the complete current inventory size.
provenance is exactly plan_id, plan_sha256, merge_sha256, base_record_id,
candidate_record_id, accepted_sections, accept_concepts. Full mode uses null for
base/candidate/acceptance fields; refresh uses its base and null candidate/
acceptance; selection binds base, candidate, exact selection and boolean. A
zero-batch refresh uses null merge_sha256. These nullable fields are present.
Hash values/IDs use lowercase 64 hex or null only where specified.
Record validation checks the discriminator, exact nested keys, identities,
counts, citation ownership and referenced immutable job/record provenance.
Resolve references only from validated IDs into known relative owned roots;
reject cycles and bound ancestry traversal to 128 records. Do not follow stored
absolute paths. Historical validation preserves relocation, while currentness
requires matching actual source bytes and imports require the current workspace.
Legacy stored wrappers retain their exact legacy shape/behavior, and legacy
import still accepts only its own freshly recomputed one-shot export.

Report processing_complete, planned_chunks, processed_chunks, batch_count and
omitted/gap lists. Processing coverage is not a claim that every fact appears
in the model summary. A final all-unknown document records a terminal closed
INSUFFICIENT_EVIDENCE completion and does not advance HEAD. Failed publication
must preserve the previous head and be retryable from immutable inputs.

## T2 — selective incremental refresh

Public APIs in light_knowledge_refresh.py:

- plan_knowledge_refresh(workspace_root, *, paper_id) -> dict
- export_knowledge_diff(workspace_root, *, base_record_id, candidate_record_id)
- apply_knowledge_refresh(workspace_root, diff, *, accept_sections,
  accept_concepts) -> dict

Refresh requires an existing validated base head for the same paper_id and a
current index. A library PDF replacement with a different digest starts a new
paper knowledge plan; old-paper facts must not become new-paper facts by alias.
Detect actual content deltas using the old complete inventory when available.
Chunk IDs can change with source digest/offsets: match only unique equal
(page,text_sha256) pairs, checking actual stored cited text where it is present,
and remap to the live chunk's exact ID/offset/hash. Ambiguous matches are changed.
For legacy incomplete inventories, explicitly report conservative_full_refresh
and process all current chunks rather than claiming an exact unseen delta.

Return retained/added/changed-or-removed chunk information, affected sections,
base record/head identity and a refresh-mode batch plan. Seed its accumulator
with old blocks whose every citation safely remaps; invalid old blocks become
unknown. Process new/changed evidence in bounded batches with the same merge
chain. Removed evidence invalidates its old blocks even when there are no added
chunks. A metadata-only refresh may need zero model batches. Bind the complete
current inventory so final processing coverage accounts for retained plus
processed delta chunks. Detect changed base head before any final adoption.

Refresh finalization creates a current candidate record but DOES NOT advance
HEAD. export_knowledge_diff returns the checked base/candidate snapshots and
before/after per-section/concept values, changed flags and retain_allowed state.
The diff is a reviewable deterministic object with a content identity, not a
model assertion. It binds base_head_record_id, candidate_record_id and actual
source/index snapshot. It must not hide stale old citations or change any note.

apply accepts an explicit unique subset of the eight known section keys and an
explicit boolean for concepts. Recompute the exact diff, verify current source
and expected base head, then form the chosen new record. Accepted fields use
candidate values; unaccepted fields retain only provably-current remapped old
values, otherwise become unknown (or omit invalid concepts), with this outcome
visible in the diff and result. Never label stale old evidence current. No
silent all-section acceptance. accept_sections can be empty; accept_concepts
must be supplied, with no implicit default. Reject an all-unknown final result. Publish a new
immutable record before advancing HEAD; preserve base/candidate/previous notes.
Exact retry may reuse the known result; a different intervening head conflicts.

No refresh operation edits knowledge/notes.md, paper notes or caller Markdown.
User-edited managed records are conflicts and are preserved. Tests must cover
retained content despite shifted offsets, deleted/changed evidence, no-delta
metadata edits, conservative legacy refresh, selective rejection and head drift.

## T3 — outlines and section revision history

Add light_writing_project.py without changing legacy light_writing behavior.
Public APIs:

- export_writing_outline(workspace_root, context) -> dict
- import_writing_outline(workspace_root, context, document) -> dict
- export_writing_section(workspace_root, *, project_id, section_id,
  instructions="") -> dict
- import_writing_section(workspace_root, context, document) -> dict
- writing_project_history(workspace_root, *, project_id) -> dict (read-only)
- export_writing_project(workspace_root, *, project_id, output) -> dict

Outline input is an existing successful live kind=writing light-context, from
normal or rewritten writing export. Revalidate exact current evidence; retain
topic/query, requirements and selected papers. Outline wrapper binds the inner
context hash and prompt. Model outline document is exactly:

    {"schema":"video-paper-wiki.light-writing-outline.v1","title":"...",
     "sections":[{"section_id":"s1","title":"...","goal":"...",
                  "status":"provisional","citations":["chunk_id"]}]}

There are 1–16 ordered sections, unique IDs matching s[1-9][0-9]?, title 1–300
characters, goal 1–2,000 characters, no control characters or caller citation
marks in titles/goals. Each section is provisional with 1–32 unique valid
evidence citations, or unknown with no citations and goal exactly 证据不足.
At least one section must be provisional. No invented sources or references.

Import creates a content-addressed project and immutable initial outline
revision, plus a validated per-project HEAD pointer. Storage is
.light-writing/projects/<project_id>/revisions/<revision_id>/ with context.json,
document.json, manifest.json and draft.md, and a per-project HEAD.json. Bind
parent_revision_id (null for the outline), exact document/context/file hashes,
project identity and section order. Use owned .light-writing/staging for atomic
bundle publication and head updates. T3 narrowly extends backup to refuse
pending writing publication; completed history is included byte-exact. T1 owns
the corresponding managed-output root protection in light_context.py.

Initial sections are visibly unwritten. Section export reads the exact checked
HEAD and target section, includes the original bounded writing evidence, outline
and current target text, and optional instructions (at most 4,000 characters).
Bind project_id, parent_revision_id and section_id. The source must still be
current; source change requires fresh writing context/new project while old
history stays readable. Do not pretend old absolute contexts can resume after
workspace relocation; history remains available as historical content.

Section document is exactly schema=video-paper-wiki.light-writing-section.v1,
project_id, section_id, status, markdown and citations. Provisional Markdown is
nonblank, <=16,000 characters, and uses the existing exact [@chunk_id] marks and
citations equality checks with 1–32 distinct current evidence citations. Unknown
uses Markdown 证据不足 and no citations. Validate prior complete revision and new
document, replace only the selected section value, and create a new revision.
All other section values and previous files remain unchanged. Repeated edits
produce a parent-linked immutable history. Old parent, wrong section/project,
tampered file, stale source or invalid citation cannot advance HEAD.

Render readable provisional Markdown with ordered headings, pending/unknown
labels, output-relative source page links and deduplicated references. History
returns revision IDs/parents/currentness/section progress without full paper
text. Export creates an explicit .work Markdown artifact, preserving existing
different bytes; identical valid bytes can reuse. It reports incomplete sections
instead of claiming a finished article. Refuse exporting a wholly unwritten or
all-unknown article as a completed draft. External edited exports are preserved.

### Frozen writing wire/storage details

Model-facing outline and section export wrappers have an 80,000-character
canonical JSON cap; oversized inputs close with LIGHT_WRITING_PROJECT_INVALID,
never truncation. The model outline document additionally has a 32,000-character
canonical cap. Section body length remains 16,000. These limits bound prompts
even if a caller supplies a nonstandard large existing writing context.

Outline export exact keys: ok, status, message, schema, context,
context_sha256, prompt. schema is
video-paper-wiki.light-writing-outline-context.v1. Success is ok=true/status=OK;
message/prompt are fixed producer constants. Import receives this whole object,
checks exact keys, inner bytes/hash/currentness, and compares its canonical
identity with a fresh export. Failed exports are never usable imports.

Section export exact keys: ok, status, message, schema, project_id,
parent_revision_id, section_id, context, context_sha256, outline,
previous_section, instructions, prompt, wrapper_sha256. schema is
video-paper-wiki.light-writing-section-context.v1. context is the original
writing evidence context, outline is the original checked model outline,
previous_section is the exact current section state. wrapper_sha256 hashes the
canonical wrapper without wrapper_sha256. First import re-exports from the exact
expected parent HEAD with frozen instructions and compares all fields, not
merely the caller hash. An exact retry after HEAD advanced to that import's
computed result validates the same referenced parent and already published
result instead; it does not regenerate a new wrapper against the child head.
Unknown/missing wrapper or model-document fields refuse.

All project/revision/hash IDs are 64 lowercase hex. project_id hashes canonical
{schema:"video-paper-wiki.light-writing-project.v1", context, outline}.
Persisted document.json is exactly schema, project_id, parent_revision_id,
kind, target_section_id, instructions, title, outline, sections. schema is
video-paper-wiki.light-writing-revision.v1. Initial kind=outline,
parent_revision_id=null, target_section_id=null, instructions=""; successors
use kind=section and their exact parent, target and instruction text. title and
outline always equal the original model outline values. sections is ordered
like outline, each object exactly section_id,status,markdown,citations. Initial
status=unwritten, markdown="", citations=[]; subsequent target values use the
checked provisional/unknown document. Other sections stay identical values.

revision_id hashes canonical {schema:
"video-paper-wiki.light-writing-revision-identity.v1",project_id,
parent_revision_id,context_sha256,document}. context.json is always the exact
original writing context. manifest.json has exactly schema, project_id,
revision_id,parent_revision_id,context_sha256,document_sha256,files. schema is
video-paper-wiki.light-writing-revision-manifest.v1; files is sorted exact
path/sha256/size_bytes rows for context.json,document.json,draft.md. A revision
directory contains exactly those three files plus manifest.json, no extra
files/directories. HEAD.json is exactly schema,project_id,revision_id, with
schema=video-paper-wiki.light-writing-head.v1. IDs and every duplicate binding
are validated against actual stored bytes and parent relations.

Read/replay the initial outline and at most 128 ancestry revisions, rejecting
cycles, skipped/foreign parents or malformed roots. Before advancing HEAD,
recheck expected parent and source. Exact retry can reuse an already published
expected target revision and current HEAD at that revision; another current
head conflicts. Do not turn a retry into another child revision. An identical
section reimport has the same target revision ID. A failed pointer publication
may leave a validated immutable orphan revision for exact retry, never a false
successful current head. A first project may lack HEAD only while recognized
owned publication is incomplete; read-only history reports it as pending.

Rendering must be deterministic from checked original context/outline and
section state: one title, provisional-model label, outline-order headings,
unwritten text 尚未撰写, unknown text 证据不足, then cited body and deduplicated
source-page references. Escape titles as Markdown labels. Do not require a
particular cosmetic whitespace beyond a single final LF and deterministic
bytes. Link hrefs are derived from actual cited sources relative to the target
draft location, including when exporting to an outside reports file.

Successful mutation results use schema=video-paper-wiki.light-writing-result.v1
and exactly ok,status,message,schema,project_id,revision_id,parent_revision_id,
page_path,reused,progress. progress is exactly total,written,unknown,unwritten,
complete; complete means no unwritten sections and at least one provisional
section, not scientific/human acceptance. History uses
video-paper-wiki.light-writing-history.v1 with ok,status,message,schema,
project_id,head_revision_id,revisions,diagnostics. Revision rows are exactly
revision_id,parent_revision_id,is_head,kind,target_section_id,source_status,
progress,page_path; diagnostics are bounded path/status/message objects.
History is read-only: valid old/relocated history is readable and explicitly
historical, source/index mismatch is stale, missing source is missing-source,
and bad bytes produce conflict diagnostics with ok=false. Never certify a
tampered old parent as a valid chain merely because HEAD itself is intact.

Project export uses video-paper-wiki.light-writing-export.v1 with
ok,status,message,schema,project_id,revision_id,path,reused,progress. It requires
live source/context; stale index uses INDEX_STALE, unsafe/invalid source uses
SOURCE_INVALID, relocated absolute context uses LIGHT_WORKSPACE_MISMATCH.
Outline/section live operations propagate those same existing statuses;
structural IDs/wrappers are LIGHT_WRITING_PROJECT_INVALID and publication,
parent or user-edit conflicts are LIGHT_WRITING_PROJECT_CONFLICT. Read-only
history diagnoses currentness and never resumes or repairs old contexts.

writing_backup_blockers(workspace_root) is read-only and returns a list of
exact {path,status,message} diagnostics. Missing .light-writing is []; safe
empty staging with no incomplete project is []; valid completed projects
with intact full ancestry are includable. Nonempty, unsafe or unknown staging,
missing/conflicting HEAD, edited/incomplete bundle or ambiguous orphan state
blocks backup and remains untouched. Validate historical integrity after
relocation independently from live-context resumability. Completed old projects
remain includable history. The helper performs no lock acquisition itself;
backup calls it under the existing workspace lock, avoiding recursive locking.

## Integration and acceptance

T3 owns CLI/Skill/docs/integration tests after all needed owner snapshots stop.
Wire knowledge batch-plan/export/import/status/merge-export/merge-import/finalize,
knowledge refresh-plan/diff/apply, writing outline-export/outline-import/
section-export/section-import/history/project-export, and qa/writing --rewrite.
Use existing secure object JSON readers. Repeat selections with one flag per
value. Help/docs must describe actual schemas/statuses and save returned JSON;
users need not construct transport JSON. Optional defaults must not broaden a
selection or accept changes implicitly.

The later integration freeze must implement these exact CLI argument surfaces;
all commands below require --workspace. JSON files use the existing secure
object reader (regular original path, strict UTF-8/duplicate/finite/depth/size
checks). Generated handoffs are saved from unmodified stdout JSON under .work.

- writing outline-export --context JSON
- writing outline-import --context JSON --document JSON
- writing section-export --project-id ID --section-id ID [--instructions TEXT]
- writing section-import --context JSON --document JSON
- writing history --project-id ID
- writing project-export --project-id ID --output MARKDOWN
- knowledge batch-plan --paper-id ID
- knowledge batch-export --plan-id ID --batch-index INTEGER
- knowledge batch-import --context JSON --document JSON
- knowledge batch-status [--plan-id ID]
- knowledge merge-export --plan-id ID
- knowledge merge-import --context JSON --document JSON
- knowledge finalize --plan-id ID
- knowledge refresh-plan --paper-id ID
- knowledge diff --base-record-id ID --candidate-record-id ID
- knowledge apply --diff JSON (--accept-section KEY repeated | --keep-sections)
  (--accept-concepts | --keep-concepts)

The two apply option groups are mutually exclusive and required; an explicit
--keep-sections passes []. Duplicate section selections refuse. qa export and
writing export retain existing flags and add optional --rewrite JSON only with
--workspace; duplicates in explicit --paper-id selection refuse for this new
route rather than silently changing the selected set. New rewrite contexts and
their model documents are read securely on light qa/writing import while the
legacy Vault route retains its established behavior. Argument misuse is USAGE;
bad handoff files are LIGHT_HANDOFF_INVALID, backend refusals retain their named
statuses. JSON success exits zero, closed result exits nonzero with no traceback.

T2 initially owns the small backup integration for batch jobs; after its stopped
handoff, T3 receives light_backup.py solely for writing-state recognition and
cross-feature validation. That transfer is explicit in a later integration
freeze. No simultaneous writers and no owner-module fixes by the integrator.

Run focused real-backend tests, then the integrated dual Python 3.12/3.13 suite,
isolated installed-wheel CLI checks, backup/restore round trips and Skill
validation. Add meaningful adversarial tests for complete coverage, source/parent
drift, foreign citations, bounded merge chains and selective field preservation.
Tests must fail if an owner implementation is absent; do not hide missing lanes
behind mocks, optional import skips or alternate editable package origins.

Real engineering trials use the three supplied VDM, SVD and VBench PDFs. Record
current-model authored Chinese rewrite questions, before/after lexical retrieval,
long-paper exact chunk coverage, at least one complete cited merged knowledge
record, selective refresh on an explicitly disposable derived-source copy, and
outline plus two section-edit revisions. Show actual outputs and independent
citation/notes/backup checks. Synthetic mutation trials are not new PDF source
truth or human scientific review. Source/prompt data sent to Cursor/Grok remains
within the user's already authorized development scope and normal tool review.

Only after stopped-source acceptance does Steward commit/push the exact manifest
to existing draft PR95. Bind current base, candidate head/tree, actual CI merge
checkout, run/attempt/jobs and all remaining limits. No merge/main/auto-merge or
closure of human gates is authorized by this contract.
