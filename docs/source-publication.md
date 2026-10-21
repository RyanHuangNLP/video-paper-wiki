# Source publication

Source publication prepares and inspects an exact, complete knowledge change.
It binds the current receipt head and every managed file's bytes, size and mode,
then checks the prospective source records, evidence, histories and generated
pages. The agent API writes generated staging under `.work/**`; applying the
inspected transaction is a separate operator action.

This profile extends the source-version semantics described in
[source-version-semantics.md](source-version-semantics.md). The fixed upstream
transaction inspector still validates the prospective provenance ledgers. Local
typed audit reports `upstream_validated: false` because it does not run that
subprocess.

## Commands

```sh
vpwiki source-publication prepare \
  --proposal /absolute/input/source-publication/proposal.json \
  --batch-id knowledge-one --operation-id knowledge-one \
  --vault-root /absolute/vault

vpwiki source-publication inspect \
  --prepared /absolute/checkout/.work/knowledge-one/source-publication/request.json \
  --operation-id knowledge-one --vault-root /absolute/vault \
  --upstream-root /absolute/pinned/claude-obsidian

vpwiki source-publication audit --vault-root /absolute/vault
```

The commands use the usual JSON success/error envelope. The `data` field holds
the preparation, authority or typed-audit result. A successful preparation has
`published: false` and `applied: false`; inspection returns an inspected ingest
transaction with its exact request, staging and upstream authority.

The external input directory contains exactly `proposal.json` and `content/`.
Each content filename is the SHA-256 of its exact bytes. The canonical proposal
has four fields:

```json
{
  "schema": "video-paper-wiki.source-publication-proposal.v1",
  "kind": "knowledge",
  "payloads": [],
  "registration": null
}
```

For each proposed file, add a payload entry containing `path`, its canonical
Vault-relative destination, and `content_file`, the exact relative spelling
`content/<sha256>`. Entries are unique and sorted by UTF-8 path bytes. The content
directory contains exactly the unique referenced digests. No arbitrary caller
file path is accepted. The displayed JSON illustrates fields; the actual file
must use canonical JSON encoding.

## Python API

```python
from video_paper_wiki.source_publication import (
    prepare_source_publication,
    prepare_source_publication_source,
    inspect_source_publication,
    audit_source_state,
)

prepared = prepare_source_publication(
    batch_id="knowledge-one",
    operation_id="knowledge-one",
    vault_root=vault,
    payloads=exact_path_to_bytes,
)
```

Preparation validates every supplied destination, preserves immutable history,
and removes byte-identical writes. It validates the entire resulting state
before returning `no_change`. That result has null request path/hash, no changed
paths, and creates no request or transaction. It cannot be passed to inspection.
Repeating an unchanged preparation returns the same result. A different request
cannot overwrite an existing batch's fixed slot.

The durable request lives at
`.work/<batch>/source-publication/request.json`; its content lives in the sibling
`content/` directory. Request, content, ancestors and the transaction transport
remain bound to retained file/directory identities through both successful and
exception exits. Extra entries, portable aliases, links, unsafe private-file
modes, changed fixed slots and changed ancestors refuse the operation.

## Registration and migration

Markdown admission accepts `publication_profile="source-v1"`. The research CLI
exposes the same choice as `formal-source admit --publication-profile source-v1`.
The existing default remains `legacy-v1`.

First registration requires the actual external capture result and a distinct
batch and operation. It adds precisely one source row, claims precisely that
previously unclaimed raw Markdown, and preserves exact old/new source-ledger
snapshots. Capture authority and result must agree on the raw path, bytes,
transaction and observed modes. The source-profile result includes
`publication_profile: "source-v1"`; an already registered source is audited and
returns its existing result without another capture result or staged request.

A knowledge proposal may migrate a legacy paper to v2 by supplying its actual
registered Markdown association, matching observation, claim ledger, assessment
history, both derived-head registries and the complete compiler output. Existing
paper identities, aliases, claim text, ownership, references and stored history
remain bound. A v2 claim uses its canonical paper page and `^<claim-id>` anchor.
Existing v1 paper/repository anchor spellings remain supported. New repository
claims and code-mapping changes belong to the separate CODE increment.

Every association uses historical ledger bytes proven by the first registration
ingest. A later current ledger cannot substitute for a missing historical
snapshot. Snapshot filenames bind their actual bytes; a sequence-one generic
genesis claim or a source-ledger write proves historical snapshot provenance.
The one prospective registration snapshot is allowed only within its validated
capture/row/ledger context and cannot authorize an association before apply.
Historical snapshots retain their original spelling, including legacy formatting.

Source IDs cannot be added or removed by knowledge publication. Existing source
metadata, including source review status, changes only when explicitly supplied;
origin, content kind, content digest and ingestion identity remain fixed. Changed
source page links must be a unique sorted set of canonical pages. Accepted claims
must also satisfy the pinned inspector's source review/freshness rules.

Display decisions are explicit supplied records. Changing a display version does
not rewrite evidence. A rollback adds another decision continuing the current
chain. Registry rollback, event replacement and automatic human acceptance are
not supported.

## Complete-state checks

The collector validates source/claim ledgers, all paper/repository records,
assessment events, associations, display decisions, their derived heads,
Markdown observations, historical ledgers and recognized legacy code/parser
artifacts. It rejects unknown schemas or filenames in these semantic namespaces.
Unrelated historical managed files remain opaque and are included in the basis
and complete transaction preconditions.

The basis inventory contains file-only tuples of `path`, `sha256`, `size_bytes`
and `mode`, sorted by UTF-8 path bytes and hashed as canonical JSON without a
trailing newline. The prospective hash overlays business writes before advancing
the receipt/head. Every other existing file, including all prior receipts, is a
read precondition. Existing writes bind their original digest/mode/size; new
writes bind retained absence. A changed current basis returns
`SOURCE_PUBLICATION_STALE` with exit code 75.

Full typed state requires exact compiler page sets and bytes plus complete
derived registries. Internal legacy registration/migration baselines may read
structurally valid older records that are not yet renderable. Public typed audit
does not report that incomplete baseline as full success. Page deletion requires
a separate retirement path and returns `SOURCE_PUBLICATION_UNSUPPORTED_CHANGE`.

Legacy publication and the legacy base catalog return `SOURCE_PROFILE_REQUIRED`
when source-profile records or namespaces are present. They do not produce a
partial view. The source-aware catalog is a subsequent increment.

Requests/proposals are bounded to 8 MiB, business writes to 1022 paths, each
payload to 64 MiB and total proposed bytes to 128 MiB. Receipt histories are
bounded to 8192 entries. The existing transaction/bundle limits also apply,
including receipt/head and original bytes; entries are never omitted to fit.

The four additional packaged contracts are source-publication request,
source-publication proposal, source-publication authority and assessment-heads
v2, bringing the offline schema registry to 69 resources. Tests cover real pinned
transactions over synthetic input, explicit fixture decisions, no-op/stale paths,
legacy migration, complete reads, unsafe/racing paths, and byte-preserving backup
plus isolated restore followed by typed audit. These tests do not close any
real-data, operator or human gate.
