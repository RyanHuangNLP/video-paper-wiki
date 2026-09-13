# Retained I/O foundation integration — R13 preparation

Architect preparation from the bounded retained-I/O advisory. This document
does not freeze an I/O implementation, change the active two-file foundation
scope, or dispatch a Builder. R6/R8/R9 and their accepted ordering and failure
precedence remain authoritative. The exact foundation implementation must be
accepted before its later I/O consumer receives an implementation handoff.

## Checkout selection and authority

The no-root-argument session captures `os.getcwd()` exactly once. This is the
operating system's current absolute directory spelling, not a supplied lexical
path whose original symlink alias can be recovered. Do not consult PWD, search
parents, normalize a caller root, or change CWD. The selected directory itself
must contain the valid retained checkout markers; invocation from a nested
directory fails without searching upward.

Validate the returned exact string before constructing path objects. Retain
root-to-checkout directory edges with no-follow descriptor-relative operations.
Later CWD changes cannot redirect that graph. No claim is made to reconstruct
an unprovided shell spelling or to detect substitutions before their first
captured observations.

Retain `.git` and `pyproject.toml` through the checkout descriptor before testing
their meaning. A `.git` directory is a named retained marker, with no enumeration
or Git configuration read. A regular worktree marker is a single-link safe input
of at most 65536 bytes; its content is not followed. Project metadata is a
single-link safe regular input of at most 1048576 bytes. Parse those retained
project bytes with stdlib TOML and require project.name exactly video-paper-wiki.
No legacy path-based root resolver or resource fallback supplies authority.

## Initial resource policy

Selected resource origins and their ancestors must be nonsymlink directories.
Retain their device, inode, type and full initial mode; do not impose a complete
set over unrelated schema/profile siblings. Do not chmod any existing path.
Source and installed origins follow the accepted foundation's lexical plan.

Each of the eleven resource files is a nonsymlink, single-link regular file.
Reject executable bits, group/other-write bits, and all special mode bits.
Owner write is allowed, as in ordinary source/package installations. The actual
read-only open must succeed; no permissions are repaired or escalated by the
public command. Compare each exact byte count and SHA-256 to production pins.
Resource directories and files retain the R8 output disjointness checks.

Initially absent or policy-invalid resource state uses resource-invalid with
the existing missing, unsafe_type, unsafe_mode or link_count reason. Exact pin,
structural or origin failures use the corresponding resource_hash,
resource_shape or resource_origin reason. A syscall failure while acquiring an
initially observed resource retains its bounded I/O error if final verification
can confirm every observation actually acquired before that failure. Never
invent a retained byte snapshot for an initial unsuccessful read.

After bytes or edges have been retained, a persistent change or inability to
revalidate them is a lineage failure and takes WORK_PATH_UNSAFE precedence.
An unchanged initial absence remains an absence observation; it is not converted
into a successful descriptor or automatically called a changed lineage.

## Session-owned foundation adapter

Session setup itself calls the accepted `resource_origin_plan()`, retains its
exact eleven paths through its graph, then calls
`compile_code_proof_resources` with a new exact builtin byte dict. The caller
cannot supply an origin plan, byte mapping, descriptor, compiler, pin, registry
or callback to this adapter. Keep the compiled context private in the session.

Add these active-session-only internal workflow surfaces to R6/R8:

- `profile_sha256`: read-only pinned digest property.
- `validate_structure(title, instance) -> None`: delegates to the session's one
  compiled foundation context.
- `materialize_limits(value) -> dict`: delegates to that context and returns its
  independent limits map.

These methods check that the session is active and never expose the underlying
context or descriptors. They do not establish public identity or derivation
validity. Full resource rereads stay at the R8 bounded checkpoints; a structural
method does not create an independent resource-read session or cache. All public
exceptions unwind through the same final graph verification and cleanup before
they can be returned.

The setup order remains capability preflight, selected checkout/lock/markers,
retained resources and compilation, initial output scan, full verification,
then yield. Setup and compiler failures run final verification over every group
reached so far, even when no successful session was yielded.

## Platform and lock capability

Before output creation, require the exact no-follow/directory/close-on-exec
flags, descriptor-relative open/stat/mkdir/link/unlink support, no-follow
stat/link support, descriptor enumeration, fstat/read/seek/write/fsync/dup/close,
and nonblocking fcntl.flock. Missing support is unavailable_primitive; silently
dropping a flag or substituting a path-based call is forbidden. This does not
require procfs and must support the same graph rules on macOS and Linux.

After retaining the checkout descriptor, acquire LOCK_EX|LOCK_NB before any
resource/work scan. Busy EACCES/EAGAIN/EWOULDBLOCK uses the R8 busy error context
and creates nothing. Duplicate that open-file description immediately and keep
the duplicate last through verification and all other closes. Failed dup or
setup still releases owned descriptions through the common cleanup path.

Require an actual directory-fsync capability check on the retained checkout
before any output creation. ENOSYS/EINVAL/ENOTSUP/EOPNOTSUPP denotes unavailable
support; other errors retain syscall_failed with bounded errno. This checks
the current filesystem, not a platform-name heuristic. Preserve any final
lineage error over capability, operation or close errors. No lock file, procfs
path, global runtime mutation or cross-platform success claim is introduced.

The implementation freeze must name test injection surfaces and add the actual
source/wheel, initial-resource, root-selection and platform-failure cases to the
existing public acceptance matrix. The advisory's local capability observations
do not replace those implementation tests or fresh Linux CI.
