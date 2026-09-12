# 终端 4 完成报告（r01）

status: LOCAL_INTEGRATION_CANDIDATE_STOPPED_WRITING  
role: 终端 4 / 集成（Grok Build `grok-4.6`）  
recorded_at: 2026-09-06  
observed_HEAD: `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`（工作区未提交）  
claim: none  
acceptance: **not requested; 本文件不是验收**  
git: 未 commit / 未 push / 未 merge  
human_gate: 未关闭  
stopped_writing: true（交本报告后停止实现写入）

先读 `architect/r01/review.md`，再处理 R1–R4，然后归档本报告。未覆盖其他终端文件。

---

## 1. 源码绝对路径与基线

| 项 | 值 |
| --- | --- |
| 集成 worktree | `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration` |
| 分支 | `integrate/manual-pdf-pipeline` |
| HEAD / 基线 | `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f` |
| 终端 1 源（只读） | `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/goal2` |
| 终端 2/3 源（只读） | `/Users/huangzhanpeng/python_code/video-paper-wiki` |
| 解释器 | `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` Python 3.13.13 |
| 固定上游 | `/Users/huangzhanpeng/python_code/video-paper-wiki/vendor/claude-obsidian` `9f8c1199047eac2c3828496279fbb7ba9540b90b` |

源目录未 reset / clean / 整树覆盖。本候选未 commit。

完整哈希见 [files.sha256](files.sha256)。日志见 [evidence/logs/](evidence/logs/)。

---

## 2. 对 architect/r01 四项优先问题的处理

### R1 导出上下文含可读证据正文

`qa.py` 导出每条 evidence 时附加：

- `claim_text` + `claim_text_kind=proposal`（catalog `claims` 表，提案）
- `source_excerpt` + `source_excerpt_kind=original-document`（Vault 内 `document.json` 按 locator `ref`/`charspan` 切片，并用 `text_sha256` 核对）

写作路径复用同一 enrichment。`tests/research/test_pipeline.py` 断言导出文件含 `TEXT` 原文，合成回答从 `source_excerpt`/`claim_text` 构造，不从上下文外取知识。

### R2 引用字段必须同属一条证据

`_match_citation` 改为：同时给出的字段必须匹配同一条已提供 evidence。仅 `paper_id` 的论文级引用仍合法。交叉配对（论文 A + 论文 B 的 fingerprint、省略 unit id）拒绝。回归：`test_cross_paper_citation_fields_are_rejected`。

### R3 非整数 PDF bbox 贯通发布→索引→QA

- `publication_bridge._bbox` 保留有限浮点坐标，不再丢掉非整数 bbox。
- ledger 仍走既有 `bbox_rationals` 整数比编码；未放宽账本/receipt 的 integer JCS。
- `evidence_join` / `catalog_store` 仅在 inventory 含浮点、integer JCS 失败时，改用 locator **wire**（`encode_ledger_locator`）做哈希。整数 locator 的旧 digest 不变。
- 贯通测试使用 `t=1.5, r=40.25, b=20.75` 的 PDF locator，并断言导出 bbox 含非整数。

### R4 真实检索链路

`tests/research/test_pipeline.py` 用同一次 genesis→capture→admit→package→paper 的夹具 Vault 生成 catalog，经 pinned upstream `bm25-index.py` 查询，不植入 `complete-baseline.json`。既有 `plant_catalog` 单元测试保留。

---

## 3. 可运行命令

```bash
cd /Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration
PYTHONPATH=src:operator/parser_executor/src:. \
  /Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python \
  tests/research/synthetic_demo.py
```

该驱动实际调用 `python -m video_paper_wiki_research` 的 `pdf intake/context/analyze`、`qa export/import`、`writing export/import`。两次 DEMO_OK 日志在 `evidence/logs/demo-run-1.log` 与 `demo-run-2.log`（合成 PDF、注入 converter；bbox 当时为整数化坐标）。R1–R4 的非整数 bbox 与 excerpt 由后续 `test_pipeline.py` 覆盖。

---

## 4. 实际测试结果

解释器 Python 3.13.13。导入路径两次均落在集成 worktree `src/`（见 `evidence/logs/import-paths.txt`）。

| 检查 | 结果 | 日志 |
| --- | --- | --- |
| Architect R1–R4 后：research + publication-wave + catalog_store + isolation | **90 passed** / 25.70s | `evidence/logs/r1-r4-pytest.log` |
| 其中 QA/writing/pipeline/publication_bridge | **22 passed** | 同上 |
| 集成后、R1–R4 前全量 | **2207 passed** / 185.68s（PATH 含 hermes `uv`） | `evidence/logs/full-pytest.log` |
| 首次全量无 `uv` | 2174 passed，33 个 installed-vertical **setup** 失败 | 未作为产品失败 |
| Wheel | `uv build --offline` 成功；新鲜 venv 导入 `video_paper_wiki_research` | `wheel-build.log` / `wheel-install.log` |

未跑：Python 3.12、非 macOS、远程 CI。R1–R4 之后**未**再跑 2207 全量；受影响的 `tests/unit/test_catalog_store.py` 已包含在上述 90 项中。

---

## 5. 未完成事项

- 真实 PDF / Docling / 模型下载与验收未做。
- 未操作真实 Vault，未运行 `vpwiki-admin`。
- 人工 approval-ref、claim assessment、合并 gate 仍开。
- `pages_included=false`：provisional 草案只发布 records/events/ledger，正式 paper/concept 页面仍要 accepted/contested 核心结论。
- QA/writing 引用检查是结构子集，不是事实正确性。
- Catalog 是发布记录上的 `.vault-meta` 索引，不是 `vpwiki-admin catalog build`，也不是 Vault 内 wiki 页面。
- 67 条 seed 未改。
- 未 commit / push / merge。

---

## 6. 是否停止写入

是。本 r01 报告与 `terminal-4.md` 写完后停止实现写入。
