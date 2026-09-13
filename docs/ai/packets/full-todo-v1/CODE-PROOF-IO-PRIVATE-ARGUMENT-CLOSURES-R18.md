# Retained I/O private argument and raw-count closure — R18

Architect disposition of the two bounded complete-instruction R1 findings.
Earlier contracts and reviews remain unchanged. These rules are integrated into
the complete R2 instruction; this document alone does not dispatch a Builder.

## Raw-count stage and ordering

Before manifest/inventory validation, the initial physical raw-object count and
raw aggregate admission use hard max_objects/max_total_object_bytes contexts at
/objects. After validation, retained physical body-map count uses /bodies with
the selected max_objects. Declared inventory count remains /objects. Enforce the
selected physical count before width, extra or missing reconciliation, in this
exact order: count-cap, width, extra, missing; all precede body open/read. Retain
the existing per-body and aggregate pointer rules. Count/byte admission failures
remain separate from changed retained lineage and stable inventory disagreements.

## Private argument types and failure order

Every session method first requires active lifetime. Install additionally refuses
an in-flight or previously failed install with WORK_PATH_UNSAFE in installation,
reason phase_mismatch, preserving its last actual phase; do not continue writing.
Then enforce the already frozen successful-setter prerequisite before inspecting
install arguments. These state checks do not evaluate caller values.

For retain_input, check path is exact builtin str, then check maximum is exact
builtin int 65536 or 1048576, then check the existing lexical path spelling before
Path construction or any traversal. The maximum rule keeps its existing private
CodeProofStructureError("limits") refusal. Wrong path type is the existing
CodeProofStructureError("type"). Do not call __fspath__, str or another converter.

For install, after the state/setter checks, check relative_name is exact builtin
str, then payload is exact builtin bytes, before conversion, hashing, comparison,
len, slicing or filesystem access. Wrong type raises the existing private
CodeProofStructureError("type"). Then validate the exact fixed output layout
name: one direct known filename or exactly one known family plus its frozen
basename. All other spellings use WORK_PATH_UNSAFE/path_spelling in installation.
For retain_input lexical refusal use WORK_PATH_UNSAFE/path_spelling in metadata.
Neither context includes the original input or filename. Reject subclasses and
path-like/byte-convertible objects without invoking any of their methods.

After those checks, a valid bytes payload exceeding the known target's selected
per-file cap uses CODE_PROOF_LIMIT_EXCEEDED with the fixed install pointer and
actual corresponding limit_name/limit/observed byte count. The C+2*N peak rule
still applies independently before any temporary or ancestor creation. Do not
classify an oversized valid byte payload as a malformed type or shape.

All new direct private and facade raises suppress unrelated exception context.
These refusals unwind through the same graph finalizer; higher-priority retained
lineage or cleanup failure may override them. An unchanged private exception is
otherwise preserved. No new exception class, public field or I/O code is added.

Tests discriminate simultaneous state/type/name/size failures in the stated
order, hostile path/str/bytes subclasses and conversion/length/hash hooks,
pre-manifest versus post-manifest count pointers, and count-cap before width,
extra and missing. Assert no body opens or output creation on these refusals.
