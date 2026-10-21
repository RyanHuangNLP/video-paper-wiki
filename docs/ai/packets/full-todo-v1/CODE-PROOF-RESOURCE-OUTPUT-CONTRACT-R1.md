# CODE resource output contract — R1 draft

This selects the output mechanism for the reviewed resource-generation plan.
It is not a launch instruction or resource acceptance. Exact CONFIG acceptance,
typed fixture preparation, a final input manifest, runtime review and a separate
Architect handoff remain prerequisites. Preserve the plan and R12 unchanged.

## Builder outputs

Grok Build authors two complete Python files in its response, without executing
them or changing the checkout:

1. `generate_code_proof_resources.py`, retained as an evidence artifact;
2. `tests/contract/test_code_proof_resources.py`, the new product test module.

Use an explicit BEGIN_FILE / END_FILE block for each file and one complete
Python code fence inside each block. Do not abbreviate definitions, omit repeated
branches, return a patch for a nonexistent file, or claim tests were run. End
with a brief naming both outputs and any unresolved contract question.

The generator accepts exactly `--output-dir PATH`. The specified directory must
be absent before execution. It creates that directory and only the eleven
resource files in R12, under their exact checkout-relative subpaths. Parent
directories for those eleven files are its only other created entries. It must
refuse an existing output directory or file, including an existing symlink,
without replacing it. The coordinator supplies an absent child of a fresh local
temporary directory. This is an offline artifact-generation operation; it does
not implement the future public retained-I/O session.

The generator contains its full resource definitions. Allowed imports are Python
stdlib modules needed for argument parsing, JSON serialization, SHA-256 and
bounded path creation. It must not import the project or its kernels, read
repository files, discover resources, invoke subprocess/Git/network, evaluate
strings as code, use dynamic imports, or modify permissions, environment,
credentials or application settings. It writes no tests, fixtures, manifest,
logs or hidden extra outputs. Resource inventory is a fixed literal tuple.

Generate all ten schemas first. Serialize every resource using UTF-8,
`json.dumps(..., indent=2, ensure_ascii=False, allow_nan=False)` plus one LF,
with integer-valued schema/profile numbers. Compute each schema's exact size
and SHA-256 from those serialized bytes, build the ASCII-filename-sorted profile
inventory, and then serialize the profile. No schema includes a profile hash;
neither a schema nor the common profile definition embeds its own byte hash.

The coordinator inspects and freezes both complete returned files, obtains an
independent generator review, then executes the generator locally against the
fresh output directory. Generator execution does not itself accept its schemas.
All eleven generated resource files must pass independent structural and byte
checks before mechanical installation in the CODE worktree.

## Test transport and ownership

The independently prepared fixture bundle is the plan's closed object
`{schema, profile_sha256, cases}`. Each case has only `{name, title, instance}`;
names are unique ASCII strings and rows sort by name. Instances cover the nine
actual instance schema titles. The common schema has no independent public
document shape: validate the actual profile separately through `$defs/profile`.

The resource test module loads the installed profile from the imported package's
`profiles` directory and source schemas from the checkout associated with that
same imported source package. It does not discover CODE resources by iterating
over unrelated schemas or use the legacy global schema registry. It names all
ten filenames explicitly, builds a fresh `referencing.Registry`, and refuses
undeclared retrieval. Wheel byte parity is also checked independently after
the complete product snapshot is frozen; no nonexistent public resource loader
or public command is assumed by this test increment.

The fixture generator and bundle packer remain separately reviewed preparation
artifacts. They may use the exact accepted pure kernels and JCS helper to
produce evidence, but do not author or alter the resource definitions. Rebuild
all profile-dependent saved documents and references with the generated profile
hash before packing the final fixture. Never replace digest strings in serialized
JSON. Ordinary request inputs continue to omit `profile_sha256`.

Grok does not emit a replacement `test_schemas.py`. The coordinator applies only
the separately reviewed assertion change `71` to `81` after all ten new schemas
exist. The complete product scope stays the plan's fourteen paths. The generator
and review records remain outside the product scope.

## Required resource tests

Test Draft 2020-12 validity, exact root metadata, all reference destinations and
JSON Pointer fragments, absence of nested resource IDs, anchors and dynamic
references, nested closed data shapes, strict integer checking, profile constants
and exact inventory hashes. The integer checker accepts only
`type(instance) is int`, including when selecting common definitions directly.
Use only the installed supported `jsonschema` and `referencing` public APIs.

Validate every prepared positive case before using it as a mutation source.
Coverage includes all six saved kinds; both ordinary inputs; five success data
branches; six states with both pending-raw-body situations; normalized present,
missing, inaccessible and unavailable outcomes; a mixed raw target set; both Git
object formats; source-only configuration; and full typed JSON/TOML results.
Typed samples include all seven corrected CONFIG success vectors, covering
source coordinates, escaped pointers, implicit TOML tables, declarations,
numeric values and original Unicode spelling. A missing sibling target must
not invalidate the separately valid configuration-evidence shape.

For each closed nested wire/result object, reject unknown fields and omission
of required fields. Exercise illegal mode/state nulls, wrong ref kinds, malformed
IDs and hashes, invalid enums, bool/float/int-subclass integers, collection caps
and malformed kernel nodes, declarations, spans, Git targets and walks. Test
fixed lexical forms with terminal LF, CR, CRLF and Unicode line separators so
regex end anchoring cannot accidentally admit trailing characters.

Keep schema structure and semantic replay distinct. Schema string lengths do
not prove UTF-8 byte limits; a lexical OID union does not prove agreement with
its selected Git format. Valid-looking hashes do not prove a ce1 identity,
reference or derivation. The separately reviewed negative-case errata preserve
intentional corrupted IDs and references. Tests must not invent public runtime
error codes or claim these later semantic checks passed.

Profile tests verify every fixed maximum and admission value from R12, all ten
exact filename/title pairs, positive byte sizes, ASCII inventory order and the
actual schema-byte hashes. Schema/profile bytes must reproduce the required
serialization exactly, including one terminal LF. The resource tests must not
rewrite resources or normalize a failed candidate in place.

After mechanical integration and source freeze, run the affected contract tests
and both locked Python regression suites. Build isolated wheels using the
existing package rules and prove the ten schemas and profile are present at
their required package paths with byte-identical contents. Preserve all 71 old
schema bytes and every source path outside the fourteen-path increment.

Resource acceptance establishes only this resource prerequisite. Public command
behavior, retained-I/O failures, saved-byte/identity/derivation replay, real host
observations and CODE successor capture remain subsequent work. No push, merge,
real Vault change or human gate is authorized by this output contract.
