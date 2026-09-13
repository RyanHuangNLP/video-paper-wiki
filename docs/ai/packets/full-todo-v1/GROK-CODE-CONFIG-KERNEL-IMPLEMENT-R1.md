# Grok Build: bounded CODE configuration kernel

Preparation only. Do not begin this task until Architect has accepted and locally
delivered the Git kernel, created `CODE-CONFIG-KERNEL-freeze-r1.json`, and issued
the explicit dispatch naming that freeze. The currently active Git repair takes
priority. This draft is not permission to run another Builder concurrently.

After that dispatch, use only Grok Build CLI `grok-4.6 / xhigh`, normal permission
mode, one Builder and no subagents. Read the exact source root, accepted baseline
head/tree, allowed paths, immutable fixture and required input hashes from the
freeze. Refuse a mismatch; never silently select the old outer repository as the
production baseline. No Git mutation, external acquisition, dependency/model
installation, real Vault/admin operation or unrelated source access is allowed.

Implement the pure API in CODE-CONFIG-KERNEL-R1.md plus the unchanged
CODE-CONFIG-CLARIFICATIONS-R2.md. CODE-PROOF-CLOSURE-R3.md supplies the exact numeric
grammar/tuple rules and source-coordinate subset cited by that contract. The
26-vector TOML transition matrix and dynamic offset vectors in the freeze are
normative supplementary examples, not a whitelist of source strings.

The prospective allowed source paths are exactly:

- `src/video_paper_wiki/code_config_parser.py`
- `tests/unit/test_code_config_parser.py`
- `tests/fixtures/code-config-vectors-v1.json`

The last is a byte-exact copy of the accepted independent `static-vectors-r2.json`
under the packet's `code-proof-v1/config-r1` evidence directory. Its actual bytes
and hash must be bound in the freeze. Do not regenerate or repair that fixture.
Do not edit the accepted Git kernel or any legacy source/schema/test/metadata.
The separate freeze names the sole new development-brief path you may write.

Build the bounded scanner and exact source-coordinate representation first,
then perform the mandatory independent stdlib whole-tree cross-check. Do not
delegate unbounded hostile input to json.loads/tomllib.loads before scanner
limits, or replace the scanner with parsing followed by regex source searches.
Preserve real original byte/codepoint spans, decoded-key identity, distinct TOML
table states, finite numeric semantics and all thirteen limits. Count every
implicit node and declaration before insertion. Return no raw bytes, Decimal,
float or source snippets in result metadata or exceptions. No dynamic evaluation,
imports of supplied source, file/resource/network/subprocess calls or global
Decimal/integer-limit changes are allowed during parser execution.

Avoid the strict-key bug rejected in the Git kernel: after exact builtin dict
and constant-time length checks, verify every key has exact str type before
set creation, membership, lookup, equality or formatting can invoke arbitrary
callbacks. Snapshot validated limits into owned primitive data.

Tests must assert complete fixture success results, including `source` and every
record in `expected_nodes`; derive budget expectations independently from those
declarative nodes and their declaration/child lists. The fixture's extra notes
are provenance, not API fields. Run all success/refusal vectors and both groups
in `supplementary_groups` (`toml_transition_matrix_r2` and
`dynamic_offset_vectors_r2`). Numeric/string/depth/node/declaration boundary and
cross-check corruption tests remain required even when absent from static data.
Compare span and text/snippet hashes to the existing pure legacy helpers in
tests; no legacy production import is required by the new implementation.

Include callback traps for non-exact primitives/keys; complete deterministic
output/key ordering and no-alias checks; CRLF, multibyte Unicode, escaped keys,
surrogate pairs, original token positions and snippet boundaries; hostile tiny
Decimal contexts with no rounding or global mutation; full TOML promotion,
dotted-prefix, closed-inline and duplicate semantics. Exercise parser mismatch
for changed type/key sets/array order/values, not only leaf counts. Rejected
inputs must never produce a partial node list or incidental Python traceback.

Construct valid fixtures before arming hash/decoder instrumentation, so tests
measure only the call under test. Do not introduce unconditional assertions,
skip/xfail or change expected results to match a defective implementation.

Use actual editing tools in bounded chunks. If an editing tool fails, report
the concrete failure rather than repeatedly describing a planned edit. After
implementation run the complete focused module on both existing locked Python
3.12 and 3.13 runtimes. Set PYTHONDONTWRITEBYTECODE=1 and
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, use this source tree's src as PYTHONPATH, and
short real /private/tmp basetemp/cache directories. No dependency install or
full-repository test run is requested at this pure-kernel boundary.

Write the new brief with exact contract/freeze/session/model/effort, actual
changed paths, every relevant command and result, any failures or unrun checks,
computed SHA-256/size of all three candidate paths, and
`source_writes_stopped: true`. Never invent counts, hashes, scientific approval
or delivery. Stop writing and return the brief path; Architect and Repo Steward
must review and replay independent cases before the next packet begins.
