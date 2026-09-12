# Grok Build implementation packet: manual-pdf-extraction-v1 R3

You are the sole Builder for this frozen packet. Work directly in the current
repository checkout. Implement and test the complete manual-PDF extraction
packet described by the frozen contract and packet below. Do not redesign the
contract, widen scope, or start a later packet.

Frozen inputs:

- Contract: `docs/ai/contracts/manual-pdf-extraction-v1.md`
  SHA-256 `d09215792fd250f6687c29346a2513c5bdb0e44ca974d14c89fe842ef9d1da5f`
- Active packet: `docs/ai/packets/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION.md`
  SHA-256 `011aa774238441f2d62fe7a471650bab1df480b2e7b5a5c5405aff1768efc454`
- Freeze record: `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/freeze-r3.json`
  SHA-256 `f1fc70e07bc236f5803fa57ecd9c263d7b8a7d891f5c04e06727f6c15d84cdcc`
- Baseline: `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`

Read the contract and packet completely before coding. Reuse existing engine
JCS, identity, strict-read, PDF validation, staging, plan/run/draft and
locator-wire implementations. Preserve all existing untracked plans, inbox,
tools, PRDs, seed/overlays (67 entries), historical evidence, default lock and
existing commands.

The implementation must cover safe local PDF intake, plan handoff, parser
profile preflight, the optional offline staged parser producer, source-context
construction with independent locator truth checks, and externally supplied
unsealed proposal validation/projection into a sealed nonempty provisional
proposal plus deterministic Markdown. Keep every staged result visibly
prospective/untrusted. Do not provide an empty-claims shortcut: the positive
fixture must prove nonempty provisional claims with true locators, while the
empty case returns the specified `SOURCE_ANALYSIS_EMPTY` outcome.

Enforce the frozen byte/hash domains, immutable/idempotent layouts, retained
descriptor checks on every exit, source/model/document identity revalidation,
portable-path and file-type refusals, exact geometry/rational locator truth,
bounded inventories and budgets, and the specified error precedence. Keep the
operator parser package separate from the default package; tests may use an
injected converter fixture only. Do not add default dependencies or models,
download anything, access websites, invoke `vpwiki-admin`, mutate a real Vault,
or make network/socket calls. Do not create a fake parser backend switch.

Allowed write paths are exactly those listed in the packet:

- `src/video_paper_wiki_research/{__init__.py,__main__.py,cli.py,contracts.py,storage.py,manual_pdf.py,parser_profile.py,source_context.py,locator_truth.py}`
- `src/video_paper_wiki_research/schemas/{common.v1,manual-pdf-intake.v1,parser-profile.v1,source-analysis-context.v1,source-analysis-proposal.v1}.schema.json`
- `src/video_paper_wiki_research/prompts/paper-analysis-v1.md`
- `operator/parser_executor/pyproject.toml`
- `operator/parser_executor/src/video_paper_wiki_parser_executor/{__init__.py,__main__.py,cli.py,exporter.py}`
- `pyproject.toml` only for research package/resource inclusion and the
  `vpwiki-research` console script; no dependency or lock changes
- `README.md` for the manual-PDF workflow and optional producer guidance
- `.agents/skills/video-paper-ingest/SKILL.md` for targeted orchestration only
- `tests/research/{__init__.py,conftest.py,test_manual_intake.py,test_parser_profile.py,test_parser_exporter.py,test_source_analysis.py,test_manual_cli.py,test_manual_boundary.py,test_manual_installed.py}`
- `tests/fixtures/research/manual_pdf/**` with synthetic data only
- `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/builder/**` for
  the builder report/evidence

Do not edit contracts, packet/freeze files, AGENTS/team/index files, existing
engine/operator packages, other Skills, workflows, uv.lock, catalog/overlays,
inbox/tools or historical evidence. Do not mutate Git, switch branches, reset,
clean, commit, push, or spawn subagents.

Use the locked default Python environment. Run focused research tests, both
locked local Python suites where available, installed-wheel/resource checks,
and the required boundary/fixture checks. Keep real parser/model execution
pending if its external environment is absent. Distinguish local fixture
results from CI, real PDF, operator, human-gate, and external-provenance
evidence.

Before finishing, inspect the actual diff for scope and whitespace errors. Write
one UTF-8 development brief at
`artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/builder/development-brief.md`
containing:

1. packet, contract, freeze and baseline hashes;
2. the exact changed files and SHA-256 for every changed file;
3. commands and exact test counts/results for every run, Python versions, and
   any unrun lanes;
4. unresolved contract gaps, blockers, and limitations;
5. an explicit `stopped_writing: true` field and the final working-tree/source
   snapshot hash if available.

Also print the same concise development brief as the final response. Do not
claim acceptance, CI, real-data success, human approval, or canonical
publication. Once the brief is written, stop all implementation writes and
wait for the Architect's decision.
