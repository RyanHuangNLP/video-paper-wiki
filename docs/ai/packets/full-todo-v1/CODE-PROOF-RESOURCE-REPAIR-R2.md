# CODE resource repair — bounded R2

This bounded successor preserves the R1 output, generated resources, reviews,
and failed boundary evidence. It does not change the accepted CONFIG source,
the fourteen product paths, the R12 resource contract, or public CODE scope.
The exact input freeze and separate Architect handoff authorize a launch.

## Ownership and output mechanism

Grok Build remains the sole author of the generator and resource test module.
R1 now supplies complete existing files. For this repair only, replace the R1
full-file response mechanism with one declarative exact-text patch response.
The coordinator may apply reviewed literal replacements to a fresh evidence
copy; this does not authorize changing or normalizing R1 evidence in place.

Return one `BEGIN_PATCH code-resource-r2` / `END_PATCH code-resource-r2` block
containing one JSON code fence. Its closed root has exactly these fields:

- `schema`: `full-todo.code-resource-exact-text-patch.v1`;
- `base_files`: the exact two filename-to-SHA-256 entries below;
- `edits`: a nonempty ordered array of closed `{file, old, new}` objects;
- `brief`: a closed object with `changes` (nonempty string array),
  `tests_run` (false), and `unresolved_questions` (string array).

The base names and hashes are:

| File | SHA-256 |
| --- | --- |
| generate_code_proof_resources.py | df798bf22b08d385c1b2de712d950e7978f5d89836486beb703d8bb1d8e749b2 |
| test_code_proof_resources.py | 19c8d6355bfe8db22c37ec7abce96409bf9d8cef989443ef560ece1af1def74f |

Each `file` names one of those two files. `old` must be a nonempty literal
substring occurring exactly once in the current file after preceding edits.
`new` is its complete literal replacement. Preserve all unrelated source.
JSON escaping must reproduce actual newlines and literal regex backslashes.
Use at most 64 edits, a response no larger than 1048576 bytes, and resulting
files no larger than 262144 bytes each, each ending in exactly one LF.
No expressions, encoded program, shell patch, executable installer, dynamic
edit logic, unrelated files, placeholders, or manual schema byte edits.

The coordinator validates the closed response, base hashes, unique matches and
resulting syntax without executing returned code, writes two fresh complete
candidate files, and freezes their hashes. Independent review must approve the
resulting full generator before controlled fresh generation. Schema validation,
profile-bound fixture rebuilding, fourteen-path freeze, regression suites and
installed-wheel byte parity remain required before resource acceptance.

## Confirmed boundary repairs

Both locked Python 3.12 and 3.13 reproduced the same 16 failing expectations
across 34 independent schema probes. The eleven-resource inventory, exact
serialization, profile inventory and all 314 references pass. All 264 original
preparation fixture shapes validate, which does not repair the omitted edges.

1. Repository component exclusions must still apply before a slash. The owner
   `.` or `..` is forbidden in ordinary and saved repositories. Repository
   name `.` or `..`, and a repository `.git` suffix, are forbidden both at the
   end of a repository string and when followed by a commit/blob/raw URL path.
   Current whole-string negative end anchors lose their effect when a component
   is followed by `/`. Preserve the R9 permitted leading dot, underscore and
   hyphen spellings, one-character components, input ASCII case and saved
   lowercase spelling. Do not apply these repository exclusions to logical
   source-path components.
2. A JSON Pointer may contain 32 path segments, each a 256-byte key consisting
   entirely of `/` or `~`. Its escaped length is `(2 * 256 + 1) * 32 = 16416`.
   Accept this exact maximum; reject 16417. Keep the existing escape grammar
   and all other CONFIG limits.
3. A 262144-byte source can end with a scalar whose one-based exclusive
   `column_end` is 262145. Permit that value and reject 262146. Preserve byte
   and starting-coordinate maxima; do not increase every coordinate together.
4. `.work/a` is a valid shortest canonical relative bundle directory, length 7.
   R3 lines 50–55 require a canonical relative path below checkout `.work`,
   with no symlink, lexical alias or exact dot/dot-dot component. R6 lines
   69–76 apply `BATCH_ID_RE` only to the output batch argument, separately
   requiring a canonical `.work/...` input path. Reusing the batch grammar
   for each input directory component is an uncontracted restriction.
   Separate these grammars. Accept `.work/input.v1`, `.work/_input`,
   `.work/-input`, `.work/input_`, `.work/input-`, `.work/.input`, and nested
   combinations. `.work`, `.work/`, repeated/trailing slashes and dot/dot-dot
   components must fail. Keep the output batch and stored-path definitions
   unchanged.

For this input-path schema, the Architect makes the lexical clarification
explicit: after literal `.work/`, require one or more nonempty slash-separated
components. A component may contain ordinary Unicode and spaces as well as
dot/underscore/hyphen; forbid slash within a component, backslash, C0/C1 control
characters, DEL, U+2028/U+2029 and exact `.` or `..`. Preserve the existing
4096-character total bound. Do not impose the batch character alphabet,
alphanumeric ends, per-component 128-character bound, Git path depth, or a
`.git` exclusion on input directory components. NFC, encoded-byte bounds,
symlinks, path identity and input/output disjointness remain semantic checks.

Add discriminating regression tests for each repaired positive and negative
boundary, validating each positive before deriving a negative from it. Include
all three URL kinds and both standalone repository definitions. These are
schema checks and must not claim filesystem identity or public-command replay.

## Test review closure

The complete test review is `steward-resource-test-review-r1.json`, SHA-256
`fb9634eee4cec492eed86e84d2b1ad14525683632daab35d57ec7e458a09a3fc`.
Repair its four findings without weakening existing assertions:

1. `(title, pointer)` deduplication skips different closed object branches at
   the same location. Include object keys and branch discriminators in the
   coverage identity, or remove the deduplication. Required-field omission and
   unknown-field rejection must exercise all represented branches. Preserve
   the sole explicit optional `limits` exception at the request-input root.
2. The typed CONFIG null-result negative must change only `result` to null.
   Test an invalid `source_only_reason` in a separate fresh mutation. A negative
   must not pass merely because an unrelated second field is invalid.
3. The generic integer-mutation traversal must preserve dictionary keys and
   list indices by container type. A string key `"0"` is not the integer index
   `0`. Add a small traversal-helper regression on a nested dict/list value
   containing that key. Do not invent a new public wire field or change the
   prepared fixture bundle: its closed wire objects have fixed field names.
4. Add focused one-field malformed-value checks for CONFIG declaration kind
   and span, Git target outcome/reason, Git walk-edge values, and nonhex/wrong-
   length IDs and hashes. CONFIG declarations have only `kind` and `span`;
   they have no `path` member. Test existing actual field shapes. Cover each
   Git target branch; an explicit structurally valid synthetic unsafe target
   may be checked through the common definition because the prepared bundle
   does not contain an unsafe Git outcome. Validate every such positive first.

Validate all prepared positive fixtures before any mutation test uses them,
including when a single pytest test is selected. A session fixture can perform
that validation once using the explicit registry. Use semantic selectors for
needed modes, states, formats and populated members, rather than assuming a
particular first row has optional fields. Preserve intentional schema-valid
identity/derivation forgeries and the separation from semantic replay.

## Runtime boundary

Use the pinned Grok Build `grok-4.6` model with `xhigh`, normal permission mode,
a fresh UUID and prepared temporary directory, no memory or subagents, and
only `read_file` on the manifest's named copies. Do not read the repository,
credentials, session history or unrelated files; do not write or execute code,
use shell/network tools, or run tests. The model response is a candidate only.
No Git delivery, real Vault action, human-gate closure or CODE completion is
authorized by this repair.
