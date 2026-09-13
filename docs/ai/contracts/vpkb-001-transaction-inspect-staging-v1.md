# VPKB-001 deterministic transaction-inspect staging contract v1

Revision: 2 architecture candidate. Architect: Codex (`gpt-5.6-sol`,
`ultra`). Revision 1 was rejected because repeated single-file `stage_bytes`
calls did not bind one directory lineage across the complete transport. Its
Builder and Repo Steward blocker reports remain immutable R1 evidence. Both
roles must independently review these revised exact bytes before implementation
is authorized. Packet baseline:
`57c2519425dbccd6bb48a0f82e77699e17afcfb6`.

This is the third bounded subrelease in VPKB-001's ordered
`adapter-contract` slice. The first subrelease authenticates and invokes the
pinned public `transaction inspect` command. The second observes one explicit
manual-inbox PDF through public capture dry-run. This subrelease fills the local
transport gap between a frozen `video-paper-wiki.transaction-facade.v1`
proposal and the already accepted read-only transaction-inspect adapter.

It stages exact caller-supplied bytes only under the current checkout's
`.work/<batch-id>/transaction-inspect/` directory. It does not derive a facade
proposal from capture authority, prepared data, code evidence, records, or any
other business object. It does not invoke upstream code, read or mutate a Vault,
execute apply/recover/admin, contact a network, parse documents, publish
canonical data, create runtime results, merge ledgers, audit managed prefixes,
build indexes, or close any human gate.

The accepted manual-PDF implementation at exact head
`57c2519425dbccd6bb48a0f82e77699e17afcfb6`, tree
`c77a7c6ccc8bae3292611c2b24c33255f248710c`, is an immutable input. Its
fresh Tests run `33477484577` checked merge preview
`058ae19131cc418edc42dd8d311354503a0e515b`; all four Linux/macOS × Python
3.12/3.13 jobs passed 1835 tests. The three post-CI records carried by the
architecture delivery have exact SHA-256 values:

- `implementation/ci-observation.json`:
  `35e7ef971ebb7d0b504705f650a8842d8800a7793a7ba72874d800c49ce7e5e6`;
- `implementation/merge-parents.json`:
  `021c76c8f2bcad6e31e443335e766be9dbdf789ca0fb3b674397fd360d1ffc97`;
- `implementation/architect-acceptance.json`:
  `752a94704d167b3f6619267e87059e6e7dffd44ddc980b9ed5b9a74dfc301c0e`.

Those records describe the historical head only. Carrying them does not make
their CI result apply to a new architecture head.

## Frozen public API

The Builder adds `src/video_paper_wiki/transaction_staging.py` with exactly
these public functions:

```python
def stage_transaction_inspect_transport(
    proposal: object,
    *,
    write_bytes: object,
    original_bytes: object,
    read_bytes: object,
    batch_id: object,
) -> dict[str, object]: ...

def validate_transaction_staging(document: object) -> dict[str, object]: ...
```

`stage_transaction_inspect_transport` uses the existing current-working-directory
checkout authority from `video_paper_wiki.staging.resolve_checkout_root`. There
is no caller-supplied checkout root, work root, destination path, filename,
mode, overwrite flag, cleanup flag, or alternate layout. The caller must run at
the exact checkout root. Existing `.git`/`pyproject.toml` identity checks and the
existing batch grammar remain unchanged.

`validate_transaction_staging` is object-only. It reads no path, changes no
filesystem state, starts no process, and returns a deep copy that shares no
mutable container with its input. Central `validate_document` dispatches the
same title-scoped semantic checks after implementation.

No CLI or entry point is added by this subrelease.

## Validation before filesystem access

The staging function performs all pure checks before resolving or opening the
checkout:

1. Call `validate_transaction(proposal)`. Only `phase=proposal`,
   `inspection=null`, and `runtime_result=null` are accepted. Capture, ingest,
   and generic operation types remain exactly those admitted by the frozen
   facade.
2. Call `verify_transaction_bytes` with all three supplied maps. Each map must
   be an exact built-in `dict` with the exact declared keys. New values must be
   exact `bytes`; create originals and null read preconditions use `None`;
   replacement originals and non-null reads use exact `bytes`. Mapping or bytes
   subclasses are not accepted. Receipt and head bytes remain the canonical
   bytes required by the facade.
3. Validate `batch_id` with the existing `validate_batch_id` grammar. The value
   is 1..128 ASCII characters matching
   `^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?$`.
4. Build the exact transaction bundle described below. Its SHA-256 must equal
   `proposal.input_bundle_sha256`, and its size must be 1..8,388,608 bytes.
5. Group write payloads by declared SHA-256. Descriptors sharing a digest must
   have equal sizes and exact equal bytes. The physical content list is the
   unique digest set in ascending lowercase-hex byte order.
6. Construct and semantically validate the complete return document with both
   possible `already_staged` values, then construct one ordered multi-file
   staging request, before the first filesystem access.

Failure in any step above leaves `.work` untouched. The function does not
probe original/read paths itself: the three byte maps are caller-supplied
snapshots, and `verify_transaction_bytes` compares only those supplied bytes.
This staging boundary does not claim that the bytes still match a later Vault.
The accepted pinned inspect adapter independently verifies the real Vault when
it is called.

## Exact upstream bundle bytes

The bundle object has exactly these fields:

```text
schema = "claude-obsidian.transaction.v1"
operation_id = proposal.operation_id
operation_type = proposal.operation_type
writes = one transport write per proposal write, in proposal order
expected_hashes = proposal.expected_hashes
read_preconditions = proposal.read_preconditions
address_requests = []
source_manifest_updates = {}
```

Each transport write has exactly `path`, `mode`, `content_file`, and `sha256`.
`path`, `mode`, and `sha256` equal the facade descriptor. `content_file` is
exactly `content/<sha256>`. Equal payload digests reuse that physical content
file while every facade write retains its own ordered bundle entry. Inline
content, absolute paths, suffixes, alternate names, caller-selected filenames,
address requests, source-manifest updates, and engine expansion are forbidden.

Bundle bytes are exactly:

```python
json.dumps(
    bundle,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
```

There is no BOM or trailing newline. This is the same raw-byte domain already
authenticated by `inspect_pinned_transaction`. It is not JCS, a transaction
declaration digest, a capture approval hash, an upstream plan approval, or a
runtime-result bundle digest. The implementation must cross-test the generated
bytes against the accepted adapter rather than silently introducing a second
encoding.

## Fixed staging layout and publication order

The only generated paths relative to the checkout are:

```text
.work/<batch-id>/transaction-inspect/content/<sha256>
.work/<batch-id>/transaction-inspect/bundle.json
```

The existing public `stage_bytes` API and its single-file behavior remain
unchanged. This release narrowly extends `video_paper_wiki.staging` with one
internal multi-file session used by `stage_transaction_inspect_transport` in a
single call. That session reuses the existing checkout resolver, segment and
batch validators, descriptor-relative no-follow directory traversal, exclusive
temporary-file creation, hard-link installation, exact-byte comparison,
conflict handling, and sibling cleanup. It is not an alternate checkout/path
authority, a general caller-selectable layout, or a second independent writer.
The internal helper name and shape are not public API; its required behavior is
frozen here.

After creating or opening the fixed directory chain and before installing the
first file, the session retains open descriptors and records device/inode
identity for the checkout, `.work`, batch, `transaction-inspect`, and `content`
directories. Before and after every content installation, before and after the
bundle installation, and immediately before a successful return, it must:

1. prove every retained descriptor is a live real directory in the retained
   `.work` ancestry;
2. reopen `.work` from checkout, batch from `.work`, `transaction-inspect` from
   batch, and `content` from `transaction-inspect` with no-follow semantics;
3. require every named reopening to match the retained device/inode identity;
4. close only the temporary comparison descriptors, retaining the common
   session lineage until the final check finishes.

Any deletion, rename, replacement, symlink substitution, or named-parent
remapping during the invocation fails with `WORK_PATH_UNSAFE`. A fresh safe tree
at the same lexical path is not accepted as continuation of the original
session. The implementation must write through the retained `content` or
`transaction-inspect` descriptors and the existing atomic installation logic;
it must not perform a sequence of independent public `stage_bytes` calls.

Unique content files are staged first in ascending digest order. `bundle.json`
is staged only after every content installation succeeds, the common lineage is
revalidated, and every declared unique content filename in that lineage is
reopened no-follow and compared with its exact expected bytes. After installing
or reusing the bundle, the session revalidates the common lineage and the
complete exact content-plus-bundle set before returning. Therefore a content
failure or a pre-bundle identity/completeness failure does not cause this
invocation to create or replace the bundle. If content succeeded but the bundle
conflicts, or an identity failure occurs after an installation, exact files and
created or displaced directories may remain as safe orphan staging objects.
The function never recursively rolls back or deletes batch content because
another exact caller may share digest-addressed files. Existing bundle/content
files are never overwritten, truncated, chmodded, or deleted.

An exact existing file is reused. The result has `already_staged=true` only
when every unique content file and the bundle were reported as already holding
the exact bytes during this invocation. If any file was created or an incomplete
exact layout was repaired, it is false. Different bytes at an existing path are
a conflict. A symlink, FIFO, socket, device, directory in a file slot, regular
file in a directory slot, checkout/`.work` replacement, deleted-open directory,
or containment failure is unsafe and fails closed under the existing staging
codes.

New directories request mode `0755`; new files request mode `0600`, both still
subject to the process umask and platform behavior. Exact reuse does not change
an existing mode. Modes are not serialized as authority, and this disposable
staging cache makes no crash-durability claim beyond the existing best-effort
fsync behavior.

The function returns only after the final same-lineage complete-set check.
Another local actor may change staging after that final check or after return;
this is not an operating-system sandbox. The pinned adapter's independent
no-follow pre/post transport checks remain required before trusting an
inspection.

## `video-paper-wiki.transaction-staging.v1`

The result is a closed portable object with exactly:

| Field | Rule |
| --- | --- |
| `schema` | literal `video-paper-wiki.transaction-staging.v1` |
| `batch_id` | exact validated batch ID |
| `operation_id` | exact facade operation ID |
| `operation_type` | `capture`, `ingest`, or `generic` |
| `transaction_declaration_sha256` | exact facade declaration digest |
| `bundle_file` | literal `transaction-inspect/bundle.json` |
| `bundle_sha256` | raw exact bundle SHA-256, equal to facade `input_bundle_sha256` |
| `bundle_size_bytes` | exact raw bundle size, 1..8,388,608 |
| `content_files` | unique physical content entries in ascending SHA-256 order |
| `already_staged` | exact invocation result described above |

Each closed content entry has `content_file`, `sha256`, and `size_bytes`.
`content_file` is exactly
`transaction-inspect/content/<sha256>`; the suffix equals its sibling
`sha256`. Digests are unique and strictly ascending. Size is 0..67,108,864.
The array has 1..1,024 entries. The result contains no checkout path, `.work`
path, Vault path, source path, input bytes, original/read bytes, receipt bytes,
credentials, environment, temporary name, timestamp, PID, device, or inode.

Schema validation alone cannot prove that a file exists. The semantic validator
checks ordering, uniqueness, content-file/digest equality, and the closed
field relationships available inside the object. Only the staging function
binds the object to a validated proposal and exact supplied byte maps.

## Stable failures and ordering

All pure transaction/staging-result failures use `ContractError`. Existing
staging filesystem failures remain `StagingError`; they are not remapped into a
generic contract code.

1. Invalid facade data: existing `SCHEMA_INVALID`, `TRANSACTION_*`, receipt,
   identity, or canonical JSON code; no checkout access.
2. Non-proposal phase: `TRANSACTION_UPSTREAM_MISMATCH`; no checkout access.
3. Invalid byte maps or payload correlation:
   `TRANSACTION_BYTES_MISMATCH`; no checkout access.
4. Invalid batch: existing `StagingError(INVALID_BATCH_ID)`; no checkout access.
5. Duplicate-digest byte disagreement, bundle encoding/correlation failure, or
   computed bundle SHA differing from `input_bundle_sha256`:
   `TRANSACTION_STAGING_MISMATCH`; no checkout access.
6. Bundle over 8,388,608 bytes: `TRANSACTION_LIMIT_EXCEEDED`; no checkout
   access.
7. Result schema or semantic mismatch: `SCHEMA_INVALID` or
   `TRANSACTION_STAGING_MISMATCH`; no checkout access when validating an object.
8. Checkout/path/type/containment failure, or any common-lineage identity or
   final-set failure: existing staging `WORKSPACE_ROOT_INVALID`,
   `WORK_PATH_ESCAPE`, or `WORK_PATH_UNSAFE`.
9. Exact-path different-byte conflict: existing `STAGING_CONFLICT`.

Expected details must not contain raw proposal, payload, original/read bytes,
credentials, or environment data. Existing local staging errors may identify
the local target path; successful portable results never do. There is no
fallback to an alternate batch, filename, inline-content bundle, writer,
upstream invocation, or Vault mutation after failure.

## Verification and release boundary

Architecture acceptance requires independent Builder and Repo Steward review,
schema/fixture validation, complete Python 3.12/3.13 regression tests, installed
wheel resource checks, an exact-path delivery manifest, fresh four-job
pull-request merge-ref CI, and a separate Architect acceptance for the exact
architecture head. Passing architecture checks authorizes only the separately
frozen implementation work package.

Implementation tests must cover at least:

- capture, generic genesis, later generic, and ingest proposals;
- exact compact bundle bytes, SHA, size, no BOM/newline, and parity with the
  accepted pinned inspect adapter;
- duplicate-write digest physical deduplication while preserving ordered bundle
  references;
- exact idempotent reuse, partial exact repair, and different-byte conflicts;
- content-before-bundle ordering, injected mid-content failure with no newly
  installed bundle, and exact final-set verification in one directory lineage;
- invalid proposal phase, exact built-in dict/bytes types, bad key sets,
  original/read mismatches, digest collisions with unequal bytes, and all
  inclusive facade/bundle limits;
- symlink, special file, directory/file slot, checkout/`.work`/batch/transport/
  content inode replacement before, between, and after file installations,
  including replacement between content files and between the final content
  and bundle; deleted-open directory, portable path, and ancestor/case/NFC
  collision regressions inherited from facade and staging;
- zero subprocess and zero network attempts;
- a real pinned public `transaction inspect` compatibility run over staged
  capture/generic/ingest transports in disposable Vaults, with complete Vault
  bytes/types/modes unchanged;
- validation deep-copy isolation, full existing adapter/manual-capture
  regressions, and installed-wheel schema/module availability.

This subrelease does not complete staged PDF/code proposal mapping,
operation-result handling, full-ledger or managed-prefix fixtures, remaining
BM25 compatibility, the ordered `integrity-runtime` slice, all of VPKB-001, PR
merge, or any human gate. Catalog and overlays remain 67, and
`base-catalog-v1` generation revision 1 remains unchanged because staging emits
no catalog rows.
