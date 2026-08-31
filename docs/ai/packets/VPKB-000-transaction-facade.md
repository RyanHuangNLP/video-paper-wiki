# VPKB-000-transaction-facade

Parent: VPKB-000. Status: frozen revision 1; local acceptance passed, candidate CI pending.
Contract SHA-256: `a800f6aff5e1af839c112b1c4da1591c3081601da866b36af83755af8597ef67`.
Architect: Sol/Ultra; Builder and Repo Steward: Sol/Medium.
Predecessor: VPKB-000-capture-contracts, accepted at
`9d87dc67b949fc0cef5ac64b91a2d15aea8ec0fe`; its separate local/CI evidence is in
`artifacts/verification/VPKB-000-capture-contracts/`. This is also this packet's
baseline. Do not use this planning note as a frozen API or inherit predecessor
test results as acceptance of new code.

This packet gives CLI, receipt and audit one non-persistent transaction
representation. It may validate supplied mappings/bytes and compare declared
plans/results; it must not inspect/apply a real Vault or create another ledger.
Architect froze fields, phases, error codes and exact allowed paths before
Builder implemented it. No retrieval or production adapter work belongs here.

The frozen contract is `docs/ai/contracts/transaction-facade-v1.md`. It contains the
full proposed transaction/head fields, exact raw plan/result correspondence,
hash domains, path/permission/budget constraints, receipt/read/claim relations,
byte APIs, error codes and the domain policy/projection compatibility decision.
Builder and Steward reviewed it independently. The public-CLI compatibility
investigation r4 and independent steward1 replay each passed all three tracks,
including strict lint and actual retrieval. This releases only the pure APIs
and permanent compatibility fixtures below, not production Vault adaptation.

## Released ownership and acceptance

Builder owns only:

- `schemas/video-paper-wiki.transaction-facade.v1.schema.json` and
  `schemas/video-paper-wiki.operation-head.v1.schema.json` (new).
- `src/video_paper_wiki/transaction_contracts.py` (new), and minimal registration,
  title-scoped JSON preflight and dispatch in `src/video_paper_wiki/contracts.py`.
- `tests/unit/test_transaction_contracts.py`,
  `tests/contract/test_transaction_contracts.py`, corresponding new valid/invalid
  facade/head fixtures, and existing registry/schema-count assertions only.
- `tests/upstream/test_transaction_compatibility.py` and at most one same-folder
  helper. Port the reviewed public-CLI fixture with repo-relative discovery and
  short pytest temporary paths, no personal path or downloads. It must check the
  exact pinned Git/source/version before execution, preserve source inventory,
  fail clearly for a missing/dirty pin (never skip), use no LLM/reranker or
  private upstream execution API, and retain the fixture's explicit limitations.
- Acceptance fix: `tests/security/test_cli_isolation.py`,
  `tests/security/test_work_staging_boundary.py`, shared helper
  `tests/security/_source_policy.py`, and `tests/security/test_source_policy.py`.
  Replace only the network-library substring scans with AST import checks,
  including aliases, submodules, from-imports and dynamic import entrypoints.
  Preserve runtime network and Vault boundary checks. Regress both forbidden
  imports and legitimate schema text such as `address_requests`; do not hide
  the frozen field or mistake static checking for an OS security boundary.

Steward owns `.github/workflows/tests.yml`, the README's replay preparation
instructions, `tests/contract/test_transaction_independent.py` for independent
probes, and `artifacts/verification/VPKB-000-transaction-facade/**`. The CI change
is limited to explicit pinned submodule setup during the network-enabled setup
phase and its checks; pytest remains offline-ready and must never auto-fetch.
Steward remains the sole Git writer but needs a later exact staging/commit/push
instruction after source review. No merge or auto-merge is authorized.

Architect owns this packet, contract, task index and team handoff. No writer may
edit another owner's files without a named handoff. Common/identity/JCS, existing
canonical schemas, CLI implementations, dependency versions and the 67-entry
catalog remain unchanged. No Docling/models/admin installation or real Vault.

Acceptance is the complete frozen contract checklist, full Python 3.12/3.13
regressions, independent probes, portable upstream compatibility replay,
installed-wheel smoke and exact candidate/CI evidence. A fixture's three tracks
are not the count of the full unit suite, and fixture compatibility does not
complete VPKB-001. VPKB-000 still requires its other projection/SQLite/dependency
contracts after this subpacket.

The initial implementation acceptance attempt failed on both Python versions:
1162 passed and two security checks failed because their source-wide substring
scan classified `address_requests` as a network import. All 272 source inputs
were stable during those runs. Keep those failed results as historical evidence;
the bounded detection fix requires a new source snapshot and complete reruns.
It does not change frozen revision 1 or relax the zero-egress requirement.

After the correction, Architect and Steward independently verified the new
274-input snapshot, SHA-256
`437fb3bb0cc0c8baa26e93cb374b1814519771c3e0cd3df161e6ab24a466fa8e`.
Python 3.12.14 and 3.13.13 each passed all 1239 tests with zero failures/errors/
skips, including 75 import-policy checks, 144 independent facade checks and the
three permanent pinned-upstream compatibility tracks. The two formerly failing
checks remain in the full suite. No production source changed for that fix.
The offline wheel build, isolated installation and installed-package smoke also
passed with all 16 packaged schemas. Source digests were equal before/after all
acceptance runs; that is a snapshot comparison, not continuous monitoring.

Architect accepts these local results, not a future commit or CI checkout.
Steward must verify the committed source against that snapshot, keep this PR
draft toward `integration`, and record the new CI run/attempt, head/base and
actual tested merge-preview SHA before candidate acceptance. This subpacket
does not close VPKB-000, VPKB-001 or any human gate, and authorizes no merge.

## Decisions to freeze

1. Separate proposal, upstream-inspected declaration and optional completed
   result; no constructor may fabricate a successful runtime result. No-write
   capture reuse stays outside write transactions and receipt creation.
2. Keep input bundle, expanded bundle, upstream approval, local capture approval
   and receipt intent digests distinct. The facade carries upstream digests;
   it must not compute them with this project's JCS by assumption.
3. Normalize a single path representation without lossy cleanup. Account for
   operation-specific write authority, exact expected hashes, create/replace,
   immutable raw, read preconditions, case collisions and bounded payloads.
4. Distinguish business writes, receipt/head writes, and upstream-expanded
   managed metadata. A runtime result's changed_paths is not just receipt.writes.
   Freeze exact expanded-path fixtures before asserting complete correlation.
5. Claimed inputs are ledger semantics, not merely an alias for every read
   precondition. Preserve receipt's established acyclic intent material and
   leave genesis/ever-claimed chain execution to VPKB-001.
6. Define declaration-only validation versus byte verification and trustworthy
   upstream inspection. Real no-follow, lock, race, atomic rollback and operator
   approval tests remain VPKB-001 adapter-contract/integrity-runtime work.

## Initial pinned-source reading, 2026-09-01

Architect downloaded these public files by exact commit URL into a temporary
review directory and read them without importing or executing them. At that
initial stage this was source-review evidence only, before submodule setup or
behavior fixtures. The historical reading evidence below is preserved; later
verification is described separately. The dependency manifest stays `pinned`
until its complete dependency/license evidence is accepted.

Commit: `9f8c1199047eac2c3828496279fbb7ba9540b90b`.

| Upstream file | Bytes | SHA-256 of downloaded bytes |
| --- | ---: | --- |
| skills/wiki/references/operation-transactions.md | 6155 | 75a6c01950983c6210647ee11104f3be0c389fd7f81458d9d0f06306401a8f83 |
| claude_obsidian/transaction.py | 179506 | e007e3b7d08f72eabc4a95c7031fb596c201562432cf37cc649136b02b223de2 |
| claude_obsidian/ledgers.py | 53046 | 9751d56272e2256bde643e7d3effd47f4c875ce02422be09a8dc0a148113f2d1 |
| LICENSE | 1088 | 1c5915b8cde3e16949e40961353e483d44a65f90fae72405465dcff60118e57f |

Reading findings to preserve during design:

- transaction.py:235 bounds upstream operation IDs at 128 characters; this is
  additional to existing receipt/capture grammar, and must be checked by the
  future adapter rather than silently rewriting an already declared ID.
- transaction.py:254 and :288 separate lexical paths from restrictions on NEW
  destinations; paths have a 1024-byte bound and case/portable-name collisions
  matter. Existing legacy reads must not be mistaken for new write authority.
- transaction.py:1011 uses Python JSON sorted-key serialization for bundle
  hashing, whereas :1287 binds expanded bundle, prepared hashes/modes and Vault
  identity in plan-approval.v3. Neither is the local capture approval hash.
- transaction.py:3522 supports nullable read-precondition digests and explicitly
  does not apply the 1024-write limit to the number of read preconditions.
- transaction.py:3745 and :4358 distinguish complete result from inspected plan,
  both with paths/hashes/modes. Result absence is not receipt-chain failure.

Primary references: [operation contract](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/skills/wiki/references/operation-transactions.md),
[transaction source](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/transaction.py),
[ledger source](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/ledgers.py),
[license](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/LICENSE).

At this initial reading stage, release still required verifying the source
through the pinned submodule, establishing isolated fixtures and licensed source
provenance, and reviewing the facade contract with both children. Any narrower
application policy needed an explicit freeze; an application restriction must
not be presented as an upstream rule.

## Subsequent source verification and investigation

Steward initialized the submodule at the fixed gitlink without following main,
changing `.gitmodules`, or changing upstream source. Detached HEAD, the v2.1.1
tag and static version agree. All four source digests above equal the checked-out
files and pinned Git blobs; tracked/untracked upstream content is clean. Upstream
AGENTS was read and there is no root CLAUDE.md. No host bootstrap or upstream
Skill was invoked. All subsequent executable fixtures use separate disposable
temporary Vaults and the public CLI/scripts, except the explicitly allowed
stable_source_id import after source checks.

Source review found that nonempty address requests modify Markdown and append
counter/manifest writes after the input write list. Two inspections can establish
the final page digest but cannot make head the final write. Directly writing the
expanded metadata is forbidden by upstream authority. The frozen project
policy instead uses canonical ledgers and the supported synthetic chunk address,
with explicit empty address requests/source updates. It is a domain workflow,
not a claim to implement the full upstream wiki-ingest Skill. The contract
documents this choice and the deterministic frontmatter additions needed by
strict lint; neither canonical schemas nor ingestion state are expanded.

Builder subsequently established positive init/capture/genesis/ingest/lint/chunk/BM25
fixtures and counterexamples for address/source expansion. Historical fixture
runs and later revised runs must remain distinct. Their upstream provenance
uses synthetic evidence honestly; passing it is not proof of the full project's
prospective records, structured locator mapping, parser or production runtime.
Those require their separately scoped contracts and VPKB-001/002 acceptance.
Steward independently reviewed the fixture and this contract before freeze.
