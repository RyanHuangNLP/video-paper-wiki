---
name: video-paper-read
description: Read local PDFs, answer from selected workspace papers, or write a short cited draft through the lightweight research workflow. Use for ordinary reading and writing. Do not use when the user explicitly asks for canonical Vault ingest, capture inspect, publication, or a pinned Claude Obsidian BM25/Vault catalog query.
---

Handle ordinary local-PDF reading, workspace Q&A, selected-paper comparison, and short related-work drafts. The current session model writes the answer; Python only prepares evidence and checks citations. Read installed or source `vpwiki-research workflow --help` before inventing flags.

Default workspace is under the caller’s approved `.work/` root. Never pick a real Vault implicitly. Create internal JSON yourself; do not ask the user to author request, context, document, or receipt files.

## Route away

- Explicit canonical staging, parser/Docling export, capture inspect, publication inspect, or Vault apply → `video-paper-ingest`. Do not recurse back here unless the user then asks for the lightweight path.
- Explicit pinned Claude Obsidian BM25 / existing Vault catalog query → `video-paper-query`.
- No OCR, Docling, model API, or network from this skill.

## Workflow

1. Reuse an explicit workspace/session when the user names one; otherwise create `.work/light-read/`.
2. Add only the PDFs the user named. Repeated adds are reuse, not a wipe of notes.
3. `workflow prepare` with `--kind qa|writing`, the user query, optional `--paper-id`, and optional `--pdf`.
4. Read the returned `context`. That object is the only evidence input.
5. In this conversation, write a model document from that evidence. Q&A uses `text`; writing uses `markdown` (text fallback is allowed). Cite used chunks as `[@chunk_id]` and list the same ids. This live document is not a structural test fixture.
6. `workflow complete` with the session id, a UTF-8 JSON document file, and an output Markdown path.
7. If the user later asks what happened, `workflow status` is read-only.

Closed results stay closed: `NO_RESULTS` / `INSUFFICIENT_EVIDENCE` means no session and no invented answer. Scanned PDFs with no native text stay `PARSER_NO_TEXT`. Stale or edited sources need re-prepare, not a silent overwrite. An existing user draft or a completed output without a matching intent is a conflict; keep the file.

Details and the structural protocol fixture live in [references/workflow.md](references/workflow.md).
