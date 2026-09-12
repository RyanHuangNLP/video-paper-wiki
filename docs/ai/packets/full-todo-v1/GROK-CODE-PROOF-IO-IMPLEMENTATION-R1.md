Implement the next private Python layer of a code-evidence workflow. Return
exactly two complete Python fenced blocks: first the new production module
`src/video_paper_wiki/code_proof_io.py`, then its pytest module
`tests/unit/test_code_proof_io.py`, followed by `Tests not run.` Do not return a
patch, incomplete definitions, ellipses or a second rewritten pair. Use only
this self-contained instruction, with no file, shell, network or model tools.
The local integrator will inspect and test the returned source before writing
the two product paths. Do not implement a CLI, parse public evidence documents,
invoke Git, retrieve source code, modify a Vault, or change any existing module.

The module owns one retained filesystem graph for one complete command. All
setup, body, verification and cleanup failures unwind through that graph. A
later pure workflow owns JSON/identity/state/derivation checks and performs no
filesystem writes. There is no success result until the context manager has
finished final verification and cleanup. Independent existing pure Git and
configuration kernels and all legacy staging/resource helpers stay unchanged.

## Existing foundation interface

Import only the existing public names needed from
`video_paper_wiki.code_proof_resources`: `resource_origin_plan`,
`compile_code_proof_resources`, `CodeProofResourceError`, and
`CodeProofStructureError`. Do not import its private constants or construct its
`CodeProofResources` directly.

`resource_origin_plan()` takes no arguments and does no I/O. It returns an
immutable record with `layout` (`source` or `installed`), absolute lexical
`package_directory`, `schemas_directory`, `profiles_directory`, and `resources`.
The last field is an ASCII-sorted tuple of eleven immutable pins, each with
`relative_path`, `size_bytes`, `sha256`. Logical names are ten
`schemas/<filename>` entries and `profiles/code-proof-v1.json`. Use the plan's
appropriate directory plus the exact final filename. Do not select origins by
CWD, environment, resource existence or an alternate fallback.

Retain each resource through this session's own graph before reading its bytes.
Then pass a fresh exact builtin dict of the eleven logical names to exact bytes
into `compile_code_proof_resources(retained_bytes)` once. It validates all
production pins, strict resource JSON/profile/schema/reference closure and
returns a fresh private validation context. The compiler does no I/O and accepts
no caller pins, origin, registry, validator or callback. Its methods are
`validate_structure(title, instance) -> None`,
`materialize_limits(value) -> independent dict`, and the read-only
`profile_sha256` property. Materialization accepts None for the pinned full
three-group map or an exact complete positive lowered map.

Both foundation exception classes expose the read-only property `reason`.
CodeProofResourceError.reason is resource_origin/resource_hash/resource_shape;
CodeProofStructureError.reason is type/shape/limits. These words are values,
not additional attributes. The I/O adapter reads only `.reason`; it does not
access or invent `.type`, `.shape` or `.limits` properties or change the original
private classes or messages.

Map resource errors during setup into this session's full resource-invalid
context. A later lineage failure still overrides them. Leave structure errors
private for the later public layer to map at a known instance pointer, while
always executing this session's finalizer.

## Private session interface and lifetime

Expose `open_code_session(*, batch_id)` as a context manager yielding a private
`_CodeSession`. It has these methods:

- `snapshot() -> dict[str, bytes]`.
- `layout_state() -> dict`.
- `retain_input(path, *, maximum) -> bytes`.
- `retain_bundle_manifest(relative_directory) -> bytes`.
- `retain_bundle_bodies(*, object_format, objects, limits) -> dict[str, bytes]`.
- `set_output_limits(limits) -> None`.
- `install(relative_name, payload) -> bool`.
- `verify() -> None`, aliasing full verification.
- `validate_structure(title, instance) -> None` and `materialize_limits(value)`.
- Read-only `profile_sha256`.

The caller cannot supply descriptors, roots, origin plans, validators, callbacks,
file policies or mutable graph records. The session selects checkout authority
from one call to `_getcwd()` itself. No parent search, PWD lookup or chdir.
Retain that one absolute directory; later CWD changes cannot redirect it.

Register finalization before the first fallible authority operation. Setup order
is capability preflight; lexical checkout ancestry; checkout lock and duplicate;
actual checkout directory-fsync capability; checkout markers; resources and
compilation; initial output scan; full verification; then active yield. Maintain
explicit setup, active, finalizing and closed states. `_require_active()` raises
`RuntimeError("CODE session is not active")` outside active lifetime. Resource
wrappers call it before delegation. No successful snapshots or layout views may
escape an in-flight installer phase. Change to finalizing before graph checks;
retain descriptors and resource context through final verification and reverse
cleanup, then clear context/resource references and mark closed.

`snapshot` is a new mapping of immutable retained bytes, not fresh path reads.
It returns only initially valid-layout files plus this command's completed
authorized installations, named relative to the output namespace. It verifies
the same retained generation on repeated calls. `layout_state` returns fresh
primitive data with exactly `initial_namespace_present`,
`current_namespace_present`, `initial_families`, `current_families`,
`initial_files`, `current_files`, `current_file_bytes`. Family maps contain
exactly `objects`, `configs`, `handoffs` booleans. File lists are unique ASCII
ordered relative names. Empty versus absent known directories is preserved.
Failed or incomplete scans never yield a successful partial snapshot.

An install returns True only for byte-identical reuse captured in the initial
complete snapshot. It returns False for a newly installed file. A file first
appearing after recorded absence never becomes reusable, even with equal bytes.
An authorized file created during this command is a separate current-state
addition, not an initially reusable file. There is no automatic orphan cleanup,
repair, replacement or adoption.

## Primitive checks and syscall seams

Bind every production syscall through private module seams: `_getcwd`, `_open`,
`_stat`, `_fstat`, `_scandir`, `_read`, `_seek`, `_mkdir`, `_write`, `_link`,
`_unlink`, `_fsync`, `_flock`, `_dup`, `_close`. They default to actual os/fcntl
operations; `_seek` is os.lseek. Tests may patch these module attributes but no
session accepts a callback and production never patches global os/fcntl state.

Define `_capability_snapshot()` to inspect actual runtime attributes and support
sets without filesystem mutation, checked once per session. Require exact
builtin integer O_RDONLY (zero is valid), O_WRONLY, O_RDWR, O_CREAT, O_EXCL,
O_NOFOLLOW, O_DIRECTORY, O_CLOEXEC, O_NONBLOCK; require nonzero access/protection
values except O_RDONLY. Require os.open/stat/mkdir/link/unlink in
os.supports_dir_fd, os.stat/link in os.supports_follow_symlinks, and os.scandir
in os.supports_fd. Require callable fstat/read/lseek/write/fsync/dup/close and
fcntl.flock, integer SEEK_SET and LOCK_EX/LOCK_NB/LOCK_UN. Missing requirements
are unavailable_primitive before any output creation; never drop flags or use a
path-based substitute. Tests may patch the private capability snapshot.

All ordinary/resource/body reads use retained read-only file descriptors with
no-follow and close-on-exec protections, plus nonblocking protection against an
unexpected unsafe object; directories use O_RDONLY, O_DIRECTORY, O_NOFOLLOW and
O_CLOEXEC. The owned temporary uses O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,
mode 0600 and retained parent dir_fd. The same returned temp fd does writes,
seek/read verification and fstat; never reopen it by path for readback.

Acquire LOCK_EX|LOCK_NB on the retained checkout directory before resource or
work scans, then duplicate its open-file description immediately. Keep the
duplicate until all other descriptor closes finish. EACCES/EAGAIN/EWOULDBLOCK
means CODE_PROOF_BUSY/lock_busy. ENOSYS/EINVAL/ENOTSUP/EOPNOTSUPP means
unavailable_primitive; any other bounded errno means syscall_failed. Deduplicate
platform errno aliases. Perform an actual fsync on the retained checkout
directory before output creation; its unsupported errno set is identical, with
operation=fsync. Do not infer support merely from the operating-system name or
create a lock file. Failed lock/dup/fsync still use the common finalizer.

## Authority graph and observations

Validate original path strings before Path construction. Never resolve,
realpath, normpath, repair spelling, follow a symlink or reopen through a later
arrival. Retain directory ancestry from filesystem root to each selected path
with descriptor-relative no-follow named operations. One absolute lexical
directory path has one retained lineage; share common ancestors. Each reached
edge stores parent fd, exact name, immutable first named stat or observed
absence, any acquired descriptor, role, and a separate explicit authorized
current-command creation record. Never overwrite the first observation with a
later observation.

Require exact-string batch IDs matching
`[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?` over the entire value. The
selected checkout itself must contain `.git` and `pyproject.toml`. Retain them
before interpreting their meaning. `.git` may be a nonsymlink directory with no
child enumeration, or a safe single-link regular marker of at most 65536 bytes;
do not follow its contents. Read project bytes from a safe retained regular
file of at most 1048576 bytes, parse via stdlib tomllib, require project.name
exactly `video-paper-wiki`. Do not read Git configuration or invoke Git.

A retained directory stamp is exactly device, inode, full mode including type;
exclude directory size, times and link count. A retained regular-file stamp is
exactly `(st_dev, st_ino, st_mode, st_size, st_mtime_ns, st_ctime_ns, st_nlink)`.
Require integer nanosecond fields, without float timestamp fallbacks. First
no-follow named stat is the baseline; the first acquired fd fstat must match it.
Every checkpoint compares both named and fd stamps with that baseline, apart
from the narrowly recorded active-temp changes below. Complete successful
reads retain immutable exact bytes; failed reads do not invent snapshots or
establish a replacement baseline.

All resources are nonsymlink single-link regular files. Reject execute bits,
group/other write and special mode bits; owner write is allowed. Resource
ancestors retain their initial nonsymlink directory modes. Do not chmod, search
alternates or enumerate unrelated schema/profile siblings. The private session
resource set contains the immutable plan, eleven ordered records and one
compiled context. Register each acquisition before lookup/open/read so partial
setup is checked on every exit. Each record retains the graph-owned parent/edge,
first observation, acquired fd if any, fixed pin/policy and bytes only after a
successful bounded read. Only publish the completed resource set after all
eleven reads and compilation succeed. The temporary compile dict is discarded;
the graph keeps the actual snapshots until after final verification and cleanup.

An initially absent resource retains its absence: unchanged absence is
CODE_PROOF_RESOURCE_INVALID/missing; later appearance or inability to check is
WORK_PATH_UNSAFE. An initially unsafe observed resource retains its edge/stamp
without opening a device or symlink; unchanged unsafe state keeps its original
resource-invalid unsafe_type/unsafe_mode/link_count reason. Initial stat errors
without an observation retain only reached parents and their bounded original
I/O error if those remain verifiable. A stat success followed by open/fstat/read
failure retains every observation actually acquired and verifies stamps without
claiming unavailable bytes. Complete bytes failing pin or compilation retain
their snapshot and original resource_hash/resource_shape. Origin-plan failure
before acquisition is resource_origin. Every later mismatch/uncheckability has
the normal final-lineage precedence.

## Fixed output layout and bounded scans

The sole output namespace is `.work/<batch>/code-evidence-v1` beneath the selected
checkout. Setup creates nothing. Checkout, `.work` and batch ancestors retain
their initial nonsymlink directory modes, without chmod. Existing namespace and
family directories require exactly 0700; newly created work/batch/namespace and
families use 0700. Existing output files require exactly 0600, nonsymlink,
single-link regular type. No nested family directory is allowed.

The direct fixed files and hard byte caps are request.json 65536, intent.json
1048576, bundle.json 1048576, observation.json 2097152. The three direct family
directories are objects, configs, handoffs. Objects accepts only
`<40-or-64-lowercase-hex>.body`, at most 2048 files, each at most 8388608 bytes,
and aggregate raw bodies at most 33554432 bytes. Configs accepts exactly
`<64-lowercase-hex>.json`, at most 32, each at most 2097152 bytes; handoffs uses
the same basename grammar, at most 32, each at most 131072 bytes. The future
public workflow checks request-selected OID width, path-hash basenames, exact
inventories, state legality and identity/derivation; this I/O layer must not
accept arbitrary filenames while waiting for those checks.

Register a bounded scan before any entry classification. Use
`with _scandir(retained_directory_fd)` and count each yielded entry immediately.
Stat names via `_stat(name, dir_fd=parent, follow_symlinks=False)`; DirEntry path
strings confer no authority. Ordinary caps are seven namespace entries, 2048
objects, 32 configs, 32 handoffs, two raw-bundle root entries and 2048 raw-object
entries. Keep at most the cap, one current owned-temp allowance when applicable,
and one excess sentinel. Stop at cap+1 rather than materializing an unbounded
iterator. A foreign temp-like name gets no allowance.

Retain initial names, reached stats, completed/over-cap flags and the first
enumeration/stat error. Completed sets are immutable except recorded authorized
additions/removals; a partial/over-cap scan never becomes a complete snapshot.
On final bounded rescan, preserve the original refusal if the observed subset
remains unchanged; an observed membership/edge change overrides it as lineage.
Do not silently replace a failed scan's initial observations with later names.
Retain all four fixed-slot and three family presence/absence observations. If
an ancestor is missing, record the earliest missing edge, with logical absent
descendants; never open those descendants through an unrelated later arrival.

Every observed regular output entry charges its actual stat size to logical
output bytes before its name/content is classified, including invalid entries
that cause refusal. Unknown names or unsafe types/modes/link counts refuse
before their contents are opened. Retain their bounded observed state for final
checks. Complete successful snapshots contain only safe known files. Total hard
output logical bytes are at most 134217728, excluding unrelated siblings,
resources and external inputs. Directories count zero bytes, but remain subject
to type/mode/set caps. No successful budget silently ignores invalid entries.

## Ordinary and raw inputs

One session admits at most one ordinary metadata input via retain_input. Keep
the caller's exact original spelling and retained named ancestry. Accept an
absolute canonical lexical spelling or a canonical relative spelling interpreted
from the captured checkout, with no empty, dot, dot-dot, NUL or symlink component.
Reject equality, containment or lexical-ancestor overlap with output, as well
as descriptor identity aliases. Its parents do not gain a complete-set scan over
unrelated siblings. Files use the resource-safe regular-file policy and bounded
same-descriptor reads. The private retain_input maximum argument is an exact builtin int equal to
65536 or 1048576. They select the fixed max_request_input_bytes or
max_observe_input_bytes admission policy respectively. Reject any other value,
including bool and int subclasses, with the existing private
CodeProofStructureError("limits") and suppressed context. This does not add a
caller-selectable resource/file policy or permit lowered admission via the
output setter. The public workflow selects the constant matching its command.
Both limits use instance_pointer=/input. An actual retained byte count above
that selected fixed maximum uses the fixed limit context defined below and corresponding
admission key, before decoding. No new public command or input field is added.

One session admits at most one raw bundle through retain_bundle_manifest.
Require an exact builtin string with at most 4096 Unicode characters, literal
`.work/` followed by at least one nonempty slash-separated component, and no
trailing or repeated slash. A component must not equal `.` or `..`. Components
may otherwise contain ordinary Unicode, spaces, dots, underscores and hyphens.
Forbid backslash, NUL, C0/C1 controls, DEL, U+2028/U+2029 and surrogates. Do not
apply the output batch alphabet, alphanumeric endpoints, 128-character component
limit, Git depth limit or `.git` exclusion to this input path.

Freeze `_MAX_BUNDLE_PATH_BYTES = 16384` as a private lexical-admission constant,
not a new request/profile limit key. This is the four-byte UTF-8 upper bound of
the existing 4096-character grammar, so it adds no smaller Unicode restriction.
Strictly encode the original spelling; require NFC equality without repairing
the path; require original and equal accepted NFC spelling to fit that byte
bound before descriptor traversal. Reject any failed spelling, encoding, NFC
or bound condition with the existing WORK_PATH_UNSAFE/path_spelling context.

The literal six-ASCII-character `.work/` prefix means the largest UTF-8 length
of an otherwise grammatical 4096-character path is at most 16366 bytes. Thus an
exact 16384-byte valid full-path example is impossible under the character
grammar; tests must not fabricate such a positive. Exercise the real maximum
character/encoded-length combination, character cap-plus-one, non-NFC spelling,
surrogates and forbidden components without filesystem traversal. The separate
named byte constant and comparison remain explicit. Actual OS filename/path
limits can cause normal bounded syscall refusal; this lexical grammar does not
guarantee every admitted spelling exists on a given filesystem.
Reject lexical and retained-descriptor equality or ancestor overlap with the
output root before creation. Sibling roots under a shared batch are allowed;
shared ancestors remain named-edge checks, not an invented whole-parent lock.
The input root has exactly manifest.json and objects. Capture both root and
objects complete sets before classification. Retain manifest bytes at the hard
or already selected max_bundle_bytes. No input path is created, modified, repaired
or chmodded.

retain_bundle_manifest first registers and completes the raw root and objects
bounded name scans and reaches the necessary no-follow named observations.
At this stage, object entries must be nonsymlink safe single-link regular files,
named exactly 40 or 64 lowercase hex characters plus `.body`. Record first
name/type/mode/link/size stamps and reject the hard layout/count/per-body and
aggregate raw-body caps before reading the manifest. Do not open or read object
bodies in this first stage and do not invent retained body byte snapshots.
Retain their observed named edges for the common finalizer.

After the later workflow validates manifest and inventory, retain_bundle_bodies
receives object_format, the complete inventory and the full five-key lowered
Git map. Check exact declared names/width and unchanged first observations,
then open, bounded-read and retain bodies in OID order under the selected count,
per-body and aggregate caps. The first acquired fd fstat must still match the
first-stage named stamp. Final checks before that acquisition verify available
named stamps only; after acquisition they additionally verify the acquired fd
and successful retained bytes. No late observation replaces the original stamp.
Inventory/type/size/hash/graph semantic checks remain subject to the unchanged
pure Git kernel and public validator; this split adds no alternate proof path.

retain_bundle_bodies uses only that already retained raw root. object_format is
sha1 or sha256. `objects` is the already validated ordered list of closed records
with `oid`, `object_type`, `body_size_bytes`, `body_sha256`, `framed_sha256`.
Validate safe primitive shapes and names independently before indexing, without
inventing a second Git proof validator. Exact lower-hex OID width is 40/64 and
types are commit/tree/blob. Read precisely that captured complete object set;
never select a new root or silently ignore extras. Preserve the existing pure
kernel's later hash/graph/consumption checks. The returned new dict maps OID to
retained exact bytes, independent of caller mutation of the inventory.

After the workflow has validated manifest/inventory and before opening any raw
body, verify the retained raw names/edges/sets. A changed or uncheckable retained
set is WORK_PATH_UNSAFE in bundle, with the applicable fixed lineage reason.
An unchanged first captured set is not a set_changed event.

Allow a narrow import from `video_paper_wiki.code_git_objects` of the public
CodeGitProofError and CODE_PROOF_INPUT_INVALID, CODE_PROOF_OBJECT_EXTRA,
CODE_PROOF_OBJECT_UNAVAILABLE constants. The local adapter may construct only
the three stable pre-body outcomes below with the existing class, exact literal
message, exact details and exit_code=2. Do not import private kernel helpers,
modify the kernel, widen the new eight-code I/O facade or invoke the complete
Git verifier without its full inputs.

Follow the actual existing `_validate_bodies_map` decision order:

1. Check every syntactically valid physical OID basename against the validated
   object_format width. Any opposite-width OID yields CodeGitProofError with
   CODE_PROOF_INPUT_INVALID, message `code git proof input is invalid`, and
   details exactly `{instance_pointer: "/bodies", reason: "invalid_oid_key"}`.
2. If widths are valid, physical OIDs outside the declared inventory yield
   CODE_PROOF_OBJECT_EXTRA, message `undeclared git object bodies were supplied`,
   and exactly `{instance_pointer: "/bodies", extra_oids: [sorted OIDs]}`.
3. With no extras, declared OIDs absent from the initial set yield
   CODE_PROOF_OBJECT_UNAVAILABLE, message `required git object is unavailable`,
   and exactly `{instance_pointer: "/bodies", missing_oids: [sorted OIDs]}`.

All emitted OIDs have already passed exact builtin/hex/width/count checks. A
physical filename outside either 40/64-lowercase-hex `.body` grammar remains
the existing initial raw-layout unknown_entry refusal, never a fabricated
lineage change or an echoed invalid filename. Count/byte admission checks still
precede opening bodies and retain their independent cap precedence.

Only after this complete stable reconciliation may declared bodies be opened
and read in OID order under the full five-key lowered Git map. Keep actual body
size/hash/type/commit/tree/consumption proof with the unchanged kernel; a wrong
declared size in an otherwise stable admitted body is not silently repaired.
Actual physical-body count limits use /bodies, declared inventory count uses
/objects; both use max_objects. These pointers are fixed and do not depend on untrusted filenames.

Tests must discriminate opposite-width+extra, extra+missing, stable missing,
invalid-layout-name, and post-capture set replacement cases. Assert zero body
opens on stable reconciliation refusals, exact existing Git class/messages/
details, and the ordinary final-lineage override after any semantic refusal.

The separate `limits` argument carries all five materialized Git keys:
max_targets=32, max_objects=2048, max_tree_entries=32768,
max_object_bytes=8388608, max_total_object_bytes=33554432 at their hard maxima.
Require exact builtin keys and exact positive int values within those maxima.
Snapshot the map. Enforce lowered object-count, per-body and aggregate byte
limits against declarations and before/while actual incoming reads. Keep the
other two keys intact for the later pure kernel; do not replace the full map
with only three I/O keys. Initial output scans use hard caps before parsing saved
request limits; the public workflow must replay retained objects under that
request's complete lowered Git limits before any success.

Resources must lie outside output; output cannot contain or be contained in a
scoped resource directory. Shared filesystem and checkout ancestors are allowed.
All overlap refusals retain reached observations and participate in final checks.

## Output limit setter and file installation

set_output_limits accepts exactly the flat seven-key output public projection:
max_request_bytes, max_intent_bytes, max_bundle_bytes, max_observation_bytes,
max_config_document_bytes, max_handoff_bytes, max_output_peak_bytes, with hard
maxima given above. Check exact builtin dict, exact string keys before set or
lookup operations, and exact positive integers within the corresponding maxima.
Copy it. Malformed maps raise CodeProofStructureError("limits") with suppressed
exception context. It succeeds once per session before the first install,
including when equal to hard maxima. A second call raises
`RuntimeError("CODE output limits are already set")`; install before a successful
setter raises `RuntimeError("CODE output limits are not set")`.

Before the setter succeeds, validate every already retained output file, total
logical size and retained raw manifest against the selected corresponding cap.
An already retained over-limit object cannot evade the later full lowered Git
replay. If manifest acquisition occurs after the setter, apply the selected
bundle cap on reading; if before, recheck it when narrowing. Do not turn a failed
setter into a successful view or permit later widening. max_inline_normalized_bytes
is a public semantic per-target check, not an I/O output-file setter key.

The later workflow must preflight the complete semantic result, serialization
and deterministic installation sequence before its first write. For each absent
payload N, it simulates C+2*N <= selected peak and then advances C by N, with
zero added bytes for initially identical reuse. This session independently
rechecks the actual C+2*N immediately before every temporary creation. C counts
all retained installed files including optional configs/handoffs. Two live names
of one inode count twice as logical path bytes; do not use disk blocks or a
current+N formula. Only one temporary is in flight.

Creation occurs only inside install after these checks. Create missing .work,
batch and namespace in that order via retained dir_fd mkdir(0700); then lazily
create only the needed family. For each new directory: verify the preceding
graph and captured absence, mkdir, immediately stat/open/check the new named
directory, record its authorized identity, verify and fsync its parent before
the next step. EEXIST after captured absence is lineage refusal. A mkdir that
raises but leaves a present name is an unverified late arrival: never adopt or
delete it. If mkdir succeeds but post-stat/open fails, keep any observations
actually obtained and refuse without inventing ownership. Portable mkdir offers
no atomic returned inode: the guarantee starts at the first captured identity.
Verified empty created directories remain after later failure, with no rollback.

The installer records phases idle, temp_created, writing, temp_ready, linked,
cleaned, durable, returning to idle only after success. Keep target/payload,
bounded random temporary basename `.ce-tmp-` plus 32 lower-hex characters,
returned fd identity, written count, successful-link-return flag, observed final
identity, temporary absence and durability state. Register the temp returned fd
immediately; never infer ownership from a later path stat. During temp_created
and writing, permit only that inode's expected size/time changes. Do not write
more than the exact payload. Handle positive short writes in chunks at most
65536; zero progress is an I/O refusal.

Check all retained names and sets before and after every write and every
temp/link/unlink transition. At temp_ready require exact complete payload,
mode 0600, regular type and one link through the same temp fd and named edge.
Use no-replace descriptor-relative `_link` with follow_symlinks=False, from
owned temp to initially absent final. No replacing rename or copy fallback.
Before publication perform full verification and file fsync; after successful
link return require both names and retained fd to be the same exact inode,
payload/mode and two links. Only then enter linked.

Before unlink, check exact temp ownership and phase; unlink only the owned name.
Require checked temporary absence and exact final single-link bytes afterward.
At cleaned, record the authorized final stamp, complete-set addition and C+N
logical count before directory fsync. Full-verify, fsync parent, full-verify and
enter durable; clear in-flight state only on successful completion. A directory
fsync failure after cleaned leaves the verified installed prefix with refusal.
Never roll back or delete an unverified final path.

On zero/failed writes, file fsync or link failure before final creation, attempt
checked owned-temp cleanup and retain the original I/O error unless a higher
priority final or cleanup error applies. A disappearing/replaced/unsafe temp
forbids unlinking its observed replacement. A final late arrival or EEXIST is
lineage failure even with matching bytes. A link syscall that raises but leaves
any final present has not authorized installation: final is late arrival and
must not be adopted/deleted; remove temp only if exact ownership and safe cleanup
are provable without adopting that final. A successful link followed by failure
keeps its success flag and actual phase; do not erase it to make checks pass.

If unlink raises and the temp still exists unchanged, report cleanup error and
retain the leftover phase. If unlink was attempted from a checked linked phase
and raises after effect, but temp is now absent and final exact/single-link,
record that observed cleaned prefix while retaining the I/O refusal. Absence
observed before this command's unlink attempt is lineage, not that exception.
No syscall exception becomes success because a later observation looks complete.
Stat/unlink is not atomic compare-and-unlink; test persistent substitutions and
make no claim to exclude unobserved external writer races.

## Verification cadence, precedence and cleanup

Implement separate names/set and full verification on the same graph. Names/set
verification checks first/current allowed named and fd stamps, absences and
bounded complete sets, accounting for the exact active temp phase. Full
verification brackets same-descriptor exact byte rereads with names/set checks;
the last names/set sweep occurs after all byte groups. Full passes occur after
initial acquisition, before first install, before each publication, after checked
temp cleanup, after directory fsync, and on every context-manager exit. During a
partial-write error, verify the recorded written prefix of the owned temp if
readable before cleanup. Do not reread every complete input on every one-byte
write: names checks follow each short write, full passes follow the bounded
installation checkpoints. Do not recursively scan unrelated directories.

Final verification attempts every reached group in this exact order: checkout,
ancestors, resources, metadata, bundle, output_layout, output_files, installation.
Within each group use the fixed checkpoint order and already validated logical
names in byte order, never set iteration or raw host paths. Retain at most one
selected failure per group and the bounded ordered unique failed-group list.
Persistent changed or uncheckable retained lineage selects WORK_PATH_UNSAFE for
the first failed group and overrides semantic, operation and cleanup errors.
With no lineage failure, cleanup error overrides the original error; otherwise
propagate the original error unchanged, according to the exact selection below. Initially unchanged missing or malformed
resources keep their resource-invalid error. Unexpected exceptions and
KeyboardInterrupt/SystemExit execute the same checks and cleanup, never success.

Close descriptors in reverse acquisition order, with the duplicated lock
description last. Record a close error and attempt all remaining closes once;
never retry a failed close on an fd number that might have been released/reused.
Preserve preceding lineage error over close failures. Attempt checked owned-temp
cleanup on every exceptional exit after creation. Keep all observations through
final checks and cleanup and do not emit successful data from the graph itself.

Before finalizer actions, save the actual original BaseException object, if any,
and retain the install record's last phase and observed successful-link/cleaned
prefix flags. Do not construct a generic substitute for a kernel, config,
public, unexpected or interruption exception.

Attempt every reached final-verification group and the applicable checked
owned-temp and descriptor cleanup. Keep all reached observations and any
lineage failures through these actions. Final selection is explicitly:

1. If any persistent lineage check failed or was uncheckable, select the first
   failed group in the fixed group order above as WORK_PATH_UNSAFE.
2. Otherwise, if cleanup failed, select the bounded cleanup error.
3. Otherwise, if an original exception was saved, propagate that same original
   object unchanged, including its class, code/message/details when present and
   KeyboardInterrupt/SystemExit identity.
4. Otherwise complete the context-manager exit successfully.

Do not enter idle after a failed installation. Enter idle only after a durable
successful completion. Post-effect observations may preserve an authorized
cleaned prefix or a successful-link flag, but never turn the syscall exception
into success. No snapshot/layout success is returned during an in-flight phase.
All-groups checking, last name/set sweep, checked temp ownership,
reverse closes with lock duplicate last and no retry of failed closes remain
required. Finalizer failures do not skip later reached groups or descriptor
cleanup. If a higher-priority failure is selected, use only bounded prior fields;
never add arbitrary original messages or exception objects to its detail map.

When propagating an unchanged original exception, preserve its existing cause
and context behavior rather than mutating that accepted exception object. New
I/O facade, adapter and private helper raises suppress unrelated raw context as
their own boundary requires. This keeps the existing kernel behavior unchanged.

## Safe error facade, fixed literal table and bounded contexts

Define CodeProofIOError with read-only code, message, details and exit_code
properties; exit_code is 2, details returns a fresh plain-data copy. The graph
never emits the CLI's outer JSON envelope. All direct boundary raises suppress
raw exception context. Messages come only from the following exact fixed literal code-to-message table.

The CodeProofIOError factory selects its message solely from this table.
Callers cannot provide a message. The code, reason and details are independent
of these fixed literals; no raw exception or source value is interpolated.

| Code | Exact message |
| --- | --- |
| WORKSPACE_ROOT_INVALID | CODE workspace root is invalid |
| INVALID_BATCH_ID | CODE batch identifier is invalid |
| WORK_PATH_UNSAFE | CODE retained path is unsafe |
| CODE_PROOF_IO_ERROR | CODE evidence I/O failed |
| CODE_PROOF_RESOURCE_INVALID | CODE evidence resource is invalid |
| CODE_PROOF_LIMIT_EXCEEDED | CODE evidence limit exceeded |
| CODE_PROOF_CONFLICT | CODE evidence artifact conflicts |
| CODE_PROOF_BUSY | CODE evidence workspace is busy |

This table applies only to this new facade. An unchanged propagated Git/config
exception keeps its original class, code, message and details, including a Git
kernel limit error that has the same code but its already accepted message.
The future public semantic error class likewise keeps its own fixed messages.
No legacy facade or envelope changes to match this table.

Malformed internal error construction must refuse with a fixed ValueError
message `Invalid CODE I/O error context`, suppressing unrelated exception
context. Validate exact builtin types and closed keys before set comparison or
lookup, and never evaluate arbitrary input formatting. The constructor accepts
only a code and its appropriate closed details, not a caller message or exit
code. Read-only properties expose independent copied data.

The eight allowed codes are WORKSPACE_ROOT_INVALID, INVALID_BATCH_ID,
WORK_PATH_UNSAFE, CODE_PROOF_IO_ERROR, CODE_PROOF_RESOURCE_INVALID,
CODE_PROOF_LIMIT_EXCEEDED, CODE_PROOF_CONFLICT, CODE_PROOF_BUSY. The six I/O,
authority, busy and resource codes have exactly nine detail fields: phase,
group, reason, operation, errno, prior_code, prior_operation, prior_errno,
failed_groups. Phase is setup, scan, retaining, any installer phase including
idle, final_verify or closing. Group is one of the eight ordered group tokens
or null before any group. Operation is null or open/stat/fstat/scandir/read/seek/
mkdir/write/link/unlink/fsync/flock/dup/close. Errno/prior_errno are null or exact
integers 0..65535. Reasons are unavailable_primitive, lock_busy, missing,
unsafe_type, unsafe_mode, link_count, edge_changed, bytes_changed, set_changed,
late_arrival, temp_ownership_lost, phase_mismatch, syscall_failed, zero_write,
path_spelling, overlap, unknown_entry, batch_id, marker_invalid, resource_hash,
resource_shape, resource_origin. failed_groups is unique and in fixed order,
with at most eight tokens. Never echo unvalidated keys, paths or raw messages.

LIMIT_EXCEEDED has exactly instance_pointer, limit_name, limit, observed;
CONFLICT has exactly instance_pointer, reason. Conflict reasons are
request_changed/acquisition_changed/config_format_changed/artifact_changed;
this layer's stable initial byte disagreement is artifact_changed. Limit keys
are the actual materialized/admission key and strict integer counts; fixed
ordinary input uses /input, planned peak uses /output. Other fixed positions and the closed recognized prior-code inventory are listed
below; do not invent or forward source-derived fields.
Preserve genuine pure kernel/public errors unchanged unless final precedence
overrides them. An overriding I/O error retains only recognized bounded prior
metadata, otherwise null, with no stringification of unknown exceptions.

For a per-file limit reached by install, use /request, /intent, /bundle,
/observation for the corresponding direct files; use /config or /handoffs for
the two derived families. For an initial output scan or retrospective setter
refusal without a parsed semantic plan, use /output rather than deriving an
instance pointer from an arbitrary filename or inferring a handoff plan index.
The later public preflight uses exact /handoffs/<index> for its known
path-ordered prospective plan. Peak limits always use /output.

Raw manifest byte limits use /bundle with max_bundle_bytes. Raw physical object count limits use /bodies with max_objects; validated
declared inventory count uses /objects with max_objects. Aggregate limits use /objects. With the validated ordered inventory, a per-body
limit may use /objects/<index>/body_size_bytes; before an inventory exists use
/objects. The limit names remain the actual frozen materialized keys, and
limit/observed remain exact nonnegative integers with a positive limit.
Stable initial install disagreement uses artifact_changed and the same fixed
per-family pointer rule. All these pointers name fixed wire fields and remain
within the existing 1024-character context bound.

The closed prior_code set is the union of this facade's eight codes, the ten
accepted Git codes, the ten accepted configuration codes, and the six public
semantic codes. In addition to this facade's codes, these are:

- CODE_PROOF_INPUT_INVALID, CODE_PROOF_OBJECT_EXTRA,
  CODE_PROOF_OBJECT_UNAVAILABLE, CODE_PROOF_OBJECT_SIZE_MISMATCH,
  CODE_PROOF_OBJECT_HASH_MISMATCH, CODE_PROOF_OBJECT_TYPE_MISMATCH,
  CODE_PROOF_COMMIT_INVALID, CODE_PROOF_TREE_INVALID,
  CODE_PROOF_CONSUMED_SET_MISMATCH (Git's LIMIT_EXCEEDED is already in the facade
  set).
- CODE_CONFIG_INPUT_INVALID, CODE_CONFIG_BYTES_INVALID, CODE_CONFIG_EMPTY,
  CODE_CONFIG_SYNTAX_INVALID, CODE_CONFIG_UNSUPPORTED,
  CODE_CONFIG_DUPLICATE_KEY, CODE_CONFIG_LIMIT_EXCEEDED,
  CODE_CONFIG_NUMBER_INVALID, CODE_CONFIG_DYNAMIC_UNSUPPORTED,
  CODE_CONFIG_PARSER_MISMATCH.
- CODE_PROOF_JSON_INVALID, CODE_PROOF_DOCUMENT_INVALID,
  CODE_PROOF_BINDING_MISMATCH, CODE_PROOF_STATE_INVALID, CODE_PROOF_NOT_READY,
  CODE_PROOF_TARGET_INELIGIBLE.

The union has 33 distinct codes. Retain only an exact builtin recognized string;
an unknown exception's unavailable/unsafe metadata yields null. No original
message, object formatting or arbitrary details are copied into prior fields.
Prior operation and errno use only the operation enum and 0..65535 bound above.
Preserving a prior code does not adopt or verify the original semantic result.
The same final group/cleanup precedence applies to known, unexpected and
interruption exceptions. No exception becomes a successful result.

## Required meaningful tests

Test actual retained source resources and genuine compiled context, ordinary
temporary checkouts with valid markers, and independent caller copies. Do not
mock pins or bypass compilation to make fixtures convenient. Runtime wheel
installation is independently verified by the integrator; source tests still
exercise both lexical origin cases and actual resource acquisition through the
seams. No test alters the real checkout, resource files, user Vault or global
os/fcntl functions. Put all fixture mutations in short isolated temporary trees.
Copy the actual fixed eleven resource byte files and preserve the actual accepted
foundation module filename in the isolated source/installed layout. Tests may
patch that module's __file__ only to select a genuine copied lexical origin plan;
never override its pins, compiler, registry or validation context. Do not mutate
tracked sources or shared resource files. Production always uses the unpatched
foundation origin selector. The integrator separately tests a fresh wheel import.

Cover setup before-yield errors, each missing primitive, lock busy/unsupported/
other errno, directory fsync unsupported/other failures, failed dup/close, exact
batch/root/marker rules and inactive resource wrappers. Cover initial resource
absence/unsafe state/partial read/pin failure, same-fd content changes, full stamp
changes, replaced/missing ancestors and resources changed during final reread.
Use a still-live original inode when building replacement fixtures; do not assume
unlink/recreate gives a different inode on every OS.

Cover bounded cap+1 scans, failures during enumeration/stat and final rescan,
unknown and unsafe siblings, every fixed missing slot, absent versus empty
families, cross-input/output/resource overlap, alias/link counts, exact ordinary
and body caps, all seven setter keys/types/boundaries, already retained over-limit
manifest/files, setter twice and install-before-set. Lower all three incoming
Git inventory/byte caps independently with the full five-key map.

Exercise fresh install, initially identical reuse, stable conflict, late equal
arrival, all C+2*N boundary cases, lazy directory creation and every mkdir
post-effect case, one-byte/zero/failed writes, file and directory fsync errors,
link failure before/after effect, unlink failure before/after effect, replaced
temp before link and cleanup, two-link/single-link phases, foreign final/temp
preservation and verified prefix after late failure. Instrument full reread
counts under one-byte writes to prove checkpoint cadence rather than unbounded
full revalidation per write.

Cause multiple groups to fail and prove all reached groups are attempted, first
group precedence is deterministic, last name sweep catches post-read changes,
cleanup overrides only when lineage is intact, remaining fds close once in
reverse order with lock duplicate last, and original semantic/interruption
errors cannot become success. Assert exact safe detail shapes, independent
copies, fixed messages and absence of adversarial markers in formatted exception
tracebacks. No test may weaken immutable first observations, pins, payload
checks, scope, zero-egress or final cleanup rules merely to pass.
