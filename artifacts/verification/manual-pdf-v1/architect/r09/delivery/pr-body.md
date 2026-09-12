## Summary

This draft adds the accepted local PDF research workflow and its user-facing quickstart to the `integration` branch.

- Ingest selectable-text PDFs into a `.work/**` workspace without copying the original PDF.
- Build the local lexical index and export/import cited QA and writing Markdown with page anchors and source provenance.
- Add manual-PDF research admission and publication-bridge validation alongside the lightweight workspace path; publication stays explicitly gated while preserving the 67-entry catalog and zero-egress agent boundary.
- Document a Bash and zsh-safe CLI-array quickstart, including installed-wheel and source-tree usage.

The exact 70-path candidate commit is `0fcae592acb977c6b422e7de3b2c3e0cf79df5a0`, prepared from baseline `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`, with canonical path-to-SHA mapping `bb64af4cc4152a21c2c5d20ecf33441b9bcb30ce7198ae1ccdb2a466d06f5d03`. The current quickstart is `0c66d84539417e7d902925f1144e558b54fe481b79fd8b77258e562a9c74910e`; README remains `f8395276775c930cf87d0e5a427663083e7a25ae55b1eb577b6383091da6458b`.

## Validation

- Architect R09 local acceptance: `3eb74d7678ab6be87a225f8f7b6173a32426ec1b4f526cbf7e6a8c7f80b7024b`.
- R08 mixed-link acceptance evidence: 19 independent verifier tests and 7 parameterized regression tests passed. The verifier is local acceptance evidence under `artifacts/**`; it is not a shipped candidate path.
- The final documented Bash and zsh flows passed the installed-wheel help, PDF add, index build, QA/writing export and import, source help, and source export checks.
- Reused program wheel SHA-256: `9e1861d92a3b5fc63159a0d0e6e1aca63eb50e283fb6e008f579ef70fce13b21`; documentation is not inside the wheel.
- Protected 188 historical inputs and the original PDF remain unchanged.

## Open delivery gates

- This is a draft PR targeting `integration`, not `main`.
- Fresh remote Tests are required on the exact delivered commit: Ubuntu/macOS × Python 3.12/3.13.
- Python 3.12 was not run locally; historical full-suite counts remain historical evidence.
- Human provenance, real Vault, catalog and publication gates remain open.

No auto-merge, approval, merge, or human-gate closure is requested.
