# Bounded discovery continuation — design R1

Design preparation during SOURCE-CATALOG's frozen local acceptance. This does
not authorize source edits or claim a new accepted baseline. Root remains the
implementation owner. The three existing assistants retain their independent
review and serialized Git duties. SOURCE conversion is accepted at 7ed55cfc;
the catalog candidate must finish its own acceptance and delivery before the
next implementation is assembled on that exact baseline.

The earlier w3-design-gap-review-r1.json and discovery-code-scope-review-r1.json
are advice. This draft resolves their circular-reference and provider-scope
ambiguities before an implementation contract is frozen. Existing preview,
source, legacy catalog and 67 seed records remain byte-compatible.

## User result and external boundary

Given one to three explicitly identified seed papers and a research question,
produce a bounded research session: provider requests, observed candidate papers,
why-found evidence, independent source ranks, fused ranking, coverage gaps,
round history and a reproducible stop/resume decision. Requests can follow
indexed references/citations/related works, search a topic, or search for a
paper's author/project signals. Candidates never become formal source entries
or user selections automatically.

Python constructs requests and validates supplied observations locally. The
host's Web/connector tools carry out approved external reads. Credentials,
cookies, authorization headers and hidden account facts are never requested,
read or stored by Python. No PDF, full text, source archive, code or weights are
downloaded by this discovery package. Requests are data with generated targets;
they cannot contain shell commands or caller-controlled arbitrary URLs.

Two explicit profiles are required: openalex-rest-normalized-v1 and
platform-web-search-normalized-v1. Provider ranks and independence keys remain
separate. The Web profile reports visible results and source locators; it does
not claim a raw HTTP response or a complete citation list. OpenAlex profiles
retain indexed-neighborhood incompleteness. An executor capability failure is
a stored outcome, never an invented empty successful result.

## Current provider documentation

Official documentation read on 2026-09-09 supports anonymous basic requests,
per_page up to 100, continuation through meta.next_cursor, and citations from
matched indexed references. The current implementation should impose its own
lower caps and preserve unavailable transport facts. No live access or response
shape has been verified by this documentation check.

- https://help.openalex.org/api/authentication/
- https://help.openalex.org/api/paging/
- https://help.openalex.org/api/searching/
- https://help.openalex.org/data/works/citations/

Do not hardcode billing prices or claim that a key is unavailable/required for
the current host. The host may use its own authorized connector. Generated
OpenAlex URLs use HTTPS api.openalex.org, fixed structured operations, snake_case
parameters and at most 4094 ASCII bytes after URL encoding. Search supports one
search parameter. Cursor continuation must derive from an exact preceding
observation, with identical query/filter/seed/field configuration. No automatic
retry or hidden cursor walk occurs inside the Python process.

## Stable identities and observation facts

Accept canonical OpenAlex Work IDs, arXiv IDs with separately represented
versions, and normalized DOI identities. Each result has at least one stable
identifier and an exact visible source locator. Titles, authors, dates and
counts can be unavailable; title similarity never merges entities. Preserve
all observed identity facts and their observation/ordinal references.

Identity deduplication must be order-independent. Merge records only through
explicit identical IDs and compatible crosswalk facts. Build connected identity
components, detect conflicting same-namespace IDs in the complete component,
and keep conflicts visible instead of greedily merging by arrival order.
Publication versus preprint relations are explicit related identities, not an
implicit DOI-to-arXiv equality rule. An arXiv version is a version label on its
entity; differently versioned observations retain their separate citations.

An observed crosswalk is provider evidence, not a newly accepted canonical
paper identity. Its confidence/representation is visible. A candidate requiring
conflict resolution cannot be handed to preview until the conflict is resolved
by a new explicit identity observation. OpenAlex-only and DOI-only candidates
remain valid discovery results even when the current arXiv preview adapter
cannot preview them; their next action identifies the missing capability.

Observation objects bind their exact request, supplied timestamp, actual visible
executor/profile facts, outcome, normalized payload and completeness. Successful
results retain original provider order, positive ordinals, title/date/count
facts, relation to the requested seed and per-result locator. Provider numeric
scores that are not safe integers are retained as validated decimal strings or
explicitly unavailable, never coerced through integer-only JCS. A failed outcome
has no invented result list. Partial results carry their failure/completeness
reason and remain distinguishable from a complete observed page.

## Immutable graph and resumable rounds

Use a fresh `.work/research/<session>/discovery-v1/` subtree with exactly the
five artifact families requests, observations, metadata, proposals and decisions.
All public artifacts are closed envelopes with domain-separated content IDs and
exact file-hash references. Use a new discovery common schema; do not enlarge
the existing preview or manual-PDF registries.

The graph must be acyclic. A session binds its config and seeds but has no
first-round back-reference. A round plan binds the session, sequence and exact
previous completed round, then declares every request in that round. Requests
bind the round plan. Observations bind requests. Candidate/rank/stop projections
bind their complete round inputs and sequence. The final round event binds all
those objects and is the last committed file for the round. No child artifact
may contain a back-reference to that not-yet-existing final round event.

Permit only one next round plan per complete predecessor. Competing plans or
terminal observations for one request are conflicts. A retry is a new explicit
request with an exact predecessor outcome, budget debit and reason. No mutable
HEAD file, database or overwrite is introduced. Derive the last complete round
from the validated immutable chain; multiple successors are an error.

Partially installed deterministic request/projection artifacts must be checked
against their committed plan and complete inputs. They are pending work, never
a completed round. Resume fills only the exactly missing deterministic files
and appends the round event last. Foreign orphan objects, unknown names,
mismatched hashes or competing results refuse. Every named edge, complete set,
input byte snapshot and originally absent target is retained across the whole
operation and checked on success and exception. Read-only status never creates
the subtree and must retain its first missing ancestor.

All source strings are untrusted data. Rendering escapes Markdown/HTML/link
syntax and cannot turn provider text into instructions or uncontrolled file
paths. No imported package/resource lookup falls back to arbitrary CWD material.

## Ranking, coverage and deterministic stopping

Config freezes the query decomposition, required research lenses, count/byte
caps, relevance predicate, rank lists, RRF k and stop precedence. Required lenses
cover method, benchmark, implementation, counterevidence and reproduction.
Search and citation results label the lens they were requested to investigate;
this label alone does not prove that the lens was answered.

Candidate records contain complete why-found tuples: seed, relation, request,
observation, result ordinal, locator and structured matching terms. Keep all
sources and known mirror/independence groups. Duplicate mirrors do not add
independent-source rank weight; unknown independence is explicit.

Build separate provider/local rank lists. Topic overlap, seed distance, citation
count, publication date and source diversity remain inspectable component
signals. Do not add incompatible raw provider scores. Rank fusion uses exact
rational RRF with a fixed positive integer k; comparison is rational and the
rendered integer score uses a documented floor scaling. Ties use canonical
candidate identity UTF-8 bytes. Scheduling order, worker count, observation
arrival order and wall time never change candidate/rank/stop projection bytes.

Stop precedence is user_stop, budget_exhausted, paths_covered, duplicate_ratio,
yield_below_threshold. Record every matched reason. Defaults from the prior
advice remain proposals pending exact profile freeze: eight rounds, 32 requests,
32 observations, 256 total candidates, one MiB per normalized input and 16 MiB
total. Explicit per-provider page limits still apply. Bounds are checked before
staging or request issuance; no silent truncation or dropped observation.

The proposed low-yield test is fewer than one new relevant candidate in two
consecutive completed rounds. Duplicate stopping is at least 80 percent in two
consecutive completed rounds, using integer counts and cross multiplication.
A zero-result round does not divide by zero or count as 100 percent duplicate.
Relevant means the frozen lexical/query predicate, not a human claim of research
quality. All new/matched/duplicate/unresolved counts remain visible.

Paths are covered only by explicit cited lens evidence or a supplied
not-applicable rationale bound to a declared scope. Any pending/failed required
lens remains a gap. Broad topic coverage, counterevidence sufficiency and
scientific stopping remain provisional and can be reviewed independently.

User stop/resume are append-only control events carrying the actual instruction
reference, exact text and supplied event identity. The developer's instruction
to implement this feature is not a stop/selection in a real research session.
Status/resume inspection can report pending work without inventing a user
resume after a stop. An explicit continuation event is required to reopen a
user-stopped session; history remains intact.

## Preview and canonical handoff

Candidate choice is an append-only decision, separate from candidate ranking.
An explicitly chosen, nonconflicting arXiv identity yields an exact W1 request
handoff. It does not manufacture metadata, a preview, user selection of a paper
version, captured bytes, source registration or a receipt. Existing W1 preview
and decide validate their own references and require the real user's choice.
Original immutable discovery refs remain attached to the handoff.

## Required next freeze

Freeze exact artifact/schema fields, enum values, ID/hash/JSON/LF rules, error
codes, CLI options, query planning and pagination algorithms, graph recovery
rules, public APIs, bounds and writable paths before implementation. Resolve
the membership proof for derived pending children and the exact identity-conflict
representation in independent review. The schema draft must not reuse an
already-existing compile or source schema name for a different contract.

Acceptance must exercise synthetic and separate held-out host observations,
three seeds, both providers, reference/citation/related/topic/project paths,
conflicting identifiers, explicit version visibility, mirror suppression,
parallel arrival invariance, all stop reasons/precedence, interrupted write and
resume, cursor/request mismatch, hostile/deep/oversize JSON, no egress, no Vault
write, installed resource parity and exact-head tests. Real access, provider
transport, human relevance judgment and actual paper selection remain separate
outcomes. CODE, DOMAIN, SYNTHESIS, QUALITY and PRODUCT remain authorized work.
