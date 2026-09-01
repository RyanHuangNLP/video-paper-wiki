# VPKB-001 adapter-contract

- Parent: VPKB-001.
- Ordered slice: `adapter-contract` before `integrity-runtime`.
- Current subrelease: `staged-pdf-capture-inspect-v1`.
- Current architecture baseline: `fb2cbcb565195a232f22d02c0474ac1b1b34f7d3`.
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

## Third subrelease implementation

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
are reused and an incomplete exact layout is repaired; conflicting, replaced,
or unsafe paths fail closed. The portable result contains no absolute host path.

Architect owns the architecture-only contract, schema, fixtures, work package,
status files and freeze evidence. Builder and Repo Steward independently
returned R2 GO against the same exact contract/work-package hashes. The exact
21-path architecture delivery is accepted at head
`62f3063fb612024179125bc7d842abdd3de0a4ee`, tree
`37dfbba09e9f73656af4bb5510f7586bb5d4223e`. Fresh run `33481415882`
tested merge preview `910e272879b728aef8d1da1db2ba88d70feba5b0`; all four
Linux/macOS × Python 3.12/3.13 jobs passed 1838 tests. The separate Architect
decision is
`ACCEPTED_VPKB_001_TRANSACTION_INSPECT_STAGING_ARCHITECTURE_AT_EXACT_HEAD`.

Implementation R1 froze ten source/test paths at snapshot
`dbdc7f617c1bddaa8bb25169a779c8a5ad264d555d6ca25066c86e0b886b635d`.
Its 428 focused checks and both 1888-test local Python suites passed, but Repo
Steward found `COMPLETE_SET_UNSAFE_ORPHAN_001`: the helper returned success with
FIFO, symlink, directory or non-digest content extras and with a transport-root
extra. The R1 work package, Builder candidate and `CHANGES_REQUIRED` review are
immutable history.

Revision-2 implementation work package
`transaction-inspect-staging/implementation/implementation-work-package.json`,
SHA-256 `c79ade9aa3b9c70c77250ef3f5a3aa7743c60652b3c4725d5d4e0995a5a67633`,
authorizes only this correction and R2 evidence. The transport root may contain
only `content` and optional/present `bundle.json`; unrelated content entries may
remain only as lowercase-64hex named no-follow regular files. Their bytes are
not read or rehashed. The three architecture post-CI records remain immutable
historical inputs. Builder cannot change the public `stage_bytes` API,
contract/schema, status files, dependencies or Git state.

Builder froze the corrected ten-path source/test snapshot
`75179e9d0a66b3d528a14d6cc48be7139d350380be9b945b61eeb18eb6cb4ab2`.
Independent Repo Steward review SHA-256
`1523f8ac0b3cfe93c013abce39332df60616d6d5d578f13ff89307459f08d80e`
records `GO` after 435 focused checks, 24 retained-lineage/complete-set checks
and eight direct probes. Architect independently replayed 435 focused checks,
24 adversarial checks, the four real pinned disposable-Vault operation vectors,
1895 tests under each locked Python version, and an outside-checkout installed
wheel with 24 schemas. Architect local decision
`PASSED_LOCAL_R2_IMPLEMENTATION_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI` is bound
to `architect-local-acceptance.json`, SHA-256
`98ec4d0c3a7571fc46e271bed260191f0bbae6b89230bbd69734a5c132126d9b`.
At that R2 gate this authorized only the exact-path delivery audit; no
implementation commit or exact implementation head existed yet, and normal
push, fresh four-job merge-ref CI plus a separate exact-head Architect decision
still remained required.

That temporary-index audit found `CACHED_DIFF_BLANK_EOF_001` before any real
index mutation: `tests/contract/test_transaction_staging.py` ended with two LF
bytes and cached diff-check rejected the new blank line at EOF. The complete R2
work package, candidate/review, local acceptance, delivery manifest and
`CHANGES_REQUIRED` delivery review are preserved byte-for-byte. Revision-3 work
package SHA-256
`1ba273bd9ae25f00583a4dac4c881b5eeb0d3796faf8b7cc10fffa34e918ac67`
authorizes only removal of the final one-byte LF and new R3 evidence. The exact
corrected file is 2848 bytes with SHA-256
`a24970e839051c43719996ab519b9e1405f1938aa201238d8681fd31c01dc797`;
the precomputed corrected ten-path snapshot is
`e5f9f9b8e8686023183c5871ebb55b4d5ac8c6a9494646f91bb614fab1cedc76`.
No production, contract, schema, fixture or other test byte may change.

Builder froze that exact R3 snapshot in `builder-candidate-r3.json`, SHA-256
`431a469fd36d4a663b09e47262a890c1f9be7c3c97baab9948cfeb855bba6258`.
Independent `steward-review-r3.json` records `GO`, SHA-256
`6c174fa4bfc16c22f4708716937ae2561e67e11defc6b3ddc1a357e838d6d641`.
Architect then replayed 435 focused checks, 24 adversarial checks, all four real
pinned operation vectors, 1895 tests on each locked Python version and the
byte-identical outside-checkout installed wheel. Local decision
`PASSED_LOCAL_R3_IMPLEMENTATION_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI` is bound
to `architect-local-acceptance-r3.json`, SHA-256
`a4ce61b1035960131d7e6484e637464ee0c302ce8242212dc449287ebc86c8a8`.
That local decision permitted only the final exact-path delivery audit; commit,
push, fresh CI and exact-head acceptance remained separate gates.

This architecture does not authorize a mapper from manual capture or code
evidence into a facade proposal. It starts no process and adds no CLI. It does
not execute transaction apply/recover, attach runtime results, merge ledgers,
audit managed state, change dependencies/vendor/workflows, touch a real Vault,
or begin the ordered `integrity-runtime` slice. `base-catalog-v1` stays revision
1 because the staging result emits no catalog rows.

The R2 semantic checks and rejected delivery remain historical evidence. The
R3 implementation was committed at exact head
`fb2cbcb565195a232f22d02c0474ac1b1b34f7d3`, tree
`4a28ee53f71a0f2971f23b87e1f4c06d3bdf5b79`. Fresh run `33491834331`
tested merge preview `12bc7925140352fad516405b7eafaa8923d106e7`;
all four Linux/macOS × Python 3.12/3.13 jobs passed 1895 tests. Separate
Architect decision
`ACCEPTED_VPKB_001_TRANSACTION_INSPECT_STAGING_IMPLEMENTATION_AT_EXACT_HEAD`
accepts only this bounded implementation. Its three post-CI records have exact
SHA-256 values
`794d1fe6a5889c2bbbb5b873dc09e4e043b15de152dd6666a231662895a7644d`,
`7b73ede5922cfe3c5604f17dfbab81407b14480f8523afc7a34af9f3b7c51908`,
and `269deabc8f4dda1681b8c51300685b4d5fa37a4051a61c77a5017dc4e0c78087`
and are carried unchanged by the successor architecture.

## Fourth subrelease architecture candidate

The next contract is
`docs/ai/contracts/vpkb-001-staged-pdf-capture-inspect-v1.md`, SHA-256
`8f9624c98ebbc9ae7eba51e61645291f11bc482f2fde1353e2ec4187f6c9d21f`.
It introduces the closed
`video-paper-wiki.staged-pdf-capture-request.v1` and
`video-paper-wiki.staged-pdf-capture-authority.v1` schemas. Architecture work
package SHA-256
`298ae880c5013c79a3db94dbc05c0d6d1c77eb0af3e507a55d5a2a2752c02421`
keeps the implementation with Builder and exact delivery/CI with Repo Steward.

Paper prepare will persist one canonical no-target request containing the
parsed desensitized approval-ref and exact plan/PDF descriptors. It must publish
the blob first and request last in one retained batch/prepared session. The
agent-safe `capture inspect --prepared` path then retains the same batch lineage
while revalidating request, canonical plan and PDF bytes. A complete no-follow
Vault sibling snapshot chooses reuse or create. Reuse keeps the requested
operation ID in the wrapper but creates no facade, staging, process, network
attempt or write. Create builds one capture-create facade, uses one shared public
compact encoder, the accepted deterministic staging boundary and the accepted
pinned read-only transaction inspector. It never applies or mutates the Vault.

Builder and Repo Steward independently returned GO after earlier review rounds
closed approval provenance, multi-file lineage, reuse operation binding,
object-only/runtime validation ownership, PDF bounds, encoder error mapping and
the accepted digest-before-limit order. Python 3.12/3.13 each passed 1901 tests,
and the checkout-external wheel exposes 26 schemas with both new resources
byte-equal. Exact-path delivery, fresh four-job CI and separate exact-head
Architect architecture acceptance was then completed at exact head
`4168e151c332cdcf89227bf086d4a6bc5308e649`, tree
`78d43e20f8937a96c6cc86357729c72d295658cb`. Fresh run `33497663181`
tested merge preview `f48d3cc3323958270f2e249d8e6a71f853df2150`; all four jobs passed
1901 tests. Decision
`ACCEPTED_VPKB_001_STAGED_PDF_CAPTURE_INSPECT_ARCHITECTURE_AT_EXACT_HEAD`
authorizes issuance of separate Builder implementation work packages. R2
candidate `20f9df83117bf296e9ef4ef6fb6ce78222b17f92cadb774c7fc15df31af11437`
passed 1938 tests on both locked Python lines, but Architect rejected it after a
hostile probe replaced an initially missing fixed slot with the same bytes and a
new inode before the caller adopted its baseline. R3 candidate
`920b126b602cb17b1727223df0698a88bded0f3d4787a07ce23e2edf941246b8`
closed that window, bound 17-path snapshot
`2902553f60693cb6596b53d8d9096cf1c20f9b2f5ff7a6f9ae340136254a5878`,
and passed 1940 tests on both locked Python lines. An independent five-case
review then rejected it as a complete release candidate: `_inputs` opened plan
before request semantics and did not reopen named prepared/plan edges on its
partial exception path. Revision 4 SHA-256
`e98e2fb4bd3efe914ab77f1882e5ce4a7887d6327b0cfba99c78fcf7cc7bb6cc`
(17,357 bytes) authorized that correction. R4 candidate
`77e2657ce77918e55763f729a86d4453ba9bdb925587d0df4c48d9aa2d43c652`
closed the target gap, bound 17-path snapshot
`ae6cd5b9fa93f00894d7a2f6ad484fb9bb066d07617d1572afb9b792125cbc02`,
and passed 1948 tests on both locked Python lines. Independent review then
rejected it as a complete release candidate after reproducing staging conflict
exits after persistent named transport/content replacement and initial/repeat
captured-snapshot scan exits without a final named-edge check. Active revision
5 SHA-256 is
`71e5af783fbb5410bc4e0fae91fec775dd92a5334aeacdb197af0e7ed76dccd5`
(19,409 bytes). It changes no contract, schema, public surface or failure order
and permits only `staging.py`, `captured_snapshot.py`,
`test_work_staging_boundary.py`, `test_staged_pdf_capture_boundary.py`, and R5
candidate evidence. R1/R2/R3/R4 work packages and the rejected R2/R3/R4
candidates remain byte-exact history. Final R5 candidate
`e4fb96af7b0eeb62d3c3cd3aa8a3c492c2ea9f1dae7a765fb4cf53f3b233435f`
binds 18-path snapshot
`c3634d7b575e25f1221f3a566014f688c90544b3d215edb1cd2b7d2b10102b8d`.
Builder and Architect each passed 1962 complete tests on both locked Python
lines. Repo Steward review
`5b2c67359bec26cd768ff3771f8779d7ef8ac43fc3c8babec6728a1abddd08a3`
returned `GO_FOR_ARCHITECT_LOCAL_ACCEPTANCE`, and Architect local acceptance
`19a5057aeea51da6305d1f911410c159f5476e5fda45c772998fb095dec51f5e`
records the original hostile-probe replays plus offline installed wheel
`a422e8dbc6f96b543b6509cbb3695e592f78c5233975c196861e8f29c5abf7e7`
with 26 schemas. Exact-path delivery, fresh merge-ref CI and separate exact-head
acceptance remain pending.
Passing this subrelease will not complete staged code capture, operation-result
handling, the rest of adapter-contract, VPKB-001, PR merge, or any human gate.

## Exclusions and rollback

Do not edit or stage `.DS_Store`, the five existing untracked planning documents,
`inbox/`, `tools/`, seed/overlays, generated `.work/**`, a real Vault,
credentials, approval material, `vendor/claude-obsidian/**`, `uv.lock`,
workflows, frozen VPKB-000 or either accepted adapter subrelease, or human-gate
evidence.

Rollback only the exact architecture or implementation commit under review.
Never use blanket reset/clean and never delete preserved user content.
