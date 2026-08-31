# Catalog rows and generation — architecture draft 1

Status: NOT FROZEN; no SQLite implementation release. Part of the complete
VPKB-000-projection-contracts packet. Runtime revision 1 is separately frozen;
canonical input/locator design is in projection-input-v1.md. This document
records Architect decisions and remaining exact DDL work, not a finished
database schema or evidence that VPKB-000 is complete.

## Projection and storage boundaries

`catalog.sqlite` is disposable derived state. Its business rows come from the
validated canonical inventory, never Markdown, a chunk, a model response or a
prior database row. A missing canonical field is not an invitation to infer a
value. No writer, renderer, Vault enumeration, file replacement or query CLI
is released by this draft. The future atomic builder belongs to VPKB-001 and
the end-to-end canonical compiler to VPKB-002.

Freeze one base DDL and a table/column/type/key manifest together. Do not
substitute a generic untyped JSON store for the primary/foreign-key contract.
The base excludes chunk-to-evidence joins, query/gold eligibility, candidate
depth, rankings, score normalization, evaluator policy and retrieval config.
Those later tables must be explicitly versioned extensions, not unannounced
additions to the base row-export contract.

## Required relational coverage

The exact columns/SQL are still under review. The following facts and links
must all be represented before DDL release; this list cannot substitute for
the eventual machine-checkable column manifest.

| Table family | Required facts and key relationships |
| --- | --- |
| canonical_inputs | Unique canonical path, kind and exact file SHA; no generated index/page inputs |
| papers | Canonical paper ID, complete page metadata and dates, input path, active extraction path/hash |
| paper_authors, paper_aliases, paper_code_urls | Original ordered values; authors may repeat; optional code_urls absence differs from present empty |
| repos, repo_papers | Canonical repo ID, original repository spelling/full commit, officiality/license/archive metadata, ordered FK paper IDs |
| subjects and claim_refs | Paper/repo owner FK, canonical stable subject, globally unique claim owner, owner ordinal, section/capability, lifecycle; core is paper-only |
| sources, source_pages | Existing source-ledger record fields, source supersedes FK, ordered page references; no new source-ID algorithm |
| paper_sources | Ordered paper-to-existing-source FKs |
| claims | Existing ledger text/risk/confidence/notes/location/supersedes and claim ID; owner identity must recompute correctly |
| claim_evidence | Original ordered evidence, source FK, wire relation, complete tagged locator; domain relation follows the explicit wire codec |
| assessment_events, assessment_heads | Immutable complete events, same-claim predecessor links, one terminal head FK per claim derived from the complete validated chain; no persisted head registry input; current assessment/date derives from this head |
| taxonomy_axes, taxonomy_terms, aliases | Supplied canonical labels, aliases and ordinals; term PK includes axis; do not invent a term-parent field absent from current taxonomy |
| paper_taxonomy | Ordered FK pairs to the supplied taxonomy; do not silently deduplicate currently allowed repeated refs |
| artifacts, run_manifests | Canonical immutable paths/hashes and complete parser/version/config/model/output bindings, including historical versions |
| code_origins, code_manifests | Logical repo/full-commit/path/source binding and capture/line metadata; one raw byte source may have several logical origins |
| alignment_manifests, alignment_capabilities | Manifest-qualified paper/repo/commit, officiality/license/archive facts, the original ordered officiality.evidence PDF locators, and all five capabilities, code locators, absence scope/search patterns and checkpoint_kind |

Do not infer capability `unverified` merely because no alignment manifest is
supplied. Missing alignment data and a supplied manifest explicitly stating
unverified are different. Repo-record currently has no active-alignment
selector: retain versions by immutable path/hash and refuse to select a
"latest" one from wall clock, directory order or lexicographic hash. Defining
a canonical selector, if needed for a current Code Page, must precede that
production compiler in VPKB-001/002.

Optional non-nullable scalar fields use SQL NULL for absence. A field allowing
both absence and explicit null needs an explicit presence bit as well, or an
equivalent closed tagged representation defined in the column manifest. For
optional arrays, retain an explicit presence bit plus ordinal children. Do not
conflate absent, null, false, zero, empty string or empty array. Required
booleans use integer 0/1 after validated conversion; arbitrary truthiness is
not a conversion rule. Preserve every array order and duplicate allowed by
its canonical schema, even when the value is not currently queried.

Full locator strings carry fractional bbox values without SQLite REAL or a
change to identity JCS. Any additional derived locator columns must be
recomputed from that exact validated string, never become a second source.
Code origins are not deduplicated by raw source ID alone. Historical PDF
artifacts and run manifests remain addressable after active extraction moves.

Manifest hash closure must be specified field by field. In particular a
run-manifest also contains ingest-plan/prepared/draft/receipt provenance hashes;
preserve those hashes, but do not require importing pending drafts or staging
documents as canonical business-fact inputs. Its document/config/model hashes
need separately defined immutable artifact bindings. A hash-only provenance
field is not proof the referenced bytes exist; the final mapping must name
which facts require a resolved artifact FK and which retain a supplied digest.

## Canonical row export decisions

The proposed export root is a closed `video-paper-wiki.catalog-rows.v1`
object with required schema, ddl_sha256, generation_sha256 and tables.
The table inventory and ordered columns must exactly equal the released base
manifest, including every empty table. A table has exactly name, columns and
rows. Rows are positional arrays with exactly one value per declared column.
No sqlite_master internals, page numbers, rowid, VACUUM output, journal state,
physical database bytes or build timestamps enter this export.

Values are exact built-in scalar strings, signed 64-bit integers or null as
allowed by the column declaration. Do not accept float or bool in an integer
cell, silently apply SQLite affinity, stringify a number, normalize text, or
replace a missing column with null. An artifact contributes its declared raw
SHA, not an embedded unbounded BLOB. Any non-scalar data column must have its
own exact canonical encoding in the final column manifest.

Before sorting or hashing, validate complete table/column shape, types,
nullability, PK uniqueness, declared unique keys, FK closure, enum constraints
and contiguous zero-based child ordinals. A duplicate is an error rather than
an upsert. Every PK component is non-null. FK checks run independently of
SQLite connection defaults; the later connection must also enable foreign
keys. Database constraints do not replace complete input/row validation.

Table order is the ASCII table-name order in the frozen manifest. Within each
table sort by the complete PK in declared PK-column order: integers compare
numerically, strings compare their exact UTF-8 bytes, matching SQLite BINARY.
No locale, case folding, Unicode normalization or undefined NULL order is used.
PK tuple element types are fixed by the table, never mixed. This row order is
distinct from JCS's UTF-16 object-key order; arrays preserve the row order.

Canonical export bytes are existing integer-only JCS of that complete valid
root, without a newline. SHA-256 is over those bytes. SQL insertion order and
physical file bytes may differ while canonical export remains equal. A
non-equivalent canonical field, ordinal, FK, presence bit, version or generation
change must be retained or refused, never dropped to manufacture stability.

## Generation fingerprint decisions

Generation describes canonical input and the implementation/version material
used to derive a projection. It must not depend on the projection output's own
hash; that would create a cycle. Bind output hashes to a generation in a
separate future build-result record, without adding fields to the pinned
upstream chunks or BM25 index.

The final generation manifest must bind all of the following explicitly:

- The complete validated canonical path/kind/raw-SHA inventory, including
  authoritative timestamps, all review history from which unique heads derive, source assessment
  material, retired refs and immutable versions. There are no volatile input
  exclusions. Raw-byte reformatting may conservatively invalidate generation.
- Exact schema and taxonomy source digests and their versions. A label or
  policy change is material, not just an ID-set change.
- The input/locator, DDL/row-export, deterministic compiler and runtime
  comparison contract versions and source digests. A new implementation cannot
  retain an old fingerprint merely because the package version was not bumped.
- The declared relevant vpwiki implementation source inventory and package
  version, with an exact frozen inventory rather than an arbitrary caller map.
- The fixed claude-obsidian commit and relevant script source digests, plus
  exact Python implementation/version and `unicodedata.unidata_version`.
  Python 3.12 and 3.13 use different Unicode data; agreement on a CJK fixture
  does not prove all normalization/tokenization behavior identical.
- The explicitly supported synthetic-prefix mode and fixed emitted chunk/BM25
  profile versions; recorded non-synthetic objects may be compared by the
  runtime API, but do not qualify as a deterministic no-LLM build.

Exclude wall-clock build time, hostname, absolute Vault/temp paths, run IDs
invented only for the index build, mtime, physical SQLite version/page layout,
and the generated Markdown/chunk/BM25/database bytes themselves. Canonical run
manifest IDs and timestamps are input facts and remain included; this
exclusion is not a blanket rule for every field named run_id or timestamp.

The proposed fingerprint is lowercase SHA-256 of integer-only JCS of a closed
versioned generation material object, no LF. The exact field/filename manifest
and public API still require review before release. A pure digest function
cannot attest that a supplied software digest describes code actually loaded
by a process; VPKB-001 must collect and authenticate the current material.

Stale comparison must validate both manifests and compare complete versioned
fingerprints. A missing stored generation is stale. Malformed current input,
an invalid stored manifest, a missing referenced canonical file or unknown
version is a typed refusal, not a synthesized empty digest or `fresh=true`.
Changing a human assessment/head, evidence relation, taxonomy or retired ref
makes the old generation stale even if a rendered sentence happens to match.
Atomic replacement, retained old index on failure and actual runtime-to-
generation binding are later builder responsibilities, not assertions of this
pure contract.

## Required decisions before release

Complete the input kind/path/closure and byte-budget table; freeze the complete
event-graph/head derivation and all ledger/taxonomy application profiles; resolve immutable
manifest locations and association rules; then publish complete SQL and its
exact ordered column/PK/FK manifest. Obtain both independent reviews, including
installed-SQLite FK probes and ordering/null/duplicate/export vectors. No
implementation may fill these open points through undocumented assumptions.
