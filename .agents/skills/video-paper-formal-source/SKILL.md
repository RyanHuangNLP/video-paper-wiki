---
name: video-paper-formal-source
description: Prepare and inspect a lightweight Markdown paper for formal source registration without copying its PDF or applying Vault changes.
---

# Formal Markdown source handoff

Use `vpwiki-research formal-source` for an existing lightweight `.work` paper.
Read [the workflow](references/workflow.md) and the command's `--help` output.

- Bind the selected light paper and exact `source.md` / `source.json` bytes using `plan`.
- Preserve explicit canonical entity and unknown/declared version provenance.
- Use the externally supplied Markdown approval reference with `prepare`; do not generate one.
- Use `inspect` with the pinned upstream and read-only Vault. Save its `data.authority` object.
- Use `bind-result` only for an externally executed create result with actual before/after descriptors.
- Use `admit` with new batch/operation IDs and an existing valid genesis chain. The result is an inspected publication handoff.

Public commands are offline and write generated files only under `.work`.
Never execute operator commands, apply a transaction, copy a PDF, or fabricate operator evidence.
Keep pending publications visibly unapplied.
Never use synthetic test references as human approval. Existing user authorization governs whether
external/operator steps can be taken; this skill does not add a new approval question.
