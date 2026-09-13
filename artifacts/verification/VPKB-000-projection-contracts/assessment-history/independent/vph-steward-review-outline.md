# Independent assessment history review plan

Frozen revision 1: ff7e7830d9931c52c447a2a95818dca091cb6d5bc97184d1be1103072ecf44cb.
Baseline: 3e2bebb1d50928a7af95e07b4868bdbe8113cd0b.
This preparation has not imported, read or executed Builder's history module.
Expected output is derived from the frozen specification and independent stdlib
identity formulas; existing identity/schema are secondary consistency controls.

## Fixed expected values

`vph-steward-vectors.json` contains full inputs, exact claim/event IDs, raw text
hashes, fingerprints and sorted expected head maps for 29 positive cases, and
38 specific negative cases. `vph-steward-build-vectors.py` imports only stdlib.
All hashed map keys are ASCII, so stdlib sorted compact UTF-8 JSON agrees with
JCS UTF-16 key ordering; no float enters hashed identity material. Evidence
fields are explicitly selected, repository casefolded, lists sorted by canonical
bytes without deduplication. Claim text uses NFKC + whitespace collapse for ID
and its original UTF-8 bytes for event text hash. Bbox/charspan/symbol are display
fields excluded from the fingerprint, but must still fully validate.

Positive coverage includes empty input/evidence, paper and repo subjects,
complete shuffled multi-claim coverage, all 16 allowed non-no-op human state
edges, system provisional-to-provisional changed-FP invalidation, old and
returned fingerprints, equal/decreasing/fractional times, years 0001/9999,
Unicode text/bbox, evidence order and duplicates, display changes, exact 65536
byte ASCII/multibyte text and an 801-event chain. Returned head dict order must
be ASCII claim-ID order regardless of input order.

Negatives isolate coverage, fork/dangling/cross-owner graph, state transitions,
human no-op, human FP changes, unchanged-FP invalidation, current FP mismatch,
evidence relation/duplicate changes, raw-text mismatch despite equivalent claim
identity, duplicate/colliding stated claim bindings, wrong event/claim hashes,
wrong materialized assessment/date, UTC/date failures, concept subject, locator
strict types/fullmatch/relations and 65537-byte text. Re-sign mutated terminal
events where needed to reach the intended relationship check; never re-sign
with the tested API. The duplicate stated-ID collision is conflicting supplied
bindings under specified priority, not discovery of a genuine hash collision.

## Honest graph and resource adversaries

A cyclic graph cannot practically have genuinely self-consistent truncated event
IDs without solving fixed points. The end-to-end synthetic-cycle vector retains
invalid IDs and expects identity refusal. Separately exercise the real graph
routine with synthetic IDs or a tightly isolated identity stub and label that
result; do not bypass production checks or call it valid persisted evidence.

`vph-steward-runtime-cases.py` defers Python-only hostile values/subclasses,
non-string keys, surrogate/non-finite values, ancestor cycles, exact depth64 vs65,
2049-bit coordinates and repeated-alias occurrence overflow. These factories do
not invoke the pending API. Verify the virtual root and both keys are charged.
Finite bbox floats remain valid, bool/int subclasses never substitute for int.
Do not allocate 64MiB multibyte adversaries just to trigger expansion; inspect
character-before-UTF8 checks and use narrow small-budget probes if necessary.

## Stable implementation review

1. Record frozen contract and three candidate path hashes before/after. Verify
   all previous 288 accepted source bytes unchanged, no identity/JCS/schema,
   codec/runtime/dependency/CLI/upstream edits. Status/new draft files are not
   part of the old source snapshot and must not be mistaken for drift.
2. Run fixed vectors first; validate returned complete heads and insertion order,
   then reverse claim/event order for positives. Check errors are ContractError,
   expected code/exit, safe pointer, no raw text/reason/repr disclosure. Do not
   invent a global priority among unrelated faults.
3. Verify all claim shapes before duplicate material comparison and before
   individual claimed-ID mismatch; full evidence codec validation precedes FP.
   Resource preflight always first; resource code retained, non-JSON value error
   becomes SCHEMA_INVALID, inner codec pointer receives claims/evidence prefix.
4. Graph must prove one genesis, same-claim existing parents, no fork/cycle,
   connected complete traversal and one terminal. Traverse iteratively; avoid
   O(n^2) repeated scans over long chains. Only terminal FP binds current data.
   Every event must bind exact original text; no-op restriction remains local.
5. Compare input deep snapshots after success and refusal; allowed shared aliases
   are not rejected solely for repeated identity. Output is a fresh dict and no
   mutable input is retained. Warming immutable schema cache is allowed; then
   block path/file I/O, processes, sockets and clock/environment queries as
   bounded independent probes. No real Vault/parser/model/runtime approval.
6. Existing identity, prospective and schema tests must retain behavior. Full
   dual-Python/wheel/new-candidate CI belongs to Architect acceptance, not this
   preimplementation preparation. Snapshot integrity, actor authorization,
   immutable raw event provenance, core replacement and publication checks are
   expressly outside this pure supplied-value slice.
