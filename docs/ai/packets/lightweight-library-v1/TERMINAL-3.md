# T3 — CLI, Skill, documentation and integrated acceptance

Own production/documentation:
- src/video_paper_wiki_research/cli.py
- .agents/skills/video-paper-read/SKILL.md
- .agents/skills/video-paper-read/agents/openai.yaml
- .agents/skills/video-paper-read/references/workflow.md
- .agents/skills/video-paper-read/references/library.md (new)
- docs/lightweight-library-quickstart.md (new)
- docs/lightweight-pdf-quickstart.md
- README.md

Own tests:
- tests/research/test_light_library_cli.py (new)
- tests/research/test_light_library_pipeline.py (new)
- tests/research/test_light_library_installed.py (new)

Implement CONTRACT T3/common and exact command/API names. Begin your own CLI/Skill/docs and focused command parsing/routing tests against the frozen API. Stubs are allowed only to unblock that independent work and must be labelled. They are not final acceptance. Read /Users/huangzhanpeng/.codex/skills/.system/skill-creator/SKILL.md before editing the Skill; ensure the Skill handles internal JSON/current-model output and uses actual CLI help.

Do not modify owner modules/tests. T1/T2 stopped exact accepted snapshots will be explicitly handed to this lane; only then copy their allowlisted files byte-for-byte and record input hashes. Integration failures go back to the owning Builder with exact evidence.

Acceptance uses real backends from your own stopped source, public module and installed CLI, Python 3.13 full suite, one isolated installed-wheel smoke outside source with PYTHONPATH cleared and actual installed module paths recorded. Preserve existing installer/no-sync/short-real-temp recipes; never copy a venv or mask failures with calls into another checkout. Python3.12/fresh remote CI are later Architect/Steward acceptance.

Locally available user PDFs:
- ROOT/inbox/arxiv-2204.03458.pdf (Video Diffusion Models, 15 pages)
- ROOT/inbox/arxiv-2311.15127.pdf (Stable Video Diffusion, 30 pages)
- ROOT/inbox/arxiv-2311.17982.pdf (VBench, 28 pages)
Read-only inputs; record verified hashes and generated size/extension inventory. Real PDF extraction can run after integration. The active Architect/current conversation model will author/verify real structured knowledge and comparison documents from exported evidence; do not substitute canned fixture text for that live trial. Preserve independent fixture and real-data reports.

First handoff may be stopped r1 own-path CLI/Skill implementation with dependency_pending clearly recorded; it is not complete/ready-for-final-acceptance until accepted owner inputs and integrated tests are present. Use a new r2+ after downstream integration.

No Git mutation or delivery while any Builder is writing; later Steward role reassignment is explicit.
