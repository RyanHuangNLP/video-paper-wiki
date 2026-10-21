# CONFIG oracle corrections — R3 candidate

This is an Architect correction candidate for independent review, not a new
Builder dispatch or permission to modify a reviewed source snapshot. Preserve
the R1/R2 fixtures, their earlier reviews, the complete Grok response, and the
unchanged three-file diagnostic candidate. Both locked Python runs exposed the
same failures; the separate 64-case JSON and 67-check adversarial runs passed.
The production module remains unaccepted until independent review finishes.

## Correct the independently authored expected data

The `toml-dotted-promotion` source is unchanged. Its `/a` declarations must be
the `a` component at bytes 25..26, the complete `[a]` header at 40..43, and its
`a` component at 41..42, in the prescribed declaration order. Bytes 15..16 are
inside the word `value` and cannot declare `/a`. Add the complete `value` key
at bytes 14..19 to `/x/z/value`, and the complete `value` key at 30..35 to
`/a/b/value`. Recompute all coordinate and hash fields from those manually
specified source slices using the established source/snippet conventions.
Other nodes, source bytes, values and children remain unchanged.

The existing `json-tuple-exponent-over` source is 131 bytes. Its first required
bounded operation exceeds `max_numeric_lexeme_bytes=128`, with observed=131.
Keep that source as the lexeme-before-exponent refusal, preserving the old ID
with a correction note. Add a separate `json-short-tuple-exponent-over` vector
using `1.0e-128`: eight source bytes, explicit exponent -128, exact tuple
exponent -129, and the expected absolute-exponent limit 128 / observed 129.
This retains both refusal obligations without permitting a larger lexeme cap.

## Distinguish diagnostic prose from required error fields

R1 requires fixed, bounded, non-source-echoing reasons. It does not enumerate
the literal reason strings for syntax, duplicate-key, byte or limit errors.
R2 separately fixes the three dynamic reason tokens and their token-start
positions. The old fixture's explanatory English `expected.reason` values
were accidentally treated as a second closed error vocabulary by the returned
test module. Move non-dynamic prose to `reason_description`; retain it as
explanation, not as the runtime reason enum. Dynamic expected reasons become
exactly `dynamic_marker` or `callable_string` as applicable, with no test-side
case-name special cases.

Likewise, the old generic `anchor_span` records are source annotations, not a
uniform promise that every error points to the same enclosing token. Preserve
them under `source_anchor_span`, with the duplicate-header annotation corrected
to the conflicting second `[a]` at 10..13. A future test must distinguish these
source annotations from explicitly required `error_details`:

- BOM and bare-CR vectors require the exact offending `byte_offset` (0 and 5).
  Their `CODE_CONFIG_BYTES_INVALID` context has no required codepoint offset.
- Dynamic vectors require `/payload`, the exact R2 reason, and the complete
  offending token's byte/codepoint start. The nine unchanged R2 supplemental
  vectors remain authoritative, including their positive near-match cases.
- Syntax, unsupported, duplicate-key and number-invalid errors retain both
  offsets. Test exact integer types, source bounds, byte/codepoint consistency,
  and a boundary that does not split CRLF. Do not require an uncontracted
  preference between a component start, enclosing header start or parser EOF.
- Every refusal still checks the exact error code, exit code 2, required closed
  context fields, bounded metadata pointer, fixed nonempty reason where required,
  and absence of raw source/decoded keys/lexemes in error context. Limit checks
  retain their exact limit name, configured value and observed count; their
  optional explanatory reason does not replace those fields.

This clarifies only the original R1/R2 distinction. It does not allow wrong
error codes, missing context, guessed offsets, dynamic-rule weakening, or a
stdlib mismatch to replace a required scanner refusal. Neither current test
failures nor the implementation alone define expected behavior.

## Correct the key-order test without losing coordinate coverage

The two sources `{"a":1,"b":1}` and `{"b":1,"a":1}` have the same canonical
node preorder and semantic values but different source spans and raw/snippet
hashes. Compare `path`, `kind`, `value`, `numeric_lexeme` and `children` for
semantic equivalence. Separately assert each source's exact key/value spans
and hashes against independently counted offsets and legacy snippet helpers.
Do not compare their entire span-bearing node arrays for equality or discard
source-coordinate testing.

## Bounded correction workflow

Generate `static-vectors-r3.json` and its correction report as new evidence
artifacts without importing the new parser. Keep all seven positive sources,
the existing 31 negative sources and both supplementary groups unchanged; add
only the short tuple-exponent refusal. Independently audit declaration attribution
and completeness, not just whether a selected substring hashes to its recorded
value. The source and test paths stay stopped while that review is pending.

After a separate exact amendment and review, a small test integration change
may consume the corrected fixture and error-context rules above. Any actual
production defect found by independent review still goes back to Grok Build.
No fixture or test correction constitutes CONFIG, public CODE, Git or CI
acceptance.
