# CODE retained I/O clarifications — R8 candidate

Architect supplement responding to CPI-R6-API-STATE-001 through
CPI-R6-CHECKPOINT-007 in the unchanged retained-I/O R6 review. R2–R7 and all
reviews remain history. This closes design choices for another independent
review; it does not authorize implementation or provide absent resource hashes.
The active implementation packet is still the Git kernel.

## Layout state and private phases

Add `_CodeSession.layout_state() -> dict` to the R6 internal API. It returns a
fresh primitive snapshot, verified against the same retained generation:

```text
{
  initial_namespace_present: bool,
  current_namespace_present: bool,
  initial_families: {objects: bool, configs: bool, handoffs: bool},
  current_families: {objects: bool, configs: bool, handoffs: bool},
  initial_files: [relative output filename, ...],
  current_files: [relative output filename, ...],
  current_file_bytes: int
}
```

File lists are unique and sorted by ASCII bytes; they contain only successfully
retained valid-layout files. The separate `snapshot()` returns their byte mapping.
The workflow can distinguish absent/empty known families without reopening any
path. A family present under a forbidden R5 state is a semantic refusal even if
empty. Callers receive no file descriptor or mutable session container.

An incomplete or refused I/O scan raises and never returns either successful
snapshot. Its partial state remains private for final verification; the workflow
does not need a partially classified filesystem result. This deliberately closes
the review's API concern without exposing failed scans as usable evidence.

Internally each reached edge records its parent descriptor, name, first stat or
absence, optional retained descriptor, role, and any authorized creation event.
The initial observation is immutable. Current owned state is a separate record;
never replace `first` with a later unrelated observation. Each directory scan
records its ordinary cap, initial observed names, reached entry stats, completion
flag, cap-exceeded flag and optional first enumeration/stat error. A completed
name set is immutable except for separately recorded authorized current-command
additions/removals. An over-cap scan is not a complete set.

The one installer record has this phase enum:

```text
idle -> temp_created -> writing -> temp_ready -> linked
     -> cleaned -> durable -> idle
```

It retains target name, payload bytes/size, temporary name and returned descriptor
identity, written byte count, successful-link-return flag, observed final identity,
temporary absence observation and directory-durability flag. Error handling keeps
the last reached phase plus its refusal; it does not relabel it idle merely to
make a final verification pass. The workflow cannot continue installing after an
install error. It unwinds through the session's all-exits path.

`temp_created` and `writing` allow only the owned temporary inode's expected
size/time changes. `temp_ready` requires its complete exact payload and one link.
`linked` requires a successful link return followed by both checked names on
that inode with two links. `cleaned` requires verified temporary absence and the
single-link exact final. At the cleaned transition, record the authorized final
stamp, complete-set addition and logical installed byte count **before** directory
fsync. `durable` follows successful directory fsync and final checks. A failure
after cleaned may leave that verified installed prefix with an I/O refusal.

Neither `snapshot` nor `layout_state` returns a successful view of an in-flight
temporary phase. On successful install return, the session is idle with either
initial exact reuse or the fully checked durable final in current state.

## First creation and directory policy

`open_code_session` always opens read-only and captures initial absence. It
validates exact batch syntax, retains lexical checkout ancestors, acquires the
nonblocking checkout flock and its duplicate, retains/validates checkout markers,
then retains installed resources and the initial output state. The finalizer is
registered before any of these fallible operations. No setup failure writes an
output directory or file.

Creation is an internal phase of `install`, after the orchestrator has validated
all semantic input and set the request's complete narrowed limits. The first
install, when needed, creates missing `.work`, batch and `code-evidence-v1`
directories in that order, using the retained earliest missing edge. Later
installs lazily create only their named family. Each step verifies the preceding
generation, calls descriptor-relative mkdir with 0700, captures/opens/checks the
new directory, records that authorized creation, then verifies and fsyncs its
parent before the next step. EEXIST after initial absence is a lineage refusal.
No path-only side channel or orchestrator mkdir is allowed.

Already verified newly created empty directories remain after a later error.
The session does not roll back directory names; it verifies their current
identity and closes descriptors. This avoids deleting a concurrently replaced
directory and permits R5's empty/request-only recovery states. A subsequent
command independently classifies the retained directory state. Unknown files or
leftover temporary names are still refused and are never automatic repairs.

| Directory | Pre-existing mode policy | New mode | Scoped ordinary entry cap |
| --- | --- | --- | ---: |
| Filesystem/checkout ancestors, checkout, .work, batch | Nonsymlink directory; exact first mode/identity retained | 0700 only for missing .work and batch | Named edges only |
| code-evidence-v1 | Exactly 0700, including an initially empty directory | 0700 | 7 |
| objects | Exactly 0700 | 0700 | 2048 |
| configs | Exactly 0700 | 0700 | 32 |
| handoffs | Exactly 0700 | 0700 | 32 |
| Raw input bundle root | Nonsymlink directory; exact first mode/identity retained | Never created | 2 |
| Raw input objects | Nonsymlink directory; exact first mode/identity retained | Never created | 2048 |

Only the current recorded owned temporary name adds one entry above its
containing output directory's ordinary cap. A foreign temp-like name is an
unknown entry, not an extra allowance. The maximum number of names retained by a
bounded enumeration is its allowed ordinary cap plus current owned-temp count
plus one excess sentinel. Ordinary caps are hard layout caps; request Git limits
may narrow the valid object inventory further. Metadata and raw body caps are
checked independently. Every observed regular file contributes its actual stat
size to output logical bytes before its name/content is classified.

Unknown names and initially unsafe modes/types are refusals, but they remain in
the captured bounded scan and reached-edge state until final verification. Safe
known files alone appear in a returned snapshot. No accepted budget result can
ignore an observed invalid entry, because that command returns no success.

## Ordinary input and resource disjointness

Before retaining an ordinary input file's bytes, validate its original spelling
and reject a path equal to, inside, or a lexical ancestor of the output namespace.
Retain the reached descriptors/edge even when the relation check refuses. Reject
descriptor identity alias with an output file; the single-link requirement also
refuses ordinary hardlink aliases. Metadata may be a sibling of the output or
reside elsewhere on the local filesystem. Its parent does not gain a complete-set
constraint over unrelated siblings merely because this input is retained.

The selected installed profile/schema origins and all resource files must be
outside the output namespace. An origin equal to or inside output refuses before
creation; output cannot be contained in a scoped CODE resource directory either.
Sharing the checkout or filesystem ancestors is expected and is allowed. This
does not prohibit source-layout resources whose package and schemas are sibling
directories of `.work`. Raw bundle disjointness remains R3/R6 in both lexical
and retained descriptor relationships.

## Bounded verification cadence

The internal implementation has `verify_names_and_sets()` and `verify_full()`;
R6's public-to-orchestrator `verify()` is an alias for verify_full. Both inspect
the same immutable first observations and explicit installation phase.

Names/set verification checks retained directory/marker/file named identities,
fd identities, expected modes/link counts, fixed absences and bounded scoped name
sets. During a write it checks the temporary inode's allowed current write phase;
it does not reread every retained source byte. Invoke this before and after every
write and each temporary/link/unlink transition. Refuse zero-progress writes;
short writes are valid only while these checks pass. Keep each requested write
chunk at most 65536 bytes.

Full verification brackets exact same-descriptor byte rereads with names/set
verification. It runs after initial acquisition, before the first install, before
each file publication, after checked temporary cleanup, after directory fsync,
and at every final command exit. It also verifies complete temporary payload
bytes before link. These full-byte passes are bounded by the number of installed
files, not by the number of short os.write returns. During a partial-temp error,
verify the recorded written-prefix bytes for that owned inode before cleanup
when readable; loss of its ownership still forbids unlinking a replacement.

Names checks remain bounded by the retained edge/set caps and at most payload
length positive-progress write calls. Full-byte passes charge at most the input
and output caps per pass; they do not recursively expand unrelated directories.
No claim of constant I/O cost or exclusion of external writers is made. Tests
instrument full-byte rereads and force one-byte writes to prove the cadence.

## Syscalls that take effect before an exception

The original error is always a refusal, even if later observations prove some
bytes were installed. Reconciliation never returns success after a syscall
exception and never turns an EEXIST outcome into initial-file reuse.

| Observed exceptional situation | Reconciliation |
| --- | --- |
| link raises, final remains absent, owned temp is single-link | Checked temp cleanup; preserve operation I/O error unless verification fails. |
| link raises and final is now present, including matching owned inode | Treat final as unverified late arrival and refuse lineage. Do not authorize or delete it. Preserve the temp unless its exact ownership and safe cleanup phase are provable without adopting that final. |
| link returned success, then a later check fails | Keep successful-link-return flag; require actual recorded phase checks. No unverified final adoption or rollback. |
| unlink raises and owned temp still exists unchanged | Preserve cleanup I/O error and leftover-temp phase; no success. |
| unlink was attempted after a verified linked phase, raises, and temp is absent while final remains exact/single-link | Record observed cleaned prefix, without claiming syscall success; preserve cleanup I/O refusal. |
| temp was already absent before this command's unlink attempt | Lineage refusal; do not use the preceding post-effect rule. |
| final, temp or any ancestor has a persistent mismatching identity | Lineage refusal takes precedence; never delete a foreign replacement. |

In all cases, a final whose installation was not authorized remains outside the
allowed current complete set. The final verifier consequently refuses it. The
session preserves the failure and closes descriptors; a later status must not
repair/adopt its leftover temporary names or double links. Stat/unlink and
mkdir/post-stat observations retain the limitations already stated in R6.

## Deterministic failure selection and cleanup

Group order for final verification is checkout authority, work/batch ancestors,
resources, ordinary input, raw bundle, output directories/sets, output files,
owned temporary/final phase. Each group is checked even after another fails.
Within a group, process already validated logical names in byte order; never
include arbitrary host-path text in a returned error. Keep at most one selected
failure per group and a bounded list of failed group tokens.

Any persistent failed lineage check yields WORK_PATH_UNSAFE, selecting the first
failed group in that order, ahead of an operation, semantic or cleanup error.
If no lineage failed, a cleanup error takes precedence over the original operation
error; otherwise preserve the original error unchanged. Initial malformed/missing
resources use CODE_PROOF_RESOURCE_INVALID if their first observed state remains
unchanged. A changed or uncheckable retained resource is WORK_PATH_UNSAFE.

The I/O error details have the closed shape:

```text
{phase, group, reason, operation, errno,
 prior_code, prior_operation, prior_errno, failed_groups}
```

Phase is `setup`, `scan`, `retaining`, an installer phase above, `final_verify`,
or `closing`. Group is one of the eight group tokens above or null when no group
was reached. Reason is one of `unavailable_primitive`, `lock_busy`, `missing`,
`unsafe_type`, `unsafe_mode`, `link_count`, `edge_changed`, `bytes_changed`,
`set_changed`, `late_arrival`, `temp_ownership_lost`, `phase_mismatch`,
`syscall_failed`, or `zero_write`. Operation is null or one of
`open`, `stat`, `fstat`, `scandir`, `read`, `seek`, `mkdir`, `write`, `link`,
`unlink`, `fsync`, `flock`, `dup`, `close`. Errno is null or a nonnegative bounded
platform errno integer, never a raw exception string. The prior fields retain
the earlier selected error when a higher-priority failure replaces it, otherwise
null; prior_code is a closed CODE/kernel/public error code from the wire freeze.
Failed_groups is a unique list in the fixed group order, with at most eight items.

The symbolic group tokens are respectively `checkout`, `ancestors`, `resources`,
`metadata`, `bundle`, `output_layout`, `output_files`, and `installation`.
A multiple-condition failure within one group selects its first encountered
condition under the fixed checkpoint/name order, not iteration over a set.
The selected message is fixed by code/reason and contains no input/source text.

Close descriptors in reverse acquisition order after final verification, with
the duplicated lock description last. A close failure is a cleanup IO_ERROR
with operation=close; record it and attempt the remaining closes once. Do not
retry a failed close on an fd number that could have been released/reused. Keep
any preceding lineage failure authoritative. Successful data is emitted only
after this cleanup completes. KeyboardInterrupt/SystemExit still run owned-temp
and descriptor cleanup; do not convert an interruption into a success payload.

Pure kernel/public semantic errors keep their own structured details when not
overridden. The R8 I/O detail shape applies to the R6 I/O/busy/resource errors;
CODE_PROOF_LIMIT_EXCEEDED and CODE_PROOF_CONFLICT retain their forthcoming
public-wire context shapes so the existing Git-kernel API is not changed.

Independent review must check these exact transitions and then the concrete
implementation. The ten public schemas, installed profile, reason/context tables
for non-I/O public errors, exact path freeze and full integration evidence remain
required; this amendment is not their substitute.
