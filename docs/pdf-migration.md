# PDF Drive migration operations

Shepherd implements inventory, plan, apply, report, and rollback. agy owns real Drive upload/reuse. Commands do not upload.

Drive A root: `1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW`

Convention: `pdfs/{category}/{paper_dir}/original.pdf`

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
