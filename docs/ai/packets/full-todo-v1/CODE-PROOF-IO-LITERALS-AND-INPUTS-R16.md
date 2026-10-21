# Retained I/O literals and private input admission — R16 preparation

This Architect preparation closes the concrete remaining R15 literal and input
API choices. It requires independent review with the complete self-contained
I/O instruction before dispatch. It does not change the foundation candidate,
authorize a Builder or reopen the accepted pure kernels/resources. The original
R15 review is preserved at its actual nested path
`artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/foundation-r1/F/io-api-seam-review-r15.json`.

## Exact I/O facade messages

The new CodeProofIOError factory selects its message solely from this table.
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
code. Read-only properties expose copied data as R15 specifies.

## Ordinary metadata admission

The private retain_input maximum argument is an exact builtin int equal to
65536 or 1048576. They select the fixed max_request_input_bytes or
max_observe_input_bytes admission policy respectively. Reject any other value,
including bool and int subclasses, with the existing private
CodeProofStructureError("limits") and suppressed context. This does not add a
caller-selectable resource/file policy or permit lowered admission via the
output setter. The public workflow selects the constant matching its command.
Both limits use instance_pointer=/input. An actual retained byte count above
that selected fixed maximum uses the R9 limit context and corresponding
admission key, before decoding. No new public command or input field is added.

## Raw bundle first acquisition

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

## Bounded I/O pointers and prior metadata

For a per-file limit reached by install, use /request, /intent, /bundle,
/observation for the corresponding direct files; use /config or /handoffs for
the two derived families. For an initial output scan or retrospective setter
refusal without a parsed semantic plan, use /output rather than deriving an
instance pointer from an arbitrary filename or inferring a handoff plan index.
The later public preflight still uses R9's exact /handoffs/<index> for its known
path-ordered prospective plan. Peak limits always use /output.

Raw manifest byte limits use /bundle with max_bundle_bytes. Raw object count or
aggregate limits use /objects. With the validated ordered inventory, a per-body
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
Prior operation and errno use only R8's operation enum and 0..65535 bound.
Preserving a prior code does not adopt or verify the original semantic result.
The same final group/cleanup precedence applies to known, unexpected and
interruption exceptions. No exception becomes a successful result.
