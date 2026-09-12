# Independent review: T1 comparison R1 and T3 acceptance

Reviewed immutable T1 R1 comparison source against the frozen lightweight-library-v1 contract.

- T1 source: `artifacts/verification/manual-pdf-v1/lightweight-library-v1/terminal-1/r1/files/src/video_paper_wiki_research/light_compare.py`
- T1 source SHA-256: `9e333f86b0bf42377704c3a587c3da5d470e1337f637a37e90d72613ec0d207d`
- Contract SHA-256: `7075cfb0a10e21448f942821dbae89028222161fbecca5b01f0feb06834fca12`
- T3 R1 snapshot SHA-256: `fc867e8c9031c7a273af07a026dc3c4ff1b9df0f2ca3656fd47d29edd3b09c6a`
- T3 R1 status: `dependency_pending`; 51 passed, 1 skipped because T1/T2 owner modules were not supplied.

## Findings

### Blocker: duplicate selected paper IDs are silently deduplicated

`_normalize_selected_papers` delegates to the T2 `_normalize_paper_ids`, which removes duplicates before the 2–8 selection bound is checked. A copied real corpus reproduced `export_comparison_context(..., paper_ids=[A,A,B])` as `ok=true` with only `[A,B]`, and `[A,A]` as a one-paper selection rather than a closed invalid selection. The contract requires 2–8 distinct selected papers and complete selection validation; caller-provided duplicates must not be silently rewritten into a different selection.

Reproduction used the accepted T1/T2 files and a temporary `.work` workspace. The public source corpus was not modified.

### Blocker: table citations are escaped before citation rendering

End-to-end `import_comparison` returned `ok=true`, but generated comparison table cells contained literal escaped citation marks such as `\\[@chunk\\]`; the source link appeared only in references. `_cell_markdown` appends `[@chunk]`, then `_render_comparison_markdown` applies `escape_table_cell` to the entire cell before `render_markdown`, so the citation marker no longer matches the renderer's citation replacement. The contract requires a readable Markdown table with linked citations owned by each cell's paper.

The reproduced temporary output had SHA-256 `cd42a577da51d4be477b4666b8ead11a571f1826ddabc8c896e91159ec9a80b3`.

### Blocker: conditions are double escaped in comparison cells

With `conditions='a|b\\nc'`, the generated cell escaped the pipe twice and escaped the `<br>` line-break markup. Conditions therefore render with incorrect text/formatting even though the structured result is accepted. The outer table-cell escape should not re-escape already-rendered condition markup.

### Review note: selection error code for a non-list

A non-list `paper_ids` argument currently raises `LIGHT_COMPARISON_INVALID`, while selection-invalid inputs otherwise use `LIGHT_SELECTION_INVALID`. The contract preserves `LIGHT_SELECTION_INVALID` semantics for selection validation. This is a lower-severity consistency issue unless the public error taxonomy intentionally classifies malformed argument types as comparison-invalid.

## No-hit and acceptance-harness observations

A real-corpus query with one selected paper having zero hits returned `ok=true`; the paper remained visible with zero coverage and the other paper supplied evidence. This is contract-compliant. It also shows that acceptance checks must not assume the first two papers both have evidence or that a cited donor exists among `cells[1:]`. The cross-feature acceptance test SHA-256 is `5f7a0c82a06d2247663328b667545a502a6d6c5dacc57fa786f1e5c421e202a1`.

The T3 ZIP tamper check should select a known nonempty regular file rather than blindly using member index 1 and `data[0]`; otherwise it can fail on a valid archive layout. After T1/T2 integration, the dependency-pending live chain must run with real owner modules and the installed-wheel smoke must exercise those backends.

## PyYAML validation

The bundled `.venv` and `/usr/bin/python3` did not expose `yaml`. The installed cached PyYAML 6.0.3 runtime is at `/Users/huangzhanpeng/.cache/uv/archive-v0/o4l3z62xfUQgdlPd`. With that directory on `PYTHONPATH`, the official skill validator returned `Skill is valid!` for the T3 skill.
