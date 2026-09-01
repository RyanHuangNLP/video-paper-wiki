# VPKB-001 adapter-contract

- Parent: VPKB-001.
- Ordered slice: `adapter-contract` before `integrity-runtime`.
- Current subrelease: `pinned-manual-pdf-capture-dry-run-v1`.
- Current architecture baseline: `17c13f6317416f47d2610240aaf905598131e5bc`.
- Original packet baseline: `acd3821b15e62bce13fa07b82c1665d501f27f67`.
- Architect: Codex / `gpt-5.6-sol` / `ultra`.
- Builder and Repo Steward: Codex subagents / `gpt-5.6-sol` / `medium`.
- PR: #94 remains open/draft to `integration`; no merge, review submission,
  ready-for-review, auto-merge, or human-gate action is authorized.
- Catalog and overlays remain exactly 67 entries.

## Accepted first subrelease

VPKB-000 was accepted at exact head `acd3821` after Tests run `33456016766`.
The first VPKB-001 architecture freeze was then accepted at exact head
`be7ecf303af2879459036ed8e6831291f168fac4` after run `33461002166`.

The resulting `pinned-read-only-transaction-inspect-adapter-v1` implementation
is now accepted at exact head `17c13f6317416f47d2610240aaf905598131e5bc`.
Fresh run `33465872376` tested merge preview
`dd6954f1c2368d83cd6d5f1d5057ed4d20acb327`; all Linux/macOS × Python
3.12/3.13 jobs passed 1747 tests. Architect decision
`ACCEPTED_VPKB_001_PINNED_READ_ONLY_ADAPTER_V1_AT_EXACT_HEAD` is bound to that
head, merge preview, accepted tree, frozen contract/profile/schema and source
snapshot.

These three post-CI files were intentionally not inserted into the already
tested commit. This successor architecture delivery carries them byte-for-byte:

- `implementation/ci-observation.json`, SHA-256
  `6d60cdd9678fa9ea49807af7c7ff56d298bfafa90d3568e6a752e920def73dc6`;
- `implementation/merge-parents.json`, SHA-256
  `20788ae4b7315fa87ee8df1c2ba812e92d211bf8cd1f9c76f67e3957d163cfc3`;
- `implementation/architect-acceptance.json`, SHA-256
  `56a6732afcce17e79bf5bbeb5ae609b39367638e45c2fd1119d86a11d329f8e6`.

The accepted v1 contract, `video-paper-wiki.upstream-authority.v1`, command
profile, fixtures and implementation are historical immutable inputs. Their
acceptance completes only the first bounded subrelease; `adapter-contract` and
VPKB-001 remain in progress.

## Current subrelease and sequencing

The next normative contract is
`docs/ai/contracts/vpkb-001-manual-pdf-capture-dry-run-v1.md`. Its machine
boundary is `video-paper-wiki.upstream-capture-authority.v1` plus the independent
static profile `claude-obsidian-capture-apply-dry-run-9f8c119-v1`.

The smallest useful upstream capture boundary is the public `capture apply`
command without `--apply`. Unlike `capture plan`, this default dry-run includes
the operation and genuine `approved_plan_sha256` required to bind the already
frozen `capture-inspection.upstream_plan_sha256`. This subrelease processes one
explicit `inbox/**/*.pdf`, with fixed one-item/64-MiB budgets and absent custom
capture config. It accepts a create dry-run or exact existing-content noop and
normalizes the real pinned output into the closed authority plus a manual PDF
capture inspection.

It does not execute capture, persist the absolute `content_file` exposed by the
upstream stdout, build a deterministic facade bundle, or use a real Vault in
verification. It does not include staged PDF/code routes, code proposal binding,
operation results, ledger merge, managed-prefix audit, mapper/compiler,
integrity runtime, network/models, BM25/index, retrieval, or publication.

After this subrelease, adapter-contract still owes staged PDF/code behavior,
operation-result handling, full-ledger/managed-prefix fixtures, and remaining
limits/pinned BM25 compatibility. The ordered `integrity-runtime` slice remains
blocked until every adapter-contract subrelease is accepted.

## Current architecture-freeze release

This architecture candidate may contain only:

- the three byte-fixed first-subrelease post-CI records named above;
- status-only updates to `AGENTS.md`, this packet, task index, team handoff and
  the verification README;
- the new normative contract, closed authority schema, one valid/one invalid
  fixture and independent static command profile;
- title-only schema-registry admission and minimum schema count/closed-object
  enumeration edits;
- current-subrelease architecture evidence and independent Builder/Steward
  specification reviews.

It contains no production adapter behavior, old v1 contract/schema/profile/
fixture byte edit, CLI/entry-point,
dependency, lock, workflow, vendor, Vault, facade, capture helper, mapper,
writer, audit, index, retrieval, catalog-row, seed, overlay, taxonomy or
generation-profile change. `base-catalog-v1` stays revision 1 because no catalog
rows are emitted. A future mapper/compiler must create a new generation profile
revision and bind every consumed authority digest.

After independent Builder and Repo Steward reviews return GO, Architect runs
focused schema/profile and real-pinned-CLI probes plus full local Python
3.12/3.13 and installed-wheel validation. Repo Steward then checks the exact
self-excluding manifest, stages only named paths, commits normally to the
existing PR branch and pushes without changing PR state. The new head requires
fresh Linux/macOS × Python 3.12/3.13 merge-ref CI and a separate Architect
architecture-freeze acceptance. Run `33465872376` is historical evidence for
`17c13f`; it cannot validate the successor head.

## Future Builder implementation work package

Production work remains blocked until Architect names the accepted freeze head,
contract/profile/schema SHA-256 values, current PR base, and exact allowed paths.
Once released, Builder is the only main-code writer and may use only:

- `src/video_paper_wiki/upstream_adapter.py`;
- title-scoped semantic dispatch in `src/video_paper_wiki/contracts.py`;
- focused unit, contract, upstream and security test files named by the exact
  implementation work package;
- packet-specific fixtures and implementation evidence under the current
  subrelease directory.

The new schema/profile/valid-invalid fixtures/normative contract, accepted v1
contract/schema/profile/fixtures and its public APIs/constants/profile selection/
error order/behavior/goldens, generation revision, task index, team handoff,
existing facade/capture helpers, vendor gitlink, dependencies, CLI and catalog
are Architect-owned frozen inputs. `src/video_paper_wiki/upstream_adapter.py` is
an expressly shared Builder path: branch-isolated additions for the new capture
API are allowed, while every accepted v1 semantic and regression must remain
unchanged. Builder reports a contract gap rather than changing a frozen input.
Architect may issue a narrow integration correction only with another
independent review.

Implementation acceptance must demonstrate real pinned create/noop dry-runs in
disposable Vaults; exact argv with no `--apply`; complete source/config/sibling
pre/post snapshots; closed stdout projection and plan binding; hostile path,
race, limit, environment, ignored-bytecode and child failure cases; deep-copy
validation; zero network attempts; and zero Vault byte/type/mode changes on
every path.

Run focused tests, then the complete locked suite on local Python 3.12/3.13.
Build/install a fresh offline wheel and prove new schema/profile/adapter bytes
equal the checkout and missing upstream fails closed without download. Repo
Steward independently reviews the exact diff/source snapshot and records fresh
four-job CI. Architect replays critical checks and accepts or returns blockers
against the exact head. Passing does not complete adapter-contract/VPKB-001 or
authorize apply/admin, PR state changes, merge, or a human gate.

## Exclusions and rollback

Do not edit or stage `.DS_Store`, the five existing untracked planning documents,
`inbox/`, `tools/`, seed/overlays, `.work/**`, a real Vault, credentials,
approval material, `vendor/claude-obsidian/**`, `uv.lock`, workflows, frozen
VPKB-000 or accepted v1 files, or human-gate evidence.

Rollback only the exact architecture or implementation commit under review.
Never use blanket reset/clean and never delete preserved user content.
