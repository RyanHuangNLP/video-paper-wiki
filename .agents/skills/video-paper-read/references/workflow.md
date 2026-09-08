# Lightweight workflow protocol

Read this only when preparing, completing, or explaining a session. Command flags come from the installed or source CLI help, not from memory.

Python APIs are `prepare_workflow`, `workflow_status`, and `complete_workflow`. Successful prepare/status payloads use `schema=video-paper-wiki.light-workflow.v1` and `ok=true` with `status=OK`. Inspected readiness is the separate `state` field: `awaiting_model`, `complete`, `stale`, or `needs_attention`.

## Structural protocol fixture

The following object is a **structural test fixture**, not an actual current-session-model trial. Terminal 4 owns the real CLI current-model trial.

```json
{
  "ok": true,
  "status": "OK",
  "schema": "video-paper-wiki.light-workflow.v1",
  "session_id": "64-lowercase-hex",
  "state": "awaiting_model",
  "context_path": "/abs/.light-workflow/sessions/<id>/context.json",
  "request_path": "/abs/.light-workflow/sessions/<id>/request.json",
  "manifest_path": "/abs/.light-workflow/sessions/<id>/manifest.json",
  "context": {
    "ok": true,
    "status": "OK",
    "schema": "video-paper-wiki.light-context.v1",
    "kind": "qa",
    "query": "What method is used?",
    "evidence": [],
    "prompt": "Use only the evidence."
  },
  "next_actions": [
    "read the exported context and construct a model document in the current session"
  ],
  "reused": false
}
```

A structural complete fixture looks like `{ok:true,status:OK,state:complete,session_id,path,output_sha256,reused}`.

## Request, identity, and files

`session_id` is SHA-256 of canonical identity `{schema:video-paper-wiki.light-workflow-identity.v1,request_sha256,context_sha256}`. Same request plus same context bytes reuse the session; a source/index change creates a new session and keeps history.

Persisted session files are `request.json`, `context.json`, `manifest.json`, optional `completion-intent.json`, and `completion.json` only with an intent. Output Markdown lives outside the session.

## Cases that change the next action

- **No results.** `NO_RESULTS` / `INSUFFICIENT_EVIDENCE` returns `session_id=null` and no session directory. Do not invent papers or quotes. Try English lexical terms for a Chinese question, or a broader/narrower selection.
- **No native text.** `PARSER_NO_TEXT` is terminal for this path. Do not start OCR or Docling.
- **Stale context.** Source or index changed after export. Status becomes `stale`. Keep any completed Markdown. Re-prepare; do not complete the old session as if it were current.
- **User-edited or pre-existing draft.** Complete never uses `overwrite=True`. No matching intent → `LIGHT_OUTPUT_CONFLICT`. Intent/receipt exist but bytes differ → `LIGHT_SESSION_CONFLICT`. Leave the file.
- **Interrupt.** A validated intent with missing or matching output stays `awaiting_model` and can retry the same document and output. A mismatching file is `needs_attention`.
- **Explicit paper ids.** Only `sha256:` plus 64 lowercase hex. Unknown or malformed ids are `LIGHT_SELECTION_INVALID`; never silently search all papers.
- **Explicit canonical / Vault request.** Stop and use `video-paper-ingest` or `video-paper-query`. Those skills keep their own gates. Do not treat a Vault path as the default lightweight workspace.

Organize, compare, library maintenance, and lightweight backup are separate CLI groups. They do not add `workflow --kind` values. Read [library.md](library.md) for those commands, including saving export-object JSON and the 8 MiB regular-file policy. The qa/writing request/document JSON loader and recovery protocol above stay intact.
