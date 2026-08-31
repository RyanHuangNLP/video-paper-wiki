# Projection contract verification evidence

This directory records independent focused review, earlier locator feasibility
investigations, the failed first full-suite attempt and successful corrected
local verification. Those historical records are not candidate-CI acceptance;
the later runtime-only CI and Architect decision are separate files described
below. VPKB-000, the complete projection packet, VPKB-001 and human gates remain open.

`independent-results.json` records the exact eight reviewed runtime file hashes,
frozen runtime revision 1 hash, commands, process exit and normalization digests.
Baseline HEAD is `5f4c186566c15ab5ee8df10c587e4709d6223f32`; the source review
was of a working-tree candidate, not a new commit. Focused pytest passed 138
with no failures/errors/skips. Its original JUnit digest and counts are retained;
the raw XML is omitted to avoid publishing unnecessary personal hostname data.
Later full-suite/wheel/CI results must be recorded separately.

`failed-attempt1/archive-results.json` preserves the first complete runs: Python
3.12 and 3.13 each passed 1322 tests and failed one, with zero errors/skips and
exit 1. The legacy search test rejected the authorized pure comparison profile
by a global `bm25` substring ban. Both 281-file source observations matched
snapshot `8493064d7490511bffef198c5a8740740964855928480da2df7cf24ddb47a671`.
The wheel build/install/smoke independently passed against that historical
snapshot with 18 schemas; it does not turn either failed suite into a pass.
All original temporary attempt files remain unchanged. Normalized result/log/
script copies retain separate raw and normalized digests; raw JUnit is omitted
while its digest and counts are preserved. Any guard fix requires new source
evidence and fresh verification, not relabelling these observations.

`independent-review.json` and its normalized prototype preserve 14 independent
numeric byte/hash vectors, 1000 exact occurrence-budget JSON probes, the prior
accepted five-chunk/five-document fixture, source hashes before/after, and
independent inspection of the new public CLI artifacts. Both prior findings
were resolved: `wiki/.md` is accepted and deep pointer construction retains
exact diagnostics without repeatedly copying full ancestor strings. The bounded
pointer probe fell from 8,793,713 to 554,513 traced peak bytes. This is one
measurement, not a universal memory bound; error pointers remain untruncated.

`number-vectors.json`, the number prototype and design review are historical
pre-freeze observations, explicitly marked review-only. Their comparator wrapper
and values agree with the separately frozen runtime contract. They do not
redefine that contract or broaden identity JCS. PDF fractional bbox validation
and fingerprint preservation were checked separately; bbox is intentionally
excluded from the existing evidence fingerprint.

`runtime-public-observation.json` and its command records preserve two actual
pinned public CLI rebuilds: ten commands exited 0, Markdown stayed byte stable,
all chunk/BM25 projections compared equal, CJK vocabulary contained the nine
specified terms, ASCII/fullwidth NFKC queries agreed and overlapping chunks
retained their identities. Each round's raw artifact digests are retained.
The committed test source is the replay authority; the original temporary Vault
is not copied. A new run has new observation times and must not be labelled the
historical run. Before/after upstream inventories match the shared 201-file
`upstream-source-inventory.json` at pin
`9f8c1199047eac2c3828496279fbb7ba9540b90b`.

The `locator-r1-*` files preserve the first public ledger transport experiment
unchanged in meaning: its PDF artifact path pointed into `.raw/captured/`, so
it did **not** satisfy the project's common PDF locator grammar. It also lacked
the later required envelope discriminator. Its passing upstream transport result
must never be labelled acceptance of a complete project locator.

The separate `locator-r2-*` files correct those limitations: common.v1 PDF
shape was checked with JSON Schema Resource/Registry before public CLI execution,
using `.raw/derived/fixture-pdf/docling/fp/document.json` and the exact
`video-paper-wiki.ledger-locator.v1` envelope discriminator. Artifact/text hashes
refer to explicit synthetic fixture bytes; the fake derived artifact remains
outside the disposable Vault. The experiment proves canonical ledger string
preservation and numeric locator round-trip, not genuine extraction coordinates,
artifact-inventory closure or a production codec. Both runs made nine calls:
eight exited 0 and the wire relation `uncertain` produced one expected exit-2
`INVALID_PROVENANCE_LEDGER` refusal. Otherwise identical `supports` and `context`
controls passed; project `uncertain` is transported explicitly as upstream
`context`. No extra upstream property or second ledger was introduced.

The locator input contract is **not frozen or released** by these experiments.
The whole-snapshot input, history, SQLite and generation contracts require their
own review and release. No full record, receipt/head, prospective workflow,
real Vault, admin install, model or scientific/human acceptance is asserted.

Normalized files replace the absolute repository root with `<REPOSITORY>` and
`/private/tmp` with `<TEMP_ROOT>`, remove per-line trailing ASCII spaces/tabs,
and use one final LF. Numeric contents are not rounded or otherwise changed.
Original raw and archived normalized digests are distinct. Enriched command
records additionally contain raw stdout/stderr digests; they are not verbatim
copies of the original command JSON. Exact original source inventories retain
their relative paths and byte hashes.

The `*.normalized.py.txt` files are preserved review sources, not directly
executable scripts and not the bytes originally run. To replay, save a copy as
Python, substitute a checkout, interpreter and fresh disposable directories,
and prepare the referenced fixture/input files at the script's expected paths.
Follow the repository's pinned-submodule/default-environment test instructions;
never download during pytest or reuse a real Vault. A replay produces new
evidence and must retain its own source/command/output digests.

`corrected-guard-review/review-results.json` records the separate independent
review of the three test-only guard changes. The original eight runtime files
are unchanged. The old global marker check now admits only the two released
pure comparison/dispatch paths and still checks those files for ordinary AST
engine, tokenizer, I/O and upstream imports/calls. No blanket file skip or
string hiding was introduced; all other source BM25 and global retrieval-gold
restrictions remain. This static check does not prove arbitrary Python dataflow
or OS isolation. Independent refusal probes and focused tests passed; final
full-suite results for the corrected source must be recorded separately.

`final-local/local-results.json` records the corrected final local source:
283 files, snapshot
`f655b80ae32c6ea1c78b65f5e5f68c3b1e5cbdfe455a1e9fda6e5750cb22a2a8`.
Python 3.12.14 passed all 1357 tests in 79.56 seconds; Python 3.13.13 passed
all 1357 in 76.41 seconds. Both exited 0 with no failures/errors/skips and
matching complete before/after source maps. Fresh offline wheel build, install
and smoke all exited 0: 18 schemas, prior identity/facade checks, 14 numeric
vectors and supplied bytes from eight actual chunks/eight BM25 documents.
Wheel SHA-256 is
`f211069babac8f9de74d895bf0e0f3887fada9f9c3e42dd12a878816bd94ea43`,
unchanged because the correction touched tests only. These records include
actual command/result/log/source hashes and normalized replay source; they do
not inherit a remote CI result or identify a not-yet-created commit. Candidate
head/base/actual checkout CI and Architect acceptance need separate evidence.

Later runtime-only acceptance is now recorded separately in
`runtime-ci-observation.json`, `runtime-merge-parents.json` and
`runtime-architect-acceptance.json`. Candidate
`208c206801214bb8f6e2f58f995ad7755ce87332` passed CI run 33431642237 attempt 1:
all four Linux/macOS and Python 3.12/3.13 jobs passed 1357 tests. Every job
actually checked out merge `1776de9b413d21471ccf2717910d10dbadb39ba6`; a read-only
GitHub parent query independently bound it to the recorded head and integration
base. CI's Python 3.13.15 is distinct from local 3.13.13. The observation's
pending-Architect flag is preserved; the separate decision records acceptance.
This does not accept the subsequent locator code, other architecture drafts,
complete projection packet, VPKB-000, production adapters or human gates.

The subsequent `ledger-locator/` directory records a separate pure-codec
candidate based on that accepted runtime commit. Its frozen contract is
`docs/ai/contracts/ledger-locator-v1.md` revision 1. The four new implementation
and test files passed Builder's 242 targeted checks, independent Steward review
with 54 boundary probes and 130 focused tests, and Architect's full local
Python 3.12.14/3.13.13 suites: 1464 passes each, no failures/errors/skips.
The 288-source snapshot is
`b689ce10e8325ee430b9a893bf5da54a9f6a2f69b59d2e4dedbb76dca7e30fed`.
Fresh offline wheel/build/install smoke passed with 18 schemas and the
independently prepared 10 positive/21 negative wire vectors plus all three
relations. Source bytes matched before/after every final check. Public fixture
transport uses synthetic metadata and proves neither genuine extraction nor
artifact/receipt/record closure. The local candidate still requires its own
new-commit CI and exact-commit acceptance; the previous runtime run is separate.

`dependency-source/` contains a bounded observation of the lock's docling
2.117.0, docling-slim 2.117.0 and docling-core 2.92.0 distributions and the
existing vendor pin. Archive SHA/size and license declarations were checked;
the metadata-only docling wheel/sdist has no separate LICENSE, whereas slim
and core supply one. Do not interpret a missing member as an invented license
file or the metadata's MIT declaration as permission for all models/dependencies.
The original dependency manifest remains `pinned`. No parser was installed,
imported or executed; no model or transitive package was fetched. Exact source
Git provenance, model/transitive license coverage and legal compliance are not
established. Downloaded package archives and selected read-only source extracts
remain outside the repository; their hashes/member paths allow later replay.
