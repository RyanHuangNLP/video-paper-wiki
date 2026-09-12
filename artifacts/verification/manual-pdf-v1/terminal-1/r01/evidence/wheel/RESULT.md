# Result: current-candidate wheel installability

**Scope:** this verifies only the current extraction candidate's ability to be built as a real wheel and imported from an install prefix. It does **not** represent the unfinished integration version, real Docling, real PDF smoke, canonical publication, or CI.

**Frozen worktree (not written):** `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/goal2` at `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`

**Candidate copy:** `/private/tmp/vpwiki-wheel-handoff/work/candidate` (includes untracked `src/video_paper_wiki_research/` and `operator/parser_executor/`)

## Wheels

| File | SHA-256 |
| --- | --- |
| `work/wheels/video_paper_wiki-0.1.0-py3-none-any.whl` | `ba580ae58bbcfdf74268186ef5913ceb9079491337f49256cf63767fe1158ebd` |
| `work/wheels/video_paper_wiki_parser_executor-0.1.0-py3-none-any.whl` | `b5bd3fcff1fdfe72cd71dfa0bbc372bead9a5c559409aa8a561dd0de91b4e1c4` |

Built with isolated `hatchling==1.32.0` via `python -m hatchling build --target wheel`.

Installed **outside** the candidate copy into `/private/tmp/vpwiki-wheel-handoff/work/install-venv` using `uv pip install --offline --no-deps`.

## Probe (PYTHONPATH unset, `python -I`, cwd not source)

From `logs/installed-probe.log`:

- `module`: `.../install-venv/lib/python3.13/site-packages/video_paper_wiki_research/__init__.py`
- schema resource: `.../video_paper_wiki_research/schemas/manual-pdf-intake.v1.schema.json` (packaged file)
- prompt resource: `.../video_paper_wiki_research/prompts/paper-analysis-v1.md` (packaged file)
- `PYTHONPATH`: null
- cwd: `/private/tmp/vpwiki-wheel-handoff/work/probe-cwd`

Installed entry `vpwiki-research pdf intake` (missing args) returns JSON `USAGE` from the installed script, not from `src/`.

## Terminal 4

```bash
/private/tmp/vpwiki-wheel-handoff/accept-candidate-wheels.sh \
  /path/to/integrated/tree \
  /path/to/output-dir
```

Requires `uv`, rsync, and `VPWIKI_PYTHON` pointing at a Python that already has jsonschema/pypdf. Installs hatchling only into that run's isolated build venv.

## Not done

No commit, push, merge. No `tests/research` re-run. No Docling. Shared `.venv` / frozen `pyproject.toml` / `uv.lock` unchanged.
