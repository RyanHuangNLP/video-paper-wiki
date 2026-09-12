# T2 revision 6 — retain regular nested paper notes

Baseline, original library contract and T2 ownership remain unchanged. Preserve
the stopped R5 snapshot and every earlier candidate/review. This packet becomes
dispatchable only with its exact `t2-r6-freeze.json` and Architect instruction.

The accepted-backend overlay found one remaining integration gap: a valid paper
with `nested/example.py` is refused by `archive_paper` because the shared live
paper classifier rejects every directory extra before complete inventory.
The independent eight-case cross-feature run passed seven and failed this case.
Ten additional focused checks reproduced five affected positive paths (listing,
archive/restore and replacement, including interrupted recovery), while five
unsafe-extra refusal cases passed. These are one shared classification defect.

The contract already requires complete regular paper directories, retained
text/code notes and complete file/directory inventory. This is a correction to
that requirement, not a new content format or a contract change.

## Bounded ownership and behavior

Only these three paths may change relative to the stopped T2 R5 bytes:

- `src/video_paper_wiki_research/light_pdf.py`
- `tests/research/test_light_library.py`
- `tests/research/test_light_library_recovery.py`

All other R5 owner files remain byte-exact. R6's final handoff still contains
the complete nine-path T2 changed-file manifest relative to packet baseline.

Correct the shared **live-paper** `classify_paper_dir` so a valid source pair
may coexist with regular nested files and directories, including empty regular
directories. Preserve the source pair's current identity/content checks and the
meaning of its returned fields. Inspect descendants without following symlinks;
unsafe/nonregular/hardlinked entries and inspection failures must not become a
complete live paper. Avoid recursive Python calls and silent skipped traversal
errors. Keep this a live tree/type classifier: archive's existing complete scan
still enforces its text/code extension, UTF-8, per-file and total-size policy.
Do not unexpectedly apply archive-specific text restrictions to unrelated old
native behaviors. If a new interface or resource limit is required, report it
before adopting it.

All shared consumers must remain consistent: library list and workspace
inspection show the valid paper, metadata updates preserve nested notes, native
same-PDF reuse leaves them intact, and archive/restore/replace/recovery preserve
the complete file/directory inventory. Replacement keeps nested old notes only
in the old archive with the existing prior-note attribution mechanism.

The native `_validate_payload` and transaction staging semantics remain EXACTLY
two generated source files. Do not loosen generated PDF/replacement staging,
the R5 before-old-archive ownership checks, archive inventory validation, backup
validation, unsafe-extra refusal, or any old assertion to make nesting pass.
Do not edit T1, T3, other owner paths, dependencies, schemas, catalog or Vault.

## Regression and verification

Add synthetic-PDF repository regressions for regular nested UTF-8 Markdown/code,
empty directories, current list/workspace classification, metadata preservation
and exact native reuse; complete archive/restore/retry; replacement retaining
all old nested notes and empty directories; and recovery after archive move,
restore move and old-paper archive. Include symlink file/directory, hardlink,
binary and oversized nested extras as refusal/preservation cases at archive.
Keep producer/staging negative regressions active. Do not read Architect's
protected real corpus or authored documents; their independent tests run later.

Run the three existing T2 owned library/recovery/backup suites and related
native/index/workspace/workflow suites with exact T2 source provenance, the
locked Python 3.13 environment, short real temporary paths and offline flags.
No full integrated product suite is required inside this bounded owner fix;
the final T3 successor and Architect will test the combined source.

Publish new immutable `terminal-2/r6` handoff/ready, checks/report and all nine
exact changed owner files. Bind R5 snapshot, original contract, R6 freeze and
actual test results. Confirm the other six files are unchanged from R5, set
`stopped_writing=true`, `architect_accepted=false`, and stop. A normal evidence
write denial permits a complete source-local bundle/location report only;
do not retry a denied write through another method. No Git, PR/CI or merge.
