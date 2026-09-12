# CODE proof resource generation contract — R12 candidate

Architect requirements for the remaining resource prerequisite. R2–R11 and
their evidence stay unchanged. This document does not dispatch another Builder,
install resources, replace the active CONFIG request, or assert CODE completion.
Generate actual resources only after a separate exact packet and handoff. The
public implementation freeze follows independently reviewed resource bytes.

## Resource inventory and reference closure

There are exactly ten new Draft 2020-12 schema files in `schemas/`:

1. `video-paper-wiki.code-proof-common.v1.schema.json`
2. `video-paper-wiki.code-proof-request-input.v1.schema.json`
3. `video-paper-wiki.code-proof-observe-input.v1.schema.json`
4. `video-paper-wiki.code-proof-command-result.v1.schema.json`
5. `video-paper-wiki.code-proof-request.v1.schema.json`
6. `video-paper-wiki.code-git-bundle.v1.schema.json`
7. `video-paper-wiki.code-acquisition-intent.v1.schema.json`
8. `video-paper-wiki.code-proof-observation.v1.schema.json`
9. `video-paper-wiki.code-config-evidence.v1.schema.json`
10. `video-paper-wiki.code-source-handoff.v1.schema.json`

For each filename F, `$id` is `https://video-paper-wiki.dev/schemas/` + F;
`title` is F without `.schema.json`; `$schema` is
`https://json-schema.org/draft/2020-12/schema`. There is no eleventh profile
schema. The common schema supplies `$defs/profile`, along with self-contained
definitions for both complete kernel results and CODE wire values. Profile
validation selects that exact definition through the retained registry.

All `$ref` values resolve to a JSON Pointer fragment in the same document or
to an exact `$id` in this ten-file set, optionally followed by a JSON Pointer
fragment. Every such fragment must resolve. Relative external references,
legacy schema dependencies, dynamic references, nested resource `$id` values,
and anchors are outside this generation. The Draft URI is a dialect identifier;
it does not authorize retrieval. Use the already installed Draft validator and
an explicit registry that refuses every undeclared retrieval. Resource discovery
must not iterate over, import, or trust unrelated schemas merely because they
are next to these ten files.

The six saved schemas validate complete R4/R7 envelopes. The two ordinary-input
schemas validate their complete R7 input objects, including R9's repository
grammar. The command-result schema validates only the successful `data` payload
for the five new CLI leaves. Its branches are request, observe, status, config,
and handoff, with exactly R7's fields. It does not define the existing outer CLI
success/error envelope and does not change a legacy command or schema.

All wire object shapes are closed at the level that owns their fields, with
required nullable fields distinct from omissions. Constrain types, enum values,
constant schema/kind fields, lexical ID/hash forms, lengths and array counts
where specified. A generic unconstrained object or array is not an acceptable
substitute for a nested kernel result, node, declaration, target, status, or ref.
Exact-string, exact-integer and container checks precede schema validation in
the pure API. A strict integer type checker accepts `type(value) is int` only.
It rejects bool, float values such as 1.0 and subclasses, even when ordinary
JSON Schema integer semantics would accept their numeric value.

Schema checking does not prove saved bytes canonical, IDs authentic, paths
ordered, limits lowerable, source text valid, OID widths consistent with the
selected format, or derivations correct. Those remain R4/R7/R9/R11 semantic
checks with retained-byte replay. Schema fixtures must label structural and
semantic rejection expectations separately; a structurally valid resealed
forgery must still fail the later public validator.

## Exact installed profile shape

The only new profile path is
`src/video_paper_wiki/profiles/code-proof-v1.json`. Its closed object has all six
required fields:

```text
{schema, profile, revision, limits, admission, schemas}
```

`schema` is `video-paper-wiki.code-proof-profile.v1`, `profile` is
`code-proof-v1`, and `revision` is exact integer 1. `limits` has exactly
`{git, config, public}`. The installed profile contains the following exact hard
maxima, not caller-lowered settings:

| Group | Key | Value |
| --- | --- | ---: |
| git | max_targets | 32 |
| git | max_objects | 2048 |
| git | max_tree_entries | 32768 |
| git | max_object_bytes | 8388608 |
| git | max_total_object_bytes | 33554432 |
| config | max_source_bytes | 262144 |
| config | max_depth | 32 |
| config | max_nodes | 1024 |
| config | max_array_items | 256 |
| config | max_object_keys | 1024 |
| config | max_key_bytes | 256 |
| config | max_string_codepoints | 16384 |
| config | max_scalars | 512 |
| config | max_numeric_lexeme_bytes | 128 |
| config | max_numeric_coefficient_digits | 64 |
| config | max_numeric_abs_exponent | 128 |
| config | max_numeric_canonical_bytes | 256 |
| config | max_declarations | 4096 |
| public | max_bundle_bytes | 1048576 |
| public | max_inline_normalized_bytes | 16384 |
| public | max_request_bytes | 65536 |
| public | max_intent_bytes | 1048576 |
| public | max_observation_bytes | 2097152 |
| public | max_config_document_bytes | 2097152 |
| public | max_handoff_bytes | 131072 |
| public | max_output_peak_bytes | 134217728 |

`admission` is exactly `{max_request_input_bytes: 65536,
max_observe_input_bytes: 1048576}`. These are fixed initial reader caps from
R10/R11, separate from `limits.public` and not lowerable by a saved request.
The request's complete limits map retains the existing lowerable semantics;
the installed profile itself must match every exact value above.

`schemas` contains exactly ten closed rows `{title, filename, size_bytes,
sha256}`, sorted by ASCII filename, with no duplicate title or filename. Title
and filename match the inventory and each other. Size is the exact positive byte
count and SHA-256 hashes the complete actual schema file, including its final LF.
Neither a schema nor its profile definition embeds its own byte hash. The common
profile definition describes these rows structurally; semantic validation
compares them to the exact retained inventory. No schema includes the generated
profile hash. This leaves an acyclic generation order: schemas, then profile,
then the external freeze and production resource pin.

Serialize schema and profile resources as UTF-8 JSON with two-space indentation,
`ensure_ascii=False`, finite integer numbers only, and one final LF. The resource
freeze pins exact bytes and does not normalize a changed resource on load. These
resource files are not ce1 envelopes; this formatting does not change R4's JCS
and LF rules for saved evidence. Resource object key order is fixed by the
generated candidate bytes, with no independent semantic ordering requirement.

## Trust root and source/installed selection

The future production resource module pins the reviewed profile size/hash and
all ten schema sizes/hashes from the freeze. Those constants are generated from
the accepted resources; they are not caller configuration or hashes trusted
only because the supplied profile says so. Every command compares all eleven
actual retained byte streams to that pin before creating outputs, validates the
profile and schema/reference closure, then creates one fresh registry from the
same retained bytes. A replaced profile plus replaced schemas cannot authorize
itself by making only its internal hashes agree.

Use R7's imported-package source/installed origins and the R6/R8 retained
session. Never consult CWD resources, select a new origin after failure, or
reuse a cached validator tied to another resource read. Profile origin is
always the imported package's `profiles` directory. The installed wheel must
carry the ten schemas in the existing package `schemas` directory and the
profile in `profiles`. Source layout uses the sibling checkout `schemas`
directory associated with that imported source package. Existing legacy
resource loaders may be reused only where they satisfy these rules; otherwise
the new module remains separate without changing their behavior.

An initially missing, mismatched or structurally invalid resource uses R8/R9's
`CODE_PROOF_RESOURCE_INVALID` context. A later changed or uncheckable retained
edge/byte stream still produces the higher-priority `WORK_PATH_UNSAFE`.
Resource hash, shape, and origin reasons stay the already defined R9 values.
No source path or raw schema-parser error is returned in public error details.

## Required generation handoff and acceptance

The later bounded Grok generation packet owns these eleven new resource paths
and separately named resource tests/fixtures. It must receive the actual
accepted kernel shapes as well as the current public contracts. Do not retrofit
accepted kernel errors or results to simplify schemas. Closed new public error
contexts remain R9/R11; the command-result success schema does not redefine
kernel errors or the outer CLI error envelope.

After the Builder stops, require an exact file manifest and independent checks
of every schema's Draft validity, `$id`/title/reference closure, nested closed
shape, hard-limit/profile inventory, hashes, and byte format. Positive fixtures
cover all six envelopes, both acquisition modes, all five result payloads,
pending states, incomplete raw targets, source-only/JSON/TOML configs, and both
Git object formats. Negative structural cases cover unknown/omitted fields,
wrong ref kind, bool/float integers, overlong or excess collections, illegal
mode-dependent nulls and kernel-result shapes. Semantic vectors separately
cover noncanonical saved bytes, wrong IDs/references, changed profile inventory,
order, lowered caps, and resealed inconsistent derivations.

The resource candidate may be reviewed before public orchestration exists;
report unavailable semantic workflow checks as pending, not passed. The public
implementation acceptance must later replay them, the complete retained-I/O
failure matrix, both locked Python suites and byte-identical installed-wheel
resource parity. Only that later exact-head acceptance completes public CODE.
