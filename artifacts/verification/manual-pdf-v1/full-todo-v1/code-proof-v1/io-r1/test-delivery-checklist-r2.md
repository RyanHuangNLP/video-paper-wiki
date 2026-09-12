# CODE I/O R2 test-delivery acceptance checklist

This checklist prepares the later separate test-only delivery for
`GROK-CODE-PROOF-IO-PRODUCTION-R2.md` (56,306 bytes,
SHA-256 `bec8fe545d55804ccdcfd867a58776fd1b53515e93e2b5535867f6f4f495e0ca`).
It is based on `architect-production-rejection-r1.json`, the independent R1
review, and the R2 supplement. The production module is reviewed separately.

The later response must contain one complete `tests/unit/test_code_proof_io.py`
pytest module in one Python fence, followed by `Tests not run.` It must contain
no production source, patch, fixture implementation, extra prose, or second
module. The integrator checks fence extraction, UTF-8 decoding, AST parsing,
path/name, and byte-preserving extraction before running it.

## Test boundary

- Use short isolated temporary trees and the locked Python environments. Copy
  the actual eleven accepted resource bytes and exercise genuine compilation in
  both source and installed lexical layouts. Do not replace pins, compiler,
  registry, validator, foundation origin selector, or global `os`/`fcntl`
  functions. Patching the private module syscall seams and the foundation
  module `__file__` is allowed only for the specified bounded cases.
- Do not touch the real checkout, tracked resources, Vault, Git state, or old
  evidence. Use a still-live original inode for replacement fixtures so the
  result does not rely on unlink/recreate inode behavior.
- Keep tests finite and behavior-focused. Each case should assert the public
  private-session result, exact facade class/code/details/message where required,
  and the relevant durable filesystem observation. Do not add tests that weaken
  first observations, pins, payload checks, zero-egress, or cleanup rules.

## Lifecycle, authority, and public session operations

Contract pointers: production instruction §§ Existing foundation interface and
Private session interface and lifetime (lines 136–224), private argument domains
(lines 228–260), and primitive checks (lines 262–302).

- Cover `open_code_session(*, batch_id)` setup, active yield, finalization, and
  closed lifetime. A valid checkout with no `.work`, absent batch, or absent
  namespace must yield an empty `snapshot()`, permit `verify()`, create no
  directory, and close cleanly. A later arrival must refuse.
- Cover exact batch/root/marker rules, unchanged CWD authority after setup,
  inactive wrappers for `snapshot`, `layout_state`, `retain_input`, `retain_bundle_manifest`, `retain_bundle_bodies`,
  `set_output_limits`, `install`, `verify`, `validate_structure`,
  `materialize_limits`, and `profile_sha256`.
- Cover capability preflight for each missing primitive, lock busy and
  unsupported/other errno classes, checkout directory fsync failure, failed
  duplicate, and failed close. Assert bounded codes and that all applicable
  descriptors are still attempted once.
- Cover the exact type/order domains for `retain_input`, `install`,
  `retain_bundle_manifest`, `retain_bundle_bodies`, `set_output_limits`, and
  `materialize_limits`, including
  hostile subclasses and conversion/length/hash hooks without evaluating them.

## Retained graph, scans, resources, and ordinary input

Contract pointers: concrete failures 1, 2, and 4 (lines 35–71), authority graph
and observations (lines 302–356), and fixed output layout/scans (lines 358–404).

- Cover initial empty/absent namespace and family distinctions; cap-plus-one
  enumeration, enumeration/stat failures, unknown and unsafe entries, all four
  direct absent slots, and family presence/absence. A failed or partial scan
  must not become a successful partial snapshot.
- Reproduce every known scan regression: late foreign namespace entry, late
  `request.json`, and late object-family body. Reproduce the newly installed
  file mutation after first installation; `snapshot`, `verify`, and context exit
  must refuse rather than return retained old bytes.
- Cover retained input with successful read, same-fd byte change, named stamp
  change, replaced/missing ancestor, failed read, and persistent inode
  replacement during the failed read. The persistent replacement selects
  `WORK_PATH_UNSAFE` over the original read error even if no input bytes were
  published. Cover lexical/type/overlap and descriptor-identity alias refusals.
- Cover genuine eleven-resource acquisition with initial absence, unsafe state,
  partial read/open/fstat failure, same-fd content/stamp change, pin/hash/shape
  failure, and missing/replaced resource during final reread. An unchanged
  initial resource refusal may remain `CODE_PROOF_RESOURCE_INVALID`; any later
  persistent missing or uncheckable lineage must select `WORK_PATH_UNSAFE`.
  After final cleanup, assert compiled context, plan, records/bytes, and graph
  authority references are cleared while closed-session guards remain bounded.

## Raw bundle and Git adapter

Contract pointers: ordinary/raw inputs (lines 406–548), concrete failure 3
(lines 57–62), and the separate raw reconciliation order (lines 480–548).

- Cover exact `.work/` spelling, Unicode/NFC/control/boundary rules, output
  overlap, raw-root complete set, and no body reads during manifest capture.
  Reproduce a third raw-root entry after capture and replacement of the named
  `objects` directory while the original remains live; both must be lineage
  refusals.
- Cover the closed five-key inventory record shape before indexing: extra keys,
  hostile keys/values, wrong primitive types, duplicate OIDs, and non-ascending
  OIDs must refuse before any body open. Bodies that pass must be opened/read in
  strict OID order and returned as an independent byte mapping.
- Exercise reconciliation precedence with physical count cap, opposite-width
  OID plus extra, extra plus missing, stable missing, and invalid-layout names.
  Assert the exact existing `CodeGitProofError` class, literal message, details,
  pointer, and exit code for the three stable adapter outcomes; assert zero body
  opens on pre-body refusals.
- Cover lowered values for all five incoming Git limits, including count,
  per-body, and aggregate byte caps, while preserving the full map for the later
  pure Git kernel. Assert `/objects`, `/bodies`, and indexed body pointers as
  applicable.

## Output limits and installation

Contract pointers: output limit setter and file installation (lines 551–640),
concrete failures 5–7 (lines 73–100), and the phase clarification in concrete
failure 6.

- Cover `set_output_limits` once, twice, before/after retained manifest/files,
  exact seven-key shape/type/bounds, already-over-limit retained content, and
  install-before-set. A 65,537-byte retained `request.json` must report
  `/output`, `max_request_bytes`, `65536`, and `65537`; exercise analogous file
  and family pointers plus the independent C+2*N peak rule.
- Cover fresh install, initially identical reuse, stable conflict, late equal
  arrival, every C+2*N boundary, lazy directory creation, and each mkdir
  post-effect outcome. A newly created file is part of all later name/fd/byte
  checks while the original absence remains immutable.
- Cover short, zero, and failed writes; file and directory fsync failures; link
  failure before and after effect; unlink failure before and after effect; temp
  replacement before cleanup; foreign final/temp preservation; and verified
  cleaned-prefix behavior. Assert no unverified path is adopted, replaced, or
  deleted.
- Cover fresh installer state after one successful file and a failed second
  installation. The second owned temporary gets checked cleanup, the first
  cleaned prefix cannot suppress the refusal, and no temporary is left when
  ownership is provably retained.
- Cover failed/in-flight view and install guards. A failure before creation
  keeps the actual pre-creation phase plus an explicit failed flag; a later
  reached phase is never relabelled `idle` after failure. `snapshot()` and
  `layout_state()` refuse until finalization; `idle` is reached only after
  durable success. Instrument bounded full-reread counts under short writes.

## Finalizer, precedence, and safe facade

Contract pointers: verification cadence and cleanup (lines 642–706), safe error
facade and bounded contexts (lines 707–813), and concrete failures 9–11 (lines
105–127).

- Cause multiple reached groups to fail and prove every reached group is
  attempted in fixed order, including the final names/set sweep. Assert first
  persistent lineage group precedence, deterministic unique `failed_groups`,
  cleanup precedence only when lineage is intact, and no semantic error becomes
  success.
- Inject an unexpected exception and an interruption into one group verifier.
  Later groups, checked owned-temp cleanup, and every descriptor close still run;
  the original `BaseException` object is preserved when no higher-priority
  lineage failure exists.
- Assert reverse descriptor closure exactly once with the duplicated checkout
  lock last. Assert no retry occurs after a failed close and no stale active
  graph/resource container remains after closed state.
- Exercise unknown prior exceptions and `.code`, `.details`, or nested metadata
  getters that raise. The selected final bounded error must survive; prior fields
  use only recognized exact builtin values and otherwise become null. Assert
  fixed messages, nine-field facade shapes, independent detail copies, exact
  limits/conflict shapes, and no raw path/message/adversarial marker in
  traceback or formatted details.

## Delivery acceptance

- Confirm the test response is complete, syntactically valid, scoped to
  `tests/unit/test_code_proof_io.py`, and contains no product implementation.
- Run the finite focused module on both locked Python versions, then run the
  repository suite and isolated wheel import as separately recorded evidence.
  Keep local results, CI results, source acceptance, and later human gates
  distinct. A passing test module does not accept or merge the production
  candidate by itself.
