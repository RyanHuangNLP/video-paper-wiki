# VPKB-000-projection-contracts — architecture review

Parent VPKB-000. Status: in progress. Runtime comparison and ledger locator
revision 1 are separately frozen. Complete canonical inputs/history, SQLite
and generation remain under architecture review. Only the two bounded slices
specified below are released.
Predecessor: VPKB-000-transaction-facade, accepted at
`5f4c186566c15ab5ee8df10c587e4709d6223f32`; this is the packet baseline.
CI run 33426054898 attempt 1 tested merge preview
`8eba91629628058614ec7cd8a88dab501c567be7`, all four jobs passing 1239 tests.
Historical evidence remains separate in the predecessor verification directory.
Architect/Builder/Steward retain the existing model and ownership arrangement.

## Runtime comparison implementation release

Architect froze [projection-runtime-v1](../contracts/projection-runtime-v1.md)
revision 1 after both medium agents independently reviewed the exact numeric
domain, budgets, error ordering and actual pinned emitter profiles. SHA-256:
`e72531c11bb7cfdee2c5d73bc51006edaa6d7226f091c7008ea03d77a52411dc`.
Steward additionally checked five real chunks and a five-document/79-term BM25
fixture against the draft. This is design evidence, not implementation acceptance.

Builder owns only these implementation paths for the released runtime slice:

- `src/video_paper_wiki/projection_runtime.py`;
- `src/video_paper_wiki/contracts.py`, only new-profile dispatch/registration;
- `schemas/video-paper-wiki.upstream-chunk-profile.v1.schema.json` and
  `schemas/video-paper-wiki.upstream-bm25-profile.v1.schema.json`;
- `tests/test_projection_runtime.py`, `tests/test_projection_runtime_upstream.py`
  and `tests/fixtures/projection-runtime/**`;
- minimal existing schema-count/packaging assertions required by the new
  resources, with every affected path identified in handoff.
- Bounded test-policy correction after full-suite attempt 1:
  `tests/unit/test_search.py`, a narrow test-only scope helper and its regression
  tests. The historical blanket `bm25` substring ban must recognize the two
  explicitly released pure profile/dispatch source files while continuing to
  reject retrieval gold and unapproved engine/tokenizer/build/query capability.
  Do not rename production contract strings to evade the old test or remove
  CLI/network/Vault protections. Every added helper path must be named in handoff.

Do not alter existing identity/JCS/receipt semantics, the central schemas'
existing error behavior, upstream files, package dependencies or security
boundaries. Public pinned CLI tests may use disposable temporary Vaults with
synthetic prefixes; no production builder, admin install or real Vault use.
No Git mutations by Builder. Steward owns independent verification and later
serialized Git only on an explicit candidate instruction.
Architect owns normative contracts and task/team/packet metadata. Report a
contract gap before changing frozen behavior; unaffected work can continue.

Required runtime evidence is specified in the frozen contract: exact independent
vectors, resource/error regressions, byte stability and public CJK/build/query
fixtures, unchanged identity goldens, complete local suites and installed wheel,
then candidate-bound CI. Evidence belongs under
`artifacts/verification/VPKB-000-projection-contracts/` when ready. This release
is a dependency within the whole projection packet, not completion of it.

Runtime full-suite attempt 1 used 281 source inputs, SHA-256
`8493064d7490511bffef198c5a8740740964855928480da2df7cf24ddb47a671`.
Python 3.12.14 and 3.13.13 each reported 1322 passes and one failure, zero
errors/skips: `test_no_retrieval_gold_or_bm25_added` still globally prohibited
the now-required BM25 schema terminology. Source files were unchanged by both
runs. The same source's isolated 18-schema wheel smoke passed, which does not
turn either failed full suite into a pass. Preserve this evidence separately;
the scoped policy correction requires a new source snapshot and full rerun.

The corrected runtime candidate passed that new full local acceptance:
Python 3.12.14 and 3.13.13 each passed 1357 tests, no failures/errors/skips.
The 283-file source snapshot is
`f655b80ae32c6ea1c78b65f5e5f68c3b1e5cbdfe455a1e9fda6e5750cb22a2a8`,
unchanged before/after both suites and fresh offline wheel acceptance. The
isolated installed wheel loads 18 schemas and passes all new numeric/profile
checks plus prior identity/locator/facade smoke checks. Only three test-policy
files changed after the first full attempt; all eight runtime implementation
and fixture files retained their independently reviewed hashes. The test-only
scope helper's limitations are explicit; CLI/runtime/network protections remain.
At that local observation, new-commit CI and Architect's exact-commit decision
were pending. The later runtime acceptance below does not rewrite that evidence
or accept the full projection packet.

Architect subsequently accepted the runtime slice at
`208c206801214bb8f6e2f58f995ad7755ce87332`, parent equal to the packet baseline.
All 283 source and 72 delivery inputs (343 unique paths) matched their reviewed
Git blobs. CI run 33431642237 attempt 1 passed all four jobs, each 1357 tests:
99618144096, 99618144182, 99618144355, 99618144439. Actual checkout was
`1776de9b413d21471ccf2717910d10dbadb39ba6`, whose parents were independently
verified as integration `08709894adfb20ec07e976783f0ba436d975b74f` and that head.
CI Python versions were 3.12.14 and 3.13.15; local versions remain 3.12.14 and
3.13.13. Exact observation, parent check and later decision are separate
`runtime-ci-observation.json`, `runtime-merge-parents.json` and
`runtime-architect-acceptance.json` files in this packet's evidence directory.
PR94 remains open/draft; merge and human gates are unchanged.

## Ledger locator implementation release

The [ledger locator wire contract](../contracts/ledger-locator-v1.md), revision 1,
is the sole normative codec specification. Builder and Steward reviewed its
exact wire/numeric/limit/error semantics against common.v1, identity/JCS,
runtime preflight and the pinned public-CLI r2 transport proof. This releases
four pure supplied-data APIs, not the whole input snapshot or a new ledger.
Slice baseline is `208c206801214bb8f6e2f58f995ad7755ce87332`.

Builder owns only:

- `src/video_paper_wiki/ledger_locator.py`;
- `tests/test_ledger_locator.py`;
- `tests/test_ledger_locator_upstream.py`;
- `tests/fixtures/ledger-locator/**`.

No new root schema registration is needed for the internal wire envelope.
Do not change existing common/identity/JCS/runtime/facade behavior, dependencies,
upstream sources or test guards. Reuse existing project helpers where appropriate;
report an actual contract gap before expanding ownership. Tests may use the
existing pinned disposable public-CLI fixture helper, including its narrowly
isolated stable_source_id subprocess; production codec must not import upstream.
No real Vault, admin, models, network-producing command or Git mutation by Builder.
Root owns contracts/task/packet docs; Steward owns independent vectors/review
and later serialized evidence/Git delivery on an exact candidate instruction.

Required evidence includes the full frozen contract's wire/hash vectors,
representability and resource refusals, mutation/isolation checks, old identity
goldens and public transport replay. Builder returns exact changed-file hashes,
targeted results and remaining issues, then stops writing for independent review.
Architect runs full supported-Python and installed-wheel acceptance; new source
requires its own commit/CI rather than inheriting the accepted runtime run.

The four-file implementation candidate now passed full local verification on
288 fixed source inputs, SHA-256
`b689ce10e8325ee430b9a893bf5da54a9f6a2f69b59d2e4dedbb76dca7e30fed`.
Python 3.12.14 and 3.13.13 each passed 1464 tests, no failures/errors/skips.
Fresh offline wheel build/install and isolated smoke passed with 18 schemas,
all prior smoke checks and the Steward's independently prepared 10 positive
locator wire/hash vectors, 21 negative wires and all three relation mappings.
Wheel SHA-256:
`b3aeded7505f67e6eb7c205c38afdb2d843be1fe9c386e9f8e4a5666cf8bd4ed`.
All source hashes remained equal before/after both suites and wheel checks.
Candidate commit/CI and the separate exact-commit decision are still pending;
these local observations belong to `ledger-locator/` evidence, not runtime CI.

The implementation review clarified the existing error boundary without changing
the frozen contract: encode-evidence locator-field preflight failures retain
locator errors/flat pointers; root container/key or relation failures are outer
evidence errors. Decode-evidence outer value/type errors precede decoding;
inner wire errors retain locator codes/envelope pointers. Resource refusals
always retain PROJECTION_LIMIT_EXCEEDED. Regression tests cover both layers.

Remaining architecture drafts, not implementation releases:
[canonical input/locator](../contracts/projection-input-v1.md) and
[catalog/export/generation](../contracts/projection-catalog-v1.md). Both agents
reviewed the complete locator wire section; the whole input and catalog
contracts still need the exact inventory/path/closure/DDL decisions. Draft 2
withdraws the mutable assessment-head registry: validate the complete immutable
event graph and derive its unique terminal, without changing facade create-only
rules. The standalone locator release does not validate coordinates or inventory.

This is the remaining shared projection contract work, not an alternate path
around facade acceptance. The complete VPKB-000 milestone also needs dependency
and licensed-source evidence; neither a successful facade nor this planning
note closes it. No retrieval-config/gold, candidate depths, exact evidence join,
runtime index writer, real Vault, parser models or human gate belongs here.

## Requirements that must become exact before implementation

- catalog.sqlite base DDL, every PK/FK, deterministic ordering and a versioned
  canonical row export. Compare logical rows, not physical SQLite file bytes.
  Canonical records/ledgers/review heads/taxonomy/immutable manifests supply
  facts; Markdown/chunk text may not supply missing canonical facts.
- A projection-generation fingerprint and stale comparison with explicit input
  inventory and version material. A missing or invalid canonical input is a
  refusal, not a value silently omitted from the digest. Runtime results and
  wall-clock index-build time are not business truth.
- An exact versioned runtime comparator with JSON-pointer volatile allowlists,
  plus strict rejection/retention rules for unexpected fields. Do not recursively
  delete every field whose name looks like a timestamp. Markdown is byte-stable
  and receives no volatile-field exclusions at all.
- Pinned upstream chunk and BM25 schema observations and public-CLI CJK
  tokenization/build/query fixtures; do not implement another tokenizer or add
  extension fields to upstream objects. Preserve overlap chunks and identity;
  later VPKB-001 maps them to canonical evidence units separately.
- Projection compatibility fields from transaction-facade revision 1: constant
  status=generated, canonical UTC date aliases and taxonomy-derived sorted tags.
  They are derived presentation fields, not ingestion/review/gate state.

## Initial pinned-source observations (not behavior acceptance)

These observations refer only to commit
`9f8c1199047eac2c3828496279fbb7ba9540b90b`. Architect read the actual emitted
objects as well as the introductory documentation; they are not always equal.

- `scripts/contextual-prefix.py:787` emits chunk schema_version=1 with
  page_path, page_address, chunk_index, raw_text, contextualized_text, **prefix**,
  prefix_source, char_count, body_hash, page_body_hash and created_at. The file's
  introductory schema example omits prefix, so it must not be used alone to
  freeze a closed schema. The candidate volatile pointer is exactly /created_at.
- `scripts/bm25-index.py:537` emits index schema_version=2 with params,
  doc_count, avg_dl, updated_at, vocab and docs. Its actual docs entries also
  contain body_hash/page_body_hash (`:519`), omitted in the introductory example.
  The candidate volatile pointer is exactly /updated_at at the index root.
- The index stores relative chunk paths, not absolute Vault paths. Public
  retrieve output may contain absolute_path and is a different contract; do not
  treat that response as the index object or add it to a broad comparator.
- Existing `video_paper_wiki.jcs` is intentionally integer-only, while genuine
  BM25 output contains fractional params/avg_dl. The runtime comparator must
  freeze finite-number serialization/equality explicitly; sending these objects
  to the current identity JCS would fail. Do not silently broaden that existing
  authority or discard numeric fields to make a comparator pass.
- The pinned index validator allows some values more broadly than its current
  emitter. Decide whether a comparator accepts emitter output only or legacy
  valid index variants, with fixtures and explicit error codes. Do not silently
  claim that extension validation is the upstream validator.
- `tokenize` at bm25-index.py:333 uses bounded NFKC/token growth rules. Public
  build/query fixtures must demonstrate the exact CJK terms and compatibility;
  static description alone is not a passing tokenizer contract.

Before each remaining implementation release, Architect supplies its complete
versioned normative document,
Builder and Steward independently review it, and packet/schema/API ownership,
fixtures and acceptance evidence paths are assigned. Do not start production
rendering or SQLite file mutation from this preparation note.
