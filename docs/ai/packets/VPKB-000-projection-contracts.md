# VPKB-000-projection-contracts — preparation only

Parent VPKB-000. Status: design-pending; no implementation release.
Predecessor: VPKB-000-transaction-facade (currently in progress).
Architect/Builder/Steward retain the existing model and ownership arrangement.

This is the remaining shared projection contract work, not an alternate path
around facade acceptance. The complete VPKB-000 milestone also needs dependency
and licensed-source evidence; neither a successful facade nor this planning
note closes it. No retrieval-config/gold, candidate depths, exact evidence join,
runtime index writer, real Vault, parser models or human gate belongs here.

## Requirements that must become exact before implementation

- catalog.sqlite base DDL, every PK/FK, deterministic ordering and a versioned
  canonical row export. Compare logical rows, not physical SQLite file bytes.
  Canonical records/ledgers/review heads/taxonomy/immutable manifests supply
  facts; Markdown/chunk text may not supply missing canonical facts.
- A projection-generation fingerprint and stale comparison with explicit input
  inventory and version material. A missing or invalid canonical input is a
  refusal, not a value silently omitted from the digest. Runtime results and
  wall-clock index-build time are not business truth.
- An exact versioned runtime comparator with JSON-pointer volatile allowlists,
  plus strict rejection/retention rules for unexpected fields. Do not recursively
  delete every field whose name looks like a timestamp. Markdown is byte-stable
  and receives no volatile-field exclusions at all.
- Pinned upstream chunk and BM25 schema observations and public-CLI CJK
  tokenization/build/query fixtures; do not implement another tokenizer or add
  extension fields to upstream objects. Preserve overlap chunks and identity;
  later VPKB-001 maps them to canonical evidence units separately.
- Projection compatibility fields from transaction-facade revision 1: constant
  status=generated, canonical UTC date aliases and taxonomy-derived sorted tags.
  They are derived presentation fields, not ingestion/review/gate state.

## Initial pinned-source observations (not behavior acceptance)

These observations refer only to commit
`9f8c1199047eac2c3828496279fbb7ba9540b90b`. Architect read the actual emitted
objects as well as the introductory documentation; they are not always equal.

- `scripts/contextual-prefix.py:787` emits chunk schema_version=1 with
  page_path, page_address, chunk_index, raw_text, contextualized_text, **prefix**,
  prefix_source, char_count, body_hash, page_body_hash and created_at. The file's
  introductory schema example omits prefix, so it must not be used alone to
  freeze a closed schema. The candidate volatile pointer is exactly /created_at.
- `scripts/bm25-index.py:537` emits index schema_version=2 with params,
  doc_count, avg_dl, updated_at, vocab and docs. Its actual docs entries also
  contain body_hash/page_body_hash (`:519`), omitted in the introductory example.
  The candidate volatile pointer is exactly /updated_at at the index root.
- The index stores relative chunk paths, not absolute Vault paths. Public
  retrieve output may contain absolute_path and is a different contract; do not
  treat that response as the index object or add it to a broad comparator.
- Existing `video_paper_wiki.jcs` is intentionally integer-only, while genuine
  BM25 output contains fractional params/avg_dl. The runtime comparator must
  freeze finite-number serialization/equality explicitly; sending these objects
  to the current identity JCS would fail. Do not silently broaden that existing
  authority or discard numeric fields to make a comparator pass.
- The pinned index validator allows some values more broadly than its current
  emitter. Decide whether a comparator accepts emitter output only or legacy
  valid index variants, with fixtures and explicit error codes. Do not silently
  claim that extension validation is the upstream validator.
- `tokenize` at bm25-index.py:333 uses bounded NFKC/token growth rules. Public
  build/query fixtures must demonstrate the exact CJK terms and compatibility;
  static description alone is not a passing tokenizer contract.

Before release, Architect supplies a complete versioned normative document,
Builder and Steward independently review it, and packet/schema/API ownership,
fixtures and acceptance evidence paths are assigned. Do not start production
rendering or SQLite file mutation from this preparation note.
