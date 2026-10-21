# CODE configuration parser kernel — R1 candidate

Architect-owned next bounded contract for independent review. No implementation
dispatch is authorized by this document. The active Grok Build packet remains
CODE-GIT-KERNEL. Its source must be frozen/reviewed before a successor dispatch.
This parser is another pure building block of CODE-PROOF, not a public command
or CODE completion. Public envelopes, retained I/O and source-only records remain
the later integration packet. CODE-RELATION and CODE-CANONICAL remain required.

This document materializes the numeric/source-coordinate/TOML decisions in
CODE-PROOF-CLOSURE-R3.md; read that immutable document too. In a conflict, this
candidate requires Architect correction before freeze. It does not change any
legacy schema. The eventual source workspace is the new CODE worktree based on
8728aafc9aa7af5caf90d60bfa6ab2ba89419f75 plus its accepted Git kernel snapshot.

## API and scope

Proposed allowed production/test paths, to be bound by a later exact freeze:

1. `src/video_paper_wiki/code_config_parser.py`
2. `tests/unit/test_code_config_parser.py`

No existing source, dependency, metadata, schema or CLI change in this slice.
An independent static span fixture may be added to the freeze only after its
actual content, provenance and hash exist. Test/evidence ownership is separate.

```python
class CodeConfigError(ValueError):
    # code: str, message: str, details: dict, exit_code: int = 2
    ...

def parse_code_config_bytes(
    *, payload: bytes, config_format: str, limits: dict[str, int],
) -> dict: ...
```

Only exact builtin bytes/str/dict/int types are accepted at the API boundary;
bool is not an int. Format is exactly `json` or `toml`. No file-like input,
coercion, custom mapping methods, path inference or file extension inference.
Snapshot validated limits. Callers must not concurrently mutate inputs.
Production is standard-library-only and pure: no file, resource-loader, network,
subprocess, environment, clock, randomness, import of supplied source or dynamic
evaluation during a call. Do not change process-global Decimal context or integer
conversion limits. Returned containers are fresh; raw bytes/Decimal/float are
never present in returned JSON-compatible metadata.

`CODE_CONFIG_PROFILE_LIMITS` is MappingProxyType around a fresh literal dict,
without an exposed mutable backing alias, in this exact order:

| limit | profile maximum |
| --- | ---: |
| max_source_bytes | 262144 |
| max_depth | 32 |
| max_nodes | 1024 |
| max_array_items | 256 |
| max_object_keys | 1024 |
| max_key_bytes | 256 |
| max_string_codepoints | 16384 |
| max_scalars | 512 |
| max_numeric_lexeme_bytes | 128 |
| max_numeric_coefficient_digits | 64 |
| max_numeric_abs_exponent | 128 |
| max_numeric_canonical_bytes | 256 |
| max_declarations | 4096 |

The limits dict has exactly all these keys, each strict int in 1..maximum.
Depth zero is the root; a lowered max_depth=1 still permits root scalars and
one level of children. max_object_keys applies per map, max_array_items per
array. Count implicit nodes as ordinary nodes, and both kinds of TOML declaration
below against the new global declaration cap. That cap bounds repeated dotted
prefix/header evidence independently of node count. Final saved config-envelope
size remains the separate 2 MiB public-wire cap, not an inferred guarantee that
every otherwise valid parser result can be installed.

## Validation and source profile

1. Check payload exact type, format exact type/enum, limits exact shape/types and
   ranges. Check limits map count before key traversal. Check source byte cap
   before decoding, hashing or allocating source-coordinate tables.
2. Decode strict UTF-8. Reject initial UTF-8 BOM, bare CR, literal C0 except TAB,
   LF and CR in CRLF, literal DEL/C1, U+2028 and U+2029. These match the existing
   normalize_code_bytes source rules. Preserve original source, including CRLF,
   codepoints, whitespace, escapes and Unicode spelling. Do not NFC-normalize.
3. A zero-byte or whitespace-only document is CODE_CONFIG_EMPTY. A TOML document
   containing only whitespace/comments is also EMPTY under this project profile,
   even though TOML itself permits it. Explicit empty JSON objects/arrays, an
   empty ordinary TOML table header, and assigned empty arrays/tables are valid.
4. Scan the complete format, charging all limits before appending the next
   node/member/element/declaration or descending beyond depth. String/key limits
   are checked on decoded content; numeric lexeme cap before Decimal conversion.
   Never allow deeply nested hostile input to enter the stdlib parser first.
5. Finish the bounded scanner successfully, then cross-check the entire decoded
   semantic tree using json.loads or tomllib.loads. Only after both agree may
   canonical nodes and their exact spans be returned. No partial result on error.

Use bounded fixed reason strings and positions; do not forward parser exception
messages, source lexemes, raw line snippets, decoded keys or arbitrary repr in
exceptions. A decoded JSON string may contain escaped control characters when
RFC 8259 permits them; a TOML basic string may contain its permitted escapes.
Those decoded characters are data. The literal-source prohibition in step 2 is
not a second blanket ban on escaped characters. Unpaired surrogate codepoints
are forbidden in every decoded key/value; valid JSON surrogate pairs represent
the corresponding scalar. No new Unicode normalization is introduced.

## Grammar and typed semantics

JSON follows the complete RFC 8259 grammar within the bounded source profile.
Root may have any JSON type. Only SP/TAB/CRLF/LF are whitespace. No comments,
trailing commas, duplicate decoded object keys, nonfinite constants, leading
plus, extra leading zeros, underscores or trailing material. Escaped and literal
spellings of the same key collide before dict construction. JSON member order
does not affect node preorder but each original declaration span is preserved.

TOML follows the single-line subset in CODE-PROOF-CLOSURE-R3. Ordinary headers,
dotted keys, quoted keys (including empty quoted keys), inline tables, mixed
arrays, booleans, single-line literal/basic strings and bounded decimal numeric
forms are supported. Dotted-key whitespace does not enter component token spans.
Bare keys use exactly ASCII A-Z/a-z/0-9/_/-, not the Git path grammar. Literal dots
inside quoted keys are part of one component. Headers address the document root;
assignments address the current table, with nested inline-table context respected.

TOML unsupported constructs are recognized and refused, never interpreted:
multiline string delimiters, arrays of tables, physical newlines inside any
array or inline table, dates/times, base-prefixed integers, inf/nan and line-joining
backslashes. Comments after a complete header/value and standalone comments are
allowed. A hash inside a string is data. Same-line trailing array comma is
allowed; trailing inline-table comma is invalid. TOML has no null token.

Track ordinary tables, implicit header parents, dotted-key-created maps and
closed inline-table boundaries. Permit implicit header-parent promotion, such as
`[a.b]` followed by `[a]`, while refusing repeated explicit headers and value/map
redefinition. Permit later child headers under dotted-key-created parents when
tomllib permits them; do not simply reject every descent through such a parent.
Inline tables and their descendants cannot be extended outside their braces.
Repeated dotted prefixes used by distinct assignments share one map node.

For both formats, kind is `object`, `array`, `string`, `integer`, `decimal`,
`boolean`, or `null`. Containers have null value; boolean has strict bool, null
has null, string has exact decoded str, and both numeric kinds have a canonical
decimal magnitude str. Numeric source lexeme is separately retained unchanged.
The R3 exact grammar, negative-zero refusal, coefficient counting, explicit and
tuple exponent bounds, and context-independent fixed-point expansion apply.
All four numeric caps in this profile can be lowered. A grammar-valid magnitude
exceeding a numeric cap is LIMIT_EXCEEDED; negative zero is NUMBER_INVALID.
For integer syntax, the implicit exponent and tuple exponent are zero. Decimal
syntax preserves its kind even when its canonical value is `1` or `0`.

Cross-check json.loads with duplicate-detecting object_pairs_hook,
parse_float=Decimal and a nonfinite-refusing parse_constant. Check json integers
as exact int, never bool. Cross-check tomllib.loads with parse_float=Decimal.
Compare the full key set, array order, node kind and exact decoded value at every
path. Compare numeric tuple/value without context-sensitive arithmetic; numeric
kind is strict int versus Decimal in stdlib. Do not use ordinary Python == alone
where True == 1 would hide a kind mismatch. Do not compare only leaf counts or a
subset of paths. Scanner rejection precedes stdlib validation; stdlib rejecting
a scanner-accepted input is PARSER_MISMATCH, including unsupported stdlib types.

The literal dynamic profile from R3 applies after decoding to each actual key
and string value. A key exactly `_target_`, `include`, `includes` or `import` is
refused. In string values refuse `${`, `$(`, `{{`, `}}`, `%(` anywhere, or a full
match of `[A-Za-z_][A-Za-z0-9_.]*\s*\(.*\)` on the stripped string. Freeze that
regex with re.DOTALL so an escaped newline inside arguments cannot bypass it;
use Python's Unicode str.strip and \s behavior, with no locale dependence.
These rules do not scan comments and do not claim general executable-code
detection. Rejection returns DYNAMIC_UNSUPPORTED; public integration may offer
an explicitly requested source-only result using the retained raw proof.

## Exact result and coordinate representation

Construct the success dict and nested records in the key order shown:

```text
{
  config_format,
  source: {
    body_size_bytes, body_sha256, normalized_sha256,
    newline_style, ends_with_newline, line_count
  },
  budget: {
    node_count, scalar_count, max_depth_observed,
    declaration_count, max_array_items_observed, max_object_keys_observed
  },
  nodes: [{
    path, kind, value, numeric_lexeme, children, value_span, declarations
  }, ...]
}
```

source contains exact raw size/SHA-256 and normalized-text metadata equivalent to
code_text_metadata. Normalize only CRLF to LF for the normalized hash/line count.
newline_style is mixed/crlf/lf/none; ends_with_newline is a strict bool. line_count
is LF count plus one for a nonempty unterminated last line. Empty selected physical
lines count. Production may implement these small pure operations independently;
tests must prove byte-exact parity with existing code_text_metadata and
code_snippet_sha256. No legacy module edit is authorized.

Node paths are JSON Pointers built from decoded keys with ~0/~1 escaping; root
is "". Use original Unicode spelling, not normalized equivalents. DFS preorder
visits maps by key UTF-8 bytes, arrays by increasing integer index. children is
the immediate child-path list in that same order; scalars have []. Each node
appears once. numeric_lexeme is str only for numeric nodes and null otherwise.
value_span is non-null for every scalar, JSON container and TOML explicit array
or inline table; it is null for TOML root, ordinary tables and implicit maps.

A Span has exactly:

```text
{
  byte_start, byte_end, codepoint_start, codepoint_end,
  line_start, column_start, line_end, column_end,
  raw_sha256, snippet_sha256
}
```

Offsets are original-source zero-based half-open; line/column one-based with
exclusive end. Every span is nonempty and in bounds. Columns count codepoints,
including TAB as one. CRLF occupies two codepoints/bytes, advances one line after
LF, and no span boundary splits it. raw_sha256 covers the exact raw byte slice.
snippet_sha256 covers actual intersecting physical lines according to existing
code_snippet_sha256; exclude a following line when end is exactly its start.
Record no raw source substring in a Span. Token spans include enclosing quotes
and escapes; explicit container spans include delimiters/interior whitespace.

declarations is a list of closed `{kind, span}` records. Sort by span.byte_start,
then span.byte_end, then kind ASCII; never duplicate an identical declaration.
The kinds and attribution are:

- `json_key`: complete original key token, attached to that member's node.
  Root and array elements have no JSON key declaration.
- `toml_key`: one complete bare/basic/literal key-component token from any key
  assignment or ordinary table header, attached to the node addressed by that
  component prefix in its actual context. Repeated prefixes on different source
  lines add distinct token declarations to their existing map node.
- `toml_table`: the complete ordinary header from `[` through `]`, attached
  only to its terminal table node, in addition to its component token declarations.

For `a . "b" = 1`, /a has the a token declaration and /a/b the "b" token,
with /a/b value_span on 1. For `[a.b]`, /a has the a declaration; /a/b has the b
declaration and full [a.b] table declaration. Both have null value_span. The
later allowed `[a]` adds its a and full-header declarations to /a. Empty declared
tables thus have evidence without invented value spans. Root's declarations
remain []. The declaration cap charges each unique record when inserted.

## Closed errors

All errors use CodeConfigError with exit_code=2, fixed non-source-echoing message
and details with a bounded `instance_pointer` naming only API metadata, e.g.
/payload, /config_format or /limits/max_depth. Do not put decoded user keys in
error pointers. Scanner errors additionally carry codepoint_offset and
byte_offset (possibly EOF), derived from the original source when available.

| code | required additional context |
| --- | --- |
| CODE_CONFIG_INPUT_INVALID | reason |
| CODE_CONFIG_BYTES_INVALID | reason, byte_offset |
| CODE_CONFIG_EMPTY | reason |
| CODE_CONFIG_SYNTAX_INVALID | reason, codepoint_offset, byte_offset |
| CODE_CONFIG_UNSUPPORTED | reason, codepoint_offset, byte_offset |
| CODE_CONFIG_DUPLICATE_KEY | reason, codepoint_offset, byte_offset |
| CODE_CONFIG_LIMIT_EXCEEDED | limit_name, limit, observed |
| CODE_CONFIG_NUMBER_INVALID | reason, codepoint_offset, byte_offset |
| CODE_CONFIG_DYNAMIC_UNSUPPORTED | reason, codepoint_offset, byte_offset |
| CODE_CONFIG_PARSER_MISMATCH | reason |

UTF-8 errors identify the first invalid byte without echoing text. Syntax-invalid
number grammar is SYNTAX_INVALID; recognized out-of-subset TOML numeric/datetime
forms are UNSUPPORTED. Repeated decoded keys, duplicate headers and semantic
table/value/inline redefinitions are DUPLICATE_KEY. Other malformed syntax is
SYNTAX_INVALID. Limit violation wins when a required bounded operation would
exceed its cap; do not allocate/convert first and then report it. Dynamic rules
are checked after that token's decoding/limits/Unicode validation and before
its semantic insertion. No incidental ValueError/RecursionError/Decimal error
or stdlib parser traceback escapes as the public exception type.

## Required acceptance cases

Use separately authored expected vectors, not only scanner output fed back into
itself. Cover JSON/TOML `1e-4`, betas `[0.9,0.999]`, decimal kind for `1e0`, plus
and underscore grammar, both explicit/tuple exponent caps, negative-zero variants,
coefficient and canonical-length boundaries, tiny/hostile Decimal contexts without
rounding or global mutation. Cover literal Unicode and escaped Unicode including
valid surrogate pairs and invalid isolated surrogates, CRLF/LF mixtures, tabs,
empty strings/keys, quotes and pointer escaping. Assert full exact spans/hashes
from original source and snippet parity, not merely offsets produced by the parser.

Exercise duplicate escaped keys, all TOML table promotion/redefinition cases,
dotted/quoted equivalence, inline boundaries, same-line nested/mixed arrays,
array trailing comma versus inline trailing comma, comment-only refusal,
unsupported multiline/date/base/inf/nan constructs and ordinary comments
containing dynamic-looking text. Test every dynamic marker including escaped
newline in a callable-looking string, plus harmless near matches. Guard every
limit with lower-cap and boundary tests, including repeated prefix declarations,
node/scalar/depth counts and early source cap before decoding/hash work.

Instrument stdlib cross-check to return wrong bool/int, missing/extra keys,
reordered arrays, incorrect strings or unsupported types and require mismatch.
Malformed inputs must be rejected without running eval/import/subprocess/network.
After import, guard filesystem/resource/network/subprocess functions during a
complete success and refusal. Repeat success to prove deterministic key/list
ordering, unchanged limits and integer-only JSON-compatible output.

Builder will run scoped tests on both locked Python runtimes in short real
/private/tmp directories. Complete CODE integration still requires both full
suites, installed wheel/resource parity, actual raw/normalized host observations
and public retained-I/O adversarial review. Passing this parser is not evidence
that a program uses a value, an official repository relationship exists, or a
paper's claim has scientific or human approval.

Reference checks for the format baseline: [TOML 1.0](https://toml.io/en/v1.0.0),
[RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html),
[Python tomllib](https://docs.python.org/3.13/library/tomllib.html),
and [Decimal](https://docs.python.org/3.13/library/decimal.html).
Source/control, subset, dynamic-marker, size and evidence restrictions here are
project policy. They do not redefine the general formats.
