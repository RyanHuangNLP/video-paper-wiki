# CODE Git object kernel — R1 contract candidate

Architect-owned bounded contract. Pending independent review and a separate
freeze/dispatch record; this file alone is not permission to start writing.
Main implementation owner after dispatch: Grok CLI `grok-4.6 / xhigh`.

This kernel implements the raw Git proof portion of CODE-PROOF. It consumes only
in-memory data. Public envelopes, JSON decoding, resources, filesystem/staging,
normalized text, configuration parsing, repository hosting/officiality, canonical
source association, capture/publication, catalog and commands remain later work.
The full CODE goal still includes CODE-RELATION and CODE-CANONICAL.

The exact source workspace and baseline will be the new CODE worktree from the
locally delivered Discovery R3 successor of ef2ff13. Steward creates that worktree
and records its exact head before the implementation freeze. No older root
checkout production file may be used as the implementation baseline.

## Allowed implementation paths

Only these three paths relative to the CODE source checkout may be written:

1. `src/video_paper_wiki/code_git_objects.py`
2. `tests/unit/test_code_git_objects.py`
3. `tests/fixtures/code-git-objects-v1.json`

The third file is an exact copy of the independent static fixture delivered by
Steward and bound in the freeze. Grok may copy it but must not alter its bytes.
Tests and production must not invoke Git. No dependencies, package metadata,
legacy code/schema, CLI or other source files change in this packet. Grok may
write its named development brief/log evidence in the separately assigned packet
directory, then must stop all source writes. No Git mutation or extra agents.

The implementation module may use stdlib hashing, regular expressions and pure
typing/collection helpers. It must not import I/O, network, subprocess, repository
configuration, resource loaders, the schema registry or code-text/parser modules.
No filesystem or network operation may occur when calling these functions.

## API and strict types

```python
class CodeGitProofError(ValueError):
    # code: str, message: str, details: dict, exit_code: int = 2
    ...

def frame_git_object(object_type: str, body: bytes) -> bytes: ...

def git_object_ids(
    object_format: str, object_type: str, body: bytes,
) -> tuple[str, str, str]:
    # (Git OID, raw body SHA-256, framed SHA-256)
    ...

def verify_code_git_objects(
    *,
    object_format: str,
    commit_oid: str,
    root_tree_oid: str,
    objects: list[dict],
    bodies: dict[str, bytes],
    targets: list[dict],
    limits: dict[str, int],
) -> dict:
    ...
```

Only exact builtin dict/list/str/bytes/int/bool types are admitted where named.
Do not call user-defined Mapping/Sequence methods, coerce values, read file-like
objects or accept bytearray/memoryview as retained bytes. Inputs are not mutated.
Snapshot validated metadata into owned primitive containers. Callers must not
mutate input containers concurrently during a call; filesystem race protection
belongs to the later retained I/O layer, not this pure API.

All returned metadata is primitive integer-only JSON-compatible data. **No raw
bytes are returned inside the proof dict.** Callers retain the original immutable
`bodies` and use the exact validated blob OID/hash records to bind those bytes.
The helper `frame_git_object` separately returns bytes by design.

`object_format` is exactly `sha1` or `sha256`; OIDs are exactly 40 or 64 lowercase
hex respectively. No abbreviation, prefix, uppercase, coercion or format mapping.
Object types are exactly `commit`, `tree`, `blob`. Raw body hashes and framed
SHA-256 hashes are always 64 lowercase hex regardless of object_format.

`objects` is a nonempty OID-sorted unique list of closed records:

```text
{oid, object_type, body_size_bytes, body_sha256, framed_sha256}
```

Exactly one record has commit type, and its OID equals commit_oid. A second
commit, including a parent commit, is invalid input. Every record has a strict
nonnegative integer body_size_bytes. Empty tree/blob bodies are allowed. Presence
and type of the referenced root tree are checked explicitly, not inferred from
its 40/64-hex spelling. An OID cannot have two records/types.

`targets` is a nonempty path-sorted list of closed records:

```text
{path, allow_executable_source}
```

Flag is a strict bool; semantic role eligibility is enforced later by the request
validator. Paths have 1–32 slash-separated ASCII components and at most 512
bytes. Each component matches `[A-Za-z0-9._-]+`, but may not equal `.`, `..`, or
case-insensitive `.git`. No absolute path, backslash, empty component, URL,
wildcard or percent spelling. Leading-dot names such as `.github` are valid.
Paths are unique, sorted by ASCII/UTF-8 bytes and casefold-unique. No requested
path may be an ancestor of another requested path. Additionally, each casefolded
component-prefix across all targets must have one exact spelling: `A/x` together
with `a/y` is refused, so directory spellings cannot alias under casefold.
These remain logical Git paths, never filesystem paths opened by this kernel.

## Fixed profile and materialized limits

The five required limit keys and hard profile maxima are:

| key | maximum |
| --- | ---: |
| max_targets | 32 |
| max_objects | 2048 |
| max_tree_entries | 32768 |
| max_object_bytes | 8388608 |
| max_total_object_bytes | 33554432 |

`limits` has exactly those keys. Every value has exact type int and is in
1..maximum; bool is invalid. Callers may lower a limit. Helpers without a limits
argument still reject raw bodies over the fixed 8 MiB maximum before hashing or
framing. A zero-length body is different from a zero limit.

`CODE_GIT_PROFILE_LIMITS` exposes those exact five maximum values as a mapping
that callers cannot mutate; no module-global mutable default can weaken limits.
The fixed path limits, 65536-byte commit header limit and 1024 physical commit
header-line limit are not caller-adjustable in this first kernel profile.

## Verification order and budget accounting

1. Validate exact top-level container types, object_format, OID spelling, the
   complete limits map and target count. Validate target shapes, paths and order.
   Reject object count over its cap before iterating the object list. Validate
   every closed object record and its strict types, identity/order/uniqueness.
2. Before any body lookup, hashing or parsing, check each declared size against
   max_object_bytes and the aggregate declared body sum against its cap. Size
   declarations cannot bypass a zero-length or bool check.
3. Validate bodies keys as exact same-width OID strings. Its key set must equal
   the declared OID set. Extra keys take precedence over missing keys if both
   exist. `CODE_PROOF_OBJECT_EXTRA` / `CODE_PROOF_OBJECT_UNAVAILABLE` are hard
   failures. Do not iterate an arbitrarily huge bodies mapping: reject an excess
   mapping count before its key traversal.
4. Check every body is exact bytes, actual per-object/aggregate sizes fit caps,
   and actual sizes equal declarations. Complete these size checks before any
   hash. Actual cap violations take precedence over size mismatch. Then, in
   OID order, verify all three hashes and the declared type framing.
5. Require commit_oid to be the declared commit; parse its headers. Require
   root_tree_oid to name a declared tree; parse every declared tree once in OID
   order, including a tree later found unused. Charge each parsed entry before
   appending/storing it; refuse immediately past max_tree_entries. Empty trees
   are valid. Tree syntax does not depend on target selection.
6. Walk targets in path order. Every intermediate tree and permitted terminal
   blob must be declared with the correct type and verified body. A needed
   undeclared OID is OBJECT_UNAVAILABLE; a declared wrong type is TYPE_MISMATCH.
   Never treat a missing object body as a proven missing filename.
7. Consumed OIDs are exactly the requested commit, the root and intermediate
   trees actually visited, and permitted terminal blobs. Require this set to
   equal all declared OIDs. Unused trees/blobs, parent commits and unsafe-target
   bodies cannot be silently retained. Reuse a shared blob once in this set but
   report each requested logical path separately.

Reject any hard failure without returning a partial proof. Work is bounded by
the object count/body sums, unique-tree entry count and at most 32x32 matched
target edges. Walks iterate the explicit component list; no recursive unbounded
tree traversal or recursive expansion of unrelated directories occurs. Repeated
tree OIDs across paths are safe and parsed once. Do not mock away cryptographic
checks to claim a hash-valid cyclic Git fixture; such a self-referential OID
requires a preimage/fixed point, not an ordinary constructible fixture.

## Git object framing

For raw body B, frame exactly `ASCII(type) + b' ' + ASCII(len(B)) + b'\0' + B`.
Length is unsigned canonical base-10 with no leading zero, except zero itself.
Git OID is SHA-1 of the frame for sha1, or SHA-256 of the frame for sha256. Use
SHA-1 as Git content identity (`usedforsecurity=False` where supported). Raw
body_sha256 hashes B only; framed_sha256 hashes the complete frame.

For sha256 the Git OID must equal framed_sha256. It is not the raw body hash.
No API in this packet accepts a caller-supplied frame/header: helpers construct
the canonical frame, and verify consumes raw bodies. A blob whose content starts
with `blob 07\0` is ordinary raw bytes; do not invent a framing-parser refusal
for it. Tests may use a noncanonical frame to compute a wrong declared OID and
prove OBJECT_HASH_MISMATCH, but there is no unused FRAMING_INVALID error code.

## Commit syntax

The first physical line is exactly `tree SP <same-format lowercase OID> LF`.
That parsed OID must equal root_tree_oid. The first LF LF terminates the header
section; absence is COMMIT_INVALID. Limit the header section, including its
terminating blank line, to 65536 bytes and 1024 physical nonempty header lines.
The message after that separator is opaque bytes and may be empty.

Headers are LF-oriented with no CR or NUL. Top-level header keys are nonempty
ASCII `[A-Za-z0-9-]+`, followed by one SP and an opaque value. Only initial SP
marks a continuation, and it must follow an ordinary non-structural header.
A continuation cannot attach to tree or parent. TAB-prefixed header lines are
invalid. Tree occurs exactly once and first. Each parent line is exactly
`parent SP <same-width lowercase OID>`; zero or more are accepted, with no
attempt to follow or authenticate those parents. Other headers/continuations
and message bytes are retained only through hashes, not interpreted as author,
date, encoding, signature, remote ownership or a full `git fsck` verdict.

## Binary tree syntax and walking

Each tree entry is `ASCII(mode) SP raw_name NUL binary_oid`, with 20 or 32 OID
bytes according to object_format. Require complete exact framing to end of body.
Canonical accepted mode tokens are `40000`, `100644`, `100755`, `120000`, `160000`.
Noncanonical/unknown modes are TREE_INVALID, not an unsafe target outcome.
Names are nonempty raw bytes without slash and not `.` or `..`; NUL is only the
entry delimiter. Names are raw-byte unique. Unrelated names may be non-UTF-8;
never decode or normalize them to compare with requested ASCII components.

Require Git byte ordering: compare each `name + b'/'` for directory mode 40000,
or `name + b'\0'` otherwise. Do not sort an invalid tree into validity. For example
file `foo.bar`, directory `foo`, file `foo0` are in that order.

For an absent component in a verified tree, outcome is missing. For a matched
intermediate component, only mode 40000 permits descent; every other mode yields
unsafe/non_directory_intermediate and does not consume that entry's object.
For the terminal component, use this exact table:

| terminal mode | outcome | reason | consume terminal object |
| --- | --- | --- | --- |
| 100644 | permitted_regular_blob | null | yes, required type blob |
| 100755 with flag true | permitted_regular_blob | null | yes, required type blob |
| 100755 with flag false | unsafe | executable_without_permission | no |
| 120000 | unsafe | symlink | no |
| 160000 | unsafe | gitlink | no |
| 40000 | unsafe | directory | no |

Missing uses reason `absent_entry`. Unsafe/missing proof remains a useful complete
kernel result when the declared set matches exactly. It is not a full source
handoff. Never open/dereference/execute a source, symlink or gitlink. Raw regular
blob bytes may be binary, empty or invalid UTF-8 at this layer.

## Exact success result

Return a fresh dict with exactly:

```text
{
  object_format, commit_oid, root_tree_oid,
  object_records: [the checked five-field records, in OID order],
  consumed_oids: [all consumed OIDs, sorted],
  budget: {
    object_count, declared_body_bytes, actual_body_bytes,
    parsed_tree_entries, target_count, walk_edges
  },
  targets: [
    {
      path,
      outcome: permitted_regular_blob | missing | unsafe,
      reason: null | absent_entry | executable_without_permission | symlink |
              gitlink | directory | non_directory_intermediate,
      walk: [{tree_oid, name_hex, mode, oid}, ...],
      stopped_at: {component_index, tree_oid, name_hex, mode, oid},
      blob: null | {oid, body_size_bytes, body_sha256, framed_sha256}
    }, ...
  ]
}
```

`walk` records only matched entries in component order, including the terminal
or blocking matched entry. Each edge records the parent tree_oid and exact
entry name as lowercase hex. `stopped_at` names the attempted final/blocking
component with zero-based component_index; mode/oid are null only for an absent
name. For a matched terminal/blocking entry its other fields equal the final
walk edge. No matched edge is invented for a missing component. Blob is non-null
only for permitted_regular_blob and repeats its exact verified record subset.
budget.walk_edges is the sum of matched walk lengths, including repeated use by
different targets; parsed_tree_entries counts each declared tree only once.

Output containers must not alias input mutable containers. Preserve deterministic
dictionary construction/list ordering; no timestamps, process/path state or
floating values. Raw bytes are accessed by callers from retained input bodies,
not copied into this JSON-compatible proof result.

## Closed error surface

Raise CodeGitProofError with exit_code=2, fixed non-source-echoing message and
details containing a bounded `instance_pointer` plus the listed context. Never
include raw body text, decoded unrelated filenames or arbitrary input repr.

| code | condition / context |
| --- | --- |
| CODE_PROOF_INPUT_INVALID | bad exact type/shape/OID/format/order/limits/target/extra commit; pointer and bounded reason |
| CODE_PROOF_LIMIT_EXCEEDED | count, declared/actual bytes, tree entries or helper body cap; limit_name, limit, observed |
| CODE_PROOF_OBJECT_EXTRA | undeclared body keys; sorted extra_oids |
| CODE_PROOF_OBJECT_UNAVAILABLE | missing declared body or required undeclared tree/blob; sorted missing_oids |
| CODE_PROOF_OBJECT_SIZE_MISMATCH | actual size differs; oid, declared_size, actual_size |
| CODE_PROOF_OBJECT_HASH_MISMATCH | any of the three identities differs; oid, field (oid/body_sha256/framed_sha256) |
| CODE_PROOF_OBJECT_TYPE_MISMATCH | required tree/blob has another declared type; oid, expected_type, actual_type |
| CODE_PROOF_COMMIT_INVALID | malformed headers, header cap or root mismatch; oid, bounded reason |
| CODE_PROOF_TREE_INVALID | mode, entry framing/name/order/duplicate failure; oid, bounded reason, byte_offset |
| CODE_PROOF_CONSUMED_SET_MISMATCH | unused supplied objects after valid walks; sorted unused_oids |

Missing/unsafe filename outcomes are not these exceptions. Error pointers name
API fields/indices/OID keys, never host paths. Validation messages may vary in
wording but must retain the required code and structured context; tests assert
the meaningful condition/context and no raw source disclosure.

## Required verification

Use the independent static Git-produced sha1/sha256 fixture in the freeze, plus
hand-built malformed cases. Verify known empty SHA-1 blob OID, raw-vs-framed hashes,
both object formats, multi-parent and signed-style continuation headers, header
root mismatch, duplicate tree/parent grammar, CR/NUL/header limits, exact tree
ordering/modes/truncation/duplicate names and opaque non-UTF-8 sibling names.

Exercise permitted executable opt-in, all unsafe terminal outcomes, unsafe
intermediate components, a proven missing name, required omitted/mistyped object,
unused extra trees/blobs, extra/missing body keys, two paths sharing a blob,
repeated subtree use, casefold prefix/path/ancestor conflicts, hidden paths,
strict bool/int checks, all five lowerable limits, exact-size and hash mismatches.
Prove declared-size and actual-size cap refusals occur before hashing, using
independent instrumentation without accepting a forged positive proof.

Assert the exact success shape/counters and primitive output, deterministic
repeatability and unchanged inputs. After importing the module, guard filesystem,
network, subprocess and resource-loader entry points during a complete successful
proof and a refusal; the kernel must not invoke them. Tests cannot spawn Git or
network. Do not mock hashes to fabricate a valid self-referential graph.

Builder runs scoped tests with the locked environment and short /private/tmp
test directories. Architect and Steward review actual code and independent
counterexamples. Both Python full suites and installed-wheel validation are
required at the complete CODE-PROOF integration boundary; do not claim this
three-path kernel alone completes public CODE-PROOF or the remaining TODOs.
