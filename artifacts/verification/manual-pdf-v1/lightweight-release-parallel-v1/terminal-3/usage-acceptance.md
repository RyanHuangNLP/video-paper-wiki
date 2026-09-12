# Terminal 3 usage acceptance — lightweight-release-parallel-v1

status: ready (task materials; not Architect acceptance)
stopped_writing: true after ready.json / handoff.json
role: Terminal 3 (Grok Build grok-4.6)
source_root: `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`
draft_root: `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-release-parallel-v1/terminal-3/draft`

## What was written

- `draft/README.md` — kept the lightweight lead-in and the remaining vault/67-catalog commands; replaced the old `vpwiki-research` console script with `python -m video_paper_wiki_research`; linked `docs/lightweight-pdf-quickstart.md`.
- `draft/docs/lightweight-pdf-quickstart.md` — continuous installed/source start, variables, pdf add → index build → export (no model) → current-session JSON (`chunk_id` from this context) → import, PDF file-page citations, INDEX_STALE rebuild, empty/scan/layout/Chinese-lexical limits.

The shared integration `README.md` was not edited. Product and test files were not edited.

## Commands actually run

Installed interpreter (not resolved through the python3.13 symlink):
`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/.work/r06-wheel-prefix/venv/bin/python`

All product launches used empty `PYTHONPATH`, `-I -B`, `-m video_paper_wiki_research`, cwd `/private/tmp/vp.t3rel`.

| step | exit | result |
| --- | --- | --- |
| `--help` | 0 | usage for pdf/index/qa/writing |
| five-module probe | 0 | site-packages paths; SHAs match R07 baseline |
| source PYTHONPATH import | 0 | `__file__` under integration/src; same SHAs |
| `pdf add` inbox `arxiv-2204.03458.pdf` | 0 | 15 pages, paper_id sha256:564428dc…a96f |
| `index build` | 0 | 19 chunks, 122961 bytes |
| `qa export` English question | 0 | OK, 8 evidence |
| `qa export` Chinese question | 2 | JSON status `NO_RESULTS` (documented lexical limit; process exit 2) |
| `writing export` | 0 | OK, 8 evidence |
| current-session JSON | n/a | chunk_ids copied from this export |
| `qa import` / `writing import` | 0 | OK; Markdown written under `import outputs/` (space) |
| href check from output.parent | n/a | all unique hrefs exist with `id="page-N"` |
| JSON markdown == disk | n/a | true / true |
| edit source.md then export | 2 | JSON status `INDEX_STALE` (process exit 2) |
| `index build` then export | 0 | OK |
| legacy fixture copy then export | 2 | JSON status `INDEX_STALE` (process exit 2); after rebuild exit 0, quasar p.1, nebula p.2 |

Workspace after the stale rebuild: 54002 bytes text/metadata, 123069 bytes index, no PDF/image copies.

## Gaps (not this packet)

- Did not run the 2246-test full suite
- Did not run Python 3.12
- Did not Git-write, push, open/merge a PR, or trigger CI
- Session JSON is a protocol walkthrough, not Terminal-2 content-quality evidence
- Did not relabel architect r06/r07 SANA replay as this run
