# Terminal-3 r5 report

Unicode backup integration after accepted T2 R8. R4 remains immutable (full-owner snapshot `24d129d75ecf804bdc68fa9416de99a98575a9a02c6127f3fd6714a942c716ed`, handoff `c235be3ffed9fd01731219faf0304da89edc0dd2875cd9456a0ed3784fec7c50`). This is ready for Architect review, not Architect acceptance.

## Functionality

- Verified all eleven stopped T3 owner paths and all fifteen R4 imports against the R5 freeze, then replaced only the two T2 R8 successor files (`light_backup.py`, `test_light_backup.py`). T1 R4 and the other thirteen imports stayed exact. All fifteen imports are read-only. No backend or CLI edit.
- Pipeline and installed-wheel fixtures now use Chinese nested Markdown (`笔记/深层/阅读.md`) and Greek code-note (`notes-α/deep/code-δ.py`) paths plus an ASCII `notes.md` control. Empty directories remain a library archive/restore property. The R4 ASCII `notes-alpha` workaround is gone.
- Same-paper archive → restore → replace → recover retains those exact Unicode names and bytes in the old archive and in `prior-paper-notes.md`.
- Backup create/verify/restore/reuse covers those nested notes, historical workflow session bytes, and an explicit Chinese external report (`外部报告.md`). Creating again against the identical ZIP is reuse.
- Installed-wheel test builds a fresh wheel, checks site-packages hashes with empty PYTHONPATH, and runs knowledge import/build/list, two-paper cited compare, metadata, archive/restore/replace/recover, and backup create/reuse through the isolated module entrypoint. The installed `vpwiki-research` console performs backup verify/restore and `library edit`.
- Docs record that Chinese/Greek user-note names and a Chinese `--include-output` report keep exact names and bytes.

## Files

Handoff `files` contains all eleven original T3 owner paths relative to baseline, including unchanged SKILL.md, openai.yaml, workflow.md, README.md, PDF quickstart, CLI and CLI tests. Fifteen imported owner paths are bound only in `imported-owner-manifests.json` and handoff `imported_snapshots`/`inputs`.

## Tests

- Focused integrated library + owner + skill/workflow CLI: 240 passed.
- Isolated installed wheel: 1 passed. Wheel SHA-256 `408602a9548c4fa6f94fd2febf0b5c1636332a99e0d5f3174446be6fdd013955`.
- Official skill validator: Skill is valid!
- Full `tests/` tree with explicit `UV_CACHE_DIR`/`LW2_UV_CACHE=/Users/huangzhanpeng/.cache/uv`: 2591 passed on Python 3.13.13 and 2591 passed on Python 3.12.14.
- R3 full-tree results (2539 passed, 33 closure setup errors on each Python) remain old failures and are not relabelled. R4 2588-pass/0-error full trees remain history.
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13 and `/private/tmp/l4r5.s54ypl35/locked-312/bin/python` 3.12.14, `PYTHONPATH` = this worktree `src`.
- Real three-PDF/current-model trial remains Architect work.

## Unresolved

- Official `E/terminal-3/r5` write, if denied, is not retried; the source-local folder is then the complete r5 evidence.
- `architect_accepted` remains false.

## Stop

Source writes stop after this evidence folder. No commit, push, merge, Vault mutation, imported-owner edit, or extra agent.
