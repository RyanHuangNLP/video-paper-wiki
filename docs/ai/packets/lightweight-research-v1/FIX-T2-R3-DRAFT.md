# T2 R3 bounded raw-path repair draft

Stopped R2 snapshot is
202c7fffafa4589f9a8db21fbf6f4ecc97a48c38f2f49b241dc319999da88532.
Architect independently ran its exact four test files: 108 passed, recorded in
terminal-2/architect-focused-r2.json. Independent erratum
terminal-2/independent-review-r2-erratum.json preserves the prior review and
records eight correctly source-bound regression passes plus one new blocker.
No R2 acceptance or integration is issued. Preserve all R1/R2 evidence.

The raw workspace .work/link/../ws passes batch plan/export/import/merge/finalize
and refresh-plan even though link is a symlink. light_knowledge._absolute_path
calls normpath before require_product_workspace can inspect the supplied edges.
The given and actual resolved workspaces can also differ when link targets an
external directory. This violates CONTRACT shared paths; ordinary success and
self-consistent plan hashes do not waive the original path check.

Repair this one raw-path class in the existing T2 eight-path ownership, without
changing public APIs, schemas, selection/merge/refresh semantics or other lanes.
The expected production edit is light_knowledge.py's shared path validation;
only directly needed same-scope regression tests should otherwise change.
Check the raw supplied workspace/output edges before normpath or resolve erases
them. Rejecting any raw '..' component at these product path boundaries is
acceptable. Keep normal absolute and relative .work workspaces usable. Check
the supplied and resolved .work boundaries and ordinary symlink/hardlink rules.
All new batch/refresh public APIs, listing/blocker reads and output helpers must
inherit refusal, not just plan creation. Expected refusals are closed statuses
and cause no creation/deletion/modification of plans, HEAD, notes or outputs.

Add regressions for a raw symlink/../ws whose real resolution differs from the
normalized existing workspace, a same-target raw symlink traversal, plain raw
parent components, safe normal paths, and existing output sentinels. Preserve
all R2 complete-inventory/zero-refresh/ancestry/merge/finalization tests. Run
COMMON's exact-source four-file knowledge/batch/refresh/backup scoped suite,
with absolute test paths, -c, --rootdir and -o pythonpath=ABS_SOURCE/src. Record
module __file__, interpreter, command, cwd, source hashes and actual result.

Evidence clarification: the prior R2 handoff lists eight source files but its
files directory has only seven copies (light_backup.py retained its R1 bytes).
Do not modify that history or describe the missing copy as present. For R3,
freeze and copy ALL EIGHT cumulative owned source/test files relative to BASE,
even when an individual file is byte-identical to R2. Each handoff row must
have a byte-exact counterpart under terminal-2/r3/files. New checks/report/
handoff/ready bind the R2 review erratum and this R3 freeze. Handoff and ready
must be byte-identical; architect_accepted=false and stopped_writing=true.
Stop writing after handoff. No Git/CI/PR/CLI/Skill/other-lane work in this repair.

This draft is not a dispatch. Root will freeze the reviewed bytes and issue the
exact prompt under existing informed user authorization and normal approval.
