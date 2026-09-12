# 终端 4 任务日志

每个终端只写本文件。新进展追加带日期和任务名的段落。详细 r01 归档见 [terminal-4/r01/report.md](terminal-4/r01/report.md)。

---

## 2026-09-06 — 集成三终端候选 + architect/r01 的 R1–R4

**任务：** 在独立集成 worktree 贯通 手动 PDF → 提案 → 来源登记/发布 → 检索问答 → Markdown 草稿；并按 `architect/r01/review.md` 优先修证据正文、引用关联、PDF locator、真实检索链路。

**源码：** `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`  
**基线 HEAD：** `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`（未 commit）  
**解释器：** `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` Python 3.13.13  
**上游：** `9f8c1199047eac2c3828496279fbb7ba9540b90b`

**完成内容：**

1. 抽取终端 1/2/3 已有实现（含未跟踪文件），统一 `vpwiki-research` CLI / 包资源 / 安装入口；保留禁止 `vpwiki-admin`。
2. 用终端 1 真实 intake、四文件 run、legacy draft 驱动终端 2 `admit_source` / `bind_capture_operation` / `bridge_publication`；capture 绑定读 Vault 事务前后文件状态。
3. 夹具 Vault：genesis → capture → admit → package → paper（package 在 paper 前）。
4. 由该次发布结果建索引，贯通 QA 与 writing 的 export/import（合成夹具回答）。
5. R1：导出 `claim_text`（提案）与 `source_excerpt`（document.json 原文切片）。
6. R2：同时给出的引用字段必须同属一条证据；补交叉配对回归。
7. R3：发布保留非整数 PDF bbox；inventory 哈希在浮点时改用 locator wire，不放宽账本 JCS。
8. R4：贯通测试走真实 pinned BM25，不植入 baseline catalog。

**测试结果：**

- R1–R4 后：`tests/research` + publication-wave + `test_catalog_store` + isolation → **90 passed**（25.70s）。见 `terminal-4/r01/evidence/logs/r1-r4-pytest.log`。
- R1–R4 前全量（PATH 含 uv）：**2207 passed**。见 `full-pytest.log`。R1–R4 后未再跑全量。
- 合成 demo 两次 `DEMO_OK`。见 `demo-run-1.log` / `demo-run-2.log`。
- `uv build --offline` 得到 wheel；源码树外 venv 导入 research 包成功。

**未完成：** 真实 PDF/Docling/模型；真实 Vault / `vpwiki-admin`；人工 gate；正式 paper/concept 页面（`pages_included=false`）；事实正确性验收；Python 3.12 / 非 macOS / 远程 CI；未 commit。

**停止写入：** 是（该段对应上一包；本文件后续段落为 lightweight-parallel-v1）。

---

## 2026-09-06 — lightweight-parallel-v1 公共 CLI / 集成 / 真实 SANA 贯通

**任务：** 终端 4。在现有 integration 目录完成 `vpwiki-research` 轻量入口、README、贯通测试；核验并复制 T1–T3 白名单；真实 SANA `pdf add` → `index build` → 当前会话问答/写作；安装入口与全量回归。

**源码：** `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`  
**基线 HEAD：** `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`（未 commit，保留上一包未提交候选）  
**解释器：** `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` Python 3.13.13  
**Git：** 未执行 commit / push / merge / reset。未下载模型。

**完成内容：**

1. 公共轻量命令：`pdf add`、`index build`、`qa export/import`、`writing export/import`，`--workspace` 位于 `.work/**`，不与旧 Vault/config/Docling 参数混用。旧 qa/writing 模式仍可用。export stdout 为 `video-paper-wiki.light-context.v1`；import 按 `context.schema` 分流并可写出 Markdown。
2. README 以轻量流程为正常路径，写明扫描件/图表/公式限制。
3. T1–T3 `ready.json` 均为 `ready` 且 `files[].sha256` 与源副本一致后，只复制白名单 8 个文件。核验记录：`lightweight-parallel-v1/terminal-4/evidence/ready-verify.json`。
4. 复制后 `light_index.build_index` 在 Markdown 与 `source.json` 摘要不一致时刷新元数据再重建，使 `INDEX_STALE` 后的 `index build` 能恢复 `OK`。未改 T1/T3 生产模块。
5. 真实 SANA PDF（31 页，SHA-256 `759588574b9b33bff83a6c8c05da1455535498c6cb70992678079242ddaeb23b`）经 CLI `pdf add` 三次同一 `paper_id`，工作区仅一份 paper 目录；文本+元数据 113078 B（< 1 MiB），索引 281923 B（< 5 MiB），无 PDF/图片/视频副本。改 Markdown 后 `search` 为 `INDEX_STALE`，重建后 `OK`。
6. 本会话阅读 `qa export` / `writing export` 原文后写入答案/草稿 JSON，再 `qa import` / `writing import`。Markdown 含论文标题、PDF 页码与 `page-N` 锚点。产物与 Architect `sana-lightweight/{notes,qa,draft}.md` 均非字节相同。
7. `uv build --offline` 得到 wheel；源码树外前缀安装后 `vpwiki-research index build` 与 `extract_pdf`/`search` 返回 `ok`/`page_count`/`OK`。全量 `tools/lightweight-pdf/test.py`：**2239 passed**（基线 2208 + 本轮 31），`exit_code` 0。

**测试结果：**

- 聚焦（复制模块 + CLI + pipeline + 旧 manual CLI）：**34 passed**（0.37s），日志 `evidence/light-focused-pytest.log`。分项：`test_light_cli.py` 6 passed；`test_light_pipeline.py` 1 passed。
- 全量：**2239 passed in 178.21s**，`full-suite/test-result.json` `exit_code` 0。
- 安装探测：源码树外前缀（排除 named venv 的 editable `.pth`）后 `vpwiki-research index build` 与 `extract_pdf`/`search` 返回 `ok`/`OK`/`page_count`；`sys.path` 不含主仓/integration `src`。

**对抗核验：** PASS。两条证据卫生建议已处理（合并聚焦日志指针；wheel overlay 不再带 `_editable_impl_video_paper_wiki.pth`）。实现源码哈希未改。

**未完成：** 扫描 OCR；跨语言语义检索；事实正确性验收；真实 Vault / `vpwiki-admin`；旧 receipt/human-gate 自动关闭；Python 3.12 / 远程 CI；未 commit。

**停止写入：** 是。交 `lightweight-parallel-v1/terminal-4/ready.json` 后停止实现写入，待 Architect 验收。

---

## 2026-09-06 — r05-fix：重建分页与输出链接

**任务：** 按 `TERMINAL-4-R05-FIX.md` 修 Architect r05 两处问题。不覆盖历史 `terminal-4/ready.json`、`architect/r05/` 或旧 sana 产物。

**源码：** `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`  
**r05 评审快照：** `e2823525133042e790cee821a7cddd280fd9bb3554e78f42bba747c944a5f879`（13 文件当时全部匹配）  
**Git / 模型 / 其他代理：** 无。

**修复：**

1. `light_index.build_index` 在 Markdown 仍保留页锚点/页标题时，按锚点重算各页 Unicode 半开区间、切片 SHA-256 和 document SHA-256，再写 `source.json` 与索引。无效/重复/乱序锚点以 `SOURCE_INVALID`（含 re-extract 提示）失败，且不改原 `source.json` 或索引。原始 PDF `paper_id`/source SHA-256 不变。
2. 轻量 `qa/writing export` 成功文档增加 `workspace_root`。`import` 可选 `--workspace`；与上下文根不一致或两者都缺则失败。落盘 Markdown 的来源链接相对 `output.parent`，并校验目标 `source.md` 与 `page-N` 锚点存在。evidence `markdown_path` 仍相对 workspace。

**测试：**

- `test_light_index.py` + `test_light_pipeline.py`：**9 passed**
- `test_light_cli.py` + `test_light_qa.py` + `test_light_writing.py`：**22 passed**
- 六个 `test_light_*.py`：**36 passed**
- 全量 `tools/lightweight-pdf/test.py`：**2244 passed in 184.41s**（基线 2239 + 本轮 5），`exit_code` 0
- 新 wheel：安装模块 SHA-256 与当前 integration 一致；`vpwiki-research index build` 返回 `ok`/`OK`；`sys.path` 无源码 `src`

**SANA：** 工作区 `integration/.work/light-sana-r05-fix/`，31 页，SHA-256 `759588574b9b33bff83a6c8c05da1455535498c6cb70992678079242ddaeb23b`，再 add 同一 `paper_id`，无 PDF/图片副本；文本+元数据 113078 B，索引 281923 B。本会话答案/草稿导入 `.../terminal-4/r05-fix/sana/`，链接从输出目录可解析到真实页锚点；与旧 `terminal-4/sana/` 及 Architect `sana-lightweight` 均非字节相同。

**未完成：** 扫描 OCR；跨语言语义检索；事实正确性；真实 Vault / `vpwiki-admin`；关闭旧 human-gate；Python 3.12 / 远程 CI；未 commit。未把 Architect `reproduce_*.py` 当作通过标准。

**停止写入：** 是。交 `.../terminal-4/r05-fix/ready.json` 后停止实现写入，等待 Architect review。不声称已通过 Architect 验收。

---

## 2026-09-06 — lightweight-r06-parallel-v1 集成

**任务：** 终端 4。接收 T1–T3 冻结产物后集成 `light_index` 与旧工作区回归，跑 SANA/wheel/全量。不覆盖 CLI/QA/writing/PDF/README，不改历史 r05/r06 Architect 证据。

**源码：** `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`  
**基线快照：** `c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39`（拷贝前 13 文件匹配）  
**Git / 模型 / 其他代理：** 无。

**交接：** T1/T2/T3 `ready.json` 均为 `ready` 且 `stopped_writing: true`。只复制 T1 `light_index.py`（`4d5a8a87…`）和 T2 `test_light_index.py` 加四个 `r06-legacy-workspace` 夹具。T3 `verify_r06.py` 用参数指向 integration，未改其冻结文件。

**恢复：** 共享 legacy 夹具物化到临时 `.work/**` 后，search 为 `INDEX_STALE`（未再改 Markdown/PDF）；`index build` 后 quasar 第 1 页、nebula 第 2 页。安装 wheel 上同样恢复。

**测试：** 六个 `test_light_*.py` **38 passed**（基线 36 + T2 新增 2）。全量 **2246 passed in 212.32s**，`exit_code` 0。新 wheel 的 `light_index` SHA 与本树一致，非 T3 旧日志。

**SANA：** `.work/light-sana-r06/`，31 页，SHA-256 `759588574b9b33bff83a6c8c05da1455535498c6cb70992678079242ddaeb23b`，再 add 同一 `paper_id`；文本+元数据 113078 B，索引 281923 B，无 PDF/图片。本会话问答/草稿在 `.../lightweight-r06-parallel-v1/terminal-4/sana/`，链接从 `output.parent` 可解析。T3 脚本在含空格输出目录同样 `links_ok`。

**未完成：** 扫描 OCR；跨语言语义检索；事实正确性；真实 Vault / `vpwiki-admin`；Python 3.12 / 远程 CI；未 commit。Architect `check_existing_workspace.py` 不是通过标准。

**停止写入：** 是。交 `.../lightweight-r06-parallel-v1/terminal-4/ready.json` 后停止实现写入，等待 Architect 复验。不声称已通过 Architect 验收。
