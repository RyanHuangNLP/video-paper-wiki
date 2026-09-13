# Discovery wire and capacity decisions R5

Design amendment for the final freeze, read after R2 design, R3 recovery, R4
bounds and provider target notes. Earlier artifacts stay unchanged. These rules
prevail where their wording differs. No implementation acceptance is implied.

## Feasible automatic prefix

Construct the full round-robin frontier prescribed by R4. Automatic planning
chooses the largest prefix length N between one and the minimum of configured
per-round requests, remaining request slots and remaining observation slots that
passes exact serialized plan/request bounds, family byte/count reservations and
total reservation. Check candidate Ns in descending order; never skip an earlier
frontier item to make a later item fit. Persist the selected specs sorted by
request_key as R3 requires; scheduler order selects membership, not slot order.
Explicit specs are a set: canonical ordering is required for their stored plan,
but their membership is all-or-reject and is never silently shrunk.

The 14 MiB total reservation remains fixed for N1 through N8. Conservative early
budget_exhausted at this total boundary is an intentional bounded storage policy,
not a claim that every smaller collection would exhaust actual filesystem space.
The largest-prefix rule can still resolve per-family, count and plan-size limits.
Status records available frontier count, chosen count, omitted count and limiting
bounds. No feasible prefix yields budget_exhausted before plan installation.
No available frontier yields needs_scope. A prior calculated/user stop retains
its specified precedence.

## Candidate charging versus incomplete estimates

Permanently charged candidate_slots_reserved is the sum of component introductions
in completed rounds, using the R3 disjoint-from-prior-identifiers definition.
For an incomplete current round, pending_candidate_introductions is a separately
named prospective estimate from its currently accepted observations. This estimate
may change when a later current-round observation supplies an explicit same_work
bridge; it is not yet a permanently charged completed-round reservation.
Before each observation installation, require completed charged slots plus that
prospective estimate <= configured unique_candidates and current components <=
that limit. Once all current inputs are terminal the estimate is final; completing
the round charges it exactly once. Previously completed charged slots never refund.
Event budget_after records the resulting permanent count; incomplete status also
shows the separate estimate, never pretending a transient estimate is immutable.

This fixes the ambiguous phrase "pending candidate reservations" in R3/R4.
Plan-time round/request/observation/retry slots remain permanently reserved exactly
as specified there. Invalid inputs are not accepted observations and consume no
new slots beyond the request slot already reserved by the plan.

## Identifier and provenance wire types

A canonical identifier is the closed object {namespace,value,version}:
namespace is doi, arxiv or openalex; value is the unversioned canonical identifier;
version is null for DOI/OpenAlex and null or a positive integer for arXiv.
DOI uses the accepted lowercase DOI canonicalizer; arXiv uses the accepted old/new
identifier parser; OpenAlex uses uppercase W followed by a nonzero, non-leading-zero
decimal integer. URL aliases may be accepted only at unsealed input normalization;
sealed artifacts contain canonical identifiers. Sorting/dedup uses JCS bytes.
A seed has at most one unversioned identifier per namespace and distinct seed keys.
Seed ids are declarations of the user's search subject, not an observation that
proves different namespaces identify one publication.

In result facts, two IDs co-occurring in one result do not create a same_work edge.
Each belongs to its graph component; the result is why-found evidence for every
component it names. Explicit identity_links alone connect different identifiers.
Their endpoints must occur in that result's ids; same_work joins, preprint_of and
published_as are retained directed relations and do not join. An OpenAlex own ID
and its reported DOI can be supplied with an explicit same_work crosswalk and the
actual provider locator. This is observed provider metadata, not scientific review.
Candidate keys are lowercase 64-hex SHA256 values over JCS-sorted unique unversioned
{namespace,value} objects. Observed arXiv versions remain separate candidate facts.

Executor uses {tool_name,identity_source,capability_profile,locator,reason};
unknown identity has tool_name="unknown" and a nonempty reason; known identity
has reason:null. Identity source is platform_reported,self_reported or unknown.
Capability profile exactly matches the request's provider. Locator is a safe
HTTPS URL or null when no source locator was returned; failures can legitimately
have null. Generator identity reuses {value,identity_source,reason} with the same
unknown/known consistency rule. No caller identity string asserts authentication.

A result mirror is {group,provenance,reason}. Unknown provenance requires group:null
and a nonempty reason; known provider_reported/host_observed grouping requires a
nonempty bounded group and reason:null. URLs normalize scheme/host case and remove
the default HTTPS port; query and path bytes remain significant. Fragments are
removed for duplicate-source grouping only, while exact visible locators remain
in provenance. No redirect equivalence is guessed.

## Fixed target representation

OpenAlex targets are {kind:"http_get",url:<regenerated HTTPS URL>} with no header,
credential, payload, method override or automatic redirect field. Web targets are
{kind:"web_search",query,max_results}. The host executes the named fixed operation
with available tools; Python itself performs no network call.

Use the exact singleton/filter/search/select/sort rules in provider target notes.
Canonical query parameter order is filter or search (when present), per_page,
select, sort (for lists), cursor (when present). Encode with percent encoding using
UTF-8, spaces as %20, no plus substitution, and RFC3986 unreserved characters only
inside parameter values. Singleton appends only select. DOI path uses doi: followed
by the canonical DOI with slash preserved; other reserved characters are escaped.
Citations sort cited_by_count:desc; ID batches also use that sort; topic uses
relevance_score:desc. The fixed nine-field select string is byte-exact.
Web lookup query is the exact chosen canonical arXiv/DOI/OpenAlex identifier; topic
and project query construction is deterministic from the declared config fields.
Unsupported operations are capability gaps, never arbitrary URL passthrough.

Normalized provider payloads cannot assert raw bytes, HTTP status or unseen headers.
Provider counts are nonnegative bounded integers or null. Provider score is null
or canonical decimal text with optional minus, no leading/trailing zeros, no plus
or exponent, and at most 128 characters; it is display-only. Publication date is
null or a calendar-valid YYYY-MM-DD. Every result must carry at least one canonical
ID; an unidentifiable search hit remains excluded normalization evidence, not a
fabricated paper candidate. This profile does not claim exhaustive web coverage.

All malformed, oversized or unsupported input remains a typed refusal before
installation. The host can explicitly record failure.code=local_normalization_failed
with its actual reason if visible content could not satisfy this bounded profile.
This is distinct from an external timeout or successful empty result.
