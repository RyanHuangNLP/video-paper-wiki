# DOMAIN acceptance preparation

This is Architect preparation for the already authorized DOMAIN TODO. It is
not an interface freeze, a Builder handoff, or acceptance of public CODE.
The existing CODE resource repair continues independently. Reconcile these
cases with the accepted public CODE interfaces before freezing DOMAIN files.

Inputs are the full-TODO README, PRD R3.3 sections 7.1, 8 and 10, and the
preserved `code-proof-v1/domain-dependency-audit-r1.json` with its correcting
`domain-dependency-audit-supplement-r2.json` in the verification artifacts.
The supplement governs DOMAIN-03/09: provisional cited comparison, live source
contexts and original/rewrite RRF already exist. Preserve these APIs.

## Cases to bind to the eventual contract

| Area | Required observable cases |
| --- | --- |
| Profile authority | An immutable profile is selected through a published head. A query argument cannot select another profile. Missing, changed or mixed heads cannot yield a current supported fact. A new profile preserves the old version and does not expand taxonomy v1 in place. |
| Annotation authority | The proposal binds claim text, evidence fingerprint, assessment head and profile. Accepted annotation review alone is insufficient when the claim assessment is not accepted. Change each bound input independently and verify the prior result is no longer current. A legacy claim with no annotation remains queryable without being presented as a supported typed fact. |
| Experiment conditions | Individually cover source version/artifact hash, model/checkpoint, active/total parameters, resolution, frames/FPS/duration, steps/CFG, benchmark version/split, zero-shot/fine-tuned, teacher/student, training-data scope, hardware, unit and metric direction. Missing or conflicting required context yields not_comparable with explicit reasons. Zero is not a substitute for unknown. Only profile-authorized equivalences may normalize units or conditions. |
| Relations | Predicate rules check endpoint types and referenced evidence. Supporting and opposing evidence remain distinguishable. Similarity, co-occurrence and mismatch detection produce candidates without changing claim assessment or publishing a factual contradiction. A reviewed relation must preserve locators on both sides. |
| Paper/code relations | Consume the accepted CODE proof and review interfaces. A repository URL, matching owner name or config filename alone cannot establish officiality, correspondence or scientific equivalence. Cover the reviewed positive branch as well as unverified and explicitly unofficial branches. |
| Publication | Prepare and inspect the annotation, review and selected head through the existing transaction authority. Receipt, audit and backup cover every new managed namespace. Exercise failure before publication, replay, conflicting current heads and rollback to a prior projection without rewriting historical claims. Use isolated fixtures only for engine validation. |
| Projection | Two builds from identical complete inputs produce identical canonical output bytes. Input manifests include annotation/review/head, claim/assessment/evidence and profile/head dependencies. Independently remove or alter each dependency; reject or return the contracted non-current status. Reject mixed generations. |
| Retrieval fusion | Independently retain exact, BM25 and typed graph ranks, then apply the frozen deterministic RRF rule. Do not sum heterogeneous raw scores. Exercise ties, duplicate evidence reached through multiple routes, missing optional dense retrieval and paper/code evidence. Preserve existing original/rewrite RRF behavior. |
| Context budget | Bind every included and omitted item, rank, selection reason, locator and source hash. Cover exact budget, one unit over budget and no source text. Relevant counterevidence omitted for budget must remain visible as an unresolved coverage gap. The same snapshot/config produces identical bytes. |
| Freshness and coverage | Recheck the actual required inputs around query. Cover changed heads during query, stale graph/comparison/catalog generations and incomplete coverage inventory. Do not turn existing stale-generation refusals into warnings. Report coverage_unknown when a complete missing-source set cannot be established; scope exclusions are separate. |
| Compatibility | Existing provisional light_compare, live contexts, claim queries, taxonomy and the 67-entry seed remain valid. New typed results cannot be inferred from the existence of a provisional comparison document. |

## Evidence boundaries

Each negative case starts from an independently validated positive and changes
one relevant input, except explicit multi-fault precedence cases. Include an
end-to-end isolated publication/receipt/audit/projection/query example after
the schemas and pure condition rules have passed their focused checks.

Keep deterministic engine checks distinct from scientific review. Synthetic
fixtures can demonstrate contract handling; they cannot establish that real
experiments are equivalent or close the user's semantic gates. Prepare real
three-paper/one-repository material separately, retaining unknown conditions
and review decisions. The full corpus and frozen evaluation protocol remain
the separately authorized QUALITY item.

No product files, schemas, profiles, canonical records, Git state, running
model calls or existing acceptance evidence are changed by this document.
