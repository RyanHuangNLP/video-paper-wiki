# Terminal 4 integration prep (before T1–T3 freeze)

Do not edit `light_index.py` until freeze. Baseline 13-file snapshot `c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39` matches the current integration tree.

## Whitelist copy (only after hash-verify + stopped_writing)

From T1 `source_root`:

- `src/video_paper_wiki_research/light_index.py`

From T2 `source_root`:

- `tests/research/test_light_index.py`
- `tests/research/test_light_pipeline.py`
- `tests/research/fixtures/r06-legacy-workspace/source.md`
- `tests/research/fixtures/r06-legacy-workspace/source.json`
- `tests/research/fixtures/r06-legacy-workspace/index.v1.json`
- `tests/research/fixtures/r06-legacy-workspace/provenance.json`

T3: do not copy production files. Invoke frozen scripts with `--source` = integration and output under this terminal-4 directory.

Do not copy whole trees. Do not overwrite CLI/QA/writing/PDF/README.

## Directed tests (after copy)

```sh
cd /Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python -B -m pytest -q \
  tests/research/test_light_index.py \
  tests/research/test_light_pipeline.py \
  tests/research/test_light_pdf.py \
  tests/research/test_light_qa.py \
  tests/research/test_light_writing.py \
  tests/research/test_light_cli.py \
  --basetemp /private/tmp/vp.r06t4/p \
  -o cache_dir=/private/tmp/vp.r06t4/cache
```

## Install / wheel (after source stable)

Offline `uv build` with `UV_CACHE_DIR` = main-repo `.work/cache/uv-tests`, install to a non-`src/` prefix, exclude editable `.pth`, probe `vpwiki-research` and `light_index` SHA against this tree, including legacy restore.
