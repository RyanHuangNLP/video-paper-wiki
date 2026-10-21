# SOURCE-CAPTURE R1: lightweight text into the formal source ledger

This is the first implementation slice of SOURCE in README.md. It implements an
actual prepare/inspect/admit handoff for the existing lightweight paper, without
copying a PDF or pretending that Markdown is a Docling artifact. SOURCE remains
incomplete until the subsequent version/locator/knowledge publication slice.

User authorization: “把剩余的TODO都完成了吧，cursor grok的权限我都approve”.
Use ordinary Cursor approval with the pinned Grok 4.6 Extra High Fast model. The
source worktree and baseline are recorded in SOURCE-CAPTURE-freeze-r1.json before
dispatch. Builder owns only its exact allowlist, returns a hashed candidate and
development brief, then stops. No Git, new workers, remote publication, real Vault
mutation, vpwiki-admin, PDF submission, model installation, or human approval.

## Existing interfaces and compatibility

Reuse the retained staging/session machinery, generic `capture` transaction
inspection, pinned `verify_pinned_source_id`, source-ledger v1 and the existing
knowledge-publication request/inspection. `.raw/captured/<sha>.md` is already a
valid generic capture path and a valid file/document source-ledger locator.
Capture itself does not create a canonical source claim; source registration
uses an ingest publication that claims the raw input. Keep these stages distinct.

Do not change or route through ingest-plan.v1, approval-ref.v1, PDF capture, code
capture, PDF source admission, paper-record.v1, Docling schemas, or legacy evidence
locators. Ingest-plan.v1 fixes a Docling parser, so it is unsuitable here. New
Markdown schemas and semantic validation live in the engine; the research adapter
reads lightweight input and provides the user entrypoint. No parallel source ledger.

## Frozen objects

All new JSON objects are closed, integer-only canonical JSON, with validated
lowercase SHA-256 values, canonical paper IDs, portable names, bounded strings,
and no unknown keys. Schema registry and installed-wheel resources expose them.
Hashes below mean SHA-256 of exact bytes, or of canonical JSON where stated.

1. `video-paper-wiki.markdown-source-observation.v1`:
   `schema`, `paper_id`, `light_paper_id`, `title`, `version`, `markdown`,
   `source_metadata_sha256`, `original_pdf_sha256`, `pages`.
   `paper_id` is the explicitly selected canonical entity (defaults to the light
   ID); `light_paper_id` is the existing sha256 paper ID. `version` is the closed
   object `{kind: "unknown", label: null}` or `{kind: "declared", label: string}`;
   declared labels are bounded nonempty human labels, not verified arXiv metadata.
   `markdown` is `{sha256, size_bytes}` (1..8 MiB). Original PDF hash is provenance
   copied from the validated lightweight source identity (nullable when unavailable);
   never read/copy that PDF.
   Each page is `{page, anchor, text_start, text_end, text_sha256}` with 1-based
   page, matching `page-N` anchor and half-open Unicode-character spans. Preserve
   exact source.md bytes; do not silently normalize text or invent coordinates.
   Recompute page anchors/spans/hashes using current lightweight rules. Reject
   stale metadata, missing/duplicate anchors, invalid UTF-8/NUL and no usable text.
   Metadata hash binds the exact source.json bytes; raw source.json/path strings
   are not copied into canonical source-ledger fields. Maximum 300 pages.

2. `video-paper-wiki.markdown-capture-plan.v1`:
   `schema`, `batch_id`, `observation`, `workspace_root`, `source_markdown_path`,
   `source_metadata_path`, `limits`, `pipeline`.
   Source paths are the two exact relative lightweight slots for light_paper_id;
   workspace_root names a validated existing .work workspace, with the caller's
   supplied path checked before resolve/normpath. `limits` is exactly
   `{max_markdown_bytes: 8388608, max_metadata_bytes: 1048576, max_pages: 300,
   max_requests: 0}`. `pipeline` is exactly `{engine: "markdown-native",
   version: "1", normalization: "preserve-exact-utf8"}`.
   No claim that this plan proves paper entity/version correctness or permission.

3. `video-paper-wiki.markdown-capture-approval-ref.v1`:
   `schema`, `plan_sha256`, `batch_id`, `paper_id`, `markdown_sha256`.
   This is a desensitized, externally supplied reference bound to the exact plan;
   it is distinct from legacy approval-ref.v1. Validate every field against that
   plan. Agent code must not generate, default, or issue this reference. Like the
   existing handoff, matching digests establish binding, not cryptographic proof
   of a human decision or permission to apply. Tests may supply explicit fixtures.

4. `video-paper-wiki.markdown-capture-request.v1`:
   `schema`, `plan`, `plan_sha256`, `approval_ref`, `approval_ref_sha256`,
   `payload_file`. Nested plan/ref validate under the above schemas; all hashes
   bind canonical bytes. payload_file is exactly
   `markdown-source/<markdown.sha256>.md` within that same batch.

5. `video-paper-wiki.markdown-capture-authority.v1`:
   `schema`, `requested_operation_id`, `request`, `request_sha256`, `disposition`,
   `stored_path`, `source_id`, `transaction_staging`, `upstream_authority`.
   stored_path is exactly `.raw/captured/<markdown.sha256>.md`; source_id is the
   actual pinned file-source ID for this path/hash. disposition is create/reuse.
   Create requires the generic capture transaction/staging: exact operation ID,
   one business create of the Markdown bytes with expected old hash null, no
   unrelated business/read/input paths, exact bundle/declaration/content hashes.
   Use the existing validators for each transport/authority layer and check all
   cross-object bindings. Reuse requires both child authorities null and verified
   existing identical bytes in that exact .md slot; it must not invent an applied
   operation ID, receipt or source registration. requested_operation_id remains
   only the user's request label. Other-extension siblings with the same digest,
   multiple siblings, changed bytes or unsafe entries are explicit conflicts.

No object in this slice claims a canonical source-version association, accepted
claim, display head or published paper page. The next slice consumes the exact
observation and source ID; it preserves unknown/declared version provenance.

## Public operations

Expose `vpwiki-research formal-source` subcommands and matching Python functions:

- `plan --workspace-root PATH --paper-id LIGHT_ID [--canonical-paper-id ID]
  [--version-label TEXT] --batch-id ID`: read/validate the exact lightweight
  source.md/source.json snapshot and stage a canonical plan at
  `.work/<batch>/markdown-source/plan.json`; return its path/hash/observation and
  `awaiting_external_approval`. No index or PDF read is required. Existing bytes
  reuse exactly; conflicts refuse; no user notes/library data change.
- `prepare --plan PATH --approval-ref PATH`: the plan must be in that fixed slot;
  re-read and bind its original source inputs, validate the supplied reference,
  then stage the exact Markdown payload and canonical `request.json` in the same
  markdown-source directory. Return path/hash and `awaiting_capture_inspect`.
  A missing ref is a clear approval-required result with no prepared authority.
- `inspect --prepared PATH --operation-id ID --upstream-root PATH
  --vault-root PATH`: require fixed `.work/<batch>/markdown-source/request.json`,
  verify plan/request/payload and approval binding, and inspect generic capture
  through the actual pinned upstream adapter. Return the validated authority and
  `awaiting_operator_capture` for create or `capture_reused` for reuse. The formal
  Vault is read-only. No PDF/code adapter and no arbitrary source path fallback.
- `bind-result --authority PATH --result PATH --before PATH --after PATH`: bind
  the externally supplied actual generic capture apply result and before/after
  descriptors using existing bind_operation_result. Require a create authority
  and its exact inspected transaction; return the existing
  operation-result-authority.v1 object. Never perform apply, synthesize a result
  or infer before/after snapshots from desired values. This is an evidence-binding
  helper; caller assertions are not cryptographic execution attestation.
- `admit --authority PATH --batch-id ID --operation-id ID --vault-root PATH
  --upstream-root PATH --ingested-at UTC [--capture-result PATH]`: require validated Markdown authority,
  safe matching captured bytes and a valid existing canonical receipt chain
  (otherwise name genesis/bootstrap as next action). Verify pinned source ID.
  For first registration require a supplied operation-result-authority.v1 for
  the generic capture: its create business write must be exactly this .md
  path/hash/size, its actual after hash/mode must match the retained current raw
  file, and for a create authority its inspected transaction must match that
  authority after removing the runtime_result attachment. A reuse authority can
  cite the prior exact-content capture result. No matching result means refusal;
  a manually placed raw orphan must not be presented as proven capture. Capture
  has no canonical operation receipt by design; do not invent or require one.
  Already registered, receipt-claimed exact sources may prove provenance from
  that current audited source registration without a separate capture result.
  Stage existing source-ledger ingest publication using the standard file/document
  source record and claimed raw path. That publication, once operator-applied,
  makes the source receipt-backed; capture bytes alone do not. `title` comes from
  the bound observation. Date is an actually valid canonical UTC timestamp.
  If an exact source ID/path/hash is already registered and receipt-claimed,
  return `source_already_registered` with no staged mutation; incompatible
  existing ID/path/hash rows or raw claim without the matching source refuse.
  Return `source_registration_prepared`, inspectable publication request and
  `awaiting_operator_publication` otherwise. published=false/receipt_backed=false
  describe that pending registration; do not label its future output applied.
  Admission batch/operation IDs name a new ingest transaction and must be
  distinct from a create capture's operation/batch IDs; they are not substituted
  into or falsely compared equal to the prior capture request. All returned
  nested publication IDs bind the new requested admission IDs.

The code does not install or call vpwiki-admin. Existing isolated fixture tests
may use the pinned vendor transaction apply helper to verify real transport;
fixtures, sample refs and receipt material must be clearly test-only. The public
agent flow stops at inspectable handoffs. Research CLI follows its established
single JSON envelope and error exit behavior; errors must never print tracebacks
or return success after malformed JSON, missing files or internal refusal.

## I/O and failure contract

All generated paths stay under the checked checkout's .work. Preserve existing
private files and all inputs. Stable fixed-slot reads include every original
named ancestor, not merely a normalized final path. Refuse parent traversal,
symlinked paths, hardlinks, special files, oversized input, unsafe intermediate
directories and persistent replacement even if replacement bytes are identical.
Retain a batch descriptor lineage for each compound prepare/inspect operation;
retain the markdown-source directory and relevant existing/missing fixed slots,
not just a before/after root stat. Check all named edges and expected bytes on
success and exception paths; a changed lineage overrides a child/parser error.
Preserve already staged files on conflict and never overwrite competing bytes.
No repeated independent stage_bytes calls may split one multi-file operation
across directory lineages. Reuse established low-level staging helpers where
appropriate; new narrow helpers may live in the new module without changing old
PDF/code behavior. Complete-set checking applies to the dedicated
markdown-source directory: plan plus optional exact digest payload/request at
the appropriate stage. Unknown entries and unexpected empty directories refuse.
Transaction transport retains the accepted complete-set behavior.

Use capture_snapshot for the complete captured sibling set and its all-exits
lineage checks. Admission must bind the source-ledger snapshot and claimed raw
path through existing publication inspection/preconditions; recheck inputs around
staging and before returning. No check may treat invalid/unknown authority as
already registered. Duplicate JSON keys, nonfinite numbers, recursion and invalid
Unicode receive a closed stable error. New semantic codes:
MARKDOWN_SOURCE_INVALID, MARKDOWN_SOURCE_STALE, MARKDOWN_PLAN_INVALID,
MARKDOWN_APPROVAL_REQUIRED, MARKDOWN_APPROVAL_MISMATCH,
MARKDOWN_REQUEST_MISMATCH, MARKDOWN_AUTHORITY_MISMATCH,
MARKDOWN_CAPTURE_CONFLICT, MARKDOWN_SOURCE_CONFLICT. Preserve useful existing
WORK_PATH_UNSAFE, RECEIPT_BOOTSTRAP_REQUIRED, and pinned-adapter error codes.

## Required acceptance

Meaningful tests must exercise plan/prepare/inspect/admit through real functions
and public CLI, including actual pinned generic capture + source-ledger ingest
in an isolated fixture Vault. Verify the existing audit and source projection
accept the registered .md source; no PDF, code manifest or Docling file is
generated. Prove zero network in public entrypoints and no input/Vault writes.

Cover exact idempotence; declaration and payload tampering; every approval field;
unknown/version-declared state; changed source.md or metadata; malformed JSON and
limits; source-path traversal and symlinks before normalization; same-byte inode
replacement during both success and failure; missing request/payload slots that
appear mid-operation; captured directory change; other-extension/multiple
siblings; partial staging retry/conflict; source registration duplicate/conflict;
receipt bootstrap; and refusal of legacy/cross-kind objects. Preserve old tests.
Candidate report binds every changed path and actual results; no fake full-suite
or real-data assertion. Run focused tests before stopping. Architect and the
independent reviewer own subsequent full regressions/wheel/actual-source checks.

Builder may implement only the exact allowlist in the freeze. Report a necessary
unlisted change as a contract gap; do not silently broaden the old schemas. This
slice is engineering source admission, not completion of all SOURCE or TODO work.
