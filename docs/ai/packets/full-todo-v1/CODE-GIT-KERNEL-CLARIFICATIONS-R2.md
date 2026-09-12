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
