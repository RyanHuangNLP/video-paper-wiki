# Bounded discovery continuation — design R2

Status: design for independent review, not a source-edit freeze. This supersedes
R1 design suggestions only. R1 and its independent review remain immutable.
Current catalog acceptance continues on its frozen R2 candidate. Root owns the
future implementation; existing assistants review and deliver serially.

## Result and boundary

One to three seeds and a research question produce an inspectable research
session containing executable host request descriptions, terminal observations,
candidate identity sets, reproducible ranks, cited coverage assessments, complete
round history and explicit stop/resume controls. This CLI is zero-egress.
The current conversation executes external reads through available Web/connector
tools and supplies normalized observations. No credentials, PDF, archive, model,
dataset or real Vault is accessed by Python. Formal admission is a later explicit
preview/source transaction. The seed catalog remains at 67.

Profiles are openalex-rest-normalized-v1 and platform-web-search-normalized-v1.
Neither asserts raw HTTP bytes, unseen headers, response status, authentication
mode or complete scholarly coverage. These transport fields remain unavailable.
A host unable to execute an operation supplies capability_unavailable; Python
never rewrites that as a successful empty page.

## Exact common representation proposed for freeze

All kinds use envelope {schema_version,kind,id,content_sha256,data}, with
schema_version equal to the kind's discovery namespace version string.
Content digest is SHA256(JCS({schema_version,kind,data})); id is
rw3:<kind>:<digest>. Saved bytes are JCS(full envelope) plus exactly one LF.
Refs are closed {id,sha256}, where sha256 hashes those saved bytes. Object keys
are unrestricted only in schemas explicitly naming their bounded map grammar.
Otherwise every object uses additionalProperties:false, including alternatives.
Reuse integer-only JCS, UTF-8, duplicate-key/non-finite/depth/size refusal from
research contracts; bool is never an integer. Never accept unknown artifacts by
ignoring them. All public schemas belong to a new discovery-common registry;
legacy preview/manual-PDF schema bytes stay unchanged.

Strings are NFC, contain no C0/C1 controls except LF/TAB in declared evidence
text, and have explicit limits. Generic evidence text max 16384 characters,
title/query 2048, identifier 256, source locator 4094. Timestamps are supplied
whole-second UTC calendar-valid strings; generated projection IDs do not include
wall time. Decisions keep actual caller-supplied timestamp and instruction data.
Set arrays are sorted by JCS bytes and duplicate-free; observations preserve
provider order with ordinals exactly 1..N. No generic unsorted-map merge policy.

## Session, config and budget reservations

Session initialization accepts an unsealed data-only JSON input:
{question,seeds,query_terms,lenses,limits,ranking,stopping}.
Seeds are one to three distinct descriptors {key,ids,title,author_terms,project_terms};
key is a safe unique slug, ids is a nonempty canonical ID set. The five lens names
are method,benchmark,implementation,counterevidence,reproduction. Each lens has
{lens,terms,scope}; it is required unless a later cited assessment explicitly
states not_applicable with rationale. question and scope are visible intent,
not model instructions overriding host policy. Query terms must be explicitly
supplied and are not inferred from a hidden model in Python.

Limits are positive configured integers bounded by hard maxima:
rounds 8, requests 32, observations 32, per_round_requests 8,
per_page 20 (OpenAlex hard capability max 100 remains adapter validation),
results_per_observation 100, total_results 2048,
unique_candidates 256, payload_bytes 1048576, total_payload_bytes 16777216.
Every family has <=256 files and <=32 MiB saved bytes; total store <=64 MiB.
Input depth <=32. Seeds and terms are bounded: 3 seeds, 32 common terms,
16 terms per lens, 8 author/project terms per seed.
Ranking {rrf_k:60,score_scale:1000000}; accept k1..1000 and fixed scale1000000.
Stopping {consecutive_rounds:2,min_new_relevant:1,duplicate_percent:80};
allow rounds2..4, minimum1..16, percentage50..100.

The config artifact seals exactly the validated configuration excluding seeds;
session artifact seals {session_key,config,seeds}. No config->session edge and
no session->first-round edge.

A round plan reserves EVERY declared request slot atomically when its plan file
is installed. A request artifact merely materializes an already reserved slot.
Reservations count even before requests/observations exist. Retrying consumes
a new slot in a later plan; failure/cancellation never refunds it.
An event distinguishes reserved_requests, materialized_requests,
terminal_observations and pending_observations. Limit tests must exercise an
interruption after the plan and after only part of its requests.

## Artifact kinds and acyclic graph

Five families: requests, observations, metadata, proposals, decisions under
.work/research/<session>/discovery-v1. Every filename is content_sha256.json,
including control/decision files. No mutable HEAD.

| Kind | Family | Proposed exact data fields |
| --- | --- | --- |
| research-config | metadata | question,query_terms,lenses,limits,ranking,stopping |
| research-session | metadata | session_key,config,seeds |
| research-round-plan | metadata | session,sequence,previous_round,control_head,request_specs,reservation_after |
| discovery-request | requests | session,sequence,plan_id,request_key,spec,target |
| discovery-observation | observations | request,observed_at,executor,outcome,payload,failure |
| research-assessment | decisions | session,sequence,plan_id,input_set_sha256,observations,lenses,generator,recorded_at |
| paper-candidate-set | proposals | session,sequence,plan_id,input_set_sha256,observations,items |
| paper-rank | proposals | session,sequence,plan_id,input_set_sha256,candidate_set,lists,fused |
| research-stop-decision | proposals | session,sequence,plan_id,input_set_sha256,assessment,candidate_set,rank,control_head,metrics,matched_reasons,primary_reason,next_action |
| research-round-event | metadata | session,sequence,plan,previous_round,requests,observations,assessment,candidate_set,rank,stop,budget_after |
| candidate-decision | decisions | session,sequence,previous,round,candidate_set,candidate_key,action,selected_arxiv,user_record |
| research-control-event | decisions | session,sequence,previous,round,action,user_record |

Each field is required; optional facts use explicit null or a closed unavailable
branch, never dropped optional properties. Typed refs resolve inside this exact
session. candidate-decision sequence is its own global session stream, controls
a separate stream. Each stream rejects forks, missing predecessors, duplicate
event identities and non-monotone timestamps. Controls reference the last
completed round or null before any completion.

Plan binds full session/config via session ref. It commits request_specs, not
request refs. Each spec carries request_key=SHA256(JCS(spec without request_key)).
plan_id is its own envelope ID. Requests repeat exact spec and plan_id; validate
against that committed slot. This breaks the plan/request hash cycle.
Final event is the first object containing the exact complete request-ref set.
No child refers to the current final event. Only the next plan refers to it.

Candidate set is ONE cumulative snapshot per round (<=256 entities), replacing
R1's suggestion of one materialized file per candidate. This avoids counting
unchanged entities repeatedly against a 256-file family cap. item.candidate_key
is a stable identity key, distinct from a round artifact ID. Rank refers to this
set and keys; decisions bind both set ref and candidate key.

input_set_sha256 is SHA256(JCS(sorted exact observation refs across completed
history plus current plan))). Assessment, candidate set and rank/stop bind that
same cumulative set. Current event also repeats current-round observations.
All references are recomputed, including previous events' cumulative inputs.
An assessment may cite only those complete inputs. One assessment per plan;
contradictory alternatives are conflicts, never arbitrarily selected.

## Request specification and planner

Closed spec fields:
{request_key,provider,operation,seed_key,subject_ids,subject_origin,lens,query,
per_page,cursor,continuation,retry,neighbor_ids,depth}.
provider has the two profile enums. operation is
lookup,references,citations,related,topic,project.
subject_origin is null for an original seed or an exact previous
{candidate_set,candidate_key}. depth is 0..2 and is derived from that lineage.
lens is one of the five names. A lookup is neutral metadata acquisition with
lens=method but does not satisfy that lens. query is null for ID operations.
cursor is null or a bounded opaque ASCII string, never parsed as code or URL.
continuation is null or an exact previous observation ref.
retry is null or {observation,reason}, with reason in
timeout,rate_limited,capability_changed,transient_failure.
neighbor_ids is null except explicitly expanding IDs from a previous lookup's
references/related list. It preserves the chosen stable ordered prefix and
binds continuation to that observation.

Automatic planning is deterministic and fully recorded. With no explicit specs,
construct a frontier from the config/seeds and completed observations:
1. For each seed lacking an observed OpenAlex or DOI record, issue one supported
   OpenAlex lookup if its IDs permit it; otherwise Web lookup by exact identifier.
2. Build required lens jobs in lens order above and seed-key order, cycling
   OpenAlex topic and Web topic/project profiles. All queries join declared
   question/common/lens terms; author/project jobs also include declared seed
   author/project terms. Duplicated normalized specs are suppressed.
3. Add references/citations/related jobs for an unambiguous observed OpenAlex
   identity. They remain indexed-neighborhood searches. A singleton lookup
   provides references/related IDs; explicit child batch retrieval validates
   the chosen IDs against that observation, max20 per page.
4. After direct seed jobs, expand up to three highest fused-ranked eligible,
   unseen candidate identities at depth1 then2. Each is bound to the previous
   candidate snapshot; never expand ambiguous identities.
Sort frontier by stage, depth, seed key, lens ordinal, provider ordinal,
canonical subject identity and spec key. Choose up to per_round_requests and
remaining request reservations. Save omitted frontier count/reasons in status
derivation. No implicit retry and no automatic cursor continuation; both require
explicit specs because they issue another external read.
Explicit plans validate every spec against the same available identities,
lineage, profile, scope, budget and depth rules; they cannot invent subjects.

No frontier and no pending requests produces next_action=needs_scope with
frontier_exhausted reason. It is not scientific coverage. A plan cannot be empty;
status can report exhausted without creating a fake completed round.
Calling plan again while a plan is pending idempotently repairs its deterministic
request materialization; a differing explicit plan is a conflict.

## Provider target and observation profiles

Targets are regenerated from spec and compared byte-for-byte. No caller URL:
OpenAlex uses only https://api.openalex.org/works and supported singleton IDs.
Singleton takes W[1-9][0-9]* or canonical DOI via documented external-ID lookup.
arXiv-only IDs have no fabricated OpenAlex direct-ID capability: use Web lookup.
citations uses structured references filter for the observed OpenAlex work;
references/related retrieve a bounded declared ID batch from the source
observation's referenced_works/related_works. topic uses one search parameter.
project uses the Web profile, not an invented OpenAlex project endpoint.
OpenAlex select is a constant allowlist of identifier/title/date/count/location
and neighborhood fields, excluding full text. Query URL ASCII length<=4094,
per_page<=100, cursor bound to exact previous request fingerprint and next_cursor.
The final filter/sort spelling must be verified against current official docs
before freeze; no previous guessed field becomes code.

Web target is a closed tool request description {kind:web_search,query,max_results};
it never promises exact HTTP request facts or exhaustive pagination. Web cursors
are unsupported. No unconstrained dynamic tool/method name.

Observation executor {tool_name,identity_source,capability_profile,locator};
identity_source=platform_reported|self_reported|unknown, and unknown requires a
reason. outcome=success|partial|timeout|rate_limited|capability_unavailable|failure.
success/partial have payload; failure variants have payload:null and a nonempty
failure object {code,message,retry_after_seconds}. Partial has both payload and
failure. Success failure:null. HTTP status/raw hash/header facts are absent from
this normalized-only schema.

Payload {results,next_cursor,total_count,completeness}; completeness is
visible_page|partial_page|indexed_neighborhood. Empty success is results:[] with
actual successful executor evidence. Each result:
{ordinal,ids,identity_links,title,summary,authors,published_at,cited_by_count,
provider_score,locator,relation,referenced_ids,related_ids,mirror}.
Unavailable title/date/count/summary use null; authors can [] for unavailable.
DOI/arXiv/OpenAlex identifiers are normalized, unique, type-tagged; arXiv
versions are separate nullable positive integers. provider_score is null or
canonical decimal string, never a binary float in JCS. references/related may
be null when unavailable, distinct from observed empty arrays. relation is the
requested operation, not independent claim of a verified scientific relation.
Each visible locator is a safe HTTPS source locator; no credentials or fragments
containing executable instructions are treated as authority.

## Identity, mirrors and candidate facts

Exact shared IDs link observations. Explicit identity_links carry
{left,right,relation,locator}, relation=same_work|preprint_of|published_as.
Only same_work edges join components; DOI/arXiv co-occurrence alone does not
imply equality. Known OpenAlex own work ID with its reported DOI is an explicit
provider crosswalk. arXiv found among locations is a version/related observation
unless the supplied visible source specifically asserts same_work.
Canonical DOI normalization reuses accepted identifier semantics; arXiv uses
existing parser. OpenAlex lowercase w normalizes to uppercase W, no zero/leading
zero integers. Preserve every observed version in why-found facts.

Build the complete graph across all current/historical result facts before
component classification. Component candidate_key is SHA256(JCS(sorted
unversioned canonical identifiers))). More than one distinct ID in a namespace
makes the component conflicted, retaining conflict {namespace,ids,facts}.
Do not split by arbitrary arrival or choose one claimed identity. Conflicted
components remain visible, are excluded from fusion/preview/expansion, and count
as unresolved. A later correcting identity relation cannot silently erase the
old observation; design for explicit correction remains a future review point.
For this first profile, conflicts require a fresh separate session with corrected
inputs rather than unimplemented conflict-resolution authority.

Each candidate item contains ids,versions,conflicts,why_found,relevance,signals.
why_found retains exact request/observation/ordinal/locator/seed/lens/relation and
matching normalized terms. Metadata disagreements remain per-fact provenance;
display title chooses first nonempty by sorted observation-ref+ordinal, not
arrival. Lowercased NFC whole-term substring matching is the explicitly
provisional relevance rule; empty term sets are invalid and unsupported languages
are not silently treated as semantic matches.

mirror is {group,provenance,reason}; group is null or an explicit normalized
stable source ID, provenance=provider_reported|host_observed|unknown.
Unknown independence never invents an independent publication source.
Same canonical source locator and same known group collapse. Independent ranks
mean independent retrieval lists, not independent scientific confirmation.
List key is provider+seed+lens+operation; cursor/retry pages remain the same list.
Duplicate mirrors within/across compatible lists contribute at most one rank
term per candidate and known mirror group; unknown groups conservatively collapse
per candidate to one unknown group. Preserve suppressed contributions for audit.

## Reproducible ranking and assessments

Provider list candidate order is lexicographic tuple:
relevant first, count of matched terms descending, depth ascending,
known cited_by_count descending (unknown last), known publication date descending
(unknown last), best observed provider ordinal ascending, candidate_key bytes.
Raw provider scores are display-only; do not add incomparable scales.
Each unique eligible candidate gets one-based list rank. After mirror suppression,
RRF=sum(1/(k+rank)) as exact reduced Fraction. Store numerator/denominator decimal
strings plus floor(score_scale*numerator/denominator). Final ordering compares
rational values, then candidate_key. Keep every contributing/suppressed list
rank with reason so mirrors and unknowns are visible.

Finish accepts a closed unsealed coverage assessment proposal. This is actual
caller/model output, not auto-generated semantic approval. It supplies generator
identity plus one entry per five lenses:
{lens,state,scope,statement,evidence,reason}.
state=covered|not_applicable|gap; covered requires >=1 exact result citation and
nonempty statement, reason:null. not_applicable requires scope-specific rationale
and no invented citation; gap requires reason, and may cite partial evidence.
Evidence {observation,ordinal,field,start,end,excerpt_sha256} resolves to exact
title/summary text Unicode codepoints, nonempty bounded span, matching hash.
An input label or successful request alone never closes coverage. All results
remain provisional_scientific_assessment regardless of generator identity.
Prompt context exposes only the declared complete inputs and asks for gaps where
evidence is insufficient. HTML/Markdown from observations is escaped when rendered.

Finish is allowed only when every reserved request has exactly one terminal
observation. Pending requests stay pending; a user can stop without fabricating
timeout outcomes. Failed required lens requests remain visible even if another
cited result covers that lens; report both operation health and provisional
coverage. Assessment absence returns assessment_required with its exact context;
no partially imagined assessment is stored.

## Stop, control and resume rules

After current observations and assessment are complete, derive cumulative
candidates/rank and round metrics: successful/partial/failed requests, raw hits,
new distinct identity components, repeated hits, new relevant candidates,
unresolved components, pending requests, each lens state and cumulative budget.
Duplicate ratio uses repeated identity hits / total current hits, canonicalized
against full previous identity graph; zero hits never trigger duplicate.
Record integer numerator/denominator; no float division.

matched_reasons ordered by precedence:
user_stop,budget_exhausted,paths_covered,duplicate_ratio,yield_below_threshold.
paths_covered means all five assessment states covered or not_applicable and no
unresolved identity needed by their cited facts. It stays provisional.
Duplicate and low-yield conditions require configured consecutive completed
rounds. No incomplete round participates. Budget exhaustion uses plan reservations
and all stored normalized payload/results, including partial/failure evidence.
A malformed rejected input was not an accepted observation and does not fabricate
a debit, but any successfully installed artifact is never refunded.
No matched reason means primary_reason:null,next_action:continue.
A matched reason gives stop; status separately reports needs_scope if no frontier.

user_stop/resume are immutable controls with actual
user_record {event_id,text,source,recorded_at}. plan captures control_head;
finalize verifies no newer control appeared without recomputing effective status.
Controls do not rewrite existing round event bytes. An active user stop blocks
new plans, observation installs and finish, while read-only status remains usable.
resume may clear only user_stop; it cannot enlarge immutable budget or negate
calculated complete-round stop. New scope/limits use a fresh session.
Resume command (without control input) repairs deterministic files and reports
pending work; it does not synthesize a user resume event. CLI control --action
resume is the explicit instruction-recording operation.

## Create-only storage and crash recovery

One retained descriptor session owns checkout/.work/research/session/discovery-v1,
all five families, complete named sets and reached file snapshots until exit.
Retain the first observed absence when any ancestor is missing. Acquisition,
parsing, schema/resource loading, preflight, projection and cleanup failures all
perform final named-edge/set/byte checks, with WORK_PATH_UNSAFE precedence.
Never create missing parents in status/context/list/handoff reads.
Writers create only expected directories/files with no-follow and atomic install.
Exact bytes reuse; competing bytes, unknown siblings or foreign orphans refuse.

Install config before session, plan before deterministic requests; accept one
terminal observation per slot. After supplied assessment, write assessment then
candidate set, rank, stop, event LAST. The full expected graph is deterministically
derivable before install. A graph parser distinguishes valid pending subsets
from unrelated orphan artifacts: pending children must equal their expected
bytes and occupy only committed slots. Existing event with missing child is
integrity failure. No next plan exists until the predecessor event is complete.
Status recognizes init_pending,round_pending,assessment_required,
projection_pending,complete,stopped,needs_scope. Conflicts/unsafe paths are
structured errors, not self-healing status. It never deletes anything.

Event budget_after is recomputed from its prefix, excluding the event's own
file size to avoid self-reference; exact store byte limits are a separate scan.
Event-file overhead is preflighted using prospective bytes before install.
Control history can advance after an event; event binds its historical control
head while status derives current effective control. Concurrent controls or
outcomes must fail rather than create forks. No lock-dependent hidden overwrite.

## Public interfaces and validation

Proposed CLI under vpwiki-research discovery:
init --session --config-input; plan --session [--specs-input];
observe --session --request --observation-input; context --session;
finish --session --assessment-input; status --session; resume --session;
control --session --action --event-id --user-text --source --recorded-at;
decide --session --candidate-set --candidate-key --action preview|skip|later
--selected-arxiv --event-id --user-text --source --recorded-at;
handoff --session --decision; render --session.

All produce the existing one JSON envelope. Public Python functions use keyword
arguments and return the same payloads. CLI root derives project from explicit
approved checkout CWD using existing staging root logic; input paths are retained
and may be outside checkout for read only. Error codes preserve shared WORK errors;
new DISCOVERY_INPUT_INVALID,DISCOVERY_GRAPH_INVALID,DISCOVERY_CONFLICT,
DISCOVERY_LIMIT_EXCEEDED,DISCOVERY_PENDING,DISCOVERY_STOPPED,
DISCOVERY_IDENTITY_UNRESOLVED,DISCOVERY_CAPABILITY_UNAVAILABLE use exit2 except
pending/stopped queries returned as normal status. Unknown exceptions propagate
after boundary verification; no blanket conversion to success.

A preview decision may select only one nonconflicting arXiv ID/version actually
observed in the referenced candidate snapshot. Handoff returns a deterministic
W1 make_request document/ref plus discovery decision ref and a command descriptor.
It writes no W1 subtree. The caller invokes existing W1 paper request separately;
that operation's own refs and actual observations determine preview. No fake
cross-session rw1 reference is stored as if it had already been created.
skip/later handoff is null.

Acceptance covers both providers, 3 seeds, five lenses/paths, full graph replay,
reserved pending slots, conflicting identities, versions/preprint relation,
mirrors/unknown independence, exact rational ties, all stop branches, retries,
cursors, interruptions at every install edge, one envelope/no egress/no Vault,
hostile inputs and all-exits retained paths, installed schemas and a separate
held-out host observation. No external/human scientific approval is inferred.

## Remaining decisions before freeze

Independent reviewers must resolve: automatic planner exact job expansion and
OpenAlex filter/sort/select target grammar; whether identity correction needs an
in-session immutable authority in this package; RRF mirror grouping across list
keys; deterministic init recovery when only config exists; and final schema/path
allowlist. This is reviewable design, not acceptance or implementation.

