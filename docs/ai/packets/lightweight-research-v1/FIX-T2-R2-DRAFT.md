# T2 R2 repair draft — no dispatch authority

R1's existing approved Builder is completing its first handoff. This draft is
not an acceptance, source ownership transfer, or permission for a new external
run. Bind the actual stopped source and independent review before a later R2
freeze. Preserve all R1 output and the active-source preliminary observations.

The original CONTRACT and eight TERMINAL-2 source/test paths remain unchanged.
Root and controllers do not implement the fixes. T3 receives no T2 files yet.

## Reproduced preliminary blockers

Architect's terminal-2/architect-preliminary-publication-r1.json records exact
before/after hashes and two disposable-fixture reproductions:

- An interruption after HEAD changes but before completion publication leaves
  the original job permanently pending. Exact finalize retry rejects the head
  that this same job just produced. Recover this recognized own publication
  from validated immutable inputs, while rejecting a different intervening
  head. Never report failure as though the old HEAD were preserved if it moved.
- Replacing completion.record_id with a nonexistent valid-looking ID makes
  finalize return OK/current/reused and a nonexistent page; backup reports no
  blockers. Completion must bind the actual expected record, full immutable
  bundle and job output, rather than treating a well-shaped hash as proof.

Architect's terminal-2/architect-preliminary-provenance-r1.json records:

- A completed job with an unknown empty directory is accepted as completed and
  includable. Validate the entire directory and file layout, retaining unknown
  material and returning a conflict, including zero-batch and interrupted jobs.
- A self-consistently rehashed record with changed knowledge prose but the
  original unchanged job/final merge is accepted by public list as current.
  Bind each extended record to the actual expected job/merge document, complete
  inventory, source snapshot and provenance. A caller-computed bundle hash is
  not authority to substitute different content. Selection records must bind
  the checked base/candidate and exact accepted fields through the same rule.

Independent review is checking complete partitions, durable merge-chain links,
citations and record ancestry. Incorporate only its concrete findings in the
final repair specification; do not silently broaden interfaces.

## Required verification

Replay each finding against the stopped R1 before accepting it as an R2 blocker.
Use real backend fixtures for publication interruption after record, after HEAD
and around completion; identical retry must finish or return an accurate closed
state. A different head, bad record, bad chain or unknown layout must refuse and
preserve all existing bytes. Check history after backup relocation separately
from live source/index resumption. Do not make pending jobs includable merely to
hide a retry failure.

Re-run scoped batch/refresh/knowledge/backup tests with COMMON's exact source
origin and runtime. Add regressions that fail on R1 and check public outputs and
unchanged user notes, not only private helper predicates. New immutable r2
evidence and stopped review are required; old 94-test results identify R1 only.
