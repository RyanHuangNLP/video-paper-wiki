# PDF locations, open, and offline behavior

DRIVE-B-R1 stores Drive/local PDF coordinates in independent location files. They do not replace `blob_path`, `source.path`, captured bytes, or sealed paper-record documents.

## Files

| Environment | Location file |
| --- | --- |
| Formal Vault / notes vault | `wiki/meta/pdf-locations/{paper_page_slug}.json` |
| Repository catalog | `catalog/pdf-locations/{paper_page_slug}.json` |
| Light workspace | `.pdf-locations/{paper_page_slug}.json` (not under `papers/` or `.raw/captured/`) |

`cache_policy` is always `keep-local`. Local originals are never deleted, moved, or renamed by these commands.

Notes-vault bindings live beside locations, not inside them:

| Environment | Binding file |
| --- | --- |
| notes vault only | `wiki/meta/pdf-bindings/{paper_page_slug}.json` |

That file records which source-only `local_ref` supplies the PDF bytes. It is a location-source registration, not capture or publication. `wiki/meta/pdf-locations/` remains the Drive/local locator written by migrate or link plans. A binding does not set `verification` to `verified`.

## Resolve

```bash
vpwiki pdf resolve --roots ROOTS.json --root-id vault-main --paper-id arxiv:2204.03458
vpwiki pdf resolve --roots ROOTS.json --root-id vault-main --paper-id arxiv:2204.03458 --prefer drive
vpwiki pdf resolve --roots ROOTS.json --root-id vault-main --paper-id arxiv:2204.03458 --offline
```

Default `--prefer auto` returns a readable, sha-matching local file when one exists, otherwise the Drive URL. `--offline` with `--prefer drive` is a parameter conflict. Offline without a valid cache returns `PDF_UNAVAILABLE_OFFLINE` and keeps the remote locator for later. Multiple PDFs without `--pdf-sha256` return `PDF_VERSION_AMBIGUOUS`.

`vpwiki` never starts a browser. `vpwiki-admin pdf open` submits an open request only; success does not mean the PDF loaded.

Unverified link-only rows can be shown and opened. They are not capture, parse, or migration success.
