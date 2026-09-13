# Discovery final admission and selection decisions R7

This final amendment resolves the narrow R5/R6 independent review findings.
Read R2 design, R3 recovery, R4 bounds, R5 wire, R6 ranking and provider notes
with this amendment last. All earlier records stay unchanged. Implementation
and remote/local acceptance evidence are still required after contract freeze.

## Capacity and admission outcomes

If at least one prefix length N>=1 passes all declared checks, automatic planning
selects the largest such N and installs that plan. This outcome is not a pre-install
budget refusal. If eligible frontier entries exist but no N>=1 passes, return
budget_exhausted and install no plan or request. If no eligible frontier exists,
return needs_scope. These explicit cases replace the grammatically ambiguous
R5 sentence about no feasible prefix. Prior calculated/user stops keep precedence.

unique_candidates is a STRICT PER-OBSERVATION ADMISSION INVARIANT. A prospective
input that would exceed current components or completed charges plus pending
introductions is rejected before it becomes an observation. No unbounded or
provisional over-cap graph is retained. A later bridge cannot retroactively turn
that rejected input into an accepted one; the host may submit a new explicit
bounded input under the current state, or record the real normalization failure.
Observation order can affect which oversized inputs are admitted at this boundary.
Arrival-order byte identity is required for the same complete set of ADMITTED
observations when each tested arrival prefix satisfies the bound, not for refused
input attempts. A refused attempt has no hidden observation or candidate debit.
All permanent completed candidate and plan slot charges keep their no-refund rule.

Duplicate stopping uses inclusive comparison:
  total_hits > 0 and repeated_hits*100 >= duplicate_percent*total_hits.
The configured consecutive-round count must also be met. Equality qualifies;
zero hits never qualify. Low yield is new_relevant < min_new_relevant, also for
the configured consecutive completed rounds. An incomplete round never counts.

## When an expansion selection becomes durable

A frontier's ranked candidate choices are tentative. A component becomes a durable
expansion selection ONLY when a committed plan contains its first expanded spec
(subject_origin nonnull). That plan atomically retains its candidate-set/key,
subject_ids, seed_key and depth even when no request file has materialized.
Do not charge a tentative candidate with no executable eligible job, and do not
write an extra selection artifact. An unavailable candidate stays a visible
capability frontier entry; it is not described as selected or as a spent slot.
If capability is later evidenced, normal deterministic planning may then select
it from the current complete graph/rank and charge it through a real plan slot.
This is the chosen alternative to persisting selection of unavailable candidates.

Reconstruct selection history by replaying committed plans in sequence, then
request_specs in request_key order. Each first expanded component receives the
lineage {plan_sequence,request_key,origin,initial_ids,seed_key,depth}; this tuple
is retained in derived status, not an independently mutable record. Compare
an expanded subject with prior selected lineages through the identity graph
available BEFORE that plan. If it intersects any prior selected component,
reuse the earliest lineage. Otherwise it introduces one selection, subject to
a hard total of three. All specs for a newly selected component in that same
plan share the first lineage; their slot order cannot charge it repeatedly.

Later aliases or bridges can coalesce active selected components but never erase
or refund historical selection introductions. If two earlier selections merge,
both historical lineages remain charged and status lists both, grouped by the
current component. The earliest lineage supplies the current preferred origin.
A fourth distinct introduction is prohibited even if merges leave only two current
active groups. Exact plan retries/repairs consume no additional selection.

The original selection depth and seed are durable. An improved later why-found
path or bridge never produces a new selection, changes that original depth or
reissues a plain job. For already-attempted plain operation suppression, compare
provider,operation,seed_key,lens and subject identity intersection IGNORING depth.
Retain depth in the spec for provenance, depth<=2 validation and initial selection,
but a changed depth is not an exemption from duplicate-attempt refusal.
Initial selection depth is one plus minimum why-found request depth in its exact
origin snapshot, bounded by two; deeper components remain ineligible. Reusing a
selected lineage uses its original depth. A same component is never reselected
at a new depth. Distinct components can be selected at depth one or two as slots
permit. Future requests retain exact current candidate-set/key while the selection
history preserves the first origin; neither field is silently retargeted.

Only explicitly validated retry/cursor/neighbor-slice specs are exempt from plain
attempt suppression, and they still consume fresh plan slots. The predecessor,
base-field, outcome, cursor and unseen-ID rules in R6 apply in full. An arbitrary
changed origin, version, alias or depth does not create such an exemption.

## Implementation and integration scope

Root remains implementation owner under LOCAL-CODEX-OWNERSHIP-R2. The final
allowed-path manifest owns the new discovery modules, 13 discovery schema files,
one prompt, one provider resource, public CLI registration, documentation and
bounded contract/integration/security tests. Existing W1 preview schemas, core
source/capture/publication/catalog behavior, catalog67 and all protected local
material stay under their existing contracts.

The implementation checkout starts at the newly committed catalog revision,
which can still be awaiting remote CI. This parallel start is permitted because
DISCOVERY uses already accepted preview/identifier/staging interfaces; it does
not depend on an unreviewed change to SOURCE. Catalog source stays frozen during
its CI. Discovery edits live only in its separate clone and own allowed paths.
Any catalog CI repair is integrated serially by the Git owner with new source/hash
checks before Discovery delivery. No pending catalog head is relabelled accepted.
Discovery delivery and exact-head acceptance still require current integrated
source, both full local Python suites, installed resource/CLI checks and fresh
four-job CI against the exact head/base. This amendment authorizes no merge,
real Vault/admin execution or human scientific approval.

Final implementation choices within these closed rules may organize helpers and
private fields, but cannot change public artifact kinds, declared authority,
request budgets, graph memberships, stop/rank semantics or safety outcomes.
The committed public schemas must close every emitted object and be exercised
with actual saved artifacts and malformed nested alternatives. The provider
resource fixes both profile constants and target fields; package reads retain
its bytes and schema/prompt bytes through each command's final verification.
