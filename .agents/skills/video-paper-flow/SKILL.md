---
name: video-paper-flow
description: Continuous discover → compare → survey workflow over an existing Vault. Run `vpwiki flow status` first. Do not use for ordinary local PDF reading (video-paper-read) or canonical ingest (video-paper-ingest).
---

Start with `vpwiki flow status --vault-root <vault> [--batch-id <session>]`. Read `next_actions` in order and show each argv to the user. Prefix `command_tree` rows with `vpwiki`. Run `module_entry` rows as written. Fill placeholders from the user: `recorded_by` is a person or agent name; `recorded_at` is RFC 3339 UTC. Do not invent clock values.

Use `vpwiki flow select --vault-root <vault> --batch-id <session> --paper-id <paper> [--association-id <sva>] [--question <question>]` to open a session. The batch is the session. A different selection needs a new batch.

Use `vpwiki flow prepare --kind experiment|article` to write structured inputs under `.work/<batch>/flow/`. Keep every identity field in the draft unchanged. Fill only scientific values (condition slots, section markdown, claims). Then run the matching `experiments record --input` or `articles import --context/--document` argv.

flow writes only under `.work/<batch>/flow/`, never the Vault; publication stays unpublished; no ranking. Domain proposal bodies and `claim_refs` are not prefilled here.

If a later Vault write is required, show `vpwiki-admin … apply` for the user; never run it from this skill.
