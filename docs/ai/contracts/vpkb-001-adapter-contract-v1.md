# VPKB-001 pinned upstream inspection adapter v1

Revision: 1 freeze candidate. Architect: Codex (`gpt-5.6-sol`, `ultra`).
Builder and Repo Steward review this exact candidate before it may be committed.
Packet baseline: `acd3821b15e62bce13fa07b82c1665d501f27f67`.

This is the first bounded subrelease in VPKB-001's ordered
`adapter-contract` verification slice. It authenticates the pinned
claude-obsidian checkout, invokes only its public read-only
`transaction inspect` CLI, binds the returned plan to the frozen transaction
facade, and permits one isolated call to `stable_source_id` for captured files.
It does not implement capture/apply/recover, an admin binary, ledger merge,
receipt or managed-prefix audit, a mapper/compiler, Docling, BM25/index
publication, or any real-Vault mutation.

The schema and static profile in this freeze are machine-readable contract
resources. Production adapter code remains blocked until this architecture
candidate has a commit, fresh four-job merge-ref CI, and a separate Architect
acceptance for that exact head.

## Fixed authority

The only supported upstream is an explicitly supplied, existing checkout with:

- distribution `claude-obsidian`, version `2.1.1`;
- commit `9f8c1199047eac2c3828496279fbb7ba9540b90b`;
- tree `b00665e266988fe99138e761dbbf4da04b2ddb5a`;
- empty `git status --porcelain=v1 --untracked-files=all`;
- every file and digest in
  `catalog/claude-obsidian-transaction-inspect-9f8c119-v1.profile.json`.

There is no download, installed-distribution fallback, alternate commit,
editable import, `PYTHONPATH` discovery, or caller-selected source list. Before
and after each upstream Python invocation, the adapter checks commit, tree,
clean status, profile bytes, and the complete profile file snapshot. The fixed
profile and verified `claude_obsidian/__init__.py` bytes authenticate version
`2.1.1`; no Python code is imported from the live checkout to discover it. An
exact clean checkout may live outside this repository; its absolute host path
is execution input and is never serialized into the authority document.

The live checkout is provenance input, never the Python execution root. For
each public CLI or source-ID child, the adapter creates a fresh private
temporary directory with mode `0700`, outside `upstream_root`, `work_root`, and
`vault_root`. It builds an execution tree containing exactly the 21
`verified_files` paths from the fixed profile. Source path components are read
without following symlinks; every leaf must be a regular file with the exact
profile size and SHA-256. Destination directories are created with mode `0700`.
Each destination leaf is created exclusively, written from those already
verified bytes, and sealed mode `0400`. No ignored file, bytecode cache,
`__pycache__`, installed package, or other checkout content is copied.

The same private allocation contains a fresh mode-`0700` scratch directory
that is disjoint from the 21-file execution tree and from all three caller
roots. The `env` mapping supplied to the subprocess replaces, rather than
extends, the caller environment and contains exactly `HOME`, `TEMP`, `TMP`, and
`TMPDIR`, each set to that scratch directory. No caller `PATH`, Python variable,
Vault selector, locale, credential, proxy, or temporary-directory setting
reaches the child. A platform Python may synthesize its own runtime locale
entry (for example `LC_CTYPE`) after process creation; it is not part of the
supplied mapping, must not preserve a caller value, and conveys no path or
credential.
The absolute `sys.executable`, `-I`, and `-X utf8` make those inherited settings
unnecessary. The scratch path and contents are transient and are never
serialized.

Before starting the child, the adapter verifies that the execution tree has
exactly the profiled paths and hashes and no extra entry. After the child exits,
it performs that same execution-tree verification and then rechecks the
original checkout's commit, tree, clean status, profile bytes, and source
snapshot. It removes the private tree in a `finally` path; failure to create,
verify, or remove it fails closed and never changes staging or Vault data. The
private path is not serialized or exposed in error details.

Git, source, and private-snapshot checks close the ordinary ignored-`.pyc` and
import-shadow routes and detect drift before and after execution. They are not
an OS sandbox against a privileged actor that can swap and restore bytes during
a process. The adapter makes no stronger tamper-resistance claim.

The public process argv is exactly:

```text
<sys.executable> -I -B -X utf8 <private-execution-root>/scripts/claude-obsidian.py
transaction inspect <absolute-bundle.json> --vault <absolute-vault-root>
```

Use an argv list with `shell=False`, a fixed timeout of 30 seconds, the exact
replacement environment above, `cwd` equal to the private execution root, and bounded
captured stdout/stderr. The verified public script's `__file__` is therefore
inside that root; its fixed `PLUGIN_ROOT` insertion makes every imported
`claude_obsidian` module resolve from the same exact source-only tree. Do not
invoke module entry points, `apply`, `recover`, capture, init/adopt, lint, BM25,
hooks, or any admin wrapper from this module.

## Deterministic staging transport

The public API receives an explicit absolute `work_root`. It must be an existing
no-follow directory named `.work`. `bundle_path` must be the exact lexical path
`<work_root>/<batch-id>/transaction-inspect/bundle.json`, where `batch-id` uses
the existing staging grammar. Every existing component from `work_root` through
the bundle and content directory is opened without following symlinks. The
adapter never creates, edits, replaces, chmods, or deletes staging files.

The bundle is a no-follow regular file, at most 8,388,608 bytes, encoded as UTF-8
without BOM, floats, duplicate keys, invalid Unicode, or trailing data. Its raw
bytes must be exactly:

```python
json.dumps(
    bundle,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
```

There is no trailing newline. This exact encoding equals the pinned upstream
`bundle_sha256` domain; its raw SHA-256 must equal both
`proposal.input_bundle_sha256` and the returned plan's
`input_bundle_sha256`. It is not the upstream plan/approval digest.

The bundle has exactly these top-level fields, with no extras:

1. `schema = "claude-obsidian.transaction.v1"`;
2. `operation_id` and `operation_type`, exactly as in the facade proposal;
3. `writes`, in facade order;
4. `expected_hashes` and `read_preconditions`, exactly as in the proposal;
5. `address_requests = []` and `source_manifest_updates = {}`.

Each bundle write has exactly `path`, `mode`, `content_file`, and `sha256`.
`path`, `mode`, and `sha256` equal the corresponding facade write.
`content_file` is exactly `content/<sha256>`: lowercase ASCII, bundle-relative,
without suffix, alternate spelling, backslash, absolute path, empty/dot/dotdot
segment, or Unicode alias. Inline `content` is outside this profile. Each unique
content path is a no-follow regular file; each write's declared size and SHA-256
must match its bytes. Equal-byte writes reuse the same content path, while the
authority transport array still contains one entry per facade write in facade
order. Existing facade limits remain authoritative: at most 1,024 writes,
64 MiB per new file, and 128 MiB total new bytes.

Because managed requests are empty, `input_bundle_sha256` and
`expanded_bundle_sha256` must be equal, and `engine_expanded_paths` remains
empty. This first profile supports only facade operation types `capture`,
`ingest`, and `generic`; it neither registers nor maps another upstream type.

`upstream_root`, `work_root`, `vault_root`, and `bundle_path` are explicit,
absolute, lexically normalized `str` or `Path` values. The three roots must be
existing no-follow directories. `vault_root` must be disjoint from `work_root`
and `upstream_root`; it cannot be either root, an ancestor, or a descendant.
The Vault must already exist because the frozen facade accepts only an existing
`vault_identity`. The adapter reads current targets/preconditions through the
pinned public inspect implementation; it performs no permission-changing probe
and does not claim atime stability.

## Public Python API

The Builder implements `src/video_paper_wiki/upstream_adapter.py` with these
interfaces:

```python
def inspect_pinned_transaction(
    proposal: object,
    *,
    upstream_root: Path | str,
    work_root: Path | str,
    vault_root: Path | str,
    bundle_path: Path | str,
) -> dict[str, object]: ...

def validate_upstream_authority(document: object) -> dict[str, object]: ...

def verify_pinned_source_id(
    stored_path: str,
    source_identity: str,
    *,
    upstream_root: Path | str,
    expected_source_id: str | None = None,
) -> str: ...
```

`inspect_pinned_transaction` validates `proposal` first, before any filesystem
or process access. It accepts only a valid facade `phase=proposal`. It then
checks path authority, pin/profile, deterministic transport, and Vault root;
runs the one public command; validates the exact success output; calls the
existing `attach_upstream_inspection`; and returns a new
`video-paper-wiki.upstream-authority.v1` object. Caller objects are never
mutated, and the returned nested transaction shares no mutable container with
the proposal or parser intermediates.

`validate_upstream_authority` loads only immutable packaged schema/profile
resources, validates all schema and cross-field rules, and returns a deep copy.
It does not read caller paths, start a process, contact a network, or treat the
document as proof that an operation ran. Central `validate_document` dispatches
the same object-only semantic checks for this schema after the Builder release.

`verify_pinned_source_id` supports only the development plan's authorized call:

```text
stable_source_id("file", stored_path, source_identity)
```

`stored_path` must be a canonical
`.raw/captured/<source_identity>.<suffix>` path accepted by the frozen capture
contract, and `source_identity` is a full lowercase SHA-256. URL/manual origin
kinds and nullable hashes are not exposed in this subrelease. After the same
pin/profile checks and construction of its own fresh private execution tree, a
separate fixed `sys.executable -I -B -X utf8 -c <program>` child explicitly
inserts only that private root, asserts version and exact package/module
`__file__` paths beneath it, checks the profile fixture
`src-42baa0cddcfa30cdd5af`, and emits one closed JSON result. The local code
must not copy or reimplement the upstream ID algorithm. The result must match
`^src-[0-9a-f]{20}$`; a supplied `expected_source_id` must equal it.
This child uses the same exact replacement environment and private scratch
rule as the public CLI child.

## Authority document

`video-paper-wiki.upstream-authority.v1` is a closed `.work` inspection
provenance object with exactly `schema`, `profile`, `upstream`, `transport`, and
`transaction`.

`profile` is the exact profile identifier. `upstream` contains only the fixed
distribution/version/commit/tree, `tracked_and_untracked_clean=true`, the raw
packaged profile SHA-256, and its source snapshot SHA-256. It contains no host
path.

`transport` contains:

- `bundle_file = "bundle.json"`, its raw digest and byte count;
- `content_files`, one closed `{write_path, content_file, sha256, size_bytes}`
  object per facade write in exact order;
- the exact successful public CLI stdout digest and byte count.

Successful stdout is at most 8,388,608 bytes, stderr is empty, and stdout is one
strict UTF-8 JSON object plus only RFC 8259 trailing whitespace. The parsed plan
must have exactly the frozen upstream plan fields, `valid=true`, and no extras.
The exact pretty-print formatting is observed through stdout hash/size, while
semantic validation uses the parsed object.

The checked-in valid authority example contains the device/inode and stdout
digest observed from one disposable Vault. It is only a closed schema and
semantic fixture. It is not a cross-host stdout golden; implementation tests
must run the real pinned child against their disposable Vault and correlate the
actual identity and stdout bytes from that run.

`transaction` is the independent facade returned by
`attach_upstream_inspection`: `phase=inspected`, non-null inspection,
`runtime_result=null`. Its plan paths, hashes, modes, operation identifiers,
input/expanded bundle hashes and approval digest remain subject to the frozen
facade correlations. Authority semantic validation additionally reconstructs
all deterministic content entries from the transaction and transport.

For capture integration, the previously opaque
`capture-inspection.upstream_plan_sha256` is now frozen to the public plan's
`approval_sha256`. The stdout digest and bundle digest have separate authority
fields and must never be substituted for this approval digest.

The authority object proves a bounded inspection observation. It is not a
source ledger, operation receipt, completed result, approval by a person, or a
canonical generation output. A future integrity-runtime contract must add an
explicit authority-hash binding before publication. Existing receipt,
run-manifest, projection-generation revision 1, and base-catalog profile are not
silently widened. Since this adapter produces no catalog rows, revision 1 stays
unchanged; the first mapper/compiler release must create a new generation
profile revision that binds adapter code, this schema/profile, and its consumed
authority digest.

The public plan attests current expected hashes, write modes, new content
hashes/sizes, and Vault identity, but it has no field for the facade write's
`original_size_bytes`. The authority preserves that proposal-local value and
validates its facade correlations; it does not independently prove the old-byte
size for a replacement. A later integrity-runtime contract must bind a secure
original-byte snapshot before claiming that stronger closure.

## Error order and stable codes

All expected adapter errors use `ContractError` and do not include raw bundle,
content, stdout, stderr, absolute Vault/work/upstream paths, credentials, or
approval material in `details`.

1. Validate proposal shape/semantics: existing `SCHEMA_INVALID` or
   `TRANSACTION_*`; no filesystem/process access.
2. Validate exact argument types, absolute/disjoint roots and staging layout:
   `ADAPTER_PATH_INVALID`, exit 2.
3. Authenticate git pin/tree/clean/profile/source snapshot, construct and
   verify the exact private execution tree:
   `UPSTREAM_PIN_MISMATCH`, exit 2.
4. Read and validate bundle/content type, limits, exact bytes and correlations:
   `UPSTREAM_TRANSPORT_MISMATCH` or `UPSTREAM_LIMIT_EXCEEDED`, exit 2.
5. Validate the existing no-follow Vault directory:
   `UPSTREAM_VAULT_INVALID`, exit 2.
6. Spawn/timeout/signal/unknown-exit or malformed failure transport:
   `UPSTREAM_EXECUTION_FAILED`, exit 1. Output over its cap uses
   `UPSTREAM_LIMIT_EXCEEDED`, exit 2.
7. A well-formed upstream exit 75 becomes `UPSTREAM_CONFLICT`, exit 75. A
   well-formed upstream exit 2 becomes `UPSTREAM_INSPECT_REFUSED`, exit 2.
   `details` may contain only `upstream_code` matching
   `[A-Z][A-Z0-9_]{0,63}` and `upstream_exit_code`; never the message text.
8. A zero exit with nonempty stderr, malformed/extra/invalid stdout, wrong plan,
   changed pin/transport/execution tree, cleanup failure, facade mismatch, or
   impossible constructed authority becomes `UPSTREAM_CONTRACT_MISMATCH`, exit
   2.
9. A syntactically valid source ID that differs from an explicit expected value
   becomes `UPSTREAM_SOURCE_ID_MISMATCH`, exit 2. Pin/helper/fixture/output
   failures use the preceding pin/execution/contract codes.

There is no fallback to another capture route, package, private transaction API,
or local source-ID algorithm after any failure.

## Verification and release boundary

Builder owns the production module, semantic dispatch, and focused unit,
upstream and security tests only after the exact architecture-freeze head is
accepted. Tests use disposable directories and the checked-in pinned submodule;
they never use a real Vault, admin/apply/recover, network, parser/model, or
credentials. Meaningful coverage must include capture/generic/ingest success,
fixed byte/plan/source-ID goldens, dirty/wrong/missing pin, symlink/special/race
transport, hostile ignored timestamp-valid `.pyc` files in the live checkout,
exact source-only private-tree construction and before/after verification, all
deterministic-layout refusals, hostile inherited `HOME`/temp/Vault/Python/proxy
environment values, private scratch containment, subprocess failure classes,
deep-copy isolation, and unchanged disposable Vault content/modes on every
success/failure path.

The installed wheel must include the schema and static profile and fail closed
when no explicit pinned checkout is supplied. No dependency or CLI entry point
is added. Full Python 3.12/3.13 local verification, an installed-wheel smoke,
independent Repo Steward review, and fresh Linux/macOS × Python 3.12/3.13 CI are
required for implementation acceptance. Passing this first subrelease does not
complete the full `adapter-contract` slice or VPKB-001.
