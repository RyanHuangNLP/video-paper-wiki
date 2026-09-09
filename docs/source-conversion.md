# Convert lightweight knowledge into a formal paper

`vpwiki-research formal-source convert` turns one current lightweight knowledge
record into a proposed canonical paper with exact Markdown citations. The source
must already have been captured and registered in the destination Vault. The
command returns a source-publication request for inspection.

Each provisional section becomes one claim. New claims remain provisional.
Existing claims keep their assessment and event history when their evidence is
unchanged. Changed evidence adds a system invalidation event and returns the
claim to provisional. Free-text concepts appear in `unmapped_concepts`; use the
paper metadata's pinned taxonomy terms to publish concept links.

## Prepare a conversion

Select the current `record_id` from the lightweight knowledge listing and supply
the corresponding Markdown capture authority. A new paper also needs a UTF-8
JSON metadata file, for example:

```json
{
  "schema": "video-paper-wiki.source-conversion-metadata.v1",
  "paper_id": "arxiv:2401.01234",
  "title": "Example paper",
  "title_zh": "",
  "authors": [],
  "published_at": "2024-01-03",
  "aliases": [],
  "taxonomy": [],
  "code_urls": [],
  "arxiv_id": "2401.01234"
}
```

This example is illustrative. Supply the actual paper identity and publication
date. The canonical paper ID must match the capture authority; the lightweight
paper ID remains its `sha256:…` identifier. Empty optional bibliography arrays
are permitted. For an existing paper, omit `--metadata` to retain its bibliography.
Supplied metadata must keep existing aliases in their exact spelling and order.

```sh
vpwiki-research formal-source convert \
  --workspace-root .work/my-library \
  --paper-id 'sha256:<light-paper-digest>' \
  --record-id '<current-record-digest>' \
  --capture-authority .work/capture-authority.json \
  --metadata .work/paper-metadata.json \
  --batch-id convert-paper \
  --operation-id convert-paper \
  --vault-root /path/to/vault \
  --proposed-at '2026-09-09T12:00:00Z'
```

`proposed_at` uses whole UTC seconds. It must not precede a changed ledger,
record or event's existing timestamp. `published_at` separately accepts an actual
date or UTC timestamp, including fractional seconds.

Inspect the returned `request_path` using the existing command:

```sh
vpwiki source-publication inspect \
  --prepared '<request_path>' \
  --operation-id convert-paper \
  --vault-root /path/to/vault \
  --upstream-root /path/to/pinned/claude-obsidian
```

Preparation and inspection leave the Vault unchanged. Applying an inspected
transaction remains the existing operator workflow. The result's `conversion`
object lists created, invalidated, unchanged and location-migrated claim IDs.
Repeated conversion with unchanged evidence and metadata returns `no_change`
without creating a publication request or event.

## Existing records and refusals

Completed batch and selective-refresh records retain their validated completion
and ancestry. Conversion reads a private retained snapshot and does not require
a current lightweight search index. Its generated diagnostic mirror lives below
`.work/<batch>/source-conversion/` and has no publication authority.

A legacy paper can upgrade while retaining its old claims, evidence, sources and
events. Claim locations acquire canonical block anchors. An unresolved legacy
claim with no evidence, or an old source ID that cannot be represented by retained
associations and current citations, produces `SOURCE_CONVERSION_UNSUPPORTED_CHANGE`.
Missing first-registration ledger history produces `SOURCE_REGISTRATION_INVALID`.
Stale lightweight heads or source bindings must be refreshed before retrying.

The first formal publication also makes an old missing `reviewed_at` field
explicitly null on every unreviewed legacy claim, including claims owned by
other papers or repositories. Their text, assessment, evidence, notes and event
history stay unchanged. This field migration does not imply a human review.

Conversion preserves existing display choices. For a new or upgraded paper with
no explicit display decision, the display and active-extraction pointers are null.
Exact citation resolution proves which text was cited; human review determines
whether that text supports the claim. Original PDF provenance stays declared
provenance, and this command does not read an original PDF or contact a network.
