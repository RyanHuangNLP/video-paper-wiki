# DOMAIN acceptance preparation supplement

Read with R1. This incorporates the four review findings in
`resources-r1/instruction-only-r1/I/domain-preparation-review-r1.json` and PRD
R3.3 sections 7.1, 7.2, 8 and 10. It is preparation, not a source freeze or
Builder dispatch. The resource integration work remains independent.

## Typed vocabulary and history

Bind the eight typed concepts Method, Model, ArchitectureComponent,
TrainingRecipe, Dataset, Benchmark, InferenceRecipe and EvaluationMetric.
Bind the nine claim_kind values architecture, training, empirical_result,
implementation, ablation, limitation, reproducibility, license and
resource_requirement independently of assessment and freshness. Unknown terms
become normalization proposals. Preserve taxonomy v1 bytes; v2 requires its own
migration and review. Exercise immutable claim IDs, annotation/review history,
superseding heads and projection rollback without rewriting the claim ledger.

## Paper/code officiality

The eventual compatible relation-review contract must retain separate evidence
classes: A, paper explicitly linking its implementation; B, paper-linked project
page explicitly linking the implementation; C, exact reverse paper citation in
README/CITATION; D, verified author identity/control evidence. Save each source
locator and implementation-versus-baseline context. Similar account names or
organization membership alone do not establish D or an implementation relation.

Cover credible direct release with no reverse citation and verified author
control plus an explicit repository-side statement with no paper backlink.
Accepted review must record the relationship evidence, missing evidence and
reason for acceptance. A reverse citation alone does not imply officiality;
missing A/B does not imply unofficiality. Explicit third-party reproduction
supports unofficial; insufficient evidence stays unverified_candidate. Project
page/README evidence needs a compatible extension linked to the existing
alignment and transaction receipt; never insert new locator types into the
closed legacy alignment schema. Code-proof success alone cannot close this
review or the source-association verification gate.

## Query, answer and stale behavior

Preserve intent values quick, standard, compare, implementation, reproduce,
survey and research, with entity/filter support for model, task, year,
resolution, benchmark and code availability. Bind answer/synthesis proposals to
the exact context, runtime/model, prompt and input summary. Separate factual
units, inference, dispute and unknowns; support review binds each exact unit to
claim, locator and original span.

Keep CATALOG_STALE and RETRIEVAL_GENERATION_MISMATCH as refusals. Changed,
missing, stale or unknown required generations block a current-library answer
and expose the existing operator rebuild action. Unrelated receipt changes
still require actual dependency checks. Exact uncovered source-version sets
require a complete auditable difference; otherwise expose coverage_unknown.
Legal query exclusions remain excluded_by_scope, separate from index omissions.

## Explicit QUALITY handoff

DOMAIN engine tests cannot satisfy the real qualification gates. The separate
QUALITY contract must freeze W5a's at least 10 answerable and 3 unanswerable
questions; W5b1's at least 6 comparisons including 2 not_comparable cases; and
W5b2's independent at least 20-question six-category benchmark. Bind corpus,
source versions, question/point IDs, truth, rubric, reviewer events and evaluator
version before qualification dispatch. Preserve development/qualification and
exposed-regression/holdout distinctions.

Register three actual independent generation rounds for each required slice.
Each answer round requires 100% supported factual units, at least 80% coverage
per answerable question and 90% overall; judge the minimum across rounds and
report median/range. Article/reproduction review retains the frozen full core
and sampled remainder scope. No cached answer copies, retrospective denominator
changes, fabricated semantic approvals or unrecorded selection of best attempts.

The complete paper Recall@5 gate needs at least 30 eligible deduplicated papers
in the declared representation. The new evidence-unit Recall@10 track needs
at least 20 actual non-gold retrievable units per question across 3 papers,
including 5 reviewed hard negatives and, where possible, 5 same-paper negatives.
Insufficient evidence remains not_informative/not_evaluable. Keep the 67
metadata-only seed records in their explicit discovery track. Version the new
@10 evaluator separately from historical evidence_recall_at_8. The configured
recall thresholds remain 0.85 and 0.75 under these applicability conditions;
engine fixtures cannot prove those real-corpus thresholds or semantic review.
