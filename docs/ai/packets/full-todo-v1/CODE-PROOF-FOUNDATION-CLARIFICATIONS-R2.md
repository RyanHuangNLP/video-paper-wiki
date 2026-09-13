# CODE foundation review clarifications — R2 preparation

This additive disposition closes the bounded R1 foundation review findings.
R1 contract/instruction and the review remain unchanged. No implementation is
dispatched and no resource candidate is accepted by this document. The later
exact freeze binds R1, this supplement and the corrected self-contained prompt.

## Named private test surfaces

The production module defines these internal helpers and uses them in its real
compiler. Tests may invoke them directly on synthetic mutated values, without
changing production pins or installing untrusted resources:

- `_parse_resource_bytes(data: bytes) -> dict`: exact bytes to an exact builtin
  root object, applying R1's strict resource parser and formatting policy.
- `_validate_schema_references(schemas: dict[str, dict]) -> None`: exact declared
  ten-ID map to reference-closure success, applying R1's forbidden keyword,
  exact-ID and resolved JSON Pointer rules. It does not retrieve resources.
- `_validate_profile_inventory(profile: dict) -> None`: check exact profile
  object, inventory rows, strict builtin values, hard limits and admission caps
  against the production constants. Schema validation still occurs separately
  within compilation, against the same actual compiled registry.

All three helpers use CodeProofResourceError/resource_shape on invalid input,
without raw diagnostic content. These private pure hooks grant no alternative
resource trust: compile_code_proof_resources always verifies all eleven byte
pins first and accepts no caller registry, pin or test-mode argument.

Profile schema validation uses a validator schema whose `$ref` is the exact
common schema ID followed by `#/$defs/profile`, with the current ten-resource
registry. This keeps internal refs such as `#/$defs/profile_limits` anchored in
the complete common document. A detached profile definition is not sufficient.

The 264 fixture rows cover nine wire titles. Add a separate common-title probe:
the accepted definitions-only common root admits an empty object structurally.
This does not make any common-root input accepted public evidence. The probe
must use `validate_structure` with the exact common title and assert None.

Private resource error messages are exactly `CODE proof resource: <reason>`;
private structure error messages are exactly `CODE proof structure: <reason>`.
Only an already validated member of the respective closed reason enum may be
inserted. Invalid constructor reasons raise ValueError with the fixed message
`Invalid CODE proof error reason`, without formatting the invalid object.
Raise boundary errors with raw exception chaining suppressed. Tests assert the
literal safe message and marker absence, in addition to the fixed reason.

## Installed-wheel acceptance is an external harness

Builder-owned unit tests exercise lexical source/installed origin selection,
pure compilation and structural behavior; they do not need a wheel path or
build/install subprocess. Actual installed-package parity is a separately
required Architect/Steward acceptance check after the two-file candidate stops.
It is never inferred from mocked origins or a repository pytest invocation.

Use a fresh private source copy of the exact accepted baseline plus the two
candidate files. Copy tracked package inputs and frozen candidate files only;
do not bring along source `__pycache__`, caches or arbitrary untracked files.
Build one actual Hatch wheel offline using the existing uv executable and an
explicit healthy locked Python. Install that wheel with uv offline/no-deps into
two fresh target directories, one for each locked Python 3.12 and 3.13 probe.
Existing locked dependencies remain available to those interpreters; do not
download dependencies, runtimes, models or extras.

Each probe runs its locked interpreter with `-I -B` in a separate empty cwd.
Its script inserts only the fresh installation target into sys.path. Check the
imported package and foundation module __file__ origins are inside that target,
and assert no original checkout/source/build-copy src path appears in sys.path.
The target must not be literally named src. Use actual installed resource files
to supply the eleven-byte mapping, compile the new context and assert its actual
origin plan is installed with package schemas/profiles directories. Read the
same pinned fixture as an explicit data input (not an import search path), replay
all 264 cases plus the common-root probe and validate full/lowered limits.
Instrument production methods after fixture/resource reads to demonstrate their
own zero-I/O boundary independently of the harness's necessary reads.

Record the actual build/install/probe argv, exit codes, interpreter/module
origins, candidate snapshot, wheel bytes/RECORD, all 81 schema byte comparisons,
the profile pin and module byte parity. Preserve the earlier resource wheel
record as a different candidate's evidence. This future check cannot be marked
passed until the actual two-file candidate exists and those commands complete.
