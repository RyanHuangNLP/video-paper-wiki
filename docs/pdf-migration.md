# PDF Drive migration operations

Shepherd implements inventory, plan, apply, report, and rollback. agy owns real Drive upload/reuse. Commands do not upload.

Drive A root: `1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW`

Frozen relative path: `pdfs/{category}/{paper_dir}/original.pdf`

Drive A already uses Awesome-Video-Diffusion section titles as `{category}`, including spaces. Prepare treats the uploaded-manifest `drive_relative_path` (and `parent_chain`) as authoritative when `result=reused` and the remote SHA-256 matches. Inventory may still propose a path; it must not overwrite A's existing directory.

Examples:

| paper_id | drive_relative_path |
|---|---|
| arxiv-1812.01717 | `pdfs/Evaluation Benchmarks and Metrics/arxiv-1812.01717/original.pdf` |
| arxiv-2204.03458 | `pdfs/Video Generation/arxiv-2204.03458/original.pdf` |
| arxiv-2312.03641 | `pdfs/Controllable Video Generation/arxiv-2312.03641/original.pdf` |
| arxiv-2410.05954 | `pdfs/Open-source Toolboxes and Foundation Models/arxiv-2410.05954/original.pdf` |

agy draft manifests (`pdf-upload-manifest.v1-draft`, `root_folder_id`/`items`, `parent_chain.id/title`) are accepted only after field adaptation. `inventory_sha256` must be a 64-hex digest; a null/empty draft digest is refused (`INVENTORY_SHA256_REQUIRED`).

## Sequence

```bash
vpwiki pdf inventory --roots ROOTS.json --batch-id drive-b-r1
# agy writes uploaded-manifest.json after remote read-back verification
vpwiki pdf migrate-prepare \
  --inventory .work/drive-b-r1/pdf-migration/inventory.json \
  --uploaded-manifest uploaded-manifest.json \
  --roots ROOTS.json \
  --batch-id drive-b-r1
vpwiki-admin pdf migrate-apply \
  --plan .work/drive-b-r1/pdf-migration/plan.json \
  --roots ROOTS.json \
  --root-id vault-main \
  --approved-plan-sha256 PLAN_SHA256 \
  --upstream-root vendor/claude-obsidian
vpwiki pdf migrate-report --plan .work/drive-b-r1/pdf-migration/plan.json --roots ROOTS.json
vpwiki-admin pdf migrate-rollback --journal JOURNAL.json --roots ROOTS.json
```

Sample handshake fixtures: `tests/fixtures/pdf-migration/sample-inventory.json` and `sample-uploaded-manifest.json`.

Only `uploaded`/`reused` rows whose remote sha256 equals the inventory sha256 may be linked. Apply re-checks before write. Parallel edits refuse with `PDF_APPLY_CHANGED`. Same paper, different sha256 is `PDF_CONTENT_CONFLICT` and is not completion.

Link-only registration:

```bash
vpwiki pdf link-prepare --roots ROOTS.json --root-id vault-main \
  --paper-id arxiv:2204.03458 --drive-file-id FILE_ID --batch-id drive-b-link-1
```

That plan is `unverified` and is not migration success.

Rollback restores this ticket's metadata/pages when the live file still matches the write-after digest. It does not delete Drive files or local PDFs.
