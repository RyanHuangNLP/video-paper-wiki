# 终端 1 任务完成报告 — 请 Architect（gpt-6-astra）审查

角色：Builder / 终端 1（Grok Build `grok-4.6`）  
对象：`manual-pdf-extraction-v1` 用户直接下达的独立实现 + 后续真实 wheel 安装核验  
状态：`IMPLEMENTATION_COMPLETE_PENDING_ARCHITECT_REVIEW`  
记录时间：2026-09-06  
Git：未提交、未推送、未合并

请 Architect 对照冻结契约审查本候选，签发 GO / 返工 / 路径补授权。本报告**不**构成验收、合并授权、真实 Docling/PDF 通过或人工 gate。

---

## 1. 审查请求

请核对：

1. 实现是否落在冻结包允许路径内；包外改动是否可补授权。
2. 合成夹具纵向流（intake → exporter 注入 converter → nonempty provisional proposal）是否满足契约 §6 的工程验收，且未被写成真实解析/入库。
3. CLI / 安装入口、真实 wheel 探测是否足够；剩余缺口是否可留给后续包。
4. 是否允许 Repo Steward 按精确清单暂存本候选（仍 draft PR → `integration`，不合并）。

历史 deadline brief `development-brief.md` 保持原字节。本文件为用户直接任务完成后的审查入口。

---

## 2. 基线与输入

| 项 | 值 |
| --- | --- |
| Worktree | `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/goal2` |
| 分支 | `repair/vpkb000-plan-approval-prepare-follow2` |
| HEAD（基线，未前进） | `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f` |
| 契约 | `docs/ai/contracts/manual-pdf-extraction-v1.md` |
| 契约 SHA-256 | `d09215792fd250f6687c29346a2513c5bdb0e44ca974d14c89fe842ef9d1da5f` |
| 工作包 | `docs/ai/packets/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION.md` |
| 工作包 SHA-256 | `011aa774238441f2d62fe7a471650bab1df480b2e7b5a5c5405aff1768efc454` |
| 交付目标 | 既有 draft PR 94 → `integration`；本候选尚未 commit |

工作树有未提交实现。HEAD 仍是冻结 baseline。

---

## 3. 交付声明（可审查的声称）

已完成、且仅在此范围内声称：

1. 默认包装提供 `vpwiki-research`：本地 PDF intake、可选 ingest-plan 交接（**不**创建 approval-ref）、staged context、provisional 知识提案。
2. 独立包 `vpwiki-parser` 做 profile / 四文件 staged export；默认 CLI **不**导入 Docling；测试仅经 Python API 注入 converter。
3. 提案非空路径要求 ≥1 claim、≥1 来自 context blocks 的 locator 线；`assessment=provisional`；`capture_authorized` / `receipt_backed` / `published` 均为 false。
4. 合成 PDF + 夹具 converter 贯通 intake → export → context → analyze。
5. 在**隔离临时环境**中用真实 hatchling 打出 wheel，并在源码树外安装；`PYTHONPATH` 清空后 research 模块、intake schema、prompt 来自 site-packages。

明确**不**声称：

- 真实用户 PDF、真实 Docling/模型、真实 Vault、`vpwiki-admin`
- 正式 genesis / 源登记 / receipt / 发布
- Python 3.12 全量套件或 Linux/macOS CI
- 本候选等于尚未完成的多终端集成树
- 任何人工 gate 已关闭

---

## 4. 实现摘要

用户路径：手动 PDF → 安全暂存 →（可选离线 parser）→ 带 locator 的 context → 当前模型 unsealed JSON → 封存 provisional 提案。

| 命令 | 行为 |
| --- | --- |
| `vpwiki-research pdf intake` | 校验单链正规 PDF，写入 `.work/blobs/<sha256>` 与 intake 信封 |
| `vpwiki-research pdf plan` | 复用现有 plan builder；`next_action=awaiting_external_approval_ref`；无 approval-ref |
| `vpwiki-parser profile` / `export` | 离线模型树清单 + 四文件 staged run；失败写入 `failed-runs/` |
| `vpwiki-research pdf context` | 校验四文件、`verify_pinned_source_id`、locator truth、task prompt |
| `vpwiki-research pdf analyze` | 校验 unsealed 提案，写出 sealed JSON、legacy draft、Markdown |

布局：`.work/research/<session>/manual-pdf/{intakes,profile,runs,contexts,proposals,failed-runs}`。PDF 字节例外放在 `.work/blobs/<sha256>`。

---

## 5. 文件清单（本终端）

精确哈希见同目录 `file-hashes.sha256`。

**已跟踪修改**

- `pyproject.toml` — 加入 `src/video_paper_wiki_research` 与 `vpwiki-research`；未改 dependencies / lock / default groups
- `README.md` — 人工 PDF 暂存流程与「非入库」说明
- `.agents/skills/video-paper-ingest/SKILL.md` — 编排 intake/context/analyze；禁止执行 admin / parser 生产者
- `tests/security/test_cli_isolation.py` — **包外路径**。仅把 scripts 断言从「只有 vpwiki」改为「vpwiki + vpwiki-research、仍无 vpwiki-admin」

**未跟踪新增（实现）**

- `src/video_paper_wiki_research/`（CLI、契约、storage、intake、profile、locator truth、context/proposal、5 schema、prompt）
- `operator/parser_executor/`（独立 hatch 包与 `vpwiki-parser`）
- `tests/research/`（packet 指定的 7 个测试模块 + conftest）
- `tests/fixtures/research/manual_pdf/document.success.json`

**本终端 builder 证据（未跟踪）**

- `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/builder/development-brief-user-direct-2026-09-06.md`
- `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/builder/file-hashes.sha256`
- `artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/builder/test-results.txt`
- 本文件

进入本会话前已存在的脏文件与未跟踪计划/`inbox/`/`tools/`/历史 freeze **不是**本实现，须保留、勿 blanket add。

---

## 6. 测试（夹具，非真实资料）

解释器：`/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`（3.13.13）

```bash
cd /Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/goal2
PYTHONPATH=src:operator/parser_executor/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  /Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python -m pytest -q tests/research
```

结果：**28 passed**（约 4.53s）。

附加（非全量）：`tests/research` + `tests/security/test_cli_isolation.py` + `tests/contract/test_dependency_manifest.py` + `tests/unit/test_commands.py` + `tests/unit/test_staging.py` → **89 passed**。

覆盖：正常/重复/显式 ID intake；损坏/加密/超页 PDF；symlink/FIFO/hardlink；profile 空树/漂移/runtime；export 成功/reuse/空文本/失败 run；四文件与 `validate_docling_artifact_set` 兼容（合成 receipt 字段，非端到端入库）；provisional 提案与篡改 locator；named-directory `WORK_PATH_UNSAFE`；安装布局入口。

未跑：全量双 Python、CI、真实 Docling。

---

## 7. 真实 wheel 核验（补原先 hatchling 缺口）

原 `tests/research/test_manual_installed.py` 在本机 `uv build --offline` 因 cache 无 hatchling 失败，曾退化为拷贝 site-packages。后续在**独立临时目录**完成真实 wheel，**未再写入**冻结 worktree 的生产文件。

| 项 | 值 |
| --- | --- |
| 交接目录 | `/private/tmp/vpwiki-wheel-handoff/` |
| 缺口 | `build-system.requires = ["hatchling"]`；共享 venv 与 uv cache 均无 |
| 隔离安装 | 仅 build-venv：`hatchling==1.32.0`（及 packaging/pathspec/pluggy/tomlkit/trove-classifiers） |
| root wheel SHA-256 | `ba580ae58bbcfdf74268186ef5913ceb9079491337f49256cf63767fe1158ebd` |
| parser wheel SHA-256 | `b5bd3fcff1fdfe72cd71dfa0bbc372bead9a5c559409aa8a561dd0de91b4e1c4` |
| 安装前缀 | `/private/tmp/vpwiki-wheel-handoff/work/install-venv`（`--no-deps`） |
| 探测 | `PYTHONPATH` 空、`python -I`；模块/schema/prompt 均在 install-venv site-packages |

可重复脚本（供终端 4 对集成树再跑）：

`/private/tmp/vpwiki-wheel-handoff/accept-candidate-wheels.sh <source-tree> [output-dir]`

详情：同目录 `DEPENDENCY.md`、`RESULT.md`、`logs/`。未改共享 `.venv` / `uv.lock`。未下载 Docling。

---

## 8. 给终端 2 的消费面

成功 stdout 为一行 JSON 信封：`src/video_paper_wiki/envelope.py`。

终端 2 应消费：

- `pdf.context` → `data.context={id,sha256}`、`data.path`、`data.prompt`、`data.prompt_sha256`、`state=staged_extraction`、三布尔 false
- 磁盘 context：`data.blocks[].locator` 为 `vpwiki-locator-v1:` 线；`text` 为原文切片
- `pdf.analyze --proposal` 的 **unsealed** 对象字段恰好为 `{context,generator,generated_at,prompt_sha256,transport_draft}`（`source_context.py` `analyze_proposal`）
- 封存后：`proposals/<content_sha256>.json` + `.draft.json` + `.md`；`state=staged_analysis_proposal`

`{id,sha256}` 的 `sha256` 是完整信封（JCS+LF），不是 `content_sha256`。

**禁止**：把 staged run / proposal 当作 receipt-backed capture、approval-ref 或已发布知识。Locator 必须从实际 context blocks 原样复制；合成占位符无效。

本 worktree 的 `vendor/claude-obsidian` 无 `.git`。context/analyze 的 pin 检查需干净 pinned checkout（测试使用 `/Users/huangzhanpeng/python_code/video-paper-wiki/vendor/claude-obsidian`）。

---

## 9. 请 Architect 裁决的问题

1. **包外路径**：`tests/security/test_cli_isolation.py` 是否追认？无此行，加入 `vpwiki-research` 会失败。
2. **Wheel**：隔离 hatchling 1.32.0 + 真实 wheel 探测是否满足安装入口验收，或仍要求 CI `uv build --offline`（需把 hatchling 纳入 job cache，而非写入 `uv.lock`）。
3. **Steward**：是否授权按精确清单 commit 本候选并更新 draft PR 94 → `integration`（不合并）。
4. **下一包**：source admission / publication 是否必须等本包 exact-head 验收后再冻接口。

---

## 10. 未完成

- 真实 PDF + 离线 Docling/模型烟测
- 正式入库/发布/检索/写作（其他终端或后续包）
- Python 3.12 与四 job CI
- Git commit（待 Steward + Architect 指令）

Builder 在本报告之后停止实现写入，除非 Architect 下达返工或路径补授权。
