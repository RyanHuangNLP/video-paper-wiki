# RESEARCH-WIKI-MANUAL-PDF-EXTRACTION

Revision 1 · 2026-09-06 · design-pending, not yet implementation-authorized.

- Baseline: `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`.
- Current delivery: existing draft PR94 → integration; base observed `08709894adfb20ec07e976783f0ba436d975b74f`.
- Scope: user-supplied local PDF intake/profile/authoritative offline parser/source-context and nonempty provisional knowledge proposals. Read `RESEARCH-WIKI-MANUAL-PDF-SCOPE.md`, manual-PDF addendum, task-index.yaml and codex-team.md first.
- Contract: `docs/ai/contracts/manual-pdf-extraction-v1.md`, exact hash to be frozen after independent reviews.
- Architect owns this packet, contract, addendum and scope/review/acceptance records. PRDs and online-W1 draft remain unchanged.
- Builder owns implementation only after explicit path handoff. Repo Steward owns independent review and serialized Git/PR/CI after explicit instruction; never main implementation or merge.
- Two children retain explicit `gpt-5.6-sol / medium`; no additional workers.

## Allowed Builder paths after freeze

- `src/video_paper_wiki_research/{__init__.py,__main__.py,cli.py,contracts.py,storage.py,manual_pdf.py,parser_profile.py,source_context.py,locator_truth.py}`.
- `src/video_paper_wiki_research/schemas/{common.v1,manual-pdf-intake.v1,parser-profile.v1,source-analysis-context.v1,source-analysis-proposal.v1}.schema.json` and `src/video_paper_wiki_research/prompts/paper-analysis-v1.md`.
- `operator/parser_executor/pyproject.toml` and `operator/parser_executor/src/video_paper_wiki_parser_executor/{__init__.py,__main__.py,cli.py,exporter.py}`.
- `pyproject.toml`: only research wheel package/resource inclusion and console script; no dependencies/lock/default group changes.
- `README.md`: manual-PDF workflow/optional external producer/basic current-model source-analysis guidance only.
- `.agents/skills/video-paper-ingest/SKILL.md`: targeted manual-PDF orchestration instructions; no admin execution or writing-skill framework. Respect OS permissions; if an edit needs escalation, prepare exact patch and request through normal tool review.
- `tests/research/{__init__.py,conftest.py,test_manual_intake.py,test_parser_profile.py,test_parser_exporter.py,test_source_analysis.py,test_manual_cli.py,test_manual_boundary.py,test_manual_installed.py}` and `tests/fixtures/research/manual_pdf/**` (synthetic data only, no actual paper/model binaries).
- `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/builder/**`: candidate report/file hashes/test results.

Existing engine source/schemas, operator admin package, other Skills, workflows, uv.lock, seed/overlays, inbox/tools and all old plans/evidence are excluded. If needed, request a narrow contract/path amendment before changing them. Literal brace lists denote precise allowed files, not arbitrary siblings.

## Acceptance and handoff

Contract §6 is normative. Builder returns exact changed-file hashes, focused/full/installed results and unresolved limitations, then stops writes. Repo Steward independently audits scope and candidate and records an exact commit before final acceptance. Architect reviews actual code, repeats meaningful acceptance and signs exact source/CI. Steward only stages a separately frozen manifest, preserving protected untracked materials; no blanket git add. Head/base changes invalidate inherited acceptance. Real parser/operator smoke, full knowledge-product completion, and all human gates remain separate from fixture/CI success.

No implementation begins under this draft. The parent will record both contract review decisions and its freeze hash, then explicitly say development may proceed and hand Builder the listed paths.
