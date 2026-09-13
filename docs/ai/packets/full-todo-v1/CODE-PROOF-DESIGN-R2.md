# Code source proof and configuration evidence — R2

Architect design for the first bounded CODE implementation, pending independent
review and an exact path/resource freeze. This is not a completion claim for CODE.
Root implements locally under LOCAL-CODEX-OWNERSHIP-R2; the existing assistants
review and serialize Git. No external Builder launches are requested.

The baseline will be the locally delivered Discovery successor of ef2ff13. The
old advisory reference to rebasing on fb2cbcb is rejected: it would discard later
accepted source work. Pending public push/CI does not prevent independent local
development. Source writes begin only in the new, inspected CODE workspace.

## Delivery sequence and compatibility

1. CODE-PROOF: bounded request, supplied Git objects or normalized observations,
   retained source proof, exact data-only configuration spans and source handoff.
2. CODE-RELATION: caller/model capability and two-sided mismatch proposals,
   evidence-bearing A/B/C/D relation review, checkpoint/license observations.
3. CODE-CANONICAL: inspected SHA-1/SHA-256 manifest successor, one receipt-backed
   source publication, immutable source association/relation pages, catalog/query
   and backup/restore closure. These remain required authorized engineering work.

Do not change the legacy code manifest, locator, alignment, compiler input,
source-publication or catalog schemas in place. Phase 1 emits no inspected capture,
source registration, officiality, canonical relation or publication authority.
Its handoff binds actual source bytes for the later adapter, including 64-hex Git
objects; no legacy 40-hex substitution is permitted.

## Public workflow

The new core `vpwiki code-evidence` group has five leaves:

- `request --input FILE --batch-id NAME`: validate/normalize one request and
  install its immutable `request.json`; return exact host acquisition targets.
- `observe --input FILE [--bundle-dir DIR] --batch-id NAME`: retain the request,
  supplied observation metadata and optional raw proof bundle together; validate
  everything; stage input intent and required bodies; install observation last.
- `status --batch-id NAME`: read-only complete/incomplete state, every requested
  path and outcome, Git/hosting/text capabilities, saved refs and next action.
- `config --path PATH --format json|toml|source-only --batch-id NAME`: derive one
  content-addressed config record from a complete stored raw observation. Explicit
  unsupported source-only input retains bytes/ref/reason and no interpreted nodes.
- `handoff --batch-id NAME`: produce deterministic per-target source-file
  handoffs after the complete raw observation has been replayed; store generated
  proposal records and return their exact local source body paths. It does not
  invoke legacy capture/prepare/inspect, a connector, Git or an operator.

One batch contains one request, one acquisition intent and at most one completed
observation. Repeating identical input is idempotent. A different request or
acquisition requires a new batch. A normalized-only observation is useful evidence
but cannot become raw proof by adding a field or supplying a later bundle to the
same immutable observation. A fresh batch is required.

No command makes network calls, starts subprocesses, reads Git configuration,
imports supplied code, opens checkpoint URLs, downloads weights or writes a Vault.
Host acquisition is separate from the public Python boundary and records its
actual available capabilities. Requests are data, not shell commands.

## Document and resource identity

New documents use a closed envelope `{schema, kind, id, data}`. The schema is
`video-paper-wiki.<kind>.v1`; the ID is `ce1:<kind>:<sha256>`, where the hash is
SHA-256 of integer-only JCS `{schema, kind, data}`. Saved bytes are exactly JCS of
the full envelope followed by one LF. A reference is `{id, sha256}` and its hash
covers those complete saved bytes. No timestamp or runtime field is excluded
from document identity. Lists have the explicit ordering below.

Kinds are `code-proof-request`, `code-git-bundle`, `code-acquisition-intent`,
`code-proof-observation`, `code-config-evidence`, and `code-source-handoff`.
They share a new closed common schema and a versioned parser/provider profile.
Public commands retain the actual installed schema/profile bytes in their one
input session and use a fresh bound registry; no stale default registry can
substitute another resource generation. Pure validators may load that same
resource set without filesystem authority.

All metadata JSON is strict UTF-8, BOM-free, duplicate-key-free, closed and
integer-only. Reject nonfinite/binary floats, surrogates, unknown fields and
trailing material before staging. Metadata identity strings are NFC. Raw source
and decoded configuration string values keep their original Unicode spelling;
no Unicode normalization or number rounding may alter evidence bytes.

## Request

Request data has exactly:

`paper_id, source_association, repository, object_format, commit_oid, targets,
require_repository_assertion, limits, profile_sha256`.

`paper_id` is an existing canonical paper identity. `source_association` is null
or an exact `{association_id, sha256}` reference. Phase 1 preserves it but cannot
verify association ownership without the canonical state; status explicitly says
`source_association_verified: false`. Later canonical validation must prove it.

`repository` is lowercased `owner/name`, with two nonempty bounded ASCII
alphanumeric/dot/underscore/hyphen components and no `.git` suffix. Normalize an
input owner/name by case only; do not accept arbitrary URLs, credentials or refs.
`object_format` is exactly `sha1` or `sha256`. Commit, tree and blob OIDs use the
chosen width (40 or 64 lowercase hex); no mixed format, abbreviation or implicit
compatibility mapping. `require_repository_assertion` is an explicit boolean.

Each target is `{path, roles, allow_executable_source}`. Roles are a nonempty
sorted unique subset of `readme,citation,license,implementation,configuration,
entrypoint`. Paths are unique, sorted by UTF-8 bytes and collision-free under
casefold and parent/file collision checks. They use 1–32 portable ASCII components
from letters, digits, dot, underscore and hyphen; no empty/dot/dot-dot component,
`.git` component, leading slash, backslash, wildcard, percent escape or URI syntax.
The complete path is at most 512 bytes. Leading dot components such as `.github`
are allowed. Executable permission may be true only when every role is
implementation or entrypoint. The request does not assert that a path exists.

The fixed profile caps 32 targets, 2048 objects, 32768 parsed tree entries,
8 MiB per object, 32 MiB total object bodies, 1 MiB bundle metadata, and 16 KiB
normalized text per target. Request limits may lower these positive caps and
must be materialized completely. The request/profile and actual budget charges
are retained in observation results. Counts and declared sizes are checked before
reading object bodies; actual bytes are checked while reading. No truncation.

Acquisition targets expose exact `https://github.com/<repo>/blob/<commit>/<path>`
and `https://raw.githubusercontent.com/<repo>/<commit>/<path>` locators plus the
logical Git commit/target-set proof requirement. They do not assert that a Web
tool can return exact raw bytes or that a GitHub API JSON response is a raw commit
object. Any practical host mapping refinement requires its own explicit profile.

## Raw bundle and object proof

A supplied bundle is a local uncompressed directory with exactly
`manifest.json` and `objects/`. The latter contains exactly the declared
`<oid>.body` single-link regular files. There are no archives, zlib streams,
packfiles, nested paths, links or undeclared siblings. The bundle must be below
the current checkout's `.work/` tree, outside the output code-evidence directory.

The manifest is a saved `code-git-bundle` envelope. Its data is exactly
`request, object_format, repository, commit_oid, root_tree_oid, objects`.
The request reference and all repeated identity fields must equal the request.
Object records are sorted by OID and contain exactly
`oid, object_type, body_size_bytes, body_sha256, framed_sha256`.
Object types are `commit,tree,blob`. The manifest ID is its complete manifest
identity; every object body is bound by its record and independently verified.
There is no circular whole-directory hash or unaudited archive digest.

For body bytes `B`, form `type + SP + decimal(len(B)) + NUL + B` exactly. The Git
OID is SHA-1 or SHA-256 of that framing. `body_sha256` hashes only B;
`framed_sha256` always hashes the full framing. All three identities and the
declared size must match before object parsing. A SHA-256 Git OID is consequently
equal to framed_sha256, never ordinarily equal to body_sha256.

The commit object must be present with type commit. Its first header is exactly
`tree <root_tree_oid> LF`; the bounded header section ends in LF LF. No second
top-level tree header or malformed same-format parent OID is accepted. Other
headers/continuations and the message are retained as opaque data; signatures,
author identity, dates and remote ref ownership are not verified.

Every supplied tree body is parsed as Git's binary sequence of ASCII mode, SP,
raw name, NUL and fixed-width binary OID. Require complete framing, nonempty names,
no slash/NUL/dot/dot-dot names, unique raw names and Git byte ordering (directory
names compare with an appended slash, ordinary entries with an appended NUL).
Accepted canonical entry modes are `40000,100644,100755,120000,160000`.
Unrelated names may be non-UTF-8 and remain opaque bytes; only requested portable
path bytes are compared. They must not be decoded into invented path strings.

Walk each requested path from the exact root tree. Intermediate trees must be
present and hash-verified. A missing edge in a proven tree is `missing`; a
declared required tree/body that is unavailable is an invalid bundle, not proof
that a file is missing. Mode 100644 is a regular source candidate. Mode 100755
requires the target's explicit executable permission. Symlinks, gitlinks,
requested directories and a non-directory intermediate component are `unsafe`
with the exact blocking edge retained; do not dereference or execute anything.

The consumed object set must equal the declared set: one root commit, all visited
trees, and bodies of requested permitted regular blobs. Bodies for unrelated,
unsafe or missing targets are not needed and are rejected as extras. A shared
blob body can satisfy multiple paths, but the separate requested paths and tree
walks remain separate target records. Cycles/repeated tree OIDs do not recurse
indefinitely: only bounded explicit path components are walked.

Regular source blobs must satisfy the existing strict UTF-8 code text rules.
Preserve raw SHA-256 and Git OID; compute CRLF-to-LF normalized SHA-256, newline
style, terminal newline and line count separately. Unsupported text stays an
explicit target outcome and never yields a source handoff.

## Observation metadata and normalized capability

The caller supplies actual acquisition metadata with `mode` equal to
`git_objects` or `normalized_text`, an actual observation timestamp, executor
identity/source, optional hosting assertion, and mode-specific target results.
The exact closed fields and executor unknown grammar are frozen with schemas.

A hosting assertion records provider/actor, repository, commit, locator and a
bounded statement. Its repository and commit must match the request. It is
retained as `host_asserted`, never cryptographic remote ownership or officiality.
Null means `unverified`; if the request requires an assertion, null prevents
complete handoff eligibility while preserving the object evidence.

Normalized results must include every requested target exactly once. Present
results contain actual bounded text and locator; missing/inaccessible/unavailable
results contain a reason and no manufactured text. This branch stores no object
bundle and has no Git/raw-byte/config-span authority. Host-reported missing is
distinguished from a missing edge proved by a Git tree.

The deterministic final observation binds the request, complete acquisition
intent, bundle reference if present, exact ordered target set, budgets and every
target outcome. Raw proof retains each path's visited edges and terminal entry.
It reports object verification, raw/text capability, repository assertion and
source-association verification separately. `complete` requires every requested
target to be a permitted strict source blob and any requested host assertion.
Partial evidence remains useful status output but cannot create a complete-set
handoff. A new narrower request can intentionally re-scope a subsequent batch.

## Retained I/O and interruption behavior

All command inputs, installed resources, checkout validation and work/output
paths share one retained descriptor tree. Capture the first named edge (including
absence) before use, remember complete scoped directory sets before classification,
retain opened single-link files and compare bytes, mode, identity and named edges
on all exits, including parse errors, limit refusal, install conflict and cleanup.
An unsafe final lineage result takes precedence over an earlier semantic error.

Use a nonblocking exclusive lock on the checkout directory before scanning the
work tree. Hold a duplicate of that descriptor through all checks and close
cleanup so another command cannot enter early. Read-only status creates no paths.
Never follow a replaced checkout marker or pyproject path to validate authority.

The fixed output layout is `.work/<batch>/code-evidence-v1/` containing optional
`request.json`, `intent.json`, `observation.json`, and the exact families
`objects/`, `configs/`, `handoffs/`. No unknown siblings or unsafe file types are
accepted. Generated files are private 0600 and directories 0700. Total retained
output bytes are bounded at 128 MiB, including pending files; each bound is
charged before installing a whole document/body.

Request installs first. Observe validates the full external input before writes,
then installs deterministic intent, sorted body files and final observation in
that order. Every install validates first-absence, uses the existing atomic
installer's returned inode identity, and revalidates the exact expected set/bytes.
Existing identical files are reusable only when observed at initial open, not
when inserted by another writer after absence. Different fixed input conflicts.

Status replays all available data and classifies an interrupted intent without
inventing missing bodies or a terminal result. Repeating observe with the same
retained input repairs the deterministic missing suffix. Complete observation
commands re-run the proof from stored intent/body bytes. Config and handoff
artifacts must exactly equal pure derivation from this replay; resealed forged
results and orphan derived artifacts are rejected.

## JSON/TOML configuration spans

Configuration requires a complete raw observation, the exact requested path,
and a configuration role. The pure parser receives retained blob bytes only.
It neither opens another path nor evaluates imports/includes/interpolation.

The bounded profile admits RFC 8259 JSON and a documented TOML 1.0 subset:
single-line basic/literal strings, decimal integers and finite decimal floats,
booleans, arrays, inline tables, ordinary tables and dotted keys. Multiline
strings, arrays of tables, timestamps and base-prefixed integers remain outside
this initial subset. YAML, Python, Hydra/OmegaConf, JSON5 and other formats remain
source-only; their raw bytes still support literal code citations.

Keep existing integer-only artifact JSON unchanged. Represent integer/decimal
config magnitudes as typed canonical decimal strings with original source lexeme.
Validate lexical grammar, use Decimal directly without float conversion, remove
TOML underscores only for conversion, emit exact fixed notation with redundant
fractional zeros removed. Bound lexeme length 128 bytes, significant digits 64,
absolute exponent 128 and expanded value length 256; reject nonfinite values and
negative-zero spelling. An input `1e-4` yields decimal value `0.0001` and lexeme
`1e-4`, both strings.

Source caps: 256 KiB, depth 32, 1024 total nodes, 256 array items, 1024 object keys,
256 bytes per key, 16384 codepoints per string, 512 scalar nodes. Each complete
config document is at most 2 MiB; at most one configuration result per requested
path is installed (32 total). Exceeding a limit refuses the complete typed result,
never truncates nodes or turns an unexamined key into absence.

Use a span-producing JSON/TOML scanner and independently cross-check its complete
typed path map against stdlib json/tomllib with Decimal parsing. Reject duplicate
decoded keys/path redefinitions, malformed/trailing syntax, unsupported constructs,
unknown scanner/parser values or any coordinate/hash mismatch. No partial verified
node list survives a failure. Explicit dynamic interpolation/include/callable
markers are refused by a frozen literal grammar; ordinary strings are never run.

Paths use decoded JSON Pointer escaping for both formats, with exact original
Unicode spelling. Each node has a typed value/container kind and an exact value
span when one exists; TOML implicit tables have no synthetic value range. Table
headers/key tokens may have separate spans. Scalar spans are mandatory.
Spans include zero-based half-open raw byte offsets and original Unicode codepoint
offsets, one-based line/column positions (exclusive end), raw span SHA-256 and
the existing normalized line-snippet hash. CRLF remains two original codepoints
and bytes but advances one physical line. Recompute every slice and hash.

Verified config parsing describes data in that exact file. It cannot establish
that the program uses the value, that training exists, that weights were tested,
or that a paper/repository relation is official. Those are separate proposals and
reviewed evidence in the required CODE successor phases.

## Acceptance required for CODE-PROOF

Freeze schemas/profile/allowed files and obtain independent semantic and I/O
reviews before implementation. Validate SHA-1 and SHA-256 object graphs, missing
and unsafe targets, extras/omissions, exact path/mode/raw/normalized distinctions,
duplicate-content separate paths, wrong-host assertions, normalized-only refusal,
every interrupted install boundary, forged saved derivations, descriptor races
on success and errors, FIFO/symlink/hardlink refusal and no-egress/no-Vault checks.

JSON/TOML tests cover exact decimal learning rate and beta values, Unicode/CRLF
coordinates, escaped duplicate keys, dotted tables/arrays, malformed syntax,
numeric/size/depth limits, dynamic constructs and scanner/parser disagreement.
Use independent Git-produced fixture objects as well as hand-built adversarial
objects; no test may substitute a body hash for a Git OID.

Run scoped tests, both locked full Python suites and installed-wheel/schema
checks. Record an actual bounded public-repository host trial separately from
synthetic object validation; missing host byte capability stays visible. Final
CODE acceptance also requires phases 2–3, scientific/human review remains distinct,
and draft PR delivery never authorizes merge.

Primary format references: [Git objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects.html)
and [Git hash transition](https://git-scm.com/docs/hash-function-transition/2.52.0.html).
These describe object framing and format-dependent identities. The bounded
transport, resource, parser and authority policies above are project decisions.
