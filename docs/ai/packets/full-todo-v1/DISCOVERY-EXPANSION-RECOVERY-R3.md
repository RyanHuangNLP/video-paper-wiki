# Discovery R3 recovery and ordering decisions

Design-only amendment to DISCOVERY-EXPANSION-DESIGN-R2.md.
It resolves the independent R2 IO findings before a complete contract freeze.
The R2 review and text remain immutable. Where this amendment conflicts, these
rules prevail. Provider target notes remain a separate design input.

## One observed serialization boundary

Every discovery command acquires a non-blocking exclusive flock on the retained
checkout-root directory descriptor BEFORE observing or creating .work/research.
Hold it through initial discovery, all graph/input/resource validation, every
install, final named-edge/complete-set verification and descriptor cleanup.
Never hold it during Web execution: external reads occur between CLI calls.
Every discovery reader and writer uses this same boundary; another process or
thread gets DISCOVERY_BUSY (exit75) without creating .work or changing artifacts.
This is a process protocol for cooperative discovery commands, not an OS access
permission boundary. Uncooperative filesystem mutations remain covered by
retained named-edge/set/byte checks and WORK_PATH_UNSAFE precedence.

No lock file, lease timestamp, stale-lock deletion or PID file is written.
OS descriptor close/process exit releases the lock. The current local macOS
feasibility check opened a temporary directory, held LOCK_EX|LOCK_NB, observed
a second Python process get BlockingIOError, then observed acquisition after
release. Linux/macOS subprocess acceptance must verify this in the product;
do not infer a Linux result from the local test.

Acquiring the checkout root requires its retained no-follow ancestor chain
and actual checkout identity; no path.resolve normalization that hides caller
aliases. Holding an fd for a directory that has been renamed is insufficient:
the named checkout/.work/research/session/family edges are still re-opened and
compared on every exit. A busy acquisition does no store scan or store writes,
but still verifies whatever named ancestors it already reached.

## Initialization is fully reconstructable

research-config.data now INCLUDES the exact canonical seeds alongside question,
terms,lenses,limits,ranking,stopping. research-session.data is only
{session_key,config}. All downstream seed access resolves session.config.
This replaces the R2 config-without-seeds/session-with-seeds split.
A config-only tree contains all input facts needed to compute the one expected
session. Different input seeds necessarily have different config bytes.

Under the shared lock:
- No store/only empty known directories: status=absent. init installs config
  then session using its supplied canonical input. Plain resume does nothing.
- Exactly one valid config and no session or any other artifact: init_pending.
  init requires identical config bytes and derives the session. resume can derive
  the same session from retained config and directory session_key.
- Exactly one valid matching config/session: session_ready or the graph's later
  state. init with identical input is a read-only idempotent result.
- Session without config, more than one config/session, a wrong config ref,
  a foreign artifact before session or changed init input: integrity/conflict
  refusal. Never reconstruct missing stored inputs or select by timestamp.
- Any unsafe named edge wins over the normal semantic classification.

## Controls are separate from calculated stops

The calculated research-stop-decision no longer stores control_head or
user_stop. Its four reasons are budget_exhausted,paths_covered,duplicate_ratio,
yield_below_threshold in that precedence. The effective status overlays active
user_stop before these reasons. This avoids a stored stop projection becoming
unreproducible after an explicit stop/resume while projections are pending.

Plan keeps its historical control_head. Final round event ADDS control_head,
the actual current control head observed while holding the shared lock at event
install. Plan.control_head must be an ancestor (or equal) of event.control_head.
Stop/assessment/candidate/rank bytes depend only on their complete observations,
config and actual supplied assessment; they never change because controls advance.
After stop then explicit resume, a pending exact projection set can finish
without discarding old artifacts or changing a sealed plan.
The effective response includes user_stop among matched reasons where active;
it never claims that the historical calculated artifact contains that reason.

Control stream order is sequence=1..N and exact previous ref, never timestamp
sorting. User recorded_at must be >= previous recorded_at; equality is allowed
and sequence is authoritative. Global event_id is unique across both control
and candidate-decision streams. Repeating an existing event_id is idempotent
only when every user/action/target field is exactly identical, including time;
a different repeat refuses. The caller supplies recorded_at; no hidden clock.

user_stop is allowed in any initialized state, including a pending plan or a
calculated stop. A second new user_stop while already stopped refuses as a
redundant control; exact same-event retry still reuses. resume is allowed only
when the effective latest control is user_stop. It clears that overlay only;
calculated stopping and immutable budgets still apply. The control.round must
equal the last complete event at control installation (null before first event).
No user control targets an incomplete event. Status validates the whole chain.

The shared lock gives a concrete ordering: if a control command installs first,
later observe/finish sees it; if finish installs its event first, a later control
must refer to that new completed event. A direct foreign control appearing in
the held snapshot is WORK_PATH_UNSAFE/conflict, never a successful stale finish.
Verify the complete decisions set after every install and at final exit.
For historical validation, control.round sequence must be nondecreasing and
each event.control_head is the last control in its preceding-round group.
Controls referencing that event belong to the following group. This checks the
interleaving without filesystem mtime or unstated wall-clock order.

## Exact memberships, hashes and pending subsets

All set ordering uses canonicalize(value) byte ordering (UTF-8 JCS). Refs are
sorted by these bytes and unique. request_specs are sorted by request_key; slot
is the zero-based array index and is repeated in requests, not hashed into the
spec key. Add request.slot to the R2 fields. Recompute spec key as
SHA256(b"rw3/request-spec-v1\0" + JCS(spec without request_key)).
It excludes plan/session/sequence, which the enclosing request/plan bind.
A plan cannot repeat the same key. Retry and continuation facts create distinct
spec keys. No ad hoc slot, sequence or arbitrary target chooses membership.

Every request maps to exactly one plan slot and has byte-identical committed
spec, key, regenerated target, plan_id, sequence and session. Missing expected
requests are pending; any other request is conflict. Observations must refer
to an installed exact request, <=1 terminal observation per slot. A missing
terminal object is pending, including after an invalid observation-input attempt.
success,partial,timeout,rate_limited,capability_unavailable,failure are terminal.
A not-found executor result is failure with code=not_found; no extra enum.

The complete cumulative observation set consists of ALL terminal refs in prior
completed rounds plus every terminal ref for the current plan. No derived refs,
plan ref, hidden pending object or controls are included.
input_set_sha256=SHA256(JCS(sorted complete refs)), with [] valid only for the
initial context/status before any terminal work. A finished nonempty plan may
have failed/empty observations but always has at least one terminal ref.
Assessment.observations and candidate-set.observations equal this full set.
The rank/stop inherit the identical digest through their exact child refs.
Lens evidence citations are a subset (possibly equal), with excerpt hash over
the exact Unicode-codepoint substring encoded as UTF-8. Config lens names/scope
must exactly agree. Failures stay in context even when another cited result
provisionally covers the lens; health and assessment are reported separately.

After all slots are terminal, there is at most one supplied valid assessment per
plan. It is a caller-authored semantic input, so membership is its exact ref and
validated complete input binding, not an invented deterministic model response.
Candidate set is deterministic from all observations; rank deterministic from
candidate set/config; stop deterministic from assessment/candidates/rank/history.
Event contains exactly the sorted current requests/observations and those four
child refs, with no extra current or orphan children. Every partial projection
must equal its deterministic expected bytes; unrelated or alternative files
refuse. A pending valid subset never authorizes a successor. Every event present
requires its entire child set present. Recompute historical events in order.
Active-ancestry checks run before memo-cache reuse.

## Budget and capacity formulas

Plan reservation_after contains only
{rounds_planned,request_slots_reserved,observation_slots_reserved,retry_slots}.
At plan installation, rounds_planned=count(plans in prefix including this plan).
Both slot totals=sum(len(plan.request_specs)); retry_slots counts specs with
retry nonnull. A plan atomically reserves every slot for both request and terminal
observation, before materializing any request file. Enforce all configured limits
then; no future child omission frees capacity.

Event budget_after fields:
rounds_planned,rounds_completed,request_slots_reserved,requests_materialized,
pending_request_files,observation_slots_reserved,terminal_observations,
pending_observations,retry_slots,result_records,normalized_payload_bytes,
candidate_slots_reserved,current_candidate_components.
Compute from the event's complete plan/request/observation prefix, including
this event as one round_completed. pending_request_files=reserved-materialized;
pending_observations=reserved-terminal. Both are zero at a complete event.
Result count sums len(payload.results) for nonnull payloads.
Normalized payload bytes sum len(JCS(payload)) for nonnull payloads, including
partial data. Failure objects do not invent payload bytes but DO count as stored
observation bytes. Invalid input with no installed artifact is not a terminal
outcome and leaves its reserved slot pending. Idempotent exact reuse adds zero.
No round/request/observation/retry reservation is refunded.

Candidate budget is cumulative component introductions, not changed hash labels:
for each completed/pending-ready round, build its full identity graph; count
new components whose identifier set is disjoint from ALL earlier identifiers.
Sum that count as candidate_slots_reserved. A bridge merging prior components
does not refund their earlier slots; new aliases joining an existing component
do not consume another slot. At first round every component is introduced.
Each current snapshot has <=256 components and reserved candidate slots<=256.
Historical snapshots/keys remain immutable even when an explicit same_work fact
changes a current component key. Set bytes always derive from the complete graph.
Do not assert a literal union of earlier candidate keys, since alias joining can
change a key without creating a new work. All conflicting components count.

Physical capacities: requests/observations/metadata/proposals <=256 saved files
each; decisions <=512 saved files. Semantic decisions caps: at most256 candidate
decisions,64 controls,8 assessments, hence <=328 decisions-family files, leaving
headroom without claiming unlimited changes. Plans reserve one assessment slot.
Controls/candidate decisions cannot consume reserved assessment capacity.
Per-family saved bytes <=32MiB; total store <=64MiB. Exact stored bytes include
all regular artifact files, including control/events, and exclude directory
metadata/OS descriptors. Unsafe special/unexpected entries refuse, not count.
These physical counters are read-only status results and pre-install checks,
not part of event budget_after (avoids self-reference and later-control changes).

Preflight prospective payload/result, candidate graph, file count and exact
saved-byte limits BEFORE an observation install, so a retained valid outcome
cannot strand finalization solely by already exceeding semantic limits.
Also estimate the deterministic projection upper-bound plus max assessment and
event envelopes against remaining physical space before accepting each plan.
The complete contract must fix an explicit conservative reserve in bytes;
if reservation cannot fit, refuse the plan before external work.
Space reservations are released into actual saved-byte usage on finalization;
semantic request slots never refund. Cap errors never delete stored evidence.

## State/action matrix

Conflict or unsafe anywhere refuses every command after final verification.
Read-only status/context/render/handoff/inspection are always non-creating.
Current effective user stop has priority over the base state below.

| Base state | init | plan | observe | finish | plain resume |
| --- | --- | --- | --- | --- | --- |
| absent | create config+session | refuse | refuse | refuse | report absent |
| init_pending | exact session repair | refuse | refuse | refuse | exact session repair |
| session_ready | exact reuse | create next plan or needs_scope | refuse | refuse | report ready |
| plan_pending_requests | exact reuse | repair exact requests | materialize none; supplied request must exist | report pending | repair exact requests |
| plan_pending_observations | exact reuse | same plan/no new slot | install one terminal outcome | report pending | report pending |
| assessment_required | exact reuse | same plan/no successor | exact existing retry only | validate/install assessment+projections/event | report assessment_required |
| projection_pending | exact reuse | same plan/no successor | exact existing retry only | exact supplied-assessment retry and repair | repair deterministic projections/event |
| complete_continue | exact reuse | next plan or needs_scope | no old new outcome | exact completed replay only | report complete |
| calculated_stopped | exact reuse | refuse | refuse | exact completed replay only | report stopped |
| needs_scope | exact reuse | explicit valid bounded plan or report needs_scope | refuse | refuse | report needs_scope |

When user_stopped is effective, all mutating init/plan/observe/finish/plain-resume
actions are blocked; they may report state without installing even deterministic
children. Only an explicit control.resume (or exact idempotent prior control
retry) can advance. Candidate decisions remain allowed on previously complete
rounds because explicit reviewing/choosing an already observed candidate is not
issuing external research; handoff stays data-only. A calculated stop similarly
does not prevent reviewing completed candidates.

The operation's JSON payload names base_state,effective_state,control_head,
last_complete_round,pending_plan,missing_requests,missing_observations,
assessment_required and remaining budgets. Mutation functions may return normal
pending status where the table says report; invalid state-changing attempts
return DISCOVERY_PENDING/STOPPED structured refusals. DISCOVERY_BUSY is new.
No automatic plan creation, external execution or invented assessment occurs
inside resume. No closure of scientific/human gates follows from this design.

