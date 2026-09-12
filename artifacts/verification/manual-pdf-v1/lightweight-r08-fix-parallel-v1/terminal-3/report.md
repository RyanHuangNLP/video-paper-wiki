# Terminal 3 R08-2 — Bash/zsh quickstart

status: ready (task materials; not Architect acceptance)
stopped_writing: true after ready.json
source_root: `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`
draft: `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r08-fix-parallel-v1/terminal-3/draft/docs/lightweight-pdf-quickstart.md`
doc_sha256: `0c66d84539417e7d902925f1144e558b54fe481b79fd8b77258e562a9c74910e`

## Fix

Replaced scalar CLI assignment and unquoted `$CLI` with array form:

`CLI=(python -I -B -m video_paper_wiki_research)` then `"${CLI[@]}" …`

Deleted the “do not quote `$CLI`” line. Custom interpreter uses a quoted path inside the array. Source form is `CLI=(python -B -m video_paper_wiki_research)` plus PYTHONPATH.

## Shell runs (documented statements, not Python argv rewrite)

| check | bash | zsh |
| --- | --- | --- |
| documented array `--help` | exit 0 | exit 0 |
| scalar unquoted `$CLI` control | n/a | exit 127 (R08-2 bug) |
| pdf add → index → qa export/import → writing export/import | exit 0, all steps 0 | exit 0, all steps 0 |

Source-mode `--help` exit 0; read-only `qa export` on the bash workspace exit 0; `light_index.__file__` is under integration/src.

Protocol `chunk_id` values come from that export. Output directories contain a space. Hrefs resolved from each Markdown parent.

## Gaps

- Did not run 38/2246 tests, Python 3.12, Git/PR/CI
- Protocol JSON is not model-quality evidence
- Did not edit integration README/quickstart (T4 copies after freeze)
