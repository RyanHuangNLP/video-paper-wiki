# Lightweight library, knowledge, compare, and backup

Read this when the user wants to organize cited notes, compare papers, edit/archive/restore/replace a paper, recover a pending library operation, or back up/restore a lightweight workspace. Confirm flags from `vpwiki-research <group> --help`. Repeatable flags take one value per occurrence (`--paper-id A --paper-id B`, not `--paper-id A B`).

Save the exact `knowledge export` / `compare export` JSON object from CLI stdout as the `--context` file. Author the matching document JSON yourself from that evidence. Do not ask the user to write context or document JSON.

Generated context/document JSON stays under `.work/**`. Explicit read-only JSON inputs and `--include-output` `.md` files may be outside `.work`, but the CLI keeps the caller-selected path: every parent/final edge must be a regular file or directory, with no symlink or hardlink, an 8 MiB bounded read, and strict UTF-8. Top-level knowledge/compare JSON must be an object without duplicate keys, NaN/Infinity, oversized integers, or nesting beyond the supported limit. Those refusals are `LIGHT_HANDOFF_INVALID` JSON/nonzero with no backend call. Do not resolve a symlinked parent and treat the cleaned path as originally safe. Do not scan receipts or directories for extras.

All workspace, backup, restore, and generated Markdown/ZIP paths must contain a `.work` component in both the given absolute path and the resolved path. New workspaces and generated results stay under `.work/**`. Original PDFs are read-only inputs and are never copied into the workspace or backup.

Removal is reversible archival. Never say a record, view, or comparison table is scientifically verified. Model text is provisional. `unknown` / `证据不足` stays closed; do not invent missing cells or sections.

## Organize

1. `library list --workspace PATH` if the user needs current paper ids.
2. `knowledge export --workspace PATH --paper-id ID`.
3. Retain the returned export JSON object (CLI stdout) as the `--context` file. Read that object only. Write `schema=video-paper-wiki.light-knowledge-document.v1` with that `paper_id`.
4. `sections` is an object with exactly these keys, rendered in this order: `summary`, `method`, `architecture`, `training_data`, `experiments`, `limitations`, `code_resources`, `open_questions`.
5. Each section has exactly `status` (`provisional` or `unknown`), `text`, and `citations` (chunk ids). Provisional text is nonblank (max 8,000 characters) with at least one citation owned by the selected paper. Unknown uses text `证据不足` and no citations. Do not put caller-authored `[@...]` marks in `text`.
6. At least one section must be provisional. An all-unknown document is a closed `INSUFFICIENT_EVIDENCE` result and must not be imported.
7. `concepts` has at most 20 objects with exactly `name` and nonempty `citations`, all bound to the selected paper.
8. Write the document JSON, then `knowledge import --workspace PATH --context CONTEXT.json --document DOCUMENT.json`.
9. `knowledge build --workspace PATH` and open the returned `index_path`.
10. `knowledge list --workspace PATH` is read-only. After title/tag edits, export/prepare stays `INDEX_STALE` until `index build`. Stale/missing-source/conflict items stay labelled; do not treat stored hashes as proof the page is current.

## Compare

1. Select 2–8 distinct present papers. No silent all-paper fallback.
2. `compare export --workspace PATH --query TEXT --paper-id ID --paper-id ID [--dimension TEXT ...]`.
3. Retain the returned export JSON object (CLI stdout) as the `--context` file. Default dimensions are method, architecture, training_data, experiments, limitations. Papers without hits stay selected as missing evidence. No global evidence is a closed result.
4. Chinese queries may need English lexical terms from this conversation; retry export with those terms. Do not add a model service.
5. Write `schema=video-paper-wiki.light-comparison-document.v1` with `rows` in frozen dimension order. Each row has `dimension`, `cells`, `comparability`, `reason`. Cells cover every selected paper exactly once and have `paper_id`, `status`, `text`, `citations`, `conditions`.
6. Status/text/citation rules match knowledge sections, except citations must belong to that cell’s paper. `conditions` is a nonblank string or literal `unknown`. Unknown cells must use conditions `unknown`. `comparability` is `comparable`, `not_comparable`, or `unknown`. A comparable row requires every cell provisional, cited, and with non-unknown conditions. `reason` is nonblank.
7. Do not rank numbers across different datasets or protocols. Label the table as a model-proposed comparison.
8. `compare import --workspace PATH --context CONTEXT.json --document DOCUMENT.json --output MARKDOWN`. Output must be `.md` under `.work/**`. The readable table is a cited Markdown file (heading and conditions included). Existing output is a conflict; keep the old bytes.

## Library maintenance

- `library list --workspace PATH` — read-only summaries, diagnostics, archives, pending operation ids.
- `library edit --workspace PATH --paper-id ID [--title TEXT] [--tag TAG ...]` — omitted `--tag` preserves tags. `--clear-tags` is mutually exclusive with `--tag` and stores an empty list.
- `library remove --workspace PATH --paper-id ID` — calls `archive_paper`. The JSON result offers restore with `archive_id`. Regular nested Markdown/code notes and empty directories stay with the paper, including Chinese/Greek user filenames. The original PDF is not deleted.
- `library restore --workspace PATH --archive-id ID` — restores into the absent original paper slot only, including nested notes, empty directories, and those exact Unicode names.
- `library replace --workspace PATH --paper-id ID --pdf PATH [--title TEXT]` — extracts the new PDF in isolated staging. Old nested notes stay byte-exact in the old archive and may be linked as prior-paper notes; they are not statements about the new PDF. A completed replace of a just-restored paper is that restore's archive successor; recover can prove it. A replace aborted before staging leaves the old paper live: that is no replacement, not a successful publication.
- `library recover --workspace PATH [--operation-id ID]` — complete or reuse only owned pending steps. If backup later refuses nonempty library staging, recover first. An owned pre-staging abort is still no replacement.

After an effective change, rebuild the index before new export/prepare. Old contexts become stale.

## Backup and restore

Place future drafts under the workspace `reports/` directory so they are included automatically. Use `--include-output` only for an explicit outside-workspace `.md` file.

- `backup create --workspace PATH --output ZIP [--include-output MARKDOWN ...]` — output is a create-only `.work` path outside the backed-up workspace. The ZIP is file-only: no empty-directory members. Chinese/Greek user-note names and an explicit Chinese `--include-output` report keep their exact names and bytes; creating again against an identical existing ZIP is reuse. Rebuildable index, unlocked ephemeral locks, and empty staging infrastructure are excluded. Pending publication/library/knowledge staging is an actionable refusal.
- `backup verify --archive ZIP` — read-only; creates no workspace or destination state.
- `backup restore --archive ZIP --destination PATH` — destination parent must already exist under `.work/**`; destination itself must be absent, including an empty directory. Restored workflow sessions land under history, not active sessions. Rebuild the index and prepare new sessions; do not resume old absolute session paths. Do not follow stored external output paths.

Unsupported binary, PDF, symlink, traversal, or oversize members are refusals. Never silently omit user files.

## Closed cases

Explain `INSUFFICIENT_EVIDENCE`, `INDEX_STALE`, `LIGHT_OUTPUT_CONFLICT`, `LIGHT_LIBRARY_NEEDS_RECOVERY`, `LIGHT_WORKSPACE_BUSY`, and unsupported-size results without inventing content. Preserve existing bytes on refusal.
