# Generate one exact repair patch

You are Grok Build, acting as the implementation author for a bounded code repair.
This call asks for CODE AS YOUR FINAL ANSWER. Do not use tools, read files, write
files, run commands, update a todo list, or claim that any test was run. All the
source and contract material needed is embedded below. The coordinator will
apply your proposed patch and independently run the tests. Earlier interactive
attempts made no repair; do not repeat their completion claims or plans.

Return exactly one fenced `diff` block in apply_patch format:
`*** Begin Patch`, one or two `*** Update File: ABSOLUTE_PATH` sections, context
hunks using `@@`, and `*** End Patch`. Use real complete replacement lines, never
ellipses or placeholders. No explanatory text outside the patch. Do not include
line counts in hunk headers. Match old lines exactly to the embedded files.

Only these existing files may occur in Update File headers:

- /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source/src/video_paper_wiki/code_git_objects.py
- /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source/tests/unit/test_code_git_objects.py

No Add/Delete/Move File sections. Preserve every other path, especially the
static Git fixture. Keep the frozen pure API, error codes, output shape and
verification order unchanged. The two files below are the complete exact R3
preimages; no repair is already applied. Required changes are only:

1. In `_validate_limits`, `_validate_targets`, `_validate_objects`, reject keys
   whose type is not exactly str BEFORE set construction/equality, membership,
   lookup or formatting might invoke a user callback. First keep exact builtin
   dict and constant-time length guards, THEN iterate keys for exact type, THEN
   perform closed-set/membership/value validation. Use existing
   CODE_PROOF_INPUT_INVALID and bounded pointers/reasons. `_validate_bodies_map`
   already validates exact-str OID keys safely; preserve its production code.

2. Repair `test_declared_and_actual_caps_precede_hashing`. Construct fixture
   records before arming hash instrumentation, or reset immediately before each
   verification. Cover declared and actual per-object AND aggregate byte caps.
   Actual-cap cases must pass all declared caps and then exceed the intended
   actual cap, not accidentally fail a different declared-size check. Assert
   the structured limit context and zero hash calls during the rejected call;
   actual failures must point to `/bodies` or `/bodies/<oid>` as appropriate.

3. In `test_type_mismatch_omitted_object_and_unused_set`, the unused empty tree
   duplicates the empty root OID. Replace only that bad branch's data with a
   distinct, well-formed, hash-correct unused tree and assert the same specific
   CODE_PROOF_CONSUMED_SET_MISMATCH and exact unused OID. Preserve the already
   correct required wrong-type and omitted-object branches. A valid nonempty
   unused tree can refer to an unmaterialized unrelated child; it must parse
   but is not walked. Do not forge hashes or weaken refusal checks.

4. In `test_inputs_unchanged_outputs_unaliased_and_repeatable`, replace the
   unconditional `or True` assertion with a meaningful JSON round-trip/primitive
   check. Retain all no-bytes, deterministic, output-shape and no-alias checks.

5. Add focused regression tests for exact builtin dicts containing str-subclass
   keys with hostile hash/equality callbacks at limits, record, target and body
   locations, for both object formats. Arm callbacks only after constructing
   test inputs. Require CODE_PROOF_INPUT_INVALID without invoking any callback,
   and a valid proof afterward. The existing fixture and helpers provide valid
   data. Include ordinary strict-type/closed-shape behavior; no skipped tests.

Do not broaden implementation or refactor unrelated code. The independent
128-DAG oracle already passes; the broken tests are 33 passed / 2 failed in R3,
and the separate strict-input oracle exposes the three callback sites. A source
patch is required, not a statement that these tests passed. This single-output
request overrides implementation-run/brief instructions quoted in the original
contracts below: no tools or execution claims are part of your answer.


--- BEGIN REFERENCE CONTRACT CODE-GIT-KERNEL-R1.md ---
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

--- END REFERENCE CONTRACT ---


--- BEGIN REFERENCE CONTRACT CODE-GIT-KERNEL-CLARIFICATIONS-R2.md ---
# CODE Git kernel freeze clarifications — R2

Architect supplement to the unchanged CODE-GIT-KERNEL-R1.md, addressing the four
minor contract findings in `E/code-git-kernel-contract-review-r1.json`. The exact
workspace and immutable fixture remain bound by the separate freeze record.

## Helpers

Both helpers raise the same CodeGitProofError, exit_code=2. For git_object_ids,
validation order is object_format, object_type, body type, then body byte cap.
frame_git_object follows the same order without object_format. A bad exact type
or unsupported enum uses CODE_PROOF_INPUT_INVALID with instance_pointer exactly
`/object_format`, `/object_type` or `/body`, and a bounded reason string.

A bytes body longer than 8388608 bytes raises CODE_PROOF_LIMIT_EXCEEDED with
details exactly `{instance_pointer: "/body", limit_name: "max_object_bytes",
limit: 8388608, observed: len(body)}`. Perform the cap check before creating any
frame/header concatenation or invoking a hash. Empty bytes are valid. These are
the only helper refusal codes. There is no caller-supplied frame parser.

## Immutable profile

CODE_GIT_PROFILE_LIMITS is a `types.MappingProxyType` wrapping a fresh literal
dict, with no separately exposed mutable backing dict. Its insertion order and
values are exactly:

```text
max_targets: 32
max_objects: 2048
max_tree_entries: 32768
max_object_bytes: 8388608
max_total_object_bytes: 33554432
```

Item assignment/deletion and mutable-map operations cannot change it. Callers
use `dict(CODE_GIT_PROFILE_LIMITS)` to obtain a mutable per-call limits map.
Lowering that copy must not change the module profile or a later call's caps.
Deliberate monkeypatching of executable module globals/code is outside the
untrusted-input contract; this rule prevents an exposed mutable profile alias.

## Closed errors and result construction

Exactly the ten `CODE_PROOF_*` codes in the R1 error table are exposed. Short
uppercase phrases such as TYPE_MISMATCH, COMMIT_INVALID or TREE_INVALID in
explanatory prose denote their fully prefixed code in that table; they are not
additional error strings. The wrong-type code is
CODE_PROOF_OBJECT_TYPE_MISMATCH, with oid/expected_type/actual_type context.

Construct success dicts in the key order shown by R1's exact success result.
Construct object_records in the five-field declaration order. Construct blob
subrecords as oid, body_size_bytes, body_sha256, framed_sha256. The budget,
target, walk-edge and stopped_at orders are also exactly as displayed in R1.
Preserve the already defined list ordering. Future saved documents use their
own JCS wire contract; these return values do not themselves supply saved-byte
identity or a public envelope.

For a missing component, **name_hex is not null**: it is the exact attempted
component's ASCII bytes in lowercase hex. The chosen complete shape is:

```text
{
  component_index: <zero-based attempted component index>,
  tree_oid: <verified parent tree OID>,
  name_hex: <attempted component ASCII bytes as lowercase hex>,
  mode: null,
  oid: null
}
```

Only mode and oid are null. The review's suggested alternative with name_hex
null is rejected because it would lose the exact absent-name evidence. Walk
contains only actual matched entries. For example missing `src/no.py` retains
the root-to-src matched edge in walk and records `6e6f2e7079` in stopped_at's
name_hex at component_index 1, together with src's verified tree_oid.

No algorithm, source-text behavior, public transport or schema is added by this
supplement. Fixture bytes/head and the three-path allowlist must still be checked
in the separate implementation freeze before Builder dispatch.

--- END REFERENCE CONTRACT ---


--- BEGIN EXACT SOURCE /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source/src/video_paper_wiki/code_git_objects.py ---
"""Pure in-memory CODE Git object kernel.

Standard-library hashing and parsing only. No filesystem, network, Git,
subprocess, schema, or resource-loader operations occur in this module.
"""

from __future__ import annotations

import hashlib
import re
from types import MappingProxyType

CODE_PROOF_INPUT_INVALID = "CODE_PROOF_INPUT_INVALID"
CODE_PROOF_LIMIT_EXCEEDED = "CODE_PROOF_LIMIT_EXCEEDED"
CODE_PROOF_OBJECT_EXTRA = "CODE_PROOF_OBJECT_EXTRA"
CODE_PROOF_OBJECT_UNAVAILABLE = "CODE_PROOF_OBJECT_UNAVAILABLE"
CODE_PROOF_OBJECT_SIZE_MISMATCH = "CODE_PROOF_OBJECT_SIZE_MISMATCH"
CODE_PROOF_OBJECT_HASH_MISMATCH = "CODE_PROOF_OBJECT_HASH_MISMATCH"
CODE_PROOF_OBJECT_TYPE_MISMATCH = "CODE_PROOF_OBJECT_TYPE_MISMATCH"
CODE_PROOF_COMMIT_INVALID = "CODE_PROOF_COMMIT_INVALID"
CODE_PROOF_TREE_INVALID = "CODE_PROOF_TREE_INVALID"
CODE_PROOF_CONSUMED_SET_MISMATCH = "CODE_PROOF_CONSUMED_SET_MISMATCH"

_ERROR_MESSAGES = {
    CODE_PROOF_INPUT_INVALID: "code git proof input is invalid",
    CODE_PROOF_LIMIT_EXCEEDED: "code git proof limit exceeded",
    CODE_PROOF_OBJECT_EXTRA: "undeclared git object bodies were supplied",
    CODE_PROOF_OBJECT_UNAVAILABLE: "required git object is unavailable",
    CODE_PROOF_OBJECT_SIZE_MISMATCH: "git object size does not match declaration",
    CODE_PROOF_OBJECT_HASH_MISMATCH: "git object identity does not match declaration",
    CODE_PROOF_OBJECT_TYPE_MISMATCH: "git object type does not match requirement",
    CODE_PROOF_COMMIT_INVALID: "git commit object is invalid",
    CODE_PROOF_TREE_INVALID: "git tree object is invalid",
    CODE_PROOF_CONSUMED_SET_MISMATCH: "declared git objects were not exactly consumed",
}

CODE_GIT_PROFILE_LIMITS = MappingProxyType(
    {
        "max_targets": 32,
        "max_objects": 2048,
        "max_tree_entries": 32768,
        "max_object_bytes": 8388608,
        "max_total_object_bytes": 33554432,
    }
)

_OBJECT_TYPES = frozenset({"commit", "tree", "blob"})
_FORMAT_WIDTHS = {"sha1": 40, "sha256": 64}
_OBJECT_RECORD_KEYS = frozenset(
    {"oid", "object_type", "body_size_bytes", "body_sha256", "framed_sha256"}
)
_TARGET_KEYS = frozenset({"path", "allow_executable_source"})
_HEX_CHARS = frozenset("0123456789abcdef")
_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")
_HEADER_KEY = re.compile(rb"^[A-Za-z0-9-]+$")
_MODE_DIR = "40000"
_MODE_FILE = "100644"
_MODE_EXEC = "100755"
_MODE_LINK = "120000"
_MODE_GITLINK = "160000"
_VALID_MODES = frozenset(
    {_MODE_DIR, _MODE_FILE, _MODE_EXEC, _MODE_LINK, _MODE_GITLINK}
)
_COMMIT_HEADER_MAX_BYTES = 65536
_COMMIT_HEADER_MAX_LINES = 1024
_PATH_MAX_BYTES = 512
_PATH_MAX_COMPONENTS = 32
_HASH_FIELDS = ("oid", "body_sha256", "framed_sha256")


class CodeGitProofError(ValueError):
    """Closed CODE Git kernel refusal."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)
        self.exit_code = exit_code


def _raise(code: str, details: dict) -> None:
    raise CodeGitProofError(code, _ERROR_MESSAGES[code], details, 2)


def _input_invalid(instance_pointer: str, reason: str) -> None:
    _raise(
        CODE_PROOF_INPUT_INVALID,
        {"instance_pointer": instance_pointer, "reason": reason},
    )


def _limit_exceeded(
    instance_pointer: str,
    limit_name: str,
    limit: int,
    observed: int,
) -> None:
    _raise(
        CODE_PROOF_LIMIT_EXCEEDED,
        {
            "instance_pointer": instance_pointer,
            "limit_name": limit_name,
            "limit": limit,
            "observed": observed,
        },
    )


def _is_oid_str(value: object, width: int) -> bool:
    if type(value) is not str or len(value) != width:
        return False
    for char in value:
        if char not in _HEX_CHARS:
            return False
    return True


def _is_oid_bytes(value: bytes, width: int) -> bool:
    if len(value) != width:
        return False
    for byte in value:
        if byte not in b"0123456789abcdef":
            return False
    return True


def _require_str_enum(value: object, pointer: str, allowed: frozenset[str] | dict) -> str:
    if type(value) is not str:
        _input_invalid(pointer, "invalid_type")
    if value not in allowed:
        _input_invalid(pointer, "unsupported_value")
    return value


def _require_bytes(value: object, pointer: str) -> bytes:
    if type(value) is not bytes:
        _input_invalid(pointer, "invalid_type")
    return value


def _sha1_hex(data: bytes) -> str:
    try:
        return hashlib.sha1(data, usedforsecurity=False).hexdigest()
    except TypeError:
        return hashlib.sha1(data).hexdigest()


def _canonical_frame(object_type: str, body: bytes) -> bytes:
    return (
        object_type.encode("ascii")
        + b" "
        + str(len(body)).encode("ascii")
        + b"\0"
        + body
    )


def _reject_helper_body_cap(body: bytes) -> None:
    limit = CODE_GIT_PROFILE_LIMITS["max_object_bytes"]
    observed = len(body)
    if observed > limit:
        _raise(
            CODE_PROOF_LIMIT_EXCEEDED,
            {
                "instance_pointer": "/body",
                "limit_name": "max_object_bytes",
                "limit": 8388608,
                "observed": observed,
            },
        )


def frame_git_object(object_type: str, body: bytes) -> bytes:
    _require_str_enum(object_type, "/object_type", _OBJECT_TYPES)
    _require_bytes(body, "/body")
    _reject_helper_body_cap(body)
    return _canonical_frame(object_type, body)


def git_object_ids(
    object_format: str,
    object_type: str,
    body: bytes,
) -> tuple[str, str, str]:
    _require_str_enum(object_format, "/object_format", _FORMAT_WIDTHS)
    _require_str_enum(object_type, "/object_type", _OBJECT_TYPES)
    _require_bytes(body, "/body")
    _reject_helper_body_cap(body)
    frame = _canonical_frame(object_type, body)
    body_sha256 = hashlib.sha256(body).hexdigest()
    framed_sha256 = hashlib.sha256(frame).hexdigest()
    if object_format == "sha1":
        git_oid = _sha1_hex(frame)
    else:
        git_oid = framed_sha256
    return git_oid, body_sha256, framed_sha256


def _snapshot_object_record(record: dict) -> dict:
    return {
        "oid": record["oid"],
        "object_type": record["object_type"],
        "body_size_bytes": record["body_size_bytes"],
        "body_sha256": record["body_sha256"],
        "framed_sha256": record["framed_sha256"],
    }


def _validate_limits(limits: object) -> dict[str, int]:
    if type(limits) is not dict:
        _input_invalid("/limits", "invalid_type")
    if len(limits) != 5:
        _input_invalid("/limits", "limits_key_set")
    owned: dict[str, int] = {}
    for key, maximum in CODE_GIT_PROFILE_LIMITS.items():
        if key not in limits:
            _input_invalid("/limits", "limits_key_set")
        value = limits[key]
        pointer = "/limits/" + key
        if type(value) is not int:
            _input_invalid(pointer, "invalid_type")
        if value < 1 or value > maximum:
            _input_invalid(pointer, "out_of_range")
        owned[key] = value
    return owned


def _validate_oid_arg(value: object, pointer: str, width: int) -> str:
    if type(value) is not str:
        _input_invalid(pointer, "invalid_type")
    if not _is_oid_str(value, width):
        _input_invalid(pointer, "invalid_oid")
    return value


def _validate_path(path: object, pointer: str) -> list[str]:
    if type(path) is not str:
        _input_invalid(pointer, "invalid_type")
    if not path.isascii():
        _input_invalid(pointer, "invalid_path")
    if len(path) > _PATH_MAX_BYTES or "\\" in path:
        _input_invalid(pointer, "invalid_path")
    parts = path.split("/")
    if len(parts) < 1 or len(parts) > _PATH_MAX_COMPONENTS:
        _input_invalid(pointer, "invalid_path")
    for part in parts:
        if (
            part == ""
            or part == "."
            or part == ".."
            or part.casefold() == ".git"
            or _PATH_COMPONENT.fullmatch(part) is None
        ):
            _input_invalid(pointer, "invalid_path")
    return parts


def _validate_targets(targets: object, max_targets: int) -> list[dict]:
    if type(targets) is not list:
        _input_invalid("/targets", "invalid_type")
    count = len(targets)
    if count == 0:
        _input_invalid("/targets", "empty")
    if count > max_targets:
        _limit_exceeded("/targets", "max_targets", max_targets, count)
    owned: list[dict] = []
    seen_exact: set[str] = set()
    previous_path: str | None = None
    component_lists: list[list[str]] = []
    prefix_spellings: dict[tuple[str, ...], tuple[str, ...]] = {}
    for index, item in enumerate(targets):
        pointer = "/targets/" + str(index)
        if type(item) is not dict or len(item) != 2 or set(item) != _TARGET_KEYS:
            _input_invalid(pointer, "not_closed_record")
        path_pointer = pointer + "/path"
        components = _validate_path(item["path"], path_pointer)
        flag = item["allow_executable_source"]
        if type(flag) is not bool:
            _input_invalid(pointer + "/allow_executable_source", "invalid_type")
        path = item["path"]
        if path in seen_exact:
            _input_invalid(path_pointer, "duplicate_path")
        seen_exact.add(path)
        if previous_path is not None and path <= previous_path:
            _input_invalid(path_pointer, "not_sorted")
        previous_path = path
        for depth in range(1, len(components) + 1):
            exact = tuple(components[:depth])
            folded = tuple(part.casefold() for part in exact)
            existing = prefix_spellings.get(folded)
            if existing is not None and existing != exact:
                _input_invalid(path_pointer, "casefold_conflict")
            prefix_spellings[folded] = exact
        for earlier in component_lists:
            if len(earlier) < len(components) and components[: len(earlier)] == earlier:
                _input_invalid(path_pointer, "ancestor_conflict")
        component_lists.append(components)
        owned.append(
            {
                "path": path,
                "allow_executable_source": flag,
                "components": components,
            }
        )
    return owned


def _validate_objects(
    objects: object,
    commit_oid: str,
    width: int,
    max_objects: int,
) -> list[dict]:
    if type(objects) is not list:
        _input_invalid("/objects", "invalid_type")
    count = len(objects)
    if count == 0:
        _input_invalid("/objects", "empty")
    if count > max_objects:
        _limit_exceeded("/objects", "max_objects", max_objects, count)
    owned: list[dict] = []
    previous_oid: str | None = None
    commit_count = 0
    commit_record_oid: str | None = None
    for index, item in enumerate(objects):
        pointer = "/objects/" + str(index)
        if type(item) is not dict or len(item) != 5 or set(item) != _OBJECT_RECORD_KEYS:
            _input_invalid(pointer, "not_closed_record")
        oid = item["oid"]
        if not _is_oid_str(oid, width):
            _input_invalid(pointer + "/oid", "invalid_oid")
        if previous_oid is not None and oid <= previous_oid:
            _input_invalid(pointer + "/oid", "not_sorted_or_duplicate")
        previous_oid = oid
        object_type = item["object_type"]
        if type(object_type) is not str or object_type not in _OBJECT_TYPES:
            _input_invalid(pointer + "/object_type", "unsupported_value")
        size = item["body_size_bytes"]
        if type(size) is not int:
            _input_invalid(pointer + "/body_size_bytes", "invalid_type")
        if size < 0:
            _input_invalid(pointer + "/body_size_bytes", "out_of_range")
        body_sha256 = item["body_sha256"]
        if not _is_oid_str(body_sha256, 64):
            _input_invalid(pointer + "/body_sha256", "invalid_oid")
        framed_sha256 = item["framed_sha256"]
        if not _is_oid_str(framed_sha256, 64):
            _input_invalid(pointer + "/framed_sha256", "invalid_oid")
        if object_type == "commit":
            commit_count += 1
            if commit_count > 1:
                _input_invalid(pointer + "/object_type", "multiple_commits")
            commit_record_oid = oid
        owned.append(
            {
                "oid": oid,
                "object_type": object_type,
                "body_size_bytes": size,
                "body_sha256": body_sha256,
                "framed_sha256": framed_sha256,
            }
        )
    if commit_count != 1:
        _input_invalid("/objects", "missing_commit")
    if commit_record_oid != commit_oid:
        _input_invalid("/commit_oid", "commit_oid_mismatch")
    return owned


def _check_declared_sizes(records: list[dict], limits: dict[str, int]) -> int:
    declared_sum = 0
    max_object_bytes = limits["max_object_bytes"]
    max_total = limits["max_total_object_bytes"]
    for index, record in enumerate(records):
        size = record["body_size_bytes"]
        if size > max_object_bytes:
            _limit_exceeded(
                "/objects/" + str(index) + "/body_size_bytes",
                "max_object_bytes",
                max_object_bytes,
                size,
            )
        declared_sum += size
    if declared_sum > max_total:
        _limit_exceeded(
            "/objects",
            "max_total_object_bytes",
            max_total,
            declared_sum,
        )
    return declared_sum


def _validate_bodies_map(
    bodies: object,
    records: list[dict],
    width: int,
    max_objects: int,
) -> None:
    if type(bodies) is not dict:
        _input_invalid("/bodies", "invalid_type")
    observed = len(bodies)
    if observed > max_objects:
        _limit_exceeded("/bodies", "max_objects", max_objects, observed)
    declared = {record["oid"] for record in records}
    extra: list[str] = []
    for key in bodies:
        if not _is_oid_str(key, width):
            _input_invalid("/bodies", "invalid_oid_key")
        if key not in declared:
            extra.append(key)
    if extra:
        _raise(
            CODE_PROOF_OBJECT_EXTRA,
            {
                "instance_pointer": "/bodies",
                "extra_oids": sorted(extra),
            },
        )
    missing = [record["oid"] for record in records if record["oid"] not in bodies]
    if missing:
        _raise(
            CODE_PROOF_OBJECT_UNAVAILABLE,
            {
                "instance_pointer": "/bodies",
                "missing_oids": sorted(missing),
            },
        )


def _validate_actual_bodies(
    records: list[dict],
    bodies: dict,
    limits: dict[str, int],
) -> tuple[dict[str, bytes], int]:
    owned_bodies: dict[str, bytes] = {}
    actual_sum = 0
    max_object_bytes = limits["max_object_bytes"]
    max_total = limits["max_total_object_bytes"]
    first_object_cap: tuple[str, int, int] | None = None
    total_observed: int | None = None
    first_mismatch: tuple[str, int, int, int] | None = None
    for index, record in enumerate(records):
        oid = record["oid"]
        body = bodies[oid]
        if type(body) is not bytes:
            _input_invalid("/bodies/" + oid, "invalid_type")
        actual = len(body)
        if first_object_cap is None and actual > max_object_bytes:
            first_object_cap = (oid, index, actual)
        actual_sum += actual
        if total_observed is None and actual_sum > max_total:
            total_observed = actual_sum
        if first_mismatch is None and actual != record["body_size_bytes"]:
            first_mismatch = (oid, index, record["body_size_bytes"], actual)
        owned_bodies[oid] = body
    if first_object_cap is not None:
        oid, index, actual = first_object_cap
        _limit_exceeded(
            "/bodies/" + oid,
            "max_object_bytes",
            max_object_bytes,
            actual,
        )
    if total_observed is not None:
        _limit_exceeded(
            "/bodies",
            "max_total_object_bytes",
            max_total,
            total_observed,
        )
    if first_mismatch is not None:
        oid, index, declared_size, actual_size = first_mismatch
        _raise(
            CODE_PROOF_OBJECT_SIZE_MISMATCH,
            {
                "instance_pointer": "/objects/" + str(index) + "/body_size_bytes",
                "oid": oid,
                "declared_size": declared_size,
                "actual_size": actual_size,
            },
        )
    return owned_bodies, actual_sum


def _verify_hashes(
    object_format: str,
    records: list[dict],
    bodies: dict[str, bytes],
) -> None:
    for index, record in enumerate(records):
        oid = record["oid"]
        computed_oid, computed_body, computed_framed = git_object_ids(
            object_format,
            record["object_type"],
            bodies[oid],
        )
        computed = {
            "oid": computed_oid,
            "body_sha256": computed_body,
            "framed_sha256": computed_framed,
        }
        for field in _HASH_FIELDS:
            if record[field] != computed[field]:
                _raise(
                    CODE_PROOF_OBJECT_HASH_MISMATCH,
                    {
                        "instance_pointer": "/objects/" + str(index) + "/" + field,
                        "oid": oid,
                        "field": field,
                    },
                )


def _commit_invalid(oid: str, reason: str) -> None:
    _raise(
        CODE_PROOF_COMMIT_INVALID,
        {
            "instance_pointer": "/objects",
            "oid": oid,
            "reason": reason,
        },
    )


def _parse_commit(
    oid: str,
    body: bytes,
    object_format: str,
    root_tree_oid: str,
) -> None:
    width = _FORMAT_WIDTHS[object_format]
    separator = body.find(b"\n\n")
    if separator < 0:
        _commit_invalid(oid, "missing_header_terminator")
    header_section = body[: separator + 2]
    if len(header_section) > _COMMIT_HEADER_MAX_BYTES:
        _commit_invalid(oid, "header_too_large")
    if b"\0" in header_section:
        _commit_invalid(oid, "header_contains_nul")
    if b"\r" in header_section:
        _commit_invalid(oid, "header_contains_cr")
    raw_lines = header_section.split(b"\n")
    if len(raw_lines) < 2 or raw_lines[-1] != b"" or raw_lines[-2] != b"":
        _commit_invalid(oid, "missing_header_terminator")
    lines = raw_lines[:-2]
    if len(lines) > _COMMIT_HEADER_MAX_LINES:
        _commit_invalid(oid, "too_many_header_lines")
    if not lines:
        _commit_invalid(oid, "missing_tree_header")
    prev_kind = None
    tree_seen = False
    for index, line in enumerate(lines):
        if line.startswith(b"\t"):
            _commit_invalid(oid, "tab_prefixed_header")
        if line.startswith(b" "):
            if prev_kind != "ordinary":
                _commit_invalid(oid, "invalid_continuation")
            continue
        space = line.find(b" ")
        if space <= 0:
            _commit_invalid(oid, "malformed_header")
        key = line[:space]
        value = line[space + 1 :]
        if _HEADER_KEY.fullmatch(key) is None:
            _commit_invalid(oid, "malformed_header")
        if index == 0:
            if key != b"tree" or not _is_oid_bytes(value, width):
                _commit_invalid(oid, "invalid_tree_header")
            parsed_tree = value.decode("ascii")
            if parsed_tree != root_tree_oid:
                _commit_invalid(oid, "root_tree_mismatch")
            tree_seen = True
            prev_kind = "structural"
            continue
        if key == b"tree":
            _commit_invalid(oid, "duplicate_tree_header")
        if key == b"parent":
            if not _is_oid_bytes(value, width):
                _commit_invalid(oid, "invalid_parent_header")
            prev_kind = "structural"
            continue
        prev_kind = "ordinary"
    if not tree_seen:
        _commit_invalid(oid, "missing_tree_header")


def _tree_invalid(oid: str, reason: str, byte_offset: int) -> None:
    _raise(
        CODE_PROOF_TREE_INVALID,
        {
            "instance_pointer": "/objects",
            "oid": oid,
            "reason": reason,
            "byte_offset": byte_offset,
        },
    )


def _parse_tree(
    oid: str,
    body: bytes,
    object_format: str,
    max_tree_entries: int,
    parsed_count: int,
) -> tuple[dict[bytes, dict], int]:
    oid_raw_len = 20 if object_format == "sha1" else 32
    by_name: dict[bytes, dict] = {}
    offset = 0
    length = len(body)
    previous_key: bytes | None = None
    while offset < length:
        entry_start = offset
        space = body.find(b" ", offset)
        if space < 0:
            _tree_invalid(oid, "truncated_mode", entry_start)
        mode_bytes = body[offset:space]
        try:
            mode = mode_bytes.decode("ascii")
        except UnicodeDecodeError:
            _tree_invalid(oid, "invalid_mode", entry_start)
        if mode not in _VALID_MODES:
            _tree_invalid(oid, "invalid_mode", entry_start)
        name_start = space + 1
        nul = body.find(b"\0", name_start)
        if nul < 0:
            _tree_invalid(oid, "truncated_name", entry_start)
        name = body[name_start:nul]
        if name == b"" or b"/" in name or name == b"." or name == b"..":
            _tree_invalid(oid, "invalid_name", entry_start)
        if name in by_name:
            _tree_invalid(oid, "duplicate_name", entry_start)
        oid_start = nul + 1
        oid_end = oid_start + oid_raw_len
        if oid_end > length:
            _tree_invalid(oid, "truncated_oid", entry_start)
        hex_oid = body[oid_start:oid_end].hex()
        sort_key = name + (b"/" if mode == _MODE_DIR else b"\0")
        if previous_key is not None and sort_key <= previous_key:
            _tree_invalid(oid, "invalid_order", entry_start)
        parsed_count += 1
        if parsed_count > max_tree_entries:
            _limit_exceeded(
                "/objects",
                "max_tree_entries",
                max_tree_entries,
                parsed_count,
            )
        by_name[name] = {
            "mode": mode,
            "name": name,
            "oid": hex_oid,
        }
        previous_key = sort_key
        offset = oid_end
    return by_name, parsed_count


def _require_declared_type(
    oid: str,
    expected_type: str,
    records_by_oid: dict[str, dict],
) -> dict:
    record = records_by_oid.get(oid)
    if record is None:
        _raise(
            CODE_PROOF_OBJECT_UNAVAILABLE,
            {
                "instance_pointer": "/objects",
                "missing_oids": sorted([oid]),
            },
        )
    actual_type = record["object_type"]
    if actual_type != expected_type:
        _raise(
            CODE_PROOF_OBJECT_TYPE_MISMATCH,
            {
                "instance_pointer": "/objects",
                "oid": oid,
                "expected_type": expected_type,
                "actual_type": actual_type,
            },
        )
    return record


def _blob_subrecord(record: dict) -> dict:
    return {
        "oid": record["oid"],
        "body_size_bytes": record["body_size_bytes"],
        "body_sha256": record["body_sha256"],
        "framed_sha256": record["framed_sha256"],
    }


def _walk_targets(
    targets: list[dict],
    root_tree_oid: str,
    parsed_trees: dict[str, dict[bytes, dict]],
    records_by_oid: dict[str, dict],
    consumed: set[str],
) -> tuple[list[dict], int]:
    results: list[dict] = []
    walk_edges = 0
    for target in targets:
        components = target["components"]
        allow_exec = target["allow_executable_source"]
        current_tree_oid = root_tree_oid
        walk: list[dict] = []
        outcome = None
        reason = None
        stopped_at = None
        blob = None
        for index, component in enumerate(components):
            name = component.encode("ascii")
            entry = parsed_trees[current_tree_oid].get(name)
            is_last = index == len(components) - 1
            if entry is None:
                outcome = "missing"
                reason = "absent_entry"
                stopped_at = {
                    "component_index": index,
                    "tree_oid": current_tree_oid,
                    "name_hex": name.hex(),
                    "mode": None,
                    "oid": None,
                }
                break
            edge = {
                "tree_oid": current_tree_oid,
                "name_hex": entry["name"].hex(),
                "mode": entry["mode"],
                "oid": entry["oid"],
            }
            walk.append(edge)
            if not is_last:
                if entry["mode"] != _MODE_DIR:
                    outcome = "unsafe"
                    reason = "non_directory_intermediate"
                    stopped_at = {
                        "component_index": index,
                        "tree_oid": current_tree_oid,
                        "name_hex": edge["name_hex"],
                        "mode": entry["mode"],
                        "oid": entry["oid"],
                    }
                    break
                _require_declared_type(entry["oid"], "tree", records_by_oid)
                consumed.add(entry["oid"])
                current_tree_oid = entry["oid"]
                continue
            mode = entry["mode"]
            stopped_at = {
                "component_index": index,
                "tree_oid": current_tree_oid,
                "name_hex": edge["name_hex"],
                "mode": mode,
                "oid": entry["oid"],
            }
            if mode == _MODE_FILE or (mode == _MODE_EXEC and allow_exec):
                record = _require_declared_type(entry["oid"], "blob", records_by_oid)
                consumed.add(entry["oid"])
                outcome = "permitted_regular_blob"
                reason = None
                blob = _blob_subrecord(record)
            elif mode == _MODE_EXEC:
                outcome = "unsafe"
                reason = "executable_without_permission"
            elif mode == _MODE_LINK:
                outcome = "unsafe"
                reason = "symlink"
            elif mode == _MODE_GITLINK:
                outcome = "unsafe"
                reason = "gitlink"
            else:
                outcome = "unsafe"
                reason = "directory"
        walk_edges += len(walk)
        results.append(
            {
                "path": target["path"],
                "outcome": outcome,
                "reason": reason,
                "walk": walk,
                "stopped_at": stopped_at,
                "blob": blob,
            }
        )
    return results, walk_edges


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
    if type(objects) is not list:
        _input_invalid("/objects", "invalid_type")
    if type(bodies) is not dict:
        _input_invalid("/bodies", "invalid_type")
    if type(targets) is not list:
        _input_invalid("/targets", "invalid_type")
    object_format = _require_str_enum(
        object_format, "/object_format", _FORMAT_WIDTHS
    )
    width = _FORMAT_WIDTHS[object_format]
    commit_oid = _validate_oid_arg(commit_oid, "/commit_oid", width)
    root_tree_oid = _validate_oid_arg(root_tree_oid, "/root_tree_oid", width)
    owned_limits = _validate_limits(limits)
    owned_targets = _validate_targets(targets, owned_limits["max_targets"])
    owned_records = _validate_objects(
        objects,
        commit_oid,
        width,
        owned_limits["max_objects"],
    )
    declared_body_bytes = _check_declared_sizes(owned_records, owned_limits)
    _validate_bodies_map(
        bodies,
        owned_records,
        width,
        owned_limits["max_objects"],
    )
    owned_bodies, actual_body_bytes = _validate_actual_bodies(
        owned_records,
        bodies,
        owned_limits,
    )
    _verify_hashes(object_format, owned_records, owned_bodies)
    records_by_oid = {record["oid"]: record for record in owned_records}
    _parse_commit(
        commit_oid,
        owned_bodies[commit_oid],
        object_format,
        root_tree_oid,
    )
    _require_declared_type(root_tree_oid, "tree", records_by_oid)
    parsed_trees: dict[str, dict[bytes, dict]] = {}
    parsed_tree_entries = 0
    for record in owned_records:
        if record["object_type"] != "tree":
            continue
        by_name, parsed_tree_entries = _parse_tree(
            record["oid"],
            owned_bodies[record["oid"]],
            object_format,
            owned_limits["max_tree_entries"],
            parsed_tree_entries,
        )
        parsed_trees[record["oid"]] = by_name
    consumed = {commit_oid, root_tree_oid}
    target_results, walk_edges = _walk_targets(
        owned_targets,
        root_tree_oid,
        parsed_trees,
        records_by_oid,
        consumed,
    )
    declared_oids = [record["oid"] for record in owned_records]
    unused = [oid for oid in declared_oids if oid not in consumed]
    if unused:
        _raise(
            CODE_PROOF_CONSUMED_SET_MISMATCH,
            {
                "instance_pointer": "/objects",
                "unused_oids": sorted(unused),
            },
        )
    object_records = [_snapshot_object_record(record) for record in owned_records]
    return {
        "object_format": object_format,
        "commit_oid": commit_oid,
        "root_tree_oid": root_tree_oid,
        "object_records": object_records,
        "consumed_oids": sorted(consumed),
        "budget": {
            "object_count": len(owned_records),
            "declared_body_bytes": declared_body_bytes,
            "actual_body_bytes": actual_body_bytes,
            "parsed_tree_entries": parsed_tree_entries,
            "target_count": len(owned_targets),
            "walk_edges": walk_edges,
        },
        "targets": target_results,
    }

--- END EXACT SOURCE ---


--- BEGIN EXACT SOURCE /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source/tests/unit/test_code_git_objects.py ---
from __future__ import annotations

import builtins
import copy
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from types import MappingProxyType

import pytest

from video_paper_wiki.code_git_objects import (
    CODE_GIT_PROFILE_LIMITS,
    CODE_PROOF_COMMIT_INVALID,
    CODE_PROOF_CONSUMED_SET_MISMATCH,
    CODE_PROOF_INPUT_INVALID,
    CODE_PROOF_LIMIT_EXCEEDED,
    CODE_PROOF_OBJECT_EXTRA,
    CODE_PROOF_OBJECT_HASH_MISMATCH,
    CODE_PROOF_OBJECT_SIZE_MISMATCH,
    CODE_PROOF_OBJECT_TYPE_MISMATCH,
    CODE_PROOF_OBJECT_UNAVAILABLE,
    CODE_PROOF_TREE_INVALID,
    CodeGitProofError,
    frame_git_object,
    git_object_ids,
    verify_code_git_objects,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "code-git-objects-v1.json"
)
FIXTURE_SHA256 = "b8936db0a65d58d533016840e3d7cfbc686f819b240c812207e73638165955f0"
FIXTURE_SIZE = 52532
EMPTY_SHA1_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

_SUCCESS_KEYS = (
    "object_format",
    "commit_oid",
    "root_tree_oid",
    "object_records",
    "consumed_oids",
    "budget",
    "targets",
)
_RECORD_KEYS = (
    "oid",
    "object_type",
    "body_size_bytes",
    "body_sha256",
    "framed_sha256",
)
_BUDGET_KEYS = (
    "object_count",
    "declared_body_bytes",
    "actual_body_bytes",
    "parsed_tree_entries",
    "target_count",
    "walk_edges",
)
_TARGET_KEYS = ("path", "outcome", "reason", "walk", "stopped_at", "blob")
_EDGE_KEYS = ("tree_oid", "name_hex", "mode", "oid")
_STOPPED_KEYS = ("component_index", "tree_oid", "name_hex", "mode", "oid")
_BLOB_KEYS = ("oid", "body_size_bytes", "body_sha256", "framed_sha256")
_PUBLIC_CODES = {
    CODE_PROOF_INPUT_INVALID,
    CODE_PROOF_LIMIT_EXCEEDED,
    CODE_PROOF_OBJECT_EXTRA,
    CODE_PROOF_OBJECT_UNAVAILABLE,
    CODE_PROOF_OBJECT_SIZE_MISMATCH,
    CODE_PROOF_OBJECT_HASH_MISMATCH,
    CODE_PROOF_OBJECT_TYPE_MISMATCH,
    CODE_PROOF_COMMIT_INVALID,
    CODE_PROOF_TREE_INVALID,
    CODE_PROOF_CONSUMED_SET_MISMATCH,
}


def _load_fixture() -> dict:
    payload = FIXTURE_PATH.read_bytes()
    assert len(payload) == FIXTURE_SIZE
    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    return json.loads(payload.decode("utf-8"))


FIXTURE = _load_fixture()


def _limits(**overrides: int) -> dict[str, int]:
    values = dict(CODE_GIT_PROFILE_LIMITS)
    values.update(overrides)
    return values


def _records_and_bodies(fmt: dict, oids: list[str]) -> tuple[list[dict], dict[str, bytes]]:
    wanted = set(oids)
    records = []
    bodies: dict[str, bytes] = {}
    for item in fmt["all_objects"]:
        if item["oid"] not in wanted:
            continue
        records.append(
            {
                "oid": item["oid"],
                "object_type": item["type"],
                "body_size_bytes": item["size"],
                "body_sha256": item["body_sha256"],
                "framed_sha256": item["framed_sha256"],
            }
        )
        bodies[item["oid"]] = bytes.fromhex(item["body_hex"])
    records.sort(key=lambda rec: rec["oid"])
    return records, bodies


def _verify_case(fmt: dict, case_name: str) -> dict:
    case = fmt["cases"][case_name]
    records, bodies = _records_and_bodies(fmt, case["required_object_oids"])
    return verify_code_git_objects(
        object_format=fmt["object_format"],
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=copy.deepcopy(case["targets"]),
        limits=_limits(),
    )


def _assert_error(exc: CodeGitProofError, code: str, **details: object) -> None:
    assert isinstance(exc, CodeGitProofError)
    assert exc.code == code
    assert exc.exit_code == 2
    assert type(exc.details) is dict
    for key, value in details.items():
        assert exc.details[key] == value
    dumped = json.dumps(exc.details)
    assert "blob " not in dumped


def _tree_bytes(object_format: str, entries: list[tuple[str, bytes, str]]) -> bytes:
    raw_len = 20 if object_format == "sha1" else 32
    chunks = []
    for mode, name, oid in entries:
        raw = bytes.fromhex(oid)
        assert len(raw) == raw_len
        chunks.append(mode.encode("ascii") + b" " + name + b"\0" + raw)
    return b"".join(chunks)


def _commit_bytes(tree_oid: str, parents: tuple[str, ...] = (), extra: tuple[bytes, ...] = (), message: bytes = b"m\n") -> bytes:
    lines = [f"tree {tree_oid}".encode("ascii")]
    for parent in parents:
        lines.append(f"parent {parent}".encode("ascii"))
    lines.append(b"author A <a@example.invalid> 1 +0000")
    lines.append(b"committer C <c@example.invalid> 1 +0000")
    lines.extend(extra)
    return b"\n".join(lines) + b"\n\n" + message


def _record(object_format: str, object_type: str, body: bytes) -> tuple[dict, bytes]:
    oid, body_sha256, framed_sha256 = git_object_ids(object_format, object_type, body)
    return (
        {
            "oid": oid,
            "object_type": object_type,
            "body_size_bytes": len(body),
            "body_sha256": body_sha256,
            "framed_sha256": framed_sha256,
        },
        body,
    )


def _minimal_graph(object_format: str, tree_body: bytes = b"", targets: list[dict] | None = None, extra_objects: list[tuple[dict, bytes]] | None = None):
    tree_rec, tree_body = _record(object_format, "tree", tree_body)
    commit_body = _commit_bytes(tree_rec["oid"])
    commit_rec, commit_body = _record(object_format, "commit", commit_body)
    records = [commit_rec, tree_rec]
    bodies = {commit_rec["oid"]: commit_body, tree_rec["oid"]: tree_body}
    if extra_objects:
        for rec, body in extra_objects:
            records.append(rec)
            bodies[rec["oid"]] = body
    records.sort(key=lambda rec: rec["oid"])
    if targets is None:
        targets = [{"path": "missing.txt", "allow_executable_source": False}]
    return {
        "object_format": object_format,
        "commit_oid": commit_rec["oid"],
        "root_tree_oid": tree_rec["oid"],
        "objects": records,
        "bodies": bodies,
        "targets": targets,
        "limits": _limits(),
    }


def test_fixture_bytes_are_frozen() -> None:
    payload = FIXTURE_PATH.read_bytes()
    assert len(payload) == FIXTURE_SIZE
    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    assert FIXTURE["schema"] == "video-paper-wiki.code-git-objects-fixture.v1"


def test_profile_limits_are_immutable_mapping_proxy() -> None:
    assert type(CODE_GIT_PROFILE_LIMITS) is MappingProxyType
    assert list(CODE_GIT_PROFILE_LIMITS.items()) == [
        ("max_targets", 32),
        ("max_objects", 2048),
        ("max_tree_entries", 32768),
        ("max_object_bytes", 8388608),
        ("max_total_object_bytes", 33554432),
    ]
    with pytest.raises(TypeError):
        CODE_GIT_PROFILE_LIMITS["max_targets"] = 1  # type: ignore[index]
    copied = dict(CODE_GIT_PROFILE_LIMITS)
    copied["max_targets"] = 1
    assert CODE_GIT_PROFILE_LIMITS["max_targets"] == 32
    assert len(_PUBLIC_CODES) == 10


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_helpers_empty_blob_and_raw_versus_framed(object_format: str) -> None:
    gold = FIXTURE["formats"][object_format]["helper_goldens"]
    oid, body_sha256, framed_sha256 = git_object_ids(object_format, "blob", b"")
    assert oid == gold["empty_blob_oid"]
    assert body_sha256 == gold["empty_blob_body_sha256"]
    assert framed_sha256 == gold["empty_blob_framed_sha256"]
    assert frame_git_object("blob", b"") == b"blob 0\0"
    if object_format == "sha1":
        assert oid == EMPTY_SHA1_BLOB
        assert oid != framed_sha256
    else:
        assert oid == framed_sha256
    nonempty = b"abc"
    oid2, raw2, framed2 = git_object_ids(object_format, "blob", nonempty)
    assert raw2 != framed2
    if object_format == "sha256":
        assert oid2 == framed2
    assert frame_git_object("blob", nonempty) == b"blob 3\0abc"


def test_helper_validation_order_and_body_cap() -> None:
    with pytest.raises(CodeGitProofError) as exc:
        git_object_ids("SHA1", "blob", b"x")
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/object_format")
    with pytest.raises(CodeGitProofError) as exc:
        git_object_ids("sha1", "BLOB", b"x")
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/object_type")
    with pytest.raises(CodeGitProofError) as exc:
        git_object_ids("sha1", "blob", bytearray(b"x"))
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/body")
    with pytest.raises(CodeGitProofError) as exc:
        frame_git_object("tree", memoryview(b"x"))
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/body")
    huge = b"a" * 8388609
    with pytest.raises(CodeGitProofError) as exc:
        frame_git_object("blob", huge)
    _assert_error(
        exc.value,
        CODE_PROOF_LIMIT_EXCEEDED,
        instance_pointer="/body",
        limit_name="max_object_bytes",
        limit=8388608,
        observed=8388609,
    )
    with pytest.raises(CodeGitProofError) as exc:
        git_object_ids("sha1", "blob", huge)
    _assert_error(
        exc.value,
        CODE_PROOF_LIMIT_EXCEEDED,
        instance_pointer="/body",
        limit=8388608,
        observed=8388609,
    )


def test_blob_starting_with_frame_prefix_is_ordinary_body() -> None:
    body = b"blob 07\0abcdefg"
    oid, raw_h, framed_h = git_object_ids("sha1", "blob", body)
    assert oid != raw_h
    assert framed_h == hashlib.sha256(b"blob 15\0" + body).hexdigest()
    assert frame_git_object("blob", body).startswith(b"blob 15\0blob 07\0")


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
@pytest.mark.parametrize(
    "case_name",
    [
        "all_safe",
        "mixed_missing_unsafe",
        "exec_opt_in",
        "exec_refusal",
        "missing_nested",
        "non_directory_intermediate",
        "shared_subtree",
    ],
)
def test_fixture_cases(object_format: str, case_name: str) -> None:
    fmt = FIXTURE["formats"][object_format]
    result = _verify_case(fmt, case_name)
    expected = fmt["cases"][case_name]["expected"]
    assert list(result) == list(_SUCCESS_KEYS)
    assert result["object_format"] == object_format
    assert result["commit_oid"] == fmt["commit_oid"]
    assert result["root_tree_oid"] == fmt["root_tree_oid"]
    assert [item["path"] for item in result["targets"]] == [item["path"] for item in expected]
    for got, exp in zip(result["targets"], expected, strict=True):
        assert got["outcome"] == exp["outcome"]
        assert got["reason"] == exp["reason"]
        if got["outcome"] == "permitted_regular_blob":
            assert got["blob"] is not None
            assert list(got["blob"]) == list(_BLOB_KEYS)
        else:
            assert got["blob"] is None
    records, bodies = _records_and_bodies(fmt, fmt["cases"][case_name]["required_object_oids"])
    assert result["consumed_oids"] == sorted(rec["oid"] for rec in records)
    assert result["budget"]["object_count"] == len(records)
    assert result["budget"]["target_count"] == len(expected)
    assert result["budget"]["walk_edges"] == sum(len(item["walk"]) for item in result["targets"])
    assert result["budget"]["declared_body_bytes"] == sum(rec["body_size_bytes"] for rec in records)
    assert result["budget"]["actual_body_bytes"] == sum(len(bodies[rec["oid"]]) for rec in records)
    for rec in result["object_records"]:
        assert list(rec) == list(_RECORD_KEYS)
        assert not any(type(value) is bytes for value in rec.values())


def test_all_safe_shape_shared_blob_and_hidden_path() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    result = _verify_case(fmt, "all_safe")
    assert list(result["budget"]) == list(_BUDGET_KEYS)
    readme = next(item for item in result["targets"] if item["path"] == "README.md")
    copy_readme = next(item for item in result["targets"] if item["path"] == "README-copy.md")
    assert readme["blob"]["oid"] == copy_readme["blob"]["oid"]
    assert result["consumed_oids"].count(readme["blob"]["oid"]) == 1
    hidden = next(item for item in result["targets"] if item["path"] == ".github/source.yml")
    assert hidden["outcome"] == "permitted_regular_blob"
    assert hidden["walk"][0]["name_hex"] == b".github".hex()
    empty = next(item for item in result["targets"] if item["path"] == "empty-helper.py")
    assert empty["blob"]["oid"] == EMPTY_SHA1_BLOB
    helpers = next(item for item in result["targets"] if item["path"] == "helpers/empty.py")
    assert helpers["blob"]["oid"] == EMPTY_SHA1_BLOB
    foo = next(item for item in result["targets"] if item["path"] == "foo/dir")
    src = next(item for item in result["targets"] if item["path"] == "src/dir")
    assert foo["blob"]["oid"] == src["blob"]["oid"]
    assert foo["walk"][0]["oid"] == src["walk"][0]["oid"]
    for target in result["targets"]:
        assert list(target) == list(_TARGET_KEYS)
        for edge in target["walk"]:
            assert list(edge) == list(_EDGE_KEYS)
        assert list(target["stopped_at"]) == list(_STOPPED_KEYS)
        assert not any(type(value) is bytes for value in target.values())


def test_missing_component_keeps_name_hex_and_matched_walk() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    records, bodies = _records_and_bodies(
        fmt,
        [
            fmt["commit_oid"],
            fmt["root_tree_oid"],
            "7ed790ce84b21ea4449f99a909748cb1265b1649",
        ],
    )
    result = verify_code_git_objects(
        object_format="sha1",
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=[{"path": "src/no.py", "allow_executable_source": False}],
        limits=_limits(),
    )
    target = result["targets"][0]
    assert target["outcome"] == "missing"
    assert target["reason"] == "absent_entry"
    assert len(target["walk"]) == 1
    assert target["walk"][0]["name_hex"] == b"src".hex()
    assert target["walk"][0]["mode"] == "40000"
    stopped = target["stopped_at"]
    assert stopped["component_index"] == 1
    assert stopped["tree_oid"] == "7ed790ce84b21ea4449f99a909748cb1265b1649"
    assert stopped["name_hex"] == "6e6f2e7079"
    assert stopped["mode"] is None
    assert stopped["oid"] is None


def test_mixed_unsafe_outcomes_do_not_consume_child_objects() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    result = _verify_case(fmt, "mixed_missing_unsafe")
    by_path = {item["path"]: item for item in result["targets"]}
    assert by_path["foo"]["reason"] == "directory"
    assert by_path["link"]["reason"] == "symlink"
    assert by_path["script.sh"]["reason"] == "executable_without_permission"
    assert by_path["submodule"]["reason"] == "gitlink"
    assert by_path["missing.txt"]["stopped_at"]["name_hex"] == b"missing.txt".hex()
    assert "1111111111111111111111111111111111111111" not in result["consumed_oids"]
    assert fmt["path_facts"]["link"]["blob_oid"] not in result["consumed_oids"]
    assert fmt["path_facts"]["script.sh"]["blob_oid"] not in result["consumed_oids"]


def test_inputs_unchanged_outputs_unaliased_and_repeatable() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    case = fmt["cases"]["all_safe"]
    records, bodies = _records_and_bodies(fmt, case["required_object_oids"])
    targets = copy.deepcopy(case["targets"])
    limits = _limits()
    snap_records = copy.deepcopy(records)
    snap_bodies = dict(bodies)
    snap_targets = copy.deepcopy(targets)
    snap_limits = dict(limits)
    first = verify_code_git_objects(
        object_format="sha1",
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=targets,
        limits=limits,
    )
    second = verify_code_git_objects(
        object_format="sha1",
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=targets,
        limits=limits,
    )
    assert first == second
    assert records == snap_records
    assert bodies == snap_bodies
    assert targets == snap_targets
    assert limits == snap_limits
    first["object_records"][0]["oid"] = "0" * 40
    first["targets"][0]["path"] = "mutated"
    assert records == snap_records
    assert first["object_records"] is not records
    assert first["targets"] is not targets
    encoded = json.dumps(first)
    assert "\\u0000" not in encoded or True
    def _walk(value: object) -> None:
        assert type(value) is not bytes
        if type(value) is dict:
            for inner in value.values():
                _walk(inner)
        elif type(value) is list:
            for inner in value:
                _walk(inner)
    _walk(second)


def test_strict_bool_and_int_and_path_conflicts() -> None:
    args = _minimal_graph("sha1")
    args["limits"]["max_targets"] = True  # type: ignore[assignment]
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/limits/max_targets")
    args = _minimal_graph("sha1")
    args["objects"][0]["body_size_bytes"] = True  # type: ignore[assignment]
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID)
    args = _minimal_graph(
        "sha1",
        targets=[{"path": "A/x", "allow_executable_source": 1}],  # type: ignore[dict-item]
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID)
    args = _minimal_graph(
        "sha1",
        targets=[
            {"path": "A/x", "allow_executable_source": False},
            {"path": "a/y", "allow_executable_source": False},
        ],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, reason="casefold_conflict")
    args = _minimal_graph(
        "sha1",
        targets=[
            {"path": "src", "allow_executable_source": False},
            {"path": "src/a.py", "allow_executable_source": False},
        ],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, reason="ancestor_conflict")
    for bad in (".git", ".GIT", "..", ".", "/abs", "a//b", "a\\b", "a%b", "a*b"):
        args = _minimal_graph(
            "sha1",
            targets=[{"path": bad, "allow_executable_source": False}],
        )
        with pytest.raises(CodeGitProofError) as exc:
            verify_code_git_objects(**args)
        _assert_error(exc.value, CODE_PROOF_INPUT_INVALID)


def test_all_five_lowerable_limits() -> None:
    args = _minimal_graph(
        "sha1",
        targets=[
            {"path": "a", "allow_executable_source": False},
            {"path": "b", "allow_executable_source": False},
        ],
    )
    args["limits"]["max_targets"] = 1
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_targets", observed=2)

    blob_rec, blob_body = _record("sha1", "blob", b"x")
    args = _minimal_graph("sha1", extra_objects=[(blob_rec, blob_body)])
    args["limits"]["max_objects"] = 1
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_objects")

    blob_rec, blob_body = _record("sha1", "blob", b"x")
    tree_body = _tree_bytes(
        "sha1",
        [
            ("100644", b"a", blob_rec["oid"]),
            ("100644", b"b", blob_rec["oid"]),
        ],
    )
    args = _minimal_graph("sha1", tree_body=tree_body, extra_objects=[(blob_rec, blob_body)])
    args["limits"]["max_tree_entries"] = 1
    args["targets"] = [{"path": "a", "allow_executable_source": False}]
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_tree_entries", observed=2)

    args = _minimal_graph("sha1")
    args["objects"][0]["body_size_bytes"] = 8
    args["limits"]["max_object_bytes"] = 4
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_object_bytes")

    args = _minimal_graph("sha1")
    total = sum(rec["body_size_bytes"] for rec in args["objects"])
    args["limits"]["max_total_object_bytes"] = 1
    assert total > 1
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_total_object_bytes")


def test_declared_and_actual_caps_precede_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    hash_calls = {"n": 0}
    real_sha1 = hashlib.sha1
    real_sha256 = hashlib.sha256

    def wrapped_sha1(*args: object, **kwargs: object):
        hash_calls["n"] += 1
        return real_sha1(*args, **kwargs)

    def wrapped_sha256(*args: object, **kwargs: object):
        hash_calls["n"] += 1
        return real_sha256(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha1", wrapped_sha1)
    monkeypatch.setattr(hashlib, "sha256", wrapped_sha256)

    args = _minimal_graph("sha1")
    args["objects"][0]["body_size_bytes"] = 100
    args["limits"]["max_object_bytes"] = 10
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_object_bytes")
    assert hash_calls["n"] == 0

    args = _minimal_graph("sha1")
    oid = args["objects"][0]["oid"]
    args["bodies"][oid] = args["bodies"][oid] + b"extra-bytes"
    args["limits"]["max_object_bytes"] = max(1, args["objects"][0]["body_size_bytes"])
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_object_bytes")
    assert hash_calls["n"] == 0


def test_size_and_hash_mismatch_and_body_key_set() -> None:
    args = _minimal_graph("sha1")
    oid = args["objects"][0]["oid"]
    args["objects"][0]["body_size_bytes"] = args["objects"][0]["body_size_bytes"] + 1
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_SIZE_MISMATCH, oid=oid)

    args = _minimal_graph("sha1")
    args["objects"][0]["oid"] = "a" * 40
    args["objects"].sort(key=lambda rec: rec["oid"])
    args["bodies"]["a" * 40] = args["bodies"].pop(oid)
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_HASH_MISMATCH, field="oid")

    args = _minimal_graph("sha1")
    args["objects"][0]["body_sha256"] = "b" * 64
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_HASH_MISMATCH, field="body_sha256")

    args = _minimal_graph("sha1")
    args["objects"][0]["framed_sha256"] = "c" * 64
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_HASH_MISMATCH, field="framed_sha256")

    args = _minimal_graph("sha1")
    extra = "d" * 40
    args["bodies"][extra] = b"x"
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_EXTRA, extra_oids=[extra])

    args = _minimal_graph("sha1")
    missing = args["objects"][0]["oid"]
    del args["bodies"][missing]
    args["bodies"][extra] = b"x"
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_EXTRA, extra_oids=[extra])

    args = _minimal_graph("sha1")
    del args["bodies"][args["objects"][0]["oid"]]
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_UNAVAILABLE)


def test_type_mismatch_omitted_object_and_unused_set() -> None:
    blob_rec, blob_body = _record("sha1", "blob", b"hello\n")
    tree_body = _tree_bytes("sha1", [("40000", b"src", blob_rec["oid"])])
    args = _minimal_graph(
        "sha1",
        tree_body=tree_body,
        extra_objects=[(blob_rec, blob_body)],
        targets=[{"path": "src/x", "allow_executable_source": False}],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_OBJECT_TYPE_MISMATCH,
        oid=blob_rec["oid"],
        expected_type="tree",
        actual_type="blob",
    )

    args = _minimal_graph(
        "sha1",
        tree_body=_tree_bytes("sha1", [("100644", b"file.py", blob_rec["oid"])]),
        targets=[{"path": "file.py", "allow_executable_source": False}],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_UNAVAILABLE, missing_oids=[blob_rec["oid"]])

    unused_tree, unused_body = _record("sha1", "tree", b"")
    args = _minimal_graph("sha1", extra_objects=[(unused_tree, unused_body)])
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_CONSUMED_SET_MISMATCH,
        unused_oids=[unused_tree["oid"]],
    )


def test_commit_grammar_and_limits() -> None:
    tree_rec, tree_body = _record("sha1", "tree", b"")
    good = _commit_bytes(
        tree_rec["oid"],
        parents=("a" * 40, "b" * 40),
        extra=(
            b"gpgsig -----BEGIN PGP SIGNATURE-----",
            b" synthetic",
            b" -----END PGP SIGNATURE-----",
        ),
    )
    commit_rec, commit_body = _record("sha1", "commit", good)
    result = verify_code_git_objects(
        object_format="sha1",
        commit_oid=commit_rec["oid"],
        root_tree_oid=tree_rec["oid"],
        objects=sorted([commit_rec, tree_rec], key=lambda rec: rec["oid"]),
        bodies={commit_rec["oid"]: commit_body, tree_rec["oid"]: tree_body},
        targets=[{"path": "x", "allow_executable_source": False}],
        limits=_limits(),
    )
    assert result["targets"][0]["outcome"] == "missing"

    def _commit_error(body: bytes, root: str | None = None) -> CodeGitProofError:
        rec, owned = _record("sha1", "commit", body)
        tree_oid = root if root is not None else tree_rec["oid"]
        if root is None:
            objects = sorted([rec, tree_rec], key=lambda item: item["oid"])
            bodies = {rec["oid"]: owned, tree_rec["oid"]: tree_body}
        else:
            objects = [rec]
            bodies = {rec["oid"]: owned}
        with pytest.raises(CodeGitProofError) as exc:
            verify_code_git_objects(
                object_format="sha1",
                commit_oid=rec["oid"],
                root_tree_oid=tree_oid,
                objects=objects,
                bodies=bodies,
                targets=[{"path": "x", "allow_executable_source": False}],
                limits=_limits(),
            )
        return exc.value

    mismatch = _commit_bytes("c" * 40)
    err = _commit_error(mismatch)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="root_tree_mismatch")

    duplicate_tree = b"tree " + tree_rec["oid"].encode() + b"\ntree " + tree_rec["oid"].encode() + b"\n\n"
    err = _commit_error(duplicate_tree)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="duplicate_tree_header")

    bad_parent = b"tree " + tree_rec["oid"].encode() + b"\nparent not-an-oid\n\n"
    err = _commit_error(bad_parent)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="invalid_parent_header")

    cr = b"tree " + tree_rec["oid"].encode() + b"\r\n\n"
    err = _commit_error(cr)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="header_contains_cr")

    nul = b"tree " + tree_rec["oid"].encode() + b"\0\n\n"
    err = _commit_error(nul)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="header_contains_nul")

    err = _commit_error(b"tree " + tree_rec["oid"].encode() + b"\n")
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="missing_header_terminator")

    tab = b"tree " + tree_rec["oid"].encode() + b"\n\tcontinued\n\n"
    err = _commit_error(tab)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="tab_prefixed_header")

    cont_tree = b"tree " + tree_rec["oid"].encode() + b"\n continued\n\n"
    err = _commit_error(cont_tree)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="invalid_continuation")

    huge = b"tree " + tree_rec["oid"].encode() + b"\n" + (b"x" * 65536) + b"\n\n"
    err = _commit_error(huge)
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="header_too_large")

    many = [f"tree {tree_rec['oid']}".encode()]
    many.extend([b"note " + str(i).encode() for i in range(1024)])
    err = _commit_error(b"\n".join(many) + b"\n\n")
    _assert_error(err, CODE_PROOF_COMMIT_INVALID, reason="too_many_header_lines")


def test_tree_syntax_order_modes_and_opaque_names() -> None:
    blob_rec, blob_body = _record("sha1", "blob", b"n")
    fmt = FIXTURE["formats"]["sha1"]
    result = _verify_case(fmt, "all_safe")
    root_entries = None
    # Parsing succeeded, including foo.bar / foo / foo0 and non-UTF-8 sibling.
    assert result["budget"]["parsed_tree_entries"] > 0
    assert fmt["tree_entry_order_checks"]["non_utf8_sibling_name_hex"] == "ff73696465636172"

    def _tree_error(entries: list[tuple[str, bytes, str]]) -> CodeGitProofError:
        body = _tree_bytes("sha1", entries)
        args = _minimal_graph("sha1", tree_body=body)
        with pytest.raises(CodeGitProofError) as exc:
            verify_code_git_objects(**args)
        return exc.value

    err = _tree_error([("100664", b"file", blob_rec["oid"])])
    _assert_error(err, CODE_PROOF_TREE_INVALID, reason="invalid_mode", byte_offset=0)

    err = _tree_error(
        [
            ("100644", b"foo0", blob_rec["oid"]),
            ("100644", b"foo.bar", blob_rec["oid"]),
        ]
    )
    _assert_error(err, CODE_PROOF_TREE_INVALID, reason="invalid_order")

    err = _tree_error(
        [
            ("100644", b"aa", blob_rec["oid"]),
            ("100644", b"aa", "1" * 40),
        ]
    )
    _assert_error(err, CODE_PROOF_TREE_INVALID, reason="duplicate_name")

    truncated = b"100644 file"
    rec, _ = _record("sha1", "tree", truncated)
    commit_body = _commit_bytes(rec["oid"])
    commit_rec, commit_body = _record("sha1", "commit", commit_body)
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(
            object_format="sha1",
            commit_oid=commit_rec["oid"],
            root_tree_oid=rec["oid"],
            objects=sorted([commit_rec, rec], key=lambda item: item["oid"]),
            bodies={commit_rec["oid"]: commit_body, rec["oid"]: truncated},
            targets=[{"path": "file", "allow_executable_source": False}],
            limits=_limits(),
        )
    _assert_error(exc.value, CODE_PROOF_TREE_INVALID, reason="truncated_name")

    bad_name = _tree_bytes("sha1", [("100644", b".", blob_rec["oid"])])
    args = _minimal_graph("sha1", tree_body=bad_name)
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_TREE_INVALID, reason="invalid_name")

    opaque = _tree_bytes(
        "sha1",
        [
            ("100644", b"ascii", blob_rec["oid"]),
            ("100644", b"\xffsidecar", blob_rec["oid"]),
        ],
    )
    args = _minimal_graph(
        "sha1",
        tree_body=opaque,
        extra_objects=[(blob_rec, blob_body)],
        targets=[{"path": "ascii", "allow_executable_source": False}],
    )
    result = verify_code_git_objects(**args)
    assert result["targets"][0]["outcome"] == "permitted_regular_blob"


def test_second_commit_and_uppercase_oid_rejected() -> None:
    args = _minimal_graph("sha1")
    parent, parent_body = _record("sha1", "commit", _commit_bytes(args["root_tree_oid"], message=b"p\n"))
    args["objects"].append(parent)
    args["objects"].sort(key=lambda rec: rec["oid"])
    args["bodies"][parent["oid"]] = parent_body
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID)

    args = _minimal_graph("sha1")
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(
            object_format="sha1",
            commit_oid=args["commit_oid"].upper(),
            root_tree_oid=args["root_tree_oid"],
            objects=args["objects"],
            bodies=args["bodies"],
            targets=args["targets"],
            limits=args["limits"],
        )
    _assert_error(exc.value, CODE_PROOF_INPUT_INVALID, instance_pointer="/commit_oid")


def _guard_side_effects(monkeypatch: pytest.MonkeyPatch):
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("kernel invoked a forbidden side effect")

    real_import = builtins.__import__
    forbidden = {
        "os",
        "sys",
        "io",
        "pathlib",
        "subprocess",
        "socket",
        "ssl",
        "urllib",
        "http",
        "shutil",
        "tempfile",
        "mmap",
        "json",
        "pkgutil",
        "importlib",
        "posixpath",
        "ntpath",
    }

    def guarded_import(name: str, *args: object, **kwargs: object):
        root = name.split(".", 1)[0]
        if root in forbidden or name.startswith("video_paper_wiki."):
            raise AssertionError(f"kernel imported {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(builtins, "open", boom)
    monkeypatch.setattr(os, "open", boom, raising=False)
    monkeypatch.setattr(os, "stat", boom, raising=False)
    monkeypatch.setattr(socket, "socket", boom, raising=False)
    monkeypatch.setattr(subprocess, "Popen", boom, raising=False)
    monkeypatch.setattr(subprocess, "run", boom, raising=False)


def test_kernel_has_no_io_imports() -> None:
    import video_paper_wiki.code_git_objects as module

    forbidden = {
        "os",
        "sys",
        "io",
        "pathlib",
        "subprocess",
        "socket",
        "json",
        "urllib",
        "resources",
    }
    for name, value in vars(module).items():
        if getattr(value, "__name__", None) in forbidden:
            raise AssertionError(name)


def test_kernel_call_does_not_use_io_or_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _guard_side_effects(monkeypatch)
    fmt = FIXTURE["formats"]["sha1"]
    _verify_case(fmt, "exec_opt_in")
    args = _minimal_graph("sha1")
    args["objects"][0]["body_sha256"] = "e" * 64
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_HASH_MISMATCH)


def test_unused_trees_are_still_syntax_checked() -> None:
    blob_rec, blob_body = _record("sha1", "blob", b"ok\n")
    good_tree = _tree_bytes("sha1", [("100644", b"ok.py", blob_rec["oid"])])
    bad_tree_body = b"not-a-tree"
    bad_tree, bad_body = _record("sha1", "tree", bad_tree_body)
    args = _minimal_graph(
        "sha1",
        tree_body=good_tree,
        extra_objects=[(blob_rec, blob_body), (bad_tree, bad_body)],
        targets=[{"path": "ok.py", "allow_executable_source": False}],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_TREE_INVALID)

--- END EXACT SOURCE ---

Return the actual bounded repair patch now. No tools and no prose.
