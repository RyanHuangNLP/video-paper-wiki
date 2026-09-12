# Resource negative-case planning corrections — R3

This is an Architect planning correction to
`public-resource-negative-cases-r2.json` (SHA-256
`9c7248fb31ccbb4c9a94c30bccf847d1b414e038d8114cad9defe5db51728006`).
Preserve R1 and R2. These corrections supply no runtime test result or public
CODE acceptance; apply them when authoring the future resource/semantic tests.

The reseal/rebind protocol must preserve the deliberately broken field. Start
with a valid dependency set, apply one mutation, then recompute only the other
IDs, saved-byte hashes and containing/consumer references needed to isolate that
mutation. Never repair the target fault in the course of resealing. Select the
target field explicitly before generating each case and assert it remains wrong
immediately before validation.

- NEG-009 changes a normalized present target's `text` to null. The present
  target has no `reason` field; the instruction to leave `reason` null was
  incorrect. Keep its other existing fields unchanged and add no `reason`.
- NEG-021 keeps the deliberately wrong Ref `sha256`. Recompute the containing
  config envelope's ce1 ID and complete saved-byte hash, then update consumers
  of that config. Do not restore the corrupted Ref from the referenced file.
- NEG-022 keeps the deliberately wrong request envelope `id` while retaining
  its schema, kind and data. Do not reseal that request ID. Compute the actual
  saved-byte hash of the invalid request and update its consumers to those
  saved bytes and the intentionally wrong ID, isolating the request's own ID
  derivation failure from incidental stale consumer references.

These are semantic-rejection vectors only where R2 labels them so. The actual
public implementation must later establish the final error code and precedence;
schema preparation alone cannot claim that replay passed.
