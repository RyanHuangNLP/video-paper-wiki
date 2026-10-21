# CODE proof retained I/O — R6 candidate

Architect design candidate following the independently reviewed R5 state and
installer decisions. R2–R5 and their reviews remain unchanged. This is not a
Builder dispatch or acceptance. The active implementation remains the three-file
Git kernel. The public wire/resource freeze must bind this candidate after its
own independent review and after the remaining public schemas exist.

## Concrete module boundary

The future private implementation is `video_paper_wiki.code_proof_io`. It owns
one retained graph for a whole public command, including setup and exceptional
exits. It does not reuse the legacy `_atomic_install`, `_unlink_at`, or a series
of independent `_open_batch_session` calls. Existing modules remain unchanged.
Low-level `secure_io.dir_open_flags`, `file_open_flags` and `stamp` may be reused
after the wrapper checks required platform support. The CODE implementation
requires no-follow, descriptor-relative open/stat/mkdir/link/unlink and directory
fsync support; it refuses unavailable primitives before any output creation.

The internal API is:

```python
@contextmanager
def open_code_session(*, batch_id: str): ...  # yields _CodeSession

class _CodeSession:
    def snapshot(self) -> dict[str, bytes]: ...
    def retain_input(self, path: str, *, maximum: int) -> bytes: ...
    def retain_bundle_manifest(self, relative_directory: str) -> bytes: ...
    def retain_bundle_bodies(self, *, object_format: str,
                             objects: list[dict], limits: dict[str, int]
                             ) -> dict[str, bytes]: ...
    def set_output_limits(self, limits: dict[str, int]) -> None: ...
    def install(self, relative_name: str, payload: bytes) -> bool: ...
    def verify(self) -> None: ...
```

These APIs receive already validated internal primitive arguments. Their own
path, byte and layout bounds still fail closed; they do not accept a caller file
descriptor, arbitrary file policy, callback, reusable-file identity or filename
outside the fixed CODE layout. `install` returns true for initial identical reuse
and false for a new installation. It never treats a later-arriving target as
reuse. `snapshot` returns fresh mappings of owned immutable bytes with names
relative to the output namespace; absence and initially empty families stay in
the session's separate retained state. A fresh mapping is not a new filesystem
snapshot. Repeated calls verify and return the same retained generation plus
this command's authorized completed installations.

Opening a session creates no path. It retains checkout authority, the installed
CODE resource set and the initial output state before yielding. `retain_input`
admits one ordinary metadata input file for request/observe; it keeps its exact
original path spelling and named lineage. `retain_bundle_manifest` admits at most
one disjoint raw input bundle for observe, capturing its root and objects complete
sets before reading its manifest. `retain_bundle_bodies` uses only that retained
bundle and the validated inventory; it cannot select or reopen another root.

The pure workflow orchestrator parses and validates the saved state, ordinary
input and all raw bodies before its first `install`. It sets the fully materialized
request limits before writing. An absent request command obtains those limits
from its validated input; every other command obtains them from the saved request.
The I/O session starts with hard caps and allows one narrowing to positive values
within those caps, never later widening. Lowered limits apply to all already
retained output bytes too. Semantic state transitions remain the R5 state table.
Only request and observe consume external input; completed status/config/handoff
do not reopen the bundle path stored in intent.

## First observations and bounded scans

Retain every ancestor from the filesystem root through the lexical checkout,
input, output and installed resource paths. One absolute lexical path has one
initial edge record and descriptor lineage. Shared ancestors are retained once.
No `resolve`, `realpath`, `normpath`, symlink fallback or path spelling repair may
turn rejected caller input into an accepted alias. Validate raw spelling before
constructing normalized Path objects. CLI path arguments are exact strings;
batch uses the existing 1–128-character `BATCH_ID_RE` grammar after an exact-str
check. The bundle path is a canonical checkout-relative `.work/...` spelling.

Capture the checkout `.git` marker and `pyproject.toml` before validating their
meaning. A marker may be a nonsymlink directory or single-link regular worktree
marker of at most 65536 bytes; do not follow a worktree marker's contents. Retain
project bytes up to 1048576 bytes and validate the existing project name. Recheck
both through all exits. Do not read Git config or mutate either marker. Checkout,
`.work` and batch ancestors retain their initial directory mode/identity without
chmod. Newly created `.work` or batch directories use 0700; pre-existing
ancestors retain the established nonsymlink directory authority rules.

Keep R2's nonblocking exclusive advisory flock on the retained checkout directory,
acquired before scanning resources/work paths. A contending CODE command receives
`CODE_PROOF_BUSY` with exit code 2 and creates nothing. Retain a duplicate of that
open-file description until final verification and all other descriptor cleanup
finish. This serializes cooperating commands; external writers need not honor it
and remain subject to the observed-lineage checks below. Do not substitute a
new on-disk lock file or silently proceed without the lock primitive.

Every complete-set registration happens before entry type, name or content
classification. Scan output root (at most seven ordinary entries), objects
(2048), configs (32), handoffs (32), input root (two) and input objects (2048)
through their retained descriptors. An active owned temporary name adds exactly
one permitted entry to its containing output directory. Fixed output slots have
explicit initial presence/absence records even when absent from enumeration.
If an ancestor is absent, retain that earliest missing edge; descendants are
logically absent and must not be separately reopened through a later arrival.

Enumeration itself is bounded: register an in-progress scan before starting a
descriptor-based iterator, keep at most cap+1 names and refuse excess before
materializing an unbounded list. Only a completed bounded scan may become a
complete-set snapshot. A refusal during enumeration/stat still retains and checks
all ancestors, reached named edges and the in-progress scan; its final bounded
rescan must not silently replace the original observed names. For a completed
scan, a changed name set is a lineage error. For a scan stopped at cap+1, the
original over-cap refusal remains unless a retained edge or observed membership
changes; this is never represented as a valid complete snapshot.

For every observed regular output entry, charge its stat size before content
reads, even if its name will be refused. Refuse unknown names and unsafe types
without opening their contents. Record type/mode/link identity before opening;
post-open fstat must match that first observation. Refuse initial files unless
regular, single-link, and within their exact policy: output mode 0600; raw and
ordinary metadata input have no executable, group/other-write or special bits.
Generated output directories require exact 0700. Resources use their frozen
read-only input policy, never caller-provided resource files. Retained directory
comparison uses device/inode/type/mode, excluding normal child-induced size/time
changes. Retained file comparison includes device/inode/full mode/size/mtime/ctime
and link count, with exact retained bytes re-read through the same descriptor.

Check bundle/output lexical disjointness and retained directory identities before
any output creation. Reject equality or ancestor relationships. Shared `.work`
or batch parents have named-edge checks, not an invented complete-set lock over
unrelated siblings. Input bundle root and objects sets remain exact; creating
output must never change either input set.

## Resource binding and verification exits

The public wire freeze supplies exact names, sizes and SHA-256 values for the
new profile and every schema referenced by the six envelope kinds and public
input schemas. Use their installed package/source-module resource origin,
independent of caller CWD; refuse non-filesystem origins in this retained API.
Construct a fresh registry solely from those retained bytes, with no remote
resolver, default cached registry or fallback resource read. The registry context
stays active until command parsing/derivation/installation is complete. Existing
unrelated schema files need not be enumerated as part of this closed resource
set. The complete wire freeze must also specify the package/source-layout
resource location rule; this candidate does not invent unbound resource hashes.

Register the session for final verification before its first authority lookup.
All construction, scan, open, stat, read, decode, size and pure semantic failures
pass through the same final verifier before closing descriptors. The verifier
attempts every retained group even when another group fails, and finishes with a
second named-edge/complete-set pass after retained byte rereads. It cannot stop
after the first resource failure and leave output/input lineages unchecked.
An observed persistent lineage failure overrides an earlier semantic or I/O
error. Remaining semantic and syscall errors retain their own bounded codes.
No success result is emitted until this final verification and cleanup finish.

## Installer checkpoints and failure decisions

Only one new file is in flight. The R5 peak check is current logical file bytes
plus twice the entire serialized payload size; it is checked before temporary
creation and remains charged during its live phases. The temporary name is a
fresh `.ce-tmp-` plus 32 lowercase hex characters, created exclusively with
0600, no-follow and read/write access. Keep its returned descriptor open until
cleanup and final verification. Record its inode immediately; do not derive
ownership from a later stat of the same name. Randomness selects only this
private name and cannot enter any saved artifact identity.

After creating and opening a new directory, verify its returned descriptor and
named edge before recording the authorized addition. EEXIST after captured
absence refuses. Portable mkdir does not return an inode; the guarantee begins
at the first captured post-mkdir identity and does not claim detection of an
unobserved replacement before that capture. The same explicit observation-bound
guarantee applies to all stat/check races; it is not a filesystem writer lock.

Before temporary creation, after each write, before file fsync, before link,
after link, before unlink, after unlink and after directory fsync, check all
retained lineages and scoped sets with the exact currently owned installation
phase. Writes handle short progress; zero progress is an I/O failure. Before link
verify payload length and exact bytes through the retained temporary descriptor.
Publish using descriptor-relative `os.link(..., follow_symlinks=False)` to the
initially absent final name. No replacing rename or fallback copy is permitted.

The live phase allows only the recorded temporary inode to change size while
being written and to gain exactly its one final hard link. Other file stamps
remain immutable. After link, verify both names against the retained descriptor,
exact payload, exact mode and link count two. Cleanup checks the named temporary
inode/mode and expected link phase before unlinking; partial temporary content
after a write failure is still owned and removable. Verify temporary absence and
the final single-link payload after unlink. Only then record the installed final
stamp and authorized complete-set addition. Never rebaseline from a replacement.

| Event | Required action and result |
| --- | --- |
| Target appears before link, or link returns EEXIST | Refuse lineage; remove only a still-owned temp; never adopt/delete target. |
| Temp disappears or changes inode/mode/link phase | Refuse lineage; do not unlink the observed replacement or claim cleanup. |
| Write is short | Continue only after retained checks; charge the full planned peak. |
| Write makes zero progress, raises, or file fsync fails before link | Attempt checked owned-temp cleanup; preserve I/O error if final lineage is intact. |
| Link fails without creating final | Attempt checked owned-temp cleanup; preserve I/O error unless lineage checks fail. |
| Link succeeds but either name does not match owned inode/payload | Refuse lineage; never roll back an unverified final name. |
| Temp unlink fails while its identity is intact | Report cleanup I/O failure; retain the leftover phase in verification; no success. |
| Final remains correct after cleanup but directory fsync fails | Preserve completed installed prefix and report I/O failure; do not unlink final. |
| Final or any ancestor/input/resource changes on an error path | Lineage error overrides the prior operation error. |

Cleanup is attempted on all exits after temporary creation, including interrupted
operations. It cannot promise atomic compare-and-unlink from a stat/unlink pair.
If a replacement occurs only between these calls and is not observable afterward,
this API cannot prove otherwise. Tests assert persistent observed substitutions
and never describe this as exclusion of unrelated writers. No unconditional
final-path rollback, swallowed cleanup error or automatic orphan repair exists.
After verified cleanup, a linked final can remain as the allowed R5 prefix even
when a later operation fails. A later command independently scans it; any leftover
temporary or double-link phase refuses instead of being adopted.

I/O-level codes are `WORKSPACE_ROOT_INVALID`, `INVALID_BATCH_ID`,
`WORK_PATH_UNSAFE`, `CODE_PROOF_IO_ERROR`, `CODE_PROOF_RESOURCE_INVALID`,
`CODE_PROOF_LIMIT_EXCEEDED`, `CODE_PROOF_CONFLICT`, and `CODE_PROOF_BUSY`.
All exit codes are 2.
Stable pre-existing byte disagreement is CONFLICT; late identity/content change
is WORK_PATH_UNSAFE. IO_ERROR retains bounded operation and errno fields, never
raw syscall messages or arbitrary path text. Public schema/input/state errors
remain the forthcoming wire contract. No new code is added to the pure Git
kernel by this private I/O candidate.

## Required independent tests

Exercise every table row, exact peak limit minus one/equal/plus one, initially
absent and initially identical files, pending prefixes, no-request status,
malformed/oversized inputs, setup failures before yield, partial scans, unknown
siblings and resource changes during final reread. Swap every ancestor and each
fixed missing slot, replace temp before link and before cleanup, change link
count in each phase, and insert siblings during exception handling. Retain the
original inode while constructing distinct replacement fixtures so the test
does not assume unlink/recreate changes st_ino on every OS. Verify no input
mutation, wrong-target deletion, fallback I/O or success after failed fsync.

This contract still needs independent review, concrete schema/resource files,
implementation, adversarial replay, both full Python suites and installed-wheel
verification at the complete CODE-PROOF boundary.
