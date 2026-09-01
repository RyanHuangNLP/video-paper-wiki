# VPKB-001 staged PDF capture inspect contract v1

Status: revision 1 architecture candidate. Architect: Codex
(`gpt-5.6-sol`, `ultra`). Packet baseline:
`fb2cbcb565195a232f22d02c0474ac1b1b34f7d3`.

This is the fourth bounded subrelease in VPKB-001's ordered
`adapter-contract` slice. The accepted predecessors authenticate the pinned
read-only transaction inspector, observe the public manual-PDF capture dry-run,
and stage an already valid transaction facade deterministically. This release
connects the existing paper `prepare` flow to those accepted boundaries for the
`staged-capture` PDF route.

It does not apply a transaction, invoke `vpwiki-admin`, mutate a Vault, fetch a
URL, parse with Docling, publish ingest records, derive source IDs, attach a
runtime result, merge a ledger, audit managed state, build an index, alter the
manual route, or close a human gate. The agent-facing command remains zero
egress. Its create branch writes only deterministic files below the current
checkout's `.work/**`; its reuse branch writes nothing and starts no child.

The third subrelease implementation is accepted at exact head
`fb2cbcb565195a232f22d02c0474ac1b1b34f7d3`, tree
`4a28ee53f71a0f2971f23b87e1f4c06d3bdf5b79`. Fresh Tests run
`33491834331` checked merge preview
`12bc7925140352fad516405b7eafaa8923d106e7`; all four Linux/macOS x Python
3.12/3.13 jobs passed 1895 tests. Its three post-CI records are immutable
successor inputs with SHA-256 values:

- `transaction-inspect-staging/implementation/ci-observation.json`:
  `794d1fe6a5889c2bbbb5b873dc09e4e043b15de152dd6666a231662895a7644d`;
- `transaction-inspect-staging/implementation/merge-parents.json`:
  `7b73ede5922cfe3c5604f17dfbab81407b14480f8523afc7a34af9f3b7c51908`;
- `transaction-inspect-staging/implementation/architect-acceptance.json`:
  `269deabc8f4dda1681b8c51300685b4d5fa37a4051a61c77a5017dc4e0c78087`.

Carrying those exact bytes does not make their historical CI result apply to a
new architecture or implementation head.

## Frozen public surface

The Builder adds `src/video_paper_wiki/staged_capture.py` with:

```python
def validate_staged_pdf_capture_request(document: object) -> dict[str, object]: ...

def validate_staged_pdf_capture_authority(document: object) -> dict[str, object]: ...

def inspect_staged_pdf_capture(
    *,
    prepared: Path | str,
    operation_id: object,
    upstream_root: Path | str,
    vault_root: Path | str,
) -> dict[str, object]: ...
```

Both validators are object-only, read no paths, start no process, change no
state, and return deep independent copies. Central `validate_document`
dispatches their title-scoped semantic checks.

The existing public `stage_bytes`, `stage_transaction_inspect_transport`,
`inspect_pinned_transaction`, manual-capture APIs, and all accepted result bytes
remain compatible. The Builder also exposes one additive pure encoder in
`video_paper_wiki.transaction_staging`:

```python
def encode_transaction_inspect_bundle(material: object) -> bytes: ...
```

`material` is an exact built-in dictionary with exactly `operation_id`,
`operation_type`, `writes`, `expected_hashes`, and `read_preconditions`.
`writes` is an exact list of exact dictionaries containing exactly `path`,
`mode`, and `sha256`. The function validates the bounded operation grammar,
the three admitted operation types, portable paths, create/replace modes,
lowercase hashes, exact map key correlation, and integer-only JSON data. It
then produces the already frozen compact upstream bundle, deriving each
`content_file` as `content/<sha256>` and fixing `address_requests=[]` and
`source_manifest_updates={}`. It performs no I/O and grants no execution or
approval authority.

The accepted staging function must use this encoder and retain byte-for-byte
parity with all accepted vectors. The staged PDF proposal builder uses the same
encoder before filling `input_bundle_sha256`. The transaction adapter's
existing private compatibility wrapper must also delegate to this encoder and
remap an impossible post-proposal encoder failure to its existing caller-chosen
upstream mismatch code. Thus staging, staged capture, and adapter transport
comparison share one encoder while their already accepted public error domains
and bytes remain unchanged.

The encoder's pure failure order is frozen. It first rejects cycles,
non-string object keys, non-JSON values, floats, and bools where a string or
integer scalar is required with `SCHEMA_INVALID`. It then checks the exact
built-in container/key shapes and bounded operation ID/type, followed by write
descriptor path/mode/hash rules, portable path collisions, exact
expected-hash/write-key correlation, and read/write disjointness using the
corresponding existing `TRANSACTION_*` codes. Compact UTF-8 JSON encoding
failure is `TRANSACTION_STAGING_MISMATCH`. The encoder returns the exact bytes
without applying the 8,388,608-byte policy itself. Each caller applies that
limit after its required digest correlation: the accepted staging API must
continue to report an input-bundle digest mismatch before an oversize error,
while staged capture computes the digest, records it in the proposal, and then
rejects oversize with `TRANSACTION_LIMIT_EXCEEDED`. This preserves the accepted
staging error order. Every encoder failure occurs without filesystem, process,
environment, network, or global-state access. There is no separate
read-precondition count; the caller's exact encoded bundle byte check remains
the bound.

The existing CLI leaf becomes:

```text
vpwiki capture inspect \
  --prepared <path> \
  --operation-id <id> \
  --upstream-root <absolute-path> \
  --vault-root <absolute-path>
```

All four flags are required and abbreviation remains disabled. `prepared` may
be relative to the current checkout or absolute, but after lexical
normalization it must be exactly
`.work/<batch>/prepared/staged-pdf-capture-request.v1.json` under the current
checkout. The batch is derived from this path; there is no separate batch,
digest, plan, blob, work-root, bundle, target, suffix, apply, cleanup, network,
or overwrite option. `upstream_root` and `vault_root` must be existing absolute
no-follow directories and disjoint from each other and from the current
checkout/work root under the accepted adapter rules. Reuse still validates
their argument shape and root separation but does not authenticate upstream
source or start a subprocess.

## Prepare request publication

For `paper-source` only, the existing `vpwiki ingest prepare --plan ...
--approval-ref ...` additionally publishes this fixed pair:

```text
.work/<batch>/prepared/<input-sha256>.blob
.work/<batch>/prepared/staged-pdf-capture-request.v1.json
```

The code-evidence prepare behavior remains unchanged. A paper plan may use
`input.kind=local-blob` or `input.kind=arxiv`. For either kind the already
required external, desensitized approval-ref supplies `input_sha256`; when the
plan also contains `input.local_sha256`, all three digests must agree. A plan's
`approval_hash` is still only its JCS integrity digest. The approval-ref is an
external binding and is not a signature, proof of human approval, permission to
apply, or evidence that the agent issued authorization.

Before publication, prepare must validate the plan and pipeline, parse and bind
the exact approval-ref, read the exact blob under the approved byte bound,
recompute its digest, and validate PDF magic, parseability, encryption status,
page count, and the plan/hard limits. Plan bytes must equal
`canonicalize(validated_plan)` exactly. The request embeds the parsed nine-field
approval-ref object, never its source path or unparsed bytes.

Paper prepare uses one retained checkout -> `.work` -> batch -> `prepared`
session. The same session retains the sibling `plan` directory and proves the
canonical plan file identity and bytes before request construction, before and
after each installation, and immediately before success. It installs or reuses
the digest-addressed blob first and the canonical request bytes last. Before
success it reopens every named edge no-follow, requires the retained
device/inode identities, and verifies both fixed regular files contain the
exact expected bytes. Two independent `stage_bytes` calls are forbidden.

Exact files are idempotently reused. A missing blob may be repaired before an
exact existing request is accepted. Different bytes, a wrong type, an unsafe
extra entry in either fixed file slot, or any named-lineage replacement fails
closed. Blob success followed by request failure may leave the exact blob as a
safe orphan. The code never recursively rolls back or deletes another caller's
digest-addressed data. The success envelope adds request path, request digest,
and pair-level `already_staged`; no absolute path is placed inside the request.

## `video-paper-wiki.staged-pdf-capture-request.v1`

The request is canonical JCS with no self hash. It has exactly:

| Field | Rule |
| --- | --- |
| `schema` | literal request title |
| `batch_id` | accepted batch grammar |
| `plan` | closed canonical plan descriptor below |
| `approval_ref` | exact parsed nine-field `approval-ref.v1` object |
| `approval_ref_sha256` | SHA-256 of JCS(parsed approval-ref) |
| `payload` | closed prepared PDF descriptor below |

The plan descriptor has `file=plan/ingest-plan.v1.json`, raw canonical-file
`sha256`, `size_bytes`, `approval_hash`, `plan_kind=paper-source`,
`stable_subject_id`, `input_kind` (`local-blob` or `arxiv`),
`limits_sha256`, `network_targets_sha256`, and `pipeline_fingerprint`.
Network targets are bound exactly but do not grant this command network access;
an arXiv fetch remains an earlier operator action.

The payload descriptor has
`file=prepared/<approval_ref.input_sha256>.blob`, matching `sha256`, exact
`size_bytes`, `media_type=application/pdf`, and exact `page_count`. Size is
5..min(plan max, 64 MiB), pages are 1..min(plan max, 300), and bytes start with
`%PDF-` and parse as a non-encrypted PDF.

The object-only semantic validator recomputes `approval_ref_sha256`, checks the
descriptor-internal and approval-ref field correlations, and enforces batch,
kind, stable-subject, input and file-name/digest equality available inside the
request. It cannot recompute a descriptor from bytes the object does not
contain. Prepare and capture inspect separately read the canonical plan and PDF
bytes, recompute both descriptor hashes plus the plan integrity, pipeline,
limit and network digests, call `bind_approval_ref`, and establish that the
serialized files exist in the retained lineage.

## Retained inspection inputs and Vault snapshot

After all pure argument checks, `inspect_staged_pdf_capture` opens one retained
current-checkout/`.work`/batch session without creating missing input
directories. Through that session it reads at most 1 MiB of the fixed request
and plan and the bounded fixed blob. It requires canonical request and plan raw
bytes, validates both documents, repeats approval-ref binding and PDF checks,
and retains checkout, work, batch, plan, prepared, request, plan-file and blob
identities. It reopens every named edge and compares identity and exact bytes at
every branch boundary, immediately before and after transaction staging,
immediately before and after pinned inspection, on every caught downstream
error, and immediately before success.

The transaction staging composition receives the same live retained batch
session. Its internal staging primitive writes `transaction-inspect/**`
through descriptors descended from that retained batch and rechecks the common
checkout/work/batch identity around every install. The accepted standalone
public staging function opens its own equivalent session and keeps its existing
signature and behavior. This additive internal mechanism prevents a successful
wrapper from combining plan/blob/request from one batch inode with transport
from another. Exact deterministic staging may remain after any later failure;
it is reusable and is not rolled back.

`src/video_paper_wiki/captured_snapshot.py` owns one staged-route snapshot
primitive rather than importing the manual source/inbox snapshot. It opens and
retains `vault_root`, `.raw`, and optional/existing `captured` directories
no-follow. It enumerates the complete captured directory with a hard maximum of
1024 entries and selects names beginning `<payload-sha256>.`. A matching name
must satisfy the frozen portable captured-path grammar. Zero matches means
create. Exactly one no-follow regular, byte-matching entry means reuse and
preserves its real suffix and mode. Multiple matches, malformed matches,
symlinks, directories, special files, digest mismatch, read drift, or a bound
violation fails `CAPTURE_SNAPSHOT_INVALID` or the existing limit code.

The session records retained directory and matching-file identity, mode, size,
mtime and bytes plus the complete entry-name/type identity inventory. It
reopens all named edges and reproduces the complete snapshot around staging and
child boundaries and on all exits. Any observed change overrides a downstream
result with a sanitized snapshot mismatch. The pinned adapter continues its
own accepted transport/Vault checks during the child. These checks detect
changes observed at their boundaries; they do not claim an OS sandbox against
an actor able to replace and restore byte-identical trees entirely between
system calls.

## Create and reuse branches

`operation_id` is validated before filesystem access and is always preserved
as wrapper `requested_operation_id`.

Reuse has one unique matching sibling. It constructs a valid
`capture-inspection.v1` with `route=staged-capture`, PDF payload,
`source_path=null`, `proposal_sha256=null`, the real sibling path and snapshot,
`would_change=false`, `operation_id=null`, and
`upstream_plan_sha256=null`. It computes the existing local capture approval
hash. The wrapper has `disposition=reuse` and both downstream fields null. It
does not build a facade proposal, encode or stage a bundle, authenticate the
upstream pin, allocate a child tree, start a process, contact a network, or
write `.work`/Vault.

Create has no matching sibling. The only target is
`.raw/captured/<payload-sha256>.pdf`. It builds exactly this facade proposal:

```text
schema=video-paper-wiki.transaction-facade.v1
phase=proposal
operation_id=requested_operation_id
operation_type=capture
writes=[one business create descriptor for the fixed target and payload]
expected_hashes={target: null}
read_preconditions={}
claimed_inputs=[]
address_requests=[]
source_manifest_updates={}
engine_expanded_paths=[]
receipt=null; head=null; inspection=null; runtime_result=null
```

The write uses payload hash/size, `original_size_bytes=0`, and
`original_mode=null`. The shared encoder produces exact bundle bytes; their raw
SHA-256 becomes `input_bundle_sha256`. The existing
`transaction_declaration_hash` then becomes `declaration_sha256`, after which
the complete proposal must validate.

The wrapper stages exact maps `{target: payload}`, `{target: None}`, and `{}`
inside the retained batch session, then invokes the accepted pinned read-only
transaction inspector against that fixed staged bundle. No apply flag exists.
The returned authority transaction must be the inspected form of the exact
proposal. The final capture inspection has the deterministic target,
`would_change=true`, the requested operation ID, no siblings, and
`upstream_plan_sha256` equal to
`upstream_authority.transaction.inspection.approval_sha256`.
`proposal_sha256` remains null because the previously frozen PDF capture schema
uses that field only for code-evidence proposals. The existing capture approval
hash is computed last.

If staging succeeds and pinned inspection fails, the exact staging remains;
the function returns no success authority and never rolls back or touches the
Vault. A retry with unchanged inputs reuses those exact bytes.

## `video-paper-wiki.staged-pdf-capture-authority.v1`

The portable wrapper has exactly:

| Field | Rule |
| --- | --- |
| `schema` | literal authority title |
| `requested_operation_id` | exact validated caller value |
| `request_file` | literal `prepared/staged-pdf-capture-request.v1.json` |
| `request_sha256` | SHA-256 of exact JCS embedded request |
| `request` | complete validated staged PDF request |
| `disposition` | `create` or `reuse` |
| `inspection` | complete `capture-inspection.v1` |
| `transaction_staging` | complete staging result for create, null for reuse |
| `upstream_authority` | complete pinned authority for create, null for reuse |

The result contains no absolute path, input bytes, inode/device, temporary
path, PID, environment, credential, token, raw approval-ref source bytes, or
timestamp.

The semantic validator recomputes the request and capture approval hashes and
all request correlations. For both branches it binds batch, payload, route,
stored path and `requested_operation_id`. Reuse enforces the exact noop shape
and two nulls. Create validates both children, then cross-binds operation/type,
target/write order/mode/hash/size/original state, declaration digest, staging
batch/content/bundle, authority transport bundle/content/stdout, inspected
transaction, capture inspection and upstream approval SHA. Any missing, extra,
crossed, reordered or independently valid but unrelated child fails
`STAGED_CAPTURE_RESULT_MISMATCH`.

## Failure order and sanitation

Pure operation/path/root shape and disjointness checks precede filesystem
access. Request path/session checks precede JSON/schema semantics; request
semantics precede plan/blob reads; plan semantics precede payload/PDF checks;
those precede Vault enumeration. Reuse finishes after final input/Vault
postchecks. Create then orders proposal/encoder validation, retained staging,
pinned inspection, wrapper correlation, and final postchecks.

Existing `ContractError`, `ApprovalError`, `StagingError`, secure-I/O,
capture-snapshot and pinned-adapter codes remain visible. New local semantic
codes are `STAGED_CAPTURE_REQUEST_MISMATCH` and
`STAGED_CAPTURE_RESULT_MISMATCH`. A final input/Vault identity or byte drift
overrides an earlier downstream exception with the corresponding sanitized
unsafe/snapshot mismatch, because the original result no longer describes the
retained inputs. Error details never include raw bytes, the full request or
approval-ref, credentials, environment, child stdout/stderr, or private temp
paths. Existing local path errors may name the caller's local argument.

## Verification and release boundary

Implementation must cover request schema semantics and deep-copy isolation;
local-blob and arXiv approval-ref binding; canonical plan/request bytes;
prepare idempotence, partial repair, conflicts and blob-first/request-last
publication; replacements of checkout/work/batch/plan/prepared and both fixed
files before, between and after installs; PDF magic, parsing, encryption,
inclusive byte/page limits; exact path and CLI isolation; complete Vault
sibling create/reuse/multiple/mismatch/symlink/special/identity races; retained
batch replacement around staging and child; exact shared encoder vectors and
accepted staging regression; create cross-binding through a real pinned public
transaction inspect in disposable Vaults; reuse proof of zero process/network/
write attempts; downstream-failure staging reuse; closed stdout and sanitized
errors; Python 3.12/3.13 full regressions; and installed-wheel schema/module
availability.

Architecture acceptance requires independent Builder and Repo Steward review,
schema/fixture validation, full locked local suites, an exact-path manifest,
fresh four-job PR merge-ref CI, and a separate Architect decision bound to the
exact architecture head. That acceptance authorizes only a separately frozen
Builder implementation package.

This subrelease does not complete staged code capture, operation-result
handling, full-ledger/managed-prefix fixtures, remaining BM25 compatibility,
the `integrity-runtime` slice, VPKB-001, PR merge, or any human gate. Catalog
and overlays remain exactly 67 and `base-catalog-v1` remains revision 1.
