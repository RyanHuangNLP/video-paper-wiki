# Terminal 3 R06 verification runner

Replayable CLI/SANA/wheel checks. The implementation under test is **always an argument**. This script never treats integration, an old wheel, or the terminal-3 source copy as the default product.

## Required parameters

```sh
/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python \
  /Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/terminal-3/verify_r06.py \
  --python /Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python \
  --source-root <TREE_UNDER_TEST> \
  --step identity \
  --report /absolute/path/report.json
```

| Flag | Meaning |
| --- | --- |
| `--python` | Interpreter that will import/run the product (shared venv or an isolated prefix's python) |
| `--source-root` | Source tree whose `src/` is put on `PYTHONPATH`. Omit when probing an already-installed tree (`--installed-root`) |
| `--installed-root` | Site-packages / `--target` prefix; `PYTHONPATH` is this path only (no copy `src/`) |
| `--workspace` | Independent knowledge workspace; must contain `.work` in the path |
| `--output-dir` | Where import Markdown is written (may be outside the workspace; may contain spaces) |
| `--pdf` | Original PDF for `pdf add` |
| `--legacy-fixture` | Directory with `source.md` / `source.json` / `index.v1.json` / `provenance.json` |
| `--step` | `identity` \| `cli-flow` \| `legacy-restore` \| `wheel-build` |
| `--report` | JSON report path |
| `--label` | Optional label, e.g. `baseline` (not an official terminal-1 result) |

`--source-root` and `--installed-root` are mutually exclusive. One of them is required so the script cannot silently import whatever the shared interpreter already has on disk.

## Steps

1. `identity` — import `video_paper_wiki_research.light_index` and record `__file__` + SHA-256.
2. `cli-flow` — `pdf add`, `index build`, `qa export`/`import`, `writing export`/`import`. Writes model JSON next to `--report`. Checks page count, PDF digest, size caps, no PDF/image copies, every cited `papers/<sha>/source.md#page-N` exists with that anchor, JSON `markdown` equals the file on disk.
3. `legacy-restore` — copy shared fixture files into `--workspace` using `provenance.materialize` (does not edit the shared fixture). Search `quasar`, then `build_index`, then search `quasar`/`nebula`.
4. `wheel-build` — hatchling wheel from `--source-root` using the existing lightweight build backend on `PYTHONPATH`; install `--no-deps` into `--installed-root` (must be outside the source tree).

Terminal 4 replay: pass `--source-root` at the integration tree after copying terminal-1 `light_index.py`.
