# Video Generation Research Wiki v1 R2：附件复核后的 MVP-first 开发方案

状态：R2 架构复核候选；等待 exact-byte Repo Steward 复核
基线：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`
目标分支：PR #94，draft → `integration`
日期：2026-09-04
前序方案：`video-generation-research-wiki-v1-plan.md`，SHA-256 `fe7ddf79d92699e34f032b838906e0d36aa199bbdd75505360c64491050b884a`
新增输入：`video_generation_llm_wiki_v1_code_comparison.md`，SHA-256 `c7fc3871c8061d4bdc6ba01ce3f07dd385ee002985ee77239a4a217bf42fdc33`

## 1. 产品目标

这个项目最终要完成一个面向个人研究的视频生成论文知识库，而不是只完成一组底层 schema 和审计工具。用户应当能够在 Codex 对话里完成以下闭环：

```text
给出种子论文或研究问题
  → 自动发现候选论文
  → 获取 arXiv 题录并生成中文摘要
  → 用户决定入库 / 跳过 / 稍后
  → 入库论文解析为可追溯 Paper / Claim / Method / Concept
  → 查找并固定官方代码仓库与 commit
  → 建立论文、代码、模型、训练、数据集、推理之间的知识图谱
  → 跨论文回答技术问题、比较方法和发现矛盾
  → 生成带出处的技术综述或文章草稿
  → Obsidian 负责最终阅读、编辑和人工确认
```

第一原则是先交付一条真实可用的纵向路径，再重构内部模块。第一版不要求用户理解 approval-ref、transaction bundle、catalog generation 或工作包编号。

### 1.1 对旧计划的明确修订

这份方案是现有 v0.3.4 引擎计划的产品化 successor。用户最新目标明确重新纳入旧计划第 2.2 节曾延期的三项能力：自动发现论文、跨论文研究综合、技术文章草稿。底层真源、事务和证据不变量继续复用；“这些能力继续延期”不再成立。

现有 `vpwiki` 仍作为确定性、离线 engine CLI。新增的 `vpwiki-research` 也保持零 egress：它只生成受限请求、校验已经捕获的 observation、管理 `.work/research/**` 状态并验证 LLM proposal。Repository Skill 使用 Codex 平台提供的只读 Web connector 获取公开题录；W1 的 capability spike 先记录该 connector 实际能导出的字段，再选择“规范化内容”或“字节精确” observation。connector 不持有 Vault 路径或写入能力。没有平台 connector，或后续 ingest 需要平台不能导出的原始字节/传输证据时，系统返回精确的 external-input request，由外部 operator 提供文件与 observation，而不是从 Python CLI 偷偷联网或伪造字段。

用户的“入库”或“发布文章”回复只作一次内容选择。Orchestrator 将该选择保存为不可变 decision artifact，并生成 plan/external-input request；`vpwiki` 和 orchestrator **从不签发 approval-ref**。当前 `approval-ref.v1` 只是外部提供的九字段摘要绑定，没有 issuer、签名或时间，其提供者身份在 v1 不可验证；它不表示人工批准或 apply 权限。Orchestrator 只能消费并校验该 ref 与本地 blob。真正写入边界仍是 inspect 对 exact bundle + Vault snapshot 产生 `transaction.inspection.approval_sha256`，再由独立 operator 交互确认并 apply。agent 不运行 `vpwiki-admin`、不直接写真实 Vault，也不把聊天回复伪装成外部 authority。

### 1.2 对新增代码对比附件的复核决定

附件是有价值的领域设计 backlog，但它假定绿地新建一个完整 `videowiki` 平台。当前仓库已经拥有通过 2152 项双版本、四矩阵验证的 identity、transaction、capture、claim/assessment、publication、catalog、BM25、audit 和 backup/restore 基础，因此 R2 只吸收能补齐用户产品目标的部分，不重建第二套内核。

| 附件建议 | R2 决定 | 落点 |
|---|---|---|
| 视频生成 taxonomy：task/paradigm/backbone/component/training/inference/evaluation | **吸收但走候选与版本迁移**；不原地扩写已固定 `taxonomy/v1.json` | P1/P4 产生 `taxonomy-extension-proposal.v1`，真实 corpus + review 后才形成未来 taxonomy v2 |
| `claim_kind`：architecture/training/result/implementation/ablation/limitation/reproducibility/license/resource | **吸收为正交分类**；绝不与 assessment 或 freshness 混用 | P1 只生成 classification proposal；P4/W5 通过 versioned canonical `claim-domain-annotation.v1` + review event + 现有 publication transaction 接受，未知类型进入 review queue |
| figure/table/equation 证据 | **吸收为现有 PDF evidence locator 的结构化引用** | W2 将 Docling block label 映射到 `ref+bbox/charspan+artifact/text hash`，不另建真源 |
| typed relations 与 apples-to-apples 比较 | **吸收并收紧** | P4 使用 predicate registry、evaluation context 和领域 lint；`improves_over` 等必须 claim-backed |
| support/counterevidence、低收益/重复率/预算停止条件 | **吸收** | P2 research session 的 append-only round/event 与可重放 stop decision |
| reproduction plan | **吸收为 proposal** | P5 生成带 commit/config/checkpoint/hardware/unknown locator 的草稿，不执行训练 |
| section/claim/config/result 分对象检索、RRF 和诊断指标 | **部分吸收** | P4 先复用 CJK BM25 + exact catalog + graph，以 RRF 融合排名；dense embedding 仍为可选 capability |
| `skill.json` 机器约束 | **改为 `skill-contract.v1` 文档/校验 manifest** | 从 W1 开始与 `SKILL.md` 一起发布；安全仍由 CLI、平台 tool policy 和 operator 强制 |
| MCP | **后移为只读/请求型适配器** | P6 仅 status/search/context/request/validate；不提供 accept/apply/Vault mutation |
| 新建 `videowiki` 包及 `raw/normalized/ledgers/state` 根目录 | **拒绝** | 继续使用 `video_paper_wiki` 唯一内核、`.raw/**`、`wiki/meta/**`、`.work/research/**` |
| Typer/Pydantic/SQLAlchemy/NetworkX/tree-sitter/FastMCP/embedding 全量依赖 | **拒绝作为 v1 前置** | 每项先做 capability/license/lock/四矩阵 spike；只有真实收益达到阈值才引入 |
| `captured→normalized→...→indexed` 新状态机、可变 `failed` | **拒绝** | 保留现有 canonical ingest lifecycle；失败追加 event 并停在最后可证明状态 |
| `review_accept`、可写 MCP、agent single writer 直接 apply | **拒绝** | agent 只在 `.work/**` proposal/inspect；独立 operator 才能 apply |
| YouTube/完整视频、多 provider、Grok runtime、watcher/scheduled refresh | **不进入当前 v1** | 另开 re-scope；当前三开发角色均为 Codex |

附件把 `claude-obsidian@ad67087...` 作为远端分析快照；本仓允许直接复用的仍是已固定并验证的 `9f8c1199047eac2c3828496279fbb7ba9540b90b`。`ad67087...` 只作为 observed remote head，不能在未完成 pin 升级、差异审计和全回归前替换本地底座。附件列出的其他功能也不能仅凭目录、README 或 Skill 名称视为已实现；代码采用仍以 [`external-reuse-audit-2026-09-04.yaml`](external-reuse-audit-2026-09-04.yaml) 的精确文件证据和后续工作包验证为准。

## 2. 用户体验

### 2.1 第一条可用路径

用户在 Codex 中输入：

```text
预览 https://arxiv.org/abs/2311.15127
```

系统自动完成：

1. 规范化 arXiv ID，并从官方 API 获取标题、作者、版本、分类和作者摘要。
2. 用当前 Codex 会话生成中文摘要，分为研究问题、方法、贡献、结果、局限和与视频生成知识库的相关性。
3. 明确标注摘要证据范围是 `abstract-only`；不得冒充已读全文。
4. 在对话中展示摘要，并询问“入库 / 跳过 / 稍后”。
5. 记录决定；只有“入库”才生成 PDF 获取请求并进入 W2 的解析、草稿、inspect 和 operator 发布流程，agent 本身不下载或 apply。

读取 arXiv 题录由 Codex 的只读 Web connector 自动完成，不要求用户复制抓取命令。用户对“入库”的回复是论文是否进入候选发布链的产品决定；真实字节保留、许可判断、claim 接受、Vault 发布和最终合并仍受第 11 节列出的既有 gate 与 operator authority 约束。

### 2.2 完整产品路径

```text
“以 Sora/DiT 为种子扩展相关论文”
  → 返回去重、排序后的候选卡片
  → 用户逐篇或批量决定
  → 已批准论文进入 Vault
  → 自动发现官方代码候选并说明官方性证据
  → 用户确认仓库后固定 commit 并建立代码证据
  → “比较这些论文如何做时空建模”
  → 返回 claim 级引用、共识、差异、矛盾和未知项
  → 可选：“给出可复现该方法的实验计划”
  → 返回绑定 repo commit、配置、checkpoint、硬件假设和未知项的草稿
  → “把结果写成技术文章草稿”
  → 生成引用完备草稿；用户可在 Obsidian 复制为自己的笔记继续编辑
```

### 2.3 不做的事情

- 不自动把“候选”升级为已入库论文。
- 不把 LLM 推断写成来源事实；每条结论必须是 `extracted`、`inferred`、`ambiguous` 或 `contradicted`。
- 不下载模型权重、训练集或视频数据。
- 不把 YouTube、完整视频解析、OCR-first 文档或多媒体知识库塞进当前 v1。
- 不依赖 Neo4j、远程向量数据库或额外模型 API 才能启动。
- 不以 MCP、dense embedding、多 provider 或定时 watcher 作为首个可用版本的启动条件。
- 不重新实现 `claude-obsidian` 已有的 Vault 事务、capture、lint 和 BM25。
- 不在未经用户决定时发布文章或改写人工笔记。

## 3. 当前仓库现状

### 3.1 可以直接复用

当前基线已经具备以下引擎能力：

| 能力 | 当前实现 | v1 用法 |
|---|---|---|
| Canonical identity | `identity.py` | arXiv、DOI、OpenAlex、PDF hash 去重 |
| 封闭 schema 与语义校验 | `contracts.py` + 53 个 schema | 所有新记录继续使用 closed JSON |
| 安全 staging | `staging.py`、`secure_io.py` | 下载、解析和生成物先进入 `.work/**` |
| PDF capture / prepare / inspect | `plan.py`、`prepare.py`、`staged_capture.py` | 用户批准后复用，不另建摄取引擎 |
| PDF 解析适配 | `parse/`、`extraction_artifact.py` | Docling 可用时生成块级 locator；pypdf 只作预览 |
| Paper / Code / Concept 编译 | `canonical_compiler.py`、`domain.py` | 生成 Obsidian Markdown 投影 |
| Claim / assessment 历史 | `assessment_history.py` | 支持 accepted、contested、unsupported 等状态 |
| 原子发布与 receipt | `publication.py`、`receipt_audit.py` | 批准内容写入 Vault |
| 结构化 catalog | `catalog_store.py` | SQL 投影、状态检查和精确映射 |
| BM25 与中文 tokenization | 固定的 `claude-obsidian` 上游 | 第一版检索，不再造另一套索引 |
| Retrieval evaluation | `retrieval.py` | 评估 paper/evidence 命中率 |
| Audit / backup / restore | 现有命令与 operator | 发布后的完整性和恢复 |
| Repository Skills | 现有 4 个 Skill | 作为新用户工作流的底层子步骤 |

当前 roadmap-closure candidate 已在本地通过 2152 个测试。PR #94 的 Tests run `33642835702`（attempt 1）也已在 merge preview `ee6159ea7d3b36720b862617b3a9a2c99ef3ba73` 上通过 Linux/macOS × Python 3.12/3.13 四个 job，每项 2152 tests；该 preview 的 parents 是 head `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f` 与 base `08709894adfb20ec07e976783f0ba436d975b74f`。仓库内尚未持久化绑定这次 run 的 CI observation、merge parents 和 Architect exact-head acceptance，因此不能把“CI success”写成“候选已接受”，也不能替代真实论文、真实 Vault 和用户工作流验收。

### 3.2 真正缺口

| 缺口 | 用户影响 | 处理顺序 |
|---|---|---|
| 没有 arXiv 预览入口 | 不能从论文链接开始 | P0 |
| 没有统一 session / `next` 状态 | 用户要手工拼十几条命令 | P0 |
| 没有“摘要后决定是否入库”的状态机 | 候选与正式入库混在一起 | P0 |
| 没有真实单篇一键摄取编排 | 引擎存在但产品不可用 | P1 |
| 没有引用/相似论文扩展 | 不能从 seed 自动增长 | P2 |
| 没有官方代码发现和候选排序 | 只能手工给 repo | P3 |
| 当前 taxonomy 覆盖浅、claim 无正交领域类型 | 难以精确比较架构/训练/结果 | P1/P4 |
| 图谱只有页面关联，没有统一边/矛盾模型 | 难以跨论文推理 | P4 |
| Q&A 只有底层 query，没有 context pack 和回答器 | 不能直接问研究问题 | P4 |
| 缺少视频实验 apples-to-apples 结构与 lint | 参数量、分辨率、帧数和 benchmark 容易误比 | P4 |
| 没有综述/技术文章 artifact | 不能把研究结果转成文章 | P5 |
| 没有引用完备的 reproduction-plan artifact | 无法从论文/代码证据形成可执行前准备 | P5 |
| CLI 与证据包过度暴露 | 首次使用成本高 | P0/P6 |

## 4. 目标架构

```text
                         Obsidian
                            │
                    Markdown Wiki / Bases
                            │
       ┌────────────────────┼────────────────────┐
       │                    │                    │
    Sources              Concepts             Methods
       │                    │                    │
    Papers ─ Models ─ Training ─ Code ─ Datasets ─ Inference
       │                    │                    │
       └──────────── Knowledge Graph ───────────┘
                            │
                  Retrieval + Context Pack
                            │
                      Agent Skill Layer
       ┌────────────────────┼────────────────────┐
       │                    │                    │
   Preview/Ingest      Research/Q&A       Synthesis/Article
```

### 4.1 分层

1. **Connector 层**：arXiv、OpenAlex、GitHub，以及候选型 Hugging Face/model-card observation。只负责受限获取和来源观察，不直接写 Vault、下载权重或数据。
2. **Evidence 层**：保存 PDF、代码字节、Docling block、URL、commit、hash 和许可证观察。
3. **Canonical Knowledge 层**：Paper、Repo、Claim、Assessment、Concept 和版本化关系。
4. **Graph 层**：由 canonical records 和 relations 确定性构建邻接表、矛盾组和社区；图是可重建投影。
5. **Projection 层**：Obsidian Markdown、SQLite catalog、BM25 index 和 Bases view。
6. **Research 层**：候选排序、context pack、Q&A、跨论文综合和文章草稿。
7. **Skill 层**：把自然语言意图映射到稳定 CLI/API，隐藏内部工作包。

### 4.2 数据所有权

- 原始来源和 hash 是证据真源。
- Paper/Repo records、claim ledger、assessment event，以及经独立 review 接受并由现有 transaction 发布的 claim-domain annotation/event/head 是知识真源。domain annotation 是 claim 的 versioned canonical sidecar，不修改或复制 claim ledger 的文本、证据和 assessment。
- Candidate、preview、research session 和 article draft 都是可丢弃、可重建的建议层，只能位于 checkout 的 `.work/research/**`；它们不是 Vault 的 `.raw/derived/**`。
- Markdown、图索引、BM25、SQLite 和 context pack 是投影。
- 用户笔记永远由用户拥有，编译器不得覆盖。

### 4.3 冻结的架构决策

以下决策在 W1–W7 不再反复讨论；只有真实纵切证明它们不可行时才写 architecture decision record 修订：

1. `video_paper_wiki` 是唯一 Vault 写入内核；不再创建第二套 transaction、claim ledger、catalog 或 BM25。
2. `video_paper_wiki_research` 是薄的离线 request/observation/orchestration 包。其 import closure 禁止 `socket`、HTTP client、`vpwiki-admin` 和 Vault mutation；它只写 checkout 的 `.work/research/**`。
3. Codex Repository Skill 通过平台只读 Web connector 执行显式注册的 HTTPS origin 请求。Request artifact 冻结 method、origin/host、允许的 redirect、超时、大小、内容类型和速率等**要求**；只有 executor 可观察并返回的约束才能被记为已执行。Observation 必须声明 capability profile：`normalized-content` 记录规范化内容、来源/最终 URL、时间、内容 hash、connector 身份及所有缺失传输字段的原因，只足以支持 P0 预览；`byte-exact` 还记录原始响应文件/hash、redirect chain、headers/content type，以及 executor 能证明时的 DNS/IP 信息，才可进入需要字节 provenance 的 ingest。平台 connector 或外部 operator 负责执行，engine 只校验它收到的证据，绝不补造不可见的 raw bytes、headers、redirect 或 DNS/IP。
4. LLM 只消费有界输入并生成 schema 化 proposal；它没有文件写入权。确定性代码先校验 proposal，再生成可检查 diff，最后交给现有 publication transaction。
5. Knowledge Graph 是 canonical record、claim 和 evidence relation 的可重建投影。BM25 与 graph expansion 负责召回；不要求向量数据库才能运行。
6. `extracted|inferred|ambiguous|contradicted|unknown` 是展示层的统一证据词汇，底层映射到现有 claim lifecycle、assessment 和 evidence locator，不另建平行真源。
7. 候选论文、候选代码和文章草稿都不是事实；只有经用户选择并通过 engine 校验的对象才进入正式库。
8. Repository Skills 对 Codex、Claude 等 agent runtime 保持中立：核心流程与 schema 共用，仅 wrapper/trigger 元数据按 runtime 生成。
9. 编译保持两阶段：source analysis/extraction 先生成独立、hash-bound proposal，entity/alias resolution 与 canonical page generation 只消费通过校验的 proposal；两个阶段都不能直接 apply。现有 draft → publication prepare/inspect → operator apply 是提交链，不再创建附件中的第二个 compiler/transaction。
10. semantic hash 只用于 dirty/cache 提示，不能成为 canonical identity 或幂等真源。canonical 重放继续绑定 exact source bytes、schema/compiler/pipeline hash、完整 locator/assessment set、transaction/Vault snapshot 和 receipt。
11. 每个 Repository Skill 同时提供 closed `skill-contract.v1`，声明输入/输出 schema、允许命令、网络/写入策略、预算、重试和幂等语义；该 manifest 可被 lint 和 adapter 生成器检查，但自身不授予 capability，也不能放宽 CLI/operator 边界。
12. P4 的 rank fusion 只融合可独立解释的有序候选列表，禁止直接相加 BM25 raw score、cosine raw score 或图置信度。首版至少融合现有 CJK BM25、exact alias/catalog 和 typed graph；dense ranker 不可用时结果仍完整可运行。
13. `claim-classification-proposal.v1` 和 `video-comparison-fact-proposal.v1` 只存在 `.work/research/**`，没有 canonical 效力。W5 先以新增 namespace、无损兼容旧 claim 的 `claim-domain-annotation.v1` 和 append-only `domain-annotation-review.v1` 承载经审查的类型与结构化值；annotation 必须绑定 active `domain-profile.v1` 的 exact SHA-256。active domain/comparison profile 只能由 transaction-published profile-head registry 选择，agent/proposal 不能切换。`video-comparison-fact.v1` 再从 accepted annotation、当前 claim/assessment/evidence、active profile/head exact bytes 确定性投影。缺少 accepted current-profile annotation 的旧 claim 仍可检索，但不能产生 supported typed edge 或通过 apples-to-apples 完成项。

### 4.4 Obsidian 目录与视图

第一版保持现有已验证目录，并补齐用户需要的导航投影：

```text
Checkout/
└── .work/research/               # Vault 外：preview/session/candidate/draft 临时建议层

Vault/
├── .raw/
│   ├── captured/                 # PDF、源码和外部响应的不可变证据
│   └── derived/                  # 仅已批准来源的解析块与受管派生产物
├── wiki/
│   ├── sources/                  # 人可读来源卡；真源仍是 source ledger + raw bytes
│   ├── papers/                   # Paper 页面
│   ├── code/                     # Repo/commit 页面
│   ├── concepts/                 # Concept/Method/Model/Training/Dataset/Inference 页面
│   ├── synthesis/generated/      # 用户批准后 create-only 发布的不可变综合快照
│   ├── views/                    # Models/Methods/Components/Training/Datasets/Benchmarks/Inference/Questions Bases 与索引
│   └── meta/                     # records、ledgers、reviews、operations、registries
└── inbox/                        # 人工资料入口；不由研究 agent 随意改写
```

`Method / Model / ArchitectureComponent / TrainingRecipe / Dataset / Benchmark / InferenceRecipe / EvaluationMetric` 首先是带 `kind` 和 taxonomy axis 的 typed concept，不立即复制成八套领域模型。`Comparison / Synthesis / ReproductionPlan / ExperimentPlan / OpenQuestion` 是研究 artifact kind，默认仍在 `.work/research/**`。Obsidian 的 `wiki/views/` 和 Bases 提供分目录般的 human UI；P6 再根据真实查询决定是否迁移为独立物理目录。这样 P1 就能复用现有 `Paper / Code / Concept` compiler，避免为视觉层级重写已经验证的发布链。

附件中的目录只做概念映射：`normalized/**` 对应现有 `.raw/derived/**`，`ledgers/**` 与 `state/**` 对应 `wiki/meta/**` 和可重建 catalog/index，`research/**` 与 `review/candidates/**` 对应 checkout 的 `.work/research/**`。R2 禁止新建这些平行 root。`wiki/synthesis/generated/<artifact-id>.md` 在 W6 才作为新的受管、create-only namespace 加入 transaction、receipt audit、backup/restore 和 migration。它是不可变生成快照：用户要继续编辑时，在 Obsidian 中手工复制到用户所有的 `wiki/notes/**`；agent 和 compiler 永远不创建或覆盖该副本。需要由 agent 改稿时，系统基于旧 artifact 生成新的 draft 和新 artifact ID，以 `supersedes` 关系串起版本，不能覆盖旧快照。

## 5. 仓库借鉴与复用策略

审计使用 2026-09-04 拉取的精确 commit；精确 commit/tree、许可证与源码字节哈希保存在 [`external-reuse-audit-2026-09-04.yaml`](external-reuse-audit-2026-09-04.yaml)，并由 closed planning schema [`external-reuse-audit.v1.schema.json`](external-reuse-audit.v1.schema.json) 校验。六仓均观察到 MIT 文件；该观察不关闭项目的外部 provenance/license gate。若未来复制源码而非独立实现，必须保留许可证和 attribution。

| 来源与 pin | 代码核验到的能力 | v1 决策 | 明确不采用 |
|---|---|---|---|
| [`claude-obsidian@9f8c119`](https://github.com/AgriciDaniel/claude-obsidian/tree/9f8c1199047eac2c3828496279fbb7ba9540b90b) | `transaction.py:1-6,1388-1814` 是带 lock、precondition、journal、dirfd confinement、atomic replace、rollback/recovery 的事务内核；`capture.py:1-6,585-720` 是 offline-first、防 TOCTOU capture；`ledgers.py:396-1100` 有稳定 source/locator 与 claim 证据规则；`scripts/bm25-index.py:1-49,134-498` 实现 CJK n-gram BM25 | **直接复用**现有 pinned submodule 和公开契约；当前 repo 已有 pin-authenticated adapter 与回归测试 | 不追随远端 main、不 fork、不改上游内部协议、不另造写入引擎 |
| [`Ar9av/obsidian-wiki@f268d43`](https://github.com/Ar9av/obsidian-wiki/tree/f268d437442a551e4121aa1b7dd680ef987a8d50) | `graph_analysis.py:315-600` 有 cohesion、Brandes centrality、bridge/surprise/BFS；`context_pack.py:354-424` 有 token budget；`graphrag.py:548-648` 有 graph expansion；`.skills/*` 定义来源标记及有界研究。其架构文档明确主流水线由 agent 执行 Markdown Skills，不是 Python 自动化服务 | **借鉴接口并按本项目 schema 重写**；若后续复制纯 Python 实现，先关闭外部代码 provenance/license gate | 不把 Markdown 变成真源，不复制其整套 session/storage、QMD 副作用或未事务化写入 |
| [`nvk/llm-wiki@7c94c9b`](https://github.com/nvk/llm-wiki/tree/7c94c9bf2968f17deb496b285db0afdb610a01d9) | `commands/research.md:115-520` 与 `references/research-infrastructure.md:73-427` 定义多轮 session、event log、checkpoint/resume、3–5 条 research paths、gap reflection、support/opposition/falsification 和串行 compile；确定性脚本明确不执行 agentic workflow | **借鉴编排协议**：持久 session、bounded rounds、多视角研究、并行只读发现/串行发布、runtime-neutral Skill source | 不复制 prompt 作为生产状态机，不采用无锁并行 Markdown 写入、嵌套 worker 直接落盘或激进自动 ingest 模式 |
| [`atomicstrata/llm-wiki-compiler@cbd09c6`](https://github.com/atomicstrata/llm-wiki-compiler/tree/cbd09c6c415f36b6001adf89a02aa805a5a5aba6) | `confined-fetch.ts:67-280` 实现 origin/host allowlist、HTTPS、逐跳 redirect、DNS 私网拒绝、IP pin、TLS SNI、超时/字节/类型限制；`rules-citations.ts:42-185` 校验 citation grammar/source/行界；`freshness/index.ts:18-142` 用 source ownership/existence/hash 区分 fresh/stale/orphaned/unverified；`linter/index.ts:33-111` 只读汇总 | **按可观察行为和 adversarial cases 独立实现 Python 版本**；证据 hash freshness 纳入现有 audit | 不复制 TS runtime/可变 state 或 Markdown-as-primary compiler；其 LLM citation-support judge 不能当确定性事实证明 |
| [`SamurAIGPT/llm-wiki-agent@4ea2c7f`](https://github.com/SamurAIGPT/llm-wiki-agent/tree/4ea2c7f916a8f7de6c787d1be014cd392250c161) | `AGENTS.md:22-106` 给出 source/entity/concept/synthesis 结构与工作流；`build_graph.py:94-371` 有 wikilink/LLM edge 和 seeded Louvain；`query.py:30-81` 是关键词/CJK bigram 加一跳邻居。代码同时显示 ingest 让 LLM 直接写文件、graph 去重会丢方向/多关系 | **只借鉴信息架构和可理解的操作语言**，作为 Obsidian 页面/导航 UX | 不复制直接写文件的 ingest、弱验证 query/semantic lint 或图实现，不让 LLM 图边绕过 claim/evidence 契约 |
| [`SwarmVault@815412d`](https://github.com/swarmclawai/swarmvault/tree/815412d24298e59e5073ded1ddd6c0e6aee9b91b) | `types.ts:978-1001,1282-1330` 有 typed edge/context pack；`graph-query-core.ts:196-588` 有过滤和有预算 traversal；`context-packs.ts:163-386,522-665` 记录 included/omitted；`vault.ts:1729-2175` 有 community 与 contradiction candidate | **独立实现稳定排序的 graph traversal、context budget/omission 和图校验**，边必须绑定本项目 claim/evidence locator | 不复制 TS daemon/monorepo/provider。其 citation 只有 source ID、contradiction confidence 算法不可靠、Louvain 未固定 RNG，均不能原样采用 |

### 5.1 复用优先级

1. **直接调用**：现有 `video_paper_wiki` 与 pinned `claude-obsidian`；这是已经过大量测试的生产基础。
2. **独立实现已核验的行为**：atomicstrata 的 confined fetch/citation/freshness；Ar9av 的 graph/context-pack 接口；SwarmVault 的 context budget 与图完整性规则。
3. **借鉴协议和 UX**：nvk 的可恢复 research session、SamurAIGPT 的页面信息架构。
4. **暂不引入**：第二套 wiki runtime、第二个检索索引、Neo4j/远程向量库、daemon、自动无审查 ingest、多个 agent 并发写同一 Vault。

每项借鉴或移植都必须在工作包中记录 upstream repo、完整 commit、源文件、许可证、适配差异和新增测试。README 只能用于理解目标，不能替代源码和运行验证。当前 `docs/ai/task-index.yaml` 中的 external provenance/license human gate 仍保持开放，因此 W1 使用本项目独立实现，不复制新增外部源码；未来若要复制而非重写，必须单独记录该 gate 的真实决定。

## 6. 新增领域契约

只新增现有 schema 无法表达的对象。所有 proposal/candidate/session 只存在 `.work/research/**`；进入 Vault 的仍是现有 paper/repo/claim/assessment/publication 真源。每个 schema 都要同时提供 valid、invalid、unknown-key、oversize 和 cross-object identity fixtures。

### 6.0 `connector-request.v1` / `connector-observation.v1`

- request 固定 connector ID/version、GET、exact origin/host、允许的 redirect origin、请求数、deadline、最大传输/解码字节和允许 content type；这些是 executor 必须核验或明确报告无法观察的要求，不因写进 request 就自动成为网络执行证据；
- observation 固定 `capability_profile=normalized-content|byte-exact`，绑定 request SHA-256、来源 URL、observed_at、执行 connector/version 和规范化 payload SHA-256；
- `normalized-content` 允许平台 connector 只导出规范化题录/页面内容。`final_url`、`redirect_chain`、`headers`、`content_type`、`dns_ips` 和 `raw_response_sha256` 中任何不可见项必须为 `null`，并逐项给出 `unavailable_reason`；这种 observation 只可用于 preview/discovery，不能证明原始字节已保留；
- `byte-exact` 必须额外绑定 raw response 文件、SHA-256、最终 URL、逐跳 redirect、content type 和 executor receipt；DNS/IP 只有 executor 实际提供时才记录。需要原始来源 provenance 的 ingest/capture 只接受该 profile 或现有外部 operator 的等价、已验证 observation；
- response bytes 如可获得，单独暂存在 `.work/research/<session>/observations/`，schema 不内嵌无限内容；
- local CLI 只能生成 request 和校验 observation，不能自己打开 socket。

### 6.1 `arxiv-metadata.v1`

- canonical arXiv ID、解析到的版本、标题、作者、分类、发布时间和更新时间；
- 作者摘要原文、abstract/PDF canonical URL；
- API endpoint、响应 hash 和观察时间；
- `preview_only=true`、`ingest_authorized=false`。

### 6.2 `paper-preview.v1`

- 绑定 `arxiv-metadata.v1` 的 SHA-256；
- 中文一句话摘要、研究问题、方法、贡献、结果、局限、相关性；
- 每一项标注 `extracted|inferred|ambiguous|unknown`；
- `evidence_scope=abstract-only|full-text`；
- generator runtime/model、prompt SHA-256、输入 metadata SHA-256 和输出 SHA-256；
- preview 不含可变 decision，也不授予 ingest authority。

### 6.3 `candidate-decision.v1`

- append-only event：`ingest|skip|later|publish`；
- 绑定 preview/candidate/synthesis SHA-256、当前 user turn reference、decided_at；
- 同一对象的当前状态由有序 event 归并，不原地篡改 preview；
- `ingest` 或 `publish` 只启动 approval/bundle 流程，不冒充 operator apply receipt。

### 6.4 `research-session.v1`

- seed paper/query、目标技术点和深度预算；
- 已发现、已预览、已入库、已跳过和待处理 candidate；
- connector observations 和失败原因；
- append-only round events：本轮 research lens、查询、来源集合、new relevant yield、duplicate ratio、support/counterevidence coverage、未决 gap 和已耗预算；
- research lens 至少区分 `method|benchmark|implementation|counterevidence|reproduction`，某 lens 不适用时要记录理由，不能默默跳过反证搜索；
- stop policy/config SHA-256 与 `stop_reason=yield_below_threshold|paths_covered|duplicate_ratio|budget_exhausted|user_stop`；相同 observation/session/config 必须推导出相同停止决定；
- 可恢复的下一动作 `next_action`；
- session 本身不授予入库或发布权限。

### 6.5 `workflow-progress.v1`

- 不新造主状态机，直接投影现有 canonical ingest 状态：`absent → planned → prepared → capture_inspected → captured → parsed → drafted → ingest_inspected → applied_provisional → verified`；
- 正交字段固定为 `approval_binding=not_bound|external_ref_bound`、`capture_disposition=null|create|reuse`、`publication_stage=none|prepared|inspected`；`prepared` 已蕴含 ref 和 blob 均完成校验，`verified` 只表示 ingest 完整性，不表示 claim 已人工 accepted；
- 当 canonical state 停在 `planned` 时，UI 的 `next_action` 可以分别显示 `awaiting_external_approval_ref`、`awaiting_external_bytes` 或 `ready_to_prepare`。这些只是缺失输入提示，不是 `approved` 状态；
- 失败追加 failure event 并停留在最后一个可由 immutable artifact 证明的 canonical state，不能写一个可变 `failed` 终态；`resume` 每次重新验证 artifact 后推导下一动作。

### 6.6 `paper-candidate.v1`

- canonical paper ID、发现来源、关系 `cites|cited_by|similar|same_method|same_dataset`；
- 排名分解：seed distance、年份、citation signal、topic overlap、去重结果；
- discovery evidence 和 freshness；
- candidate 本身不含 decision；人类选择只存在 append-only `candidate-decision.v1`。

### 6.7 `code-candidate.v1`

- paper ID、repo ID/URL、发现来源和 observation SHA-256；
- evidence signals：`paper-linked|author-linked|author-org|community-only|ambiguous`；
- canonical officiality 继续使用现有 `official|unofficial|unverified_candidate`：paper 原文链接形成的 `paper-linked` 或完成作者身份核验的 `author-linked` 才映射 `official`；仅组织归属的 `author-org` 和 `ambiguous` 保持 `unverified_candidate`；`community-only` 映射 `unofficial`；
- 许可证只记录 observed SPDX/file hash，是否允许保留源码由 `EXTERNAL-PROVENANCE-LICENSE-001` 决定。

### 6.8 `graph-edge-projection.v1`

- `subject_id`、`predicate`、`object_id`；
- 支持 edge 的 claim/evidence IDs；
- 状态和置信度来源；
- `derived_by` 与 generation hash；
- `status=candidate|supported|contested`，矛盾探测只能先产生 candidate；
- predicate 必须来自版本化 relation profile，并验证 subject/object kind。初始候选集为 `introduces|extends|implements|reproduces|trained_on|evaluates_on|uses_component|uses_objective|distills_from|compares_with|improves_over|ablates|supersedes|alias_of|derived_from|has_checkpoint|has_code`；`supports|contradicts` 保持 evidence/claim relation，再投影到图，不与普通实体边混写；
- `improves_over|reproduces|ablates|evaluates_on` 必须绑定 comparison context 与 claim/evidence，不能从页面共现或模型相似度推断为 supported；
- 图谱只接受有来源的边，不能把 embedding 相似度直接写成事实边；
- 该对象由 canonical truth 确定性生成并带 generation hash，删除后可重建，绝不成为平行知识真源。

### 6.9 `context-pack.v1`

- query、intent `quick|standard|compare|implementation|reproduce|survey|research`、target kinds、catalog/graph/BM25 generation 和严格 token/byte/item budget；
- 每个候选记录 `exact|bm25|graph|optional_dense` 各自 rank、确定性 RRF 结果和选择理由；raw scores 不跨 ranker 相加，dense 缺失时不能改变基础功能可用性；
- included items 带选择理由、claim ID、evidence-unit ID 和精确 locator；
- omitted items 带 `budget|duplicate|low-rank|unsupported|stale` 原因；
- 相同输入 snapshot/config 产生 byte-identical pack。

### 6.10 `synthesis-artifact.v1`

- query/topic、使用的 context pack 和 generation；
- 共识、差异、矛盾、未知项；
- 逐段 claim refs；
- artifact kind：`answer|comparison|research-note|article-draft|reproduction-plan|experiment-plan|open-question`；
- 默认 `draft`，不得自动升级为 accepted claim。

### 6.11 `support-review.v1`

- 绑定 exact answer/synthesis artifact SHA-256、被审查的 factual unit/paragraph ID、claim ID、evidence-unit ID、locator 与 source-byte SHA-256；
- locator 做双向绑定：`artifact factual unit → claim/evidence locator` 必须唯一可解析，`locator → frozen source bytes/span → same factual unit` 必须可回查；语法、hash、范围或反向引用任一不成立即确定性拒绝；
- 语义审查结果只允许 `supported|partially_supported|unsupported|contradicted|not_assessable`，并记录 reviewer、reviewed_at、理由和引用 span；
- `supported` 表示该 factual unit 的全部实质断言均被所引证据支持；`partially_supported` 不能计为通过。模型自评只能是 proposal，不能替代冻结 gold review 或人工发布 review。

### 6.12 `taxonomy-extension-proposal.v1` / `claim-classification-proposal.v1`

- 现有 `taxonomy/v1.json` 保持 immutable；新 term 提案携带 axis、canonical slug、中文/英文 label、aliases、supporting paper/claim locators、collision check 和 proposed version，位于 `.work/research/**`；
- 附件给出的 task、paradigm、backbone、component、training、inference、evaluation 词表只作为候选 seed。`t2v|text-to-video`、`flow_matching|flow-matching` 等先归一化，不能静默创建 canonical term；
- claim 分类是正交 proposal，`claim_kind=architecture|training|empirical_result|implementation|ablation|limitation|reproducibility|license|resource_requirement`；proposal 不改变现有 `provisional|accepted|contested|unsupported|deprecated` assessment，也不把 `stale` 变成 claim status；
- classification proposal 必须绑定 claim ID、claim text SHA-256、evidence fingerprint、当前 assessment head、`domain_profile_sha256`、建议类型/结构化值及每个值的 locator；在 W5 review/publication 前，它不能生成 supported graph edge、canonical comparison fact 或满足完成定义；
- taxonomy v2 迁移必须另有 versioned contract、migration、回滚、完整回归和真实 review；W1/W2 不修改 taxonomy，repository seed/overlays 仍为 67。

### 6.13 `claim-domain-annotation.v1` / `domain-annotation-review.v1`

- W5 新增并固定以下 managed canonical namespace：`wiki/meta/profiles/domain/<profile-sha256>.json`、`wiki/meta/profiles/comparison/<profile-sha256>.json`、`wiki/meta/registries/domain-profile-head.json`、`wiki/meta/registries/comparison-profile-head.json`、`wiki/meta/claim-domains/<claim-id>/<annotation-id>.json`、`wiki/meta/claim-domain-reviews/<claim-id>/<event-id>.json` 和 `wiki/meta/registries/claim-domain-heads.json`。它们与现有 claim ledger 一起由同一 publication transaction、receipt、managed-set audit 和 backup/restore 覆盖；禁止另建 claim ledger 或让 agent 直接写入；
- `domain-profile.v1` 的 canonical bytes 完整覆盖 claim-kind registry、结构化 field schema、unit normalization、metric direction 和 qualifier rules；annotation 固定 `annotation_id`、claim ID、stable subject ID、claim text SHA-256、evidence fingerprint、assessment head event ID、`domain_profile_sha256`、`claim_kind`，以及零到多个 `field/original_value/original_unit/normalized_value/normalized_unit/direction/qualifiers/locator`。人工或 LLM 的未记录换算不能进入 annotation 或 projection；
- `domain-profile-head.json` 与 `comparison-profile-head.json` 各自唯一选择 active immutable profile path/SHA-256 和 predecessor；profile 或 head 只能经 inspected transaction + independent operator 发布。agent、proposal、query caller 不得指定或切换 active profile。profile 升级保留旧 bytes/history，不原地修改；
- `domain-annotation-review.v1` 是 append-only event，单独记录 `accepted|contested|rejected|superseded`，不得复用或改变 claim assessment。`claim-domain-heads.json` 的每项原子绑定 `{claim_id,domain_profile_sha256,annotation_id,review_event_id}`；annotation successor、review head 与 registry entry 在同一 inspected transaction 中切换，不能分别更新；
- 只有 current annotation review 为 `accepted`、所绑定 claim 的当前 assessment 为 `accepted`、claim text/evidence/assessment head 仍精确匹配当前 canonical bytes，并且 annotation 的 `domain_profile_sha256` 等于 active domain-profile head 的 exact bytes，才可驱动 supported typed edge 或 comparison projection；claim assessment 为 `contested` 时最多产生 contested projection，profile 过期、head 替换、混用或其余失配只能得到 candidate、unsupported 或 stale；
- annotation ID、review event ID 和 profile ID 由 closed canonical bytes 推导。修订产生 successor 并保留历史，不能原地改写；
- 旧 claim 没有 domain annotation 时继续按既有 schema、compiler、catalog 和 query 工作。迁移先新增 namespace/projector，不重写 claim ID 或旧 ledger bytes；rollback 停止选择新 generation 并恢复旧 projector，旧数据保持可读。fixture review 只能验证机制，真实 accepted annotation 仍需对应人工 review 证据。

### 6.14 `video-comparison-fact-proposal.v1` / `video-comparison-fact.v1`

- proposal 位于 `.work/research/**`，可从未审查 classification 建议产生 `candidate|not_comparable`，不能进入 canonical catalog/graph，也不能满足 W5 完成项；
- canonical `video-comparison-fact.v1` 只由 accepted current `claim-domain-annotation.v1` bytes、annotation review event、原子 claim-domain head entry、当前 claim/assessment/evidence bytes、active domain/comparison profile bytes 及两个 profile-head registry bytes 确定性投影；它把已审查值规范为 `field/value/unit/direction`，并绑定 annotation、paper/model/checkpoint、source claim/evidence locator 和观察版本；同一 comparison generation 禁止混用不同 domain/comparison profile；
- comparison context 至少覆盖：active/total parameters、resolution、frames、FPS、duration、inference steps、CFG/guidance、benchmark version/split、zero-shot/fine-tuned、teacher/student、training data scope、hardware、metric direction 和 checkpoint；
- lint 先做可确定的单位、字段、identity、版本和缺失限定检查；不同 context 的值默认 `not_comparable`。语义矛盾只生成 candidate，不能自动修改 assessment；
- projector 不得自行补充、猜测或修正 annotation 中没有的值；projector generation manifest 必须列出 annotation、annotation review、claim-domain head、claim/assessment/evidence、domain/comparison profile 及 profile-head 的路径和 SHA-256。任一输入改变都生成新 projection generation；旧 profile 的 projection 可保留为历史，但不能出现在 current supported result。删除 comparison fact 后可由这些 canonical bytes byte-identical 重建；它不替代原 claim、evidence、assessment 或 domain annotation。

### 6.15 `reproduction-plan.v1`

- 绑定目标 paper/model、officiality 已核验的 repo + full commit、入口脚本/配置行 locator、checkpoint/许可证 observation、软件环境、硬件假设、数据要求和预期输出；
- 每项标注 `verified|inferred|unknown|blocked`，`verified` 必须能回到 claim/evidence；不得把 README 宣传、社区 fork 或不可访问权重写成已复现；
- 只生成 `.work/research/**` proposal 和用户可读草稿，不下载权重/数据、不启动训练、不声称复现成功。

### 6.16 `skill-contract.v1`

- 与每个 `SKILL.md` 同版本，固定 trigger/intents、CLI commands、input/output schema、allowed tools、network/write policy、token/file/time/source budget、retry、idempotency 和 stable errors；
- `SKILL.md` 与 manifest 的命令/能力差异由 closure test 拒绝；跨 Agent wrapper 只能收窄，不能扩大 canonical contract；
- manifest 是可检查声明，不是 OS capability、approval 或写入授权。实际边界仍由 `vpwiki`/`vpwiki-research` import/PATH/socket tests、平台 tool policy 和独立 operator 强制。

### 6.17 LLM proposal 边界

Repository Skill 负责调用当前 Codex 会话做摘要、回答和写作，并输出上述闭合 schema；CLI 不绑定第二个模型 provider。每个 LLM proposal 必须携带 input/context-pack hash、prompt/template hash、runtime/model 标识和生成时间。`vpwiki-research ... validate --proposal <file>` 只做确定性 schema、预算、引用和 hash 校验；失败时保留输入与错误码，可在同一输入上重放。Standalone CLI 没有 proposal 时只生成请求/上下文，不伪装成已经完成摘要。

## 7. CLI 与 Skill 设计

### 7.1 面向用户的稳定命令

```bash
# 本地 CLI：生成只读 connector request；真正获取由 Codex Web connector 完成
vpwiki-research paper request --arxiv 2311.15127
vpwiki-research paper observe --request <request.json> --response-file <response.atom>

# Codex 生成 proposal 后，本地确定性校验、渲染和记录用户选择
vpwiki-research paper preview validate --metadata <metadata.json> --proposal <preview.json>
vpwiki-research paper preview render --proposal <preview.json>
vpwiki-research paper decide --preview <preview.json> --decision ingest

# 研究扩展
vpwiki-research research start --seed arxiv:2311.15127 --topic "时空建模"
vpwiki-research research request-next --session <session-id>
vpwiki-research research observe --session <session-id> --observation <observation.json>
vpwiki-research research status --session <session-id>

# 代码
vpwiki-research code request --paper arxiv:2311.15127
vpwiki-research code observe --request <request.json> --response-file <response.json>
vpwiki-research code rank --paper arxiv:2311.15127 --observations <dir>

# 问答和综合：CLI 构建 context，Codex 生成，CLI 再验证 proposal
vpwiki-research ask context --mode compare --question "DiT 视频模型如何处理时间维度？"
vpwiki-research ask validate --context <context.json> --proposal <answer.json>
vpwiki-research synthesize context --kind compare --topic "时空注意力"
vpwiki-research synthesize validate --context <context.json> --proposal <article.json>
vpwiki-research reproduce context --paper arxiv:... --repo repo:github:...@<commit>
vpwiki-research reproduce validate --context <context.json> --proposal <reproduction-plan.json>
```

这些是可脚本化、零 egress 的内部命令；普通用户只需在 Codex 对话中表达同样意图。Repository Skill 执行 request → Web connector → observation → Codex proposal → validate/render。它只能按 W1 capability spike 实际证明的 profile 构造 observation；平台只给规范化内容时，不得把它包装成 raw response。底层 `vpwiki ingest plan/prepare/capture inspect/publication inspect` 保留为 engine API；任何 fetch/apply 仍不进入 agent PATH。W1 必须用 import-closure、socket sentinel、PATH sentinel 和 fake connector tests 证明 `vpwiki`/`vpwiki-research` 无网络与 admin 能力。

### 7.2 Repository Skills

| Skill | 触发意图 | 结果 |
|---|---|---|
| `video-paper-preview` | “看看这篇 arXiv” | 自动题录获取、中文摘要和入库选择 |
| `video-paper-ingest` | “把这篇入库” | PDF request/observation → 草稿 → diff → inspected bundle；operator receipt 后确认发布 |
| `video-paper-expand` | “从这些论文继续找” | 去重候选、排序理由和预览队列 |
| `video-paper-code-map` | “找官方代码并解释实现” | repo/commit/path/line 级证据 |
| `video-paper-query` | 事实问答和比较 | context pack、引用完备回答 |
| `video-paper-synthesize` | 综述或文章 | 结构化 synthesis artifact 和 Markdown 草稿 |
| `video-paper-reproduce` | “如何复现这篇论文” | commit/config/checkpoint/hardware/unknown 全绑定的复现计划草稿 |
| `video-paper-audit` | 检查知识库 | 来源、claim、freshness、矛盾和索引状态 |

Skill 可以调用稳定命令和当前 Codex 推理；每个 Skill 的 `SKILL.md` 与 `skill-contract.v1` 必须同版本。网络 connector、Vault transaction 和模型推理的结果必须分别记录，不能混成一个不可审计步骤。

### 7.3 MCP 的边界

MCP 不是 P0–P5 的启动依赖。CLI/Skill 纵切稳定后，P6 可生成一个薄适配器，只暴露 `status/search/query-context/research-status/request/validate/transaction-preview` 等只读或 proposal 操作，并复用同一 closed schema 与 CLI envelope。`source_add`、`review_accept`、`apply`、index build、真实 Vault mutation、任意 URL fetch 和 provider credential 都不进入 agent MCP。若未来需要写能力，必须作为 workspace/agent 外的 operator broker 单独设计、授权和验收，不能通过换协议绕过当前边界。

## 8. Agent 编排

### 8.1 开发期

- **Architect（GPT-5.6 Sol Ultra）**：产品目标、系统边界、schema/API、工作包、整体验收。
- **Builder（GPT-5.6 Sol Medium）**：按冻结契约实现生产代码和测试。
- **Repo Steward（GPT-5.6 Sol Medium）**：独立 diff、安全、CI、PR 和精确 head 证据。

团队始终只有这三个角色，最多两个 active child。六仓代码阅读是本次 Architect 的架构职责与 Repo Steward 的独立核验，不增加第四个常驻角色。同一文件同一时刻只有一个写入者。外部仓库代码只有在许可证、pin、provenance gate 和适配成本明确后才进入实现；优先调用公开接口或按已核验行为独立实现。

### 8.2 运行期

一个 Research Orchestrator 管 session，底下是有界、可重放的逻辑步骤：

```text
Intake Agent        规范化 seed / query
Discovery Agent     找候选并提供来源
Preview Agent       摘要并等待用户决定
Ingest Agent        只处理已批准候选
Code Agent          找官方 repo 并建立代码证据
Graph Agent         生成可验证边、矛盾组和社区
Answer Agent        从 context pack 回答
Synthesis Agent     生成综述或文章草稿
```

Agent 之间只传 schema 化 artifact，不靠聊天上下文隐式传状态。每个 session 有预算、重试上限、失败码和 `next_action`；某篇失败不会阻塞其他候选。

这些名称不是八个常驻或并发 Codex 子 agent。默认由一个 orchestrator 串行执行；只有互不写同一路径的 discovery/reading proposal 才可在现有两子 agent 上有界并行，所有 compile、decision 归并和 publication preparation 都串行。

## 9. 实施阶段

### 全阶段不变量

- W1–W7 都不得修改 `docs/seed/engine-mvp.json` 或任何 overlay；repository seed catalog 固定为 67。自动发现和真实入库只扩展用户的隔离 Vault/catalog 投影。若要改变这 67 项，必须另开 re-scope packet 并记录 human gate。
- `vpwiki` 与 `vpwiki-research` 保持零 egress、无 admin、无真实 Vault mutation；所有 agent 生成物先进入 `.work/**`。
- 真实 PDF、仓库源码、用户 claim 决定、Obsidian 视觉验收和备份锚点不能用 fixture 代替；第 11.3 节 gate 必须保持真实状态。
- 每阶段的 fixture CI、live connector smoke、真实 Vault/operator observation 三类证据分开记录。

### P0：可用入口（最高优先级）

目标：用户给一个 arXiv 链接，系统自动给中文摘要并等待入库决定。

交付：

- `CAP-WEB-OBS-001` capability spike：在当前 Codex Web connector 上逐项记录能否获得规范化 payload、来源/最终 URL、raw bytes、headers/content type、redirect chain 和 DNS/IP；冻结 observation profile 与 operator fallback，缺失字段必须显式为 `null + unavailable_reason`；
- arXiv request/observation adapter、metadata/preview/decision schema；
- 离线 `paper request/observe/preview validate/preview render/decide` CLI；
- `video-paper-preview` Skill + closed `skill-contract.v1`；
- `.work/research/**` 中的 preview 列表和 `pending/ingest/skip/later` 派生状态；
- README 的 3 分钟 quickstart；
- 固定 fixture 测试，CI 不访问真实网络；
- 一次真实 arXiv ID 的人工 smoke test。

验收：在具备 Codex Web connector 的会话中，从自然语言输入到中文摘要最多一次用户请求；即使 connector 只能提供 `normalized-content` 也可完成 abstract-only 预览，但必须如实保留 capability 限制。摘要明确是 abstract-only；决定前后真实 Vault/catalog 均不变化，repository seed/overlays 仍为 67；本地两个 CLI 的 import/socket/PATH 测试证明零 egress 和无 admin。任何需要原始来源字节的后续 ingest 都不能拿该 smoke 冒充 `byte-exact` 证据。

### P1：真实单篇入库

目标：用户回复“入库”后，由 orchestrator 自动生成并串起全部 engine artifact，用户不再手工拼底层命令。

交付：

- workflow orchestrator 复用现有 capture、Docling、draft、review、publication inspect；
- 统一 `workflow status/next/resume`；
- Paper Page、claims、locators、Concept 反向链接；
- source analysis/extraction 与 canonical compile 两阶段分开；figure/table/equation 使用现有 Docling artifact + PDF locator，不复制原始真源；
- 生成 `claim-classification-proposal.v1` 与未知 taxonomy term review queue；本阶段不修改固定 taxonomy v1；
- 将一次“入库”选择绑定 decision 和 plan/external-input request；orchestrator 等待外部提供的 approval-ref 与 PDF blob，只校验二者的 exact digest binding。当前 ref 不含可验证签发者，也不等于批准；需要记录“谁批准了下载”时必须另建可签名 `approval-attestation`，不能篡改 `approval-ref.v1` 语义；发布前展示 diff；
- agent 到此停止，现有独立 operator 完成 apply/index build 后，orchestrator 只读消费 receipt 并 audit；
- 首篇真实论文的可恢复纵切。

W2 保留现有 canonical ingest 顺序 `absent → planned → prepared → capture_inspected → captured → parsed → drafted → ingest_inspected → applied_provisional → verified`。`planned` 阶段的 UI 以正交 `next_action` 显示 `awaiting_external_approval_ref`、`awaiting_external_bytes` 或 `ready_to_prepare`；两份输入可以任意顺序到达，但只有 ref 已绑定且本地 blob digest/限制/PDF 校验全部通过，才进入 `prepared`。`capture_inspected` 的 `create` 分支必须等独立 operator apply result 才能成为 `captured`，`reuse` 分支也必须重新验证唯一 byte-matching sibling。失败只追加事件并停在上一可证明状态。decision、approval-ref、external bytes observation、capture apply result 和 publication apply result 是独立 artifact，不能互相冒充。

验收：一篇真实论文从 arXiv 到 Obsidian；所有 factual claim 有 locator 或明确 `unsupported`；中断后可恢复且不会重复页面/来源；receipt 绑定 exact inspected bundle。若要把最后的 operator 动作也变成对话内一步，必须先交付 P6 的可信 host approval broker，不能让 agent 调用 `vpwiki-admin` 规避边界。

### P2：种子论文自动扩展

目标：从已入库 seed 生成可审核候选，而不是自动灌库。

交付：

- OpenAlex/arXiv discovery adapter；
- references、citations、related topic、author/project page 四类论文来源；GitHub/Hugging Face 只产生 P3 code/checkpoint candidate observation，不下载仓库、权重或数据；
- canonical ID 去重、版本合并、候选评分解释；
- research session、队列和批量 preview；每轮记录 method/benchmark/implementation/counterevidence/reproduction lens、coverage gap、new-yield、duplicate ratio 和预算；
- 以冻结 stop config 确定 `yield_below_threshold|paths_covered|duplicate_ratio|budget_exhausted|user_stop`，支持 checkpoint/resume 与 byte-identical replay；
- 每篇仍由用户决定。

验收：对固定的 connector observation bytes、ranking config 和 stop config，3 篇 seed 产生 byte-identical 候选集与停止决定；重复论文只出现一次；每个候选说明“为什么找到它”和“基于什么来源”，gap report 同时显示支持、反证和未覆盖 lens。Live API smoke 只验证可获取性和 schema，不要求跨日期返回相同结果。

### P3：官方代码发现与映射

目标：对已入库论文找到官方代码并建立 commit 级证据。

交付：

- 从论文链接、作者组织和 README 反向引用发现候选；
- 候选保留 `paper-linked|author-linked|author-org|community-only|ambiguous` signals，并按 6.7 的规则映射现有 canonical `official|unofficial|unverified_candidate`；
- GitHub repo、许可证、完整 commit、文件和行号固定；
- Hugging Face/model-card/checkpoint 只作为候选 URL、revision 和许可证 observation；不下载权重，无法固定 revision 或官方性时保持 unverified；
- 复用现有 code capture、code-evidence manifest 和 Code Page；
- Paper ↔ Repo ↔ Method edge。

验收：`HUMAN-GATE-BASELINE-001` 与 `EXTERNAL-PROVENANCE-LICENSE-001` 有真实记录后，才对其确定的 5 个代表仓库完成 officiality、license observation 和 commit 证据；重要实现声明可定位到固定代码行，不能只引用 README 宣传。Gate 未关闭时仍可生成候选，但不得声称“五仓验收完成”。

### P4：知识图谱、矛盾与 Q&A

目标：让库能回答跨论文问题。

交付：

- 从 canonical records 构建图投影；
- 模型、训练、数据集、代码、推理和方法关系；
- contradiction groups 和 community detection；
- contradiction detector 只产生 candidate，不能自行修改 assessment；community 算法固定 seed、排序和 generation；
- versioned relation profile、subject/object kind 约束和 claim-backed `improves_over/reproduces/ablates`；
- 将 W2 的 `claim-classification-proposal.v1` 按 transaction-published active domain profile 通过独立 review 与现有 publication transaction 发布为 `claim-domain-annotation.v1` + append-only review/head；旧 claim 无 annotation 时保持兼容，但不能生成 supported 领域边或比较事实；
- 从 accepted current-profile annotation + 精确 annotation review/head、claim/assessment/evidence、active domain/comparison profile 与 profile-head bytes 确定性投影 `video-comparison-fact.v1`，并执行 apples-to-apples lint；proposal 只产生 candidate/not-comparable，canonical projection 显式携带 annotation、模型/checkpoint、参数口径、分辨率、帧数/FPS/时长、steps/CFG、benchmark version/split、训练方式、硬件、单位和 metric direction；
- CJK BM25 + exact alias/catalog + typed graph 各自排序 → deterministic RRF → evidence filter → context pack；dense ranker 仅为可选输入，缺失时全功能可用；
- section、claim、figure/table/equation block、implementation/config locator、benchmark result 和 comparison row 作为不同 `target_kind`，不只索引整页摘要；
- 分开记录 source-byte `fresh|stale|orphaned|unverified` 与 observed-at 时间衰减，禁止混成一个不可解释分数；
- 回答按 factual/inference/unknown 分段，并带 paper/page/block 或 repo/commit/line 引用。

验收：先证明 domain/comparison profile 与 profile-head、domain-annotation namespace、append-only review/atomic head、旧 claim 兼容、successor/rollback、transaction/receipt/audit/backup 与 byte-identical comparison projection；normalization profile substitution、accepted annotation 绑定 deprecated profile、mixed-profile comparison、profile-head replacement/reopen 必须 fail closed 或成为 stale/non-current projection。fixture 只能验证机制，真实 supported comparison 还要求 accepted annotation 与其所绑定的 claim assessment/evidence 和 active profile/head 均为 current。冻结至少 20 个问题的 gold set，覆盖 model/method/training/dataset/inference/code 六类，并给每项标 `target_kind`，记录文件 SHA-256；paper Recall@5 ≥ 0.85、evidence-unit Recall@10 ≥ 0.75、事实句可解析引用覆盖率 100%、悬空引用 0。MRR、nDCG、entity exact-match recall、implementation-locator recall 和 apples-to-apples rate 先作为不可删的诊断指标；积累足够 gold 后才以新版本阈值升为 gate。对 gold set 全部回答先拆成 atomic factual units，再按 `support-review.v1` 做 locator 双向核验与语义复核：通过要求 **100% factual units=`supported`**，`partially_supported|unsupported|contradicted|not_assessable` 任一数量大于 0 都失败，必须重写、降格为明确 inference/unknown，或修复证据后重跑；不能只靠“存在一个引用”判断正确。相同 generation/config 的 context pack byte-identical；删除 graph/index/comparison projection 后可从 canonical claim、annotation、review 与 active profile/head bytes 重建。阈值变更必须新版本 gold/config，不能就地降低。

### P5：跨论文综合与技术文章

目标：把查询结果转成可编辑研究产物。

交付：

- comparison matrix：问题、假设、架构、训练数据、目标函数、结果、局限；
- consensus/difference/contradiction/unknown 分类；
- research note 和 article outline/draft；
- reproduction plan：目标 repo/commit、入口/config locator、checkpoint/license observation、软件环境、硬件假设、数据需求、验证步骤、未知项和 blocker；只规划，不执行训练；
- 段落级 claim refs、bibliography 和 freshness manifest；
- draft 始终留在 `.work/research/**`；W6 扩展受管 namespace 后，写入 `wiki/synthesis/generated/<artifact-id>.md` 前展示 diff，由用户决定是否发布。发布结果是 create-only 不可变快照；用户在 Obsidian 中手工复制到 `wiki/notes/**` 后继续编辑，agent 永不写该用户副本。agent 改稿只能产生带新 ID、引用旧 ID 的 successor artifact。

验收：针对一个技术轴生成完整中文文章草稿；所有 factual 段至少绑定一个可解析 claim/evidence locator，悬空引用为 0。按段落 ID 排序取前 10 个 factual 段（不足则全取），拆出其中全部 atomic factual units 并做固定人工 `support-review.v1`，不能用临时随机抽查替代；样本通过要求 **10/10 段中的每个 factual unit 都为 `supported`**，任一 `partially_supported|unsupported|contradicted|not_assessable` 都使该候选失败，修订并生成新 artifact 后重新评审。复现计划必须固定官方 repo 与完整 commit，对入口/config/checkpoint/license/software/hardware/data 的每一项给出 locator 和 `verified|inferred|unknown|blocked`；缺失项必须留作 unknown/blocker，且输出明确标注“未执行、未验证复现结果”。生成内容不反向污染 accepted claim。发布验收还需 `HUMAN-CLAIM-ASSESSMENT-001` 与 `HUMAN-OBSIDIAN-VISUAL-001` 的真实证据。

### P6：重构和产品化

在 P0–P5 的真实用例稳定后再做：

- 拆分 `connectors/`、`domain/`、`orchestration/`、`projections/`；
- 将当前大型模块拆成窄接口；
- schema migration 和版本兼容；
- 只读发现/proposal worker 可并行；canonical publication、ledger、catalog/index build 继续串行单写者；缓存、增量图和增量索引必须可由真源重建；
- Obsidian Bases/dashboard、队列和失败恢复 UI；
- 只读/request/status/context MCP adapter，与 CLI 共用 schema/envelope；禁止 accept/apply/Vault mutation；
- FTS5 trigram、dense embedding、tree-sitter、增量 RRF 等只作为 capability/performance spike；任何新增依赖先做锁定、许可证、降级路径和 Linux/macOS × Python 3.12/3.13 验证，达不到冻结收益阈值则不引入；
- 可选的可信 host operator broker：位于 agent venv/workspace 之外，只消费 exact inspected bundle + 单独的用户 approval attestation，保留 OS trust、receipt 和 fail-closed 校验；它不回填或伪造 `approval-ref.v1` issuer。未验收前继续使用现有独立 TTY operator；
- 性能、成本和 corpus 回归基准。

重构不得改变已有 artifact 的 canonical bytes 或无迁移地修改 schema。

## 10. 工作包与依赖

```text
W0 代码审计与架构冻结
  └─ W1 arXiv preview MVP
       └─ W2 single-paper workflow
            ├─ W3 discovery expansion
            └─ W4 official code mapping
                 └─ W5 graph + context pack + Q&A
                      └─ W6 synthesis + article
                           └─ W7 refactor/productize
```

每个工作包必须声明：baseline commit、允许路径、输入/输出 schema、失败码、网络与写入边界、测试、候选 snapshot、reviewed head 和 CI SHA。工作包通过表示可以进入下一个工程阶段，不代替用户对论文入库和文章发布的决定。

### 10.1 各包入口与退出条件

| 包 | 可开始条件 | 工程退出条件 | Gate 影响 |
|---|---|---|---|
| W0 | 当前 repo 与六仓源码可读 | 审计 manifest 通过 closed schema；`video-generation-research-wiki-v1-w0-r2-freeze.json` 绑定原 W0、附件、复核报告、manifest/schema 和本方案 SHA-256；Builder 与 Repo Steward 对同一 exact bytes 给 GO；Architect 只冻结 W1 范围 | 不关闭任何外部 gate |
| W1 | R2 W0 GO；单独 W1 packet/contract hash 已冻结 | capability observation、Skill contract、focused tests、2152+ 全回归、wheel、四矩阵 CI、exact-head acceptance；真实 arXiv preview smoke 单独记录 | 无；不得写 Vault |
| W2 | W1 exact-head accepted | single-paper two-stage local pipeline、figure/table/equation locator 与 operator receipt 纵切通过；失败可恢复 | 真实发布受 provenance/license、claim 与 visual gate 约束；taxonomy 只产生 proposal |
| W3 | W2 engine 可用 | 固定 observation/config 上 discovery/去重/排序/stop decision byte-identical，support/counterevidence gap 可见，live smoke 独立 | 候选发现无 gate；候选入库继承 W2 gate |
| W4 | W2 + W3 | candidate officiality mapping、commit/line evidence、checkpoint candidate 与 code capture 通过 | 五仓完成声明需 baseline + provenance/license gate |
| W5 | W2 + W4 | canonical domain/comparison profile-head、claim-domain annotation/review/atomic head 的兼容迁移，profile 替换/过期/混用 fail closed，transaction/receipt/audit/backup、typed graph/RRF/comparison rebuild、comparison lint、frozen gold/context pack 与 Q&A 阈值通过 | 真实 accepted annotation 需独立 human domain review；其绑定 claim/最终 corpus 另需 claim assessment；最终 UI 需 visual gate |
| W6 | W5 | synthesis/reproduction/support-review schema、引用覆盖、`wiki/synthesis/generated/**` create-only namespace、receipt/audit/backup 通过 | 发布文章需 claim/visual；生产 readiness 需 backup anchor；不执行训练 |
| W7 | 七条真实纵切完成 | migration/兼容/性能回归；可选依赖 spike 与只读 MCP closure；PR exact-head acceptance | merge 仍需 readiness/merge gate 和精确指令 |

每个包的 `contract_sha256` 在 Builder 开始前计算并写入 packet；`candidate_head/base/merge_preview/run/attempt/jobs` 只能在真实交付发生后填写。Fixture、local、installed-wheel、live smoke、operator 和 remote CI 证据分别存档，禁止相互冒充。

### 10.2 W1 待冻结的窄契约

W1 只做“arXiv metadata → abstract-only 中文 preview → decision event”，不下载 PDF、不改 Vault、不做 related-paper discovery。Builder packet 固定以下行为：

- 实现前先完成 `CAP-WEB-OBS-001`：在实际 Codex Web connector 上对“规范化 payload、source/final URL、raw bytes、headers/content type、redirect chain、DNS/IP”逐字段记录 `available|unavailable` 和样本 hash。结果冻结为 W1 packet 输入；代码和文档不得预设 connector 拥有未验证能力。
- 输入接受 canonical arXiv ID、带可选 `vN` 的新式 ID、合法旧式 category ID，以及 `arxiv.org/abs/...` URL；URL fragment、额外 query、非 arXiv host、userinfo 和模糊标题均拒绝。
- Request 使用官方 legacy API 的 `id_list=<id>&max_results=1` 语义；Web connector 单连接执行，所有 arXiv legacy API 请求全局至少间隔 3 秒。该限制来自 [arXiv API Terms](https://info.arxiv.org/help/api/tou.html)，并作为配置下限而非可调默认值。
- 若 capability spike 证明 `byte-exact`，单次 preview 最多 1 request、2 次同源 redirect、20 秒、1 MiB encoded/decoded response，只接受 Atom/XML 媒体类型；XML 禁 DTD、external entity 和 XInclude，并限制 element 数、深度与每字段字符数。若平台只能返回 `normalized-content`，Skill 对返回内容施加 1 MiB canonical JSON、字段长度和条目数上限，transport-only 字段一律 `null + unavailable_reason`；该路径只允许 preview/discovery。
- Metadata 缓存按 request SHA-256 + resolved version，默认 24 小时；显式 refresh 仍服从 3 秒全局 rate limit。arXiv 文档说明 Atom entry 包含 title/id/published/updated/summary/author/category，解析器不得从 HTML 猜字段，见 [官方 API manual](https://info.arxiv.org/help/api/user-manual.html)。
- Preview 固定六节：一句话、研究问题、方法、贡献/结果、局限、与视频生成知识库的相关性。所有节都绑定同一 metadata hash，并显示 `abstract-only`；没有摘要中证据的内容标 `inferred|unknown`。
- Session 路径固定为 `.work/research/<session-id>/{requests,observations,metadata,proposals,decisions}/`；所有文件 canonical JSON + LF，重复同字节幂等，不同字节同 ID 冲突。
- 稳定失败码至少包括：`ARXIV_ID_INVALID`、`CONNECTOR_REQUEST_INVALID`、`CONNECTOR_CAPABILITY_UNAVAILABLE`、`OBSERVATION_MISSING`、`OBSERVATION_BINDING_MISMATCH`、`OBSERVATION_PROFILE_INSUFFICIENT`、`RESPONSE_TOO_LARGE`、`MEDIA_TYPE_REFUSED`、`ARXIV_XML_INVALID`、`ARXIV_ENTRY_NOT_FOUND`、`ARXIV_ID_MISMATCH`、`PREVIEW_PROPOSAL_INVALID`、`PREVIEW_SCOPE_INVALID`、`DECISION_CONFLICT`。
- `skip|later` 只追加 decision event；`ingest` 生成 W2 输入。三种决定都不触发网络或 Vault 写入。

W1 packet 必须列出上述常量、schema ID、CLI envelope、允许文件和 test names，并在 Builder 开始前由 Architect 计算 contract hash。方案中的命名是架构约束，不是提前伪造的实现完成记录。

### 10.3 W0 与 R2 successor 冻结记录

原 W0 的 `docs/ai/video-generation-research-wiki-v1-w0-freeze.json` 继续只绑定原方案 exact bytes，禁止覆盖或把其 GO 重标给 R2。R2 使用新的 `docs/ai/video-generation-research-wiki-v1-w0-r2-freeze.json`，绑定原方案及原 freeze、附件 SHA-256、附件复核报告、R2 本方案、外部审计 manifest/schema、两名独立 reviewer verdict 与 Architect decision。该记录不自我哈希，避免递归；它不关闭任何 human/external gate，也不把已有 engine CI 写成 W1 实现 CI。只有 R2 记录中的输入 hash 与 reviewer 实际复核输入一致，R2 才能成为 W1 工作包的架构输入；W1 仍须另建带 contract hash 的工作包。

## 11. 测试与验收

### 11.1 自动测试

- schema valid/invalid、canonical ID、去重和跨对象 identity；
- connector 的正常响应、超时、429、畸形数据、错误 ID、缓存和 freshness；
- 所有网络测试使用 fixture transport，CI 禁止真实网络；
- preview/skip 阶段 Vault、catalog、index 零变化；
- ingest 幂等、崩溃恢复、重复请求和并发；
- claim/locator 完整性、assessment 状态机和矛盾边；
- classification proposal 与 canonical domain annotation/review/atomic-head 隔离、旧 claim 兼容、accepted-current-profile 绑定、profile 替换/过期/混用拒绝和 comparison projection 重建；
- graph/context pack 的确定性和删除后重建；
- Q&A/article 的引用覆盖率和悬空引用拒绝；
- installed wheel、Linux/macOS、Python 3.12/3.13；
- 固定上游契约和完整回归套件。

### 11.2 产品验收

1. **一分钟预览**：一个 arXiv URL → 中文摘要 → 入库选择。
2. **单篇纵切**：选择入库 → Obsidian Paper Page → audit 通过。
3. **扩展纵切**：3 个 seed → 去重候选 → 用户可连续预览。
4. **代码纵切**：一篇论文 → 官方 repo → commit/line 证据。
5. **问答纵切**：一个跨论文技术问题 → 引用完备答案。
6. **文章纵切**：一个技术轴 → 可编辑中文文章草稿。
7. **复现纵切**：一篇论文及官方代码 → commit/config/checkpoint/hardware/unknown 均可追溯的复现计划，不执行训练。

只有七条纵切都通过，才能称为附件复核后的 v1；底层测试全绿只能称为 engine candidate。

### 11.3 现有人工与外部 gate

下表继承 `docs/ai/task-index.yaml` 的真实状态。实现代码、fixture 或 Architect 判断都不能自行关闭这些 gate。

| Gate | 当前状态 | 阻塞的 v1 结果 | 必须保存的真实证据 |
|---|---|---|---|
| `HUMAN-GATE-BASELINE-001` | `not-recorded` | W4 五个代表 repo 的最终名单、W5/W6 完整 corpus 验收 | gate-decision event、当前 registry head、匹配 baseline manifest 与五仓列表、publication receipt |
| `EXTERNAL-PROVENANCE-LICENSE-001` | `not-recorded` | 真实 PDF/源码保留、任何新增外部源码复制、W2/W4/W6 真实发布验收 | 真实来源 provenance、许可证文件/hash、允许保留的外部判断 |
| `HUMAN-CLAIM-ASSESSMENT-001` | `not-recorded` | W5 accepted/contested claim 与 W6 发布文章的事实依据 | 人工 review decision、current assessment head、绑定 reviewed bytes 的 receipt |
| `HUMAN-OBSIDIAN-VISUAL-001` | `not-recorded` | W5/W6 Obsidian 最终可读性验收 | 真实隔离 Vault 中的人工视觉验收记录 |
| `EXTERNAL-BACKUP-ANCHOR-001` | `not-recorded` | v1 生产 readiness | raw-inclusive archive manifest 的外部 anchor 与绑定该 manifest 的隔离 restore observation |
| `HUMAN-READINESS-MERGE-001` | `not-recorded` | PR #94 merge | exact-head CI/Architect acceptance 后的用户 readiness；点名当前 head/base/target 的 merge 指令 |

Gate 只阻塞其后的真实发布或“已完成”声明，不阻塞 W1 的只读预览、W3/W4 的候选发现、`.work/**` 草稿和自动测试。PR 保持 draft → `integration`；任何阶段都不得合并到 `main`。

## 12. 近期执行顺序

1. 固化附件复核报告、R2 本方案 hash 和独立评审结论，完成 W0 successor 冻结；原 W0 保持不可变历史。
2. 冻结窄 W1 packet 后立刻实现 P0，不继续扩写底层审计框架。
3. 用真实 arXiv 论文做 P0 人工 smoke；根据实际体验修正摘要卡片。
4. 把现有 ingest/capture/publication 串成 P1 orchestrator，而不是再造一条摄取路径。
5. 完成 P1 后再并行开发 discovery 和 code discovery。
6. 用真实 corpus 驱动 graph/Q&A，再开发 article；避免对合成 fixture 过拟合。
7. P0–P5 都有真实纵切后统一重构。

### 12.1 预期代码落点

| 工作包 | 新增或主要修改路径 | 复用路径 |
|---|---|---|
| W1 arXiv preview | `src/video_paper_wiki_research/request.py`、`observations/arxiv.py`、`preview.py`、`cli.py`；connector/metadata/preview/decision/`skill-contract.v1` schemas；`.agents/skills/video-paper-preview/` | `identity.py`、`contracts.py`、`jcs.py`；Codex Web connector 只存在于 Skill 运行层 |
| W2 single-paper workflow | `orchestration/session.py`、`orchestration/single_paper.py`、`workflow` CLI/Skill；claim-classification/taxonomy-extension proposals；figure/table/equation locator mapping | `plan.py`、`prepare.py`、`staged_capture.py`、`extraction_artifact.py`、`canonical_compiler.py`、`publication.py` |
| W3 discovery | `observations/openalex.py`、`discovery/rank.py`、`research_session.py`、`research_stop.py`；candidate/session/round-event/stop-decision schemas | connector request/observation、`identity.py`、catalog paper records |
| W4 code mapping | `observations/github.py`、`observations/huggingface.py`、`discovery/code.py`；code/checkpoint candidate schemas | connector request/observation、`staged_code_capture.py`、`code_evidence_contracts.py`、`compile_code_page` |
| W5 graph/Q&A | `domain/profiles.py`、`domain/claim_annotation.py`、`graph/build.py`、`graph/contradictions.py`、`retrieval/context_pack.py`、`retrieval/fusion.py`、`comparison.py`、`answer.py`；domain/comparison profile-head、claim-domain-annotation/review/atomic-head、relation-profile、comparison proposal/projection、context-pack schemas；publication/audit/backup 对新增 canonical namespace 的兼容迁移 | 现有 claim ledger/assessment/evidence、`catalog_store.py`、`retrieval.py`、固定上游 BM25 |
| W6 synthesis | `synthesis/compare.py`、`synthesis/article.py`、`synthesis/reproduction.py`；synthesis/reproduction/support-review schemas 与 Skills；transaction/publication/receipt/audit/backup 对 `wiki/synthesis/generated/**` 的 create-only 扩展 | context pack、claims、assessment heads、canonical compiler；不触碰 `wiki/notes/**` |
| W7 refactor | 包边界和兼容 adapter；只读 MCP 仅按 closed method allowlist 镜像 P0–P5 已验收 CLI，不新增领域能力；可选依赖 capability/performance spikes | 所有已通过真实纵切的模块 |

`video_paper_wiki_research` 是新的薄、零 egress 编排包，不复制 `video_paper_wiki` 引擎实现。它生成 connector request 并校验平台 Web connector 返回的 observation；orchestrator 只组合已有 API 并写 `.work/research/**`。等真实路径稳定后，再判断是否把两个包合并。

### 12.2 每个工作包的最小测试面

| 工作包 | 必须通过的 focused tests | 不允许用来冒充验收的结果 |
|---|---|---|
| W1 | arXiv ID/URL/version、Atom 解析、超限/超时、缓存、摘要绑定、决定状态、Skill/contract 同版本和 policy lint | 合成英文摘要生成中文模板 |
| W2 | 真实本地 PDF、两阶段编译、figure/table/equation locator、classification proposal 的 claim-kind 正交性与 exact claim/evidence/head binding、未知 taxonomy 不静默晋升、断点恢复、重复 ingest、publish diff、audit | 只验证 schema、只渲染 Markdown，或把 proposal 当 canonical claim 分类 |
| W3 | 多 connector 去重、引用方向、排序解释、每轮 support/counterevidence coverage、低收益/重复率/预算停止重放、checkpoint/resume | 手写候选列表或把 bounded candidate 自动入库 |
| W4 | candidate signals → 现有三态 officiality 映射、commit pin、许可证观察、line locator、checkpoint revision/officiality 保守映射 | 只保存 repo URL、README 自称 official 或下载权重 |
| W5 | domain/comparison profile 与 current-head schema、claim-domain annotation/review/atomic-head、旧 claim 兼容、successor/rollback、transaction/receipt/audit/backup、accepted-current-profile binding、comparison byte-identical rebuild；normalization substitution、deprecated-profile accepted annotation、mixed-profile comparison、profile-head replacement/reopen 对抗；predicate kind、矛盾组、社区、RRF、target-kind recall、video-comparison lint、context budget、引用覆盖 | 只有关键词搜索命中、直接相加异构 raw score，或用 `.work/**`/旧 profile proposal 产生 current supported edge/fact |
| W6 | 比较矩阵、段落 claim refs、freshness、复现计划 locator/unknown/no-execution、publication diff | 无来源的通用文章或把计划宣称成复现成功 |
| W7 | migration、兼容、性能和完整回归；MCP 无写方法/任意 URL fetch；可选依赖锁定、许可证、降级和四矩阵 | 改目录后 unit tests 仍绿或本机 spike 通过 |

## 13. 完成定义

工程完成必须同时满足：

- 用户可以在 Codex 中从 seed 或问题开始，而不是从 JSON 文件开始；
- 候选论文先预览、再由用户决定入库；
- 已入库论文具备 PDF/claim/locator provenance；
- classification proposal 不具有 canonical 效力；产品 v1 通过 versioned `claim-domain-annotation.v1` + append-only review/head + 现有 transaction 持久化 `claim_kind`，它与 claim assessment/freshness 正交，且旧 claim 无 annotation 时仍兼容；未知 taxonomy term 只进入 review queue，不能静默成为 canonical term；
- 官方代码具备 repo/commit/path/line 证据；
- 知识图谱和索引可从 canonical truth 重建；
- research session 的 support/counterevidence coverage、低收益/重复率/预算停止决定可由冻结输入 byte-identical 重放；
- 视频实验比较只由 accepted-current-profile domain annotation 与精确 annotation review/atomic head、claim/assessment/evidence、active domain/comparison profile 及 profile-head bytes 重建，并通过 checkpoint、参数口径、分辨率、帧数/FPS/时长、训练条件、benchmark version/split、单位和 metric direction 的 apples-to-apples lint；`.work/**` 或旧/mixed-profile proposal 不能满足该完成项；
- Q&A 和文章的事实均有可解析引用；
- reproduction plan 的 commit/config/checkpoint/license/hardware/unknown 均可追溯，并明确未执行训练、未验证复现结果；
- 失败可以恢复，不产生重复 ID、重复页面或半发布状态；
- Obsidian 中的 Paper、Code、Concept、Method 和综合页面可读；
- 可选 MCP 只暴露只读/request/validate/preview 操作，不包含 accept/apply、任意 URL fetch、provider credential 或 Vault mutation；
- repository seed manifest 与 overlays 仍为冻结的 67，或存在单独 re-scope gate；
- 六项现有 human/external gate 各自有真实状态和所需证据，任何 `not-recorded` 都不能被 fixture 或 agent 结论覆盖；
- 真实使用路径、自动测试、四矩阵 CI、持久化 CI observation/merge parents 和精确 head Architect 验收全部通过；
- 第 11.2 节的七条真实纵切全部通过，才可称为附件复核后的产品 v1；
- PR #94 仍只按 draft → `integration` 流程交付，最终 merge 另需 `HUMAN-READINESS-MERGE-001` 和精确 merge 指令。
