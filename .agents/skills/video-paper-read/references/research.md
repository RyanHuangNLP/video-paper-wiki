# Lightweight research: rewrite, batches, refresh, and writing projects

Read this when the user asks a Chinese question over English papers, wants complete long-paper knowledge batches, selective refresh, or outline/section revision history. Confirm flags from `vpwiki-research <group> --help`. Repeatable flags take one value per occurrence.

Create internal JSON yourself from CLI stdout. Do not ask the user to write rewrite, context, document, or diff files. Save unmodified successful stdout objects under `.work/**` and reuse those exact files as `--context` or `--diff`. Users never create internal JSON.

`--rewrite` is optional and only valid with `--workspace` on `qa export` / `writing export`. It is USAGE on vault/catalog routes. Duplicate `--paper-id` values on this rewrite route refuse. New rewrite contexts and their model documents are read as secure objects on workspace `qa import` / `writing import`.

Processing coverage (`processing_complete`, planned/processed chunks) is not a claim that every fact appears in the model summary. Writing `progress.complete` means no unwritten sections and at least one provisional section; it is not scientific or human acceptance. Intact unwritten or partial drafts are valid persisted history and may be backed up. Pending publication (unsafe/unknown staging, missing/conflicting HEAD, edited/incomplete bundle, or orphan) blocks backup.

## Chinese / English rewrite

Current model writes this exact object; Python does not translate:

```json
{
  "schema": "video-paper-wiki.light-query-rewrite.v1",
  "original_query": "the exact original question",
  "rewritten_query": "English lexical search terms",
  "language": "en"
}
```

`original_query` must equal the `--question` / `--topic` bytes. `rewritten_query` is nonblank, ≤2000 characters, contains a Latin letter, and has no control characters. `language` is exactly `en`.

1. `qa export --workspace PATH --question TEXT [--paper-id ID ...] --rewrite REWRITE.json`
2. Or `writing export --workspace PATH --topic TEXT --requirements TEXT [--paper-id ID ...] --rewrite REWRITE.json`
3. Save stdout as `--context`. Import with the existing workspace `qa import` / `writing import` after writing the usual cited answer or draft.
4. Citations still come only from `evidence`. `query_plan` is diagnostic retrieval provenance.

## Long-paper batches

Do not send a whole paper to the model. Plan, export one batch, write a cited knowledge document, import, merge in order, then finalize.

1. `knowledge batch-plan --workspace PATH --paper-id ID`
2. `knowledge batch-export --workspace PATH --plan-id ID --batch-index N` (zero-based integer)
3. Write `schema=video-paper-wiki.light-knowledge-document.v1` from that batch’s evidence only. Section keys remain `summary`, `method`, `architecture`, `training_data`, `experiments`, `limitations`, `code_resources`, `open_questions`. All-unknown batch documents are allowed as processed evidence; they do not create a knowledge record.
4. `knowledge batch-import --workspace PATH --context CONTEXT.json --document DOCUMENT.json`
5. `knowledge merge-export --workspace PATH --plan-id ID` then write the same document shape from the prior accumulator plus the next batch document. Permitted citations are the union actually cited by those two objects.
6. `knowledge merge-import --workspace PATH --context CONTEXT.json --document DOCUMENT.json`
7. `knowledge batch-status --workspace PATH [--plan-id ID]` is read-only.
8. `knowledge finalize --workspace PATH --plan-id ID` publishes one normal knowledge record only after the complete partition and merge chain.

A pending batch job or leftover publication stage blocks backup. Completed jobs remain byte-exact history.

## Selective refresh

1. `knowledge refresh-plan --workspace PATH --paper-id ID` after a current validated head exists.
2. Process any returned batches/merges, then `knowledge finalize` to create a candidate. Finalize does not advance HEAD.
3. `knowledge diff --workspace PATH --base-record-id ID --candidate-record-id ID`
4. `knowledge apply --workspace PATH --diff DIFF.json` plus exactly one section choice and exactly one concepts choice:
   - `--accept-section KEY` repeated, or `--keep-sections` (empty accept list)
   - `--accept-concepts` or `--keep-concepts`
   Missing either group is USAGE. Duplicate section keys refuse. There is no implicit accept-all.
5. Accepted fields use candidate values; unaccepted fields keep only remapped current old values, otherwise become unknown. An all-unknown final result refuses.

A library PDF replacement with a different digest is a new paper; do not alias old facts onto the new bytes.

## Outline and section revisions

Start from a successful live `kind=writing` light-context (normal or rewritten writing export).

1. `writing outline-export --workspace PATH --context WRITING.json`
2. Current model writes:

```json
{
  "schema": "video-paper-wiki.light-writing-outline.v1",
  "title": "...",
  "sections": [
    {
      "section_id": "s1",
      "title": "...",
      "goal": "...",
      "status": "provisional",
      "citations": ["chunk_id"]
    }
  ]
}
```

1–16 unique `s[1-9][0-9]?` sections. Titles 1–300 characters, goals 1–2000, no control characters or caller `[@...]` marks. Provisional sections need 1–32 current evidence citations. Unknown sections have no citations and goal exactly `证据不足`. At least one section must be provisional.

3. `writing outline-import --workspace PATH --context OUTLINE.json --document DOCUMENT.json`
4. `writing section-export --workspace PATH --project-id ID --section-id ID [--instructions TEXT]`
5. Current model writes every required field, including `project_id`:

```json
{
  "schema": "video-paper-wiki.light-writing-section.v1",
  "project_id": "64-lowercase-hex",
  "section_id": "s1",
  "status": "provisional",
  "markdown": "nonblank cited body [@chunk_id]",
  "citations": ["chunk_id"]
}
```

Provisional Markdown is ≤16,000 characters and must use the same `[@chunk_id]` marks as `citations` (1–32 distinct current evidence ids). Unknown uses Markdown `证据不足` and no citations. `project_id` must match the export.

6. `writing section-import --workspace PATH --context SECTION.json --document DOCUMENT.json`
7. `writing history --workspace PATH --project-id ID` is read-only.
8. `writing project-export --workspace PATH --project-id ID --output MARKDOWN` writes a `.work` Markdown file. It reports incomplete sections instead of claiming a finished article. A wholly unwritten or all-unknown article is refused as a completed draft.

Unwritten text renders as `尚未撰写`. Relocated history stays readable as historical content and is not resumed from old absolute contexts. Source change requires a fresh writing context and new project; old revisions remain readable.

## Closed cases

Explain `QUERY_REWRITE_INVALID`, `LIGHT_BATCH_INVALID` / `LIGHT_BATCH_CONFLICT` / `LIGHT_BATCH_INCOMPLETE`, `LIGHT_REFRESH_INVALID` / `LIGHT_REFRESH_CONFLICT`, `LIGHT_WRITING_PROJECT_INVALID` / `LIGHT_WRITING_PROJECT_CONFLICT`, `INDEX_STALE`, `SOURCE_INVALID`, `LIGHT_HANDOFF_INVALID`, `LIGHT_WORKSPACE_BUSY`, and `NO_RESULTS` without inventing evidence. Preserve existing bytes on refusal.
