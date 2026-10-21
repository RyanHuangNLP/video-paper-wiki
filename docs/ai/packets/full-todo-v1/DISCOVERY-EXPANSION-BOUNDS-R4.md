# Discovery physical reservation and scheduling R4

Design amendment for freeze review; read with R2 design, R3 recovery decisions
and the provider target notes. This closes the remaining numeric reservation
decision and specifies a bounded default schedule. It is not source acceptance.

## Serialized size limits

Every limit below applies to COMPLETE UTF-8 JCS envelope bytes INCLUDING its one
LF, not just data fields. Ref length and schema/kind names are therefore included.

| Artifact kind | Maximum saved bytes |
| --- | ---: |
| config, session, plan, request, round-event | 65536 each |
| discovery-observation | 1114112 each |
| research-assessment | 262144 |
| paper-candidate-set | 2097152 |
| paper-rank | 1048576 |
| research-stop-decision | 262144 |
| candidate-decision, research-control-event | 65536 each |

Observation payload alone is additionally bounded by config.payload_bytes<=1048576
JCS bytes. The extra 65536 covers observation envelope/executor/failure fields;
it is not a larger result payload allowance. Generic unsealed observation input
may be <=1114112 bytes, other input kinds use their exact envelope upper bound;
all still have strict depth/count/string limits before canonicalization.
Config and session already exist before a plan reserves work and count as actual
saved usage. Bootstrap preflights both exact config+session bytes together before
the first config install, and checks their family/total caps prospectively.

Assessment has exactly five lenses, <=8 evidence spans per lens, <=16384
characters per statement/reason, and remains <=262144 saved bytes.
Control/decision texts <=16384 characters with the 65536-byte bound also applied.
No input or output is silently truncated to fit. A validly encoded oversized
object refuses before installation. Evidence may be resubmitted in a bounded
explicit input, preserving its actual meaning and provenance.

## Per-plan byte reservation proof

Let N be the plan's committed request count, 1<=N<=8.
Reserve these family capacities BEFORE installing the plan:

requests: N*65536
observations: N*1114112
metadata: 131072 (one plan and one final event)
proposals: 3407872 (candidate-set + rank + stop)
decisions: 262144 (one assessment)

At N=8 their sum is 13238272 bytes (12.625 MiB).
In addition, reserve a conservative TOTAL capacity of 14680064 bytes (14 MiB)
for every pending plan, independent of N. This exceeds the sum above by
1441792 bytes at N=8. It does not reserve config/session again. At most one
pending plan is permitted, so reservations never overlap with another plan.
The metadata plan/event reservation excludes current directory metadata and
OS descriptors; no artifact embeds its own physical byte count.

Compute U_f as actual saved artifact bytes in family f that do NOT belong to
the pending plan; U=sum(U_f). A new plan is eligible only if:
U_f + R_f(N) <= 33554432 for EVERY family and
U + 14680064 <= 67108864.
Existing completed artifacts and every control/candidate decision are in U,
including those whose semantic target is an earlier round. File counts also
reserve N requests,N observations,2 metadata,3 proposals,1 assessment.
Family count caps remain 256 except decisions512; semantic256 choices+64
controls+8 assessments stay independently enforced.

While a plan is pending, actual files owned by it consume its reserved capacity.
Physical status reports both actual bytes and unspent reservation, using
U_f + max(R_f(N), actual_pending_f) and
U + max(14680064, actual_pending_total).
Every allowed pending object must pass its kind-size bound; therefore
actual_pending_f<=R_f(N), and actual_pending_total<=13238272<=14680064.
An out-of-reservation or unknown object is an integrity/limit refusal, never
adopted as useful progress.

Any control/candidate decision while a plan is pending is a non-reserved write:
preflight its exact prospective bytes/counts in U and require the same family
and total inequalities. It cannot consume capacity promised to finalization.
Every install recalculates using retained family sets under the shared lock;
exact idempotent reuse has zero incremental usage.
After installing and verifying the final event, the plan becomes complete;
all its files become actual U for future plans and its unused physical reserve
is released. This release is physical capacity bookkeeping only. No semantic
round/request/observation/retry/candidate slot reservation is refunded.

The advertised semantic maxima are independent upper bounds, not a promise that
all maximum-sized artifacts fit simultaneously. A completed session may stop
before its eighth round when the next whole plan reservation cannot fit.
Record budget_exhausted with the limiting family/total capacity; do not create
an empty plan or strand a partly materialized external request to test capacity.

## Semantic closure before observation install

For each prospective terminal observation, reconstruct the tentative cumulative
identity graph and its pending candidate-set projection using ALL accepted
observations plus this one, even if other slots remain pending.
Enforce current candidate components and introduction reservations<=256, the
candidate-set saved size<=2097152, and its deterministic rank<=1048576 before
installing that observation. Partial current inputs are used only for these
bounds, never stored as a completed candidate/rank or assessed coverage.
As remaining slots arrive, repeat the prospective check.

This prevents retained observations alone from exceeding the final projection
caps. A rejected oversized/malformed/identity-cap input leaves its request
pending; an explicit bounded terminal failure describing that actual
normalization refusal can be supplied instead. Never invent an external timeout
or capability result on its behalf. Stop and event have fixed small bounded
fields/counters; final size checks still run before their install.
Caller assessment remains an independent bounded input; an invalid assessment
does not erase observations or consume another request.

Before dispatchable plan creation, recompute full candidate and rank upper-bound
sizes for prior accepted inputs and require every already stored projection fits
these kind limits. If a legacy future incompatible schema cannot fit, refuse
before external work, not while committing a claimed complete event.

## Deterministic default frontier without starving citation paths

The R2 "all lens/seed/provider products before all neighborhoods" description is
replaced by the following bounded scheduling policy.

Base request families:
- lookup: one unresolved identifier lookup per original seed;
- references, citations, related: one eligible direct operation per original seed;
- topic: exactly two jobs per lens (one per provider), ten total, using the
  declared global question/lens scope. Assign seed_key cyclically in sorted seed
  order by lens index for OpenAlex and (lens index+1) for Web. All seed-specific
  provenance remains explicit; this is not every lens x seed x provider product;
- project: one Web query per seed with nonempty declared author/project terms.

Direct base jobs therefore number at most 3+9+10+3=25. Jobs whose required
identity/neighborhood is unavailable are pending-capability frontier entries,
not fabricated requests. A terminal failure marks that exact job attempted;
only an explicit retry can issue it again. A prior accepted observation may
enable formerly unavailable neighborhood jobs in a later plan.

Sort each available family by depth,seed_key,lens order,provider order,
canonical subject IDs,spec key. Fill each plan by repeated round-robin passes
over [lookup,references,citations,related,topic,project], taking one item from
each nonempty family per pass until per_round_requests or remaining slots is
reached. The same immutable history always yields the same plan.
When all direct eligible jobs have been attempted, add depth1 then depth2
neighborhood jobs for at most three highest-ranked unambiguous not-yet-expanded
candidate components from the last complete candidate set. The same family
round-robin policy applies. Bind the exact candidate-set/key origin.
Candidates without observed OpenAlex identity can use Web lookup; no invented
OpenAlex arXiv lookup or recursive URL traversal is created.

Request identity compares the canonical operation specification excluding
round/plan/slot metadata. Store each attempted spec key; duplicate base jobs are
suppressed regardless of which round first materialized them. An explicit retry
adds its predecessor observation/reason, so its key differs and gets a new slot.
Cursor continuation likewise binds an exact predecessor and next_cursor.
No default retry/cursor is generated. No direct job is suppressed merely because
a similarly titled result already exists; stable identifiers are authoritative.

An explicit plan must choose from the same validated eligible bounded frontier,
or be a separately validated continuation/retry of previous terminal work.
It cannot change question/lens scope, invent a seed/candidate, exceed depth,
repeat a plain attempted job or bypass configured reservations.
No valid available jobs yields needs_scope when required evidence is still
missing. Lack of capacity yields budget_exhausted. A prior calculated stop
takes precedence over creating any additional plan.

## Acceptance obligations

Prove the sum above programmatically; test N1 and N8 and exact family/total
limits. Fill unreserved decisions around a pending plan and show that assessment
and final event still fit. Interrupt every install edge and check that status
uses the entire outstanding reservation, then completes without lost capacity.
Test malformed/oversized input without stored debit, explicit local-normalization
failure outcome, partial outcomes and identity aliases changing component keys.
Test 3 seeds and both providers with enough observed IDs to make all six
families eligible; round-robin must actually issue citation/reference/related
jobs before the default 32-request cap and preserve byte-identical plans under
observation arrival permutations. These are future tests, not claimed passes.

