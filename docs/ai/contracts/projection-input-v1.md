# Canonical projection inventory and application profile — revision 1

Status: FROZEN by Architect, 2026-09-01. The 34-table DDL and
generation contract are reviewed with this document. Runtime, locator and complete
assessment-history revision 1 remain unchanged. This revision authorizes only pure
foundation implementation and tests; it does not authorize Vault enumeration,
publication, a production compiler/index build, a real Docling/model run or any
human-gate transition.

## Authority and guarantee boundary

VPKB-000 freezes a complete declared file inventory, the application profile needed
to represent its facts, and the relations required of supplied catalog rows.
`validate_projection_inventory` proves only that a declaration has the closed shape
below. `validate_projection_bytes` additionally proves that one supplied in-memory
byte map exactly matches every declared size and raw SHA-256. Neither function proves
that the declaration enumerates an authoritative Vault, that typed rows were derived
from those bytes, that a receipt published them, or that a PDF/code locator is true.

VPKB-001 must authenticate corpus membership and map the same verified bytes to rows.
VPKB-001/002 must also validate public upstream ledgers at an explicit audit date,
recompute authentic source IDs, verify producer/config/model identities, and prove
Docling text/page/ref/span/bbox or inspected code evidence. No caller boolean, parsed
object map, detached hash or internally consistent row set may replace those steps.

Canonical business fields come only from source/claim ledgers, paper/repo records,
complete assessment events, taxonomy and immutable run/code/alignment manifests.
Markdown, frontmatter, chunks, BM25, old SQLite rows, staging, receipts and model
responses are not alternate field sources. Opaque captured/document/config/model
bytes receive only path/kind/raw-SHA/size rows in the base catalog; their internal
parser-specific values do not become a generic JSON store.

## Public pure APIs and errors

Module `video_paper_wiki.projection_input` exports:

- `validate_projection_inventory(value: object) -> None`
- `validate_projection_bytes(value: object, *, bytes_map: object) -> None`

Both retain no reference to caller data, perform no filesystem/package/network I/O,
and return `None` on success. They use `ContractError`, exit code 2. Validation runs
the frozen runtime tree preflight first. Resource failures preserve
`PROJECTION_LIMIT_EXCEEDED`; unsupported Python values, cycles or surrogate text at
preflight use `SCHEMA_INVALID`. Closed shape, path/kind/cardinality/order/collision or
hash spelling failures use `PROJECTION_INPUT_INVALID`. A byte-map type/key-set/value,
declared-size/actual-size or raw-hash mismatch uses `PROJECTION_INPUT_MISMATCH`.

Diagnostics contain safe fixed fields and JSON pointers only. They never echo an
untrusted path/key/value, call its `repr`/`str`, or identify a later item as verified.
Preflight and a complete byte-map type/key/length/aggregate scan precede all payload
hashing. Apart from those phases, simultaneous failures have no cross-rule priority.

## Closed inventory

The root is an exact built-in dict with exactly `schema,entries`; `schema` is
`video-paper-wiki.projection-input.v1`. `entries` is an exact built-in list. Every
entry is an exact built-in dict with exactly `path,kind,sha256,size_bytes`:

- `path` is a Unicode-scalar string and entries are strictly increasing by its UTF-8
  bytes. Paths are unique and obey frozen transaction lexical/NFC/portable component
  and casefold-collision rules. No normalization or order repair occurs.
- `kind` is one of the exact 13 strings below and must match the path branch.
- `sha256` is exactly 64 lowercase hexadecimal characters.
- `size_bytes` is exact built-in `int`, never bool, in `0..67,108,864`.

Declared aggregate size is at most 8,589,934,592 bytes. The full byte API requires an
exact built-in dict whose keys equal the complete declared path set and whose values
are exact built-in bytes. The same per-file and aggregate bounds apply to actual
bytes, counting every declared path even when two values reference one bytes object.
No partial byte map, lazy resolver, filesystem path, memoryview or parsed-document map
is accepted. Raw SHA is over the complete byte sequence.

The companion JSON Schema closes serialized shape and path branches. Exact Python
types, ordering, portable aliases, aggregate budgets and cross-file rules remain
mandatory application checks because JSON Schema alone cannot express them.

| Kind | Exact logical path | Cardinality and local binding |
| --- | --- | --- |
| source-ledger | `wiki/meta/ledgers/source-ledger.json` | Exactly one |
| claim-ledger | `wiki/meta/ledgers/claim-ledger.json` | Exactly one |
| taxonomy | `taxonomy/v1.json` | Exactly one project provider |
| paper-record | `wiki/meta/records/papers/<name>.json` | Zero or more; unique embedded canonical paper ID |
| repo-record | `wiki/meta/records/repos/<name>.json` | Zero or more; unique embedded canonical repo ID |
| assessment-event | `wiki/meta/reviews/<clm-20hex>/<ase-20hex>.json` | Path IDs equal validated embedded IDs; complete history for every claim |
| captured-artifact | `.raw/captured/<64hex>.<extension>` | Filename digest equals entry SHA; digest unique within this kind |
| docling-document | `.raw/derived/<S>/docling/<P>/document.json` | `S` is source raw SHA and `P` is the unchanged pipeline fingerprint |
| parser-config | `.raw/derived/<S>/docling/<P>/parser-config.json` | Exact sibling role |
| model-manifest | `.raw/derived/<S>/docling/<P>/model-manifest.json` | Exact sibling role |
| run-manifest | `.raw/derived/<S>/runs/<run-id>.json` | Embedded run ID equals filename; key is source-qualified path |
| code-evidence-manifest | `.raw/derived/code-manifests/<64hex>.json` | Filename digest equals complete file SHA; inspected state only |
| alignment-manifest | `.raw/derived/alignment-manifests/<64hex>.json` | Filename digest equals complete file SHA; retain every version |

`name`, `extension` and `run-id` are complete portable destination components with the
shown suffix handled outside the variable. No aliases, alternate casing or extra
subdirectories are admitted. Full-file hashes in filenames are not self-excluding
manifest fields. This is an explicit new closed profile: legacy locations, partial
run bindings, null-hash file sources and unknown extensions cause whole-input refusal
and are never moved, repaired, enriched or silently omitted.

No Markdown, `.vault-meta`, notes, staging, gate/operation registry, receipt, mutable
assessment-head registry, generated chunk/BM25 output or SQLite file is an input.
Every retained canonical historical version/event admitted by this profile is listed;
the later managed-prefix receipt audit must detect hidden omissions or rollback.

## Exact ledger profile

Fixed objects reject unknown fields. Dynamic source/claim map keys are IDs, not
extensions. `DATE` is a real Gregorian `YYYY-MM-DD`, years 0001–9999. `LEDGER_UTC` is
a real whole-second `YYYY-MM-DDTHH:MM:SSZ`, with no fraction, offset or leap second.
`SRC` is local fullmatch `src-[0-9a-f]{20}` and `CLM` is
`clm-[0-9a-f]{20}`. This narrower SRC grammar applies only to complete ledgers; it
does not change the broader common, locator or history APIs. Authentic source-ID
recomputation remains the isolated pinned public adapter.

The source-ledger root has exactly `schema,generated_at,sources`, with schema
`claude-obsidian.source-ledger.v1`, LEDGER_UTC retained verbatim and an exact built-in
source map that may be empty. Each source has required `origin,content_kind,title,
authority,review_status,pages` and exactly six optional-nullable fields:
`content_sha256,ingested_at,retrieved_at,refresh_due,independence_key,supersedes`.
Presence is material: omitted, explicit null and a value remain distinct in rows.

`origin` has exactly `kind,locator`; kind is `file|url|manual`. `content_kind` is one
of `document|webpage|dataset|image|audio|video|code|conversation|synthetic|other`;
authority is `official|primary|secondary|community|synthetic|unknown`; review status
is `unreviewed|active|superseded|rejected`. Title and a nonnull independence key must
be nonblank under Python `strip()` while their exact original spelling is retained.
Pages are scalar strings with order and duplicates preserved; empty is valid.

Every file source in every review state must have the `content_sha256` key present and
nonnull. Its locator is the exact supplied captured-artifact path, its digest equals
that artifact's entry SHA, and it has exactly one `source_artifacts` row. URL/manual
sources have zero such rows; their content hash remains optional-nullable. Several
logical source IDs may bind the one captured artifact. A file source accepted by the
broad pinned validator with an absent/null hash is deliberately rejected because
adding a hash would change stable source identity and all references.

At this pure layer a URL/manual locator promise is only exact built-in nonempty
Unicode-scalar text with original spelling and common budgets. It is not described as
a valid or safe URL. Absolute HTTPS/host/port, fragment, credential/sensitive-query,
canonical URL and authentic source identity remain the pinned public adapter. File
paths additionally obey the captured-path branch. No private URL canonicalizer is
copied into this foundation API.

Static source checks include `(content_kind == synthetic) == (authority ==
synthetic)`; nonnull `ingested_at` requires nonnull content hash; `observed` is
nonnull `retrieved_at` else `ingested_at`; active requires observed and refresh_due;
and when both exist `refresh_due >= observed`. Supersedes resolves inside the complete
source map and the full graph is acyclic. Future-date, freshness, high-risk support
and independence-group checks require the later pinned adapter with explicit audit
date and are not approximated here.

The claim-ledger root has exactly `schema,generated_at,claims`, schema
`claude-obsidian.claim-ledger.v1`, retained LEDGER_UTC and a map that may be empty.
Each claim has required `text,risk,assessment,confidence,location,reviewed_at,evidence`
and optional-nullable `notes,supersedes`. `reviewed_at` is required but may be null;
missing never becomes null. `location` has required path and optional-nullable anchor.
Text is nonblank under `strip()`, preserved raw, and at most 65,536 UTF-8 bytes.

Risk is `normal|high`, assessment is
`accepted|provisional|contested|unsupported|deprecated`, and confidence is
`high|medium|low|unknown`. Evidence is an ordered exact list, duplicates retained;
every closed item has `source_id,relation,locator`, with source FK, wire relation
`supports|contradicts|context`, and a required canonical tagged locator no longer than
65,536 UTF-8 bytes. Reconstruct the exact outer evidence object and use frozen
`decode_ledger_evidence`; decoding maps wire `context` to domain `uncertain`, verifies
outer source/relation against the decoded locator source/domain relation, and rejects
noncanonical wire rather than repairing it. An accepted claim has a nonnull review
date; a contested claim has at least one
contradicting evidence occurrence or nonblank notes. Claim supersedes resolves in the
complete map and is acyclic.

Every claim, including retired claims, is referenced exactly once by one paper or repo
record. Recompute its stable subject and unchanged claim ID from that actual owner and
raw text. Complete assessment events and frozen history revision 1 derive the unique
head and require the ledger assessment/reviewed_at projection; no mutable head input,
timestamp maximum, event-order guess or second evidence list is allowed.

## Managed page addresses and owner binding

The complete generated page-address set is derived without reading Markdown:

- paper: `wiki/papers/{paper_page_slug(paper_id)}.md`, using existing identity code;
- repo: `wiki/code/{repo_page_slug(repo_id)}.md`;
- concept: `wiki/concepts/{axis}/{term_slug}.md`, retaining slash-separated axis
  components from the exact taxonomy axis.

The new pure `identity.repo_page_slug(repo_id)` first requires an exact canonical repo
ID and returns `github-` plus lowercase SHA-256 of the exact repo-ID UTF-8 bytes. It
does not trim/casefold an invalid input or accept original `owner/repo` spelling.

Every `source.pages` occurrence must be an exact member of this derived set. Order,
duplicates and empty arrays remain valid. A claim location is exactly its one primary
owner page: the paper address for a paper claim or repo address for a repo claim.
Concept pages are not claim owners. Actual rendered-page existence, content equality
and anchor resolution remain later compiler/audit duties.

## Taxonomy v1 profile

`taxonomy/v1.json` is the sole machine provider; YAML is a human copy. Root, policy,
axis and term objects are closed. Version is exact `v1`. Policy is exactly:

- `unknown_terms = "review_queue"`
- `silent_create = false` as exact bool
- `statement_en = "Unknown terms MUST enter a review queue and MUST NOT be silently created as canonical terms."`
- `statement_zh = "未知术语必须进入 review queue，不得静默创建新的 canonical term。"`

Axes occur exactly once in this exact order:

1. `task/conditioning`
2. `formulation/objective`
3. `representation/tokenizer`
4. `backbone`
5. `spatial-temporal-modeling`
6. `data/captioning/filtering`
7. `training/parallelism/optimization`
8. `inference/distillation/acceleration`
9. `control`
10. `evaluation/dataset/benchmark`

Each axis has exactly `slug,label_zh,label_en,aliases,terms`; each term has exactly
`slug,label_zh,aliases,status`. Every axis has at least one term. Term slug fullmatches
`[a-z0-9]+(?:[-_][a-z0-9]+)*`, is unique within its axis and may repeat across axes;
status is exact `canonical`. Labels and alias items are Unicode-scalar strings whose
UTF-8 byte length is greater than zero; they are not trimmed or normalized. Alias
arrays may be empty and may contain duplicates, shared values or a slug/label value;
all ordinals remain material. Labels may repeat. No parent, term English label,
redirect or alias resolver is inferred. Term count is not fixed at two. Paper taxonomy
references resolve exact `(axis,slug)`; unknown terms are refused without creating a
queue artifact as a side effect.

## Run and artifact closure

Every run path supplies source context `S` and has exactly one source artifact binding
to the unique captured artifact with raw SHA `S`; at least one file source binds that
captured path. A present `input_hashes.source_sha256` equals `S`. The source role exists
even when that optional field is absent and means context association, not producer
authentication. Pre-capture diagnostics remain staging and cannot become canonical
runs under this profile.

Pipeline fingerprint `P` absent permits no parser-config, model-manifest or document
hash and no corresponding role. Other original provenance/version fields remain.
`P` present requires the unchanged complete five-field bound Docling identity with
pinned Docling/core versions, parser-config/model hashes and recomputed P. Each present
named parser/model/document hash has exactly its prescribed `.raw/derived/S/docling/P/`
sibling artifact and role; each declared parser/model artifact is referenced by at
least one matching role. Partial config/model/document hashes without P are rejected
even when the older run API accepted them. No existing run schema/API is changed.

Every docling document has both sibling config/model artifacts and at least one matching
run whose error_code is null, pinned versions and source/config/model/document hashes
are all present and equal. Multiple qualifying runs stay distinct; choose no first,
latest or lexicographically smallest row. Failed/unbound admitted runs retain every
original field. ingest-plan/prepared/draft/receipt hashes remain raw provenance inside
the run-manifest input hash; they are neither dereferenced inputs nor artifact roles.

A paper active extraction names an admitted qualifying document. At least one source
role for that document's S context resolves to a file source with content_kind document,
exact captured-S binding and exact membership in that paper's source_ids. Matching by
SHA alone is forbidden; other logical sources sharing S need not belong to the paper.

## Locator and manifest membership

Claim evidence uses the outer ledger evidence wrapper described above. Alignment
officiality and capability arrays instead contain direct PDF/code locator objects;
they have no outer relation wrapper. Direct alignment rows canonically decode and
re-encode the locator, require the row source and kind to equal the decoded locator,
and apply owner membership without inventing `supports`, `context` or `uncertain`.

Every PDF locator names an admitted qualifying docling document and its source binds
the document's S captured context. For a paper-owned claim the source is in that paper's
source_ids; for a repo-owned claim it is in at least one paper linked by the repo record;
alignment officiality PDF evidence belongs to the alignment's paper. Actual PDF node,
selected text, page/ref, ratios, charspan and bbox truth remains mandatory later.

Every code locator resolves one inspected code-evidence manifest with exact source,
original repository identity, full commit and origin path. For a repo-owned claim it
matches that repo; for a paper-owned claim the resolved repo links that paper; alignment
capability locators match the alignment repo and commit. Base row validation
reconstructs the closed code manifest; validates its proposal/self hashes, declared
source identity, payload SHA/size/newline/line metadata and stored capture association;
and requires `capture.source_id` to resolve a file source with `content_kind=code`
whose `source_artifact` path/hash exactly equal `stored_path`/payload SHA. These are
declared row relationships. Row validation does not inspect the captured payload, and
`validate_projection_bytes` proves only that each supplied inventory byte value matches
its own declaration. Actual payload SHA/size/newline/normalization/line/snippet truth
and proof that manifest rows came from those bytes remain VPKB-001 mapper duties.
Proposal-only manifests stay staging.

Repo records retain every historical paper link and claim ref; alignment manifests
retain every immutable version. Missing alignment remains missing and never creates
five inferred unverified capabilities. Each supplied alignment has all five unique
capability names in original ordinals 0..4; official requires PDF evidence;
present/partial requires code locators; absence scope/pattern/checkpoint presence is
preserved exactly wherever the existing schema admits it.

The column manifest enumerates the remaining one-to-one typed roots, ordered children,
FKs, presence pairs, acyclicity, full history and cross-row reconstruction rules. Base
row validity never certifies genuine Docling formula/soft-hyphen/enrichment/
multi-provenance behavior. VPKB-001/002 must freeze and test selected-text,
normalization, span, provenance and bbox semantics; no clamping, orig fallback or
first-provenance guess is authorized.
