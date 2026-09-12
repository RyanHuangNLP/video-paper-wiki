Users can take manually supplied PDFs through local extraction, cited questions and drafting, then organize and maintain the resulting lightweight paper library.

- Add cited structured knowledge notes, concept views and explicit multi-paper comparisons with evaluation conditions.
- Add title/tag editing, reversible paper archive/restore, replacement and interruption recovery while preserving nested user notes.
- Add deterministic lightweight backup, read-only verification and restore, including Unicode filenames and historical workflow sessions.
- Expose the complete flow through the installed CLI and natural-language Skill, with quickstarts and recovery guidance.

Local validation: Python 3.12.14 and 3.13.13 each pass 2591 tests; 125 independent checks, 21 additional backup checks and Unicode/invalid-ZIP checks pass. A fresh three-PDF trial covering 73 pages produces cited knowledge and comparison output, then verifies 39 restored files byte-for-byte. Installed console and module entrypoints pass.

See `docs/lightweight-library-quickstart.md`, `docs/ai/lightweight-library-release-2026-09-08.md` and `artifacts/verification/lightweight-library-v1/local-acceptance.json`. The local record binds the 26-file product snapshot; raw papers and trial outputs remain local.

This PR remains a draft targeting `integration`. Text extraction and citation structure checks do not establish human scientific or visual acceptance; original PDFs, the formal Vault and the 67-entry catalog remain outside this increment.

Fresh [Tests run 34197658919](https://github.com/RyanHuangNLP/video-paper-wiki/actions/runs/34197658919), attempt 1, passed all four Linux/macOS × Python 3.12/3.13 jobs with **2591 tests per job** and no failures, errors or skips. CI used Python 3.12.14 and 3.13.15.

Accepted head: `6963292a93ae322eaf9bb563b7b1170dee6a6fc6`. Base: `08709894adfb20ec07e976783f0ba436d975b74f`. Actual CI merge checkout: `7d9a0268d5bbe2b65bc9ff5d77018d5ccab54781`; its ordered parents are that base and head, and its tree equals the delivered tree.

Architect decision: `ACCEPTED_LIGHTWEIGHT_LIBRARY_V1_AT_EXACT_HEAD`. The post-CI local acceptance record has SHA-256 `22c66970879aa4a86f95039cecc70060ebf7136c40040c079e12116a984bf7ad` and is external to the tested commit. The PR remains draft; this decision does not authorize merging.
