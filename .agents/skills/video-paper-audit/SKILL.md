---
name: video-paper-audit
description: Run the pinned Claude Obsidian strict read-only Vault lint through vpwiki.
---
Run `vpwiki audit --vault-root <vault> --upstream-root <pinned-claude-obsidian> [--as-of YYYY-MM-DD]`. Report `valid`, the strict exit code, summary and upstream findings without claiming a human gate passed.

This skill does not repair or apply changes. If a runtime projection is stale, show `vpwiki-admin catalog build --vault-root <vault> --upstream-root <pin> --config <retrieval-config.json>` and ask the user to run it; never execute it.

`vpwiki backup manifest|verify` only reads a raw-inclusive complete set and a distinct restored tree. If the user requests the private archive workflow, show `vpwiki-admin backup create --vault-root <vault> --manifest <manifest.json> --destination <archive.zip>` or `vpwiki-admin backup restore --archive <archive.zip> --source-root <source-vault> --restore-root <private-empty-root> --manifest <manifest.json> --upstream-root <pin> --config <retrieval-config.json>`. Do not execute either command. External anchoring and a real isolated restore observation remain human gates.
