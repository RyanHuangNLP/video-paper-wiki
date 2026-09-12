---
name: video-paper-code-map
description: Prepare UTF-8 source evidence and inspect a staged code capture.
---
Run `vpwiki code-map plan --request <request.json>`, then `vpwiki code-map prepare --plan <plan.json> --approval-ref <approval-ref.json> --source-path <repository-relative-path>`. Inspect with `vpwiki code-map inspect --prepared <.work/.../prepared/staged-code-capture-request.v1.json> --operation-id <id> --upstream-root <pinned-claude-obsidian> --vault-root <vault>`.

The result includes the inspected code-evidence manifest. Only run `vpwiki`. For a requested write, show `vpwiki-admin transaction apply --bundle <bundle.json> --vault-root <vault> --upstream-root <pin> --approved-plan-sha256 <sha>` and leave execution to the user. Never invoke the operator command.
