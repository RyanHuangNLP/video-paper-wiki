# 终端 3 完成报告（请 gpt-6-astra 审查）

status: LOCAL_CANDIDATE_STOPPED_WRITING  
role: 终端 3 / Builder 侧独立实现（Grok Build `grok-4.6`）  
recorded_at: 2026-09-06  
observed_branch: `repair/vpkb000-plan-approval-prepare-follow2`  
observed_HEAD: `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`（工作区未提交）  
claim: none  
acceptance: **not requested; 本文件不是验收**  
ci: not_run  
git: 未 commit / 未 push / 未 merge  
human_gate: 未关闭  
stopped_writing: true（交本简报后停止实现写入）

请 Architect（`gpt-6-astra / ultra`）按仓库源码、测试和本清单审查。本简报不代替代码审阅，不代替 Steward 交付，不提供人工批准。

---

## 1. 本终端被指派的范围

用户直接下达、替代已结束 8 小时串行调度的两段工作：

1. **检索问答与简单写作手递（实现）**  
   现有知识库检索 → 带证据的问答 → 可编辑 Markdown 草稿。  
   两个可独立调用的流程，用**显式导出上下文 / 导入当前对话模型的响应**衔接，不新建模型服务、不硬编码 API key。

2. **真实 PDF 验收样例（只读草案）**  
   只用用户已放入本项目的 PDF（优先 `inbox/`），整理待核对的问答/写作验收草案。不是标准答案，不编造通过率。

明确不做：图检索、写作 Skill、全量 benchmark、新前端、真实 Vault、`vpwiki-admin`、模型下载、改 67 条目录、公共 research CLI / schemas / `pyproject.toml` / README / 检索引擎源文件。

---

## 2. 流程 A：问题 → 证据 → 导出上下文 → 导入回答 → 校验引用

独立模块入口：`PYTHONPATH=src python -m video_paper_wiki_research.qa_cli`

| 步骤 | 函数 | 行为 |
| --- | --- | --- |
| 检索 | `retrieve_evidence` / `export_from_question` | 先 `catalog_status`，再 `query_catalog`，再对 `raw_hits` 调用公共 `rank_hits`，用 `mapping_from_database` 还原 locator，不自写 BM25 |
| 导出 | `export_qa_context` |  bounded `qa-context`：question、papers、evidence（paper_id / evidence_unit_id / claim_id / locator_fingerprint / locator） |
| 导入 | `import_model_document` | 读调用方提供的 JSON/Markdown，不发起网络或模型调用 |
| 校验 | `check_citations` / `import_and_check` | 引用必须是**已提供证据身份的子集**；成功文案写明这是结构检查，不是事实正确性审查 |

四类非成功结果（互斥，不编造论文/出处/模型调用）：

| status | label | 含义 |
| --- | --- | --- |
| `INDEX_STALE` | 旧索引 | catalog 非 current，或查询期 generation 变化 |
| `NO_RESULTS` | 无结果 | 排名无论文命中 |
| `INSUFFICIENT_EVIDENCE` | 证据不足 | 有论文但无可用 evidence unit / locator |
| `INVALID_CITATION` | 无效引用 | 引用指向未提供的 paper/unit/locator |

CLI：

```bash
PYTHONPATH=src python -m video_paper_wiki_research.qa_cli export \
  --question 'Video Paper' \
  --vault-root <vault> \
  --upstream-root <upstream-with-scripts/bm25-index.py> \
  --config <retrieval-config.json>

PYTHONPATH=src python -m video_paper_wiki_research.qa_cli import \
  --context qa-context.json \
  --answer model-answer.json
```

`model-answer.json` 由当前对话模型在读完导出上下文后写入，例如：

```json
{
  "text": "The method is described in arxiv:2311.15127.",
  "citations": [
    {
      "paper_id": "arxiv:2311.15127",
      "evidence_unit_id": "evu-96fd392e71707f7e9717",
      "locator_fingerprint": "6c019ec4cf1a61a475cae459964b5ce7e15f4b02b1a4758879c924ee4b753b88"
    }
  ]
}
```

本地 fixture 上一次 export/import 观察到：`ok=true`，`kind=qa-answer`，`citation_check={"kind":"structural-subset","accepted":true}`。该 `evu-*` 仅对应当次 catalog fixture，不是真实 Vault 证据。

---

## 3. 流程 B：主题 / 写作要求 / 选定论文 → 写作上下文 → 导入草稿 → Markdown + 参考文献

独立模块入口：`PYTHONPATH=src python -m video_paper_wiki_research.writing_cli`

| 步骤 | 函数 | 行为 |
| --- | --- | --- |
| 收集 | `collect_writing_evidence` / `export_from_request` | 同样走 current catalog + `query_catalog(topic)` + mapping；范围限制为选定 `paper_id` |
| 导出 | `export_writing_context` | `writing-context`：topic、requirements、papers、evidence |
| 导入渲染 | `import_and_render` | 结构引用通过后输出 `kind=editable-markdown`，参考文献绑定**提供的**论文/证据 |

与 PDF `draft.export` 的 `video-paper-wiki.paper-analysis-draft.v1` JSON **不是同一条路径**。四类拒绝与流程 A 相同。

CLI：

```bash
PYTHONPATH=src python -m video_paper_wiki_research.writing_cli export \
  --topic 'video generation transformers' \
  --requirements 'Write a short editable overview with sources.' \
  --paper-id arxiv:2311.15127 \
  --vault-root <vault> \
  --upstream-root <upstream> \
  --config <retrieval-config.json>

PYTHONPATH=src python -m video_paper_wiki_research.writing_cli import \
  --context writing-context.json \
  --draft model-draft.json
```

本地 fixture 上一次 import 得到 Markdown 含 `# topic`、写作要求、`## 参考文献`，以及绑定到 `arxiv:2311.15127` / `evu-96fd392e71707f7e9717` 的 references；正文不含 `paper-analysis-draft.v1`。

---

## 4. 本终端写入的文件与 SHA-256

`src/video_paper_wiki_research/` 以 **PEP 420 命名空间包**存在（无 `__init__.py` / 无公共 `cli.py` / 无 contracts / 无 schemas），以便 `PYTHONPATH=src python -m ...` 启动，且不创建被禁止的公共 research 文件。

| 路径 | SHA-256 | 行数 |
| --- | --- | --- |
| `src/video_paper_wiki_research/qa.py` | `4604f4665eaa2c137dd35e7d38640278726b2e7ca9e99084739e7a9aed8a3653` | 459 |
| `src/video_paper_wiki_research/qa_cli.py` | `6034f5459fafb13aa17bc90d75534c5ca4081a6cfb0dee4d2926f9684d4a6ce4` | 58 |
| `src/video_paper_wiki_research/writing.py` | `bba21a3aac66d6f94bbcfd87839a9299d8246126b97e78cb00b98e21a0ac84e2` | 318 |
| `src/video_paper_wiki_research/writing_cli.py` | `b632a73836c5b68a21ffbb481d69cab50bddeb74c87bac98857ac750cbfdfe35` | 62 |
| `tests/research/test_qa.py` | `7e9a3a591b3d3da50076e794ef01b71bd88e4562eb3be8114a9ef1593aa9da6b` | 343 |
| `tests/research/test_writing.py` | `36cf7ba5d1e60a9529a2abf3d4a2776687e00bd0f62417bf3a6b18e5cb1d1855` | 149 |

未改：`pyproject.toml`、`README.md`、`src/video_paper_wiki/retrieval.py`、`evidence_join.py`、`catalog_store.py`、公共 research `__init__.py`/`cli.py`/`contracts.py`/schemas（这些公共文件仍不存在）。`git diff` 对上述禁止路径为空。

同目录下另有他端写入、**本简报不主张为终端 3 候选**的文件（请 Architect 分开审）：

- `src/video_paper_wiki_research/source_admission.py`
- `src/video_paper_wiki_research/publication_bridge.py`
- `tests/research/test_source_admission.py`
- `tests/research/test_publication_bridge.py`

---

## 5. 测试与未跑车道

锁定默认环境：`.venv/bin/python`（本机 3.13），`PYTHONPATH=src` / pytest `pythonpath = ["src"]`。

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/python -m pytest tests/research/test_qa.py -q` | **8 passed** |
| `.venv/bin/python -m pytest tests/research/test_writing.py -q` | **7 passed** |
| 两文件合计 | **15 passed in 1.20s**（2026-09-06 复查） |
| `python -m video_paper_wiki_research.qa_cli export -h` | 可启动 |
| `python -m video_paper_wiki_research.writing_cli export -h` | 可启动 |

测试覆盖：

- 从**问题 + 合法 catalog/evidence fixture**走 retrieve → export → import，不跳过检索。
- 导出上下文含真实检索到的 paper/evidence/locator 身份。
- 引用为提供证据子集则结构接受；成功 JSON 不含「事实正确性」宣称。
- 旧索引 / 无结果 / 证据不足 / 无效引用四类拒绝；失败结果不把虚构 paper_id 写入 `papers`/`evidence`。
- 写作输出为可编辑 Markdown + 基本参考文献，不是 paper-analysis-draft JSON。
- 源码不含 `api_key` / `openai` / `anthropic` / `httpx` / `urllib.request`。

测试中的 BM25 子进程按计划**仅隔离该子进程**（`catalog_store.bm25_query`），hits 来自 mapping 中已有 chunk，不发明 paper id。Catalog 证据单元绑定 complete-baseline 中**无 bbox 浮点**的 code locator（`clm-6b2c14bc79f44aaa7714`），因为 mapping JCS 禁止 float；PDF bbox locator 不能经 catalog 往返。

| 未跑车道 | 状态 |
| --- | --- |
| Python 3.12 全量套件 | 未跑 |
| Python 3.13 全量套件 | 未跑 |
| 安装 wheel / 资源检查 | 未跑（research 包未列入 hatch packages） |
| 远程 CI 四 job | 未跑（无 commit） |
| 真实 Vault 上的 Flow A/B | 未跑 |
| 真实模型生成回答/草稿 | 未跑（设计为导入外部文档） |
| 公共 `vpwiki` CLI 接入 | 未做（按任务推迟） |

---

## 6. 真实 PDF 验收草案（待核对，非 gold）

只用 `inbox/` 已有 PDF。三份均可 pypdf 抽字；选 SVD。未下载、未猜扫描件。

| 项 | 值 |
| --- | --- |
| 路径 | `inbox/arxiv-2311.15127.pdf` |
| SHA-256 | `654ef597e183c0544cd753494cb442125bc42b17dd2477481b6799114482a92e` |
| 页数 | 30（30 页非空） |
| 元数据标题 | 缺省 |
| 正文标题（第 1 页） | Stable Video Diffusion: Scaling Latent Video Diffusion Models to Large Datasets |
| 抽取引擎 | 默认环境 `pypdf.PdfReader.extract_text`（无 Docling） |

交付（仓库外，供集成后实跑对照）：

| 路径 | SHA-256 |
| --- | --- |
| `/private/tmp/vpwiki-real-pdf-acceptance/acceptance-draft.json` | `af66edbc0394a960135f9efb1324c0559da2109fa1027fdbf890f24c5ed0c343` |
| `/private/tmp/vpwiki-real-pdf-acceptance/acceptance-draft.md` | `f25a47b4feb0196e7fb2f79b07658ff6a888722480213b5cea2c3f7bebdda0b2` |

两份均标明 **待核对的验收草案**；`human_gate_closed=false`，`pass_rate_claimed=null`。

五个可回答问题（摘录已与对应页抽出文本做子串核对）：

1. SVD 是什么、T2V/I2V（第 1 页）
2. 三阶段训练（第 3 页）
3. 时间层插入与全模型微调（第 3 页）
4. LVD 规模与过滤信号（第 4 页）
5. UCF-101 FVD 242.02；25 帧 I2V 相对 GEN-2/PikaLabs 的人类偏好（第 6 页）

两个证据不足问题：

1. RTX 4090 上 25 帧 576×1024 的实测时延/显存（第 15 页仅有定性局限）
2. 与 Sora/Kling 的数字对比（全文未出现这些名字）

写作任务：主题为三阶段训练与数据策展如何支撑 T2V/I2V；读者为 wiki 初读者；约 600–900 字；结构为一句话结论 → 方法 → 数据/训练 → 结果 → 局限；只引用本 PDF 已抽出页码与摘录。

inbox 未选用：`arxiv-2204.03458.pdf`（Video Diffusion Models，15 页）、`arxiv-2311.17982.pdf`（VBench，28 页）。

---

## 7. 请 Architect 审查的要点

1. 是否接受「命名空间包 + 独立 `python -m` 入口、公共 CLI 后接」为当前边界。
2. 引用检查只做结构子集、成功路径不宣称事实正确性，是否符合 addendum。
3. 测试隔离 BM25 子进程、用 baseline code locator 避开 JCS float，是否仍算「从问题/catalog fixture 出发的真实检索路径」。
4. 流程 B 是否足够区别于 `draft.export` paper-analysis JSON。
5. 真实 PDF 草案是否只能当对照清单，不能当 HUMAN-* 关闭证据。
6. 同命名空间内 `source_admission.py` / `publication_bridge.py` 是否与本候选抢所有权；终端 3 不把它们列入本交付。

审查对象请绑定上表 SHA-256。HEAD 未变（`bcff631`）；实现仅在未跟踪工作区。HEAD 变化或他人改写这些路径后，本简报失效。

---

## 8. 未完成（按任务要求留下，不是本终端漏做）

- 公共 research / `vpwiki` CLI 与 `pyproject.toml` console script
- PDF 解析产物 → 发布 → 索引 → 本 Flow A/B 的端到端贯通
- 图检索、写作 Skill、全量 benchmark、新前端
- 真实 Vault 运行、模型下载、67 条目录变更
- Git commit / draft PR 更新 / CI / Architect 精确 head 验收 / 人工 gate
- Python 3.12 与全量 3.13 套件、wheel 暴露

---

## 9. 停止状态

实现与测试写入已停。本文件是给 gpt-6 的审查输入，不是验收记录，不是 merge 授权。Steward 在 Architect 点名当前路径、哈希、HEAD/base 之前不应暂存本候选。

---

## 2026-09-06 · r02 · 统一报告目录交接

- **任务：** 以后报告只写 `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/`；本终端只维护 `terminal-3.md` 与 `terminal-3/rNN/`。
- **基线：** 工作树 `/Users/huangzhanpeng/python_code/video-paper-wiki`，HEAD `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`，分支 `repair/vpkb000-plan-approval-prepare-follow2`。
- **完成内容：** r01 保留不覆盖；本轮写入 `terminal-3/r02/report.md`、`files.sha256` 和 `evidence/`（pytest 日志、CLI help、环境、哈希）。已读 `architect/r01/review.md`。R1 证据正文、R2 引用同条关联、R3 PDF locator、R4 真实 BM25 链路按审查交给终端 4，本终端不改源码、不写 `terminal-4.md`。
- **源码哈希（绝对路径，与 r01 相同）：** 见 `terminal-3/r02/files.sha256`。六份 QA/writing 文件 SHA-256 未变。
- **测试结果：** `.venv/bin/python -m pytest tests/research/test_qa.py tests/research/test_writing.py -q` → 15 passed in 1.23s。原始日志：`terminal-3/r02/evidence/pytest-qa-writing.log`。未跑全量套件、CI、真实 Vault、SANA 实测。
- **未完成：** R1–R4；公共 CLI；PDF→发布→索引贯通；人工 gate / Git / 模型下载。
- **停止写入：** 是。本轮无实现修改。

修订快照：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/terminal-3/r02/report.md`

---

## 2026-09-06 · lightweight-parallel-v1 · 问答/写作上下文与引用渲染

- **任务：** 在指定源码副本实现 `export_qa_context` / `render_answer` / `export_writing_context` / `render_draft`（冻结 light-context + 联合引用校验 + 可编辑 Markdown）。
- **源码绝对路径：** `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-v1/terminal-3`
- **允许文件：** `src/video_paper_wiki_research/light_qa.py`、`light_writing.py`、`tests/research/test_light_qa.py`、`test_light_writing.py`
- **完成内容：** 上下文保留 retrieval 的原文/页码/路径摘要；prompt 要求当前模型引用给定 chunk、不编造来源；`paper_ids` 空则用命中论文、非空则严格过滤；`[@chunk_id]` 与 citations 列表必须一致；可选身份字段必须与同一 evidence 项联合匹配；渲染标题、PDF 页码、Markdown 锚点和原文摘录。未调用额外模型服务。未改旧 `qa.py`/`writing.py`/公共 CLI。
- **测试结果：** 锁定解释器 `.venv/bin/python`（3.13.13）。`test_light_qa.py` 8 passed；`test_light_writing.py` 6 passed。进程内四函数 export→render 连续两次成功。日志不在本文件内重复。
- **未完成：** 终端 4 的 SANA 贯通、live `search()`、公共 CLI、Git/CI/人工 gate。
- **停止写入：** 是。`ready.json` 已原子写入。
- **就绪文件：** `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-parallel-v1/terminal-3/ready.json`

---

## 2026-09-06 · lightweight-r06-parallel-v1 · 独立 CLI/SANA/wheel 验证

- **任务：** 执行 `docs/ai/packets/lightweight-r06-parallel-v1/TERMINAL-3.md`：参数化验证脚本、基线 CLI、绑定终端 1 `light_index.py` SHA、真实 SANA 流程、新 wheel 隔离安装、旧工作区恢复。
- **源码副本：** `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/terminal-3`
- **verified_light_index_sha256：** `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8`（与终端 1 ready files 一致；官方 SANA/wheel/legacy 均打印该 SHA）
- **完成内容：** 写出 `verify_r06.py` + `USAGE.md`（实现路径为参数，未写死 integration/旧 wheel/terminal-3）。两次 identity 导入不同 source-root 的 `light_index.py` 路径。baseline CLI（tiny.pdf）在复制前观察并标明 baseline。复制后 SANA：31 页、PDF SHA `75958857…eb23b`、文本/元数据 113240 字节、索引 286054 字节、无 PDF/图片副本、含空格输出目录、来源路径与 page 锚点可打开、JSON markdown 与落盘一致。隔离 wheel 的 light_index SHA 相同。legacy：search INDEX_STALE 后 build_index 使 quasar 第 1 页、nebula 第 2 页。
- **测试结果：** 见 `lightweight-r06-parallel-v1/terminal-3/ready.json` 的 tests；原始 JSON 在同目录 artifacts。
- **未完成：** 全量 2244、Python 3.12、远程 CI、Git、人工质量审稿。
- **停止写入：** 是。`files=[]`。未改他端文件。
- **就绪文件：** `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/terminal-3/ready.json`

---

## 2026-09-06 · lightweight-release-parallel-v1 · 使用说明与安装入口

- **任务：** 执行 `docs/ai/packets/lightweight-release-parallel-v1/TERMINAL-3.md`：写出可照做的 README + `docs/lightweight-pdf-quickstart.md`，用只读 R06 wheel 跑安装入口，并按文档对 baseline PDF 走查 pdf add → index → export → 当前会话 JSON → import。
- **源码绝对路径：** `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`
- **基线：** `baseline.json` SHA-256 `06b0c1ac60885e7dd59485a863542fbf8bce0e6f9a2ad41eaab02021798f8357`；包 SHA-256 `f429905c09a18f57a2178ec33155f3861fef64b40eb140851c763ca45caf633c`；R07 快照 `ea67d3b8…ab0dd`。HEAD `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`。
- **完成内容：** 草稿仅在 `.work/parallel/lightweight-release-parallel-v1/terminal-3/draft/`。已安装 `-I -B -m video_paper_wiki_research`（cwd `/private/tmp/vp.t3rel`，空 PYTHONPATH）两次启动；五个轻量模块 SHA 与基线一致。源码 PYTHONPATH 导入 `__file__` 在 integration/src。走查 PDF：`inbox/arxiv-2204.03458.pdf` SHA `564428dc…a96f`，15 页。输出 `import outputs/`（含空格、workspace 外）。href 从 output.parent 解析成功。INDEX_STALE 后重建 OK。legacy 副本重建后 quasar p.1 / nebula p.2。未改 integration README 或生产/测试文件。
- **测试结果：** pdf add / index build / qa+writing export+import 均为 exit 0、OK。中文问句 NO_RESULTS（文档边界）。JSON markdown 与落盘一致。工作区无 PDF 副本。未跑 2246 全量。详情：`lightweight-release-parallel-v1/terminal-3/command-checks.json`、`outputs.json`。
- **未完成：** 2246 全量、Python 3.12、Git/CI、Architect 验收、T4 把草稿拷进 integration。会话 JSON 不是 T2 质量证据。
- **停止写入：** 是。文档草稿已冻结。
- **就绪文件：** `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/terminal-3/ready.json`
- **修订快照：** `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/terminal-3/r03/report.md`

---

## 2026-09-06 · lightweight-release-parallel-v1 · 审查纠正（CLI 变量与退出码）

- **任务：** 修复 skeptic 两项：quickstart 第 2 节补 `CLI=`；usage 表写入真实 exit 2。
- **完成内容：** 变量块现为 `CLI="python -I -B -m video_paper_wiki_research"`。粘贴测试：未赋值 exit 127（`pdf: command not found`）；赋值后 `$CLI --help` 与 `$CLI index build` exit 0。usage 表中文 NO_RESULTS / INDEX_STALE / legacy 过期导出改为 exit 2，与 `command-checks.json` 一致。重写 ready.json。
- **测试结果：** 见 scratch `cli-paste-result.txt`、`exit-code-table-check.txt`。未重跑 2246。
- **未完成：** 同上一节；T4 若已复制旧草稿，需再取本轮 quickstart。
- **停止写入：** 是。
- **就绪文件 SHA-256：** `99aca9687a8ad9e8bd9a1e7b044deb4a643cb6ac423f43a7f4e5ec911ffd3810`

---

## 2026-09-06 · lightweight-r08-fix-parallel-v1 · Bash/zsh 数组 CLI

- **任务：** 执行 `docs/ai/packets/lightweight-r08-fix-parallel-v1/TERMINAL-3.md`（R08-2）：quickstart 在 Bash 与 zsh 中可执行。
- **源码绝对路径：** `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`
- **基线：** `baseline.json` SHA-256 `a616c8e5ff3db04a72df65f043b88634c33f02d31448f7a150910e005a80de28`；包 SHA-256 `3f83248eeea99abfaebca7c77c8c90d560b1b473d5799edfe66d15473ecceb68`。起始草稿 `82d44948…`。
- **完成内容：** 标量 `$CLI` 改为 `CLI=(python -I -B -m video_paper_wiki_research)` + `"${CLI[@]}"`。删除“不要加引号”。`/bin/bash --noprofile --norc` 与 `/bin/zsh -f` 跑文档语句：`--help` 均为 0；zsh 标量对照 127。对 `inbox/arxiv-2204.03458.pdf` 两套独立 `.work` 工作区完成 add/index/export/import，输出目录含空格。源码模式 `--help` + 只读 export，`__file__` 在 integration/src。未改 integration 文档或产品源码。
- **测试结果：** 见 `lightweight-r08-fix-parallel-v1/terminal-3/outputs.json`。href 从 output.parent 解析通过。
- **未完成：** 38/2246、Python 3.12、Git/CI；T4 复制 integration。
- **停止写入：** 是。此 ready 不再原地修改。
- **就绪文件：** `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1/terminal-3/ready.json` SHA-256 `00e6f52097ea8c65c1881fe47bf35b442293fdb940058fc71d35fa42c6c76ebe`
- **quickstart SHA-256：** `0c66d84539417e7d902925f1144e558b54fe481b79fd8b77258e562a9c74910e`

