# T2 revision 5 — last pre-move stage check

Surgical correction to stopped R4 snapshot
`e11be2214f411547295c8947245e56cbb05d9fe8600f94c9994244b5219ed2bf`.
Original contract/baseline and nine owner paths remain unchanged. Preserve R4
and every earlier source/evidence bundle. This is not a new broad implementation.

R4 closes every previously reproduced pre-extraction/post-extraction failure.
Architect replay now passes 65 of 68 checks. Three failures introduce unknown
file, empty directory or modified lock at the existing `before_old_archive`
boundary: they are preserved and a closed result is eventually returned, but
the old live paper has already moved. At `light_library.py:1516-1543`, the exact
stage/producer checks run BEFORE archive metadata writes and the hook, followed
by `os.rename` with no post-hook stage check. R4 requires complete validation
immediately before old-payload movement.

Repeat or place the existing complete stage inventory/producer validation AFTER
`run_library_inject("before_old_archive")` and immediately BEFORE the old-live
rename. A mismatch returns the existing closed conflict/recovery result with
all unexpected content intact AND the old paper still live. Reuse the existing
R4 validators; do not weaken them, move/disable the hook, or rewrite the workflow.
Also keep the exact old-payload check at this final boundary so a late old-paper
edit is not knowingly moved based on a stale check. Preserve ordinary replacement
and all interruption/recovery paths; no new public interface or backup changes.

Only `src/video_paper_wiki_research/light_library.py` and
`tests/research/test_light_library_recovery.py` may change relative to stopped R4.
Other seven owner files must remain byte-identical R4, although the new handoff
still inventories all nine changed-vs-baseline owner files. Port the six cases
from Architect acceptance SOURCE `architect_t2_r4_premove.py` into owned synthetic
tests (both `after_replace_staged` and `before_old_archive`), plus a meaningful
late old-payload-change refusal if needed. Do not read/run the real-PDF corpus.

Run the three owned test files and related existing PDF/recovery/index/workspace/
workflow tests with locked source-local Python 3.13 per COMMON. Do not weaken
assertions or add skips. No broader audit or extra feature work is requested.

Freeze fresh `terminal-2/r5` files/checks/report/handoff/ready binding this revision,
original contract and exact R4 input. Normal E write once; if denied, complete
source-local R5 and report the location without an alternate-method copy retry.
Stop source writes after the handoff. No T3 import, Git or final acceptance.
