# DRIVE-B sample inventory / uploaded-manifest handshake

These fixtures are **samples for agy**, not evidence of a real Drive upload.

- `sample-inventory.json` — `video-paper-wiki.pdf-migration-inventory.v1`
- `sample-uploaded-manifest.json` — `video-paper-wiki.pdf-upload-manifest.v1`

The `inventory_sha256` inside the sample manifest matches the sample inventory.
Replace `drive_file_id`, `parent_chain`, and `remote_pdf_sha256` with values from a real Drive A read-back before migrate-prepare against live roots.

Drive A root folder id: `1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW`
Path convention: `pdfs/{category}/{paper_dir}/original.pdf`

When joining a real Drive A reused row, keep the manifest path. Example:
`pdfs/Evaluation Benchmarks and Metrics/arxiv-1812.01717/original.pdf`

A draft uploaded-manifest with `inventory_sha256: null` is fail-closed until agy binds the inventory digest.
