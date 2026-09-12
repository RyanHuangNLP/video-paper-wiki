# T3 R2 integration review R1

This is a read-only static review. No source was imported, launched, or executed. The review covered the draft integration requirements and the stopped T3 R1 CLI/docs/tests.

Reviewed inputs:

- Draft: `docs/ai/packets/lightweight-library-v1/INTEGRATION-T3-R2-DRAFT.md`, SHA-256 `9e5834ac9c320577ccf65b884ddded42698349013cd22cbfa09773ab59d5dfc0`.
- T3 R1 `cli.py`, SHA-256 `b20c0eeefb57d152ebb0a06ca8a296265c77634e5c87a02e32de41f89dabf7c3`.
- T3 R1 snapshot: `fc867e8c9031c7a273af07a026dc3c4ff1b9df0f2ca3656fd47d29edd3b09c6a`.
- T3 R1 tests: pipeline `e9968ccfec29db5f6844ef0f2e499d7b5013d658af72481dabb0c93e63803437`, installed `decb07ac7fcb43823b30899b5ace2f46fdac349269d96f37e3227a65a25f9db0`, CLI `8d7a2fd6ccda7e4a964151597a4e7780c0cf6b56337efd9787e45e5701c2293e`.

## Findings

### P1: JSON input paths bypass the documented `.work` safety policy

`src/video_paper_wiki_research/cli.py:368-376` `_read_json` accepts any path and follows it with `Path.read_text`; it does not require a `.work` component, reject symlink traversal, or require a regular file. `knowledge import` calls it at lines 920-924 and `compare import` at lines 955-960. The docs state that internal context/document JSON is produced by the Skill, and the contract requires managed paths to stay under `.work/**`; the R2 draft explicitly calls for JSON input path safety. Add a shared safe-input resolver and tests for outside-root, symlink, directory, malformed JSON and non-object JSON before invoking an owner backend. The existing tests cover missing/unreadable JSON only and use paths already inside `.work`.

### P1: `--include-output` also lacks the `.work` and parent-symlink checks

`_regular_markdown` at `cli.py:825-846` checks suffix, final symlink and regular-file status, but never requires `.work` in either the given or resolved path. It therefore allows an arbitrary regular `/tmp/*.md` as an explicit backup input despite the contract/reference saying all backup paths must contain `.work` and symlink traversal is refused. The integrated CLI test should cover outside `.work`, a symlinked parent, and a valid outside-workspace `.work` file.

### P1: the live integration test still stops before the required operations

`tests/research/test_light_library_pipeline.py:116-169` only adds two PDFs, builds the index, lists papers, exports knowledge, exports comparison, creates a backup, and verifies it. It does not import/build/list knowledge, import comparison and inspect readable output, exercise metadata staleness, archive/restore note preservation, replace/recovery, backup restore byte equality, or historical workflow-session remapping. `_require_live_backends()` skips the entire chain when any owner API is absent. The R2 draft correctly requires removing this dependency-pending skip after exact owner import; until the expanded chain runs, this is not integration acceptance.

### P1: installed-wheel coverage is missing the real backend assertions

`tests/research/test_light_library_installed.py:73-181` verifies only the CLI module hash, help output, usage JSON, and the expected `LIGHT_MODULE_UNAVAILABLE` response from `library list`. The console-script check also invokes only an incomplete `knowledge export` command and observes a usage refusal. It does not assert that `light_knowledge`, `light_compare`, `light_library`, `light_backup` and their dependencies are packaged with source-matching hashes, nor does it run successful operations through both the console script and `python -I -B -m video_paper_wiki_research`. The recorded observation explicitly says `owner_modules_expected: dependency_pending`. The R2 draft requires a fresh wheel, isolated imports from site-packages, package/hash checks, and real backend operations; those assertions remain to be added after owner integration.

### P2: wrapper retention is structurally preserved but untested end-to-end

`_cmd_knowledge_import` and `_cmd_compare_import` load the complete JSON object and pass it as `context`; they do not extract the inner `context`, so the wrapper-retention path is statically aligned with the contract. However, the current CLI tests use labelled stubs and only assert one schema or a forwarded field. The live pipeline never writes a returned export object to a context file and feeds it back through import. Integrated tests should retain the complete export wrapper byte-for-byte, assert `context_sha256`/selected-paper/dimension fields survive the handoff, and verify the owner receives the wrapper rather than only its inner light-context.

### P2: Skill/quickstart still omit several R2 documentation requirements

The stopped docs mention UTF-8 for workflow documents but do not declare the lightweight library file/size policy, the file-only treatment of empty directories, or the required “abandoned pre-staging means no replacement/publication” outcome. They mention reindex/reprepare after restore and external PDF exclusion, but the R2 draft requires those points to be explicit in the finalized Skill/quickstart. Add these statements alongside actual backend result fields after integration.

## Review disposition

No GO for final T3 R2 integration is available from the stopped R1 source. The concrete blockers are the missing live chain and missing real-backend installed-wheel checks; path-policy and documentation gaps also require closure. Wrapper pass-through itself has no static defect, but needs an end-to-end retention assertion. No owner module was edited.
