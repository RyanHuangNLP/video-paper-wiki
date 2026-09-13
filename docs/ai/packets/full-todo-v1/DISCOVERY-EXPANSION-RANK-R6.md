# Discovery ranking and logical frontier decisions R6

Final semantic amendment for independent review with R2 through R5. It resolves
the mirror/list equivalence finding without adding external authority. All facts,
contributions and suppression reasons stay inspectable and deterministic.

## List and mirror equivalence

A retrieval list key is the JCS serialization of
{provider,seed_key,lens,operation}. All observations from those same four values
belong to ONE list across rounds, candidate subjects, depths, cursor pages,
explicit ID slices and retries. A list rank is computed once over all eligible
candidate components represented in that cumulative list. It is not an appended
provider-page ordinal. Raw per-observation ordinals remain evidence facts.
All lists are compatible for mirror suppression; no separate seed/lens/operation
can multiply the same mirror source's contribution.

For each eligible candidate, build mirror equivalence classes over its result
facts. Facts with the same normalized source locator are joined. Facts declaring
the same known mirror.group are joined, regardless of provenance label. Take the
transitive closure of these links. A class is known if it contains at least one
provider_reported/host_observed group declaration. Conflicting known labels on
one URL join into one class and remain visible in the class's group_labels; they
never yield two independent terms. Other classes have unknown independence.
Class key is SHA256(JCS(sorted {observation,ordinal} fact citations)); class
membership therefore does not depend on arrival. Normalized locator is used only
for this equivalence, never to rewrite exact observed evidence.

Each list/candidate has one provisional term at its computed list rank. Select
one representative class from its facts by known classes first, then class_key;
choose the exact representative fact by observation-ref JCS bytes then ordinal.
All alternative facts/classes remain recorded as same_list_candidate suppression.
This is deliberately conservative: one list never contributes twice just because
it returned more than one known location for a work.

Now sort provisional terms by rank ascending, list-key JCS bytes ascending,
class_key ascending and representative fact ascending. Keep at most one term per
known class for the candidate, suppressing later terms as same_mirror_class.
If any provisional term has a known class, suppress unknown-class provisional
terms as independence_unknown_with_known; their independence is unproved.
If none has a known class, keep exactly the first unknown term and suppress all
other unknown terms as independence_unknown_duplicate. No unknown fact is promoted
to known by a title, organization, similar URL or model confidence. Every eligible
candidate with facts therefore has at least one term, but mirrored retries cannot
increase its score. This is retrieval weighting, not scientific confirmation.

Compute exact reduced rational sum 1/(k+rank) over kept terms, retaining decimal
numerator/denominator, floor(1000000*numerator/denominator), every contributing
term and every suppression with reason. Sort fused candidates by exact Fraction
descending then candidate_key bytes. Conflicted components have no list or fused
rank; preserve their facts and conflict reasons in candidate-set items.

## Deterministic fact and ranking fields

Match lowercase NFC whole-term substrings against each result's title and summary
separately. The term set for a fact is config.query_terms plus that request lens's
terms, plus original seed author_terms/project_terms for project operations only.
Terms are normalized lowercase/NFC, deduplicated, sorted by JCS, and must contain
non-whitespace text. Do not split words or use a hidden semantic model. A candidate
is relevant for a list if any fact in that list matches at least one term; its
match count is the size of the union of those matched terms in that list.
Global provisional relevance is the union over all its facts. Unsupported or
unmatched wording stays unmatched, not an assertion of scientific irrelevance.

For one list/candidate, the R2 order tuple uses only its facts in that list:
relevant first, distinct matched-term count descending, minimum depth ascending,
maximum known cited_by_count descending (null last), latest known publication
date descending (null last), minimum observed ordinal ascending, candidate_key.
Different counts/dates stay visible in facts; maxima are ranking signals only.
Display title still uses the first nonempty title by observation-ref/ordinal.
No normalized provider score enters this ordering or RRF.

Repeated-hit and yield metrics use result-component memberships, not file order.
For every current-round result, each distinct component it names is one hit.
A hit is repeated if that component intersects identifiers in completed prior
rounds OR it is after the first occurrence of that current component in canonical
observation-ref/ordinal order. total_hits counts those memberships; repeated_hits
counts that subset. Duplicate threshold compares repeated_hits*100 against
configured_percent*total_hits; total_hits=0 never qualifies as duplicate.
new_relevant is the count of current components disjoint from all prior IDs with
at least one term-matching current fact. Low-yield compares this count with the
configured minimum. These definitions follow full current identity joins and
keep versions/aliases from manufacturing new works.

## Logical frontier attempt identity

Request keys continue to hash the complete exact spec, including provenance refs.
For default attempted-job suppression, additionally derive a logical job key from
{provider,operation,seed_key,lens,unversioned subject IDs,depth}. Exclude transient
candidate-set/observation refs, query text (deterministically fixed by config),
version labels, neighbor slice IDs, cursor, retry and request_key. This prevents
a new round snapshot from reissuing the same base job merely because its origin
ref changed. A logical job is attempted when any matching plan slot is committed,
including a missing request file or a terminal failure. Exact user retries and
continuations are separate explicitly authorized slots, never new plain jobs.
An identity bridge uses the current full identifier set; if it intersects a
previous attempted subject for the same other fields, the logical job remains
attempted. Do not reissue after alias extension or identity merge.

Choose a seed subject deterministically: OpenAlex ID first, otherwise DOI,
otherwise arXiv. The request still retains its full subject_ids. Seed lookup
uses the chosen ID (Web for arXiv). Neighborhood operations require a previously
observed OpenAlex identity and its exact request/result provenance. references
and related require that observed result's nonnull neighbor list. Empty lists
are observed exhausted paths with no fabricated request. A null list is an
unavailable capability entry. Citation queries can use the observed OpenAlex ID
without a neighbor list. Choose among matching source observations by exact ref
then result ordinal; store the chosen origin in the spec's continuation field.

Default neighborhood lenses: references and related use method; citations use
counterevidence; project uses implementation. Topic retains its assigned lens.
Topic query is question + lens.scope + common terms + lens terms, each retained
in declared order separated by a single ASCII space. Project query additionally
appends seed title, author terms and project terms in declared order. Empty optional
pieces are omitted, nonempty text is preserved; enforce the final 2048-character
query and 4094-byte target bounds. Lookup ignores these search terms.

After all currently eligible direct jobs have been attempted, select at most
three distinct unambiguous candidate components for graph expansion across the
whole session. Previously selected components keep their place; aliases/bridges
do not free or consume an extra selection. Choose new ones by last complete fused
rank then candidate_key. Derive seed_key from the lowest depth why-found fact,
then seed key, then request ref. A candidate's expansion depth is one plus its
minimum why-found request depth, at most two. A component already selected at a
shallower depth is not selected again at a deeper depth. Sources available only
at depth two produce no deeper requests. Bind every fresh expanded request to
the last complete candidate-set/key; historical requests retain their original
refs. The three-selection count is a status/graph-derived bound, not an artifact
that could lose its origin across a restart.

Retries must reference a previous terminal observation for the same logical
operation and preserve all base fields; reason must match timeout/rate-limited,
failure (transient_failure), or unavailable (capability_changed). Success cannot
be retried. A partial outcome may use transient_failure or a documented next
page, retaining its original partial data. New retry has retry.observation set
and cursor:null unless the previous failed request itself was an exact cursor
request, in which case preserve that cursor/continuation. No hidden retry loop.
Cursor continuation is topic/citations only, equals the previous payload's exact
nonnull next_cursor and preserves the previous base fields. Explicit reference/
related slices preserve the singleton provenance, select a nonempty <=per_page
prefix of not-previously-requested neighbor IDs in canonical ID order, and remain
in the same retrieval list. They consume slots and require explicit specs.

Acceptance must assert exact term/suppression lists, known/unknown mixtures,
same-URL conflicting groups, cursor/retry/slice collapse, Fraction ties and all
arrival permutations. It must prove alias changes do not reissue plain jobs,
three expansion selections survive merges, depth two does not recurse, and the
same immutable inputs always regenerate identical targets and plans.
