# T1 R2 repair draft — not dispatch authority

T1 R1 stopped snapshot is
b7554d0e8542d779de1a2b0fa4ed4b113fc2c1853627648d5873dcf4b53f39e0.
Its 63 focused passes remain historical evidence. Architect review
artifacts/verification/manual-pdf-v1/lightweight-research-v1/terminal-1/architect-review-r1.json
(SHA-256 b1fcf5a42769026fc5e801c49874347df23d762e51f9b8cf402b993f140fd50f)
verified the six stopped file copies and reproduced the contract failures below.
R1 is CHANGES_REQUIRED, not accepted. Preserve all R1 source/evidence copies.

Pending independent review may add a concrete finding before the exact R2 freeze.
No new Cursor invocation is authorized by this draft: the rejected external
launch requires the pending informed user confirmation. Do not bypass or route
through another process/model. Root/Luna do not implement these fixes.

Required bounded repairs under the unchanged contract:

1. Validate route status types before set membership. A caller-supplied [] or
   object must return LIGHT_CONTEXT_INVALID rather than TypeError through
   validate_live_context/render/import. Cover the other trace enum/type paths.
2. Bound numeric conversion/checking so an integer such as 10**400 in a candidate
   score returns a closed invalid result, never OverflowError. Keep boolean,
   nonfinite and mismatched score checks; do not normalize untrusted malformed
   scores into apparently valid ranks or evidence.
3. Reject duplicate paper IDs on the new rewrite route before calling the legacy
   normalizer that silently deduplicates. Preserve ordinary legacy search/export.
4. Enforce the new workspace contract before losing the caller's given path:
   .work in given and resolved paths, no symlink in any parent/final edge.
   A symlinked parent with an ordinary final directory is currently accepted,
   as is a workspace completely outside .work. Both must refuse.
5. Acquire the existing nonblocking workspace lock for the new public rewritten
   export, return LIGHT_WORKSPACE_BUSY when occupied, and release on every exit.
   Raw retrieval/trace validation helpers must not recursively reacquire a lock
   already held by a caller. Do not change old workflow session kinds.
6. Reject hardlinked source.md/source.json and other unsafe live source edges
   before export and again on live import of a traced context. Actual source
   hashes do not substitute for the existing regular-file/link rules.

Apply given-path/source checks throughout the new traced-context path, including
legacy render/import entrypoints when query_plan is present: checking only after
_require_workspace has resolved a symlink loses the original unsafe edge.
Untraced legacy behavior remains compatible. Reuse existing strict helpers where
appropriate and keep imports acyclic; do not silently redefine another lane API.

The next freeze will keep the original six-path T1 owner set. Add meaningful
regressions for these cases and re-run focused query/context/index/QA/writing
tests with exact SOURCE pytest provenance. Assert expected closed statuses and
unchanged preexisting output bytes, not just absence of exceptions. Return fresh
r2 immutable files/checks/report/handoff/ready and stop for independent review.
