# CODE proof public closure — R9 candidate

Architect supplement to R7/R8, answering the R7 public-wire review and the R8
mkdir exception finding. Existing candidates, reviews and rejected evidence stay
unchanged. This is still design material. Actual schemas/profile bytes, their
independent check, the exact source freeze and implementation remain required.

## Repository and handoff family choices

Restore both repository components to `[A-Za-z0-9._-]{1,100}`. Exclude exact `.`
and `..`, and exclude a case-insensitive `.git` suffix from the repository name.
Saved spelling is lowercase; ordinary request preparation only lowercases case.
Leading dot, underscore and hyphen remain allowed, including `owner/.github`.
This bounds locators without claiming that GitHub accepts or owns every matching
name. Apply the same saved spelling to request, bundle and hosting assertions.
R7's alphanumeric-first restriction is superseded.

The handoffs family must be exactly a prefix of requested paths in path order,
including the empty prefix. Every present member must also pass exact saved-ID,
reference/body binding and fresh derivation equality. An initial non-prefix
subset is STATE_INVALID with reason=nonprefix_handoffs and is never filled in or
adopted. The command produces the missing suffix in path order, with initial
identical-file reuse only. A late appearance still refuses as lineage failure.
Status lists the actual validated prefix and selects prepare_source_handoff
until it is complete. Its `missing` list retains R7's acquisition-dependency
meaning; it does not mix optional derived files into that list.

Configs remain an arbitrary individually validated subset because users request
one path at a time. Raw objects retain R5's distinct OID-sorted prefix rule.
Source-handoff eligibility applies to the whole requested target set and any
required hosting assertion, irrespective of the current derived family sizes.

## Serialization preflight and refusal ordering

For request, cap the ordinary input bytes before JSON decoding. Then validate
the complete request and materialize its profile/limits, seal the request and
check its actual saved bytes. For observe, cap the ordinary input bytes before
decoding; validate all acquisition fields and per-target normalized bytes or the
entire raw bundle/inventory/proof. Complete pure derivation, seal both the intent
and observation, and check their complete saved-byte caps before the first new
intent write. Raw bundle copy and every body must already be validated too.

Within this preflight, the fixed raw input cap takes precedence over decoding
and any per-target interpretation. Per-target inline limits are checked before
constructing sealed intent/observation bytes. Saved intent is checked before
saved observation. No new aggregate normalized-text limit is invented: the
per-target cap, input cap and actual serialized intent cap are separate required
checks. Valid per-target text can still cause a deterministic saved-cap refusal.
R6/R8 final lineage precedence continues to apply to each refusal.

Configuration produces its whole pure result and saved envelope and checks its
actual saved size before installation. Handoff computes and checks every complete
path-sorted saved envelope before its first write. Raw-proof fields, typed nodes,
source metadata or references are never dropped to make an envelope fit.

Before writing any planned output, also simulate the entire deterministic install
sequence from the current retained logical byte count C. Reused initial identical
files add zero; for each missing payload of N bytes, require C+2*N within the
lowered peak cap, then set prospective C=C+N for the next missing file. Include
all retained files, including optional existing config/handoff files, in initial
C. Every prospective step must pass before the first new install. Repeat the
same actual-phase check immediately before each temporary creation. This avoids
writing a prefix merely to discover a predictable saved/peak limit failure later;
unexpected I/O/lineage failures may still leave the verified prefixes described
by R5/R8.

Serialization or peak refusal uses CODE_PROOF_LIMIT_EXCEEDED with exactly
`{instance_pointer, limit_name, limit, observed}`. Limit_name is the corresponding
materialized key, e.g. max_intent_bytes, max_observation_bytes,
max_config_document_bytes, max_handoff_bytes, or max_output_peak_bytes. Pointers
are respectively `/intent`, `/observation`, `/config`, `/handoffs/<index>`, or
`/output`; indices are bounded plan positions, never arbitrary source keys.
Observed is the actual serialized or simulated logical peak byte count. The
fixed ordinary-input limits use max_request_input_bytes and max_observe_input_bytes
with pointer `/input`. Limit values and observed counts are strict integers.

The separate Architect structural-bound calculation is
`architect-serialized-bounds-r2.py` and its JSON result under the kernel evidence
directory. It constructs independent field-width upper bounds, not hash-valid
Git data: up to 2048 object records/consumed OIDs, 32 targets, 32 walk edges per
target, aggregate matched-name hex length at most twice its 512-byte path, and
maximal SHA-256 widths. The resulting bounds are:

| R7 data | Conservative canonical byte bound |
| --- | ---: |
| Git proof object | 1014633 |
| Raw saved observation including LF | 1041187 |
| One saved handoff including LF | 12910 |

These are below the default saved caps. They do not exempt lowered request caps
from actual preflight checks. They also do not bound normalized intent/config
serialization, whose actual saved bytes remain independently capped. The R1
calculation underestimated handoff DOI escaping and remains historical; R2
conservatively doubles all 512 possible ASCII paper-ID bytes for JSON escaping.
The R2 shape is intentionally not a valid fixture or evidence of a real Git
repository. Independent review must verify the field-width premises and bound.

Required tests include ordinary-input cap boundaries; 32 escaped LF/backslash
text targets; intent/observation/config/handoff saved lengths at cap-1, cap and
cap+1; lowered caps below a valid generated result; and a later planned file
whose peak would exceed the cap. Every preflight refusal must leave all initial
output bytes and directory states unchanged.

## mkdir and post-create observation failures

Add these rows to R8's post-effect matrix:

| Observed event | Required result |
| --- | --- |
| mkdir raises and the first-absent name remains absent | Preserve the operation I/O error, subject to final lineage verification. |
| mkdir raises and that name is present | Unverified late arrival; WORK_PATH_UNSAFE. Never adopt or delete the entry, even if it is an empty 0700 directory. |
| mkdir returns success but post-create stat/open fails before a descriptor and named identity are verified | Creation ownership is not established. Preserve the operation error and perform final checks; a present/mismatching unverified edge is a lineage refusal. Never delete or adopt it. |
| Creation has a verified named identity/descriptor, but its parent fsync fails | Retain that authorized empty directory, report I/O error, and perform final verification/descriptor cleanup. |
| A later check observes replacement/removal of an authorized new directory | WORK_PATH_UNSAFE; do not delete the replacement or re-create the missing path. |

The first captured post-mkdir identity remains the observation boundary stated
in R6. This matrix does not claim that portable mkdir returns an inode or detect
an unobserved replacement before its first capture. Test both a syscall wrapper
that creates then raises and post-mkdir stat/open failures, with the old inode
kept live when a distinct replacement is required by the test.

## Closed public semantic error contexts

Both pure kernels keep their frozen codes and structured contexts. Their R1/R2
contracts permit bounded fixed reason wording for some conditions; this public
supplement does not retrofit a new reason enum into those pure APIs. Saved Git
target reasons and normalized acquisition reasons are already closed by R1/R7.
Public orchestration may propagate a kernel error's code/details unchanged; the
resource/schema freeze must express those actual existing context shapes without
changing kernel behavior to fit an invented enum.

The six new public semantic codes have details exactly
`{instance_pointer, reason}`, except TARGET_INELIGIBLE as specified below.
Pointers use only known schema fields and bounded numeric array positions, with
at most 1024 characters. An unknown object key is reported at its parent pointer,
never echoed as a new pointer component. Reason choices are:

| Code | Reason enum |
| --- | --- |
| CODE_PROOF_JSON_INVALID | utf8, bom, duplicate_key, float, nonfinite, integer_range, depth, syntax, trailing, surrogate |
| CODE_PROOF_DOCUMENT_INVALID | shape, type, string_bound, integer_bound, enum, noncanonical_text, repository, path, target_order, role_permission, limits, datetime, identity, canonical_bytes |
| CODE_PROOF_BINDING_MISMATCH | reference_kind, reference_hash, request, repository, object_format, commit_oid, root_tree_oid, path, blob, raw_body, profile, derived |
| CODE_PROOF_STATE_INVALID | missing_dependency, forbidden_slot, forbidden_family, nonprefix_objects, nonprefix_handoffs, orphan_derived |
| CODE_PROOF_NOT_READY | request_absent, observation_incomplete, raw_evidence_required |
| CODE_PROOF_TARGET_INELIGIBLE | path_not_requested, missing, unsafe, unsupported_source_bytes, configuration_role_required, repository_assertion_required, complete_target_set_required |

TARGET_INELIGIBLE details are `{instance_pointer, reason, blockers}`. Blockers is
a path-sorted list of at most 32 closed `{path, status, reason}` rows derived from
the actual retained request/observation, with no source text. Only requested
logical paths may appear. Missing/unsafe/unsupported per-target blockers carry
their existing saved target status/reason. A selected target missing its
configuration role uses status=source_text and reason=configuration_role_required.
An unknown requested selector or missing whole-set host assertion uses an empty
blocker list rather than echoing an unbound path or inventing a target outcome.

A handoff with invalid complete_target_set returns complete_target_set_required
and all non-source-text blockers. If the target set is complete but hosting is
required and unverified, return repository_assertion_required with no blockers.
Config checks the selected raw source/role, never whole-set handoff eligibility.
Valid incomplete acquisition uses NOT_READY; corrupted dependencies or illegal
family states use STATE_INVALID. A normalized observation requesting raw-only
config/handoff uses NOT_READY/raw_evidence_required.

CODE_PROOF_CONFLICT details are exactly `{instance_pointer, reason}`, with reason
request_changed, acquisition_changed, config_format_changed or artifact_changed.
They denote stable initially retained disagreement. A changed named edge/bytes
after the initial observation is a lineage refusal, even if it would otherwise
look like an ordinary conflict. Existing resealed forged derivations use
BINDING_MISMATCH/derived before any install reuse check.

I/O messages/details follow R8. Extend its bounded reason enum by path_spelling,
overlap, unknown_entry, batch_id, marker_invalid, resource_hash, resource_shape
and resource_origin, covering initial path/layout/authority/resource refusals.
An unknown directory entry is WORK_PATH_UNSAFE/unknown_entry; a known but
mode-forbidden family is STATE_INVALID/forbidden_family. Errno/prior_errno are
null or integers in 0..65535. No raw operating-system or parser error text is
forwarded. Under a replaced/uncheckable retained lineage, the final WORK_PATH_UNSAFE
still overrides every error above.

The public CLI error envelope remains the existing one. The new command-result
schema closes successful data payloads; it must not redefine an incompatible
outer error envelope or change a legacy command's behavior. Tests assert the new
context shapes and meaningful ordering above; independent unrelated-invalid
field precedence is not an extra contract beyond the explicitly specified
validation/limit/lineage rules.

The next freeze must include generated ten-schema/profile bytes, exact resource
and source origins, strict-integer/no-external-ref schema validation, positive and
negative wire fixtures, and the final public implementation allowlist. None of
these missing artifacts is implied by this design review packet.
