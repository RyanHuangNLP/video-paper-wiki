# Implement the CODE resource prerequisite — exact bounded R1

You are the sole Grok Build implementation author, explicitly grok-4.6 / xhigh.
Return complete code as specified below. This call permits only read_file on the
prepared files named in invocation-inputs.json in your current input directory.
Read that descriptor and the complete listed inputs. Do not read the repository,
other directories, credentials, session logs or unrelated files. Do not invoke
shell, writes, network/web, MCP, agents, package tools or repository discovery.
Do not run your outputs or tests. Normal permission mode stays enabled.

## Exact scope and input precedence

Implement exactly the reviewed R12 resource prerequisite: ten new schema files,
one profile and a new contract-test module. Generate the resources through the
self-contained Python generator specified by
CODE-PROOF-RESOURCE-OUTPUT-CONTRACT-R1.md. That output contract selects the output
mechanism of CODE-PROOF-RESOURCE-GENERATION-PLAN-R1.md. The coordinator has now
accepted CONFIG at local head 4ab1830939cd41981983909763434d5612df6070, tree
22fc77a38704386eaad5ad9be8a9268f0a1a5392. Earlier present-tense statements in these
preserved preparation documents about a running/rejected CONFIG candidate are
historical. The invocation descriptor records completed preparation reviews.
No public CODE orchestration has yet been accepted.

R2–R12 public contracts apply cumulatively, with explicit later amendments
controlling earlier suggestions. R7 supplies the complete closed public shapes;
R9 supplies repository grammar and public closure; R10/R11 fix caps and resource
admission; R12 fixes the ten-resource inventory, exact profile and reference
closure. R4 supplies the full six saved envelopes, IDs, refs and stored paths;
R5 supplies all pending-state nullability and success-state dependencies.
R6/R8 retained-I/O requirements are context for the later public implementation,
not permission to implement a filesystem workflow in this increment.

Both complete accepted kernel contracts and their clarifications are supplied.
Preserve their full result shapes, lowerable-limit maps, node/declaration types,
source spelling and coordinates. Do not redesign either kernel to simplify a
schema. The interface-facts and legacy-value-facts files supply checked existing
package APIs, lexical/value conventions and the distinction between inherited
helper behavior and the public layer's strict builtin-type requirements.

selected-positive-examples-r1.json is a compact transport of actual accepted
synthetic fixture values. Its preparation profile hash is 64 zeroes. It includes
all 82 base wire JSON cases and all seven typed CONFIG success variants using
SHA-1; the coverage inventory also names the locally prepared SHA-256 counterparts.
These are legitimate fixture shapes, not provider attestations or actual public
command executions. The coordinator will rebuild the complete 264-case bundle
with the generated profile hash and updated ce1 IDs/references before testing.
Do not embed the zero hash, sample IDs, selected file order or sample count as
production constants. Test code must iterate over the full final bundle.

public-resource-negative-cases-r2.json and its R3 errata distinguish schema
rejections from later semantic replay. Preserve deliberately malformed IDs or
references when constructing those negatives. A valid-looking resealed forgery
can be structurally valid; do not invent a schema claim that proves its origin,
reference identity, byte budget or derivation.

## Complete output format

Return exactly two complete Python files, each with its own explicit markers:

BEGIN_FILE generate_code_proof_resources.py
```python
<the complete self-contained resource generator>
```
END_FILE generate_code_proof_resources.py

BEGIN_FILE tests/contract/test_code_proof_resources.py
```python
<the complete product contract tests>
```
END_FILE tests/contract/test_code_proof_resources.py

The angle-bracket lines above describe required content; do not output them as
placeholders. No elisions, TODO implementations, diff for a nonexistent file,
separate manual resource edits or partial definitions. Finish with a short brief
naming the two outputs, explicitly stating that tests were not run, and listing
any actual unresolved contract question. Do not claim delivery or acceptance.

The generator accepts exactly --output-dir PATH, refuses any existing path
including a symlink, and creates only the eleven literal resource paths and
their parents beneath the supplied fresh absent directory. It contains all
resource definitions. Allow only necessary stdlib argument/JSON/hash/path
imports. No project imports, repository reads, subprocess, Git, network, dynamic
imports/code execution, environment/settings/permission changes or extra files.
Serialize each resource with indent=2, ensure_ascii=False, allow_nan=False and
one LF, using only integer-valued numbers. Generate schemas first; then compute
their exact byte counts/hashes and generate the ASCII-filename-sorted profile.
No self-hash cycle or profile hash inside schemas.

## Resource and test acceptance essentials

Use the exact R12 filenames, IDs, titles and dialect. Every $ref resolves inside
the explicit ten-resource set and its JSON Pointer fragments. No legacy schema
dependencies, relative external refs, nested $id, anchors or dynamic references.
The common schema supplies complete closed definitions for public values and
both kernel results, and $defs/profile. Nine schemas accept actual instances;
the common profile definition is validated separately using the same registry.

Close every object at its owning level, require all declared nullable fields,
and constrain full nested kernel nodes, declarations, spans, targets, walks,
refs, limits and status payloads. Preserve mode/state-dependent nullability and
branches. Ordinary request input permits omitted limits but never profile_sha256;
saved request requires complete limits and profile_sha256. Source-only config
has result=null and the fixed reason; JSON/TOML carry the complete typed result.
A mixed raw observation remains valid, and a separately proved configuration
target remains valid when a sibling target is missing.

Test exact-int validation with type(value) is int, rejecting bool, float 1.0 and
int subclasses. Test profile constants, all inventory sizes/hashes/order, exact
serialized bytes and one LF. The common profile definition describes rows
structurally; tests compare their actual byte inventory semantically. Fixed
lexical values must reject terminal LF, CR, CRLF, U+2028 and U+2029. JSON Schema
search-pattern semantics require actual end anchoring. Preserve original Unicode
source keys/pointers/values; do not impose NFC on source-derived fields.

Load the profile from the imported source package's profiles directory and the
ten named source schema files from that same checkout's schemas directory.
Build a fresh explicit referencing.Registry with undeclared retrieval denied;
use only supported jsonschema/referencing public APIs in the interface facts.
Do not assume a nonexistent public loader/function/exported error constant, or
discover neighboring unrelated resources. Tests must be read-only.

The final fixture path is tests/fixtures/code-proof-resource-v1.json. Its closed
transport is {schema, profile_sha256, cases}; each closed case has {name, title,
instance}, unique ASCII names sorted by name. Assert that profile_sha256 matches
actual profile bytes, and validate every case before selecting mutation seeds
by declared title/kind/state/format. Exercise all six saved kinds, both ordinary
inputs, five success payloads, six states and both pending-raw-body situations,
normalized other outcomes, mixed raw proof, both Git formats and all seven
typed CONFIG variants. Mutation tests reject unknown/missing required fields in
every represented closed nested object, malformed typed results and strict
integers, wrong ref kinds, invalid enums, excess arrays and impossible nulls.
Keep structural limits distinct from full byte-budget/identity/derivation replay.

The coordinator alone will mechanically pack reviewed fixture material and
change the existing test_schemas.py count assertion from 71 to 81 after the ten
resources exist. Do not return or alter that file. No package metadata changes,
public commands, retained-I/O engine, legacy schemas or other product paths are
in scope. After you stop, the coordinator will inspect both complete outputs,
obtain independent generator review before offline execution, verify generated
resources, rebuild fixtures, integrate the exact fourteen paths, freeze them,
and run both locked Python suites plus independent installed-wheel byte parity.

This output establishes a candidate resource prerequisite. It does not complete
CODE, authorize Git operations, publish source, change a real Vault, or close
human gates. If a real contract contradiction prevents a valid complete output,
report the exact conflict rather than silently weakening the required behavior.
