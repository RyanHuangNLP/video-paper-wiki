# T1 r3 — bounded evidence-score and symlink/.. repair

Lane 1 Builder candidate against R3 freeze `9760f6627e59573428251a9723fe039ebe09b227f6db2e891f228c0a1b047e13`, repair specification `88eafd96da71e2fd81fd0fa7525b7313bb2d4348573b821bb5ff2afe15a7873c`, and unchanged contract `d1d1ddef4273e37b5f8e30a14ad22f3cb3e6c6fa9782763ed5544d20479f2fab`. Baseline remains `6963292a93ae322eaf9bb563b7b1170dee6a6fc6`. Stopped R2 snapshot `7c2aea0be5b74eb394670625d4839381c444c471ccb9a8188fcad702ebee1992` and its 66 focused passes remain historical. Architect has not accepted this candidate.

## Functionality

Both reproduced R2 defects are closed on every new traced-context entrypoint. Untraced legacy search/export/import keep their established behavior, including `math.isfinite` OverflowError on a huge untraced evidence score and lexical/resolved workspace selection without the new parent-traversal refusal.

1. A traced context with `evidence[0].score=10**400` now returns `LIGHT_CONTEXT_INVALID` from `validate_live_context`, `render_document`, and `import_document` before the legacy evidence-copy helper can raise `OverflowError`. Boolean, NaN, and infinite evidence scores are refused the same way. Valid rewritten evidence scores still equal the fused query-plan scores. Preexisting output bytes are unchanged on refusal.
2. The traced workspace helper inspects the caller-supplied path before any lexical `normpath`. A supplied `real/.work/link/../ws` edge, where `link` targets `other/subdir`, is refused with `WORKSPACE_INVALID` on export, validate, render, and import. Ordinary absolute and relative `.work` paths still succeed. Untraced callers are unchanged.

`light_index.py` and `tests/research/test_light_index.py` are byte-identical to stopped R2.

## Public result shapes

Unchanged from R2 except the two closed refusals above. Successful rewritten export still returns `light-context.v1` plus `query_plan`. Other closed errors omit `query_plan`. Legacy contexts without `query_plan` stay compatible.

## Files

Owned changed paths only; unchanged index files remain in the six-path snapshot:

- `src/video_paper_wiki_research/light_query.py`
- `src/video_paper_wiki_research/light_context.py`
- `src/video_paper_wiki_research/light_index.py` (unchanged from R2)
- `tests/research/test_light_query.py`
- `tests/research/test_light_context.py`
- `tests/research/test_light_index.py` (unchanged from R2)

Canonical six-path snapshot `5bf01318533d4e17beecd338fe4cd8f9c36392ebbb8c5b7b237351970410422d`.

## Tests

Pinned interpreter `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` (3.13.13) with `PYTHONPATH` set to this worktree `src`. Official focused command exit 0: **69 passed in 0.36s**. Modules resolved to this SOURCE, not the old root checkout. Disposable Architect-style probes reproduced `LIGHT_CONTEXT_INVALID` for huge/boolean/nonfinite traced evidence scores and `WORKSPACE_INVALID` for the raw symlink/`..` edge on all four path operations, with preexisting output preserved. No dependency install, no Git mutation, no Vault write, no model/network client. Probes were not edited.

## Unresolved issues

T1 R3 is not Architect-accepted. Independent review remains open. Stopped R1/R2 evidence is preserved. T3 still owns CLI/Skill/docs and `--rewrite` wiring. Dual-Python full suites, installed-wheel CLI, and real-paper/current-model trials remain later integrated gates.
