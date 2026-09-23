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

agy draft manifests (`pdf-upload-manifest.v1-draft`, `root_folder_id`/`items`, `parent_chain.id/title`, `item_id` `seed:sha256`) are accepted only after field adaptation, including normalizing draft item ids to schema sha256 before validation. `inventory_sha256` must be a 64-hex digest; a null/empty draft digest is refused (`INVENTORY_SHA256_REQUIRED`). agy may still emit a final v1 manifest.

Apply binds `roots.json` path and live directory identity into `roots_sha256`. Formal and notes apply share the same target-role, roots-binding, and approved-plan before-digest checks. `migrate-report` treats a formal item as linked only when the receipt content, writeset, journal, and operation-head chain agree.

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

Only `uploaded`/`reused` rows whose remote sha256 equals the inventory sha256 may be linked. Apply re-checks the approved before digest, live page/location bytes, and root directory identity at the actual install, immediately before replace, keeps the dest inode open across the native replace, and installs by exchanging the dest inode so a concurrent temp+rename save is not dropped. If exchange is unavailable, apply refuses hardlink plus plain replace before covering the page, rolls back this ticket's unfinished location, and raises `PDF_APPLY_CHANGED` with reason `PDF_APPLY_EXCHANGE_UNAVAILABLE`; it does not install after bytes. Another dest read or hardlink cannot close the window between a last check and a plain replace. If the held inode, the displaced dest, or the installed path is rewritten during an exchange install, apply restores the concurrent dest, rolls back this ticket's unfinished unit, and refuses with `PDF_APPLY_CHANGED`. Same paper, different sha256 is `PDF_CONTENT_CONFLICT` and is not completion.

Link-only registration:

```bash
vpwiki pdf link-prepare --roots ROOTS.json --root-id vault-main \
  --paper-id arxiv:2204.03458 --drive-file-id FILE_ID --batch-id drive-b-link-1
```

That plan is `unverified` and is not migration success. A notes-vault PDF binding does not turn a link-only plan into `verified`.

## Notes-vault PDF bindings

A binding is a PDF-location source registration at `wiki/meta/pdf-bindings/{paper_page_slug}.json`. It is not a canonical capture, a paper-record, or a receipt (`capture_authorized` and `receipt_backed` stay false). It does not upload, edit Drive, move the original PDF, or write a verified locator. Verified Drive locators still come only from `migrate-prepare` / `migrate-apply`.

The frozen scope is the 19 engine-mvp arXiv papers that already sit in the 67-paper seed catalog. The seed row (or an existing note whose paper id matches it) is the bibliographic basis, not proof that the PDF is that paper. `identity_credential.method` is `pdf-internal-arxiv-id`: page 1 excerpt, its digest, the canonical paper id, and the PDF digest. Prepare and apply re-read the source-only PDF and require that excerpt on page 1. A seed title alone is not accepted. Intake `paper_id` is still not identity. Prepare also re-checks the intake seal, the intake blob, the `local_ref` bytes, and the basis file digest. An existing note stays a valid basis after migrate-apply adds the PDF section for that same digest; other note edits still invalidate it.

```bash
vpwiki pdf bind-prepare \
  --roots ROOTS.json --root-id notes-vault \
  --request BIND_REQUEST.json --batch-id BIND_BATCH
vpwiki-admin pdf bind-apply \
  --plan .work/BIND_BATCH/pdf-bind/plan.json \
  --roots ROOTS.json --root-id notes-vault \
  --approved-plan-sha256 PLAN_SHA256
```

`bind-prepare` only writes `.work/<batch>/pdf-bind/plan.json` and `diff.json`. Apply writes the binding and, when `papers/{seed_alias}.md` is missing, a source page that states the identity, title, source URL, and `PDF 已登记，尚未生成研究内容。` Existing notes are left byte-for-byte. The same paper with two digests, or one digest or `local_ref` bound to two papers, is refused at prepare and again under the apply lock, including when the second plan was prepared before the first apply. The first registration stays. Inventory then reads that binding's `local_ref` across roots and can mark the canonical paper `included` without copying bytes into `.raw/captured`. Cache files that merely share a digest or filename stay `intake-only`.

Apply re-checks preserve pages, seed basis files, and source PDFs at commit time, including while bindings are being written. If one of those changes, apply removes bindings it wrote in that attempt and leaves the edited note bytes in place.

Roll migration back before the binding. This applies to created source pages and to preserved notes. `bind-rollback` refuses while `wiki/meta/pdf-locations/{paper_page_slug}.json` is still present, so a locator is not left behind a deleted binding. The journal must name its plan and its `derived_write_set` must be exactly the paths sealed in those bindings (`wiki/meta/pdf-bindings/{slug}.json`, plus `papers/{seed_alias}.md` only when this bind created that source page). Any other path is refused. Each removal re-checks root identity, path, file identity, and the write-after digest. A failure in the middle restores files already removed in that attempt. Existing notes are not rewritten on the way back. Local PDFs and Drive files stay in place.

```bash
vpwiki-admin pdf migrate-rollback --journal MIGRATE_JOURNAL.json --roots ROOTS.json
vpwiki-admin pdf bind-rollback --journal BIND_JOURNAL.json --roots ROOTS.json
```
