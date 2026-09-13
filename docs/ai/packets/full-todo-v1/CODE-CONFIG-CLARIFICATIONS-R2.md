# CODE configuration kernel clarifications — R2 candidate

Architect supplement to unchanged CODE-CONFIG-KERNEL-R1.md. This closes the two
semantic findings in E/code-config-kernel-contract-review-r1.json. It is not an
implementation dispatch or fixture/worktree freeze. Prior review stays history.

## Dynamic refusal positions

Every CODE_CONFIG_DYNAMIC_UNSUPPORTED byte_offset/codepoint_offset is the start
of the complete original source token that decoded to the offending key or
string value. For a quoted token this is the opening quote. For a TOML bare key
this is the first key character. For dotted/header keys it is that exact component
token, not the beginning of the entire dotted expression/header/assignment.
Do not map the decoded match position back into raw escapes. The same rule
applies to substring markers and the full stripped callable regex, including
values containing escaped newlines or escaped dollar signs.

The instance_pointer is /payload. Reasons are exactly dynamic_key for the four
forbidden exact keys, dynamic_marker for any of the five substring markers,
or callable_string for the full regex. Marker detection takes precedence over
callable-string classification if both match the same value. No marker text or
decoded source value is included in the exception. Normal token limits and
Unicode validation still precede the dynamic rule.

## TOML table state transitions

The separately hand-authored CODE-CONFIG-TOML-MATRIX-R2.json provides 26 finite
positive/negative vectors with complete expected semantic maps or exact refusal
code. Both locked Python versions must independently reproduce the stdlib
acceptance/map portions before implementation freeze. They supplement these
rules; they are not a whitelist of exact source strings.

Treat ordinary headers as section boundaries. Root is the initial section.
Before starting another header, finalize all map prefixes traversed/introduced
by dotted assignments in the section just left. Track these states distinctly:
implicit header parent; explicitly header-declared table; current-section dotted
prefix; finalized dotted prefix; and closed inline-container/value boundary.

For a new ordinary header, resolve components from the root. Ancestor components
may be any normal table, including a finalized dotted prefix or header-declared
table, but never a scalar, array, inline table or descendant of a closed inline
container. Missing ancestors become implicit header-parent tables. The terminal
table must be absent or an implicit header parent; mark it header-declared.
An existing header-declared or finalized/current dotted-prefix terminal cannot
be redeclared. This permits both parent promotion and new child headers below
a dotted-created table without reopening the dotted parent itself.

For a dotted assignment, start at the current table (or currently parsed inline
table's own local root) and resolve the components before the final key. Each
such relative prefix must be missing, an implicit header parent, or a dotted
prefix belonging to that same current section/local inline-table context. An
explicitly header-declared relative prefix or a finalized dotted prefix cannot
be used to redefine that namespace by a dotted assignment. The starting current
table itself is context, not a relative prefix to reclassify. Missing or implicit
relative prefixes become current-section dotted prefixes, shared by later
assignments in that same context. A scalar/array/closed inline boundary refuses
descent. The terminal assignment key must be entirely absent, even if an existing
value is an empty table or otherwise equal.

Inside an inline table, dotted assignments may create/share local prefixes.
Any nested inline table or array value becomes closed when that value finishes;
later assignments cannot extend it or any descendant. The outer inline table
becomes closed when its own brace closes. Ordinary headers cannot occur inside
an inline table. No array-of-tables behavior is implemented by this profile.

Every stated redefinition/descent refusal uses CODE_CONFIG_DUPLICATE_KEY in
the scanner. It is not deferred as PARSER_MISMATCH. The stdlib remains the final
independent full-tree check; a discrepancy on an input that passes the explicit
scanner rules is PARSER_MISMATCH. This replaces reliance on the phrase “when
tomllib permits” as the sole promotion rule without widening the TOML subset.

Existing node identity/declaration attribution, span shape, dynamic profile,
numeric semantics and all limits remain unchanged. Before any future dispatch,
the exact static span fixture, matrix hashes, successor source snapshot and final
allowed paths must still be bound in the separate freeze.
