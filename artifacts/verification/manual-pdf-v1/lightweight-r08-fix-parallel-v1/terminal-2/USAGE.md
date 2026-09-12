# Terminal 2 mixed-link regression

Independent CLI tests for `verify_links.py`. They do not import the verifier module. Select the script with `--verifier` or `VERIFY_LINKS_SCRIPT`.

```sh
export PYTHONDONTWRITEBYTECODE=1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export UV_OFFLINE=1
export UV_PYTHON_DOWNLOADS=never
export UV_CACHE_DIR=/Users/huangzhanpeng/python_code/video-paper-wiki/.work/cache/uv-tests
export VERIFY_LINKS_SCRIPT=/absolute/path/to/verify_links.py
export MIXED_LINKS_REPORT_DIR=/absolute/report-directory
export MIXED_LINKS_IDENTITY_LOG=/absolute/identity.log

/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python -m pytest \
  /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r08-fix-parallel-v1/terminal-2/test_mixed_links.py \
  --verifier "$VERIFY_LINKS_SCRIPT" \
  --basetemp=/private/tmp/vpwiki-t2-r08-run \
  -o cache_dir=/private/tmp/vpwiki-t2-r08-cache \
  -v
```

Frozen cases: mixed `source.md?x=1#page-1`, Markdown title href, unquoted HTML `page-2`; plus valid-only, missing source.md without query/title, and valid plus missing non-source. Disk existence is checked before the report is trusted. A crash with no report is not a pass.
