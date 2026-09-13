# CODE-PROOF contract closure — R3

Architect decisions answering `E/code-proof-design-review-r2.json`. This document
amends the listed sections of CODE-PROOF-DESIGN-R2; the earlier design and review
remain immutable. The complete public workflow is still pending its exact wire
schemas and I/O review. This document alone does not authorize production edits.
Subsequent main implementation is Grok CLI `grok-4.6 / xhigh` under ownership R3.

The pure in-memory Git verifier may be implemented as an independently frozen
kernel packet before the public transport/configuration schema freeze. Its own
input/output/limits/errors and allowed paths must be complete and reviewed first.
It does not implement or approve any public workflow, path safety, hosting claim,
source admission or full CODE completion. CODE-RELATION and CODE-CANONICAL remain
required successor work; their scope has not been removed.

## Persisted raw input and deterministic repair

The output fixed files are `request.json`, `intent.json`, `bundle.json`, and
`observation.json`. The exact child families are `objects/`, `configs/`, and
`handoffs/`. `bundle.json` contains the byte-exact supplied canonical saved
`code-git-bundle` envelope, including its one terminal LF. It exists only for the
git_objects mode. Observation binds both intent and bundle saved-byte references.
Normalized-only mode forbids bundle.json and objects. Extra files/directories,
unsafe types/modes and derived objects without complete observation are refused.

Intent binds the request, mode, complete normalized acquisition metadata and
its identity. In raw mode it additionally binds the canonical checkout-relative
input bundle directory spelling and complete bundle saved-byte reference. That
bundle contains the ordered exact object inventory with each OID, type, body size,
body SHA-256 and framed SHA-256. Consequently intent transitively binds every
input body and the complete target set; it cannot change after a partial install.
Do not use an unbound input path or an unrelated directory checksum as identity.

Install order is request first; observe preflights the entire supplied input,
then installs intent, bundle, OID-sorted bodies and observation last. A repeated
observe must re-retain and fully revalidate the same path spelling, mode,
metadata, manifest and exact body inventory before repairing the missing suffix.
Changed/missing external input refuses repair without writing. Once complete,
status/config/handoff replay only the retained output bytes; the external bundle
is no longer required and must not be reopened for those commands.

An output intent without observation is pending, even if every expected body is
already present. Status must identify missing expected files or the absent final
observation without manufacturing either. A saved observation without all exact
dependencies is corrupt, not pending. Existing identical files are reused only
when captured on the initial scan; late insertion after first absence is unsafe.

## Input and output roots

The raw input bundle must be a canonical relative path below checkout `.work`,
resolved through retained descriptors and checked against its original spelling.
No symlink component, lexical alias, dot/dot-dot component or replaced marker is
permitted. Input bundle root and output code-evidence root must be disjoint:
neither equal nor an ancestor/descendant of the other. Reject equal descriptor
identities as well. Sibling bundles in the same batch are allowed if their fixed
complete sets are disjoint; shared ancestors are retained once with one identity.

Capture bundle root and objects complete sets before classifying their entries,
including every unsafe or unknown sibling. Retain all accepted source files,
directory descriptors, exact bytes and named edges through every output install
and all error exits. Output creation must not mutate an input directory's scoped
entry set. Persistent named-edge failure overrides an earlier semantic error.

## Limits and raw versus normalized text

The 16 KiB limit applies only to inline normalized_text observation input.
It does not limit a raw Git blob or a normalized hash computed from retained raw
bytes. Raw object bodies may be up to 8 MiB, within the 32 MiB aggregate body cap.
Raw observations and handoffs contain hashes/metadata and exact local byte refs,
never a duplicate full inline code string. A valid raw UTF-8 blob may therefore
have more than 16 KiB of text and remain a handoff candidate.

Typed configuration parsing separately requires a configuration-role raw blob
of at most 256 KiB. A larger source can retain raw proof and literal source
handoff, but config parsing returns an explicit limit error. No truncated typed
result is emitted. Request caps may lower every relevant positive profile limit.

Before reading any body, check manifest bytes <=1 MiB, object count <=2048,
each declared size <=8 MiB, sum of all declared sizes <=32 MiB, and matching stat
sizes. Zero-length bodies are permitted; counts and limit values are strict ints,
never bools. While reading, verify exact bytes and hashes; never treat stat alone
as proof. Parsed unique supplied tree entries are charged against the total
32768 cap before appending each parsed entry. A declaration cannot pre-state the
exact tree-entry count, so this is an incremental parsing cap, not an impossible
pre-read assertion. Bound each path walk by its requested component count.

The 128 MiB output limit includes all installed logical files, generated
canonical request/intent/bundle/observation/config/handoff bytes and any live
atomic temporary files. Before an install, charge actual current retained bytes
plus the complete new target when absent, plus the maximum temporary duplicate
the concrete installer can create. Include orphan/pending files before refusing
them; do not exclude bytes because their name is invalid. Never start an install
whose peak charge exceeds the limit. Expected bounded files are pre-serialized
before writes. Unknown oversized files are refused by stat without being read.
One private install temp may exist at a time; retain/verify its returned identity
and clean its expected name on every exit, with all-exit lineage checks. At most
32 config documents of 2 MiB each are possible. The final wire freeze must name
caps for every other metadata file and the total family file counts.

## Numeric grammar and canonical typed values

All artifact JSON continues to use the existing integer-only JCS implementation.
Configuration numeric values are strings with an explicit integer/decimal kind;
their original source lexemes and spans are separately retained. No float
conversion or Decimal arithmetic depending on the process context is permitted.

JSON numeric lexemes match exactly:

```text
-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?
```

A lexeme containing a dot or exponent has decimal kind, including `1e0`; otherwise
it has integer kind. JSON plus signs, leading-zero integers, underscores, `1.`,
nonfinite values and trailing fragments are invalid.

For TOML define `D = [0-9](?:_?[0-9])*` and
`I = (?:0|[1-9](?:_?[0-9])*)`. Decimal-integer tokens match `[+-]?I`.
Finite-float tokens match `[+-]?I(?:\.D(?:[eE][+-]?D)?|[eE][+-]?D)`.
These are grammar macros expanded before matching, not literal regex names.
Base-prefixed integers, infinity/NaN, timestamps and every other numeric form are
outside the supported subset. Underscores are removed only for Decimal parsing.
TOML plus signs are accepted and omitted in the canonical magnitude string.

Bound each numeric source lexeme to 128 UTF-8 bytes. After removing separators,
the coefficient contains at most 64 digits after leading zero removal (all-zero
coefficient counts as one digit; trailing coefficient zeros still count).
The explicit written exponent and the exact Decimal tuple exponent must each be
within [-128,128]. Check explicit exponent magnitude before constructing Decimal.
The coefficient/sign/exponent tuple is used directly to expand fixed notation;
no rounding, quantize, normalize or context-sensitive arithmetic is allowed.
Strip redundant fractional zeros and a resulting decimal point. Canonical zero
is `0`; any lexeme with a negative sign and zero value is refused, for either
numeric kind. The final canonical string is at most 256 bytes. Integer values
have no decimal point. Decimal values may canonically be `1`, while their kind
and source lexeme still prove they were written as decimal/float syntax.

Cross-check complete shape, paths, decoded values and numeric kinds against
stdlib JSON with `parse_float=Decimal` and TOML with `parse_float=Decimal`.
JSON integer tokens cross-check as strict int; do not mistake bool for int.
Reject duplicate decoded JSON keys before dict creation, nonfinite constants,
surrogates, trailing bytes and scanner/parser disagreements. The standard parser
is a second check, not permission to accept syntax outside the frozen subset.

## Source coordinates and TOML subset

Offsets and columns refer to the original strict UTF-8 source decoded to Unicode
codepoints, before CRLF normalization and before interpreting string escapes.
Byte offsets and codepoint offsets are zero-based half-open ranges. Line/column
positions are one-based, with exclusive end. Columns count codepoints, including
one for a tab; they are not display cells, graphemes or UTF-16 units.

CRLF consumes two bytes/codepoints and advances one line after LF. The position
between CR and LF is still the old line with the column incremented by one; no
valid token boundary may split that pair. Bare CR is refused. LF alone advances
one line. A JSON string token span includes its quotes and source escapes; it
does not point into the decoded value. Raw span SHA-256 hashes that exact byte
slice. Line-snippet SHA-256 follows the existing code_snippet_sha256 contract
over the actual physical lines intersected by the nonempty span, excluding an
exclusive end at the start of the following line. No value span is fabricated
for an implicit node. Empty source has no typed document.

JSON root and explicit containers have spans from opening to closing delimiter,
including interior whitespace but not unrelated leading/trailing source
whitespace. Keys have separate token spans. Every scalar has a mandatory value
span. TOML document root and implicit/ordinary table map nodes have null value
spans; table header and key token declarations have separate exact spans.
Array and inline-table nodes have their explicit bracket/brace value span.

The initial TOML subset allows single-line basic/literal strings, the numeric
forms above, booleans, single-line arrays (including nested single-line arrays),
single-line inline tables, ordinary table headers and dotted keys. Reject
multiline strings, multiline arrays/inline tables, arrays of tables, dates/times,
base-prefixed integers and unsupported syntax before cross-checking stdlib.
Comments after complete values/headers and standalone comments are allowed;
comment markers inside a string are ordinary data. A backslash does not join
physical lines. Arrays may use a same-line trailing comma when TOML 1.0 permits
it; inline tables may not. Array element types may differ.

Decoded key equivalence governs collisions: quoted/unquoted/dotted spellings
cannot create duplicate values or redefine an already defined table/value.
Implicit parent tables may be promoted by a later ordinary header only when
TOML 1.0 and tomllib allow that exact construct; emit the same single map node and
add its explicit header span, never a duplicate node. Parent array/inline-table
boundaries and dotted-key-created tables cannot be redefined by a later header.
All constructs must yield the exact same complete typed tree in both parsers.

Node paths use original decoded keys with JSON Pointer `~0`/`~1` escaping.
Keep Unicode spelling unchanged. Traverse nodes in deterministic depth-first
preorder: map children by decoded key UTF-8 bytes, array children by integer
index. Root path is the empty string. Count root and all container/scalar nodes
toward 1024; root depth is zero, maximum node depth 32. Arrays have at most 256
items, maps at most 1024 keys, each decoded key at most 256 UTF-8 bytes, each
decoded string at most 16384 codepoints, and the entire tree at most 512 scalars.
The final schema will express a closed node record with kind, typed value,
children, optional value span and separate declaration/key spans.

Dynamic configuration interpretation is never attempted. In typed mode, refuse
decoded string values containing `${`, `$(`, `{{`, `}}`, or `%(`. Also refuse an
entire stripped string matching `[A-Za-z_][A-Za-z0-9_.]*\s*\(.*\)` and any map key
exactly equal to `_target_`, `include`, `includes`, or `import`. These deliberate
conservative literal profile rules apply to keys/values as stated, not arbitrary
substring searches over comments or all raw source. Such a file can still receive
an explicit source-only result with raw proof and no typed nodes. These rules do
not claim to detect executable semantics generally; nothing is evaluated even
when a string passes them.

## SHA-256-capable handoff

A source-file handoff is explicitly `successor_only: true`; no phase-1 command
passes it to any legacy manifest/capture adapter. Each target handoff carries
the request/observation/bundle refs; object_format; exact-width commit/root-tree/
blob OIDs; logical path and roles; raw body ref and size/body SHA-256/framed
SHA-256; normalized text metadata; verified walked-edge proof; host assertion
status; and the unverified source-association ref when supplied. An optional
config ref must bind that same blob and path. Handoff paths refer to stored blob
bytes and do not duplicate or reinterpret them. Source body SHA-256 is distinct
from Git framed hash. Exact fields and per-file caps are closed in the successor
public wire schema before implementation. Legacy 40-hex schemas stay unchanged.
