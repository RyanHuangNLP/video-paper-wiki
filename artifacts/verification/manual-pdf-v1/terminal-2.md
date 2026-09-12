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

---

## 2026-09-06 · 统一报告目录归档（r02）

任务：后续报告改写到固定绝对目录 `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/`；本终端只写 `terminal-2.md` 与 `terminal-2/r02/`。r01 保留。

完成内容：

- 新增 `terminal-2/r02/report.md`、`terminal-2/r02/files.sha256`、`terminal-2/r02/evidence/`。
- 证据含源码 SHA-256、QA/writing pytest 日志副本、衔接 focused 12-pass 捕获记录。
- 源码绝对路径、基线 `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`、文件清单见 r02 报告。

测试结果：本修订未重跑测试。沿用既有结果：衔接 focused 两次 12 passed；publication-wave 12 passed；QA/writing 15 passed。

未完成：未提交；公共 CLI 未接；paper/concept 页面仍须 human assessment 与 operator apply；衔接原始 scratch `.log` 已随会话删除。

是否停止写入：是。

---

## 2026-09-06 · 轻量索引 / 真实文本检索 / 页码引用（lightweight-parallel-v1）

任务：在指定源码副本实现 `build_index` / `search`（COMMON 冻结接口），不改公共 CLI，不等待终端 1。

源码副本：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-v1/terminal-2`

改动文件（仅允许的两份）：

- `src/video_paper_wiki_research/light_index.py` SHA-256 `5c5ee760e073dd2d942593c289ba242ef2391c253598d1ff7baa3b9de9f5dbeb`
- `tests/research/test_light_index.py` SHA-256 `423b060ff4b26f67b173eeeea44ce67a19870e23e9330c10682fa77ce5ee96e2`

完成内容：从 workspace `papers/<sha>/source.json` + `source.md` 校验 Unicode 页切片后写入可重建 `.light-index/index.v1.json`；BM25 词法检索（拉丁词 + 中文 uni/bigram）；evidence 含 PDF 页码与 Markdown 切片；长页按页内分块；无匹配 `NO_RESULTS`；Markdown/论文集合变化 `INDEX_STALE`。小样本两篇论文索引 `size_bytes=2838`。

命令与结果（共享解释器 `.venv/bin/python` 3.13.13）：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 UV_OFFLINE=1 \
UV_PYTHON_DOWNLOADS=never UV_CACHE_DIR=/Users/huangzhanpeng/python_code/video-paper-wiki/.work/cache/uv-tests \
PYTHONPATH=.../terminal-2/src \
.venv/bin/python -m pytest tests/research/test_light_index.py \
  --basetemp=/private/tmp/vpwiki-t2-light-index-run1 -v
```

两次均为 **5 passed / 0 failed**（0.14s 与 0.12s）。未跑全量。未使用 Git。

未完成：未接公共 CLI；未跑真实 SANA PDF（终端 4）；词法中文不等于跨语言语义匹配。

是否停止写入：是。


---

## 2026-09-06 · lightweight-r06-parallel-v1 独立恢复回归

任务：在指定源码副本编写旧工作区错位分页恢复回归，先在基线模块上记录历史 red，再按 SHA 复制终端 1 的 `light_index.py` 做 green 验证。

源码副本：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/terminal-2`  
基线快照：`c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39`  
工作包 SHA-256：`9ea6ef6590b877418e2521ead4251e728e0822542459e2c6d99c075657fded81`

本终端交付文件（不含复制的实现）：

- `tests/research/test_light_index.py` `b80b680e907931c70fd2112627daca11bf8545acd6934adef5a1db9ff3d45b0c`
- `tests/research/fixtures/r06-legacy-workspace/source.md` `f985d353c7b2f643e2b2addd76182b3c99641b64814e3001ff43ee34c2266804`
- `tests/research/fixtures/r06-legacy-workspace/source.json` `4aab5a9a49b3d8aae1ba252d80c2963d4afa1e7f22960767b409f8452f69a5db`
- `tests/research/fixtures/r06-legacy-workspace/index.v1.json` `5d8a185db8177b6dc59ad201ef94f62dab1a0d902b54269377cdd84002f7347f`
- `tests/research/fixtures/r06-legacy-workspace/provenance.json` `36c32e09bea20a1a9258d3753c2f0352129f2a228d6d52f1a5c63262c5770a2b`

完成内容：夹具按 provenance 物化后调用已发布 `search`/`build_index`。基线 red：`quasar` OK 第 2 页、`nebula` NO_RESULTS，断言 INDEX_STALE 失败。核对终端 1 ready SHA 后只复制 `light_index.py`（`4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8`）。同一断言 green：重建前 INDEX_STALE，重建后 quasar 第 1 页、nebula 第 2 页；六个 `test_light_*.py` 共 38 passed。日志在 `artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/terminal-2/evidence/` 与 `terminal-2/r03/`。

测试结果：

- 基线 red：1 failed in 0.22s（exit 1），打印 `R06_BEFORE_REBUILD OK [2] NO_RESULTS []`
- 候选 green：38 passed in 0.27s（exit 0），打印 `R06_BEFORE_REBUILD INDEX_STALE [] INDEX_STALE []` 与 `R06_AFTER_REBUILD OK [1] OK [2]`
- 未跑全量。未使用 Git。

未完成：全量/SANA/wheel/CLI 属终端 3/4；无 Python 3.12/CI；未提交。

是否停止写入：是。


---

## 2026-09-06 · lightweight-release-parallel-v1 四论文试用

任务：在只读 integration 源码上对 baseline 四份 PDF 做真实 CLI 入库、检索、问答/写作试用，冻结证据后停止。

源码根：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`  
工作区：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-release-parallel-v1/terminal-2/workspace`  
证据：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/terminal-2`  
handoff/ready SHA-256：`d0b8a6cd0756a69fd029ab4b7a2b58e0d404fc98e014d7347415edde795e0b58`

完成内容：四份 PDF 哈希核对后 `pdf add` + `index build`（4 篇、197 chunk）；`cases.json` 先于答案 JSON；本会话根据 export evidence 生成答案/草稿；import 到含空格目录；链接自检通过；15 条 claim 均为 supported。

测试结果：四次 add 与 index build exit 0；无关查询与中文 writing 首次 export 为 NO_RESULTS（exit 2）；改写后的比较/写作与三道单篇 QA import 均为 OK。未跑全量。未改产品代码。未使用 Git。

未完成：全量/3.12/CI/文档属其他终端；首次比较与中文写作检索不足已记录。

是否停止写入：是。


---

## 2026-09-06 · lightweight-r08-fix-parallel-v1 混合引用回归

任务：独立 CLI 回归覆盖三条混合坏来源引用，先在冻结旧 verifier 上记录 red，再按 SHA 只读验证终端 1 新脚本。

工作目录：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r08-fix-parallel-v1/terminal-2`  
证据：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1/terminal-2`  
回归 SHA-256：`a04ded686c5507c49fb25da92b6727f3679f18d7e4e2c0966021a62d27e82531`  
tested_verifier_sha256：`1ca5f342517294c1d5ed3ed3974585bc6ede410a15b08d78f84f6ae285120197`

完成内容：`test_mixed_links.py` 通过 `--verifier` 子进程调用脚本，磁盘 oracle 先确认缺文件/缺锚点。旧脚本 3 failed / 4 passed（混合例 exit 0、ok=true）。T1 ready 后同一断言 7 passed。files=[]。未改产品或 T1 实现。

测试结果：

- 基线 red：3 failed, 4 passed in 0.19s，exit 1
- 候选 green：7 passed in 0.17s，exit 0

未完成：全量/3.12/CI 不在本终端。未 Git。

是否停止写入：是。
