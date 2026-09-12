# QA / writing coverage matrix

Shipped modules: `src/video_paper_wiki_research/{qa,qa_cli,writing,writing_cli}.py`.
In-repo tests: `tests/research/test_qa.py`, `tests/research/test_writing.py`.
Catalog fixture: `plant_catalog` in `test_qa.py` (same planting used by writing tests).

Each row names the existing test that **calls the shipped retrieve/export/import function** and asserts `ok` / `status` / papers / evidence / citation identities — not process success alone.

| Named behavior | QA existing test | Shipped function | Writing existing test | Shipped function | Verdict |
| --- | --- | --- | --- | --- | --- |
| 无检索结果 | `test_empty_results_are_distinct_and_non_fabricated` (`hits="empty"`) | `export_from_question` → `retrieve_evidence` | `test_writing_unknown_paper_is_empty_result` | `export_from_request` → `collect_writing_evidence` | Covered. `ok is False`, `status == NO_RESULTS` (`无结果`), `papers == []`, `evidence == []`. QA also asserts the planted paper id is not fabricated into the payload. Writing asserts `missing_paper_ids`. |
| 过期索引 | `test_stale_index_is_distinct_and_does_not_invent_hits` (mutates `query_version`) | `export_from_question` → `inspect_catalog` | `test_writing_stale_index_is_distinct` | `export_from_request` → `inspect_catalog` | Covered. `status == INDEX_STALE` (`旧索引`), empty papers/evidence, no invented paper ids. |
| 证据不足 | `test_insufficient_evidence_keeps_retrieved_papers_without_locators` (`assessment="deprecated"`) | `export_from_question` → `retrieve_evidence` | `test_writing_insufficient_evidence_is_distinct` (`with_evidence=False`) | `export_from_request` → `collect_writing_evidence` | Covered. `status == INSUFFICIENT_EVIDENCE` (`证据不足`), papers retained (`arxiv:2311.15127`), `evidence == []`. |
| 回答/草稿引用不存在的证据时拒绝 | `test_invalid_citation_is_refused_without_adding_invented_papers` | `import_and_check` → `check_citations` | `test_writing_invalid_citation_is_refused` | `import_and_render` → `check_citations` | Covered. Invented `arxiv:0000.00000` (QA also invents `evu-000…`) → `status == INVALID_CITATION` (`无效引用`). Invented id is not added to `papers` / `evidence` / writing `references`. QA records it in `invalid_citations`. Writing keeps `markdown == ""`. |
| 上下文和回答/草稿不匹配时有明确结果 | `test_answer_without_citations_is_invalid` plus the invalid-citation test above | `import_and_check` | `test_writing_invalid_citation_is_refused` | `import_and_render` | Covered as structural mismatch (the shipped check is identity-subset, not semantic Q↔A match). No citations, or citations that are not a subset of the exported context, return `INVALID_CITATION` with `ok is False`. The modules document that this is not a factual-correctness review. |
| 正常回答及 Markdown/参考文献保留可核验证据关联 | `test_question_retrieve_export_import_accepts_structural_subset` (CLI: `test_qa_cli_export_then_import`) | `export_from_question` then `import_and_check` | `test_topic_requirements_papers_render_editable_markdown` (CLI: `test_writing_cli_export_then_import`) | `export_from_request` then `import_and_render` | Covered. QA accepted citations keep `paper_id`, `evidence_unit_id`, `locator_fingerprint`, `claim_id`. Writing Markdown contains `# topic`, requirements, `## 参考文献`, the paper id and `evidence_unit_id`; `references[]` repeats those identities. Not paper-analysis-draft JSON. |

## Notes

- CLI tests also assert payload `ok` / evidence identities, not only exit code 0.
- `test_shipped_qa_modules_do_not_embed_model_clients` / `test_writing_modules_do_not_embed_model_clients` are static source scans, not used as proof of the named runtime behaviors.
- No extra handoff tests: every named behavior already has an in-repo assertion on the shipped path, and that assertion passed (see `existing-qa-writing-pytest.log`).
