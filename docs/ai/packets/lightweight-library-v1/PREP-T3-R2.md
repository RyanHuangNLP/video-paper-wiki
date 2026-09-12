# T3 revision 2 — independent CLI/input/documentation corrections

This is an independent preparation packet while T2 R3 is still writing.
It authorizes only the original eleven T3 owner paths at baseline
`3368c6435db166a285b4b0e2df00f5d6a7491956`, under original contract
`7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12`.
Do not import ANY T1/T2 owner files in this packet. T1 R4 is accepted separately,
but complete integration waits for both frozen accepted owners and a later exact
input handoff. Preserve the immutable source-local T3 R1 bundle.

Read the independent review in terminal-3/t3-r2-integration-review-r1.json and
the Architect resolution in INTEGRATION-T3-R2.md. This PREP packet applies only
the independent CLI/Skill/documentation corrections from that integration plan;
the full backend pipeline, dual suites and installed wheel remain future work.

## Implement now

1. Add bounded safe loading for the NEW knowledge/compare JSON inputs. Validate
   every parent/final path edge before resolving away evidence, regular file type,
   no symlink/hardlink, 8 MiB bounded read, strict UTF-8, top-level JSON object,
   duplicate keys and nonfinite numbers. Expected input errors are JSON/nonzero
   with no backend mutation. Explicit read-only JSON files may be outside `.work`.
   Skill-generated JSON stays under `.work`. Keep legacy qa/writing/workflow input
   behavior unchanged. Catch known input failures in scope, not arbitrary bugs.

2. Preserve caller-selected extra Markdown path safety until the backend checks
   it. Do not resolve away a symlinked input parent and pass the sanitized path as
   if it had been safe. Read-only extras may be outside `.work`, but must be
   explicit safe regular `.md` inputs, with no symlink/hardlink and 8 MiB strict
   UTF-8 limits. No arbitrary external directory/receipt scanning. The later T2
   backend handles workspace-vs-extra identity and capture validation. Generated
   workspace/Markdown/backup/restore output paths remain under `.work`.

3. Expand owned CLI routing/input tests for these cases, including missing,
   malformed, non-object, duplicate-key, NaN, parent/final symlink, hardlink,
   directory/FIFO and oversized files plus successful valid wrappers and an
   explicitly selected outside-.work input. Use synthetic fixtures. If owner
   modules are stubbed, label those checks honestly as routing/input tests; do
   not claim they prove a real backend pipeline or final acceptance.

4. Update Skill/references/quickstart/README to reflect saved export-object JSON,
   ordinary users not authoring internal documents, the file/size policy, file-only
   empty-directory backup semantics, original PDF exclusion, reindex/reprepare,
   and an aborted-before-staging result meaning no replacement. Read skill-creator
   instructions as required by TERMINAL-3. Preserve natural-language routing and
   all existing canonical/Vault and qa/writing boundaries. Use actual CLI help.

The existing cached PyYAML path for the official skill validator is recorded in
INTEGRATION-T3-R2.md. Use it without installing a product dependency or inspecting
unrelated account/config files. Do not rewrite or weaken existing legacy tests.

## Stop with honest intermediate evidence

Run the owned CLI/input tests, independent documentation checks and relevant
existing CLI tests using the locked source-local Python 3.13 / short real temp
recipe. Do not run or relabel the R1 missing-backend installed-wheel smoke as
integrated acceptance. The dependency-pending full-pipeline marker can remain
for this PREP revision; the later integration packet must remove it and run real
backends through successful and rejected operations and both installed entrypoints.

Publish a fresh immutable terminal-3/r2 bundle with all changed owned files and
checks/report/handoff/ready. Set `dependency_pending=true`,
`ready_for_final_acceptance=false`, `architect_accepted=false`,
`stopped_writing=true`; status may be `ready_for_architect` for this bounded PREP
review only. Bind R2 freeze, original contract and previous R1 snapshot. No owner
imports in inputs, no full-suite/wheel/CI/real-paper acceptance claim.
If normal E writes are denied, keep a complete source-local r2 bundle and report
it, without retrying a denied copy via another method. Then stop all source writes.
No Git, merge, new worker, model/dependency change or human gate closure.
