Provide a bounded correction to an unaccepted private Python 3.12/3.13 resource
validation module. Use only these natural-language instructions. Do not read
files, use tools, run shell commands, browse, delegate, change Git, or claim tests
ran. No attachments or source files are supplied. Return only the two requested
Python fenced blocks once, followed by the sentence "Tests not run." Do not
repeat an earlier draft before your final answer.

The existing module is video_paper_wiki.code_proof_resources. Keep all existing
byte pins, schemas, profile, dependency choices, public signatures and zero-I/O
scope. This correction does not implement a public command or a file loader.
The caller supplies only an exact eleven-entry dict of retained resource bytes
to compile_code_proof_resources; no caller pins, validators or configuration
are permitted. The local integrator will replace the named definitions below
and leave every other source definition byte-identical.

Observed issues in the original unaccepted source:

1. materialize_limits compares dict keys using frozenset without first checking
   their exact types. A str-subclass group or key can be accepted, and custom
   keys can execute equality/hash code during that comparison. The private
   profile mapping helper has the same omission.
2. A JSON Pointer list index of more than Python's configured decimal conversion
   digit limit escapes as raw ValueError. Malformed input to the named schema
   reference helper must always fail with its safe private resource error.
3. The schema-reference walk has no JSON graph preflight. A cycle through an
   anonymous dict/list can loop; nested non-builtin or surrogate keys can be
   overlooked. The helper is explicitly required to handle malformed input.
4. CodeProofResources.__init__ directly accepts caller-provided digest, pins,
   validators and hard limits, allowing construction that bypasses the compiler.
   Make construction internal to the verified compiler. Python private-attribute
   tampering is not an OS security boundary and is not part of this correction.
5. Both Python versions ran the original unit tests: 261 passed and one failed.
   The failed assertion expected the definitions-only common schema to reject
   an empty list. That schema deliberately accepts any preflight-valid JSON
   value. Fix the test expectation; do not change the schema or narrow validation.

First fenced block: return exactly these seven complete top-level definitions,
with these exact names and no imports, constants, additional definitions or
monkeypatching: _require_plain_json_tree, _canonical_list_index,
_validate_schema_references, _require_exact_mapping, CodeProofResources,
compile_code_proof_resources, and _walk_schema_document. Order does not matter.

Existing production imports available to those definitions are copy, enum,
hashlib, json, dataclass, Final, NoReturn, Draft202012Validator, extend, Registry
and DRAFT202012. Existing private exceptions are CodeProofResourceError(reason)
and CodeProofStructureError(reason). Use resource_shape for the former in these
corrections, and type/shape/limits for the latter as appropriate. Their messages
are fixed and safe; raise them from None when converting other exceptions. Do
not format untrusted objects or leak parser, key, path or validator diagnostics.

_require_plain_json_tree(root: object) -> None:
Iteratively admit only exact builtin dict, list, str, int, bool and None, with
exact str dict keys and no surrogate codepoints in strings or keys. Use the
existing pure _contains_surrogate(text: str) helper. Reject cycles with
CodeProofResourceError("resource_shape"), while accepting shared acyclic
containers. Use explicit entry/exit traversal and ancestor/completed sets so
shared graphs do not expand exponentially. Do not recurse, mutate, normalize,
serialize, or add integer magnitude, depth or node caps. Check type before
performing any key equality/hash or invoking user-defined operations.

_canonical_list_index(token: str) -> int:
Require an exact nonempty ASCII decimal string, canonical spelling with no
leading zero except the sole character 0. Convert to a nonnegative int. Any
conversion failure must become resource_shape with chaining suppressed. The
existing pointer resolver checks that the index is less than the list length;
do not create a new public JSON integer-range rule. No percent aliases, Unicode
digits, signs or whitespace are valid.

_validate_schema_references(schemas: dict[str, dict]) -> None:
First require an exact builtin dict and preflight its complete JSON graph with
_require_plain_json_tree. Require exactly the existing ten IDs in _SCHEMA_IDS,
exact builtin str keys and exact builtin root dicts, each with its exact str
$id equal to its map key. Then visit each document in sorted ID order using
_walk_schema_document(document, document, schemas). Return None. Do not retrieve,
alter pins, permit a registry override, or infer a new schema inventory.

_walk_schema_document(document: dict, current_root: dict,
schemas: dict[str, dict]) -> None:
The caller above has already proved the entire graph is plain, surrogate-free
and acyclic. Iteratively visit dict/list nodes. Reject any nested $id; a $id is
allowed only on the root document itself. Reject all keys named in the existing
_FORBIDDEN_SCHEMA_KEYWORDS. For every $ref use the existing pure
_resolve_ref(ref, current_root, schemas), which checks exact permitted IDs and
fully resolved JSON Pointers without retrieval. Track already visited containers
to avoid repeated expansion of shared acyclic subgraphs. A node encountered
nested must not acquire root privileges merely because its identity was seen
before. No change to the existing _resolve_ref or _resolve_json_pointer helpers
is requested; the latter calls the corrected _canonical_list_index.

_require_exact_mapping(value: object, expected_keys: tuple[str, ...]) -> dict:
Require an exact dict, inspect every key's type before set construction or key
lookup, require exact str keys and the exact expected key set, and return the
original dict without mutation. Reject failures with resource_shape. This helper
is used by the unchanged _validate_profile_inventory to validate all its closed
maps. Its expected_keys argument is internal trusted constants.

CodeProofResources:
Keep slots _hard_limits, _profile_sha256, _resource_pins, _validators. Read-only
properties profile_sha256 and resource_pins return the stored pinned digest and
immutable pin tuple. Public direct construction must refuse, with no supported
caller-controlled constructor or factory. Use an __init__(self) that raises a
safe CodeProofResourceError("resource_shape"); the compiler alone will allocate
with object.__new__(CodeProofResources) and assign the four private slots after
all checks succeed. Do not add a caller token, public factory or test bypass.

validate_structure(self, title: object, instance: object) -> None:
Require exact str title membership in self._validators, otherwise raise
CodeProofStructureError("shape"). Call existing _preflight_instance(instance),
which raises safe CodeProofStructureError("type") for non-JSON builtins, subclass,
surrogate or cycle errors and permits shared acyclic values. Then call the
selected private validator's validate(instance). Convert validator failures to
safe CodeProofStructureError("shape") from None. Return None on success. Keep
validation structural only, preserving caller data and Unicode spelling. Do
not impose an object-only requirement on the definitions-only common title.

materialize_limits(self, value: object) -> dict[str, dict[str, int]]:
None means the private omitted-value sentinel and returns
_copy_hard_limits(self._hard_limits), an existing independent-copy helper.
Otherwise require exact builtin dict outer/inner maps, every key an exact str
checked BEFORE set comparison or lookup, and exactly the groups in
_LIMIT_GROUP_KEYS and each group's keys in _LIMIT_KEYS[group]. For every field
require type(raw) is int, raw > 0 and raw <= self._hard_limits[group][key].
Reject subclasses, bool, float, missing/extra keys and raises with safe
CodeProofStructureError("limits"). Return new independent outer/inner builtin
dicts. Never modify caller maps or the stored maxima. No admission fields are
part of this helper, and no caller validation configuration is accepted.

compile_code_proof_resources(retained_bytes: object) -> CodeProofResources:
Keep this exact existing compile sequence using existing pure helpers/constants:
_require_retained_mapping produces an ASCII-key-sorted list of (key, bytes) after
strictly checking complete builtin mapping shape. _check_production_pins checks
all eleven lengths and SHA-256 pins before parsing. Parse each snapshot entry
using _parse_resource_bytes into a private key-to-document dict. For each
(stem, size, digest) in _SCHEMA_STEMS, take parsed[_schema_logical_key(stem)],
call _require_schema_header(document, stem), associate it with _schema_id(stem),
and call Draft202012Validator.check_schema(document). Convert schema-check
exceptions to resource_shape safely. Call _validate_schema_references on the
complete ten-ID map. Select parsed[_PROFILE_LOGICAL_KEY] and call the unchanged
_validate_profile_inventory(profile).

Then build exactly one fresh registry with existing _build_registry(schemas),
which registers exactly the ten IDs with immutable private document copies and
a deny-all retrieval callback. Validate the profile with
_StrictDraft202012Validator({"$ref": _PROFILE_DEF_REF}, registry=registry), where
_PROFILE_DEF_REF is the exact common-ID #/$defs/profile reference, preserving
the full common-document reference base. Create a private title-to-validator
dict using _schema_title(stem) and _StrictDraft202012Validator over a deepcopy
of schemas[_schema_id(stem)] and that same registry. Convert construction and
profile-validation exceptions to resource_shape safely. Only then allocate a
CodeProofResources with object.__new__, assign _profile_sha256=_PROFILE_SHA256,
_resource_pins=_PRODUCTION_PINS, _validators=the newly created private dict and
_hard_limits=_copy_hard_limits(_HARD_LIMITS), and return it. No public constructor
is called and no raw resources or mutable validation configuration are exposed.

Second fenced block: return exactly these five complete pytest functions, with
no imports, fixtures or new top-level helpers. The first replaces an existing
test and the other four are appended: test_structure_preflight_and_titles,
test_limit_exact_key_and_value_types, test_profile_exact_builtin_keys,
test_schema_reference_malformed_graphs, test_context_rejects_external_configuration.

Existing test imports are copy, json, pytest and cpr (the production module),
CodeProofResourceError, CodeProofStructureError, compile_code_proof_resources,
resource_origin_plan, _parse_resource_bytes, _validate_profile_inventory and
_validate_schema_references. Existing fixtures: resources is a compiled genuine
context, retained_bytes is the genuine eleven-key mapping, schema_map is a fresh
dict of the ten parsed schemas keyed by ID, profile_document is a fresh parsed
profile. Existing helpers: _assert_resource(exc, reason) and
_assert_structure(exc, reason) assert exact private class/reason/message with no
secret-marker leakage, _full_limits(resources) returns an independent full map.
Existing constants: _COMMON_TITLE is video-paper-wiki.code-proof-common.v1,
_COMMON_SCHEMA_ID is its exact full schema ID, and _MARKER is secret-marker text.
Existing simple builtin subclasses are _Str, _Dict, _List, _Int and _Bytes.

The replacement test_structure_preflight_and_titles(resources) must preserve
negative coverage for URI/noninventory/profile/fragment/subclass titles; reject
dict/list/str/int subclasses, floats and nonfinite values, surrogate keys/strings,
non-string or subclass keys, and dict/list/mixed cycles with reason type under
the common title. Explicitly assert shared acyclic containers and [] succeed
under the common title, without mutating shared NFD text. Use the actual wire
title video-paper-wiki.code-proof-request.v1 with {} to demonstrate a safe shape
failure. Unknown marker title uses shape. Do not weaken structural schemas.

The limits test must reject str-subclass group/key names, builtin-container
subclasses at each level and int-subclass values, in otherwise complete valid
maps. Also use an untrusted object key whose hash/equality methods are armed
only AFTER its dict is constructed: rejection must not call those methods or
format its marker text. Check outer and inner key boundaries independently.
Keep positive full/one/max acceptance and independent returned maps covered by
the existing test suite; add valid acceptance as a control if useful.

The profile test should replace one existing exact key at each of the profile,
limits, limit subgroup, admission and one inventory-row maps with _Str(key).
Each otherwise intact profile must refuse with resource_shape. Include a valid
unmodified profile control. Do not modify production pins or fixture files.

The schema-reference test must reject a greater-than-4300-digit decimal pointer
into a list, a cycle in an anonymous dict and list, a nested str-subclass key,
and a surrogate nested key/string, all through _validate_schema_references with
resource_shape. Include successful acyclic shared anonymous subgraphs and valid
escaped ~0/~1 pointers as controls. Build test mutations on fresh deep copies;
do not patch pin or registry validation. For the huge-index test, the helper's
safe refusal must work regardless of the interpreter's configured digit limit.

The context test must prove CodeProofResources() refuses safely and attempts
to pass external digest/pins/validators/hard_limits cannot create a context or
invoke an external validator callback. Since unsupported arguments are rejected
by Python's signature, TypeError is acceptable for those argument attempts;
do not assert diagnostics containing user-supplied values. Compile genuine
retained_bytes successfully, assert the result type, both read-only properties,
independent contexts and inability to reassign either property. Do not test or
claim protection against deliberate object.__new__ or private-slot tampering.
