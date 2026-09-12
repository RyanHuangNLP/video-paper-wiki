## Change

This PR provides the lightweight research workflow for manually supplied PDFs: native text extraction, cited retrieval and Q&A, structured knowledge drafts, batch processing for long papers, selective refresh, paper maintenance, writing history, and lightweight backup/restore.

The latest change removes the two tracked synthetic PDF fixtures and generates the same sample bytes at test runtime. Git ignore rules and CI reject case-insensitive `.pdf` paths. The current tracked tree contains no PDFs; historical synthetic fixtures remain in earlier commits. Production source is unchanged by this fixture migration. The catalog and overlays remain at 67 entries.

## Validation

- Python 3.12 and 3.13 each passed all 2,701 local tests.
- The fixture migration passed 16 focused tests and 34 independent checks.
- Fresh [Tests run 34256770949](https://github.com/RyanHuangNLP/video-paper-wiki/actions/runs/34256770949), attempt 1, passed all four Ubuntu/macOS × Python 3.12/3.13 jobs, with 2,701 tests per job. All tracked-PDF guard steps passed.
- Reviewed head: `62e05c08be73e84b0eb2d3c89b619c89de14ac86`; tree: `be13818d9a8d8afd0630672d58b952250dec6e10`.
- Actual CI checkout: `fceb3c6a54de3626b1a36fe683591a6ceb1ce813`, whose parents are integration base `08709894adfb20ec07e976783f0ba436d975b74f` and the reviewed head.
- Architect accepted this exact no-PDF head after independent review and fresh CI. Acceptance record SHA-256: `ca45e99405da0e001635e59d3f7452fabfa828e1ad8b07a7a50b3a6e24310171`.

Earlier lightweight workflow validation includes three real-paper trials with 147 chunks, cited Chinese Q&A and writing, selective refresh, installed-package checks, and byte-exact lightweight backup/restore. These are bounded engineering and source trials; they do not establish full scientific qualification.

## Remaining scope

The original full research-Wiki TODOs remain unfinished: formal Markdown source and knowledge publication with version governance; online preview/discovery; official code/configuration mapping; typed relations and strict comparison; full articles and reproduction plans; corpus/gold qualification; and integrated Obsidian and cross-namespace recovery. The source-capture and preview packets are frozen for subsequent implementation. Their completion is not claimed by this PR description.

PR #95 remains a draft targeting `integration`. No merge or auto-merge is requested. Real operator application, provenance/license judgments, human claim and visual review, external backup anchoring, and readiness remain separate.
