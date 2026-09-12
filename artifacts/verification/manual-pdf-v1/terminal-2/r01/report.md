# 终端 2 任务完成报告（请 Architect / gpt-6-astra 审查）

角色：Builder（Grok Build，本会话为终端 2）  
日期：2026-09-06  
审查对象：本工作树未提交候选，不是 commit/CI 验收。  
请 Architect 独立核对范围、接口、authority/receipt 语义、测试是否驱动真实入口，以及剩余 operator 步骤是否写清。

---

## 0. 工作树与基线

| 项 | 值 |
| --- | --- |
| 绝对路径 | `/Users/huangzhanpeng/python_code/video-paper-wiki` |
| 分支 | `repair/vpkb000-plan-approval-prepare-follow2` |
| HEAD / 基线 | `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f` |
| HEAD 说明 | `test: stabilize installed git fixture`（2026-09-02） |
| Git | **未提交、未推送、未合并**；HEAD 未前进 |

本终端完成两件独立任务：

1. **主任务（实现）**：解析后的知识提案 → 可检查的入库准备 → 现有知识发布流程的衔接。
2. **后续任务（只读验收）**：检查终端 3 的问答/写作实现，不改其源码。

---

## 1. 主任务：来源登记 + 发布衔接

### 1.1 目标

在不重写 capture / package / publication / operation_result / receipt_audit 的前提下，补齐：

staged intake + 四文件 run + 提案/legacy draft  
→ 来源登记（claim captured PDF，写入 source-ledger）  
→ capture 结果绑定  
→ 现有 `prepare_docling_publication`  
→ paper/claim 记录的 publication prepare/inspect。

测试夹具按 `docs/ai/contracts/manual-pdf-extraction-v1.md` 形状构造，不等待 PDF 解析终端。不伪造 receipt/head。

### 1.2 本包文件（请只审查这些）

**未跟踪新增**

- `src/video_paper_wiki_research/source_admission.py`
- `src/video_paper_wiki_research/publication_bridge.py`
- `tests/research/test_source_admission.py`
- `tests/research/test_publication_bridge.py`

目录 `src/video_paper_wiki_research/` 与 `tests/research/` 未跟踪，且 **没有** `__init__.py`（按包约束：不改公共入口）。导入依赖 pytest `pythonpath = ["src"]`。

**已跟踪、窄改**

- `src/video_paper_wiki/publication.py`（inspect 对 derived `document.json` 的解析）
- `tests/unit/test_publication_wave.py`（float vs 严格信封回归）
- `tests/upstream/test_publication_wave.py`（真实 inspect 接受有限浮点 `document.json`）

`git diff --stat` 上述三文件约为 +62 / −2。

### 1.3 明确未改（公共入口与配置）

未修改：

- `src/video_paper_wiki/__init__.py`
- `src/video_paper_wiki/contracts.py`
- `src/video_paper_wiki/cli.py`
- `src/video_paper_wiki_research/__init__.py`（不存在，也未创建）
- `pyproject.toml`、`README.md`、`uv.lock`、schemas

`vpwiki-research` console 仍未接入。调用方式是库导入 + 现有 `publication.prepare` / `publication.inspect`。

同目录并行文件（终端 3，本包未写）：`qa.py`、`qa_cli.py`、`writing.py`、`writing_cli.py`、`tests/research/test_qa.py`、`tests/research/test_writing.py`。

会话开始时已有的未跟踪计划/`inbox/`/`tools/`/`AGENTS.md` 等保持未动（主任务范围内）。

### 1.4 实现要点

**`admit_source`**：校验 extraction 形状的 intake 与 `inspect_staged_pdf_capture` 权威；Vault 须已 genesis（`receipt_backed`）；`verify_pinned_source_id` 得到 `src-…`；拒绝缺失 PDF、缺失/损坏 approval-ref、已登记/已 claim 的重复；`stage_publication_request(operation_type="ingest")` 写入 `wiki/meta/ledgers/source-ledger.json`，并把 `.raw/captured/<sha>.pdf` 放进 `claimed_input_paths`。不写 receipt/head。

**`bind_capture_operation`**：对已 apply 的 capture 调用现有 `bind_operation_result`，校验 digest 与 stored_path。

**`bridge_publication`**：先确认 PDF 已在 `audit_integrity()["ever_claimed_raw"]`，再调用现有 `prepare_docling_publication`；然后从 legacy draft 回绑 `source_id` / `artifact_path` / `artifact_sha256` / `paper_id`，暂存 paper-record、genesis events、claim-ledger。因现有 `compile_pages` 要求 1–3 条 accepted/contested 核心结论，provisional 草案 **不** 写入 `wiki/papers/` 或 `wiki/concepts/` 页面；`pages_included=false`，并点名 human claim assessment。

**`publication.py` 窄修**：仅路径  
`.raw/derived/[0-9a-f]{64}/docling/[0-9a-f]{64}/document.json`  
用 `parse_projection_json`（允许有限浮点）。receipt / head / ledger / knowledge-publication-request 仍走 `parse_strict_json`（禁浮点）。非有限数字仍失败。

稳定错误码（两模块共用）：

| 码 | 含义 |
| --- | --- |
| `SOURCE_MISSING` | 无 intake / 无 captured PDF / ledger 中无已登记来源 |
| `SOURCE_AUTHORITY_INVALID` | 坏或缺失 approval-ref、未 inspect 就放入的 PDF、package 时 PDF 尚未被 receipt claim |
| `SOURCE_DUPLICATE` | 同一 PDF 已登记、派生路径字节冲突、或 paper-record 已在固定路径 |

未做 genesis 时仍抛现有 `RECEIPT_BOOTSTRAP_REQUIRED`。未放宽 authority/receipt。

### 1.5 实际函数签名

```python
def admit_source(
    *,
    intake: object,
    capture_authority: object,
    vault_root: Path | str,
    upstream_root: Path | str,
    batch_id: object,
    operation_id: str,
    ingested_at: str = "2026-09-01T00:00:00Z",
    title: str | None = None,
) -> dict[str, Any]:
```

```python
def bind_capture_operation(
    *,
    inspected_transaction: object,
    apply_result: object,
    vault_before: object,
    vault_after: object,
    expected_pdf_sha256: str,
    stored_path: str,
) -> dict[str, Any]:
```

```python
def bridge_publication(
    *,
    intake: object,
    capture_bind: Mapping[str, Any] | None,
    captured_pdf: Path | str,
    document_json: Path | str,
    parser_config: Path | str,
    model_manifest: Path | str,
    run_manifest: Path | str,
    legacy_draft: object,
    source_id: str,
    vault_root: Path | str,
    package_batch_id: object,
    package_operation_id: str,
    paper_batch_id: object,
    paper_operation_id: str,
    created_at: str = "2026-09-01T00:00:00Z",
) -> dict[str, Any]:
```

全部为 keyword-only。`bridge_publication` 内部依次调用 `package_extraction_run` 与 `prepare_paper_concept_publication`。

### 1.6 串联调用（与已跑测试同一路径）

Agent 侧停在 prepare/inspect。Apply 只用现有 vendor `claude-obsidian.py transaction apply`，禁止 `vpwiki-admin`。

```text
make_checkout + chdir
→ vendor init（pristine ledgers）
→ stage_publication_request(genesis, claimed both ledgers) → inspect_publication → vendor apply
→ staged_pdf_capture_input → inspect_staged_pdf_capture → vendor apply
→ admit_source(intake, capture_authority, …)
→ prepare_publication_source + inspect_publication(admission request) → vendor apply
   （此后 audit_integrity.ever_claimed_raw 含该 PDF，因真实 inspect/apply claim，不是预填 receipt）
→ bind_capture_operation(inspected capture tx, apply_result, vault_before/after, digest, stored_path)
→ bridge_publication(intake, capture_bind, 四文件 run, legacy_draft, source_id, …)
→ prepare/inspect package request（含有限浮点 document.json）
→ prepare/inspect paper-records request
→ 仍须 operator apply；paper/concept Markdown 还须 human claim assessment
```

夹具：`tests/research/test_source_admission.py` 的 `intake_for` / `capture_pdf` / `bootstrap_genesis`；`tests/research/test_publication_bridge.py` 的 `four_file_run` / `legacy_draft`。

一次真实 adapter 返回（摘要）：

- `source_id`: `src-52596c7e9367d80d27ac`
- `pdf_sha256`: `260e2f55fdddd8a17c66699f0852fed9d9299cfe5b47d5d12c1b6cfb8f824f0c`
- `next_action`: `awaiting_operator_apply`
- `agent_may_run_vpwiki_admin`: `false`
- `pages_included`: `false`（compiler 需要 accepted/contested 核心结论）

### 1.7 仍须用户 / operator 执行

1. Capture 尚未授权时：外部 **approval-ref**（本适配器永不创建）。
2. 每个已 inspect bundle 的 **operator `transaction apply`**（genesis、capture、admission、package、paper records）。这是唯一 Vault 变更。
3. Paper/Concept 页面发布前的 **human claim assessment**。
4. **不要跑 `vpwiki-admin`。** 不改真实 Vault、不下载模型、不改 67 条目录。

### 1.8 主任务测试

解释器：`/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`（CPython 3.13.13，pytest 9.1.1）  
Cwd：仓库根。`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。

两次 focused，均为 **12 passed / 0 failed / 0 skipped**（约 12.53s 与 12.54s）：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  tests/research/test_source_admission.py \
  tests/research/test_publication_bridge.py \
  tests/unit/test_publication_wave.py::test_publication_decodes_finite_float_docling_document_only \
  tests/upstream/test_publication_wave.py \
  --basetemp=/private/tmp/vpwiki-research-bridge-run1 -v
# 第二次 basetemp=/private/tmp/vpwiki-research-bridge-run2
```

另跑完整 publication-wave 文件：**12 passed**。

覆盖：happy path 贯通 prepare/inspect；`SOURCE_MISSING` / `SOURCE_AUTHORITY_INVALID` / `SOURCE_DUPLICATE` 分支码互异；有限浮点 `document.json` 可 inspect；receipt/ledger 浮点仍拒绝；测试未预写 `wiki/meta/operations/` 或 `operation-head.json`。

未跑全量套件。未跑 `vpwiki-admin`。

---

## 2. 后续任务：终端 3 问答/写作只读验收

范围：只读 `qa.py`、`qa_cli.py`、`writing.py`、`writing_cli.py` 及 `tests/research/test_qa.py`、`test_writing.py`。不改终端 3 源码，不改公共接口，不启动子 agent。

结论：**六项点名行为均已有现成测试驱动真实 export/import 入口，并断言 `ok`/`status`/papers/evidence/citation，不只是退出码。15/15 通过。未发现缺陷，因此未再新增用例。**

| 行为 | 现成测试（QA / writing） | 断言 |
| --- | --- | --- |
| 无检索结果 | `test_empty_results…` / `test_writing_unknown_paper…` | `NO_RESULTS`，空 papers/evidence |
| 过期索引 | `test_stale_index…` / `test_writing_stale_index…` | `INDEX_STALE`，不编造 hits |
| 证据不足 | `test_insufficient_evidence…` / `test_writing_insufficient_evidence…` | `INSUFFICIENT_EVIDENCE`，保留 papers，`evidence == []` |
| 引用不存在的证据 | `test_invalid_citation…` / `test_writing_invalid_citation…` | `INVALID_CITATION`，不写入 invented id |
| 上下文与回答不匹配 | QA `test_answer_without_citations…` + 上列 invalid-citation | 明确 `INVALID_CITATION`（结构子集，非事实正确性） |
| 正常回答与 Markdown 参考文献 | `test_question_retrieve_export_import…` / `test_topic_requirements_papers_render…` | 保留 `paper_id`、`evidence_unit_id` |

引用检查按 `qa.py` 文档，只验证提供的身份子集，不宣称科学正确。

解释器同上。命令：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  tests/research/test_qa.py tests/research/test_writing.py -v
# 15 passed in 1.03s
```

交付目录：`/private/tmp/vpwiki-qa-acceptance-handoff/`  
（`coverage.md`、`existing-qa-writing-pytest.log`、`commands.md`、`no-new-tests.txt`、`issues.md` 为 `none`）。

---

## 3. 请 Architect 裁定

1. 主任务候选是否可进入独立 Repo Steward 审查 / 是否需要补公共 `vpwiki-research` 入口（当前按包约束故意未接）。
2. provisional 草案只发 paper-record / events / claim-ledger、不发 compiler 页面，是否接受；或是否要求另开包改 `compile_pages`（本包明确未改 compiler）。
3. `publication.py` 仅对 derived `document.json` 放开有限浮点，是否视为允许的衔接修复。
4. 终端 3 QA/writing：现有 15 测已覆盖点名行为且通过，验收是否记为无缺陷、无需终端 4 修复。

Builder 不替代 Architect 终验，不合并。当前 HEAD 仍为 `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`。
