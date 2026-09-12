# Retained I/O dispatch closures — R17 preparation

Architect disposition of the complete instruction's first independent review.
R6/R8/R9/R13–R16 and the original review remain preserved. This closes the five
concrete findings for the next complete instruction review; it is not a freeze
or Builder dispatch. The accepted foundation source and pure kernels do not
change. The standalone final instruction must contain these decisions directly.

## Foundation exception property

Both foundation exception classes expose the read-only property `reason`.
CodeProofResourceError.reason is resource_origin/resource_hash/resource_shape;
CodeProofStructureError.reason is type/shape/limits. These words are values,
not additional attributes. The I/O adapter reads only `.reason`; it does not
access or invent `.type`, `.shape` or `.limits` properties or change the original
private classes or messages.

## Exact raw bundle path admission

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

## Stable raw inventory reconciliation and narrow Git error adapter

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

The review described extra/missing/width as kernel order, but the actual kernel
checks key width inside its initial loop before either set-difference refusal.
This disposition corrects that ordering without changing the preserved review.
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
/objects; both use max_objects. This specializes R16's general raw count pointer
without introducing an untrusted pointer or changing the context schema.

Tests must discriminate opposite-width+extra, extra+missing, stable missing,
invalid-layout-name, and post-capture set replacement cases. Assert zero body
opens on stable reconciliation refusals, exact existing Git class/messages/
details, and the ordinary final-lineage override after any semantic refusal.

## Saved original exception and final selection

Before finalizer actions, save the actual original BaseException object, if any,
and retain the install record's last phase and observed successful-link/cleaned
prefix flags. Do not construct a generic substitute for a kernel, config,
public, unexpected or interruption exception.

Attempt every reached final-verification group and the applicable checked
owned-temp and descriptor cleanup. Keep all reached observations and any
lineage failures through these actions. Final selection is explicitly:

1. If any persistent lineage check failed or was uncheckable, select the first
   failed group in the fixed R8 order as WORK_PATH_UNSAFE.
2. Otherwise, if cleanup failed, select the bounded cleanup error.
3. Otherwise, if an original exception was saved, propagate that same original
   object unchanged, including its class, code/message/details when present and
   KeyboardInterrupt/SystemExit identity.
4. Otherwise complete the context-manager exit successfully.

Do not enter idle after a failed installation. Enter idle only after a durable
successful completion. Post-effect observations may preserve an authorized
cleaned prefix or a successful-link flag, but never turn the syscall exception
into success. No snapshot/layout success is returned during an in-flight phase.
Existing R8 all-groups checking, last name/set sweep, checked temp ownership,
reverse closes with lock duplicate last and no retry of failed closes remain
required. Finalizer failures do not skip later reached groups or descriptor
cleanup. If a higher-priority failure is selected, use only bounded prior fields;
never add arbitrary original messages or exception objects to its detail map.

When propagating an unchanged original exception, preserve its existing cause
and context behavior rather than mutating that accepted exception object. New
I/O facade, adapter and private helper raises suppress unrelated raw context as
their own boundary requires. This keeps the existing kernel behavior unchanged.
