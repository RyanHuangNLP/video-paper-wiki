# Independent Terminal 1 review — Contract A

Decision: **CHANGES_REQUIRED** for the frozen Terminal 1 R2 snapshot.

Reviewed source root: `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-1/source`

R2 handoff binding: `artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-1/handoffs/r2/handoff.json`; baseline `0fcae592acb977c6b422e7de3b2c3e0cf79df5a0`; contract `559e2b339c192837fa5d6c47f15ea7688f484155b95b2492f28eeee6d940e5dc`; freeze `2128528583787cb10aad69eb1954b424bba10873327885792dce7c7e3ae3099e`.

## Hashes checked

- `light_pdf.py`: `d51551b81939039114ebb208eb94db5ae48dc84f42b785ed9597542674e96770`
- `light_workspace.py`: `a166be3a82d2bd62223fbf1196bef7540514f816552e36487eb15f336f8929f2`
- `test_light_pdf.py`: `db5efdd709a9e9df63582e731f9653127dd8b38c04c1b62dc6e905ae9ab3808a`
- `test_light_pdf_recovery.py`: `28bf0645b17721360666495f9a7404306440682d29ce24dd5831e6d8672c76d0`
- `test_light_workspace.py`: `08a23596194a8732143a2b7ca88aea4f7776ea5cfba2a8215534894ccc1d7f65`

These match the R2 handoff file list.

## Validation

Using the shared project `.venv` and the Terminal 1 source `PYTHONPATH`:

`test_light_pdf.py`, `test_light_pdf_recovery.py`, and `test_light_workspace.py`: **29 passed**.

The same three plus `test_light_index.py`, `test_light_pipeline.py`, and `test_light_cli.py`: **48 passed**.

## Findings

### Blocker 1 — malformed Markdown can escape as a traceback

`_load_paper()` reads `source.md` with `Path.read_text(encoding="utf-8")`, but `classify_paper_dir()` catches only `ResearchError`. A damaged paper with invalid UTF-8 therefore makes both `extract_pdf()` reuse/recovery and `inspect_workspace()` raise `UnicodeDecodeError`, rather than returning a structured `SOURCE_INVALID` result or diagnostic. Reproduction: create a valid paper, replace `source.md` bytes with `b"\\xff"`, then call `extract_pdf()` or `inspect_workspace()`.

This violates Contract A's requirement that damaged entries be refused and reported as diagnostics, and the shared error convention's no-traceback expected failure behavior.

### Blocker 2 — recognized complete staging is published before content validation

`_recover_owned()` renames a recognized staging directory to `papers/<digest>` when it has exactly the two regular filenames, then calls `classify_paper_dir()`. If `source.json` or `source.md` is malformed, the invalid pair has already become the final paper directory. The function returns `SOURCE_INVALID` but leaves the invalid final pair in place. Recovery must validate the staged pair before publishing; a recognized ownership marker does not prove valid paper content.

Probe: create a valid ownership marker and complete two-file staging whose `source.json` has the wrong schema, call `_recover_owned()`, and observe `ok=false/SOURCE_INVALID` with `papers/<digest>/source.json` and `source.md` still present.

### Blocker 3 — transaction symlink can redirect lock state outside the workspace

`_prepare_workspace()` does not validate `.light-transactions`, and `_try_lock()` follows an existing symlink. With `workspace/.light-transactions -> /tmp/outside`, `extract_pdf()` succeeds and creates `<digest>.lock` under the outside directory. Transaction and lock state must remain inside the approved workspace and unsafe transaction paths must be refused.

### Finding 4 — valid empty index is reported as stale

After `build_index()` on a workspace with no papers, `inspect_workspace()` returns `state=empty`, `index_state=stale`, and the valid index ID. `_index_state()` only accepts `current` when `valid_papers` is truthy. The contract separates the empty state from index state; a structurally valid zero-paper index should be `current`.

## Conclusion

The normal and crash-injection test suites are strong, but the malformed-content and unsafe-path probes expose Contract A gaps. I recommend a T1 R3 before acceptance; no source or Git files were modified by this review.
