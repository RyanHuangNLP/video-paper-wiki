# Base catalog rows and generation material — revision 1

Status: FROZEN by Architect, 2026-09-01, paired with projection input revision 1.
The reviewed structural resource is 34 SQLite STRICT tables and 230 columns. This
revision authorizes only pure foundation implementation and tests. It does not release
a filesystem mapper, SQLite writer, renderer, atomic compiler/index build, query CLI,
publication transaction or human gate.

## Derived-state boundary

`catalog.sqlite`, Markdown, chunks and BM25 are disposable outputs. Catalog business
rows are a typed relational representation of the complete canonical input profile;
they never come from a prior database, generated page, search result or model guess.
A missing field stays absent/null according to its source profile and is never filled
from another representation.

VPKB-000 validates supplied rows and binds them to a declared generation material.
This proves closed structural consistency only. It cannot prove that arbitrary rows
were mapped from the inventory bytes or that supplied implementation/resource/
dependency/upstream hashes and versions name code actually loaded. VPKB-001 must
authenticate the corpus, collect software material and perform the deterministic
byte-to-row mapping. VPKB-001/002 retain all
real ledger, producer, PDF/code evidence, publication and atomic replacement duties.

The base intentionally excludes chunk/evidence joins, retrieval candidate depth,
rankings, score normalization, query/gold eligibility, evaluator policy and search
configuration. Those require versioned extensions; they are not nullable columns or
undocumented tables in base-catalog-v1.

## Frozen machine resources

The checkout resources are:

- `catalog/base-catalog-v1.sql`: SQLite >= 3.37 STRICT DDL, SHA-256
  `3459beb249e348c869070220fda658cfd95c0f092fc12a18978baf19651a5c8c`;
- `catalog/base-catalog-v1.columns.json`: exact table/column/type/nullability,
  complete PK/UQ/FK/CHECK/presence/ordinal mapping and 25 required semantic checks;
- `catalog/base-catalog-v1.generation-profile.json`: closed implementation/resource/
  upstream names, validation dependency sets, constants, source mappings and runtime
  tuples, with names but no expected file hashes;
- schemas `video-paper-wiki.projection-input.v1`,
  `video-paper-wiki.projection-generation.v1` and
  `video-paper-wiki.catalog-rows.v1`.

DDL has no REAL, JSON, BLOB, custom SQL function, default, trigger or business payload.
All text uses BINARY collation. Source booleans are converted to INTEGER 0/1 only by a
later authenticated mapper after source validation; row callers cannot pass bool as an
integer cell. The canonical row APIs never open SQLite and never inherit its affinity,
version or diagnostic behavior. Deferred FKs and `PRAGMA foreign_keys=ON`, committed
constraints and `PRAGMA foreign_key_check` apply only to independent DDL acceptance
probes and the later SQLite writer. SQL remains an implementation defense rather than
the authority for application semantics.

The column manifest is authoritative for the 34 table names, exact column order,
SQLite types, nullability, complete keys, source mapping, presence pairs and ordinal
groups. A change to any of those or a semantic check requires a new reviewed catalog
profile/resource revision. The manifest contains the DDL hash but never its own hash.

## Relational coverage

The base represents all of these facts without a generic JSON column:

| Family | Required representation |
| --- | --- |
| canonical_inputs, artifacts | Every path/kind/raw-SHA/size; typed root or one of four opaque artifact rows |
| papers and ordered children | All paper metadata, authors/aliases/code URLs/source IDs/taxonomy, optional-array presence and active extraction |
| repos and repo_papers | Canonical/original repository, full commit, officiality/license/archive and ordered paper links |
| subjects, claim_refs, claims | Exactly one paper/repo owner per claim, section/core or capability shape, lifecycle and complete claim fields |
| sources, source_pages, source_artifacts | Closed ledger fields/presence, ordered page links, supersedes and exact file/captured iff binding |
| claim_evidence | Original order/duplicates, wire relation/source and complete canonical tagged locator |
| assessment_events, assessment_heads | Every immutable event and the unique derived head from frozen complete history |
| taxonomy tables | Root policy, exact axes/terms/labels/status and ordered duplicate-preserving aliases |
| run_manifests, run_artifact_bindings | Every run field/presence and exact source/config/model/document roles |
| code_origins, code_manifests | Every logical repo/commit/path/source origin and inspected capture/hash/line metadata |
| alignment tables | Every immutable version, officiality evidence, five capabilities, locators, absence scope/patterns and checkpoint kind |

Optional nullable values use explicit presence bits when omission differs from null.
Optional arrays use a parent presence bit where absence differs from present empty.
Ordered children retain zero-based ordinals and every duplicate admitted by the source
schema. SQL NULL never stands for false, zero, empty string and omission at once.

All 25 non-SQL semantic checks in the manifest are mandatory. They include exact
Python scalar types; inventory and typed-root coverage; artifact metadata equality;
closed reconstruction; roots/presence/ordinals; one-owner identity; supersedes graph;
file-source binding; managed page addresses; active extraction; complete assessment
history; taxonomy; canonical locator and owner membership; inspected code origins;
run roles/qualification; alignment coverage; row ordering; and generation binding.
They may call the accepted existing schema/identity/locator/history validators, but
must not weaken, normalize or replace their authority.

For `claim_evidence`, locator closure reconstructs the outer evidence wrapper, uses
`decode_ledger_evidence`, and requires outer source/relation equality with the decoded
locator. Alignment officiality/capability rows contain direct locators and have no
outer relation; they validate decoded source/kind and owner membership without
inventing a relation. Code-manifest rows prove reconstructed closed objects,
proposal/self identities and declared source/artifact path/hash associations. They do
not inspect captured payload bytes or prove newline, normalization, line or snippet
truth; those byte-to-row checks remain VPKB-001 mapper work.

## Public row APIs

Module `video_paper_wiki.projection_catalog` exports:

- `canonical_catalog_rows(*, generation_material: object, tables: object) -> bytes`
- `catalog_rows_sha256(*, generation_material: object, tables: object) -> str`

`tables` must be an exact built-in list. Every item is an exact dict with exactly
`name,columns,rows`; columns is the exact manifest-order list and rows is an exact list
of positional exact built-in scalar lists. Input table and row order may vary. No
mapping-shaped row, iterator, tuple, custom Mapping/Sequence or implicit missing cell
is accepted. Functions retain no caller objects and never mutate them.

The public validation order is exact:

1. Run frozen runtime preflight over one virtual root containing both arguments.
2. Load and hash-check the immutable DDL, column manifest and generation profile and
   require all embedded paths/hashes/counts to agree.
3. Validate generation material in its complete phase order below.
4. Validate the table collection, exact table/column set, cell types and row lengths.
5. In manifest table order, input row ordinal and manifest column order, validate
   nullability, integer range, enum/CHECK and presence constraints.
6. In that same stable traversal discipline, validate PK, UQ, FK and ordinal closure.
7. Execute the 25 manifest semantic checks in their listed order; each check uses
   manifest table order, input row ordinal and manifest field/key order internally.
8. Sort, construct and integer-only-JCS encode the canonical export.

An earlier phase wins when several phases fail. These traversal orders choose a stable
diagnostic inside a phase. The API does not execute SQLite. It accepts cells only as
exact built-in `str`, signed 64-bit `int` or `None` where the column permits; rejects
bool, float including 1.0, subclasses, coercible strings, surrogate text and unbounded
integers; and requires every table exactly once, including empty tables. A duplicate
is an error, never an upsert.

The generation inventory and canonical_inputs rows must be exactly equal as sets of
`path,kind,sha256,size_bytes`; input order remains the inventory contract's order.
This equality does not prove that other rows came from those bytes. The taxonomy input
SHA must equal the generation resource SHA for
`video_paper_wiki/taxonomy/v1.json`. The supplied DDL, column-manifest and generation-
profile resource hashes must equal the immutable packaged bytes used by this API, and
the manifest's embedded DDL hash must agree. Other supplied implementation/resource/
dependency/upstream hashes and versions remain declarations until the authenticated
collector.

Canonical output is an exact object with exactly:

```text
schema = video-paper-wiki.catalog-rows.v1
ddl_sha256
generation_sha256
tables
```

Each table has exactly `name,columns,rows`. Table order is ASCII name order from the
manifest. Rows sort by the complete declared PK in PK-column order: INTEGER compares
numerically; TEXT compares its exact UTF-8 bytes under BINARY semantics. PK components
are never mixed types or null. This differs from JCS object-key UTF-16 order. Columns
stay in exact manifest order and positional row arrays preserve that order.

Return existing integer-only JCS bytes for the complete output with no trailing LF.
`catalog_rows_sha256` is lowercase SHA-256 of exactly those bytes. No rowid,
sqlite_master value, insertion order, page/VACUUM/journal state, physical SQLite bytes,
build timestamp or output self-hash enters the export. This release adds no implicit
API for validating previously serialized row-export bytes.

Errors use `ContractError`, exit code 2. Runtime resource preflight preserves
`PROJECTION_LIMIT_EXCEEDED`; invalid generation uses
`PROJECTION_GENERATION_INVALID`; packaged DDL/manifest/profile disagreement uses
`CATALOG_RESOURCE_MISMATCH`; all table/cell/key/FK/semantic refusals use
`CATALOG_ROWS_INVALID`. Details contain safe fixed metadata/pointers and never echo
untrusted values. SQLite execution/writer failures are outside these public row APIs.

## Generation material

Module `video_paper_wiki.projection_generation` exports:

- `projection_generation_sha256(material: object) -> str`
- `projection_is_stale(*, current: object, stored: object) -> bool`

Material is an exact built-in dict with exactly these keys:

```text
schema, profile, inventory, implementation, resources, dependencies, upstream, runtime
```

`schema` is `video-paper-wiki.projection-generation.v1`; `profile` is
`base-catalog-v1`; inventory is a complete valid projection-input.v1 declaration.
`implementation` has exactly `package_version,files`; `resources` has exactly files;
`dependencies` has exactly `profile,distributions`; `upstream` has exactly
`commit,version,files`; runtime has exactly the six fields below. Every file item has
exactly `path,sha256`, with 64 lowercase hex. Every distribution item has exactly
`name,version`, both exact scalar strings. Arrays must equal the profile-owned exact
names, versions and strict ASCII order, with no missing/extra/reordered entry. A caller
cannot choose files, dependencies or supply a `valid` flag.

The machine profile fixes:

- 13 implementation files under logical installed paths `video_paper_wiki/...`,
  including the three projection modules; source checkout maps them under
  `src/video_paper_wiki/`. All must exist before a build qualifies; no placeholder or
  fabricated compiler digest is permitted.
- 25 package resources: all 21 registry schemas, taxonomy JSON, DDL, column manifest
  and the generation profile itself. Checkout mappings are exact `schemas/`,
  `taxonomy/` and `catalog/`; installed qualification has no CWD fallback.
- validation profile `vpwiki-jsonschema-date-utc-v1` and the exact runtime-selected
  distribution set below. The serialized schema closes the shape; application
  validation enforces the conditional exact set and order from the machine profile.
- 8 upstream files relative to the clean pinned submodule: six reviewed
  `claude_obsidian` modules and the public contextual-prefix/BM25 scripts.
- package version `0.1.0`; upstream commit
  `9f8c1199047eac2c3828496279fbb7ba9540b90b`, version `2.1.1`.

Runtime has exact `python_implementation,python_version,unicode_version,prefix_mode,
chunk_profile,bm25_profile`. Implementation is `CPython`; prefix is `synthetic`;
profiles are `claude-obsidian.chunk.v1` and `claude-obsidian.bm25.v2`. Only these
exact version pairs are admitted, never their cross-product:

| Python | Unicode data |
| --- | --- |
| 3.12.14 | 15.0.0 |
| 3.13.13 | 15.1.0 |
| 3.13.15 | 15.1.0 |

Use `platform.python_implementation()`, `platform.python_version()` and
`unicodedata.unidata_version`; do not use build-prose `sys.version`, major/minor ranges
or `>=3.12`. A patch or Unicode update requires reviewed profile expansion/revision.

The five distributions common to all admitted runtimes, in exact order, are
`attrs==26.1.0`, `jsonschema==4.26.0`,
`jsonschema-specifications==2025.9.1`, `referencing==0.37.0` and
`rpds-py==2026.6.3`. CPython 3.12.14 additionally requires
`typing-extensions==4.16.0` as the sixth item; both CPython 3.13 tuples require exactly
the five common items. These are behavior-relevant selected dependencies, not an
enumeration of every installed distribution.

The validation profile makes format behavior independent of optional package
discovery. JSON Schema `date` uses exact ASCII `YYYY-MM-DD` plus real Gregorian date
validation. Every project `date-time`/UTC field is checked by the explicit project
grammar and a real Gregorian clock check: year 0001–9999, hour 00–23, minute/second
00–59, optional one-to-nine decimal fractional digits where the source schema admits
them, literal `Z`, and no leap second. Canonical projection code must not construct an
unrestricted auto-discovered `FormatChecker`; an incidentally installed
`rfc3339-validator` cannot change success. Changing this profile or a relevant exact
distribution version requires review and changes generation.

`projection_generation_sha256` uses this exact phase order:

1. Run frozen runtime tree/resource preflight over the caller value.
2. Load and integrity-check the immutable packaged generation profile and schema
   resources; a resource failure is `CATALOG_RESOURCE_MISMATCH`.
3. Validate exact root/nested shape and exact built-in scalar types.
4. Validate schema/profile constants, runtime tuple, format profile, conditional exact
   dependency set, and implementation/resource/upstream names/order/counts.
5. Validate the embedded inventory, remapping its ordinary contract refusals to
   `PROJECTION_GENERATION_INVALID` under `/inventory` while preserving
   `PROJECTION_LIMIT_EXCEEDED`.
6. Validate cross-material relations, including taxonomy input/resource SHA equality.
7. Integer-only-JCS encode the entire material and return lowercase SHA-256, with no LF.

An earlier phase wins; within a phase, object fields follow the profile-declared order
and arrays follow their input order. A post-preflight canonicalization failure is an
internal invariant failure, never a stale/fresh fallback. The function does not read
the declared source files or attest their hashes. Raw formatting changes remain
conservatively material. The profile resource lists its own name but no expected hash,
so neither it nor the material contains a self-hash equation.

`projection_is_stale` validates `current` first. Exact `stored is None` then returns
true. Otherwise it validates stored and compares complete generation fingerprints.
Malformed current or stored material is a typed refusal, never silently stale/fresh.
No filesystem state is read behind the caller and no mutable object is retained.

Generation excludes expected output hashes, Markdown/chunk/BM25/SQLite bytes and
SQLite library versions, the whole `uv.lock`, unrelated installed distributions,
tests, fixtures, seed catalog, taxonomy YAML, contract/status/packet/team/CI Markdown,
receipts/staging, absolute paths, CWD, hostname, mtime and build clock. The whole lock
contains development, optional Docling and platform state that cannot make this pure
base result stale. Canonical ledger/run timestamps remain material through raw
inventory hashes. The column manifest and generation profile contain
names/relationships but never their own expected digests. Future mapper/compiler
modules or file-set changes require a new profile revision, not a wildcard.

## Collection, packaging and later authority

Wheel packaging must include all 21 schemas plus exact taxonomy and catalog resources.
Production resource loading is installed-package relative and rejects missing files;
source-checkout fallback is for deterministic development only and never qualifies an
installed build through CWD discovery.

A later authenticated collector must enumerate exactly the profile names, raw-hash
complete installed implementation/resources and the clean pinned upstream files,
verify the runtime-selected required distributions with `importlib.metadata`, and
verify package/upstream/runtime identities. It rejects aliases and missing, extra or
misordered profile file names. An unrelated installed distribution is ignored because
the explicit format profile prevents optional-provider discovery from altering
behavior. Caller-declared dependency values alone are not attestation. The collector
does not prove canonical input completeness or byte-to-row mapping.
`validate_projection_bytes` proves supplied input-byte equality. The VPKB-001 mapper
and receipt audit separately prove authoritative membership and derivation. A future
build-result record may bind generation to output hashes without adding an output hash
to generation itself.

The accepted DDL probe evidence covers exact tables/columns/keys/FKs, all event
transition combinations, subject XOR, alignment combinations and source presence
pairs. Final implementation acceptance must add adversarial pure API fixtures,
including a deliberately honest inventory paired with forged but internally consistent
rows to demonstrate the guarantee limit; exact Python coercion cases; packaged wheel
resource enumeration; both supported local Python lines; and fresh PR merge-ref CI.
Independent DDL/writer probes cover SQLite STRICT coercion, foreign-key enable/commit/
check behavior and the minimum 3.37 feature level, but those results never enter the
canonical row API or generation fingerprint. No green result closes VPKB-001/002 or a
user gate.
