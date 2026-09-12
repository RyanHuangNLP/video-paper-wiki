# Retained I/O API seams — R15 preparation

Architect disposition of the bounded R15 advisory. This supplements R6/R8/R9,
R13/R14 and the accepted resource contract; it does not dispatch I/O work or
change the active foundation correction. The eventual I/O freeze must bind
these decisions, their independent review and the accepted foundation revision.
The advisory is preserved at
`artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/foundation-r1/F/io-api-seam-advisory-r15.json`.

## Read/write temporary descriptor

Add exact builtin integer `os.O_RDWR` to R14's per-session capability checks.
It must be nonzero and is an access-mode choice, not an additional protection
flag to combine with `O_WRONLY`. Retain the other R14 requirements unchanged.
Open each owned temporary with `O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW |
O_CLOEXEC`, the retained parent `dir_fd` and mode 0600. Use that one returned
descriptor for writes, seek/read verification, fstat and cleanup. Read-only
resources and ordinary/raw inputs still use `O_RDONLY` and their existing
protection flags. No second open or path-based readback substitutes for the
temporary descriptor. Missing support is `unavailable_primitive` before output
creation, subject to the existing final-lineage precedence.

## Exact limit projections

The foundation and public workflow retain the complete independent nested
`{git, config, public}` map. The I/O setter does not reinterpret that map or
select a different profile. Freeze `set_output_limits(limits)` as an exact
builtin flat dict containing these seven output-related public keys:

| Key | Retained or planned bytes governed |
| --- | --- |
| max_request_bytes | request.json |
| max_intent_bytes | intent.json |
| max_bundle_bytes | retained raw manifest and its identical bundle.json copy |
| max_observation_bytes | observation.json |
| max_config_document_bytes | each configs JSON record |
| max_handoff_bytes | each handoffs JSON record |
| max_output_peak_bytes | complete output logical bytes and each C + 2*N peak |

Require every key to be exact str before set comparison or lookup; every value
must be an exact positive int within its pinned hard maximum. Copy the map.
It can be set once per session, before the first install, including the case
where the selected values equal the hard maxima. A second call is private API
misuse and raises `RuntimeError("CODE output limits are already set")`; an
install before a successful setter call raises
`RuntimeError("CODE output limits are not set")`. Both unwind through the normal
finalizer. Existing data is checked against the selected limits before the
setter succeeds; no retroactive successful view or installation can ignore an
already retained over-limit file or manifest. The hard limits remain the setup
and scan caps until this one narrowing. Limit refusal retains the existing
R9 limit context; no new wire reason or error code is introduced.
Malformed setter maps or values use the existing private
`CodeProofStructureError("limits")`. The R9 limit context applies when a valid
selected map refuses actual retained or planned byte counts. The later public
workflow already validates its complete request limits before projecting them.

`max_inline_normalized_bytes` remains a public semantic per-target check during
observe preflight. It is deliberately not an output-file policy. Fixed ordinary
request/observe admission caps remain separate and cannot be lowered through
the setter. Config's thirteen values still reach the pure configuration parser.

Pass the complete exact five-key `materialized["git"]` map separately to
`retain_bundle_bodies` and the accepted Git kernel. The body reader enforces
lowered `max_objects`, `max_object_bytes` and `max_total_object_bytes` against the
declared inventory and actual reads; the kernel continues to enforce all five
values with its unchanged error contexts. Initial output scanning uses the hard
layout/body caps because it precedes saved-request parsing. Public saved-state
validation must then replay its retained object set under the saved request's
complete lowered Git limits, including per-object and aggregate bytes, before
any successful status or other command result. The setter's output projection
does not remove that requirement. No old object body may evade a lowered Git
limit merely because it was read before request parsing.

The workflow can perform the one setter call after it knows the validated full
request limits; this need not wait for the last pure derivation. The stronger
R9 requirement still holds: all semantic/serialization checks and the complete
prospective installation sequence pass before the first new install. If a raw
manifest is retained before narrowing, the setter rechecks its retained size;
if retained after narrowing, its bounded reader uses the selected bundle cap.

## Private error facade

Define `CodeProofIOError` in `code_proof_io.py`, with read-only `code`, `message`,
`details` and `exit_code` properties. `exit_code` is always 2. `details` returns
a fresh plain JSON-data copy so a caller cannot mutate the selected final
failure. The graph never constructs or emits the CLI's outer JSON envelope.

The internal error factory accepts only the frozen I/O/busy/resource/workspace
codes and R9 limit/conflict codes. Its message is selected from fixed literal
code-to-message constants; caller paths, arbitrary keys/values and raw exception
messages cannot enter it. The eventual implementation instruction freezes those
literals. Validate and retain the appropriate closed details shape:

- I/O, busy, resource, invalid batch/root and unsafe path errors use all nine
  R8 fields with R9's extended reasons and bounded errno values.
- Limit errors use exactly `instance_pointer`, `limit_name`, `limit`, `observed`.
- Stable initial conflicts use exactly `instance_pointer`, `reason`.

R8's installer phase enum includes `idle`; keep it alongside the other setup,
scan, retaining, installer, final_verify and closing phases. The advisory's
enumerated phase list omitted idle and is not the authoritative closed enum.
No reason, operation, group or other enum is widened by this supplement.

Foundation resource errors are mapped by the owning retained session into the
full resource-invalid context before final selection. Structure errors remain
private until the later public validator supplies its known field pointer and
semantic context. Preserve original Git/config/public semantic exceptions and
their details when final verification and cleanup do not override them. Prior
metadata in an overriding I/O error uses only a recognized frozen code and
bounded operation/errno; unrecognized exception metadata supplies null fields,
never stringified diagnostics. Unexpected exceptions and interruptions still
unwind through all retained checks and cleanup and cannot become success.

At the future command boundary, pass the final error's code, fixed message,
copied details and exit code to the existing `envelope.emit_error` interface.
Do not change the outer envelope, legacy staging behavior or either pure kernel
to accommodate this new private facade.

## Acceptance additions

Inject missing O_RDWR before setup and prove no output creation. Verify the
actual temporary descriptor is used for both short writes and exact readback.
Exercise all seven setter fields, exact key/value types, an already retained
over-limit manifest/file, a second setter call, install-before-set and current
logical bytes at the selected peak boundary. Separately lower all three Git
inventory/byte caps for incoming and initially retained bodies; successful
public saved-state replay must enforce the same request limits.

Verify each facade detail shape, read-only properties and independent detail
copies. Check idle-phase representation, bounded prior metadata, safe messages,
unchanged kernel propagation and final-lineage/cleanup precedence. These are
future implementation checks, not results claimed by this preparation.
