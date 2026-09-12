# Bounded paper discovery

`vpwiki-research discovery` turns an explicit research question and one to three
seed identifiers into an inspectable, resumable discovery session. It writes only
under the checkout's `.work/research/<session>/discovery-v1/` directory. It performs
no network requests, runs no external tools, downloads no PDF, and changes no
Vault. The host conversation executes the generated requests with available Web
or connector tools and records only what those tools actually returned.

Start from the checkout root. Every command returns the existing single JSON
success/error envelope. A session slug contains 1–64 lowercase ASCII letters,
digits, underscores or hyphens, beginning with a letter or digit.

```sh
vpwiki-research discovery init --session video-study --config-input config.json
vpwiki-research discovery plan --session video-study
vpwiki-research discovery context --session video-study
```

The plan reserves every declared request and terminal observation slot before any
request file is written. Context lists the materialized request documents, their
exact identifiers and fixed targets. Execute those targets through the host,
then record an observation for each installed request:

```sh
vpwiki-research discovery observe --session video-study \
  --request rw3:discovery-request:REQUEST_DIGEST --observation-input observation.json
vpwiki-research discovery finish --session video-study --assessment-input assessment.json
vpwiki-research discovery status --session video-study
vpwiki-research discovery render --session video-study
```

The example digest is a placeholder; copy the complete identifier from context.
All file inputs are retained read-only through the command's final verification.
Use ordinary paths without symlinks, traversal or alternate spellings. A failure
leaves already committed artifacts intact; it never invents a terminal outcome.

## Configuration

Supply a data-only JSON object with exactly `question`, `seeds`, `query_terms`,
`lenses`, `limits`, `ranking`, and `stopping`. For example:

```json
{
  "question": "Which methods improve temporal consistency in video diffusion?",
  "seeds": [{
    "key": "starting-paper",
    "ids": [{"namespace": "arxiv", "value": "2401.12345", "version": null}],
    "title": null,
    "author_terms": [],
    "project_terms": []
  }],
  "query_terms": ["video", "temporal consistency"],
  "lenses": [
    {"lens": "method", "terms": ["diffusion"], "scope": "Temporal modeling methods"},
    {"lens": "benchmark", "terms": ["benchmark"], "scope": "Comparable temporal evaluations"},
    {"lens": "implementation", "terms": ["code"], "scope": "Available implementation evidence"},
    {"lens": "counterevidence", "terms": ["failure"], "scope": "Limitations and contrary results"},
    {"lens": "reproduction", "terms": ["configuration"], "scope": "Conditions needed to reproduce results"}
  ],
  "limits": {
    "rounds": 8,
    "requests": 32,
    "observations": 32,
    "per_round_requests": 8,
    "per_page": 20,
    "results_per_observation": 100,
    "total_results": 2048,
    "unique_candidates": 256,
    "payload_bytes": 1048576,
    "total_payload_bytes": 16777216
  },
  "ranking": {"rrf_k": 60, "score_scale": 1000000},
  "stopping": {"consecutive_rounds": 2, "min_new_relevant": 1, "duplicate_percent": 80}
}
```

The seed above illustrates identifier syntax, not a recommended real paper.
Every limit is positive and may be reduced. The profile values are hard maxima.
Identifiers use closed `{namespace,value,version}` objects: canonical DOI bodies,
OpenAlex `W` identifiers, or unversioned arXiv identifiers with a separate observed
version. DOI/OpenAlex versions are always null. Input aliases are normalized only
when initializing a config; stored artifacts require canonical identifiers.
Seed IDs declare search subjects and do not prove cross-namespace equivalence.

Keep all five lenses in the displayed order. Query construction preserves declared
text and term order. Provisional relevance uses the deduplicated, lowercase NFC
term set, matching each title and summary separately. It is an inspectable string
match and makes no scientific relevance judgment.

## Host observations and coverage

`observation.json` has exactly `observed_at`, `executor`, `outcome`, `payload`, and
`failure`. `executor` has `tool_name`, `identity_source`, `capability_profile`,
`locator`, and `reason`. Its profile must match the exact request. Identity may be
platform-reported, self-reported, or unknown; unknown uses the literal `unknown`
and a reason. It never implies authentication or permission.

Terminal outcomes are `success`, `partial`, `timeout`, `rate_limited`,
`capability_unavailable`, and `failure`. Success has a payload and null failure;
partial has both; other outcomes have null payload and a failure object containing
`code`, `message`, and nullable `retry_after_seconds`. If the host cannot execute a
request, record the actual capability gap. If visible source data cannot satisfy
the bounded normalized format, use `failure` with `code: local_normalization_failed`
and its actual explanation. Do not relabel those cases as an empty successful page.

Payloads contain `results`, `next_cursor`, `total_count`, and `completeness`.
Results preserve provider order with exact 1-based ordinals. Every result contains:

- `ordinal`, canonical `ids`, and explicit `identity_links`;
- nullable `title`, `summary`, `published_at`, `cited_by_count`, and `provider_score`;
- `authors`, a visible HTTPS `locator`, and the requested operation as `relation`;
- nullable `referenced_ids` and `related_ids`, distinguishing unknown from empty;
- `mirror: {group,provenance,reason}` with honest known/unknown source grouping.

Each identity link has `left`, `right`, `relation`, and `locator`; both endpoints
must occur in that result. Only `same_work` joins identifiers. `preprint_of` and
`published_as` remain observed relationships. Co-occurring IDs alone do not join.
Every hit must contain a supported identifier; this profile cannot turn an
unidentified Web hit into a fabricated candidate. Provider scores are canonical
decimal strings for display, and never enter ranking arithmetic.

Use the installed `discovery-common.v1.schema.json` definitions for the full closed
nested shapes and limits. The schema registry includes all twelve artifact kinds,
plus the common definitions. Stored envelopes use JCS with integer numbers only,
a content-derived `rw3:<kind>:<digest>` ID, and exactly one final newline. A shape-
valid envelope is insufficient: every command also replays the entire retained
reference graph, deterministic projections, budgets and operation lineage.

Once all reserved requests have terminal observations, `context` supplies the
complete cumulative evidence set and assessment prompt. `assessment.json` contains
`lenses`, actual `generator` identity and caller-supplied `recorded_at`. Each lens
has `lens`, `state`, the exact configured `scope`, `statement`, `evidence`, and
nullable `reason`. Covered lenses require an exact title/summary citation with
`observation`, `ordinal`, `field`, Unicode-codepoint `start`/`end`, and
`excerpt_sha256`. A not-applicable lens needs a scope-specific reason and no invented
citation. A gap needs a reason. Every coverage assessment remains provisional;
request success, titles and citation counts do not establish scientific coverage.

## Ranking, continuation and stopping

The default schedule interleaves lookup, reference, citation, related-work, topic
and project operations. There are exactly two topic jobs per lens, using OpenAlex
and Web, with seed provenance assigned cyclically. Metadata lookup and observed
neighborhoods enable later requests. An unavailable identity or neighborhood stays
visible as a capability entry. OpenAlex targets use a fixed endpoint, explicit
select fields, canonical query encoding and supported filters. Web targets are
closed search descriptions. The CLI cannot follow arbitrary response links.

Candidate identity components preserve every observed version, provenance and
namespace conflict. Conflicted components remain visible and are excluded from
ranks, preview and expansion. A candidate key hashes its complete canonical
unversioned identity set; later aliases can change the current key while prior
snapshots remain immutable.

Each retrieval list is provider + seed + lens + operation across all pages and
rounds. List ordering uses matches, depth, known citation counts, known dates,
provider ordinals and candidate key. Reciprocal-rank fusion uses exact rational
arithmetic. Known mirrors collapse across all lists; unknown independence is
weighted conservatively. Contributions, mirror classes and every suppression
reason remain in the rank artifact. Similar titles do not establish a mirror.

Plain jobs are attempted when their plan slots are committed, even if their files
are not yet materialized or their outcomes fail. No automatic retries or cursors
are generated. An optional `plan --specs-input specs.json` accepts an exact eligible
specification set, or a validated retry, actual next cursor, or unseen canonical
neighbor-ID slice. All consume new reserved slots; an explicit set is all-or-reject.
Default planning chooses the largest feasible prefix without skipping earlier jobs.

After available direct jobs are attempted, at most three candidate selections may
introduce bounded expansion at depths one and two. The first committed expanded
plan slot retains the selection's origin, seed and depth. Later aliases or merges
never refund historical selection or completed candidate charges.

Calculated stop reasons, in precedence order, are exhausted budget, provisional
path coverage, repeated-result ratio, and low yield. Duplicate and low-yield stops
require consecutive completed rounds. Ratio equality qualifies; zero-hit rounds
do not count as duplicates. Empty available scope is reported as `needs_scope`,
without an empty plan or a fabricated scientific coverage claim.

## Recovery and explicit decisions

```sh
vpwiki-research discovery resume --session video-study
vpwiki-research discovery control --session video-study --action user_stop \
  --event-id stop-001 --user-text 'Pause this research session' \
  --source user_message --recorded-at 2026-09-09T12:00:00Z
vpwiki-research discovery control --session video-study --action resume \
  --event-id resume-001 --user-text 'Resume this research session' \
  --source user_message --recorded-at 2026-09-09T13:00:00Z
```

Use actual user instructions and timestamps. `fixture` is reserved for explicitly
synthetic tests. Plain `resume` only repairs deterministic files and reports pending
work; it creates no user instruction, assessment, new plan or external request.
An active user stop blocks research mutations; an explicit resume clears only that
control, without changing immutable budgets or calculated stopping decisions.

Interrupted initialization can reconstruct the session from its retained config.
Interrupted plans retain every reservation. Interrupted assessment/projection writes
recover exact bytes, with the final round event installed last. Every command uses
one nonblocking checkout-directory lock held through retained descriptor cleanup.
A busy process returns `DISCOVERY_BUSY` with exit 75 before observing `.work`.
Other malformed, conflicting or unsafe inputs return structured refusals. Reads
never create missing parents. No command deletes or overwrites artifacts.

Physical reservations promise enough space for all children of one pending plan:
14 MiB total, with explicit family and file-count reserves. Actual family storage
is limited to 32 MiB and total storage to 64 MiB. Those physical limits can stop a
session before every independent semantic maximum is reached. Before accepting
any observation, the prospective cumulative candidates and rank must also fit;
rejected observations leave the reserved request pending.

A completed candidate can receive an explicit `decide` action of `preview`, `skip`,
or `later`. Supply `--candidate-set`, `--candidate-key`, the same instruction fields
as controls, and `--selected-arxiv` only for preview. Preview selection must name an
arXiv identity/version actually observed in that nonconflicting snapshot.
`handoff --decision <exact-decision-id>` returns the existing W1 preview request
and command descriptor, without writing a W1 artifact or admitting a formal source.
The caller executes that separate preview workflow explicitly. Human review,
source admission, code provenance, formal publication and real Vault application
remain separate, auditable operations.
