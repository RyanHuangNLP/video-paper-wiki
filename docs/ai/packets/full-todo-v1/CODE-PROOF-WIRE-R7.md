# CODE proof public wire — R7 candidate

Architect candidate closing the public data shapes left open by R2–R6. This is
requirements material, not a source dispatch, installed schema set or acceptance.
R2–R6, both kernel contracts and their reviews remain unchanged. Resource files,
hashes, exact implementation paths and independent review are still required
before public implementation. The active Grok packet remains the Git kernel.

All records below are closed: every listed field is required unless a rule
explicitly permits omission, and no unlisted field is admitted. Null is distinct
from omission. Types are exact JSON builtins with integer-only numbers, including
strict bool checks before integer validation. Canonical saved envelopes, ce1 IDs,
saved-byte references and per-file maxima follow R4. Identity metadata must be
NFC and source-derived text/keys/pointers/lexemes retain original Unicode spelling.
Schema validation never substitutes for cross-reference and replay validation.

## Common values and limits

`Ref(K)` is `{id, sha256}`, with the exact ce1 kind K in its ID and a 64-lowercase-
hex saved-byte SHA-256. A ref to the wrong kind fails before lookup. `OID(F)` is
exactly 40 lowercase hex for sha1 or 64 for sha256. All repeated formats, IDs,
repositories and paths must equal the bound request; there is no coercion.

Repository components match `[A-Za-z0-9][A-Za-z0-9._-]{0,99}`, exclude exact `.`
and `..`, and the name has no case-insensitive `.git` suffix. Input case is
lowercased once when preparing a request. Saved repository spelling is already
lowercase. This is a bounded locator grammar, not verification that the GitHub
repository exists. Paper IDs are exact strings up to 512 UTF-8 bytes satisfying
the current `identity.is_canonical_paper_id` after the exact-str check. They do
not require membership in the frozen 67-entry seed. Association refs keep R4's
legacy `{association_id, sha256}` semantics and remain explicitly unverified.

Each target is `{path, roles, allow_executable_source}` with R2's role enum and
Git-kernel path/casefold/prefix rules. Sort paths by ASCII bytes and roles by
ASCII bytes. All enum sets are unique. Executable permission may be true only
when every selected role is implementation or entrypoint.

The request `limits` is a closed three-part object `{git, config, public}`.
`git` contains exactly the five Git-kernel limits; `config` contains exactly the
thirteen configuration-kernel limits. `public` has these eight fields:

| Field | Hard maximum |
| --- | ---: |
| max_bundle_bytes | 1048576 |
| max_inline_normalized_bytes | 16384 |
| max_request_bytes | 65536 |
| max_intent_bytes | 1048576 |
| max_observation_bytes | 2097152 |
| max_config_document_bytes | 2097152 |
| max_handoff_bytes | 131072 |
| max_output_peak_bytes | 134217728 |

All values are positive exact ints, fully materialized and lowerable only within
their respective hard maxima. An ordinary request may omit `limits` entirely to
select the full profile; if present, the complete three-part map is required.
Saved request limits are never omitted. Ordinary request input is capped at
65536 raw bytes; ordinary observe input at 1048576 raw bytes. The lowered saved
caps apply to complete canonical envelope bytes, including LF and JSON escaping.
A representable text/node result may still exceed its serialized cap and refuse;
no envelope is truncated or partially installed to make it fit.

Acquisition timestamps are exact valid Gregorian UTC `YYYY-MM-DDTHH:MM:SSZ`,
20 characters, years 0001–9999, no fractional seconds/leap seconds/offsets.
No current-time inference or clock call supplies a missing acquisition time.
Executor is `{kind, id}`; kind is `human`, `host_tool`, or `unknown`. Human/host
IDs are nonempty NFC strings up to 128 UTF-8 bytes without control characters;
unknown has id=null. These are recorded assertions, not authenticated identities.

`Hosting` is null or `{provider, actor, repository, object_format, commit_oid,
locator, statement}`. Provider is `github`; actor uses the same executor shape.
The repeated origin equals the request. Locator is exactly the generated HTTPS
GitHub commit URL for the request origin. Statement is nonempty NFC text up to
2048 UTF-8 bytes with LF/TAB allowed but other C0/DEL/C1 controls forbidden.
An assertion can be present with an unknown actor; it remains `host_asserted`.
No provider, actor, statement or URL converts an object hash into officiality.

Acquisition locator values for a path are either its exact generated GitHub blob
URL or raw.githubusercontent.com URL from R2, without query/fragment/credentials.
URLs are constructed from the portable ASCII request fields without fetching.
This profile makes no claim that a particular host tool can return raw objects.

`TextMetadata` is `{normalized_size_bytes, normalized_sha256, newline_style,
ends_with_newline, line_count}`. Hash/line/newline fields exactly follow existing
`code_text_metadata`; normalized_size_bytes is the length after CRLF-to-LF only.
The text helper's existing byte cap must be verified to admit this profile's
8 MiB raw cap before it is reused. No legacy normalization behavior is changed.

## Ordinary command inputs

Request input has `{paper_id, source_association, repository, object_format,
commit_oid, targets, require_repository_assertion}` plus optional `limits`.
`source_association` is null or the R4 association ref. Profile hash is selected
from the retained installed profile, never supplied as a caller override.
All fields other than repository case and omitted limits are already canonical;
sorting, trimming, removing unknown fields or repairing OIDs is not permitted.

Observe input is one of two closed forms:

```text
git_objects:
{mode, observed_at, executor, hosting_assertion}

normalized_text:
{mode, observed_at, executor, hosting_assertion, targets}
```

In git_objects mode `--bundle-dir` is required; normalized_text mode forbids it.
The mode enum is the indicated exact string. Normalized `targets` contains every
requested path once in the same order, with one of these closed records:

```text
present: {path, status: "present", locator, text}
other:   {path, status: "missing"|"inaccessible"|"unavailable", locator, reason}
```

For other outcomes, locator is null or an exact permitted URL for that path and
reason is one of `host_reported_missing`, `permission_denied`, `not_returned`,
`capability_unavailable`, `request_failed`, matching status as follows: missing
requires host_reported_missing; inaccessible requires permission_denied;
unavailable permits the other three. No arbitrary error text is saved as reason.
Present locator is required. Text is exact str, already LF-oriented strict source
text under the existing code text control/BOM rules, and its UTF-8 byte count
fits max_inline_normalized_bytes. CRLF and bare CR in this already-normalized
branch refuse; no raw-byte identity or Git proof is inferred from the text.
Empty present text is permitted and has the existing zero-line metadata.

## Six saved data records

`code-proof-request.data` is exactly:

```text
{paper_id, source_association, repository, object_format, commit_oid, targets,
 require_repository_assertion, limits, profile_sha256}
```

Profile hash is SHA-256 of the exact retained installed profile bytes. Request
identity is batch-independent; the output location remains a separate local
transport property. Request preparation returns request ref and host targets.

`code-git-bundle.data` is exactly the R2 record:

```text
{request, object_format, repository, commit_oid, root_tree_oid, objects}
```

`request` is Ref(code-proof-request). Objects are the Git kernel's exact sorted
five-field declarations, with exactly one commit and matching full-width OIDs.
The input manifest is a canonical saved envelope. Its output bundle copy is
byte-identical, not reinterpreted as an ordinary JSON input.

`code-acquisition-intent.data` is:

```text
{request, mode, acquisition, bundle}
```

`acquisition` is the complete validated ordinary observe input, including its
mode, all normalized text when applicable, executor, time and hosting assertion.
The top-level mode equals acquisition.mode. `bundle` is null in normalized mode;
in raw mode it is `{directory, reference}`, with the exact canonical checkout-
relative input directory and Ref(code-git-bundle). This transitively binds every
raw body before the first install; do not replace it with a lexical folder hash.

`code-proof-observation.data` is:

```text
{request, intent, bundle, mode, git_proof, targets, capabilities, eligibility}
```

Refs have their exact corresponding kinds. Bundle and git_proof are null only
in normalized mode. Raw git_proof is the complete exact Git kernel result;
its limits, target flags and body inventory come from the retained request and
bundle. Recompute it from stored bytes for every completed-state command.
Targets contains every requested path once, in request order, with closed rows:

```text
{path, status, reason, text}
```

Raw status is `source_text`, `unsupported_source_bytes`, `missing`, or `unsafe`.
Source_text has reason=null and TextMetadata from the exact proved regular blob.
Unsupported_source_bytes has reason=`unsupported_source_bytes` and text=null;
the object proof and raw body remain valid. Missing/unsafe copy the corresponding
Git proof reason and have text=null. Normalized status is `normalized_text`,
`host_missing`, `host_inaccessible`, or `host_unavailable`. Normalized_text has
reason=null and TextMetadata from its retained supplied LF text; the other
statuses retain the acquisition reason and have text=null. Observation does not
duplicate the inline normalized source stored in intent.

Capabilities is `{git_objects_verified, raw_bytes_retained,
repository_assertion, source_association_verified}`. The first two booleans are
true only in raw mode; raw_bytes_retained means the complete consumed body set,
not that every requested target was a regular file. Repository_assertion is
`host_asserted` iff acquisition.hosting_assertion is non-null, else `unverified`.
Source_association_verified is always false at CODE-PROOF phase 1.

Eligibility is `{complete_target_set, repository_requirement_met,
source_handoff_eligible}`. Complete_target_set is true only for raw mode when
every requested target is source_text. Repository_requirement_met is true when
the request does not require hosting assertion or one is retained. Handoff
eligibility is the conjunction of these two. A normalized observation always
has false complete_target_set and false source_handoff_eligible.

R5's complete observation means the final saved acquisition result and all its
dependencies are present. It does not mean that every target is eligible. A
completed raw observation containing missing/unsafe/unsupported targets is valid
and useful evidence; handoff refuses the complete set and names the blockers.
Do not reinterpret that valid saved result as an interrupted acquisition.

`code-config-evidence.data` is:

```text
{request, observation, bundle, path, object_format, blob_oid, raw_body,
 format, result, source_only_reason}
```

Raw_body is R4's `{path, size_bytes, sha256}` canonical stored body reference.
All refs/origin/body bytes bind the same requested path and verified blob.
The observation must be complete raw and this target must be source_text with
configuration among its roles. Other requested targets may be ineligible: their
state does not remove proof for this selected configuration path. Repository
assertion does not gate literal config evidence, only complete-set handoff.

Format is json, toml or source-only. Json/toml result is the exact complete
configuration-kernel output for that format and request.config limits, and
source_only_reason=null. A parser refusal returns its error and installs no config
artifact. Explicit source-only does not invoke the typed parser: result=null
and source_only_reason=`explicit_source_only`. It still requires retained strict
source bytes and the configuration role. Unsupported binary input does not
become a source-text configuration artifact. Existing typed/source-only choices
for the same path are immutable; requesting a different format conflicts.

`code-source-handoff.data` is:

```text
{successor_only, request, observation, bundle, paper_id, source_association,
 repository, object_format, commit_oid, root_tree_oid, path, roles,
 allow_executable_source, blob, raw_body, text, proof,
 repository_assertion, source_association_verified}
```

Successor_only=true. Blob is the Git kernel's four-field blob metadata. Proof is
the exact corresponding successful kernel target result, including path/walk/
stopped_at/blob. Text is the matching TextMetadata. Source_association is the
unchanged request association ref or null, and source_association_verified=false.
Repository_assertion is the observation capability string. Handoff requires the
whole observation's source_handoff_eligible=true and emits one per requested path.

Handoffs deliberately contain no optional config reference. Configuration may
be derived after a handoff without changing its immutable identity. A successor
joins a config by its exact request/observation/bundle/path/blob/raw-body bindings
when needed. This is an explicit amendment of R3's optional-config-ref suggestion,
preventing derivation order from silently changing a path's fixed handoff bytes.
There is no claim that a config value is used by execution, or that these proposed
sources have been admitted, captured, licensed, reviewed or published.

## Public status and command behavior

All five leaves use the existing CLI JSON success/error envelope. The new data
payloads contain only the closed fields below. Returned output paths are canonical
checkout-relative paths to actual retained/installed files; no absolute host paths
are needed. Fixed word tokens are API states, not invented scientific conclusions.

Request returns `{batch_id, request, already_staged, acquisition_targets}`.
Acquisition targets are ordered `{path, github_url, raw_url}` rows for every
request target. Hash/Git acquisition requirements come from the saved request
and the documented bundle input profile, not from executable shell strings.

Observe returns `{batch_id, observation, status}` with the new Ref and the same
status payload as a subsequent read-only status call. Config returns
`{batch_id, path, config, stored_path, already_staged}`. Handoff returns
`{batch_id, handoffs}`, where each ordered row is
`{path, handoff, stored_path, source_body_path, already_staged}`.

Status data is:

```text
{batch_id, state, request, intent, bundle, observation, mode,
 missing, targets, capabilities, eligibility, configs, handoffs, next_action}
```

State is `empty`, `requested`, `pending_normalized`, `pending_raw_bundle`,
`pending_raw_bodies`, or `observed`. Refs are null exactly when absent. Mode is
null before intent. Empty means absent/empty namespace with no request and all
other files/families forbidden; it creates nothing. Requested means request only.
Pending states follow R5's exact dependency/prefix rules. Pending_raw_bodies also
covers all bodies present with only observation absent. A missing required prior
dependency under a saved observation is corrupt and returns an error, never one
of these successful states.

Missing is an ordered list of relative output filenames still required at that
stage: requested uses `["intent.json"]`; pending_normalized uses
`["observation.json"]`; pending_raw_bundle uses
`["bundle.json", "observation.json"]`; pending_raw_bodies lists missing OID-sorted
`objects/<oid>.body` then `observation.json`. Empty and observed use []. Before
the stored bundle exists, no missing object inventory is fabricated.

Before observation, targets is the requested path list as `{path, status:
"unobserved", reason:null, text:null}` rows, or [] for empty. Capabilities and
eligibility are null until an observation is present; even an intent's assertion
does not invent a completed proof. Observed status uses its exact validated
targets/capabilities/eligibility. Configs and handoffs are ordered
`{path, reference, stored_path}` rows for actual validated derived files, otherwise
[]. Each must equal a fresh derivation; a valid ce1 hash alone is insufficient.

Next_action is `prepare_request` for empty, `supply_observation` for requested,
`resume_same_observation` for any pending state, `prepare_source_handoff` for an
eligible observed batch with an incomplete handoff family, `successor_capture`
for an eligible observed batch with its complete handoff family, and
`new_request_or_acquisition_required` for ineligible observed evidence. This last
token does not discard its evidence or prevent configuration of an individually
eligible raw target. Status never repairs or creates files.

Handoff preflights all per-target derived bytes and caps before its first write,
then installs missing path-sorted files, reusing only initial identical files.
A prefix interrupted by a failure remains verifiable and repeatable. Configs
may be derived in any command order; their initial valid subset is not required
to be a path prefix. Each already saved config retains its originally selected
format. Every retained artifact must pass exact dependency and derivation replay.

## Errors, schema resources and remaining freeze work

Keep both kernels' closed errors and R6's I/O codes unchanged. Public semantic
errors add `CODE_PROOF_JSON_INVALID`, `CODE_PROOF_DOCUMENT_INVALID`,
`CODE_PROOF_BINDING_MISMATCH`, `CODE_PROOF_STATE_INVALID`,
`CODE_PROOF_NOT_READY`, and `CODE_PROOF_TARGET_INELIGIBLE`, all exit code 2.
Details contain bounded metadata pointers and fixed reason enums; parser raw
messages, code text, arbitrary repr and local absolute paths never leak through.
NOT_READY covers a valid state without required completed proof; TARGET_INELIGIBLE
covers a valid observed target/set that lacks required source/role/host capability.
Malformed stored identity/dependency state uses the specific document/binding/
state error, not an ordinary NOT_READY outcome. R6 lineage precedence applies to
all public errors. Exact reason enums and CLI help text are freeze deliverables.

Schema files are new `schemas/video-paper-wiki.<kind>.v1.schema.json` for all six
kinds, plus `code-proof-common`, `code-proof-request-input`,
`code-proof-observe-input`, and `code-proof-command-result` under the same naming
pattern. New $ids use `https://video-paper-wiki.dev/schemas/<filename>` and titles
use `video-paper-wiki.<kind>.v1`, with Draft 2020-12. No legacy schema changes.
The profile is `src/video_paper_wiki/profiles/code-proof-v1.json`, included by the
existing package rule; root schemas retain the existing wheel force-include.
The common schema must be self-contained for CODE values and both kernel result
shapes, with no undeclared external resource dependency or remote retrieval.

Pure validation must use the exact strict integer checker, preflight string and
container bounds before canonicalization, and separately verify byte budgets,
cross-references, target ordering, OID width, document IDs and derived equality.
The resource freeze binds all ten schema bytes and the profile after generation
and independent check. In source layout, schema origin is the sibling checkout
schemas directory tied to the imported package; in installed layout it is the
package schemas directory. Profile origin is always the imported package profiles
directory. Neither mode consults CWD resources or silently switches origin after
a missing/changed file. Retain the selected exact origins through the R6 session.

Before dispatch: independently review these choices, generate and inspect the
actual schemas/profile and positive/negative examples, freeze hashes, close the
error detail table, and bind production/test/resource paths. Test normalized and
raw observations, incomplete eligibility, arbitrary config derivation order,
handoff-before-config identity stability, every R5 interruption state, resealed
forged derivations and installed-wheel schema/resource parity. An actual bounded
public-repository acquisition remains separate from synthetic fixture proof.
