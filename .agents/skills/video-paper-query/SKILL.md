---
name: video-paper-query
description: Query an existing pinned Claude Obsidian BM25 index and shape its results. Use video-paper-read instead for ordinary lightweight workspace Q&A or short drafts from local PDFs.
---
Ordinary workspace lexical Q&A and short drafts from local lightweight papers belong to `video-paper-read`. Use this skill only when the user explicitly asks to query a pinned Claude Obsidian BM25 index or an existing Vault catalog. Do not treat a Vault as the default workspace for “read this PDF”. Do not recurse back into `video-paper-read` unless the user then asks for the lightweight path.

Run `vpwiki query --json --text <query> --vault-root <vault> --upstream-root <pinned-claude-obsidian> --config <retrieval-config.json>`. The config fixes the upstream candidate depth. This is read-only and returns canonical paper top-10/top-5 plus evidence top-8 from the verified SQLite catalog.

If the catalog is missing or stale, show `vpwiki-admin catalog build --vault-root <vault> --upstream-root <pinned-claude-obsidian> --config <retrieval-config.json>` for the user to run. Do not run it or modify the index from this skill.

Use `vpwiki retrieval validate|evaluate` for an independent gold set. Gold must never influence mapping or ranking.
