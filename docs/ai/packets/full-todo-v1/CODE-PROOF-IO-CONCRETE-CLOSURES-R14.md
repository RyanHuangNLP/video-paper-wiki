# Retained I/O concrete closures — R14 preparation

This additive Architect preparation resolves the three concrete decisions in
the R13 review. R6/R8/R9/R13 remain inputs. It does not dispatch implementation
or enlarge the active two-file pure foundation scope. A later I/O freeze must
bind this document, an independent review and the accepted foundation candidate.

## Private ownership and lifetime

The I/O module owns a private `_RetainedResourceSet` in `_CodeSession`.
Only session setup constructs it. It holds one immutable origin plan, an
ASCII-logical-name ordered tuple of eleven `_RetainedResource` records, and
one private compiled `CodeProofResources` context. No caller supplies any of
these values. A resource record holds:

- Logical path and origin layout (`source` or `installed`).
- Session-owned parent-directory record and exact final name edge.
- First observation state, first file stamp when obtained, and descriptor when
  successfully acquired. The graph, not a second owner, closes descriptors.
- The fixed file policy and production size/hash pin.
- Exact retained bytes only after a complete successful bounded read.

During setup a private ordered acquisition collection can be partial. It is
registered in the session graph before lookup/open/read; final verification
checks the acquired subset on all setup exits. A completed `_RetainedResourceSet`
is installed only after all eleven acquisitions and compilation succeed. Build
a fresh exact builtin dict from their retained bytes, call the accepted pure
compiler once, then discard that transient dict. Its byte values refer to the
same immutable snapshots held by the graph. Compilation neither closes nor
reopens resources and cannot substitute a different origin, pin or descriptor.

The session alone holds the resource set. `profile_sha256`,
`validate_structure` and `materialize_limits` first call its private
`_require_active()` and then delegate to its compiled context. They return only
the R13 digest/None/independent plain limits result. A retained session reference
cannot use them before yield, during finalization or after close: these misuse
cases raise `RuntimeError("CODE session is not active")`. That private misuse
error is not a public wire error. Transition to finalizing before graph checks;
retain snapshots/context/descriptors through final verification and reverse
cleanup, then clear context/resource-set references and mark the session closed.
Final verification uses the graph directly, never an active-only wrapper.

## First observations and final comparisons

A resource regular-file stamp is exactly
`(st_dev, st_ino, st_mode, st_size, st_mtime_ns, st_ctime_ns, st_nlink)`.
Require integer nanosecond stat fields; do not substitute float timestamps.
The first no-follow named stat is the baseline. The successful descriptor's
first fstat must match it. Every later successful-resource checkpoint compares
the named stat and same descriptor fstat to that full baseline, rereads exact
bytes from that descriptor with bounded seek/read, compares size/hash/bytes,
then checks descriptor and named stamps again. The R8 last sweep still follows
all groups. Failed reads never replace a snapshot or establish a new baseline.

A resource directory/ancestor compares exactly device, inode and full mode
(which includes type), through the retained descriptor and name edge. Exclude
directory size, times and link count, which can change with unrelated children.
Do not enumerate unrelated schema/profile siblings or add a resource complete
set. Ordinary output complete-set rules remain unchanged.

Initial resource conditions have these deterministic dispositions:

| First acquisition outcome | Final checks and resulting original error |
| --- | --- |
| Named lookup observes ENOENT beneath a retained parent | Retain an absence record; if it remains absent and parent lineage is intact, resource-invalid/missing. Appearance or uncheckability is WORK_PATH_UNSAFE. |
| Named stat succeeds but type/mode/link policy fails | Retain the observed edge and applicable stamp, without opening an unsafe object. If the same observed state can be verified, retain its resource-invalid reason. A changed or uncheckable observation is WORK_PATH_UNSAFE. |
| Named stat fails without a usable observation, other than observed absence | Retain the parent/ancestors already acquired, but invent no child stamp or bytes. If those remain verifiable, preserve bounded IO_ERROR/syscall_failed for stat. |
| Named stat succeeds, but open/fstat/seek/read fails before complete bytes are obtained | Retain each observation/descriptor actually acquired. Verify the named baseline and each available descriptor stamp; no byte comparison is claimed. If unchanged, preserve bounded IO_ERROR/syscall_failed for the failed operation. Any retained edge/stamp mismatch or inability to verify it is WORK_PATH_UNSAFE. |
| Complete bytes exist but pin/parse/profile/reference checks fail | Keep the complete snapshot through final checks. If unchanged, preserve resource-invalid/resource_hash or resource_shape; later change or uncheckability is WORK_PATH_UNSAFE. |
| Origin planning fails before any resource is observed | Preserve resource-invalid/resource_origin unless a reached earlier graph group fails final verification. |

These outcomes are original errors subject to R8 final selection: attempt all
reached groups; select the first failed lineage group in the existing order;
otherwise select a cleanup error before the original error. Do not restart
acquisition on a different path to repair an initial syscall failure. Policy
checks on a first observation do not authorize following a symlink or opening a
device for the purpose of later verification.

## Exact primitive checks and test seams

The I/O module defines `_capability_snapshot()` to read the actual Python
capability sets/attributes without filesystem mutation. Preflight requires:

- Integer `O_RDONLY`, `O_WRONLY`, `O_CREAT`, `O_EXCL`, `O_NOFOLLOW`,
  `O_DIRECTORY`, `O_CLOEXEC` and `O_NONBLOCK` attributes. Zero is valid for
  `O_RDONLY`; protection flags must be nonzero.
- `os.open`, `os.stat`, `os.mkdir`, `os.link`, and `os.unlink` membership in
  `os.supports_dir_fd`.
- `os.stat` and `os.link` membership in `os.supports_follow_symlinks`.
- `os.scandir` membership in `os.supports_fd`.
- Callable `os.fstat`, `os.read`, `os.lseek`, `os.write`, `os.fsync`, `os.dup`
  and `os.close`; integer `SEEK_SET`; and available callable `fcntl.flock`
  with integer `LOCK_EX`, `LOCK_NB` and `LOCK_UN`.

Absent requirements produce unavailable_primitive before output creation;
never drop flags or replace descriptor operations with path operations. The
capability snapshot is checked per session and is not caller-overridable.
Tests may monkeypatch this private function to simulate missing capabilities.

Use `os.scandir(retained_directory_fd)` in a context manager. Count each returned
entry immediately against the R6/R8 cap, and stop at cap+1 with an incomplete
scan record; never materialize an unbounded iterator. Retain exact validated
entry names and obtain their no-follow stats via `_stat(name, dir_fd=parent,
follow_symlinks=False)`. DirEntry path strings are not authority. Close the
iterator on every exit and preserve the underlying retained directory record.

The module binds private syscall seams `_getcwd`, `_open`, `_stat`, `_fstat`,
`_scandir`, `_read`, `_seek`, `_mkdir`, `_write`, `_link`, `_unlink`, `_fsync`,
`_flock`, `_dup`, and `_close` to the matching actual operations (with `_seek`
bound to `os.lseek`). Every production invocation goes through these seams.
Tests patch these module attributes, retaining the originals when forwarding;
no workflow accepts callbacks or changes global os/fcntl state. No legacy
loader or conditional-flag helper supplies a missing primitive.

Actual checkout flock uses LOCK_EX|LOCK_NB. EACCES/EAGAIN/EWOULDBLOCK selects
the existing busy refusal. ENOSYS/EINVAL/ENOTSUP/EOPNOTSUPP selects
unavailable_primitive with operation=flock. Other errno values select bounded
syscall_failed. Actual directory fsync uses the same unsupported-errno set with
operation=fsync, otherwise syscall_failed. Deduplicate platform errno aliases;
do not infer support from the operating system's name. After successful lock,
duplicate its open-file description immediately, probe checkout directory fsync,
and continue setup only on success. The duplicate closes last under R8 cleanup.

Later acceptance must inject each unavailable capability, each flock error
class, fsync unsupported/other failures, partial acquisition errors and close
errors. It must exercise same-descriptor content changes, full file-stamp
changes, unchanged initial unsafe/absent states, final uncheckability, inactive
session wrappers, actual source and wheel origins, and cap+1 enumeration.
Local capability observations alone do not claim Linux CI or implementation
acceptance.
