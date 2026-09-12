# Draft PR description (R08, not published)

Local Terminal 4 draft. No GitHub PR was created or updated. Target remains **draft PR → `integration`**, not `main`.

## Title (proposed)

Light PDF path plus R08 verifier mixed-link fix and Bash/zsh quickstart

## Summary

First-version light PDF workspace path plus R08 close-outs:

- R08-1: `verify_links.py` `1ca5f342…` rejects mixed good+bad source citations (query, Markdown title, unquoted HTML). Frozen T2 suite: 7 passed on that exact CLI.
- R08-2: `docs/lightweight-pdf-quickstart.md` `0c66d845…` runs as real Bash 3.2 and zsh 5.9 array commands (`"${CLI[@]}"`).
- R08-3: this-round frozen ready SHAs received once, hashed, and re-checked at stop.

README frozen at `f8395276…`. Product `src/` and repo `tests/` unchanged this round.

## Evidence (this round)

- T1 19 implementation tests; T2 7 mixed-link tests
- T4 Bash/zsh walkthrough on reused wheel `9e1861d9…` (program package; docs not inside)
- Verifier on T3/T4 Markdown and labelled OLD T2/T3 outputs: all ok

## Still open

- Serialized Git / draft PR → `integration` / fresh four-job Tests
- Local Python 3.12
- Human gates, real Vault, catalog 67

## Explicit non-claims

- `git_mutations_executed=false`
- `remote_ci_executed=false`
- `architect_accepted=false`
- Materials-ready is not product publication
