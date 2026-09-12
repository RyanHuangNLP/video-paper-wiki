Implement a small Python 3.12/3.13 private resource-validation foundation. Return
two complete Python fenced blocks, first code_proof_resources.py and then
test_code_proof_resources.py. Use only this natural-language instruction. Do not
read files, use tools, run shell commands, browse, delegate, change Git, or claim
tests ran. I will review and run your returned source locally. There are no file
attachments to inspect. Do not implement public command orchestration or file I/O.

The production module will live in the existing video_paper_wiki Python package.
The project already has jsonschema and referencing installed. Use their explicit
Draft202012Validator and Registry APIs, with a strict integer checker that only
accepts type(value) is int. Use standard-library dependencies otherwise. Do not
import the project's legacy resource loader or other product modules.

Define immutable ResourcePin(relative_path, size_bytes, sha256) and
ResourceOriginPlan(layout, package_directory, schemas_directory,
profiles_directory, resources) records. The resources field is an ASCII-sorted
tuple of ResourcePin records. Directory fields are absolute lexical strings.
resource_origin_plan() has no arguments and uses only this module's __file__.
It must be absolute, have no NUL, dot or dot-dot components, and sit directly in
a directory named video_paper_wiki. If that package's parent is named src, choose
layout source and that src directory's sibling schemas; otherwise choose layout
installed and package/schemas. Profiles is always package/profiles. Never use
CWD, environment overrides, resolve(), existence checks or an alternative-origin
fallback. An installed package literally under src deliberately selects the
source rule. The later retained I/O owner establishes actual filesystem-backed
origins and no-follow identity; a lexical plan alone grants no file authority.

The module must pin the following eleven exact resource bytes using these
literal production constants. For each schema stem S below, filename is
video-paper-wiki.S.v1.schema.json, title is video-paper-wiki.S.v1, schema ID is
https://video-paper-wiki.dev/schemas/ plus that filename, and logical resource key
is schemas/ plus filename. The profile's logical key is profiles/code-proof-v1.json.

Schema stem | byte size | SHA-256
code-acquisition-intent | 818 | acf785648ef3e8c085db3ec0863b0c67230464a15a24aa93f5e5a27418fedbef
code-config-evidence | 803 | 86be2b14d9ef748283aa0c5671ac6b94ea038cc04eee553e1f5a93dd1ce2821b
code-git-bundle | 778 | 69f112e15e430a537bf05417281013bc1ce9d674c9dfc0521f3adb4884cf9aac
code-proof-command-result | 353 | a9040ea7362d2ca8d9f6a16a3e05f7d80b02a91c5ba086d4c925988c059641d2
code-proof-common | 96085 | e151c80eba28e8a0ee8346a64bb7969fd0be03db64b90b282e5fa6b86498ea82
code-proof-observation | 818 | da1f61febafe8a7601b63114c15c8523ff381db47549b072965066e14a8cb85b
code-proof-observe-input | 350 | 146459e1da831ec6c7fb26382608686047085fe3de98f4101a1ba19f5e7be137
code-proof-request-input | 350 | a0492606c26a681ef9c457d27708b7b797ea3de3bff11f0d6525fc5d48913339
code-proof-request | 794 | d3f34854069567640564ae000f6b7f71c77f903cf92588704bc579deb7429ad7
code-source-handoff | 799 | 27f5388be15eb78e3aced47f72832468d3a7b6b54bc352263afb7f5534402876
Profile | 3761 | 650a6a51a1f08651d659262424577a90233649e4949bfc0cc4850d7a7777ee32

compile_code_proof_resources(retained_bytes) requires an exact builtin dict with
exact builtin str keys and exact builtin bytes values and exactly those eleven
keys. It returns a fresh CodeProofResources. First check complete mapping types
and keys, then in ASCII logical-key order compare each byte length and digest to
production pins, before parsing JSON or creating any validators. Never trust a
set merely because a supplied profile matches supplied schemas. No caller-supplied
pins, origins, registry, callbacks or validation configuration are permitted.

Parse retained resource bytes with strict UTF-8; reject BOM, duplicate keys,
floating or nonfinite numbers, surrogates, trailing JSON and any formatting other
than json.dumps(value, ensure_ascii=False, indent=2) plus exactly one LF. Preserve
parsed key order for that comparison. Add no public JSON integer-range/depth
policy; this private parser sees only byte-pinned resources in production.

Each schema must be a valid Draft 2020-12 schema with exact $schema
https://json-schema.org/draft/2020-12/schema and its exact $id/title. Check every
reference without retrieving anything: forbid nested $id, $dynamicRef,
$dynamicAnchor, $anchor, $recursiveRef and $recursiveAnchor. A $ref may be a
same-document fragment, an exact one of the ten schema IDs, or that exact ID
plus a fragment. An empty fragment names the document root; a nonempty fragment
must start with / and use only valid ~0/~1 JSON Pointer escapes. Require every
pointer to resolve; list index spelling must be canonical nonnegative decimal.
Reject URI percent-escape aliases, undeclared/relative IDs and nonexistent
targets. Walk schema dictionaries/lists for forbidden keywords and refs. There
are no external references or anchors in the accepted resources.

Create one fresh referencing.Registry with exactly the ten schema IDs and an
explicit retrieval callback that always raises a non-retrieval failure. The Draft
dialect URI grants no retrieval authority. Construct the strict validator from
those schema objects and this registry. There is no eleventh profile schema or
profile resource registration. Validate the profile using the common schema's
exact /$defs/profile definition and the same registry.

The profile has exactly schema, profile, revision, limits, admission, schemas.
schema is video-paper-wiki.code-proof-profile.v1, profile is code-proof-v1,
revision is exact int 1. schemas is a filename-sorted list of exactly ten unique
closed rows {title, filename, size_bytes, sha256}; compare each row to the
production schema pin. admission is exactly max_request_input_bytes=65536 and
max_observe_input_bytes=1048576. limits is exactly the three groups below, with
these exact builtin integer hard values:

git: max_targets=32, max_objects=2048, max_tree_entries=32768,
max_object_bytes=8388608, max_total_object_bytes=33554432.
config: max_source_bytes=262144, max_depth=32, max_nodes=1024,
max_array_items=256, max_object_keys=1024, max_key_bytes=256,
max_string_codepoints=16384, max_scalars=512, max_numeric_lexeme_bytes=128,
max_numeric_coefficient_digits=64, max_numeric_abs_exponent=128,
max_numeric_canonical_bytes=256, max_declarations=4096.
public: max_bundle_bytes=1048576, max_inline_normalized_bytes=16384,
max_request_bytes=65536, max_intent_bytes=1048576,
max_observation_bytes=2097152, max_config_document_bytes=2097152,
max_handoff_bytes=131072, max_output_peak_bytes=134217728.

CodeProofResources exposes only read-only profile_sha256 and resource_pins plus
the two methods below. Keep raw bytes, parsed documents and validators private;
no mutable schema/profile/registry is returned. Input-dict replacement after
compilation cannot affect the context. No process-global resource/validator cache.

validate_structure(title, instance) returns None on structural success. Title
must be exact str and one of the ten declared titles, not an arbitrary URI or
fragment. Before invoking its strict validator, iteratively check exact JSON
builtins: dict, list, str, int, bool and None only; all dict keys exact str;
reject subclasses, floats even 1.0, nonfinite values, surrogate keys/strings and
cycles. Shared acyclic containers are permitted. Check bool separately from int.
Do not mutate or normalize caller values. This proves structural shape only:
it does not authenticate IDs, canonical saved bytes, references, NFC metadata,
source text, ordering, limits, states, derived results or officiality. A resealed
semantic forgery may be structurally valid. Return no accepted/eligible flag.

materialize_limits(value) uses None for omitted caller limits and returns a new
independent plain three-group dict of full hard limits. For an exact builtin
dict, require every exact group/key, exact nested builtin dicts and positive
exact builtin ints no greater than each hard maximum. Reject extra/missing
keys, bool, float, subclasses, zero and increases. Return independently copied
nested dicts. Admission caps are separate and not lowerable. The later public
input validator distinguishes explicit JSON null from omission before calling
this helper, so None is only a private omitted-value sentinel.

Use CodeProofResourceError(reason) for resource_origin (invalid lexical origin),
resource_hash (size/digest mismatch), or resource_shape (mapping/types, parsing,
profile, Draft or reference failure). Use CodeProofStructureError(reason) for
type (preflight type/cycle/surrogate failure), shape (title/schema failure) or
limits (limit helper failure). Each exposes only that fixed reason and a fixed
safe message. Never expose raw paths, arbitrary names/values, parser/resolver/
validator diagnostics or chained raw exceptions. Do not replace these private
errors with a public command envelope. The later retained I/O session constructs
its full public context and makes changed lineage outrank all other failures.

Production import (apart from Python's normal imports), origin selection,
compilation and validation must perform zero filesystem reads/writes/enumeration,
network calls, shell/Git calls or legacy-loader use. This module takes bytes from
the later single retained I/O owner and must not open its own independent session.

For the test module, use pytest and actual existing repository fixtures. Tests
are permitted to read fixture inputs. From tests/unit/test_code_proof_resources.py,
the checkout root is Path(__file__).parents[2]. Actual schemas are at root/schemas;
profile is at root/src/video_paper_wiki/profiles/code-proof-v1.json. The existing
root/tests/fixtures/code-proof-resource-v1.json is a JSON object with schema,
profile_sha256 and cases; cases has 264 positive structural rows, each exactly
name, title, instance. Read and replay those rows against the new production
context without embedding or modifying the fixture. This instruction describes
its interface only; you do not need to inspect or reproduce its content.

Add meaningful tests for immutable pins/context independence, source/installed
lexical origins and changed CWD independence, missing-origin no-fallback policy,
every pin mutation, mapping types/missing/extra entries, self-consistent forged
resource/profile bytes, strict parsing, forbidden/missing refs, denied retrieval,
builtin subclasses/cycles/surrogates/shared acyclic values, unknown titles and
every limit field's 1/max/max+1/zero/bool/float/missing/extra boundaries. To reach
private parser/ref checks, test those helpers on mutated input directly; never
disable or replace production pins. Keep schema-acceptance expectations separate
from semantic acceptance. Instrument filesystem/network/subprocess/legacy-loader
entrypoints after necessary module imports and fixture reads; exercise production
methods under those guards. Verify errors cannot include marker secrets. Return
complete runnable test definitions with honest unexecuted status, not pseudocode.

Concrete implementation clarifications, incorporated into this same instruction:

Name and use these private pure helpers so the tests can exercise malformed
branches without defeating production pins: _parse_resource_bytes(data: bytes)
returns an exact builtin root dict after the strict resource-format checks;
_validate_schema_references(schemas: dict[str, dict]) returns None for a valid
exact ten-ID schema map with full reference closure; and
_validate_profile_inventory(profile: dict) returns None after exact builtin
profile shape, rows, hard limits and admission checks against production pins.
Each rejects malformed input with CodeProofResourceError("resource_shape").
The production compiler invokes these helpers after all byte pins pass. No
public test mode or pin/registry override is allowed.

Validate the profile using a validator schema containing a $ref to the exact
common schema ID followed by #/$defs/profile and the fresh ten-resource registry.
Do not detach the profile definition from its common root: its local refs must
resolve against the full common document.

The 264 fixture rows cover nine wire titles. Add a separate explicit structural
probe of an empty object under the exact common title and assert None. This
accepted common root is definitions-only; do not claim that it authenticates
arbitrary evidence.

Freeze private exception strings exactly: CODE proof resource: <reason> and
CODE proof structure: <reason>. Insert only a validated enum member. An invalid
constructor reason raises ValueError with exactly Invalid CODE proof error reason
without formatting the invalid object. Suppress raw exception chaining. Tests
assert exact safe messages and absence of adversarial marker text.

The returned unit test file only needs pure checks and lexical source/installed
origin tests, with the actual source resources as fixture data. A separately owned
external acceptance harness will actually build/install the wheel and replay all
264 cases plus the common probe under both isolated interpreters. Do not add a
wheel build subprocess or require a wheel environment variable in your unit tests.
That external harness will verify the installed module and resource bytes, use
-I in an empty cwd with only a fresh installation target added to sys.path, and
reject any accidental import from source/src. Mocked origin tests do not claim
that installed-wheel check has run.
