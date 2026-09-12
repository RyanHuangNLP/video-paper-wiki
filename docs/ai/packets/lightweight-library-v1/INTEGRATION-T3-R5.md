# T3 revision 5 — exercise Unicode filenames through installed backup

Dispatch only after t3-r5-freeze.json binds the stopped R4 candidate and the
Architect-accepted T1 R4/T2 R8 owner inputs. Preserve R4's complete source bundle,
reported Unicode defect, ASCII fixture workaround and successful tests as
historical evidence; none supplies final acceptance for this successor.

Verify all eleven current T3 owner paths against the stopped R4 bundle and all
fifteen imports against accepted T1 R4/T2 R7. The explicit successor handoff may
replace only the two imported T2 R8 paths named by the new freeze:
light_backup.py and test_light_backup.py. Keep every other import exact. All
fifteen imports remain read-only afterward; do not modify backend implementation.

T2 R8 corrects one supported-content gap: deterministic ZIP verification accepts
the stdlib writer's UTF-8 filename flag consistently in both headers, while
preserving all unsafe metadata refusals. Extend T3-owned actual-CLI pipeline and
fresh isolated installed-wheel coverage to use non-ASCII nested note paths,
including Chinese Markdown and Greek code-note names, through library
archive/restore, same-paper replacement/recovery, backup create/verify/restore
and reuse. Assert exact names and bytes of the old notes retained in the archive
and restored backup. Include an explicitly selected outside-workspace Markdown
report with a Chinese filename in a backup roundtrip. Keep the ASCII controls,
knowledge imports/views, cited comparison, source-staleness checks and historical
workflow session checks. Empty directories are preserved by library archive/
restore; the contract's file-only ZIP does not promise empty-directory entries.

Remove the R4 fixture workaround as the reason to avoid non-ASCII paths. Do not
rename, drop or restrict user filenames to make verification pass. Do not modify
the main CLI unless a concrete T3-owned integration defect is demonstrated;
report backend issues to Architect and pause only affected work. Update the
owned quickstart/reference only if needed to accurately document the behavior.

Run all focused integration checks, the official Skill validator, a fresh
installed-wheel operation suite with site-packages/byte-hash proof and isolated
empty PYTHONPATH, and the complete tests tree on both locked Python 3.12.14 and
3.13.13. Exercise both the isolated module entrypoint and installed
`vpwiki-research` console script; run actual backup verify/restore and at least
one library maintenance action through the console script, beyond a list smoke.
The R4 installed-operation breadth and explicit dual UV cache settings
from INTEGRATION-T3-R4.md remain required. Do not use old wheel or subset results
as final evidence. Preserve each actual command exit and full count.

Publish a complete terminal-3/r5 bundle: all eleven original T3 owner files
relative to original baseline, all fifteen separate accepted owner import hashes,
checks/report, R4 and R5/contract binding and byte-identical handoff/ready. Set
stopped_writing=true and architect_accepted=false, then stop. A normal evidence
write denial permits a complete source-local bundle and location report only,
without retrying the denied copy. No Git/PR/CI, merge, Vault, real-PDF/model-document
reads, extra workers or model/dependency/default changes. Architect runs the
separate local three-real-PDF/current-model trial after independent acceptance.
