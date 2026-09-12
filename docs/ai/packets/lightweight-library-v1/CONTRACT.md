# Lightweight library v1 — contract revision 1

Architect contract for the user's 2026-09-08 instruction “那继续开发完成吧”, following the inventory and explicit discussion of remaining knowledge organization, paper maintenance, light backup/restore and basic comparison. This authorizes those bounded functional additions and real-paper engineering validation. It does not reopen the original full research-platform PRD.

Baseline: `3368c6435db166a285b4b0e2df00f5d6a7491956`, tree `fc317f13ad781a9121c15503c4f1d945c5fafe2a`. Dispatch authority is a separate `freeze.json` binding the exact contract and lane packets. Until it exists this document is a review draft.

## Outcome, ownership and limits

A user can organize supplied papers into cited structured notes and concept/related-paper views; list/edit/archive/restore/replace a paper without losing notes; compare selected papers in a cited conditions-aware table; and back up/verify/restore the lightweight workspace.

The existing lightweight QA/writing and recovery APIs remain compatible. All new product workspace roots must be beneath a `.work` path component in both the given absolute path and its resolved path, with no symlink traversal. The `.light-knowledge`, `knowledge`, `.light-library` and other relative directories below are children of that approved workspace, not exceptions outside `.work`. Existing draft-output behavior remains compatible. No copied original PDF, page images, OCR, Docling execution, model downloads, extra dependency/model client, embedding service, real Vault/operator/admin changes, automatic canonical publication, catalog/overlay changes (67), or remote paper/repository discovery. Python is zero-egress; the current conversation model authors knowledge/comparison documents. Model suggestions remain provisional. Valid citation structure is not proof of factual correctness.

The user's instruction now selects a dedicated lightweight backup increment. It does not decide the larger historical FABLE-008 formal Vault/checkpoint proposal. Old captured-PDF/receipt authority cannot be reused for this no-PDF-copy light workspace.

Three existing Luna/xhigh controllers each own one Cursor Builder, exact `cursor-grok-4.6-xhigh-fast`, normal Smart Auto. Astra freezes/reviews/accepts, and an existing controller later handles serialized Git/PR95/CI. No additional agents. Only Builder writes its production/tests. The new allowlists supersede the old completed 25-path packet for this increment; old evidence/workspaces are preserved.

- T1 owns knowledge/comparison modules, tests and the small protected-root addition to light_context.py.
- T2 owns library maintenance/backup modules, tests and necessary small PDF/index/workspace integration changes.
- T3 owns public CLI, Skill/docs and integration tests. It consumes stopped immutable T1/T2 snapshots; it never edits their implementation.
- Shared existing light_workflow.py, light_qa.py, light_writing.py, pyproject.toml, uv.lock, core engine and schemas stay unchanged. New exporters wrap existing kind=writing light-context; do not extend the old session kinds.

## Common behavior and persistence

Public Python APIs use Path workspace roots and return JSON-serializable dictionaries with `ok`, `status`, `message`; expected closed results have ok=false. Invalid arguments/unsafe paths may raise existing ResearchError. CLI maps these to actionable JSON/nonzero without traceback. No rejected operation may overwrite an existing user artifact. Validate types, finite values, identifier syntax, bounds, source identity and complete selections; do not silently broaden to all papers.

Use `sha256:<64 lowercase hex>` paper IDs. Preserve the current source.md/source.json layout, source PDF digest, page anchors and Unicode slice offsets. Existing source/index/citation validators remain authoritative. Unknown evidence IDs, mixed-paper citations, stale context, malformed anchors, changed source bytes and output aliases are refusals, with old bytes preserved.

New durable JSON uses UTF-8, sorted keys, ensure_ascii=False, separators comma/colon, nonfinite values forbidden, plus exactly one LF. Hash canonical JSON without LF where defining content identity; persisted-file hashes include the LF. Keep schema, identity and reference validation explicit; a recomputed self-hash does not replace checking actual referenced bytes.

Mutations acquire the existing nonblocking workspace lock via light_workflow._exclusive_lock(_workspace_lock_path(workspace), workspace); catch _Busy as LIGHT_WORKSPACE_BUSY. This coordinates new operations with workflow prepare. Maintenance also uses existing per-paper PDF locks for affected live papers. Preserve lock identities; do not unlink live advisory locks. Standalone legacy index/add and external editors are not magically serialized: observe source/file sets before and after, refuse detected change, and retain recoverable state. Process interruption is in scope; arbitrary hostile concurrent filesystem replacement and power-loss durability are not newly claimed.

All new input/output directory chains must reject symlink/nonregular/hardlinked file hazards and traversal; generated destinations are within the explicit workspace or an explicit approved .work backup/restore path. Stage complete bundles on the same filesystem and atomically publish to absent destinations. Reuse immutable bundles only after exact byte/hash/set validation. Unknown extra content and user-edited generated pages are preserved/refused, not recursively deleted. Managed pointers/journals may be atomically replaced only after validating their expected schema/identity. No destructive permanent paper deletion.

New module-specific errors may be LIGHT_KNOWLEDGE_INVALID/CONFLICT, LIGHT_COMPARISON_INVALID, LIGHT_LIBRARY_INVALID/CONFLICT/NEEDS_RECOVERY, LIGHT_BACKUP_INVALID/CONFLICT. Preserve existing INDEX_STALE, LIGHT_SELECTION_INVALID, LIGHT_CONTEXT_INVALID, LIGHT_OUTPUT_CONFLICT, SOURCE_INVALID, WORKSPACE_INVALID and LIGHT_WORKSPACE_BUSY meanings.

## T1 — structured knowledge

Public APIs in light_knowledge.py:

- `export_knowledge_context(workspace_root, *, paper_id) -> dict`
- `import_knowledge(workspace_root, context, document) -> dict`
- `list_knowledge(workspace_root) -> dict` (read-only)
- `build_knowledge_views(workspace_root) -> dict`

Exporter requires a current index and one present paper. It does not rebuild the index silently. Construct a successful existing kind=writing light-context from current derived evidence, then validate_live_context. Include bounded whole-paper coverage, not only one keyword hit: at most 48 chunks and 80,000 Unicode text characters, choose a deterministic page-spread selection, preserve complete chunk bytes, report total/exported chunks, omitted pages and truncated flag. If a whole chunk cannot fit, omit it rather than inventing a new locator. No evidence returns a closed result.

Return `schema=video-paper-wiki.light-knowledge-context.v1`, `paper_id`, `context` (existing light-context.v1), `context_sha256` of its canonical bytes, `coverage`, `paper_snapshot` binding paper_id/markdown_sha256/source_json_sha256, and `prompt`. Cross-check these fields on import rather than trusting caller-added duplicates. The prompt instructs the current model to use only provided evidence and the document schema below.

Knowledge model document is exactly `schema=video-paper-wiki.light-knowledge-document.v1`, `paper_id`, `sections`, `concepts`. `sections` is an object with exactly these keys, rendered in this fixed order regardless of JSON key order: summary, method, architecture, training_data, experiments, limitations, code_resources, open_questions. Each section has exactly `status: provisional|unknown`, `text: string`, `citations: [chunk_id,...]`. Provisional text is nonblank (max 8,000 characters) with at least one citation owned by the selected paper; unknown uses text “证据不足” and no citations. Text contains no caller-authored [@...] citation marks; renderer appends marks from the validated list. At most 32 citation IDs per section; no duplicates/unknown IDs. At least one section must be provisional; an all-unknown document closes as INSUFFICIENT_EVIDENCE without publishing a record.

Concepts are at most 20 objects with exactly `name` and nonempty `citations`, all bound to the selected paper. Normalize names consistently with Unicode NFC/trim/casefold for grouping, while preserving a readable display label. Names are 1–120 characters, no control characters. Escape labels in generated Markdown/link contexts and derive filenames from hashes, never raw model/user paths.

Import validates the wrapper, exact document shape, every citation and live context before publishing. Use existing citation rendering and output-relative source links. Store a compact immutable record bundle under `.light-knowledge/records/<record_id>/` containing the checked model document, source context/identity, record manifest and readable knowledge.md. Define record_id deterministically from canonical wrapper+document; return it, paper_id, page path, source status and reused. Repeated identical import is exact reuse. A different valid document becomes a new record; prior records/user notes remain. Maintain a validated managed per-paper head map under .light-knowledge; it is a pointer to suggestions, not a formal reviewed/canonical head.

Listing returns active records and current/stale/missing-source/conflict state, never full paper text. A source edit/removal invalidates affected knowledge; do not certify old content current just because stored self-hashes agree. Saved records are bound to relative source paths, actual page/chunk identity and source byte hashes. After a verified relocation, byte-identical sources can still support readable saved knowledge; do not rewrite old exported contexts or pretend they are reusable live model sessions. Fresh model imports must always use a context for the current explicit workspace.

Views are immutable versioned snapshots under `knowledge/views/<view_id>/`, plus a validated managed `knowledge/CURRENT.json` pointer. Include index.md, individual paper links, concept pages, and basic related-paper links derived from shared evidenced concepts. Label these as same-concept suggestions; do not invent support/opposition or official-paper relationships. Show stale/historical items distinctly and exclude them from current relationship assertions. Return an actual readable index_path. Preserve existing notes.md and all older view snapshots. Revalidate current source/heads before switching the pointer. Retry may reuse a byte-identical completed snapshot; altered/unrecognized existing files are conflicts.

Add .light-knowledge, .light-library and knowledge to light_context's managed-output root protections so ordinary QA/writing cannot overwrite these inputs/state. No other shared semantic change in that file.

## T1 — multi-paper comparison

Public APIs in light_compare.py:

- `export_comparison_context(workspace_root, *, query, paper_ids, dimensions=None) -> dict`
- `import_comparison(workspace_root, context, document, *, output) -> dict`

Select 2–8 distinct present papers, filter per paper before retrieval, and export up to 6 actual lexical chunks per paper into an existing writing light-context. No silent all-paper fallback. Query is nonblank. Dimensions are 1–12 distinct nonblank labels (max 120 chars each), default method, architecture, training_data, experiments, limitations. Wrapper schema is `video-paper-wiki.light-comparison-context.v1`, with inner context, its canonical SHA, exact selected paper_ids/dimensions and per-paper coverage. Papers without hits remain selected and visible as missing evidence; no global evidence closes INSUFFICIENT_EVIDENCE. Do not manufacture snippets. Skill may reformulate a Chinese query into English terms using the current model.

Comparison document is exactly `schema=video-paper-wiki.light-comparison-document.v1`, `rows`. One row per frozen dimension in order, with dimension, cells, comparability, reason. Cells cover every selected paper exactly once in order and have paper_id, status, text, citations, conditions. Status/text/citation rules match knowledge sections, except each cell's citations must belong to that cell's paper. conditions is a nonblank string or literal “unknown”. Unknown cells must have conditions “unknown”. comparability is comparable|not_comparable|unknown; a comparable row requires every cell provisional, cited and with non-unknown conditions. Reason is nonblank. This is a model-proposed comparison, not deterministic scientific verification; render that distinction plainly. Do not automatically rank numbers or equate scores across different datasets/resolution/frame counts/evaluation protocols.

Render a readable Markdown table with linked citations, explicit conditions and comparability/reason. Escape cell delimiters, labels and line breaks correctly. Reuse live validation and atomic create-only Markdown I/O. Output must have .md suffix and a `.work` component in both its given absolute and resolved path, with no symlink traversal, outside managed inputs; the default is workspace/reports/. Existing output is LIGHT_OUTPUT_CONFLICT and remains byte-identical; source changes after export refuse publication. The new raw export/import flow is repeatable via its saved files; it does not claim the old qa/writing session state machine supports new kinds.

## T2 — library maintenance

Public APIs in light_library.py:

- `list_papers(workspace_root) -> dict` (read-only, includes valid paper summaries, diagnostics, archive summaries and pending operation IDs)
- `update_paper_metadata(workspace_root, paper_id, *, title=None, tags=None) -> dict`
- `archive_paper(workspace_root, paper_id) -> dict`
- `restore_paper(workspace_root, archive_id) -> dict`
- `replace_paper(workspace_root, paper_id, pdf_path, *, title=None) -> dict`
- `recover_library(workspace_root, *, operation_id=None) -> dict`

Metadata update permits display title (1–500 chars) and at most 30 distinct tags (1–100 chars each). Preserve source PDF identity, source.md, page anchors, notes and unknown existing metadata fields. Store title/tags in source.json and change no original evidence text. Exact no-op is reuse. A changed metadata file leaves the old index observably stale; do not re-label old contexts or silently rewrite completed output.

Archive moves the complete regular paper directory into owned `.light-library/archive/<archive_id>/paper/` with a manifest binding original paper ID and every retained file's exact path/hash. Keep user-authored text/code notes. Never follow symlinks or discard unknown files. Refuse unsafe/binary/unbounded extras before the move. The action is reversible and removes the paper from active search; it does not delete the original PDF.

Restore validates its manifest and complete set, restores to the absent original paper slot, and never overwrites an existing live paper. Record the completed archive/restore event so repeating the exact operation is safe; ambiguous duplicates are a conflict. Preserve all user bytes.

Replace first validates/extracts the explicit new PDF through native light_pdf. Same digest is safe reuse; a distinct already-active replacement paper is a conflict rather than a note merge. Preserve the old paper and notes in an archive, install the replacement under its own true PDF hash, and retain/copy old notes as clearly attributed prior-paper notes without overwriting anything already present in the replacement. Old notes must never be silently represented as statements about the new PDF. Return old/new IDs, archive ID, retained-note paths and index rebuild instructions. No PDF bytes are retained beyond existing extraction runtime.

Use owned versioned journals/staging under .light-library for multi-step operations. Record intent before the first irreversible directory move, binding kind, identities, exact allowed paths and source hashes. A detected process interruption leaves an explicit pending operation; recover or exact retry validates state and completes/reuses only owned steps. Never age-delete, guess a journal, lose an archived paper or report complete with a partial final directory. Expose test injection seams at meaningful before/after publication stages, not production CLI injection flags. Failures preserve user bytes; unexpected extras/conflicting destination require attention.

After effective changes, queries/contexts must observe actual stale/missing source state until the index is rebuilt. A complete restoration of identical source bytes may recover the same content-addressed index identity; no invented permanent generation counter is required. list and diagnostics do not repair state.

## T2 — lightweight backup and restore

Public APIs in light_backup.py:

- `create_backup(workspace_root, *, output, extra_outputs=None) -> dict`
- `verify_backup(archive_path) -> dict` (read-only)
- `restore_backup(archive_path, *, destination) -> dict`

Archive format is a deterministic stdlib ZIP with one versioned JSON manifest: schema `video-paper-wiki.light-backup.v1`, original workspace identity, sorted relative file inventory (path, size_bytes, sha256), explicit exclusions, explicit extra-output mapping, and manifest content hash. Do not reuse the formal Vault backup schema or claim receipt-backed canonical authority.

Preserve Markdown, user notes, source.json, small textual records/code, knowledge records/views, reports inside the workspace and stable completed/incomplete workflow session documents. Exclude only documented rebuildable index and ephemeral lock/staging files. Pending/ambiguous PDF/library/knowledge publication staging causes an actionable refusal until recovered. Empty ephemeral directories and unlocked persistent lock files do not imply an active operation.

No symlink/hardlink/nonregular/binary file, PDF/image/video/model/weight, unsafe/absolute/traversal/backslash member, duplicate/casefold collision, encrypted ZIP member, unknown manifest member or hash/size mismatch is accepted. Use bounded UTF-8 text/code extensions; define the exact extension set and limits in code/docs. Maximum 10,000 files, 8 MiB per text file and 128 MiB total uncompressed; enforce archive/container size limits and streaming verification to prevent an unbounded ZIP expansion. Refuse unsupported content; never silently omit user files.

Backup output is an explicit .work path outside the backed-up workspace, create-only (exact valid existing bytes may be reused; never replace different bytes). Snapshot file identity/set/hashes and recheck before installing the archive. Stage only in an owned same-parent temporary file. No unrelated workspace mutation by backup/verify.

Never follow arbitrary external paths found in a stored model document or receipt. Report external output references as not included; `extra_outputs` is an explicit caller list of regular .md text files to include. Bind their original path/hash and map them into a collision-free exports namespace on restore. Documentation and Skill should place future drafts under the workspace's reports directory by default and clearly state original PDFs remain external.

Restore verifies the entire archive before publishing into a new absent .work destination. Extract into a sibling owned stage, validate exact bytes/set and atomically rename; existing destination is a conflict even if empty. On failure, no partial final destination or modification of the original workspace. Restored source/notes/knowledge text must be byte-exact. Index is rebuilt separately. Preserve old workflow request/context/receipt bytes as history; they bind the original workspace/output paths and are not automatically resumed under the new root. Return explicit reindex/reprepare instructions and included/excluded/external-output summary. No automatic reading or overwrite of original external outputs.

## T3 — user entrypoints and verification

Keep vpwiki-research and python -m video_paper_wiki_research equivalent; preserve all existing behavior. New commands:

- `library list --workspace PATH`
- `library edit --workspace PATH --paper-id ID [--title TEXT] [--tag TAG ...]`
- `library remove --workspace PATH --paper-id ID` (archives; result offers restore)
- `library restore --workspace PATH --archive-id ID`
- `library replace --workspace PATH --paper-id ID --pdf PATH [--title TEXT]`
- `library recover --workspace PATH [--operation-id ID]`
- `knowledge export --workspace PATH --paper-id ID`
- `knowledge import --workspace PATH --context JSON --document JSON`
- `knowledge list --workspace PATH`
- `knowledge build --workspace PATH`
- `compare export --workspace PATH --query TEXT --paper-id ID --paper-id ID [--dimension TEXT ...]`
- `compare import --workspace PATH --context JSON --document JSON --output MARKDOWN`
- `backup create --workspace PATH --output ZIP [--include-output MARKDOWN ...]`
- `backup verify --archive ZIP`
- `backup restore --archive ZIP --destination PATH`

Repeatable flags mean one value per occurrence. Internal JSON files are authored by the Skill/current model, not by ordinary users. `--tag` omitted means preserve tags; add `--clear-tags` mutually exclusive with --tag for an explicit empty list. Resolve paths through current .work policy before side effects; verify doesn't create state. Errors are JSON/nonzero; no ok=true on an operation refusal.

Update video-paper-read Skill and its references/metadata for natural-language organize, compare, edit, remove/restore and backup intents. Keep explicit canonical/Vault routing/gates. Read skill-creator instructions when editing the Skill. Use actual CLI help, check returned evidence, construct correct typed documents, import and open real Markdown results. Chinese query fallback uses current-model English lexical terms; no added model service. Removal UI describes reversible archival; never claim a record/page is scientifically verified. For organize, execute export -> current model -> import -> build views; for compare, execute balanced export -> current model -> import. Explain stale/unknown/unsupported cases without inventing content. Keep the existing qa/writing recovery protocol intact.

Add docs/lightweight-library-quickstart.md and link it from README/lightweight PDF quickstart. Cover practical commands, output paths, source preservation, pending recovery, restore limitations and no copied PDF. Build behavior tests using real backends after consuming stopped owner handoffs; stubs can help parallel CLI work but do not constitute final integration acceptance.

Final acceptance includes focused module tests; cross-feature CLI/Skill routing; preservation on rejected operations and interruptions; current-source/cross-paper citation checks; source/metadata changes -> stale state; archive/restore and replace note preservation; backup tamper/traversal/size/binary/extra-file refusals; successful byte-exact fresh restore; both Python 3.12/3.13 full suites and isolated installed-wheel entrypoint check. Preserve the 67 catalog/overlay and dependency pins.

Use the locally available user PDFs for real source extraction and current-model knowledge/comparison output. At least the three available papers can be tested; do not fabricate a 5–10-paper corpus or count synthetic PDFs as real papers. Record exactly which PDFs/pages/cases ran, output sizes/extensions, actual current-model content/citations and remaining semantic-review limits. These runs are engineering evidence, not human provenance/claim/visual acceptance.

After all Builders stop, Astra reviews exact candidates, then a reassigned existing controller integrates exact allowlisted bytes, commits/pushes the authorized delivery to existing draft PR95 -> integration and collects fresh exact-head CI. Do not merge, change main or close human gates.

## Pre-freeze clarification — shared locks and operation layouts

This section resolves the read-only draft review; its precise rules govern the corresponding broad descriptions above.

T2 updates native extract_pdf so, after safely establishing/validating its workspace root, it acquires the SAME `.light-workflow/locks/workspace.lock` before managed paper/transaction side effects, then its existing per-paper lock. Lock order is workspace -> paper. Keep the existing extract_pdf signature/return behavior and existing non-.work test callers compatible; .work restrictions apply to the new library APIs. A lazy shared helper in light_library_state.py may provide this guard without introducing a module-import cycle. workflow.prepare adds before taking its own workspace lock, so this guard does not nest the same lock for that path. T2 replacement extracts in a distinct isolated staging workspace and must not recursively acquire the live workspace lock. Existing standalone build_index and workflow completion are not universally workspace-locked: backup must still observe active per-session locks/staging and recheck all captured identities/file sets.

All knowledge record/view publication staging is under `.light-knowledge/staging/<kind>-<id>-<token>/`, with an ownership.json written first, binding version, kind, target ID, intended relative target and allowed payload set; payload is a child directory. Exact same import/build retry can recover/reuse or remove only its verified generated partial staging. Unknown/extraneous/unsafe staging is preserved and reported. Backup refuses nonempty knowledge staging and names retry-import/build as the recovery action. Do not introduce another undocumented staging location.

### Library journal and archive semantics

Use `.light-library/operations/<operation_id>.json` with schema `video-paper-wiki.light-library-operation.v1`, operation_id, kind (archive|restore|replace), paper_id, optional new_paper_id, archive_id, phase, exact owned relative paths, and source/file inventories. operation_id/archive_id are opaque lowercase hexadecimal IDs generated once and validated, not raw user paths. Additional implementation fields are allowed only as a documented versioned shape validated before recovery; never evaluate journal instructions.

Archive payload manifest schema is `video-paper-wiki.light-paper-archive.v1`, with archive_id, original paper_id, original directory `papers/<digest>`, transport directory `paper`, and complete sorted file/directory inventory. Each file binds original_relative_path, archive_relative_path, size_bytes and sha256. Keep source.json and source.md byte-identical: source.json.document.path remains `papers/<digest>/source.md`. Validate the archived pair against original paper identity and paths while reading the archive transport; do not call _load_paper on an archive directory whose name is not the digest and do not rewrite metadata to fit transport.

Archive phases: intent (live source present, archive target absent) -> archived (source absent, validated archive payload present) -> complete. Persist intent/manifest before the move. After a crash, recognize an already-completed atomic move from exact file sets, not only the recorded phase. If neither side has a complete expected payload, or both sides exist unexpectedly, report NEEDS_RECOVERY/CONFLICT and preserve all bytes. One exact matching non-restored archive event/payload for an absent live paper is an idempotent repeat of archive_paper; zero means missing selection, multiple means conflict. An already archived copy plus a separately recreated live paper is a conflict until reconciled, not permission to create duplicate histories.

Restore phases: intent (validated archive present, live slot absent) -> restored (archive payload absent, live paper byte-exact) -> complete. Retain archive manifest/event metadata after moving the payload out. Repeated restore returns reused only when its completed event and exact live payload match; a changed/existing unrelated live slot is never overwritten.

Replace creates an intent BEFORE extraction side effects and uses `.light-library/staging/<operation_id>/workspace/` as an isolated native extraction workspace. Persist a complete manifest of the new pair before moving the old paper. Phases are intent -> staged (old live/new staged) -> old_archived (old archived/new staged) -> new_published (old archived/new live) -> complete. Validate both old and new manifests on each transition. Recover forward after a staged pair exists without needing the external PDF again. A pre-staging extraction failure leaves old live untouched; an owned failed stage may be discarded only after ownership/set validation. Missing/corrupt new staging after the old move requires attention and retains the old archive; never lose the remaining good copy or fake completion. Resolve exact previously-published bytes after interruption; both/none/foreign states refuse.

Old user notes remain BYTE-EXACT in the old archive. Do not copy their prose into the replacement's notes.md. A new clearly labelled prior-paper-notes.md may link to archived old note paths; return those retained paths. This is the single attribution rule for replacement.

Metadata updates use atomic source.json replacement, preserve the old file on failure, and clean only owned temporary files. Repeated no-op returns reused. recover_library without an ID inspects only recognized operation journals and returns per-operation results; it never scans random directories into invented operations.

### Shared text policy and backup state table

T2 owns one shared policy used by paper-archive extras and backup: UTF-8 regular files with case-insensitive extensions .md, .markdown, .txt, .json, .jsonl, .yaml, .yml, .toml, .py, .pyi, .js, .jsx, .ts, .tsx, .css, .html, .sh, .sql, .rs, .c, .cc, .cpp, .h, .hpp, .cu, .cuh, .go, .java, .r, .tex, .bib, .csv, .tsv, .xml, .ini, .cfg, .conf, .log, or exact case-insensitive basenames README, LICENSE, NOTICE, Makefile. Reject NUL/binary bytes and forbidden media/PDF/weights regardless of naming. Source.md/source.json have the same 8 MiB/file cap, no hidden exemption; larger sources are a documented closed unsupported-size result, not silent truncation. Apply 10,000-file and 128 MiB uncompressed caps before publication.

Backup treatment:
- .light-index: exclude only a structurally recognized rebuildable index tree; refuse unknown extra user content.
- .light-transactions: validate known digest.lock files, marker names/shapes and staging via the existing producer rules. Active lock, pending recognized publication or unknown entries refuse. Exclude only recognized unlocked locks and empty staging infrastructure.
- .light-workflow/locks: validate regular known workspace/session lock names, refuse active other locks, exclude known unlocked files; this call's own workspace lock is exempt from its active-lock check.
- .light-workflow/staging: empty recognized directory may be excluded; any pending/unknown entry refuses.
- .light-workflow/sessions: include stable allowed request/context/manifest/intent/completion documents byte-exact; active completion or incomplete publication staging refuses.
- .light-workflow/history: include previous historical text files normally.
- .light-library: include archive payloads/manifests/completed operation records; pending operations or nonempty owned staging refuse and name recover_library.
- .light-knowledge: include immutable records/heads; nonempty staging refuses as above.
- knowledge, papers, reports and ordinary user text/code files: include them. No generic “hidden-file” omission.
- Empty directories need not be preserved by backup; document that only file content and required parent directories are restored. Native paper archive moves preserve existing directories.

### Fixed ZIP/manifest and restored history

Manifest member is `LIGHT-LIBRARY-MANIFEST.json`; that name is reserved at archive root. Manifest exact top-level fields: schema, workspace_root, workspace_id, files, exclusions, extra_outputs, restore_remaps, manifest_sha256. workspace_id is SHA-256 of canonical {workspace_root: resolved original root}. files are sorted archive-relative path/size_bytes/sha256 objects. exclusions records the applied recognized ephemeral/rebuildable rules. extra_outputs contains original_path/archive_path/restore_path/hash for each explicit outside-workspace .md input. An explicitly included path already inside workspace is invalid/redundant; omit that flag because normal inventory already includes it. Map external outputs to `exports/external/<sha256>/<basename>.md`; collision with any different workspace member refuses.

restore_remaps is exactly the mapping of current `.light-workflow/sessions/` to `.light-workflow/history/<workspace_id>/sessions/`; previously existing history remains unchanged. The corresponding restore destinations must be collision-free. Manifest SHA hashes canonical manifest excluding manifest_sha256; the ZIP member is canonical manifest plus one LF. No duplicate JSON keys or unknown top-level fields.

ZIP contains manifest FIRST then sorted files, no explicit directory members, ZIP_STORED compression only, timestamp 1980-01-01 00:00:00, fixed regular-file private permission metadata. No ZIP64/encryption/multi-disk/extra members. Container cap is 136 MiB and uncompressed data cap is 128 MiB. Verify metadata, allowed member names, counts, claimed and actual read sizes, file hashes and complete set; never trust zipfile.extractall. An existing backup output is reusable only if exact valid archive bytes/manifest equal the newly captured workspace+extras snapshot; another valid archive is still a conflict.

Verify the entire archive before creating restore staging. The destination parent must already exist and be a safe .work directory; destination itself must be absent. Restore source/notes/knowledge and explicitly included outputs byte-exact using manifest mapping. Put historical sessions under the declared history root, NOT active sessions; existing workflow_status can then start cleanly without invalid absolute-root diagnostics. Return historical_session_root and instructions to rebuild index/prepare new sessions. A small generated restoration record may describe the mapping, but do not rewrite old request/context/receipt bytes or follow their old external output paths. New restores of prior restores preserve all historical namespaces without duplicate-path overwrite.
