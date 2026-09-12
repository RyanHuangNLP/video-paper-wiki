# Source-aware catalog and citation lookup

`vpwiki source-catalog` searches published paper and code claims, their cited
source excerpts, source versions and coverage. Each command verifies the current
Vault history and compiled pages before returning a result. It works locally
without a model, an upstream checkout or network access.

Build one catalog in a fresh batch, then use that batch for reads:

```sh
vpwiki source-catalog build --vault-root /path/to/vault --batch-id research-01
vpwiki source-catalog status --vault-root /path/to/vault --batch-id research-01
vpwiki source-catalog query --vault-root /path/to/vault --batch-id research-01 --text '时序注意力'
vpwiki source-catalog lookup --vault-root /path/to/vault --batch-id research-01 --kind paper --key 'arxiv:2401.01234'
vpwiki source-catalog resolve --vault-root /path/to/vault --batch-id research-01 --claim-id clm-0123456789abcdef0123 --evidence-ordinal 0
```

Build creates `.work/<batch>/source-catalog/catalog.json` with mode 0600. An
identical build reuses its existing bytes. After the Vault, installed source,
schema resources or Python dependency versions change, use a new batch. A
different occupied cache returns `SOURCE_CATALOG_CONFLICT`; it is never replaced.
Status and the three readers do not create directories or write the Vault.

Status reports `absent`, `current` or `stale`, along with `coverage_counts` and
`uncovered_count`. A current catalog can still contain registered sources with no
canonical owner, unregistered captures or unreferenced derived artifacts. These
remain visible in coverage. Invalid source history or malformed cache bytes
return typed errors. A cache is a reproducible view of the current source state;
its contents do not grant publication or human approval.

Query accepts `--scope claims|source_excerpts|all`, `--paper-id`,
`--assessment all|accepted|provisional|contested|unsupported|deprecated`, and
`--lifecycle active|retired|all`. Defaults are all scopes, all assessments and
active references. Repository claims match a paper filter only when the
repository explicitly lists that paper. Excerpt hits inherit their claim's
assessment and lifecycle.

Search uses deterministic Unicode normalization, Latin word tokens and Chinese
character/bigram tokens with integer lexical overlap scores. `--limit` is 1–1000
(default 20); `--offset` is 0–1000000 (default 0). Results include `next_offset`
and `catalog_sha256`. Pass that digest with `--catalog-sha256` to bind subsequent
query, lookup or resolve calls to the same catalog. Queries are bounded to 512
characters, 4096 UTF-8 bytes and 1000 tokens, including normalization expansion.

Lookup supports `paper`, `repository`, `source` and `claim`. Papers also match
exact titles and declared aliases; repository names match case-insensitively.
Results include associated evidence and source coverage. An unknown lookup key
returns an empty match list.

Resolve uses the claim's original zero-based evidence ordinal. It returns the
exact cited excerpt, hash, source path, position and assessment/lifecycle. A
later display-version selection or rollback does not retarget that citation.
Markdown preserves exact Unicode text. Code uses the established normalized
line slice. A legacy PDF citation resolves from its existing parser artifact
only when its JSON pointer, page, character span and text hash are reproducible.
Otherwise it reports `UNSUPPORTED_LEGACY_RESOLUTION` with a fixed reason; a
supplied invalid span or mismatched hash is an error. No original PDF is parsed
by these commands.

Fully rendered legacy and modern published states are supported. A structural
legacy state must complete its explicit source-publication migration first.
Backup and isolated restore preserve the source inputs; rebuilding in the same
runtime yields equal catalog bytes. Changes to runtime versions intentionally
produce a different generation digest.
