Users can take manually supplied PDFs through local extraction, cited questions and drafting, then organize and maintain the resulting lightweight paper library.

- Add cited structured knowledge notes, concept views and explicit multi-paper comparisons with evaluation conditions.
- Add title/tag editing, reversible paper archive/restore, replacement and interruption recovery while preserving nested user notes.
- Add deterministic lightweight backup, read-only verification and restore, including Unicode filenames and historical workflow sessions.
- Expose the complete flow through the installed CLI and natural-language Skill, with quickstarts and recovery guidance.

Local validation: Python 3.12.14 and 3.13.13 each pass 2591 tests; 125 independent checks, 21 additional backup checks and Unicode/invalid-ZIP checks pass. A fresh three-PDF trial covering 73 pages produces cited knowledge and comparison output, then verifies 39 restored files byte-for-byte. Installed console and module entrypoints pass.

See `docs/lightweight-library-quickstart.md`, `docs/ai/lightweight-library-release-2026-09-08.md` and `artifacts/verification/lightweight-library-v1/local-acceptance.json`. The latter binds the 26-file product snapshot and preserves the distinction between local evidence and the fresh CI required for this delivery. Raw papers and trial outputs remain local.

This PR remains a draft targeting `integration`. Text extraction and citation structure checks do not establish human scientific or visual acceptance; original PDFs, the formal Vault and the 67-entry catalog remain outside this increment.
