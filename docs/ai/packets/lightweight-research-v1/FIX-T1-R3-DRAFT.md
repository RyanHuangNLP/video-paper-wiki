# T1 R3 bounded repair draft

Stopped R2 snapshot is
7c2aea0be5b74eb394670625d4839381c444c471ccb9a8188fcad702ebee1992. Its 66
focused passes remain history. Architect's independent 40-case run passed 37;
terminal-1/architect-adversarial-r2.json records three OverflowError failures.
terminal-1/architect-dotdot-r2.json records the separate path bypass. Both
records bind the exact stopped source hashes before and after disposable probes.
R2 is not accepted; preserve all R1/R2 evidence and source copies.

Keep the same six T1 paths and unchanged CONTRACT. This draft is not a Builder
dispatch. Root will freeze reviewed bytes and explicitly dispatch under the
user's current informed authorization, with normal tool approval.

1. A traced context with evidence[0].score=10**400 must return
   LIGHT_CONTEXT_INVALID through validate_live_context, render_document and
   import_document. The legacy evidence-copy helper performs math.isfinite and
   still raises OverflowError before trace validation. Validate or safely close
   the malformed numeric evidence boundary for traced contexts before invoking
   that helper; preserve untraced legacy behavior and actual score equality.
   Cover boolean/nonfinite values and preserve preexisting output bytes.
2. Validate the actual supplied path edges before any lexical normpath erases
   them. A supplied real/.work/link/../ws, where link targets other/subdir,
   actually resolves to other/ws but R2 silently operates on real/.work/ws.
   Export/validation/render/import all return OK; import overwrites existing
   output. The new traced route must refuse this symlink/.. path before access
   or mutation. Rejecting any supplied parent-traversal component on this new
   route is acceptable; do not change untraced legacy semantics. Preserve
   ordinary absolute and relative .work paths without unsafe traversal.

Apply both fixes to all new traced-context entrypoints; checking only export or
checking only after the original path is resolved is insufficient. Add meaningful
regressions for the exact four path operations, the three evidence-score paths,
normal rewritten success, legacy compatibility and unchanged output on refusal.
No new public API, CLI or other lane path. Use COMMON's scoped exact-source
query/context/index/QA/writing tests, then return fresh r3 immutable
files/checks/report/handoff/ready and stop. Source acceptance and integration
remain separate Architect decisions.
