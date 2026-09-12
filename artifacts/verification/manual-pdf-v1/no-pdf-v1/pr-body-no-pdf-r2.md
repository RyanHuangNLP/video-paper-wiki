## Summary

This increment completes the lightweight paper research flow on top of the manual-PDF and lightweight-library work already accumulated in draft PR #95. It provides Chinese-to-English retrieval handoffs that preserve the original and rewritten search evidence, bounded processing for long papers, selective knowledge refresh, and cited writing workflows with outline and section history.

The flow processes extracted text in batches, supports explicit refresh choices, preserves notes and prior content, and restores writing history through lightweight backups. The 67-entry catalog and overlays remain unchanged.

## Validation

- 2,685 tests pass on Python 3.12.14 and 3.13.13, with no failures, errors, or skips.
- 38 independent CLI checks pass; 22 actual CLI replay commands and four installed-console workspace reads pass.
- Three real papers produced 147 extracted chunks processed in five batches and five merges: Video Diffusion Models (19), VBench (72), and Stable Video Diffusion (56).
- Four Chinese QA cases, 14 citation-link checks, two writing sections, and four writing revisions pass.
- Selective refresh covers metadata-only changes and a controlled source change with explicit section/concept choices.
- The initial backup restores 68 payload files byte-for-byte; the 69-file archive rebuilt from restored history verifies and byte-matches its source workspace; the isolated wheel is byte-exact across nine tested modules on both Python versions, and Skill validation passes.

The frozen delivery manifest records 26 product files and six sanitized metadata files. The local Architect acceptance record (`ae1b5db65cb48929b6c118369134c491823341c501b760e9475840b2ba0ef13d`) binds this validation to the candidate snapshot.

## Delivery status

Fresh Linux/macOS × Python 3.12/3.13 CI for commit `b7c9764` passed in [Tests run 34250402474](https://github.com/RyanHuangNLP/video-paper-wiki/actions/runs/34250402474), attempt 2. All four jobs completed successfully with 2,685 tests passed on Python 3.12.14 and 3.13.15; the merge-preview checkout was `cd3d510379b897ccf48af84b591813f40a1c549f` with base `integration` parent `08709894adfb20ec07e976783f0ba436d975b74f` and PR head parent `b7c9764fc68a08d0b20089572b87b094fc32e104`. A no-PDF candidate is prepared locally for independent review: it removes the two tracked synthetic PDF fixtures, generates equivalent samples at runtime, and adds case-insensitive tracked-PDF guards. Its focused and full candidate validation, independent review, and fresh CI remain pending. This PR remains draft against `integration`; no merge or auto-merge is requested. Human scientific and page-image review remains open, and this increment does not claim OCR, formula/layout completeness, or full scientific acceptance.
