# VPKB-001 pinned manual PDF capture dry-run contract v1

## Status and authority

- Parent packet: `VPKB-001-adapter-contract`.
- Subrelease: `pinned-manual-pdf-capture-dry-run-v1`.
- Architecture baseline: `17c13f6317416f47d2610240aaf905598131e5bc`,
  the separately accepted first adapter implementation head.
- Upstream distribution/version: `claude-obsidian` `2.1.1`.
- Upstream commit/tree: `9f8c1199047eac2c3828496279fbb7ba9540b90b` /
  `b00665e266988fe99138e761dbbf4da04b2ddb5a`.
- Source snapshot: the same exact 21-file source-only snapshot
  `94148615f5aec9c137a7b449d869de0ca2a85e92e10581eafb7de4f799a18c34`.
- Static command profile:
  `claude-obsidian-capture-apply-dry-run-9f8c119-v1`.
- Machine authority title:
  `video-paper-wiki.upstream-capture-authority.v1`.

The hash values for this contract, profile and schema are frozen by the
architecture candidate manifest after independent review. A later byte edit
creates a different candidate and invalidates prior review.

## Purpose and exact boundary

This subrelease observes one manual PDF through the pinned public
`capture apply` command in its default dry-run mode. That command is required
instead of `capture plan` because only the dry-run `capture apply` response
contains the transaction operation and, for a create, the genuine
`approved_plan_sha256` calculated by the pinned public implementation.

The adapter accepts exactly one existing lowercase-`.pdf` source under the
default visible `inbox/`, authenticates the pinned upstream checkout, executes
the fixed public command from a fresh private source-only tree, projects its
host-dependent stdout into a closed portable observation, and constructs the
already-frozen `video-paper-wiki.capture-inspection.v1` declaration. It supports
only these outcomes:

1. **create dry-run**: no matching captured sibling exists; the upstream item
   proposes `.raw/captured/<payload-sha256>.pdf`, the operation has exactly one
   create write, and the inspection binds `upstream_plan_sha256` to the genuine
   `approved_plan_sha256`;
2. **reuse noop**: exactly one regular matching captured sibling exists, with
   any already-valid legacy suffix; the upstream operation has no writes and no
   approval fields, while the inspection has null operation/plan identifiers as
   required by the frozen capture contract.

This release covers one manual PDF route and the public capture dry-run
behavior needed by that route. It does not authorize `--apply`, transaction
apply/recover, capture queues, external adapters, implicit discovery, custom
capture configuration, legacy `.raw` sources, staged PDF/code routes, code
proposal binding, operation-result handling, ledger merge, integrity runtime,
network, models, admin commands, a real-Vault test, or publication. It emits no
catalog row and does not change generation revision 1.

## Public Python API

The implementation adds these functions to
`video_paper_wiki.upstream_adapter`:

```python
def inspect_pinned_manual_pdf_capture(
    *,
    source_path: str,
    operation_id: str,
    generated_at: str,
    upstream_root: Path | str,
    vault_root: Path | str,
) -> dict[str, object]: ...

def validate_upstream_capture_authority(
    document: object,
) -> dict[str, object]: ...
```

`source_path`, `operation_id`, and `generated_at` are required keyword-only
strings. No coercion, trimming, normalization, current-clock fallback, source
discovery, or environment-based Vault selection is permitted. Roots use the
same exact absolute, lexical, no-symlink and disjoint-root rules as the accepted
transaction adapter. The returned value and public validation result are deep
copies; the caller never receives internal mutable state.

## Argument grammar and fixed request

Validate all non-filesystem argument shape before authenticating roots or
reading any file.

- `source_path` is 1..1024 UTF-8 bytes, matches the existing portable path
  grammar in full, begins exactly `inbox/`, has at least one non-dot path
  segment after it, and ends exactly lowercase `.pdf`. Backslashes, absolute
  paths, empty/dot/dot-dot components, whitespace, Unicode, control/format
  characters, terminal line separators and NUL are refused. The final filename
  is at most 240 UTF-8 bytes and its stem before the first dot, compared in
  uppercase, is not `CON`, `PRN`, `AUX`, `NUL`, `COM1`..`COM9`, or
  `LPT1`..`LPT9`. These pinned upstream filename restrictions are phase-1
  `ADAPTER_PATH_INVALID`, rather than deferred upstream refusals.
- `operation_id` matches `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` in full and is
  copied unchanged.
- `generated_at` is an actual Gregorian UTC second spelled exactly
  `YYYY-MM-DDTHH:MM:SSZ`; fractional seconds, offsets, leap seconds, whitespace
  and non-calendar dates are refused.
- `upstream_root` and `vault_root` are existing absolute lexically normalized
  no-follow directories, are disjoint in both directions, and do not contain
  one another. The private allocation root is also disjoint from both.
- The Vault has no-follow directories `.obsidian`, `wiki`, `.raw`, and `inbox`.
  `.vault-meta` and its `capture` child may each be absent or a no-follow
  directory; `.vault-meta/capture/config.json` must be absent. This version
  therefore fixes the visible inbox to `inbox`, raw store to `.raw`, and
  legacy-raw discovery to its upstream default without accepting configuration
  semantics.

The child argv is exactly, in this order, with the explicit root/source values
substituted:

```text
<python> -I -B -X utf8 <private>/scripts/claude-obsidian.py
capture apply
--vault <vault-root>
--inbox inbox
--max-items 1
--max-total-bytes 67108864
--max-file-bytes 67108864
--operation-id <operation-id>
--generated-at <generated-at>
<source-path>
```

`--apply`, `--approved-plan-sha256`, additional sources/flags, queue commands,
external adapters, implicit discovery and environment selection are forbidden.
Child stdin is `DEVNULL`; cwd is the private scratch directory; no shell is
used.

## Upstream authentication and private execution

The new command profile is independent of the accepted transaction-inspect
profile even though both bind the same upstream commit/tree/version and exact
21 source files. It changes public command authority and therefore has its own
name and digest. The implementation must not widen, rewrite, or reinterpret the
old profile.

Authenticate the explicit checkout and construct the private execution tree
using the accepted v1 rules:

- exact commit and tree, no tracked or untracked Git changes, fixed version,
  fixed source-profile hash and exact source-snapshot formula;
- no-follow regular-file reads with exact size/hash for all 21 files;
- fresh mode-0700 allocation, only required ancestor directories, exact files
  created exclusively then sealed mode 0400;
- no bytecode, ignored files, caches, installed package, caller `PYTHONPATH`,
  user-site input or live-checkout import;
- exact pre/post tree enumeration and hashes, plus checkout authentication
  before and after the child;
- a replacement environment containing exactly `HOME`, `TEMP`, `TMP`, and
  `TMPDIR`, all equal to the fresh private scratch directory;
- bounded stdout/stderr, fixed timeout and fail-closed cleanup with no private
  path serialized in the authority or error details.

The output may contain the absolute upstream `operation.writes[0].content_file`
because that is pinned public behavior. The adapter verifies it equals the
selected source's canonical absolute path, but persists only raw stdout
SHA-256/size and the portable projection below. It never persists the absolute
path, raw stdout, approval hint, payload bytes, source path outside the Vault,
or a private execution path.

The checked-in valid authority fixture is a closed schema/semantic exemplar
from one disposable run. Its stdout digest and plan approval are host/Vault
identity dependent and are not cross-host goldens. Runtime tests derive those
values from their own authenticated disposable invocation.

## Source and captured-sibling snapshot

Before spawning the child, open the Vault and every fixed directory component
without following aliases. The source must be a regular no-follow file below
the fixed `inbox` directory. Read at most 67,108,864 bytes plus one refusal byte,
require size 5..67,108,864, SHA-256 the exact bytes, require `%PDF-` at byte zero,
and retain its device, inode, permission bits, size and nanosecond modification
time. The source filename extension and upstream metadata must remain `.pdf`.

Enumerate `.raw/captured` without following it. Absence is equivalent to an
empty directory for a create. If present it must be a no-follow directory. At
most 4096 directory entries may be inspected; exceeding that count is
`UPSTREAM_LIMIT_EXCEEDED`. Collect every direct child whose name begins with the
payload digest followed by `.`. At most one is accepted. Its path must satisfy
the frozen captured-path grammar. It must be a regular no-follow file whose
complete bytes are within the same 64 MiB limit and hash to the payload digest.
Symlinks, special files, multiple matches, malformed matching names or wrong
bytes are `CAPTURE_SNAPSHOT_INVALID`. Persist its permission bits in the
capture-inspection sibling object. Irrelevant nonmatching entries are counted
for the enumeration limit but are not authority data.

After the pre-child Vault baseline has been obtained, record a closed private
snapshot of the Vault root/sentinels, absent config, source, captured directory
and matching sibling identities/types/modes/sizes/hashes before the child.
Repeat it after every success or mapped failure. Any
change, disappearance, replacement, new matching sibling, config appearance,
source change, or directory-entry count change is
`UPSTREAM_CONTRACT_MISMATCH`. All successful and refused tests assert that the
complete disposable Vault tree is byte/type/mode equal before and after.

This is a point-in-time non-mutating observation. It does not claim an OS
sandbox against a privileged same-host actor and does not prove that the plan
will still match during a later apply.

## Public stdout contract

Successful stdout is one strict UTF-8 JSON object followed only by RFC 8259
whitespace, at most 8,388,608 bytes; stderr is empty. Duplicate keys, floats,
non-finite numbers, integers over 1024 digits, trailing data, extra/missing keys
or the wrong case are refused. The exact pretty bytes are represented only by
`transport.stdout_sha256` and `transport.stdout_size_bytes`.

There is exactly one `items` entry. Its exact fields are `schema`, `adapter`,
`source_identity`, `source`, `stored_path`, `would_change`, `skip_reason`,
`execute`, and `metadata`. Values are fixed/correlated as follows:

- `schema=claude-obsidian.filesystem-capture-plan.v1`,
  `adapter=filesystem`, `execute=false`;
- `source`, `source_identity`, `stored_path`, `would_change` and `skip_reason`
  equal the request and pre-child snapshot;
- metadata has exactly `name`, `extension`, `size_bytes`, `sha256`, `kind`,
  `media_type`, `detected_by`; the fixed values are `.pdf`, `pdf`,
  `application/pdf`, `magic`, with name/size/hash equal to the source.

The operation has exactly `schema`, `operation_id`, `operation_type`,
`expected_hashes`, `writes`, `address_requests`, and
`source_manifest_updates`; schema/type/id are fixed, and the latter two
collections are empty.

For create, top-level keys are exactly `schema`, `status`, `items`, `operation`,
`approved_plan_sha256`, `generated_at`, and `approval_hint`; status is
`dry-run`. There is one expected-hash entry mapping stored path to null and one
write with exact `path`, `mode=create`, `content_file`, and `sha256`. The
approval is lowercase SHA-256, generated time equals the request, and the hint
must exactly embed that digest in the pinned upstream sentence. The adapter
does not represent the hint in authority data.

For reuse, top-level keys are exactly `schema`, `status`, `items`, and
`operation`; status is `noop`. Expected hashes and writes are empty, and
approval/generated-at/hint keys are absent. The upstream operation still echoes
the request operation ID, but the frozen capture inspection correctly sets its
operation ID and upstream plan SHA to null because no transaction is proposed.

## Authority schema and correlations

`video-paper-wiki.upstream-capture-authority.v1` is a closed object with exactly
these required fields:

| Field | Content |
| --- | --- |
| `schema` | exact authority title |
| `profile` | exact new command profile name |
| `upstream` | fixed distribution/version/commit/tree, clean=true, exact profile and source-snapshot hashes |
| `request` | closed route/source/operation/time plus exact fixed budget |
| `transport` | raw stdout SHA-256 and byte count only |
| `observation` | closed portable projection of item, operation, and nullable upstream approval/time |
| `inspection` | full `$ref` to `video-paper-wiki.capture-inspection.v1` |

The portable observation normalizes create/noop to the same closed shape:

- `status`: `dry-run` or `noop`;
- `item`: the complete portable item projection and closed metadata;
- `operation`: schema/id/type plus `expected_path` and nullable closed `write`;
- `approved_plan_sha256` and `generated_at`: populated only for create, otherwise
  null.

Semantic validation performs full-string/type checks and all correlations, then
recomputes `capture_approval_hash(inspection)`. Both branches require
`route=manual-inbox`, PDF media, null proposal SHA, request source equality,
payload/source/item/metadata hash and size equality, exact captured target and
the full sibling snapshot.

Create additionally requires empty siblings, `would_change=true`, status
dry-run, null skip, exact one create write/expected path, inspection operation
ID equal request, inspection upstream plan SHA equal the genuine approval, and
observation generated time equal request. Reuse requires exactly one valid
sibling, `would_change=false`, status noop, skip `content-unchanged`, null
write/expected path/approval/time, and null inspection operation/plan values.

The object-only `validate_upstream_capture_authority` entry point maps JSON
preflight and schema-shape failures to `SCHEMA_INVALID`. After schema admission,
any nested capture-inspection semantic failure or authority cross-field failure
is normalized to `UPSTREAM_CONTRACT_MISMATCH`. It never exposes the nested raw
message/details. The central title dispatch applies the same rules.

The authority proves this bounded dry-run observation. It is not a transaction
facade, applied result, operation receipt, source-ledger entry, human approval,
publication authorization, or canonical generation output. A later staged
route must construct deterministic `.work/.../bundle.json + content/<sha>`
transport and use the separately accepted transaction-inspect adapter; this
authority must never masquerade its absolute-path upstream operation as that
transport.

## Error order and stable codes

All expected failures use `ContractError`. Error details may contain only fixed
field names, upstream code and exit code where specified. They never contain
absolute roots, source/payload bytes, stdout/stderr, approval/hint, credentials,
private paths or caller environment values.

1. Pure argument grammar/type/calendar validation: `ADAPTER_PATH_INVALID`, exit
   2; no filesystem/process access.
2. Absolute roots, disjointness, fixed Vault layout and absent config:
   `ADAPTER_PATH_INVALID` or `UPSTREAM_VAULT_INVALID`, exit 2.
3. Profile/Git/source/private-tree authentication: `UPSTREAM_PIN_MISMATCH`, exit
   2.
4. Source PDF and captured snapshot: `CAPTURE_SNAPSHOT_INVALID`, exit 2;
   byte/count/output limits use `UPSTREAM_LIMIT_EXCEEDED`, exit 2.
5. Spawn/timeout/signal/unknown exit or malformed failure transport:
   `UPSTREAM_EXECUTION_FAILED`, exit 1.
6. A well-formed upstream exit 75 becomes `UPSTREAM_CONFLICT`, exit 75. A
   well-formed exit 2 becomes `UPSTREAM_INSPECT_REFUSED`, exit 2. Details contain
   only `upstream_code` matching `[A-Z][A-Z0-9_]{0,63}` and the exact exit code.
7. Nonempty stderr on success, malformed/extra output, projection mismatch,
   source/Vault/pin/private-tree postcheck failure, cleanup failure, or invalid
   constructed authority: `UPSTREAM_CONTRACT_MISMATCH`, exit 2.

There is no fallback route, direct private capture API, local imitation of the
upstream approval algorithm, permissive parser, or execution retry.

## Builder implementation and acceptance boundary

Production remains blocked until the exact architecture-freeze commit passes a
fresh Linux/macOS x Python 3.12/3.13 merge-ref matrix and receives a separate
Architect acceptance. The subsequent Builder work package may allow only:

- `src/video_paper_wiki/upstream_adapter.py`;
- title-scoped semantic dispatch in `src/video_paper_wiki/contracts.py`;
- focused unit, contract, upstream and security tests for this subrelease;
- subrelease-specific fixture/evidence paths.

The new schema, profile, this contract, old v1 contract/schema/profile/fixtures,
capture schema/helpers, facade, vendor gitlink, dependencies, workflow, CLI,
catalog, seed and generation profile are frozen inputs. The accepted v1 public
APIs, constants, profile selection, error order, output behavior, tests and
goldens are immutable compatibility requirements. The complete
`src/video_paper_wiki/upstream_adapter.py` file is deliberately a shared allowed
path: Builder may add branch-isolated capture helpers/APIs there, but must not
widen or alter any accepted v1 semantic. Builder reports a contract gap instead
of changing a frozen input.

Acceptance includes real pinned create/noop dry-runs in disposable Vaults,
exact stdout/projection goldens, all grammar/config/source/sibling/race/limit/
child failure cases above, hostile environment and ignored-bytecode regression,
deep-copy validation, zero network attempts, and complete byte/type/mode Vault
stability on every path. Run focused tests, then the complete locked suite on
local Python 3.12/3.13. Build/install a fresh offline wheel and prove the new
schema/profile and adapter code are byte-equal to the checkout and missing
upstream fails closed without download. Repo Steward independently reviews the
exact source snapshot and delivery, then fresh four-job CI and post-CI Architect
acceptance bind the implementation head.

Passing this subrelease still leaves staged PDF/code routes, code proposal
binding, operation-result handling, full-ledger/managed-prefix fixtures, the
remaining limits/BM25 compatibility work, and the ordered integrity-runtime
slice. It does not complete VPKB-001 or authorize PR state changes, merge, or a
human gate.

This contract targets the accepted POSIX/macOS/Linux private-tree mode. It does
not claim a Windows implementation for this subrelease.
