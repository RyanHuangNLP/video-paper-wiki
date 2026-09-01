# VPKB-001 adapter-contract

- Parent: VPKB-001.
- Ordered slice: `adapter-contract` before `integrity-runtime`.
- Current subrelease: `pinned-read-only-transaction-inspect-adapter-v1`.
- Packet baseline: `acd3821b15e62bce13fa07b82c1665d501f27f67`.
- Architect: Codex / `gpt-5.6-sol` / `ultra`.
- Builder and Repo Steward: Codex subagents / `gpt-5.6-sol` / `medium`.
- PR: #94 remains open/draft to `integration`; no merge, review submission,
  ready-for-review, auto-merge, or human-gate action is authorized.
- Catalog and overlays remain exactly 67 entries.

## Purpose and sequencing

VPKB-000 was accepted at exact head `acd3821` after Tests run `33456016766`.
That acceptance authorizes VPKB-001 architecture and contract work. It did not
authorize production implementation. This architecture release persists the
historical VPKB-000 acceptance records, updates the active handoff, and freezes
the first narrow upstream adapter contract.

The normative contract is
`docs/ai/contracts/vpkb-001-adapter-contract-v1.md`. The machine boundary is
`video-paper-wiki.upstream-authority.v1` plus the fixed profile
`claude-obsidian-transaction-inspect-9f8c119-v1`. The first implementation may
only authenticate the pin, inspect a deterministic staged transaction through
the pinned public CLI from a private source-only execution snapshot, attach its
genuine plan to the existing facade, and call the pinned
`stable_source_id("file", ...)` function from a separate private snapshot child.

This subrelease does not complete `adapter-contract`. Later subreleases still
owe capture CLI behavior, manual/staged/code routes, operation-result handling,
full-ledger merge fixtures, limits and pinned BM25 behavior. The ordered
`integrity-runtime` slice remains blocked until all adapter-contract work is
accepted.

## Architecture-freeze release

The architecture candidate may contain only:

- the three byte-fixed VPKB-000 post-CI closure records;
- `AGENTS.md`, this packet, the normative contract, task index and team handoff;
- the new authority schema, one valid/one invalid authority fixture, the static
  upstream profile, title-only registry addition, and the minimum schema
  enumeration/closed-object test edit;
- architecture evidence and independent Builder/Steward specification reviews.

It contains no adapter module, CLI command, dependency, lock, workflow, vendor,
Vault, mapper, writer, audit, index, retrieval, catalog-row, seed, or generation
profile change. The current `base-catalog-v1` generation profile stays revision
1 because this adapter emits no catalog rows. A future mapper/compiler must
create a new generation profile revision and bind the consumed authority digest.

After both independent reviews return GO, Repo Steward alone may stage the exact
manifest paths, commit normally to the existing PR branch, and push. The new
head requires fresh Linux/macOS × Python 3.12/3.13 merge-ref CI and a separate
Architect architecture-freeze acceptance. The post-CI decision is historical
evidence carried by the next implementation delivery; it cannot be inserted
into the already-tested commit or relabel old CI.

## Builder implementation work package

Production work remains blocked until Architect names the accepted freeze head,
contract/profile/schema SHA-256 values, current PR base, and exact allowed paths.
Once released, Builder is the only main-code writer and may use only:

- `src/video_paper_wiki/upstream_adapter.py`;
- title-scoped registration/semantic dispatch in
  `src/video_paper_wiki/contracts.py`;
- `tests/unit/test_upstream_adapter.py`;
- `tests/contract/test_upstream_authority.py`;
- `tests/upstream/test_vpkb001_transaction_inspect.py`;
- `tests/security/test_upstream_adapter_boundary.py`;
- packet-specific fixtures under `tests/fixtures/upstream-authority/**`;
- implementation evidence under
  `artifacts/verification/VPKB-001-adapter-contract/implementation/**`.

The schema, profile, valid/invalid contract fixtures, normative contract,
generation revision decision, task index, team handoff, existing facade, capture
contract, secure I/O primitives, vendor gitlink, dependencies, CLI and catalog
are Architect-owned/frozen inputs. Builder must report a contract gap instead
of changing any of them. Architect may issue a new exact work package for a
necessary integration correction; another agent then reviews that correction.

## Implementation acceptance

The implementation must demonstrate all normative positive/refusal cases,
including proposal-before-I/O ordering, exact `.work` layout, compact bundle and
`content/<sha256>` goldens, capture/generic/ingest plan attachment, clean
pin/tree/profile verification before and after execution, source-ID fixture and
expected-value behavior, ignored timestamp-valid `.pyc` exclusion, exact
21-file private execution-tree construction and revalidation, replacement of a
hostile inherited environment with the exact private scratch environment,
closed bounded stdout/stderr, stable error mapping, deep-copy isolation, and
zero content/mode changes to disposable Vault fixtures. The checked-in authority fixture is a
schema/semantic example only; tests obtain their Vault identity and stdout
digest from the real disposable invocation.

Run the focused suite first, then the complete locked suite on local Python
3.12/3.13. Build/install a fresh offline wheel and prove the schema/profile are
byte-equal to the checkout and missing upstream fails closed without download.
Repo Steward independently reviews the exact diff and source snapshot, performs
serialized Git/push, and records a fresh four-job CI run. Architect replays the
critical checks and accepts or returns blockers against the exact head. Passing
does not authorize apply/admin, complete adapter-contract/VPKB-001, alter PR
state, merge, or close a human gate.

## Exclusions and rollback

Do not edit or stage `.DS_Store`, the five existing untracked planning documents,
`inbox/`, `tools/`, seed/overlays, `.work/**`, a real Vault, credentials,
approval material, `vendor/claude-obsidian/**`, `uv.lock`, workflows, frozen
VPKB-000 schemas/contracts, or human-gate evidence.

Rollback only the exact architecture or implementation commit under review.
Never use blanket reset/clean and never delete preserved user content.
