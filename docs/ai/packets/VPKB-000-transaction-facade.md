# VPKB-000-transaction-facade — architecture preparation

Parent: VPKB-000. Status: design-pending; implementation not released.
Architect: Sol/Ultra; Builder and Repo Steward: Sol/Medium.
Predecessor: accepted VPKB-000-capture-contracts. Do not use this planning note
as a frozen API or claim that the predecessor has passed.

The next packet will give CLI, receipt and audit one non-persistent transaction
representation. It may validate supplied mappings/bytes and compare declared
plans/results; it must not inspect/apply a real Vault or create another ledger.
Architect must freeze fields, phases, error codes and exact allowed paths before
Builder implements it. No retrieval or production adapter work belongs here.

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

## Pinned-source reading, 2026-09-01

Architect downloaded these public files by exact commit URL into a temporary
review directory and read them without importing or executing them. This is
source-review evidence only: the submodule is not initialized/verified and no
upstream behavior fixture has passed. The dependency manifest stays `pinned`.

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

Before release: verify the source through the pinned submodule, establish
isolated fixtures and licensed source provenance, then review the actual facade
contract with both children. Freeze any narrower application policy explicitly;
do not claim an application restriction is an upstream rule.
