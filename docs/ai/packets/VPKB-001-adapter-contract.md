# VPKB-001 adapter-contract

- Parent: VPKB-001.
- Ordered slice: `adapter-contract` before `integrity-runtime`.
- Current subrelease: `deterministic-transaction-inspect-staging-v1`.
- Current architecture baseline: `57c2519425dbccd6bb48a0f82e77699e17afcfb6`.
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

## Accepted second subrelease and sequencing

The second normative contract is
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

After that subrelease, adapter-contract still owes staged PDF/code behavior,
operation-result handling, full-ledger/managed-prefix fixtures, and remaining
limits/pinned BM25 compatibility. The ordered `integrity-runtime` slice remains
blocked until every adapter-contract subrelease is accepted.

## Accepted second-subrelease implementation

The 24-path architecture freeze is accepted at exact head
`3ab19eda4f417b96d89a0a50b2ce2c05233a8478`, tree
`9580fd8735ba8dfc286b257ac5c2b9ed9aae6cca`. Fresh run `33469912314`
tested merge preview `ea86e96fbbbcaf6fbda360679c6e6d209a6151b7`; all four Linux/macOS ×
Python 3.12/3.13 jobs passed 1750 tests. The separate decision is
`ACCEPTED_VPKB_001_MANUAL_PDF_CAPTURE_DRY_RUN_ARCHITECTURE_AT_EXACT_HEAD`.
Its three post-CI records are byte-fixed inputs carried by this implementation
delivery.

The revision-1 implementation work package fixed a 22-path delivery. Builder's
R1 candidate and Repo Steward's `CHANGES_REQUIRED` report remain preserved. R2
fixed the semantic blockers and independently passed, but its exact staged
delivery was rejected because cached diff-check found one blank line at EOF.
The R2 work package, local acceptance, manifest, Steward rejection and clean
index rollback remain immutable history.

Revision 2 authorizes only removal of that final one-byte LF plus new R3
evidence. The corrected R3 binds the same seven production/test files at snapshot
`c275904d2865cb1560408e1d3ba3894ed172e3a9ecf51c44d5c392e2d5b3a50d`.
Repo Steward proved the exact byte relation, replayed the three private-directory
and matching-sibling identity replacements and returned
`GO_FOR_ARCHITECT_R3_ACCEPTANCE`.

Architect local acceptance replayed 342 focused tests and the complete 1835-test suite
on Python 3.12.14 and 3.13.13, real pinned create/noop controls, the four identity
replacement attacks and an offline installed-wheel smoke from outside the
checkout. Repo Steward then verified the self-excluding delivery manifest and
committed exactly 28 named paths as
`57c2519425dbccd6bb48a0f82e77699e17afcfb6`, tree
`c77a7c6ccc8bae3292611c2b24c33255f248710c`, without changing PR state.
Fresh run `33477484577` tested merge preview
`058ae19131cc418edc42dd8d311354503a0e515b`; all four Linux/macOS × Python
3.12/3.13 jobs passed 1835 tests. The separate Architect decision is
`ACCEPTED_VPKB_001_MANUAL_PDF_CAPTURE_DRY_RUN_IMPLEMENTATION_AT_EXACT_HEAD`.

The three resulting post-CI records are intentionally absent from the tested
head and carried byte-for-byte by the current architecture delivery:

- `manual-pdf-capture-dry-run/implementation/ci-observation.json`, SHA-256
  `35e7ef971ebb7d0b504705f650a8842d8800a7793a7ba72874d800c49ce7e5e6`;
- `manual-pdf-capture-dry-run/implementation/merge-parents.json`, SHA-256
  `021c76c8f2bcad6e31e443335e766be9dbdf789ca0fb3b674397fd360d1ffc97`;
- `manual-pdf-capture-dry-run/implementation/architect-acceptance.json`, SHA-256
  `752a94704d167b3f6619267e87059e6e7dffd44ddc980b9ed5b9a74dfc301c0e`.

No production file outside the two named adapter/contract modules changed. Old
v1 bytes, the new frozen contract/schema/profile/fixtures, CLI/entry-point,
dependencies, lock, workflow, vendor, real Vault, facade, mapper, writer, audit,
index, retrieval, catalog rows, seed, overlays, taxonomy and generation profile
remain unchanged. `base-catalog-v1` stays revision 1 because no catalog rows are
emitted.

## Third subrelease architecture work package

The next bounded contract is
`docs/ai/contracts/vpkb-001-transaction-inspect-staging-v1.md`; its machine
result is `video-paper-wiki.transaction-staging.v1`. This subrelease stages an
already valid transaction proposal and all three exact caller-supplied byte maps
into the only accepted layout:

```text
.work/<batch-id>/transaction-inspect/content/<sha256>
.work/<batch-id>/transaction-inspect/bundle.json
```

R1 Builder and Repo Steward reviews rejected a sequence of independent
`stage_bytes` calls: replacing the batch or transport directory between calls
could split content and bundle across two directory lineages while the wrapper
still returned success. Those blocker reports are preserved. Revision 2 keeps
the existing public `stage_bytes` behavior unchanged and authorizes one narrow
internal multi-file session in `staging.py`. It retains the checkout, `.work`,
batch, `transaction-inspect`, and `content` descriptors; reopens every named
edge around each installation; and verifies the complete exact file set in the
same lineage before success. Unique content is installed in digest order,
followed by the exact compact bundle as the final file. Existing identical bytes
are reused; conflicting, incomplete, replaced, or unsafe paths fail closed. The
portable result contains no absolute host path.

Architect owns the architecture-only contract, schema, fixtures, work package,
status files and freeze evidence. Builder and Repo Steward independently
returned R2 GO against the same exact contract/work-package hashes. Python 3.12
and 3.13 each passed all 1838 tests under the required host AF_UNIX environment;
an isolated installed wheel exposes all 24 schemas with exact new-schema bytes.
Production implementation remains blocked until the exact 21-path
architecture-only delivery receives fresh four-job merge-ref CI and a separate
exact-head Architect acceptance. This architecture commit's only production
delta is title registration in `contracts.py`; it changes no adapter behavior.
A later implementation package may authorize only the new staging module, the
additive retained-lineage helper in `staging.py`, narrowly required semantic
dispatch, and focused unit/contract/security/upstream tests.

This architecture does not authorize a mapper from manual capture or code
evidence into a facade proposal. It starts no process and adds no CLI. It does
not execute transaction apply/recover, attach runtime results, merge ledgers,
audit managed state, change dependencies/vendor/workflows, touch a real Vault,
or begin the ordered `integrity-runtime` slice. `base-catalog-v1` stays revision
1 because the staging result emits no catalog rows.

Architecture and later implementation acceptance each require complete locked
Python 3.12/3.13 regression tests, an installed-wheel resource check,
independent Repo Steward review, fresh Linux/macOS × Python 3.12/3.13 CI and a
separate Architect decision at the exact head. Passing does not complete
adapter-contract/VPKB-001 or authorize PR state changes, merge, or a human gate.

## Exclusions and rollback

Do not edit or stage `.DS_Store`, the five existing untracked planning documents,
`inbox/`, `tools/`, seed/overlays, generated `.work/**`, a real Vault,
credentials, approval material, `vendor/claude-obsidian/**`, `uv.lock`,
workflows, frozen VPKB-000 or either accepted adapter subrelease, or human-gate
evidence.

Rollback only the exact architecture or implementation commit under review.
Never use blanket reset/clean and never delete preserved user content.
