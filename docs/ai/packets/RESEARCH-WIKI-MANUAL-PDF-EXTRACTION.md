# RESEARCH-WIKI-MANUAL-PDF-EXTRACTION

Revision 3 · 2026-09-06 · frozen, implementation-authorized under the current 8-hour run.

- Baseline: `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`.
- Current delivery: existing draft PR94 → integration; base observed `08709894adfb20ec07e976783f0ba436d975b74f`.
- Scope: user-supplied local PDF intake/profile/staged offline parser/prospective source-context and nonempty provisional knowledge proposals. Read `RESEARCH-WIKI-MANUAL-PDF-SCOPE.md`, manual-PDF addendum, task-index.yaml and codex-team.md first. Canonical source admission/publication is a separate next packet; raw capture alone does not create a canonical receipt.
- Contract: unchanged revision 2 `docs/ai/contracts/manual-pdf-extraction-v1.md`, frozen SHA-256 `d09215792fd250f6687c29346a2513c5bdb0e44ca974d14c89fe842ef9d1da5f`.
- Architect owns this packet, contract, addendum and scope/review/acceptance records. PRDs and online-W1 draft remain unchanged.
- Builder is Grok Build `grok-4.6 / xhigh`, invoked and monitored by Progress Monitor. The paths below are explicitly handed to Builder by this freeze. Repo Steward owns independent review and serialized Git/PR/CI after explicit instruction; never main implementation or merge.
- Architect is `gpt-6-astra / ultra`; Progress Monitor and Repo Steward are the two `gpt-5.6-luna / high` children. Read `MANUAL-PDF-8H-DEVELOPMENT.md`; no additional workers.

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

Progress Monitor and Repo Steward independently returned GO for exact R2 contract `d09215792fd250f6687c29346a2513c5bdb0e44ca974d14c89fe842ef9d1da5f` and pre-freeze packet `5bb7e9d279e41660915112189fa00571c867c2de120127e8ec5a4a3483e51e17`. Architect accepts the technical contract and authorizes implementation. This R3 changes only role assignment, freeze status and handoff metadata; R2 technical contract/allowed source paths are unchanged. R2 bytes are archived in `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/reviews/r2/`. The exact R3 packet hash and review decisions are bound by the separate freeze record.

Builder must return its development brief and exact source hashes, then stop writing until Architect's review instruction. Monitor may write prompts/process logs only under this packet's `monitor/` verification folder or its named temporary run directory; it cannot edit implementation or run Git mutations. Unresolved optional improvements go to TODO; concrete contract gaps return to Architect without silently changing interfaces.

## Preserved R1 review

R1 contract `fcfc75d40848f9d59771a4f816da3a7d7cdadb55da5dccd40c976c93e81b9d47` and packet `21fcd7638e3944927708cb0abecf278b2201f1b258328fa8fd96a9e437103f0d` are archived byte-for-byte under `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/reviews/r1/`. Builder and Repo Steward requested changes; no freeze/implementation/GO was issued for R1. Architect independently traced capture transactions and confirmed they forbid operation receipts/head, so R2 parses staged intake bytes and keeps all outputs prospective. R2 also fixes locator transport versus legacy schema, precise node/span/geometry truth, block/hash domains, and focused-versus-legacy operator test scope. No engine authority rule was weakened.
