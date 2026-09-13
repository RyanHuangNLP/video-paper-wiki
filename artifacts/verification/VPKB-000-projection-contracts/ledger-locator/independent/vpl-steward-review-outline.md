# Independent ledger-locator review plan

Frozen contract revision 1 SHA256:
493fc3d135141512c7956f3729726ae72febbb1a34cc8cd5669add96af16e191.
Prepared before importing or evaluating Builder's ledger_locator module.
No repository, upstream, Git or public CLI mutation in this preparation.

## Independent fixed expectations

vpl-steward-vectors.json contains ten positive full-wire UTF8/SHA256 vectors,
expected decoded locators and three independently calculated evidence hashes,
plus 21 negative wire vectors. The generator uses only standard JSON over
fixed ASCII object keys (so code-point and UTF16 key sorting agree) and derives
binary64 ratios directly from IEEE754 bits, not as_integer_ratio/Builder output.
Existing identity.py, jcs.py and common schema byte hashes are recorded.

Positive cases: minimal PDF/code; PDF optional bbox+charspan; Unicode/whitespace/
quote/backslash ref and symbol; integer-valued floats and signed zero; 0.1,
minimum subnormal, largest finite float; signed 2048-bit integer coordinates;
and exact 65,536-byte ASCII and multibyte wires. Input coordinate values are
synthetic, not real extraction assertions. Compare the complete decoded
locator, not only the fingerprint (bbox and charspan are excluded from it).

Negative cases: LF/structural whitespace, alternate escaped solidus, different
key order, duplicate literal/escaped schema key, float/exponent page spelling,
65,537-byte ASCII and multibyte wires (the latter has fewer than 65,536 chars),
and malformed/unreduced/non-power-two/bool/float/negative-denominator ratios.
Exact ratio adversaries cover 2^-1075 underflow, (2^53+1)/2^53 rounding,
(2^2047-1)/2 overflow, 2049-bit budget and negative-zero JSON spelling.

## Implementation review after stable handoff

1. Verify every candidate file hash and frozen contract, record before/after;
   inspect exact allowed four-path implementation scope. Existing identity/JCS/
   common/upstream/dependencies must be byte unchanged. No broad runtime helper
   semantics change hidden in the locator implementation.
2. Execute all fixed vectors for encode/decode and all three evidence relations.
   Insert domain dictionaries in reverse order; canonical bytes must agree.
   Optional bbox absent remains absent; charspan and code symbol survive;
   integral-float and zero normalization is exactly the stated equivalence.
3. Test each common patterned field with trailing LF: source ID, code repo,
   commit, every hash, portable code path and derived artifact path. Reject
   captured path for PDF; reject unsafe source IDs, null optionals, unknown or
   missing keys, envelope relation, duplicate bbox, code bbox_rationals.
4. Exercise bool/float in page/lines/charspan/pair ints, all container/scalar
   subclasses, tuple/Decimal/Fraction, non-string keys, cyclic extra fields,
   hostile __str__/__repr__ and deeply invalid values. No custom formatting or
   raw TypeError/UnicodeError/OverflowError/RecursionError may escape.
5. Test 2048-bit input acceptance versus 2049-bit refusal, ancestor depth 64/65,
   shared acyclic lists counted again, wire exact bytes and Unicode boundary,
   raw string char guard before full UTF8 allocation. Use bounded probes or
   small-budget runtime helper controls for million-count/64MiB pathways;
   never run a multi-gigabyte adversarial allocation.
6. Copy/alias checks: two decode calls return distinct nested lists/maps; changing
   decoded charspan/bbox/lines never changes another result or original input.
   Encode does not delete bbox or relation from caller dictionaries. Shared
   acyclic original lists must not remain mutable aliases in returned output.
7. Warm immutable registry, then deny caller file/path open, subprocess and
   socket operations in-process. Supplied-data codecs still succeed/refuse
   appropriately; no upstream identity/private imports or fake authentication.
8. Re-run existing identity goldens and compare independent fingerprints.
   Reuse r2 public CLI transport evidence as control; a new full CLI replay is
   not needed during preparation. Required eventual implementation acceptance
   belongs to Architect's stable-candidate full-suite/wheel/CI procedure.

## Error ownership clarification from Architect

- encode_evidence: locator-field non-JSON preflight errors are
  LEDGER_LOCATOR_INVALID with flat pointer; invalid root container/object key
  or relation non-JSON errors are LEDGER_EVIDENCE_INVALID.
- decode_evidence: outer non-JSON/type failures before entering decode_locator
  are LEDGER_EVIDENCE_INVALID. Wire JSON/envelope/ratio failures after entering
  decode_locator are LEDGER_LOCATOR_INVALID and keep envelope-relative pointers.
- All resource failures retain PROJECTION_LIMIT_EXCEEDED.
- Direct encode locator pointer is domain-relative (/page, /lines/start).
  Decode common-field pointer is envelope-relative (/locator/page); ratio
  pointers identify /bbox_rationals/... . Raw wire/canonical spelling errors
  use empty pointer; do not invent character offsets inside a string.
- Missing or extra locator fields in flat encode_evidence are locator errors
  after valid relation; source mismatch is outer evidence error. Multiple
  independent faults in one phase do not require an invented total ordering.

Candidate execution has NOT run. These are independent expectations and review
requirements, not a statement that the implementation already passes them.
