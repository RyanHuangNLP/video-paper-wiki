---
name: video-paper-ingest
description: Prepare and inspect a local PDF for Video Paper Wiki without mutating a Vault.
---
Run `vpwiki seed validate`, then `vpwiki ingest plan --request <request.json>` and `vpwiki ingest prepare --plan <.work/.../ingest-plan.v1.json> --approval-ref <approval-ref.json>`. Inspect the prepared capture with `vpwiki capture inspect --prepared <.work/.../prepared/staged-pdf-capture-request.v1.json> --operation-id <id> --upstream-root <pinned-claude-obsidian> --vault-root <vault>`.

Only run `vpwiki`; it writes generated staging below `.work/**`. For canonical publication material, use `vpwiki publication prepare --request <publication-input/knowledge-publication-request.v1.json> --batch-id <batch>` and then `vpwiki publication inspect --prepared <.work/.../publication-input/knowledge-publication-request.v1.json> --operation-id <id> --upstream-root <pin> --vault-root <vault>`. If the result needs to be applied, show `vpwiki-admin transaction apply --bundle <bundle.json> --vault-root <vault> --upstream-root <pin> --approved-plan-sha256 <sha>` and ask the user to run it. Never execute it or treat an approval-ref as permission to apply.
