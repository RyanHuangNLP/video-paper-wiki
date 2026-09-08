---
name: video-paper-read
description: Read local PDFs, answer from selected workspace papers, write a short cited draft, organize cited knowledge notes, compare selected papers, edit or reversibly archive papers, and back up or restore a lightweight workspace. Use for ordinary reading, writing, organize, compare, library maintenance, and backup. Do not use when the user explicitly asks for canonical Vault ingest, capture inspect, publication, or a pinned Claude Obsidian BM25/Vault catalog query.
---

Handle ordinary local-PDF reading, workspace Q&A, selected-paper comparison, short related-work drafts, cited knowledge organization, paper list/edit/archive/restore/replace, and lightweight backup. The current session model writes notes and comparison rows; Python only prepares evidence and checks citations. Read installed or source `vpwiki-research --help` and the matching subcommand help before inventing flags.

Default workspace is under the caller’s approved `.work/` root. Never pick a real Vault implicitly. Create internal JSON yourself; do not ask the user to author request, context, document, or receipt files. Save each `knowledge export` / `compare export` JSON object from CLI stdout as the `--context` file. Generated JSON stays under `.work/`. Explicit read-only JSON or `--include-output` `.md` files may be outside `.work`, but must be regular files: no symlink/hardlink, 8 MiB, strict UTF-8. Do not scan receipts for extras. Backup ZIP is file-only (no empty-directory members) and never copies original PDFs. After restore, rebuild the index and prepare new sessions. A replace aborted before staging is no replacement.

## Route away

- Explicit canonical staging, parser/Docling export, capture inspect, publication inspect, or Vault apply → `video-paper-ingest`. Do not recurse back here unless the user then asks for the lightweight path.
- Explicit pinned Claude Obsidian BM25 / existing Vault catalog query → `video-paper-query`.
- No OCR, Docling, model API, or network from this skill.

## Choose a path

- Read / Q&A / short draft → existing `workflow` (`--kind qa|writing` only). Do not invent new session kinds.
- Organize cited notes / concept views → [references/library.md](references/library.md) organize flow: `knowledge export` → current model → `knowledge import` → `knowledge build`.
- Compare selected papers → [references/library.md](references/library.md) compare flow: balanced `compare export` → current model → `compare import`.
- List / edit title or tags / remove / restore / replace / recover → [references/library.md](references/library.md) library commands. `library remove` is reversible archival (`archive_paper`); offer restore. Never claim a record or page is scientifically verified.
- Backup / verify / restore the lightweight workspace → [references/library.md](references/library.md) backup commands. Original PDFs stay external; do not copy them into the archive.

## Workflow (qa / writing)

1. Reuse an explicit workspace/session when the user names one; otherwise create `.work/light-read/`.
2. Add only the PDFs the user named. Repeated adds are reuse, not a wipe of notes.
3. `workflow prepare` with `--kind qa|writing`, the user query, optional `--paper-id`, and optional `--pdf`.
4. Read the returned `context`. That object is the only evidence input.
5. In this conversation, write a model document from that evidence. Q&A uses `text`; writing uses `markdown` (text fallback is allowed). Cite used chunks as `[@chunk_id]` and list the same ids. This live document is not a structural test fixture.
6. `workflow complete` with the session id, a UTF-8 JSON document file, and an output Markdown path.
7. If the user later asks what happened, `workflow status` is read-only.

Closed results stay closed: `NO_RESULTS` / `INSUFFICIENT_EVIDENCE` means no session and no invented answer. Scanned PDFs with no native text stay `PARSER_NO_TEXT`. Stale or edited sources need re-prepare, not a silent overwrite. An existing user draft or a completed output without a matching intent is a conflict; keep the file.

Chinese queries may miss English PDF terms. Reformulate lexical English terms in this conversation, then retry export/prepare. Do not add a model service.

Details and the structural protocol fixture live in [references/workflow.md](references/workflow.md). Library, knowledge, compare, and backup command shapes live in [references/library.md](references/library.md).
