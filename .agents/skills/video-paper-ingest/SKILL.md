---
name: video-paper-ingest
description: Prepare and inspect a local PDF for Video Paper Wiki canonical staging, capture inspect, or publication inspect without mutating a Vault. Use video-paper-read instead for ordinary local reading, workspace Q&A, or a short cited draft.
---
Ordinary local-PDF reading, workspace Q&A, selected-paper comparison, and short related-work drafts belong to `video-paper-read`. Switch there only when the user asked for that lightweight path and did not request canonical staging, parser/Docling export, capture inspect, publication inspect, or Vault apply. Do not bounce between the two skills in a loop.

For an explicit canonical ingest of a user-supplied local PDF, first run `vpwiki-research pdf intake --pdf <file.pdf> --session <id>`. This stages bytes under `.work/blobs/<sha256>` and an immutable intake envelope. Do not invent DOI/arXiv/license metadata. The result is staged input, not a capture receipt.

Parser profile and Docling export are optional and external: show `vpwiki-parser profile --artifacts-path <models> --session <id>` and `vpwiki-parser export --intake <intake.json> --profile <profile.json> --artifacts-path <models> --session <id> --run-id <run>` for the user to run in a prepared offline environment. Never import or execute the parser producer from this skill, never download models, and never call `vpwiki-admin`.

After a staged four-file run exists, run `vpwiki-research pdf context --intake <intake.json> --profile <profile.json> --run <run-dir> --upstream-root <pinned-claude-obsidian> --session <id>`. Give the returned task prompt to the current model. Then `vpwiki-research pdf analyze --context <context.json> --proposal <unsealed.json> --upstream-root <pin> --session <id>`. Proposals stay provisional and unpublished.

`vpwiki-research pdf plan --intake <intake.json> --profile <profile.json> --batch-id <batch>` only stages an ingest plan. It must never create an approval-ref. Real capture still needs the later genesis/admission workflow. Do not tell the user to capture into a pristine unbootstrapped Vault and then run package.

For already-authorized capture inspect, run `vpwiki seed validate`, then `vpwiki ingest plan --request <request.json>` and `vpwiki ingest prepare --plan <.work/.../ingest-plan.v1.json> --approval-ref <approval-ref.json>`. Inspect the prepared capture with `vpwiki capture inspect --prepared <.work/.../prepared/staged-pdf-capture-request.v1.json> --operation-id <id> --upstream-root <pinned-claude-obsidian> --vault-root <vault>`.

Only run `vpwiki` or `vpwiki-research`; they write generated staging below `.work/**`. For canonical publication material, use `vpwiki publication prepare --request <publication-input/knowledge-publication-request.v1.json> --batch-id <batch>` and then `vpwiki publication inspect --prepared <.work/.../publication-input/knowledge-publication-request.v1.json> --operation-id <id> --upstream-root <pin> --vault-root <vault>`. If the result needs to be applied, show `vpwiki-admin transaction apply --bundle <bundle.json> --vault-root <vault> --upstream-root <pin> --approved-plan-sha256 <sha>` and ask the user to run it. Never execute it or treat an approval-ref as permission to apply.
