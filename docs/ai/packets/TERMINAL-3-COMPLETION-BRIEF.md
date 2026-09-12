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
