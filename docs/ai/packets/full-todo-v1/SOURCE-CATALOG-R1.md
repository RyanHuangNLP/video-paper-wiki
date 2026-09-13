# SOURCE-CATALOG R1 — current source-aware lookup and exact citation resolution

This contract requires its later exact freeze and accepted SOURCE-CONVERSION
baseline before implementation. Root implements locally; existing assistants
review independently and serialize Git/PR/CI. The older draft/advice remain
history. Advice that invented fields, accepted invalid orphan states, or called
an occupied fixed slot replaceable is superseded by the concrete rules here.
Keep the 67 seed/overlay entries, legacy catalog schemas/profiles/SQL, original
PDF policy, zero-egress CLI, real-Vault/operator/human gates and no-merge boundary.

## Public surface and authority

Add `vpwiki source-catalog build|status|lookup|query|resolve`, each requiring
`--vault-root` and `--batch-id`. No upstream checkout, config, remote service or
light index is needed. The cache slot is exactly
`.work/<batch>/source-catalog/catalog.json`. There is no arbitrary output/cache
path argument. Only build may create generated files. A new live generation
uses a fresh batch; an occupied differing slot is never overwritten.

Keyword-only public APIs in source_catalog are build_source_catalog,
source_catalog_status, lookup_source_catalog, query_source_catalog and
resolve_source_catalog. They return ordinary agent-safe success/error envelopes
through the CLI. API errors are ContractError with original code, message,
structured instance_pointer and exit_code. Do not erase lower-level safety,
history, source-publication or schema errors behind a generic stale result.

Every command uses one retained `_vault(vault_root, None)` session for
audit_integrity and `collect_source_state(require_rendered=True)`. This requires
the complete canonical compiled-page set and all modern head registries. There
is no `allow_legacy_structural` relaxation: pre-publication structural states
must finish their explicit migration before entering this catalog. Fully typed
and fully rendered legacy v1 states remain supported. Empty initialized Vaults
and valid registered-but-unowned sources remain supported. An orphan parser,
unknown semantic path, missing source, unsafe path or broken history is an
error, never an apparently successful `orphan_invalid` cache row.

All retained Vault ancestors, inventory sets and bytes are verified on success
and exception through the existing retained implementation. The cache file,
every named cache ancestor and an absent slot/first missing ancestor are also
retained across reconstruction and result assembly. Reading status on an absent
batch must not create it. Final safety failure has priority over ordinary
absence, stale, not-found or input errors. Reuse existing no-follow primitives;
never stat a path after a race and adopt that identity as the original one.

## Artifact, complete rows and deterministic generation

The single new public artifact schema is
`video-paper-wiki.source-catalog.v1`. Its closed root has exactly schema,
profile, basis, generation, rows and catalog_sha256. Profile is source-catalog-v1.
The stored bytes are JCS UTF-8 without BOM or added LF. catalog_sha256 is
SHA-256 of `video-paper-wiki.source-catalog.v1` followed by one NUL byte and JCS
of the root with catalog_sha256 omitted. There are no timestamps, absolute paths,
batch IDs, inode/device/mtime values, access-order values or cache authority
claims in the artifact. Those belong only to local safety checks.

`basis` contains operation_head_sha256, inventory_sha256 and inventory. Inventory
is the complete audited path/hash/size/mode list from snapshot_material, sorted
by exact path. It includes actual head, receipts, captured artifacts, parser/run
files, records, ledgers, historical source snapshots and generated pages. No
semantic subset may replace that list.

`generation` contains profile_sha256, resources, implementation, runtime and
rows_sha256. `resources` is the complete sorted list of canonical schema resources
plus taxonomy/v1.json and catalog/source-catalog-v1.json, each with logical
resource path, SHA-256 and size. The schema list must come from the package/repo
resource registry, never CWD. `implementation` includes every .py file recursively
within the installed video_paper_wiki package, with package-relative name, exact
SHA-256 and size; this deliberately binds all transitive compiler/reader/query
code without an incomplete hand-picked dependency list. `runtime` contains
Python implementation and complete version, Unicode database version, and exact
jsonschema/referencing/rpds-py versions. No OS or installation path is included.
rows_sha256 hashes JCS of the complete rows object. Implementations and resources
are captured/rechecked around projection; changed generation bytes refuse.

Rows has exactly these groups, each sorted by its declared key without removing
rows: documents(path), papers(paper_id), repositories(repo_id), claims(claim_id),
evidence(claim_id,ordinal), sources(source_id), associations(association_id),
display_decisions(decision_id), assessment_heads(claim_id), display_heads(paper_id),
artifacts(path), compiled_pages(path), coverage(kind,id). Key comparison is
exact UTF-8 byte order; ordinals are zero-based original citation positions.
Duplicate group keys refuse. Arrays that represent original record data retain
their original order; newly derived identity sets are sorted unique arrays.

The schema freezes these closed row shapes:

- documents: kind, path, sha256, json_text. Include every parsed semantic JSON
  document from collect_source_state, plus both actual ledgers and every source
  ledger snapshot. json_text is exact original UTF-8 JSON text, not a reparsed
  serialization; this preserves optional-key presence and historical contextual
  bbox floats without passing those floats through the integer-only JCS encoder.
- papers: paper_id, record_path, record_schema, title, title_zh, authors,
  published_at, aliases, taxonomy, code_urls, source_ids, association_ids,
  display_association_id, active_extraction_path, active_extraction_sha256.
  New nullable projection fields do not reinterpret old schema fields; v1
  association_ids is empty and display_association_id is null.
- repositories: repo_id, record_path, canonical_repository, canonical_commit,
  paper_ids, officiality, license, archived. Missing old archived projects null,
  with exact presence still visible in documents.
- claims: claim_id, text, owner_kind, owner_id, page, reference, assessment,
  reviewed_at, risk, confidence, location, head_event_id, head_event_sha256,
  evidence_profile. reference is the exact paper section or repo capability ref;
  lifecycle comes from that ref. Assessment comes from validated terminal history.
- evidence: claim_id, ordinal, source_id, kind, wire, association_id,
  display_association_id, resolution. wire is the exact three-field existing
  ledger evidence object. A referenced Markdown association is independent of
  the selected display association. Legacy PDF/code association_id is null.
- sources: source_id, row. row retains the complete validated source-ledger row
  with its original optional presence and arrays. Receipt/history bindings are
  already carried by basis, documents and exact association registration fields;
  do not manufacture first-registration proof for a legacy web-only source.
- associations: association_id, path, sha256, document. document is the exact
  validated existing source-version-association object.
- display_decisions: decision_id, path, sha256, document. document is the exact
  validated existing source-display-decision object.
- assessment_heads: claim_id, event_id, event_sha256, evidence_profile.
- display_heads: paper_id, head. head is the exact existing derived display-head
  row, not a new authority or display decision.
- artifacts: path, kind, sha256, size_bytes, source_ids. Include every `.raw/`
  inventory file, including snapshots, captured files and unreferenced derived
  material. source_ids is the exact derived set of sources whose origin/capture,
  run ancestry or association links the file; a historical source-ledger snapshot
  may cover several sources. Unknown attribution stays an empty set.
- compiled_pages: path, sha256, text. Include the complete compiler output.
- coverage: kind, id, state, source_ids, paper_ids, repo_ids, reason. Emit one
  row per source and one per artifact, even when covered. Source states are
  registered_owned or registered_unclaimed. Artifact states are captured_registered,
  captured_unregistered, derived_referenced or derived_unreferenced. A source is
  owned when referenced by a canonical paper's source_ids or a repo claim's
  evidence; artifact reference additionally includes actual legacy active
  extraction and complete parser/code/association ancestry. Keep unreferenced
  historical files visible. Reasons are fixed profile strings, not model prose.

The new catalog/source-catalog-v1.json resource lists all row groups and keys,
constants, digest/tokenizer rules, resolution policy and limits. Public schema
and code validate all closed shapes and identities; source reconstruction supplies
semantic authority. Foreign JSON, partial rows or self-consistent forged hashes
never become authority. Each status/lookup/query/resolve reconstructs the entire
catalog from the same retained current Vault and generation material, then
requires exact canonical bytes to equal the retained cache before using it.

Limits: existing narrower Vault/source bounds remain; at most 100000 inventory
entries, 1000000 total rows, 64 MiB complete cache bytes, 16 MiB per exact JSON
document string, 65536 UTF-8 bytes per resolved excerpt, 512 Unicode characters
and 4096 UTF-8 bytes per query, 1000 query tokens, query limit 1..1000 and offset
0..1000000. Check before staging, never trim a source row or silently truncate
an excerpt to satisfy the bounds. An oversized legacy excerpt is explicit
unsupported (`excerpt_limit`) for that evidence; malformed or mismatched evidence
is an error. All other exceeded limits return SOURCE_CATALOG_LIMIT, exit75.

## Citation resolution

Every evidence resolution is computed during reconstruction from retained source
bytes. The closed resolution object contains state, reason, excerpt,
excerpt_sha256, source_path, source_sha256, position. RESOLVED has nonempty exact
excerpt/hash and null reason. UNSUPPORTED_LEGACY_RESOLUTION has null excerpt/hash
and a fixed reason. The original evidence wire remains in the enclosing row.
Position is one closed union: Markdown {kind,charspan,page_anchor}, PDF
{kind,page,ref,charspan}, or code {kind,lines}. No bbox is reinterpreted as a text
offset. Null position is permitted only for explicit unsupported legacy input.

Markdown calls decode_evidence and resolve_markdown_locator with the exact bound
association and raw bytes, returning exact Unicode text including CRLF/combining
characters. Source ID, path/hash, association reference, page interval and excerpt
hash must all match. Historical citations remain valid through display selection
or rollback when their own bound source history is intact.

Code uses the existing unique inspected manifest match and validate_code_locator
against exact retained capture bytes. Return the same UTF-8 line slice used by
code_snippet_sha256, including established newline behavior; compare its hash.

Legacy PDF resolves only an exact existing JSON pointer to a text-bearing parser
object: standard JSON Pointer decoding, object .text string, a matching page_no
in its .prov array, and a valid nonempty Unicode charspan with matching
text_sha256. Verify artifact_path/artifact_sha256 and the already validated
raw/parser/run/source ownership first. An otherwise validated legacy locator
whose object/page/text cannot be reconstructed returns a fixed explicit
UNSUPPORTED_LEGACY_RESOLUTION reason; a supplied hash/span mismatch refuses with
SOURCE_CATALOG_EVIDENCE_INVALID, exit75. Never guess OCR text, parse an original
PDF, download a model or reinterpret contextual bbox values.

resolve accepts required --claim-id and --evidence-ordinal, optional
--catalog-sha256. It returns binding (profile/catalog_sha256/basis), claim ID,
ordinal, exact evidence row and the owning claim's assessment/lifecycle. It uses
the citation association regardless of current display. Unknown claim/ordinal
returns SOURCE_CATALOG_NOT_FOUND exit75. The ordinal must be a real integer,
not a Boolean or coerced float. No caller locator override is accepted.

## Build, status, lookup and lexical query

Build reconstructs before cache installation. Retain the fixed absent/present
slot and all relevant .work/batch ancestors, then install via the same retained
session. Absent creates once with mode0600; byte-identical existing content reuses
without rewriting; differing existing bytes return SOURCE_CATALOG_CONFLICT exit75.
Symlink/hardlink/nonregular/permission/named identity changes return WORK_PATH_UNSAFE.
Do not silently adopt a foreign byte-identical file that appeared after an absent
observation. Recheck all edges, complete bytes and original Vault on every exit.

All result objects carry profile, catalog_sha256, basis and counts; build also
has state=created|reused and cache_path. The path is generated output metadata,
not part of the cache hash. Status returns state=absent|current|stale with
cache_sha256 (actual whole-file SHA-256 or null) and expected_catalog_sha256.
Absence is a success only after valid current reconstruction. A well-shaped,
self-hash-valid old cache with different generation/rows is stale, including a
self-consistent forged projection. Malformed/noncanonical bytes return
SOURCE_CATALOG_INVALID exit2, without rewriting. Status coverage_counts and
uncovered_count remain separate from cache state: current can still have gaps.
Status does not claim human readiness. Non-status readers require current cache
or return SOURCE_CATALOG_ABSENT / SOURCE_CATALOG_STALE, exit75. If supplied,
catalog_sha256 must exactly equal the current reconstructed digest or is stale.

Lookup accepts --kind paper|repository|source|claim, required --key and optional
--catalog-sha256. It matches exact canonical identity for all kinds; paper also
matches exact title/title_zh and declared alias, repository also exact repository
name case-insensitively. Return all matching rows in stable identity order;
an empty result is a valid lookup. Include relevant source coverage and evidence
rows, not just one preferred display version. No free-form remote lookup.

Query requires --text; optional --scope claims|source_excerpts|all (default all),
--paper-id, --assessment all|accepted|provisional|contested|unsupported|deprecated
(default all), --lifecycle active|retired|all (default active), --limit (default20),
--offset (default0), --catalog-sha256. Exact filter values and bounded integers
are validated before IO. Paper filter includes that paper's own claims and repo
claims when the repo explicitly lists it; all source-excerpt hits inherit their
owning claim's history/lifecycle filters. Unclaimed sources remain in lookup and
coverage rather than being represented as invented cited excerpts.

Tokenizer: Unicode NFKC then casefold; ASCII [a-z0-9]+ words, each Han character
and each adjacent Han bigram within contiguous U+3400..U+4DBF, U+4E00..U+9FFF,
U+20000..U+2FA1F runs. Other Unicode alphabetic/digit contiguous runs are terms,
with punctuation/whitespace as boundaries; retain duplicates for term counts.
Document tokens are deterministically capped only by existing text/cache bounds,
never silently truncated. A nonblank query with no tokens is invalid.
Score is integer Dice overlap: floor(2000000 * sum(min(query_count[token],
document_count[token])) / (total_query_tokens + total_document_tokens)). Emit
positive-score hits only. Sort descending score, then claims before excerpts,
claim_id UTF-8 bytes and evidence ordinal (claims use -1). Results contain kind,
claim_id, owner_kind/owner_id, source_id/association_id/display_association_id
(nullable for claim hits), evidence_ordinal (nullable), exact text, score,
assessment, lifecycle. Return total_matches, offset, limit and next_offset
(null at end). Paging remains bound to catalog_sha256; no mutable cursor state.

The legacy catalog_status collector catch must preserve SOURCE_PROFILE_REQUIRED
and its exit75 instead of rewriting it to CATALOG_STALE. Make only that precise
compatibility fix; preserve all other legacy status/query/build behavior.

## Acceptance and delivery

Freeze new owned files plus the narrow CLI/legacy-status/command-tree/schema-test
integration paths. Test empty, legacy, Markdown and mixed catalogs; all coverage
states reachable in valid audited fixtures; exact code/Markdown/PDF resolution
and explicit unsupported/mismatch cases; selected-vs-cited source with display
selection/rollback; accepted/provisional/invalidation/retired filters; stable
ordering and pagination including Chinese queries; absent create, identical reuse,
different cache, forged rows, corrupt/noncanonical cache, runtime/resource/source
changes, all limits and named-edge/complete-set races on success and exception.
Verify a synthetic backup/isolated restore rebuilds equal rows/digest in the same
runtime. Replay legacy query compatibility, both locked full suites and installed
wheel/resource parity, then deliver draft PR95 -> integration with exact-head CI.
SOURCE is complete only after this accepted increment; DISCOVERY expansion, CODE,
DOMAIN, SYNTHESIS, QUALITY and PRODUCT remain authorized subsequent work.
