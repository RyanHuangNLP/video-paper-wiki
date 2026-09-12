## Summary

This increment completes the lightweight paper research flow on top of the manual-PDF and lightweight-library work already accumulated in draft PR #95. It provides Chinese-to-English retrieval handoffs that preserve the original and rewritten search evidence, bounded processing for long papers, selective knowledge refresh, and cited writing workflows with outline and section history.

The flow processes extracted text in batches, supports explicit refresh choices, preserves notes and prior content, and restores writing history through lightweight backups. The 67-entry catalog and overlays remain unchanged.

## Validation

- 2,685 tests pass on Python 3.12.14 and 3.13.13, with no failures, errors, or skips.
- 38 independent CLI checks pass; 22 actual CLI replay commands and four installed-console workspace reads pass.
- Three real papers produced 147 extracted chunks processed in five batches and five merges: Video Diffusion Models (19), VBench (72), and Stable Video Diffusion (56).
- Four Chinese QA cases, 14 citation-link checks, two writing sections, and four writing revisions pass.
- Selective refresh covers metadata-only changes and a controlled source change with explicit section/concept choices.
- Backup payloads containing 68 and 69 files restore byte-for-byte; the isolated wheel is byte-exact across nine tested modules on both Python versions, and Skill validation passes.

The frozen delivery manifest records 26 product files and six sanitized metadata files. The local Architect acceptance record (`ae1b5db65cb48929b6c118369134c491823341c501b760e9475840b2ba0ef13d`) binds this validation to the candidate snapshot.

## Delivery status

Fresh Linux/macOS × Python 3.12/3.13 CI for the new commit is **PENDING**. This PR remains draft against `integration`; no merge or auto-merge is requested. Human scientific and page-image review remains open, and this increment does not claim OCR, formula/layout completeness, or full scientific acceptance.
