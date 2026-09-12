# Agent 2 r3 repair addendum — malformed context shapes

Read with REPAIR.md; same contract B and same five-file ownership. This is additional reproduced evidence for finding T2-R2-2, not new scope.

Independent review and Architect replay found `validate_live_context` returns OK for a successful context with missing evidence, evidence=null/0/false/empty-string, or missing query. See `schema-probe-results.json`. `context.get("evidence") or []` normalizes invalid inputs into an accepted empty collection instead of checking their type.

Validate the required existing light-context.v1 fields and their types before consuming them. Missing/wrong-type required fields must return LIGHT_CONTEXT_INVALID; legitimate legacy contexts without the optional selected_paper_ids field remain supported. A successful usable context must have actual well-shaped evidence. Do not rely on the later renderer failing to make validate_live_context truthful. Add focused direct-validator and import regressions alongside the malformed kind/index cases in REPAIR.md.

Include this addendum and its SHA in the new r3 handoff inputs. Preserve both original r2 evidence and these read-only review files.
