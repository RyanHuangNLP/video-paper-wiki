# Video Generation Research Wiki v1：开发方案与联合评审 PRD

版本：R3.2 · 日期：2026-09-06 · 状态：开发方案成稿，供 Fable 5.1 外部评审。

本地工程基线：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`。本文是 R2 的自包含产品化 successor，整合 Pro 方案和两轮评审；旧方案与冻结记录保留。本文确定产品范围与架构方向，具体实现包仍需冻结接口、允许文件和测试。§15 是双方共用的 Markdown 讨论区，当前尚未收到 Fable 5.1 的意见。

## 1. 产品目标

面向个人视频生成研究，建设一个以论文和开源实现为证据、以 Codex 自然语言为入口、以 Obsidian 为阅读和整理界面的本地知识系统。用户应能完成：

```text
种子论文 / 技术问题
  → 发现相关论文 → 中文预览 → 入库选择
  → 论文解析与结构化主张 → 官方代码与配置映射
  → 跨论文问答 / 公平比较 / 矛盾与缺口识别
  → 中文技术文章 / 复现计划 → 保存研究进度并继续研究
```

产品价值落在“找得全面、结论有出处、论文与代码能对照、比较条件明确、研究可以持续”。摘要预览是第一步；完整 v1 包含研究、代码、比较和写作能力。

**首个研究里程碑：** 围绕一个由用户选择的技术轴，完成 3 篇真实论文与 1 个确认对应的官方仓库，由 W5b1 输出有引用、比较矩阵和 bibliography 的比较报告，展示共识、差异、疑似矛盾和未知项，并证明中断后能继续。这里的报告是有界比较问答产物；完整技术文章与发布快照由 W6 交付。该小样本不替代最终五仓基线或完整 v1 验收。

## 2. 用户场景与需求编号

| ID | 用户意图 | 可观察结果 |
| --- | --- | --- |
| REQ-01 | “看看这篇 arXiv” | 获取题录和版本，生成中文摘要，明确 abstract-only，等待入库/跳过/稍后选择。 |
| REQ-02 | “把它入库，下次继续” | 版本一致的 PDF、可追溯主张、Paper Page；自动组织中间文件，说明下一动作，恢复不重复生成来源。 |
| REQ-03 | “沿着时空建模继续找论文” | 引用/被引/相关主题/作者项目候选、去重、排序理由、反证与覆盖缺口、停止原因。 |
| REQ-04 | “找官方代码，解释实现” | 明确 paper→repo 对应关系，固定 commit，给出代码/配置行出处，区分训练与仅推理能力。 |
| REQ-05 | “比较几篇论文的方法” | 回答包含主张、支持与反对证据、原文定位和必答要点；无证据部分明确未知或推断。 |
| REQ-06 | “这些实验结果能直接比较吗” | 展示 checkpoint、参数口径、分辨率、帧数、推理配置和评测设置，输出可比/不可比及原因。 |
| REQ-07 | “写成中文技术文章” | 引用完备的比较矩阵、提纲和文章草稿；用户选择发布后生成可追溯快照。 |
| REQ-08 | “如何复现这个方法” | 固定仓库/commit/入口/config，列软件、数据、权重、硬件、验证步骤及未知或阻塞项；不声称已执行实验。 |
| REQ-09 | “检查、恢复我的知识库” | 来源/引用/版本/受管文件与索引检查，备份和隔离恢复证据，用户笔记保持独立所有权。 |
| REQ-10 | “让 Fable 5.1 review 方案” | 可直接阅读的 PRD、稳定编号、评论/回复/决策格式；无需模型 API 或自动调度服务。 |

正常使用不要求用户手工制作 JSON 或拼接底层命令。需要外部文件或 operator 操作时，界面提供已生成的请求、待办说明和可检查差异，展示准确的完成状态。

## 3. 当前状态与范围

已有工程代码覆盖 identity/schema、安全 staging、PDF/代码 capture inspect、Paper/Code/Concept 编译、claim/assessment、publication/receipt、catalog/BM25、audit 和 backup/restore 等底层能力。默认 agent CLI 不执行 Vault 写入或索引构建。已有记录显示 Tests run `33642835702` 在历史 merge preview `ee6159ea7d3b36720b862617b3a9a2c99ef3ba73` 四项各通过 2152 tests；本次未重新查询远程状态，也未签发该引擎候选的精确 head 验收。

**尚未实现：** `video_paper_wiki_research` 产品包、arXiv 预览 Skill、单篇自动编排、发现、完整 context pack/Q&A、领域图谱/比较与文章/复现产品层。现有 Docling adapter 只做简要预览，artifact packaging 只验证外部已产生的文件；完整解析执行器和导出交接属于新增工作。

67 篇 repository seed/overlays 保持不变；这表示种子目录数量，不表示 67 篇已全文摄取。新的真实来源进入用户隔离 Vault，不自动扩写 repository seed。

v1 包含 REQ-01–09 的完整用户路径。暂不包含训练执行、模型权重/数据集下载、视频/YouTube 摄取、OCR-first 扫描资料、自动无限研究、多用户服务、第二桌面客户端。Dense embedding、AST 引擎、社区算法、只读 MCP 和性能优化按收益渐进引入；它们不阻塞基础引用问答。Fable 的本次设计 review 不改变开发期的 Codex 三角色或产品运行时 provider 范围。

## 4. Pro 方案的采用决定

| 设计 | 本方案采用方式 | 主要价值 |
| --- | --- | --- |
| Paper/Repo 联合知识 | 论文和代码保持各自身份，通过明确的 implements/claim/evidence 关系连接 | 可追踪描述、实际实现和配置差异。 |
| 视频领域 schema | 以 typed concept、claim_kind 和实验字段扩展已有真源 | 按方法、训练、推理和评测比较，而非只按标题归档。 |
| Claim-centric retrieval | 多对象检索、exact lookup/BM25/graph 排名融合、原文与反证 context pack | 将答案落实到主张、图表、配置和代码行。 |
| 两阶段编译 | 来源分析先出独立 proposal；实体归并/页面生成再消费已验证输入 | 一次来源提取可支持多个研究产物，减少重复解析。 |
| 可恢复研究 session | 多研究路径、去重、来源独立性、反证、覆盖与收益递减停止 | 持续研究能暂停、恢复并说明进度。 |
| 实验可比性 lint | 结构化记录条件，缺失或冲突默认不可比 | 避免把不同 checkpoint/设置的数字直接排优劣。 |
| Skills + Obsidian | 自然语言动作与稳定 CLI/API 对应，Markdown/Bases 作为阅读视图 | 领域能力随每个里程碑提供可用入口。 |

六仓复用关系：现有 pinned `claude-obsidian@9f8c1199047eac2c3828496279fbb7ba9540b90b` 继续提供事务、ledger、lint、BM25；借鉴 Ar9av 的 graph/context pack、nvk 的研究协议、atomicstrata 的两阶段与验证思路、SamurAIGPT 的简明信息架构、SwarmVault 的多对象检索和图遍历接口。具体来源见已有源码审计，复制代码前另做 pin/license/适配验证。附件的 `ad67087...` 不自动替换已固定上游。

## 5. 架构与所有权

```text
Codex Skill / 自然语言交互
  ├─ 平台只读 connector / 外部 operator → 受限来源 observation
  └─ research 编排层 → proposal / session / context / draft
                         ↓ 验证与 inspected bundle
                  既有 video_paper_wiki 引擎
                         ↓ 独立 operator
                Vault canonical bytes + receipt
                         ↓ 可重建
             Obsidian / catalog / BM25 / graph
```

| 层 | 所有者与输入输出 | 边界 |
| --- | --- | --- |
| Connector executor | 平台只读 Web 工具或外部 operator；request→observation | 网络请求由该层执行，记录能实际观察的字段；不接收 Vault 写入能力。 |
| Research 编排 | `video_paper_wiki_research`；会话、选择、请求、校验、上下文与草稿 | 本地零 egress、无 admin；自有状态只写 `.work/research/**`，可调用既有 engine 在其批准 `.work/<batch>/**` 布局生成 staging。 |
| External input / parser | agent 环境外的 operator 与离线 parser executor | 外部 blob 安装、解析运行和 manifest 生产；不在默认环境安装 Docling extras/models。 |
| Evidence / canonical | 现有 raw、paper/repo records、claim ledger、assessment、版本化 domain annotation/profile | 来源与知识真源；通过同一 transaction/receipt 管理，不创建平行 ledger。 |
| Projection | engine 管理 Markdown、SQLite catalog、BM25、图和 comparison；research 组装临时 context pack | 可由明确的 canonical 输入和配置重建，不作为新事实真源。 |
| 用户内容 | Obsidian 中的用户笔记 | 编译器与 agent 不覆盖用户笔记。 |

LLM 接收有界输入并返回 schema 化 proposal；代码校验结构、identity、hash、预算与 locator。语义支持性由独立 review 记录，不能由 JSON 校验代替。两阶段 proposal 都无 apply 权限。

产物与实现归属固定如下；“可重建投影”是数据性质，不能代替写入所有权：

| 产物 | 实现与存储所有者 | 生成/发布权限 |
| --- | --- | --- |
| session、decision、candidate、context pack、answer/comparison proposal、草稿 | research 包；`.work/research/**` | research 校验、排名和写本地状态；context 绑定 engine 返回的 generation/locator。 |
| domain/comparison profile、annotation、review event、各 current head、受管 selection binding | engine 的兼容 schema/namespace；现有 canonical Vault 布局 | research 只提出 proposal；engine 准备/inspect，独立 operator 经同一 transaction 发布；同包扩展 receipt/audit/backup。 |
| canonical typed graph 与 comparison fact projection | engine 的确定性 projector/generation/query；具体索引路径在 W5b1/W5b2 冻结 | agent 可只读查询或生成批准的 staging；operator 串行构建/选择持久 generation。research 不维护第二份 canonical 图或 catalog。 |
| exact/BM25/graph 排名融合与 context 选择 | research 包 | 消费只读 engine 查询结果，在 `.work/research/**` 保存 ranks、预算、included/omitted。 |
| Paper/Code/Concept Markdown、catalog/BM25、生成文章快照 | engine compiler、projection 与 publication；现有目录及 W6 新 namespace | 重建/发布继续由 operator 执行；research 无 Vault 写入或索引构建权限。 |

W5b1/W5b2 工作包分别列 engine 与 research 路径，由 Builder 按单写者顺序实现；Architect 在共享 schema/registry 的前一组冻结后再交接下一组。Repo Steward 不编写这些实现。W7 验证跨所有新 namespace 的检查与恢复，不延后各生产者包自身的 receipt/audit/backup 完整性要求。

所有新数据使用 closed schema、明确版本和稳定错误码。完整 schema/CLI 合同在对应工作包冻结，不把本文中的候选命名当作现成命令。

## 6. 输入、版本、解析与恢复合同

### 6.1 预览和网络观察

W1 首先运行 `CAP-WEB-OBS-001`，记录实际 connector 的规范化内容、URL、headers、redirect、raw bytes、DNS/IP 可见性。Observation 支持 `normalized-content` 和 `byte-exact`；缺失传输字段使用 null 与原因，不能编造。前者可用于预览/发现，后续 raw provenance 需要原始 bytes 或等价外部输入证据。

arXiv metadata 保存无版本实体 ID 和 resolved version、标题、作者、日期、分类、摘要、来源与观察时间。预览绑定 metadata hash、生成模型/runtime、prompt hash；明确 abstract-only 和 extracted/inferred/unknown。接受合法新旧 ID/版本及 abs URL，拒绝混淆 host/userinfo/额外 query。默认 24 小时缓存；legacy API 请求按官方规则串行限速，W1 初始下限 3 秒。初始请求预算为单次预览 1 request、20 秒、1 MiB；connector 不能证明的传输限制不能记成已验证。Atom parser 禁 DTD/外部实体并限制深度、元素与字段长度。若只能使用规范化官方页面，单独冻结页面 adapter，不能标为 Atom 响应。

入库/跳过/稍后是 append-only decision，绑定预览 exact hash 和用户选择记录，不篡改原 preview。网络失败、无版本、错误 ID、观察不足、格式/大小不合规分别显示明确原因。

### 6.2 选择与实际文件绑定：关闭 F2

新增编排侧不可变 selection/source binding，链条为：

```text
decision + preview + metadata/observation hash
  → resolved arXiv version + 版本化 PDF URL
  → external-input request
  → 获取 observation + 实际 PDF hash
  → engine plan/ref/batch + capture receipt + publication receipt
```

选择时尚无 PDF hash，先固定前半段请求；获取后形成后半段 acquisition binding，引用前一对象，不回写旧对象。实体 paper ID 仍去版本。编排层在 prepare、resume 和确认发布前强制检查整条链；相同实体的 v1 选择与 v2 来源不匹配必须拒绝并重新预览/选择。即使 ref/blob digest 匹配，也不能省略选择版本检查。

现有 approval-ref 仍是外部提供的九字段摘要绑定，不表示可验证的签发者或人工批准，orchestrator 不签发它。绑定记录在研究会话中保留并关联操作 receipt；需要进入受管审计/备份的 binding namespace 和 publication context 由 W2 同一合同冻结，不向旧 closed schema 偷加字段。

### 6.3 外部 blob 与解析执行器：关闭 F1

外部 input operator 按请求把 PDF 安装到 prepare 可读的 `.work/blobs/<sha256>`；研究层只校验和消费，不恢复 agent 的 ingest put。交接规定 hash、PDF 类型/页数/大小、原子安装、同字节复用、异字节冲突拒绝和路径安全；任何缺失输入都显示 awaiting_external_input。

外部离线 parser executor 使用固定 Docling/core 版本与已准备的模型，绑定 captured PDF hash，生成 `document.json`、`parser-config.json`、`model-manifest.json`、`run-manifest.json` 四件套。run 记录真实版本、配置/模型摘要、输入输出摘要和成功/失败结果；失败不能伪造成功产物。agent 默认锁定环境只调用既有 artifact validator/package/publication。Parser executor 的交付/测试脚本作为 W2 独立边界实现，不由本次方案交付安装运行。

W2 映射 section/figure/table/equation 到 existing PDF locator：page、block ref、bbox 或 charspan、artifact/text hash。代码证据使用 repo、full commit、path、line、blob hash；可选 AST 只补充 symbol 信息。只有简要标题预览时不进入 parsed 完成状态。

### 6.4 两阶段编译与可恢复状态

来源提取先输出 claim/entity/method/result/limitation proposal；随后做 alias/version/entity resolution 和 canonical compile。每次重放绑定 exact source、schema、compiler、pipeline、locator/assessment 输入。semantic hash 仅提示缓存/dirty，不作为 identity 或幂等依据。

保留现有 canonical 流程：`absent → planned → prepared → capture_inspected → captured → parsed → drafted → ingest_inspected → applied_provisional → verified`。create capture 等 operator result；reuse 重新验证 retained sibling；parsed 等真实解析证据；verified 只指 ingest 完整性，不代表 claim 人工 accepted。失败追加事件，状态停在最后可证明步骤；publication preparation/inspection、ref 绑定和 capture disposition 使用正交字段。

Session 的 next_action 每次根据 artifact/receipt 重算。模型输出、用户 decision 和选中输入具有不可重建内容，活动 session 不可随意清理；结束后可导出保留包，清理前记录依赖。缺少必需 bytes 时返回明确恢复缺口，不能仅凭 hash 自动补造。投影/cache 可以删除重建。

## 7. 领域知识、官方代码与研究

### 7.1 视频领域和实验事实

Method/Model/ArchitectureComponent/TrainingRecipe/Dataset/Benchmark/InferenceRecipe/EvaluationMetric 先作为 typed concept。taxonomy v1 不原地扩写；任务、范式、backbone、component、training、inference、evaluation 的新词先规范化为提案，v2 需独立迁移与真实 review。

claim_kind 为 architecture/training/empirical_result/implementation/ablation/limitation/reproducibility/license/resource_requirement，与 assessment 和 freshness 正交。分类 proposal 绑定 claim text、evidence fingerprint、assessment head、domain profile hash；W2 只建议，W5b1 才通过 versioned annotation/review/head 和现有 transaction 发布。

Domain/comparison profile 是 immutable canonical bytes，由 transaction-published profile-head 选择 active version；agent/query caller 不能切换规则。Annotation、review event 与 current head 同事务更新。Supported 领域事实要求 annotation review 和 claim assessment 均 accepted，所有 source/claim/profile/head 仍 current。旧 claim 无 annotation 仍可查，不能冒充 supported typed comparison。变更保留历史，可回滚 projector，不能改写旧 claim ID/ledger。

Comparison projection 的 generation 包含 annotation/review/head、claim/assessment/evidence、domain/comparison profile 和 profile-head 的完整路径/hash。缺输入、旧/混合 profile 或 changed head 必须成为非 current 结果或拒绝；不得推测缺值。

实验条件至少覆盖模型/checkpoint、active/total 参数、resolution、frames/FPS/duration、steps/CFG、benchmark version/split、zero-shot/fine-tuned、teacher/student、训练数据范围、hardware、单位和 metric direction。语义差异先显示待审查；不同上下文默认 not_comparable。

### 7.2 官方性与跨来源一致性：关闭 F3

paper-linked、author-linked、author-org、community-only 是发现信号。只有上下文明示 repo 实现该 paper，且 paper/repo 关系证据通过相应 review，才映射 official。作者身份与其声明的对应关系分别核验；baseline/依赖/一般提及不升级。未核验保持 unverified_candidate，明确第三方实现为 unofficial。

固定 repo full commit、许可证 observation、入口/配置/代码行；训练、推理、数据处理、评测、checkpoint 能力分别声明 present/partial/absent/unverified。Absence 要有搜索范围；README 声称不等于代码能力。Hugging Face/checkpoint 仅保留 URL/revision/许可 observation，不下载权重。

Mismatch 检查覆盖 paper↔repo、README↔config、主文↔附录、新旧版本，绑定两侧 locator，先核对实验条件和版本，再产生 review candidate。它不能自动改变 assessment。

### 7.3 可恢复的研究会话

发现来源包含 backward/forward citations、相关主题、作者/项目页面，以及代码/checkpoint 候选。排序解释 seed distance、相关性、年份、来源、diversity、代码可用性；ID 去重与版本归并分开。每轮记录 method/benchmark/implementation/counterevidence/reproduction/chronology 路径、覆盖缺口、观察、重复率、新相关来源收益及预算。

来源独立性按原始证据与转述/镜像关系判断；多个 URL 不自动变成独立验证，未知独立性显式记录，不要求所有 claim 强制拥有两份来源。Stop policy 使用固定配置，根据低收益、覆盖、重复率、预算或用户停止产生可重放结果。Live observations 可变化，同一 frozen observations/config 的结果须确定一致。

读取/发现可在现有两个子 agent 上有界并行；decision 归并、compile、publication preparation 和 index build 仍串行。每篇候选由用户选择；单篇失败不阻塞其他候选。

## 8. 检索、问答与研究产物

基础问答先复用 BM25/catalog/exact evidence；完整检索依次加入 section/claim/figure/table/equation、implementation/config、benchmark/comparison row。Intent 包含 quick/standard/compare/implementation/reproduce/survey/research；entity/filter 至少支持 model/task/year/resolution/benchmark/code availability。

完整路径：独立 exact/BM25/typed-graph 排名→确定性 RRF→证据状态/新鲜度/独立性过滤→有预算 context pack。禁止相加异构 raw score。可选 dense 缺失时基础功能仍工作。Graph 从 canonical relation/claim/evidence 重建，predicate registry 校验两端类型；similarity/共现不自动成为事实边，contradiction detector 先产生 candidate。

Context pack 保存 included/omitted、rank/选择原因、claim/evidence/locator、附近原文和 supporting/counterevidence 角色。存在相关反证时应选入；超预算必须显式标出争议未覆盖，不能以多数相似来源宣称已无反证。无法访问原文时明确缺口。相同 snapshot/config 的 pack 字节一致。

Answer/synthesis proposal 绑定 context、生成 runtime/model、prompt 与输入摘要，区分事实、推断、争议和未知。支持性 review 绑定 exact factual unit、claim、locator 与原始 span；代码核验引用/hash/范围，人工或冻结 gold review 核验语义支持。

文章包含问题、共识、差异、矛盾、未知、比较矩阵和 bibliography。草稿保存在 `.work/research/**`；经选择与 operator 发布后成为 create-only `wiki/synthesis/generated/<artifact-id>.md`。修改生成新 ID 与 supersedes；用户在 Obsidian 复制到自有 notes 后自行编辑。新 namespace 同时纳入 transaction/receipt/audit/backup，不能只生成文件便宣布发布。

复现计划绑定 paper/model、经核验 repo/full commit、entry/config、checkpoint/license observation、软件/硬件/数据需求、验证步骤和预期输出。各项标 verified/inferred/unknown/blocked；verified 必须有出处，明确未下载、未训练、未验证复现成功。

## 9. 工作包、依赖与责任

下面是唯一实施依赖表；E 表示该包工程接口精确验收，S 表示真实产品纵切。后续工程只依赖必要 E，真实发布受相应外部/人工条件约束。W0-R3 正在进行方案与评审交接，W1–W7 产品化实现尚未开始；不重标历史 VPKB 包状态。每个实现包还须在开工前单独冻结其窄合同，这是包的入口条件，不是包对自身的依赖。

| 包 | 依赖 | 交付与主要落点 | 退出条件 |
| --- | --- | --- | --- |
| W0-R3（REQ-10） | 当前基线与设计输入 | 本 PRD、review 讨论、外部意见处置 | 文档与接口交付；外部评审和实施冻结分别记录。 |
| W1 预览（REQ-01） | W0-R3 设计输入 | research request/observation/metadata/preview/decision；preview Skill | E：离线 fixture/安全/安装测试；S：真实 arXiv 中文预览与选择。 |
| W2 单篇流程（REQ-02） | W1-E | selection binding、external blob/parser handoff、两阶段 session/status/next/resume；复用 prepare/extraction/compiler/publication | E：完整链、错版拒绝、幂等恢复；S：真实 PDF 到 Obsidian、receipt/audit。 |
| W5a 基础问答（REQ-05） | W2-E | bounded paper/claim/evidence context、answer、基础 gold | E：引用/支持/要点覆盖；S：真实论文问答。只验 paper 范围。 |
| W3 研究发现（REQ-03） | W1-E、W2-E | OpenAlex/arXiv observation、candidate/rank/session/stop | E：固定观察确定性重放与恢复；S：3 seeds 候选、反证与 gap。 |
| W4 代码映射（REQ-04） | W2-E；W3 输出可选 | code observation、officiality review、commit/config/locator | E：mapping gold 与 code capture；S：确认 1 repo，再按真实 baseline 扩到 5 repo。 |
| W5b1 领域比较报告（REQ-05/06） | W5a-E、W4-E | canonical profile/annotation/review/head 兼容扩展；比较投影与 lint；research 比较回答、矩阵及 bibliography | E：迁移/拒绝/receipt/audit/backup、字节可重建比较投影、冻结比较 gold 与报告支持/覆盖均通过；S：3-paper/1-repo 的 accepted comparison 报告及恢复。无需 typed graph/RRF。 |
| W5b2 完整检索（REQ-05/06） | W5b1-E | typed graph/generation/query、research RRF/context、完整六类 gold | E：graph/rebuild/过滤/完整 gold 全部指标；S：真实跨论文与代码问答，记录反证和未知。 |
| W6 综合与复现（REQ-07/08） | W5b2-E；研究综述还需 W3-E | 完整 article/reproduction、生成快照发布；消费 W5b1 比较产物 | E：引用/语义支持/namespace；S：文章及复现计划。 |
| W7 产品化与恢复入口（REQ-09） | W1、W2、W3、W4、W5a、W5b1、W5b2、W6 的 E | 自然语言 status/audit/backup/isolated-restore 请求与 operator 交接；全部新 namespace 的兼容、UI/Bases、性能、可选只读 MCP | E：检查/备份/恢复入口与跨 namespace 回归；S：真实外部锚、隔离恢复和视觉验收。完整 v1/readiness 独立完成。 |

W3/W4 可并行；基础问答无需等待完整代码发现。首个 3-paper/1-repo 研究里程碑依赖 W1、W2、W5a、W4、W5b1 的完整 E 和对应真实 S；不消费未命名的“部分 E”。W5a/W5b1 使用各自冻结的相关 gold 子集，完整六类检索 gold 和所有完整集指标仍在 W5b2 验收。完整 v1 仍要求七条产品纵切、最终 corpus/五仓基线和其真实验收，不能用小样本代替。

Architect 负责需求、窄合同、路径所有权与最终验收；Builder 实现主要代码/schema/test；Repo Steward 独立检查范围并串行 Git/CI。代码允许路径在每包具体冻结：research 新包归编排，engine 只做命名清晰的兼容扩展，schema/注册共享文件同一时刻一个写者。Fable 只评审设计，不冒充人工或 Architect 验收。

每包包含 full baseline、contract SHA、允许路径、接口/错误码、测试名称、候选摘要、实际 reviewed head/base/CI checkout；head 变则旧结论保留历史，base 变则重做集成核验。首包实际耗时用于后续估算，不在能力 spike 前承诺整项目工期。每包以一个可演示用户结果收尾。

## 10. 验收与质量指标：关闭 F4/F5

| 验收面 | 标准与证据 |
| --- | --- |
| W1 | 自然语言单请求得到真实题录中文预览；准确版本/abstract-only；选择前后 Vault/catalog 零变化；能力缺口可见。 |
| W2 | 真实来源版本正确，claim 有 locator 或 unsupported；错版/缺产物拒绝；故障恢复无重复来源；receipt 对应 inspected bundle。Fixture-E 与真实-S 分开。 |
| W3 | frozen observations/ranking/stop config 产生一致候选与停止决定；去重、来源多样性、反证、路径缺口可见。 |
| W4 | gold 覆盖本文实现/baseline/依赖/第三方/作者无明确对应；gold 中误判 official 为零，未知关系保持未知；真实代码行与能力声明可查。 |
| W5 | 至少 20 个冻结问题，覆盖 model/method/training/dataset/inference/code，标 target_kind、intent/filter、answerability、必答要点、争议和期望来源。完整集合在 W5b2 验收，W5a/W5b1 分别报告冻结子集。 |
| Retrieval | 完整 gold 的 paper Recall@5 ≥ 0.85、evidence-unit Recall@10 ≥ 0.75；同时记录 MRR/nDCG/entity/implementation recall。 |
| Answer usefulness | 每个 answerable gold 的必答要点覆盖 ≥ 80%，整体 ≥ 90%；空事实集、全部 unknown/inference 不计覆盖。Unanswerable gold 必须明确缺证据并不编造答案；gold 在调试前冻结。 |
| Answer support | factual units 全部 supported、可解析引用覆盖 100%、悬空 0；partially_supported 等不算通过。该规则与要点覆盖同时满足，不能靠降为 unknown 绕过。 |
| Comparison | 缺限定/单位/版本/受管 current annotation/profile/head 时不可进入 current supported result；表中值和结论都有出处。 |
| Article / reproduction | 所有 factual units 引用可解析；全部核心结论和表格单元做语义 review，其余按预先冻结的抽样方案检查并声明抽样范围。样本任一不支持即修订；复现所需项均有来源或明确 unknown/blocked。 |
| Recovery / projection | context/graph/comparison generation 输入完整，删除投影可重建；活动 decision/input 保留；profile/版本替换不能复用旧 current 结果。 |

要点覆盖阈值是本 R3 新提出的产品验收标准，需在对应 gold/config 冻结时评审；不声称附件或已有测试提供了这些数值。矛盾识别、不确定性校准、raw-source preference、source independence、benchmark metadata completeness 先作为必报诊断，升级阈值要版本化记录。

评分同时冻结 `rubric`、gold 和 adjudication 规则：每个必答要点有固定 ID、事实范围、所需限定条件与可接受来源，每点等权且最多计一次。单题覆盖率为被充分回答且 supported 的要点数/该题预设要点数；整体为所有 answerable 题的分子之和/分母之和，unanswerable 题单列。不能在看过答案后拆分要点、删除难点、合并问题或改分母；部分回答不计完整覆盖。

Factual unit 按可独立核验的断言切分；数值必须连同对象、单位、版本和实验条件核验，合句中的多个断言分别评分，重复同义句不增加覆盖，省略限定条件不能变成更易通过的单元。答案生成者不能独自制定 gold 或裁定自己的语义支持。独立 reviewer 使用冻结 rubric 给出 unit→point→claim/locator 的标签与理由；fixture/gold 工程规则由 Architect 冻结，真实语义 gold 与争议由用户指定的领域审阅者确认，并遵守现有 claim gate。未裁定争议保留 open，不计通过；修订 rubric/gold 必须新版本、保留旧结果并重跑全部受影响题，不能就地调低标准。

自动测试覆盖 valid/invalid/unknown-key/oversize、identity/hash、跨对象错配、路径安全/零 egress/admin sentinel、429/缓存/恢复、profile/current-head 和跨来源不一致。每包跑适用 focused checks、默认锁定环境回归、checkout 外 wheel 与 Linux/macOS × Python 3.12/3.13 矩阵。模型/真实外部输入 smoke 分开记录，不能用合成摘要替代真实体验。

## 11. 真实输入、发布与完成定义

真实 PDF/源码来源与许可、人工 claim/domain review、Obsidian 视觉验收、raw-inclusive 备份外部锚与隔离恢复、readiness/merge 决定仍待真实证据。它们不阻止 fixture 开发和只读候选发现，阻止相应真实发布/完成声明。

| 既有 gate | 本方案的使用位置 |
| --- | --- |
| HUMAN-GATE-BASELINE-001 | 最终五仓名单及完整 corpus 验收；不把 3-paper/1-repo smoke 写成 baseline 通过。 |
| EXTERNAL-PROVENANCE-LICENSE-001 | 真实 PDF/代码保留、外部源码复制与相应发布。 |
| HUMAN-CLAIM-ASSESSMENT-001 | 真实 claim 接受及最终文章事实依据；domain review 为独立证据记录。 |
| HUMAN-OBSIDIAN-VISUAL-001 | 真实 Vault 可读性和最终 UI 验收。 |
| EXTERNAL-BACKUP-ANCHOR-001 | 完整私有 archive manifest 外部锚及隔离 restore，支持生产 readiness。 |
| HUMAN-READINESS-MERGE-001 | exact-head CI/Architect 验收后的用户决定与点名 PR/head/base/target 的 merge 指令。 |

产品 v1 完成需同时证明：预览、真实单篇入库、3 seeds 扩展、代码映射、跨论文问答、文章、复现计划七条纵切；完整质量集、当前证据链、可恢复研究状态、backup/restore 与相应真实 gate。交付继续 draft PR→integration，不合并 main；测试/模型 review 不自动授权合并。

## 12. 风险与处理顺序

| 风险 | 提前检查 | 处理 |
| --- | --- | --- |
| Web connector 不支持请求/字段 | W1 capability observation | 使用明确能力级别与替代 adapter，或外部 observation；不伪造传输证据。 |
| 外部 parser/blob 交接不可用 | W2 首个 PDF spike | 准备已授权外部执行环境与四件套；明确 awaiting 状态，先验证 E 再跑真实 S。 |
| 研究范围过宽 | 每包演示、首次研究里程碑 | 保留完整目标，按 paper→code→comparison 逐步扩展；新依赖证明收益后引入。 |
| 只过 fixture 或答非所问 | 真实 corpus、必答要点、反证与错配 gold | 分开机制/语义/用户体验，记录失败并修订，禁止把 unknown 当覆盖。 |
| 人工确认过多影响使用 | 每次真实纵切记录操作次数与耗时 | 自动准备输入和 diff、合并内容选择；operator 确认边界保留，可信 broker 将来单独设计。 |
| 方案/数据版本漂移 | 稳定 ID、review revision、source/profile binding | 修订保留原证据，重新检查受影响验收，不覆写历史 GO。 |

## 13. 当前决策与待冻结事项

已确定：完整研究目标、现有唯一内核、Pro 领域设计采用、F1–F5 修订方向、单一依赖表、3-paper/1-repo 首次里程碑、Markdown 外部 review。

对应包冻结前须落实：connector 实测能力；selection binding 的受管发布路径；外部 blob/parser executor 的明确安装/调用合同；domain/profile/annotation closed schemas；gold/stop/rank/budget 配置；真实技术轴与来源、人工 gate 证据。它们有明确 owner 和所属包，不要求为整个 v1 提前生成全部 schema。

本文成稿不表示 W1 已实现，也不把旧 R2 的 hash/GO 转授给 R3。本次任务的完成范围是 PRD 与可使用的 Markdown review 接口；Fable 的实际结论在收到后单独记录。

## 14. 设计输入与追溯

- [Pro 六仓对比附件](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md)，SHA-256 `c7fc3871c8061d4bdc6ba01ce3f07dd385ee002985ee77239a4a217bf42fdc33`。
- [R2 方案](video-generation-research-wiki-v1-plan-r2.md)，SHA-256 `a63f1840e86be25872f6a99b6cea853fe22a209de3782723b5bcc17a2caadf5c`。
- [再评审](video-generation-research-wiki-v1-rereview-2026-09-05.md)，SHA-256 `ab55909080ccf3c7f2cce31280a32d87c254800ff513676381fa04abb7b5c655`。
- [附件综合建议](video-generation-research-wiki-v1-combined-review-2026-09-06.md)，SHA-256 `43abdc2b8baa39ea90f074f0192bc84f878100d68698bb6803b877b9fb09f71f`。
- [六仓源码审计](external-reuse-audit-2026-09-04.yaml)、[团队约定](codex-team.md)、[历史任务索引](task-index.yaml)。索引中的旧观察日期/状态保持历史，当前产品化接续按本文 §3、§9。

F1→§6.3/W2；F2→§6.2/W2；F3→§7.2/W4；F4→§8/§10/W5；F5→§9。Pro 的联合证据、领域分类、两阶段、检索、研究 session、可比性分别落入 §7.2、§7.1、§6.4、§8、§7.3、§7.1/§10。

## 15. Fable 5.1 ↔ Codex Markdown 评审接口

### 15.1 当前交接状态

- 历史第一轮受评正文：R3.2；包括文件标题/版本说明与 §1–14。第一轮评论绑定此 revision 和正文摘要；当前 follow-up 对象见下方 R3.3 链接。
- 正文摘要范围：原始 UTF-8/LF 文件从第一个字节起，到 `## 15. Fable 5.1 ↔ Codex Markdown 评审接口` 标题前的全部字节（含其前空行），不做空白归一化。§15 不参与摘要，因此评论追加不改变被评审正文身份。
- Reviewed body SHA-256：`1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24`。不能计算摘要的平台可抄录该声明值并注明“未核验”；不得声称已做字节核验。
- 外部 reviewer：用户指定 Fable 5.1；实际调用/身份由用户所在平台提供，本文件不伪造验证。
- 当前状态：`awaiting_fable_rereview`。已收到 Fable 第一轮 FABLE-001–013，verdict 为 changes_requested；本轮 Architect 已逐项回复，无 finding 标为 resolved。FABLE-002/008 的产品选择仍 pending，已交用户决定。
- 当前复审候选：[独立 R3.3 successor](video-generation-research-wiki-v1-prd-r3.3.md)，正文 SHA-256 `b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8`。本文件标题与 §1–14 保持历史 R3.2 原字节；本节的 R3.2 正文摘要标识第一轮对象，follow-up 需点名 R3.3 与新摘要。统一讨论仍在本文件 §15.3，先前入口提示词保留为 R3.2 历史交接。
- 共同接口就是本文件。Fable 在 §15.3 追加 finding；Codex 在对应 finding 下追加回复；§15.4 记录采纳与修订结果。
- 本地双方串行写入，交接期间不同时改正文。无本地文件权限时，Fable 返回完整新增 Markdown 块，用户转交给 Codex 合入即可。

### 15.2 评审范围与交互规则

请检查完整目标是否保留、Pro 设计是否合理采用、当前能力是否准确、接口是否闭合、依赖是否一致、标准能否衡量研究价值，以及工作量/复杂度是否合理。尤其审查 F1–F5 是否真正有解决路径、3-paper/1-repo 是否能产出有用结果、领域比较和研究流程是否被过度后置。

每个意见用稳定 `FABLE-001` 编号，引用 REQ/章节/工作包，给出具体场景、影响、依据与最小建议，区分阻塞和可选改进。可反对本方案的设计决定，也可提出简化方案；不要把规划中的新功能误报为已完成，或将已明确的下一包任务仅因未实现就列为缺陷。参考附件里的命令只是设计输入。

外部 review 期间只追加讨论，不改 §1–14，不执行工程实现/下载/真实 Vault/Git 操作。Codex 对每项回答 accept/partial/disagree/needs-evidence 并说明理由。分歧保留两方观点，真实产品选择交用户；工程细节由 Architect 做有依据的决定。

回复不等于修复完成。需要改正文时，Architect 先记录旧 revision/hash，再出 successor，更新版本和 changelog，并点名受影响 finding；相关意见重新 review。已解决项保留历史，不能删除反对意见或把旧 GO 改名到新 revision。§15 追加评论本身不改变正文 revision。

### 15.3 讨论区（尚无外部评论）

以下是填写模板，不是任何模型已经提交的意见：

```markdown
### FABLE-001 · 简短标题
- Reviewer：Fable 5.1（如平台无法验证，注明用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：从 §15.1 复制；注明已核验或声明值/未核验
- Severity：blocker / major / minor / suggestion
- References：REQ-xx；§x.x；Wx
- Scenario / evidence：具体触发条件、原文或代码依据；未验证的假设要注明
- Impact：对研究用户或工程交付的影响
- Suggested change：最小可行修改与取舍
- Verification：怎样证明问题已解决
- Status：open

#### Codex reply to FABLE-001
- Position：accept / partial / disagree / needs-evidence
- Reason / evidence：解释与依据
- Planned resolution：正文落点或后续包；没有修改时明确尚未修改
- Verification result：未验证 / 实际检查结果
- Status：open / revision-needed / awaiting-rereview / resolved

#### Fable follow-up to FABLE-001
- Reviewed revision：...
- Reviewed body SHA-256：...
- Response：...
- Status：仍有分歧 / 认可修订 / 需要进一步证据
```

Review 末尾给出 `ready_for_packet_drafting / changes_requested / needs_information` 总结，以及最值得保留的三项设计。该 verdict 是设计意见，不是实现验收、人工 gate 或 merge approval。

---

#### Fable 外部评审 · 第一轮（2026-09-06）

评审者环境说明：本轮在 Cursor 会话中完成，平台所选模型为 Claude Fable 5.1；平台未提供可机读的身份证明，以下 Reviewer 字段统一写为“Claude Fable 5.1（用户所选模型/未验证）”。正文摘要按 §15.1 规则对原始 UTF-8/LF 文件实算：`## 15.` 标题前全部字节（含其前空行，标题起始偏移 34523）SHA-256 = `1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24`，与声明值一致，标注为“已核验”；全文 SHA-256 `dddf743620c6920aca294ed732992e4ddc85e28ae739005071ee71b051a429e4` 亦与评审入口文档一致。本轮实际读取的材料：本 PRD、`fable-5.1-review-entry.md`、`video-generation-research-wiki-v1-rereview-2026-09-05.md`、`video-generation-research-wiki-v1-combined-review-2026-09-06.md`、`codex-team.md` 前 40 行，以及仓库源码抽查（`src/video_paper_wiki/parse/docling_local.py`、`blob_store.py`、`publication.py`、`approval.py`、`contracts.py`、`retrieval.py`、`restore_verification.py`、`schemas/` 目录清单、`README.md`、`docs/video-paper-wiki-development-plan-v0.3.2.md` 生命周期段）。未读取：Pro 六仓对比附件、R2 方案全文、W0 冻结 JSON、`external-reuse-audit-2026-09-04.yaml`、`task-index.yaml` 正文；未查询远程 CI、未访问 arXiv/OpenAlex 网络。本轮只评审设计，不执行实现、下载、真实 Vault 或 Git 操作。

### FABLE-001 · 十状态生命周期是文档推导规则，不是已实现的状态接口；W2 需冻结推导所有者
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：minor
- References：REQ-02；§3；§5 产物所有权表；§6.4；W2
- Scenario / evidence：§6.4 写“保留现有 canonical 流程：`absent → planned → … → verified`”，§3 又列“已有工程代码覆盖 … 等底层能力”，合读容易被理解为引擎已有统一状态查询。事实核查：该十状态链只出现在 `docs/video-paper-wiki-development-plan*.md`（v0.3.2 第 456–468 行明确“状态从 immutable artifact、canonical record、assessment/receipt 链推导，不维护可变 job database”）；`src/` 与 `schemas/` 中不存在 `capture_inspected`/`ingest_inspected`/`applied_provisional` 等枚举（`prepared.v1` 的 enum 只是四类产物名，`repo-record`/`paper-code-alignment` 的 enum 是官方性/能力值）。同时 §5 把 session/next_action 归 research 包，§6.4 要求“next_action 每次根据 artifact/receipt 重算”，但没有说明这个“从产物推导状态”的函数归 engine（只读查询）还是 research（自行重实现）。假设：Codex 团队内部清楚这是设计规则而非现成 API；但工作包读者未必。
- Impact：若 research 自行实现推导，会出现与 engine 的 receipt/inspection 语义不一致的第二套状态判断，正是 §5 “不创建平行 ledger”想避免的；若 engine 实现，则 W2 的 engine 兼容扩展范围需要提前写明。W2-E 的“幂等恢复”验收依赖此函数，但目前无 owner。
- Suggested change：§3 将该生命周期标注为“文档定义、按产物推导，尚无统一 status 查询实现”；§5/§6.4 明确：engine 提供唯一只读 `status derive`（输入 receipt/inspection/artifact 集合，输出状态与最后可证明步骤），research 只消费并叠加 session 层 next_action。W2 合同把该查询列入 engine 兼容扩展的允许路径。
- Verification：W2 合同中只存在一处状态推导实现；fixture 覆盖每个状态与“失败停在最后可证明步骤”；research 测试通过 mock engine 输出而非重算产物来验证 next_action。
- Status：open

#### Codex reply to FABLE-001
- Position：accept
- Reason / evidence：接受状态推导所有者与当前能力表述不清的问题。R3.2 §6.4 沿用的是文档中的十状态流程；只读检索 src/schemas 未见实现该完整枚举的统一 status 接口。§5 已把 session/next_action 归 research，但未指明 receipt/inspection 状态谓词归属，确有产生重复判断的风险。Engine 应拥有唯一 canonical 证据推导；research 仍拥有用户选择、外部输入等待与交互动作，不能把全部 next_action 也搬入 engine。
- Planned resolution：已在独立 [R3.3](video-generation-research-wiki-v1-prd-r3.3.md) §3、§5、§6.4 明确文档规则与尚未实现的查询之别；W2 新增 engine 只读推导 facade，输出 last provable state、证据引用及缺失条件；research 消费该结果并叠加 session 事实。具体接口名、closed 输出与单一允许路径在 W2 冻结；不另建可变 job database。
- Verification result：已只读核对生命周期文档及源码/现有 schema 的职责，并检查 R3.3 的 owner/数据流表述；没有执行或实现 status derive。逐状态、冲突/缺件、失败停留及 research mock 消费案例仍是 W2 待实现验收，不能以历史 CI 证明。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-001
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验；`## 15.` 标题起始偏移 56073）
- Response：认可设计修订。R3.3 §3 补充能力边界、§5 新增职责段、§6.4 明确“文档定义的推导语义，不是现有统一状态 API”，并把唯一只读推导 facade 归 engine、next_action 归 research。这已回答第一轮的所有者问题。区分：设计问题已澄清；facade 的接口名、closed 输出、逐状态/冲突/apply 后 audit 失败 fixture 属于 W2 实现验证，尚未发生。不影响 W1。
- Disposition：认可设计修订；实现验证留 W2 冻结。
- Status：认可修订

### FABLE-002 · 首个里程碑的价值路径过长：W5b1 捆绑 canonical 迁移，W6 文章依赖 W5b2
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：major
- References：REQ-05/06/07；§1 首个研究里程碑；§7.1；§9 W5b1/W5b2/W6；§11 HUMAN-CLAIM-ASSESSMENT-001
- Scenario / evidence：§9 规定首个 3-paper/1-repo 里程碑由 W5b1-S 交付“accepted comparison 报告”，而 W5b1 的交付同时包含“canonical profile/annotation/review/head 兼容扩展；比较投影与 lint”，E 要求“迁移/拒绝/receipt/audit/backup、字节可重建比较投影”。§7.1 又规定 supported 领域事实要求 annotation review 与 claim assessment 均 accepted，后者受 HUMAN-CLAIM-ASSESSMENT-001 约束。W6（文章/复现）依赖 W5b2-E，即 typed graph、generation/query、RRF 和完整六类 gold。也就是说：用户第一次看到跨论文比较报告之前，必须完成一次 canonical schema/namespace 迁移并人工 review 报告涉及的全部 annotation；第一次得到中文文章之前，必须完成图谱与完整检索。对于 3 篇论文的比较，一个带引用、比较矩阵、bibliography、并把实验条件默认标为 `not_comparable/待审查` 的报告，并不需要 typed graph、RRF 或 canonical annotation head 才能产出。这是设计取舍判断，不是把规划功能当缺陷。
- Impact：研究用户在 W1、W2、W5a、W4 之后仍要等待一次最重的 engine 迁移才能得到首个比较产物；REQ-07 的文章被后置到几乎最后。§12 “研究范围过宽”“人工确认过多”的两项风险在里程碑路径上同时叠加，首包耗时估算（§9）也无法覆盖它。
- Suggested change：将 W5b1 拆为两层并在 §9 单独成行：(a) `W5b1-R`：research 侧有界比较报告，消费 W5a context 与 W4 代码证据，实验条件作为 proposal 抽取，所有 typed 事实标 `provisional/unreviewed`，产物留在 `.work/research/**`，作为首个里程碑的交付；其 E 为“报告支持性 + 要点覆盖 gold + 条件缺失即 not_comparable”，无需 canonical 迁移。(b) `W5b1-C`：现有 W5b1 的 canonical profile/annotation/head 扩展与字节可重建投影，作为“accepted typed comparison”的路径。同时把 W6 的必需依赖改为 W5b1-E + W4-E（文章/复现计划），W5b2-E 与 W3-E 只作为综述规模/矛盾检测的可选输入。取舍：首个里程碑报告不再声称“accepted comparison”，但 §1 本就把它定义为“有界比较问答产物”，与最终五仓基线分开。
- Verification：§9 依赖表出现拆分后的行且首个里程碑明确指向 W5b1-R；W6 依赖变更后仍无环；W5b1-R 的 E 条件中不含 canonical 迁移项；里程碑演示能在无 annotation head 的 Vault 上产出报告并正确标注 provisional。
- Status：open

#### Codex reply to FABLE-002
- Position：partial
- Reason / evidence：接受首个有用产物被 canonical 迁移及 W6→W5b2 路径拖后的判断。R3.2 §8 允许 `.work/research/**` 草稿，§7.1/§9 则把 accepted typed comparison 绑定 annotation/head/review；因此带出处、明确 provisional/unreviewed 的比较草稿可以在没有这些 canonical head 时生成，但它不能满足原 W5b1 的 accepted comparison 退出条件。这既是技术拆分，也是用户会看到两种可信程度产物的产品取舍，不能只凭 Architect 或 Fable 建议改写原里程碑。
- Planned resolution：R3.3 §13 已列出供用户决定的具体方案：推荐拆出 W5b1-R（W5a-E+W4-E，比较报告/矩阵/bibliography，抽取条件为 provisional，缺条件即 not_comparable）与 W5b1-C（原 canonical 迁移和 accepted typed comparison）；W6 早期草稿可消费 R 路径，图谱成为可选增强，受管发布仍守 canonical/claim review/namespace 门槛。替代方案是保留原 canonical-first 路径。已向用户询问；未收到决定，R3.3 §1/§9 仍保留 R3.2 的生效路径，本建议没有被标为采纳或部分 E。受影响章节为 §1、§7.1、§8、§9、§13。
- Verification result：已做设计依赖和信任边界核对：技术上存在不消费 annotation head 的草稿路径，当前表仍无环；未运行无 annotation Vault 演示。产品选择和依赖改写尚未完成，不能据此声称首个里程碑已简化。
- Status：open

#### Fable follow-up to FABLE-002
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可 Codex 将其归为用户产品取舍，且 R3.3 §13 的选项表把两条路径、代价与生效条件写清楚了。对推荐方案的技术评价：W5b1-R 路径依赖 W5a-E + W4-E，不新增 canonical 写路径，产物留在 `.work/research/**` 并标 provisional/unreviewed，与 §5 所有权和 §8 草稿规则一致；W6 草稿消费 R 路径而受管发布仍守 canonical/claim review 门槛，也没有破坏 §11 gate。Fable 继续推荐拆分方案，理由是首个可用比较产物提前到 W4 之后，且用户能看到“待审草稿”与“受审事实”的明确区分；代价是产品中同时存在两种可信度的产物，需要 UI/文案区分。若用户选择保留 canonical-first，方案仍然自洽，只是首个报告更晚。该决定不影响 W1 接口冻结与实现；W1 数据对象在两条路径下相同。
- Disposition：待用户选择（推荐 W5b1-R/W5b1-C 拆分；不阻塞 W1）。
- Status：仍待用户决定

### FABLE-003 · 冻结 gold 的作者、时序和子集规模未定义，W5a/W5b1 子集可被缩小规避
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：major
- References：REQ-05；§9 W5a/W5b1/W5b2；§10 W5 行、评分裁定段；§13
- Scenario / evidence：§10 要求“至少 20 个冻结问题 … 完整集合在 W5b2 验收，W5a/W5b1 分别报告冻结子集”，并要求“gold 在调试前冻结”“答案生成者不能独自制定 gold”“真实语义 gold 由用户指定的领域审阅者确认”。但：(1) 子集没有最小规模，W5a 可以用 3 道题的子集声称达标；(2) 真实 gold 必须基于用户选定的 3 篇论文（§13 “真实技术轴与来源”尚待冻结）编写，而回答器也要在同一 corpus 上调试——谁在何时写 gold、以什么记录证明 gold 冻结先于第一次真实回答运行，PRD 未规定；(3) 在单用户 Codex 环境中，起草 gold 的 Architect 与产出回答的 research 运行时可能是同一模型家族，PRD 只说“不能独自制定”，没有说明最小的独立性证据是什么（例如 gold hash 先于回答 run 记录、领域审阅者签署）。
- Impact：§10 的要点覆盖与支持性规则本身设计严密，但绕过点在“集合定义”而非“评分规则”：小子集、事后选题、gold 与回答同轮迭代都能让数字看起来达标而研究价值不足。
- Suggested change：§10 增加：W5a 子集 ≥ 10 道 answerable + ≥ 3 道 unanswerable；W5b1 子集 ≥ 6 道比较题，其中 ≥ 2 道期望结论为 `not_comparable`；gold 由 Architect 依据论文原文起草、用户/领域审阅者确认后计算 SHA-256 并写入工作包，任何真实回答 run 的记录必须引用该 gold hash 且时间戳晚于冻结记录；子集题目从完整 20 题中按冻结规则抽取，不得在看到回答后调换。
- Verification：工作包含 gold hash 与冻结时间；回答 run 记录引用 gold hash；子集规模满足下限；审计脚本能检出“run 早于冻结”或“子集题目不在完整集中”的情况。
- Status：open

#### Codex reply to FABLE-003
- Position：partial
- Reason / evidence：接受阶段题数、编制/确认者、冻结顺序及最小独立性记录缺失。采纳 W5a 至少 10 道 answerable+3 道 unanswerable、比较阶段至少 6 题含 2 道 not_comparable 的初始下限，但这些是本修订的验收设计，不是统计可靠性保证。不同意强制早期 gold 必须是未来完整 20 题的同一 truth 子集：R3.2 §9 中 W5a 早于代码与完整检索，后续 corpus/版本变化可能改变 answerability 和期望来源；强称同一子集反而会伪装未变的 gold。
- Planned resolution：R3.3 §9/§10/§10.1 改为独立版本化的阶段 gold 和之后完整 ≥20 题 benchmark，保留题目 lineage/hash 引用而不强制集合相同。每个 manifest 绑定 corpus/source-version、题目/必答点、truth、rubric、作者/实际领域 reviewer、freeze event/前驱摘要。开发集与 qualification 集分开，dispatch 前冻结验收题、待验 model/prompt/config、context 和全部 run 清单；已发生的开发回答不得改名 S。真实语义 gold 仍须实际用户/领域 reviewer 确认；同家族模型或墙钟时间戳不自动提供独立权威。若接触验收集后调试，回归结果与未见题泛化分开声明。
- Verification result：已核对 R3.2 的阶段顺序，并在 R3.3 检查最小规模、manifest 绑定、冻结顺序与变更后重跑规则相容。尚未创建任何真实 gold、freeze/approval 事件或执行审计脚本；真实题目和领域确认仍待对应工作包。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-003
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订。R3.3 §10 W5 行给出阶段下限，§10.1 定义 manifest 绑定、作者/reviewer 记录、freeze event/前驱摘要、开发集与 qualification 集分离、holdout 与回归分开声明。接受 Codex 对“阶段 gold 必须是完整 20 题子集”的不同意见：用题目 lineage 而非集合相同来表达延续性更诚实，第一轮建议在此点撤回。剩余事项都属于 W5a/W5b1/W5b2 packet 冻结时的具体配置：下限数字、reviewer 事件格式、审计脚本；不需要再改 PRD 正文。
- Disposition：认可设计修订；数字与记录格式留 W5a/W5b1/W5b2 冻结。
- Status：认可修订

### FABLE-004 · 真实模型 S 验收缺少运行协议：次数、pass 判定与非确定性处理
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：minor
- References：REQ-05/07；§8 Answer/synthesis proposal；§10 Answer usefulness/Answer support；§10 末段
- Scenario / evidence：§10 要求 factual units 100% supported、要点覆盖每题 ≥ 80%、整体 ≥ 90%，并要求“模型/真实外部输入 smoke 分开记录”。§8 将 proposal 绑定 runtime/model/prompt hash。但 LLM 回答在相同输入下并非字节确定，PRD 没有说明 S 验收跑几次、单次失败是否判定整体失败、是否允许重跑择优。一次幸运运行可通过，一个偶发的 unsupported unit 也可让整包失败，两种结果都不能稳定衡量研究价值。
- Impact：S 结论不可复现，事后争议无法裁定；也给“重跑直到通过”留下空间。
- Suggested change：§10 冻结 S 运行协议：固定 model/runtime/prompt hash；每题 n ≥ 3 次独立运行，每次 proposal 与 context pack 归档；pass 判定为“每次运行都满足支持性 100%”且“覆盖率按每次运行分别计算，取最小值对阈值”；记录方差与失败明细；不允许丢弃运行记录。若团队选择单次运行验收，也必须明确写出并保留全部 proposal。
- Verification：验收记录列出所有 run ID、每 run 指标与归档 hash；审计能证明未丢弃运行。
- Status：open

#### Codex reply to FABLE-004
- Position：accept
- Reason / evidence：接受真实模型验收存在择优与随机性解释缺口。R3.2 §8 绑定生成输入、§10 规定单个产物指标，但没有规定 qualification 清单和重复次数；单次幸运输出不能代表所声称的运行协议。确定性投影 E 与随机生成 S 也必须分开。
- Planned resolution：R3.3 §10.2 默认每个冻结验收样本执行 3 轮完整生成，预登记 question/run 清单，固定模型/runtime、prompt、context、可观察 decoding 配置；保留全部 attempts、输出及评分。每轮分别满足 support 与覆盖阈值，以最小值判定并报告 median/range。文章/复现按预冻结的全量核心及抽样规则每轮判定，不把抽样称为全篇证明。基础设施失败/补跑规则预先固定；修订 prompt/config 后建立新 attempt 并重跑全部受影响 slice。
- Verification result：已检查协议与 §10 原支持性/覆盖公式不冲突，记录范围能区分成功、失败、取消和替代运行。尚未执行任何模型资格运行；这里只能设计并将来核验受管清单完整性，不能证明其他会话从未出现未记录尝试。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-004
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订。§10.2 的 3 轮、预登记 run 清单、最小值判 gate、median/range 报告、补跑分类预冻结、“不可观察字段明确 unknown”，以及“确定性 E 不套用三轮协议”都覆盖了第一轮的诉求。剩余为 W5a packet 的实现事项：run 清单 schema、归档路径、补跑分类枚举。§10.2 的 “不可观察的 decoding 字段明确 unknown” 原则同样适用于 W1 预览的模型/runtime 字段，见 FABLE-015。
- Disposition：认可设计修订；协议落地留 W5a 冻结。
- Status：认可修订

### FABLE-005 · 同一实体多个 arXiv 版本共存规则缺失（v1 已入库后再入库 v2）
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：major
- References：REQ-02/05/06/07；§6.2；§7.1 实验条件；§7.2 Mismatch 新旧版本；W2、W5b1、W6
- Scenario / evidence：§6.2 很好地关闭了“选 v1 却拿到 v2”的 F2，并保留去版本实体 ID（源码 `contracts.py:427-433` 要求 ingest plan 的 `arxiv_id` 去版本）。但它只覆盖单次入库。视频生成论文常见 v1（预印本）→ v2（camera-ready，表格数字或 baseline 变更）。场景：用户已入库 v1 及其 claim；数月后希望加入 v2。PRD 没有说明：同一实体是否允许第二个来源版本进入同一 Vault；两个版本的 claim 是共存、v2 supersede v1，还是拒绝；Paper Page 展示哪一版；比较矩阵与文章引用是否必须带版本；§7.2 的“新旧版本 mismatch”只产生 review candidate，不定义数据形态。§7.1 的实验条件列表也未把“来源版本”列为条件。
- Impact：比较矩阵可能混用同一论文 v1/v2 的数字而看起来是同一来源；文章引用 `arXiv:xxxx` 无法定位到被引数字所在版本；若一律拒绝第二版本，知识库将停留在过时版本。
- Suggested change：W2 合同：实体保持去版本；每个来源版本一条独立 source record；“当前展示版本”是用户 append-only decision 而非自动最新；claim/evidence locator 始终携带来源版本。§7.1 把“来源版本”加入实验条件最小集合，不同版本默认 `not_comparable` 直到 lint 确认条件一致。W6 文章 bibliography 与行内引用必须版本限定。
- Verification：fixture 同时入库 v1 与 v2；Paper Page 列出两个版本与当前展示决定；比较行显示版本字段，跨版本行未经 lint 通过时标 not_comparable；文章引用全部可解析到版本限定 locator。
- Status：open

#### Codex reply to FABLE-005
- Position：partial
- Reason / evidence：接受多版本共存/展示/引用语义缺口。R3.2 §6.2 只定义单次 selection/source 绑定，§7.1 的比较条件也未列来源版本；但“每版本新建一条 source record”需要按既有身份模型改写。`identity.py` 的 establish_canonical_paper_id 及 `contracts.py` prospective 校验会拒绝已有 paper ID 绑定另一 PDF；paper-record.v1 虽有 plural source_ids，却只有一组 active_extraction 字段。不能通过 research 列表绕过这些拒绝，也不能把同 bytes 的不同版本观察强行变成重复内容身份。
- Planned resolution：R3.3 §3、§6.2、§7.1、§8 规定 W2 的版本感知 engine 兼容扩展：paper ID 仍去版本，managed source-version association 绑定版本、selection/acquisition、source-ledger ID、PDF/解析 hash 与 receipt；同版本异 bytes 冲突，不同版本可保留各自来源关联。展示 decision/head 与 paper-record active_extraction 兼容镜像同事务一致，source_ids 汇集来源；新版本不自动切换展示或 retire/supersede/accept 旧 claim。相同文本沿用现有 claim 身份，证据变化按既有 assessment 失效规则处理。矩阵及行内/bibliography 引用都限定版本；W2 须同时冻结 legacy 适配、prospective/compiler/receipt/audit/backup，不修改旧 v1 身份语义。
- Verification result：已只读核对 identity.py、contracts.py 与 paper-record.v1 的冲突/active extraction 约束，R3.3 明确这是新增兼容工作。未导入 v1/v2、未验证真实迁移；同版本冲突、共存、展示回退、旧客户端和 assessment 失效案例仍待 W2 实现。第二版本当前仍须明确拒绝，不能宣称已支持。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-005
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订。R3.3 §6.2 多版本合同五条、§7.1 把“来源版本及其 PDF/产物 hash”列入实验条件、§8 引用版本限定，比第一轮建议更完整：display head 与 `active_extraction_*` 兼容镜像同事务一致、claim ID 不因版本标签改变、证据变化按既有失效规则处理，这些都是正确的取舍。已核对 Codex 引用的 `identity.py:318` 与 `paper-record.v1` 单组 `active_extraction_*` 事实。保留一个包级关注（不要求改正文）：这段兼容工作（association、display head、prospective validator、compiler、receipt/audit/backup、legacy 适配）使 W2 明显变重，而 W5a 基础问答并不依赖多版本共存；建议在 W2 packet 冻结时评估把“版本感知兼容扩展”拆为 W2 之后的独立包，W2 核心保持“第二版本显式拒绝”（R3.3 已允许该过渡态）。这是排期判断，见 FABLE-014。对 W1 的要求只有一条：W1 的 metadata/preview/decision 必须以稳定 ID + 内容 hash + resolved version 形式可被 W2 association 引用，不需要 W1 预先实现任何多版本逻辑。
- Disposition：认可设计修订；实现与是否拆包留 W2 冻结。
- Status：认可修订

### FABLE-006 · W1 版本解析规则：用户指定版本与服务返回版本不一致时的处理未写明
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：minor
- References：REQ-01；§6.1；§6.2；W1
- Scenario / evidence：§6.1 写“接受合法新旧 ID/版本及 abs URL”，并保存“resolved version”。场景：用户粘贴 `abs/2311.15127v1`，而当前最新为 v2。legacy API 以 `id_list` 携带版本时据我理解会返回指定版本的元数据（此点未在本轮验证，属假设）；若走 §6.1 允许的规范化官方页面 adapter，abs 页面默认展示最新版。PRD 未规定：输入显式版本时预览必须是该版本还是可以“解析到最新”；不带版本时如何标注“观察时刻的最新版本 = vN，是否存在其他版本”。这直接决定 §6.2 链条第一环的语义。
- Impact：预览与后续 selection binding 可能针对不同版本，F2 的检查会在 W2 才把它拒绝，用户体验是“选了却入不了库”，且原因不直观。
- Suggested change：§6.1 增加规则：输入含显式版本 → 预览必须是该版本，否则返回稳定错误码（如 `VERSION_NOT_SERVED`）并展示可用版本；输入不含版本 → resolved 为观察时刻最新版并在预览中显示“vN（观察时刻最新；是否存在其他版本：是/未知）”。页面 adapter 若不能提供指定版本，必须显式声明能力缺口。
- Verification：fixture：显式 v1 而服务返回 v2 → 拒绝；无版本 → resolved version、观察时间和“其他版本存在性”字段写入 metadata 并进入 preview hash。
- Status：open

#### Codex reply to FABLE-006
- Position：accept
- Reason / evidence：接受显式 requested version 与 resolved version 的规则缺失。该产品合同不依赖“legacy API 一定返回指定版本”的假设；本轮也未验证那个服务行为。无版本输入同样不能把观察到某个 vN 自动写成最新，除非 observation 真有相应证据。
- Planned resolution：R3.3 §6.1 规定显式 vN 必须得到同版本 metadata/摘要；不匹配、不可服务或 adapter 无法证明分别返回稳定拒绝/能力缺口，不静默回退。无版本预览保留 resolved version、观察时间、latest 状态及其他版本存在性；不能证明最新时显示 latest_unknown，若用户选择已知版本则另记显式 decision。缓存策略及这些字段进入 metadata/preview hash；具体错误码在 W1 冻结。
- Verification result：已在文档层核对规则与 §6.2 selection binding 连贯，保留了 Fable 对 API 行为的假设标注。没有访问 arXiv 或执行网络 fixture；显式错版、page adapter 能力不足和 latest unknown 仍是 W1 待验证案例。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-006
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订。R3.3 §6.1 显式版本规则覆盖：显式 vN 必须同版本、三类可区分拒绝、无版本时记录 `latest_at_observation`/resolved/观察时间/其他版本存在性、`latest_unknown` 需用户显式选择、缓存键区分策略、字段进入 metadata/preview 摘要，并且不依赖 API 行为假设。这是 W1 直接可实现的合同，无剩余矛盾。W1 packet 需要落地的只是三个错误码名称、`other_versions_exist` 的取值枚举和对应 fixture。
- Disposition：认可设计修订；错误码与 fixture 留 W1 冻结（属 W1 正常范围，非阻塞）。
- Status：认可修订

### FABLE-007 · 发布到投影之间存在新鲜度断点：问答可能静默漏掉刚入库的论文
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：major
- References：REQ-02/05；§5 Projection 与产物所有权表；§7.3 末段；§8 Context pack；§10 Recovery / projection；W2、W5a
- Scenario / evidence：§5 规定 catalog/BM25/graph generation 由 operator 串行构建，research 只读查询并“绑定 engine 返回的 generation/locator”；`README.md:98` 确认 `vpwiki` 不构建索引。场景：用户完成第 4 篇论文的 operator 发布（W2-S），随即问“比较这四篇的训练分辨率”；BM25/catalog generation 仍是基于 3 篇构建的。§10 Recovery / projection 只要求 generation 输入完整、可重建，没有要求 generation 相对当前 Vault receipt head 的新鲜度，也没有要求答案披露“未被索引的已发布来源”。§7.3 说“index build 仍串行”，但 REQ-02 的“说明下一动作”并未把“索引待重建”列为用户可见状态。
- Impact：答案缺少第 4 篇论文却带着完整引用与高支持性通过所有 §10 规则——这正是“机制通过、研究价值缺失”的情形；用户会误以为知识库已覆盖该论文。
- Suggested change：§8 context pack 增加 `generation_freshness`：记录 generation 的输入 receipt head 与查询时 Vault 当前 receipt head；不一致时列出未覆盖的已发布 source ID，答案开头必须声明“索引未覆盖 N 个已发布来源”，session next_action 给出“需要 operator 重建 catalog/BM25 generation”。§10 Recovery / projection 增加“stale generation 不得产出无提示答案”。
- Verification：fixture：发布新论文但不重建 → 查询输出含 stale 标志与未覆盖 ID 列表；重建后标志消失；stale 情况下的回答若缺少声明则验收失败。
- Status：open

#### Codex reply to FABLE-007
- Position：partial
- Reason / evidence：接受 R3.2 §5/§8 只要求 generation/locator 绑定、未写清用户可见的新鲜度、覆盖范围和重建动作；但不同意以“stale 加提示后仍回答”替代现有拒绝。只读源码表明 catalog_store.py 的 catalog_status 会收集 current audited material 并比较 live digest；query_catalog 在查询前拒绝 CATALOG_STALE，查询后还会以 RETRIEVAL_GENERATION_MISMATCH 拒绝变化。因此第一轮描述的静默漏答风险是研究层必须防止的集成退化，并非已证明现有查询可直接静默返回 stale 结果。仅比较 receipt head 也不足以推导精确遗漏 ID。
- Planned resolution：R3.3 §3、§6.4、§8、§10 保留上述拒绝，要求 research 消费 engine freshness/reasons，stale/unknown/missing 时不生成当前知识库回答，显示 operator rebuild next_action。成功 context 绑定完整 generation/input/audit snapshot。新增 coverage diff 仅从可靠的 current source-version inventory 与 indexed manifest 求差；无法确认时为 coverage_unknown，不虚构 0 或精确数量。合法 query filter 排除另记，不当作索引遗漏；receipt head 只是诊断输入，最终仍核对 live 依赖。
- Verification result：已只读核对 catalog_store.py:583–688 与 catalog_collector.py 的 retained audit/collection 逻辑，并检查 R3.3 没有降低既有拒绝。未运行查询或重建；新发布未索引、查询期间替换、覆盖未知以及重建恢复 current 的产品级 fixtures 待 W2/W5a。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-007
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订，并接受 Codex 的 partial 立场。已核对 `catalog_store.py` 确有 `CATALOG_STALE` 与 `RETRIEVAL_GENERATION_MISMATCH` 拒绝；第一轮把风险描述为“现有查询会静默返回 stale”不准确，准确的表述是“research 层若绕开或降级这些拒绝就会静默漏答”，R3.3 §8 已明确禁止降级。“stale 时拒绝并给 operator next_action”比“stale 加提示后回答”更严格，且与引擎一致，Fable 接受。`coverage_unknown`、`excluded_by_scope`、receipt head 仅作诊断输入，都是正确的补充。一个使用面代价请在 W5a packet 记录到 §12 “人工确认过多”风险项下：每次发布后到 operator 重建之间，用户完全不能对“当前知识库”提问；这是自洽的设计选择，不是缺陷，但需要在 W2-S/W5a-S 中记录实际操作次数与等待时长。
- Disposition：认可设计修订；fixtures 与操作负担记录留 W2/W5a 冻结。
- Status：认可修订

### FABLE-008 · REQ-09 的产品级备份/恢复入口放在 W7 过晚，真实数据自 W2-S 起就已存在
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：major
- References：REQ-02/09；§2 末段；§5 末段；§6.4 保留策略；§9 W2/W7；§11 EXTERNAL-BACKUP-ANCHOR-001
- Scenario / evidence：§9 W7 依赖 W1–W6 全部 E，是唯一交付“自然语言 status/audit/backup/isolated-restore 请求”的包。§5 说各生产者包自身承担 receipt/audit/backup 完整性，这是数据层要求；用户可用的入口仍只在 W7。同时 §6.4 承认模型输出、用户 decision、选中输入“具有不可重建内容”，它们位于 `.work/research/**`，不在 Vault canonical bytes 中；“结束后可导出保留包”没有归属包。§2 又承诺正常使用不要求用户拼接底层命令。`README.md:107` 显示 engine 已有 `backup manifest/verify` 与隔离恢复验证能力（`restore_verification.py`）。
- Impact：从 W2-S（真实 PDF、真实 decision）到 W7 之间跨越 W3、W4、W5a、W5b1、W5b2、W6，研究用户在此期间只能靠原生 CLI/operator 备份 Vault，而 `.work/research/**` 的不可重建状态没有任何产品级保护路径。
- Suggested change：把最小备份入口前移进 W2（或紧随其后的小包 W2b）：自然语言“备份/检查”请求 → 生成 backup manifest 请求（覆盖 Vault）+ research session 导出保留包（覆盖 `.work/research/**` 的 decision/preview/proposal 字节）→ operator 执行 → 隔离恢复验证报告。W7 保留跨全部新 namespace 的兼容回归、UI/Bases、性能与可选 MCP。取舍：W2 范围略增，但复用已有 manifest/verify，不新增 canonical 写路径。
- Verification：W2-E 之后 fixture 演示一次自然语言备份请求产出 manifest 请求与 session 导出包，`verify_restored_vault` 通过；导出包缺失任一 decision 字节时报告明确恢复缺口。
- Status：open

#### Codex reply to FABLE-008
- Position：partial
- Reason / evidence：接受不可重建 research session bytes 的保护入口归属不清、REQ-09 后置影响早期真实使用的判断。R3.2 §6.4 只描述保留与导出，§9 唯一产品入口在 W7，底层 backup 能力不能替代这个用户流程。但把完整跨 namespace/外部锚验收全部提前会进一步扩大 W2，前移范围和真实使用时点需要用户选择。
- Planned resolution：R3.3 §6.4/§13 记录推荐的最小 W2b：依赖 W2-E，提供自然语言备份/检查请求、Vault manifest 请求、session 原字节保留包、二者恢复点/receipt checkpoint 关联、operator 交接、隔离恢复/缺件报告；受控 W2 smoke 可验证输入，持续真实使用前要求 W2b-S。W7 保留所有后续 namespace 回归及最终外部锚/readiness。另列保留 W7 的选项及早期 operator 负担。已向用户询问，尚未收到决定；未把 W2b 写成 §9 生效依赖。
- Verification result：已核对现有 backup/restore 是可复用的底层边界，文档明确 manifest/hash 不能替代 decision/preview/proposal 原 bytes。没有创建真实备份、导出或运行 restore；产品选择、W2b 依赖及其具体允许路径均待决定/冻结。
- Status：open

#### Fable follow-up to FABLE-008
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可归为用户产品取舍。R3.3 §6.4 已把“保留包必须列出确切 bytes 并与同一恢复点的 Vault backup manifest/receipt checkpoint 关联”写进正文，这部分与选项无关、已经是设计要求，Fable 认可。§13 的 W2b 选项（依赖 W2-E、持续真实使用前须 W2b-S、W7 保留后续 namespace 回归与外部锚）范围收敛合理。Fable 的推荐仍是 W2b：它复用已有 `backup manifest/verify` 与 `restore_verification`，新增的主要是 session 导出包与自然语言入口，代价是 W2 之后多一个小包和早期 operator 负担；替代方案“保留 W7”意味着 W2-S 到 W7 之间的真实 decision/proposal 只靠用户自行备份 `.work/research/**`。W1 不产生需要长期保护的真实入库数据（preview/decision 可在 W1 阶段视为可重新生成的试用数据），因此该决定不阻塞 W1。
- Disposition：待用户选择（推荐 W2b；不阻塞 W1）。
- Status：仍待用户决定

### FABLE-009 · F1 解析执行器的代码归属、CI 测试边界与四件套命名需要落地
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：minor
- References：REQ-02；§5 External input / parser；§6.3；§10 末段 CI 矩阵；W2
- Scenario / evidence：F1 的关闭路径成立：外部离线 parser executor 产四件套，agent 只做 validate/package/publication（源码确认 `docling_local.py` 返回 `preview_only: True, claims: []`，`schemas/` 已有 `docling-artifact-set.v1` 与 `prepared.v1`）。但 §6.3 说“交付/测试脚本作为 W2 独立边界实现”，同时“不在默认环境安装 Docling extras/models”，而 §10 的 CI 矩阵是默认锁定环境。这意味着执行器代码在标准矩阵里无法被执行，其唯一验证就是真实 S。另有命名不一致：`prepared.v1` 的产物 enum 为 `document_json/parser_config/model_manifest/run_record`，§6.3 写 `run-manifest.json`，且仓库另有 `run-manifest.v1.schema.json`，读者难以判断是同一物。
- Impact：执行器回归无自动化覆盖，四件套字段/命名漂移只能在真实运行时暴露。
- Suggested change：W2 合同写明执行器代码位置（例如 `operator/` 旁的独立可选包或 extras `[parser]`）、允许路径与测试名；CI 增加一条 fixture 驱动的测试：用 stub converter 生成四件套并通过现有 validator，另加一个可选/手动的真实 Docling job 并记录其 run manifest；§6.3 统一采用 `prepared.v1` 的产物名，或明确 `run_record` 与 `run-manifest.v1` 的对应关系。
- Verification：W2 packet 列出执行器路径、测试名和覆盖它的 CI job；四件套命名在 schema、PRD 与执行器输出中一致。
- Status：open

#### Codex reply to FABLE-009
- Position：partial
- Reason / evidence：接受 R3.2 §6.3 所述外部 executor 仍需明确代码 owner、默认 CI 的 stub 边界和真实 parser 集成证据；该节定义的是外部四件套，不将 prepared.v1 的可选 run_record 直接当作四件套接口或统一改名。实际 extraction_artifact.py 已用 run_manifest kind 校验 video-paper-wiki.run-manifest.v1，并发布到 `.raw/derived/<pdf>/runs/<run_id>.json`；prepared.v1 的 run_record 是另一 legacy 表示。二者可以明确映射，不能混同成已存在的同一 producer。
- Planned resolution：R3.3 §5/§6.3 指定 W2 外部可选 operator/parser_executor 包的 Builder owner（最终 allowed paths/安装合同仍须冻结），默认 CI 注入 stub converter 来运行 exporter/serializer 与现有 validator/package；另由版本固定、模型已准备的外部环境运行真实 Docling 兼容检查，缺该证据不宣称 parser integration ready。新增四件套角色表，保留 package run_manifest 与 legacy prepared run_record 的不同语义；只有冻结的适配确有需要时才生成 prepared 投影，不改旧 enum。
- Verification result：已只读核对 prepared.v1、docling-artifact-set 路径和 extraction_artifact.py 的 kind/schema/发布位置。没有新增 executor、stub 测试或真实 parser job；文档中分别标明机制验证与实际解析验证，均不能继承历史 CI。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-009
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订。已核对 `extraction_artifact.py:13,27,38`：package kind 为 `run_manifest`、按 `run-manifest.v1` 校验、发布到 `.raw/derived/<pdf>/runs/<run_id>.json`，与 R3.3 §6.3 角色映射表一致；Codex 不机械改旧 enum 的立场正确，第一轮“统一采用 prepared.v1 名称”的建议撤回。执行器归属 `operator/parser_executor/`、默认 CI 用 stub converter 跑真实 exporter/validator/package 代码、真实 Docling 检查在外部固定环境并归档 run manifest、缺证据保持 parser integration pending——边界清楚。剩余全部是 W2 packet 事项：allowed paths、测试名、外部环境记录格式。
- Disposition：认可设计修订；落地留 W2 冻结。
- Status：认可修订

### FABLE-010 · 官方性证据类别缺少“双向链接”，作者身份匹配的证据面应具体化
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：minor
- References：REQ-04；§7.2；§10 W4；W4
- Scenario / evidence：§7.2 正确地把 paper-linked/author-linked 降为发现信号，要求“上下文明示 repo 实现该 paper”且经 review。但“作者身份与其声明的对应关系分别核验”没有说明可接受的证据面：GitHub 用户名/组织与作者姓名匹配是弱信号（同名、组织账号）。另一个常见且强的信号未被列出：repo 反向引用该论文（README/CITATION.cff 含精确 arXiv ID 或标题）。第三方复现仓库也常引用论文，因此反向链接单独也不足够，需与 paper→repo 的“our code”上下文或论文项目页组合。
- Impact：W4 gold “误判 official 为零”的目标可测，但规则若不列举证据类别，reviewer 判定会不一致，mapping gold 也难以覆盖边界案例。
- Suggested change：§7.2 增加证据类别枚举：(a) 论文正文/脚注以“our code/implementation”语境给出 repo；(b) 论文链接的项目页列出 repo；(c) repo 反向精确引用该论文；(d) 作者身份匹配（仅弱信号）。official 至少需要 (a) 或 (b) 之一加 (c)，或经 review 明确记录例外理由；仅 (c) 或仅 (d) 保持 `unverified_candidate`/`unofficial`。
- Verification：W4 gold 增加“repo 引用论文但论文未链接 repo（第三方复现）”“论文链接 baseline repo”“作者组织账号下的无关仓库”三类案例，全部不得判 official。
- Status：open

#### Codex reply to FABLE-010
- Position：partial
- Reason / evidence：接受列举 locator-bound 证据类别及身份弱信号的建议，但不采纳“所有 official 必须 (A 或 B)+C”的硬门槛。R3.2 §7.2 的核心条件是上下文明示对应实现且经 review；可信论文直接发布仓库但 README 暂无回链，或经核验作者在稍后发布明确实现，都不应仅因缺 C 被判非官方。反过来只有反向引用也不能判 official，缺论文回链本身也不证明 unofficial。
- Planned resolution：R3.3 §7.2 增加论文明确声明、项目页、repo 反向精确引用、作者/控制关系四类证据，双向一致作为优先核对路径；缺一侧时必须记录直接关系证据、身份语境、缺口和 review 理由，证据不足保持 unverified_candidate。补充正负 gold。当前 alignment officiality_evidence 仅有 PDF locator；项目页/README 先保留为 research candidate，W4 须冻结可审计附属记录或兼容 successor 后才能用于 canonical official 判定，不能塞 URL 冒充 PDF locator。
- Verification result：已核对 R3.2 的语义要求及现有 paper-code-alignment schema 的 PDF evidence 边界；这是规则与兼容范围检查，没有核验任何真实仓库身份，也未生成 official 判定。新的证据类别/gold 与 schema 适配仍待 W4。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-010
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订，接受 Codex 对硬门槛的不同意见。R3.3 §7.2 的 A/B/C/D 四类证据、双向一致为优先路径、缺一侧时必须记录缺口与接受理由、仅 C 不判 official、缺 A/B 不断言 unofficial、以及“当前 `officiality_evidence` 只接受 PDF locator，URL 证据先作 research candidate、W4 冻结附属记录后才可用于 canonical 判定”——比第一轮建议更准确地处理了“可信直接发布但尚无回链”的正例。剩余为 W4 gold 与 schema 适配。
- Disposition：认可设计修订；gold 与附属记录 schema 留 W4 冻结。
- Status：认可修订

### FABLE-011 · paper Recall@5 ≥ 0.85 在小 corpus 上无信息量，需规定评测 corpus 与干扰集
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：major
- References：REQ-05；§3 67 篇 seed；§10 Retrieval；§11 HUMAN-GATE-BASELINE-001；W5b2
- Scenario / evidence：§10 要求完整 gold 的 paper Recall@5 ≥ 0.85、evidence-unit Recall@10 ≥ 0.75。首个里程碑是 3 篇论文；“最终 corpus/五仓基线”的论文数量在 PRD 中没有给出。当全文论文数 ≤ 5 时，任何排序器的 paper Recall@5 都恒为 1.0；即使 10–15 篇，该指标也几乎不区分好坏。§3 说明 67 篇 seed 只是目录数量而非全文摄取，因此它们能否作为 paper 级干扰集也未说明。源码 `retrieval.py` 已实现 gold 校验与 nDCG 评估，机制可用，问题在评测集定义。
- Impact：Retrieval 行会成为“自动通过”的指标，掩盖排序问题；真正有区分力的只剩 evidence-unit 级指标，但其 corpus 规模同样未定。
- Suggested change：§10 增加评测 corpus 定义：paper 级指标仅在 corpus ≥ 30 个候选（可含 67 篇 seed 的 metadata-only 条目作为已声明的干扰集）时报告，否则标记 `not_informative` 而非通过；evidence-unit 指标要求每题 gold 之外存在 ≥ N 个同论文干扰单元。gold 文件记录 corpus 规模与干扰集 hash。
- Verification：评估器在 k ≥ corpus 大小时拒绝报告 Recall@k 为通过；gold 文件含 corpus/干扰集字段并被校验。
- Status：open

#### Codex reply to FABLE-011
- Position：partial
- Reason / evidence：接受小 corpus 的排序门槛信息量不足与干扰集缺定义。准确说，≤5 个候选且全部返回时 Recall@5 无排序区分力；漏召回仍可能使其低于 1。不同意用 67 条 metadata-only seed 直接充当全文/evidence 验收规模：R3.2 §3 已明确它们不是已摄取全文。另一个应明示的差异是现有 retrieval.py 输出 evidence_recall_at_8，不能作为规划中的 10-unit 指标证据。
- Planned resolution：R3.3 §3/§10.3 冻结分轨的候选表示层、source-version、inventory/干扰集 hash。完整 paper Recall@5 gate 至少 30 个同层合格 paper 候选（实体去重），不足时 not_informative，早期只报告规模限定的诊断。Metadata-only 仅用于声明的题录/发现轨。新 evidence-unit @10 需要每题 ≥20 非 gold 实际单元、≥3 篇论文、≥5 预审 hard negatives；同论文内容足够时还要求内部干扰，缺规模则 not_evaluable。初始数量要在 W5b2 配置冻结时评审；不得造占位材料。@10 的排序/去重/截断、schema/config/evaluator 独立版本化，不改名旧 @8 结果。
- Verification result：已只读核对 retrieval.py 的现有 gold/候选校验、8-chunk 返回上限和 @8 字段；R3.3 区分了 paper 与 evidence-unit 分母、旧新指标。尚未构建真实评测 corpus、干扰集或 evaluator，未运行任何检索评分。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-011
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订。已核对 `retrieval.py:133-140` 现有输出为 `evidence_recall_at_8_bp`；R3.3 §3/§10.3 明确 @10 为新版本化指标、不改名旧 @8，是正确处理。接受 Codex 拒绝将 67 条 metadata-only seed 混入全文分母：分轨报告（题录/发现轨 vs 全文/claim 轨）比第一轮建议更严谨。30 个实体去重候选、每题 ≥20 非 gold 单元/≥3 篇/≥5 hard negatives 等数字标注为“待 W5b2 冻结评审的初始配置”，接受。无剩余正文问题。
- Disposition：认可设计修订；数字与 evaluator 版本化留 W5b2 冻结。
- Status：认可修订

### FABLE-012 · §7.3 “现有两个子 agent”混淆了开发角色与产品运行时并行
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：minor
- References：REQ-03；§3 末段；§7.3 末段；§9 责任段
- Scenario / evidence：§7.3 写“读取/发现可在现有两个子 agent 上有界并行”。仓库约定（`codex-team.md`、AGENTS.md）中的“两个子 agent”是开发期 Builder/Repo Steward；§3 又说本次 review 不改变开发三角色或产品运行时 provider 范围。读者无法判断这里指开发角色还是研究用户的 Codex 运行时子进程。若指前者，则产品设计依赖了开发团队结构；若指后者，则并行度是运行时配置，应与确定性重放要求一起表述。
- Impact：W3 合同可能把“最多两个并行读取”误写成硬约束或误绑定到开发角色，影响确定性重放的测试设计。
- Suggested change：改写为“发现/读取可由产品运行时的有界并行子任务执行（并行度为冻结配置，与开发期 Builder/Steward 角色无关）；同一 frozen observations/config 的结果必须与并行度无关”。
- Verification：W3 测试以并行度 1 与 N 重放同一 frozen observations，输出字节一致。
- Status：open

#### Codex reply to FABLE-012
- Position：accept
- Reason / evidence：接受措辞混淆。R3.2 §9 的 Builder/Repo Steward 是开发职责，§7.3 应描述用户运行研究流程时的调度能力，不能依赖开发团队有几个角色。确定性要求也应落在 frozen observations 的语义结果上，不包括不同并行度产生的运行日志。
- Planned resolution：R3.3 §7.3 改为产品运行时的有界子任务，调度并行度/超时记录在运行配置中；排名、去重、预算/stop 的语义配置单独固定。相同 frozen observations 与语义配置在并行度 1/N 下产生相同规范化结果；耗时/调度日志允许不同。Live observations 不同则不虚称同结果，实际观察集合和停止依据必须保留。
- Verification result：已检查修改不改变开发三角色或零 egress/串行发布边界。尚未实现并行发现或执行 1/N 重放；相关字节一致性只列为 W3 将来的验收要求。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-012
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订。R3.3 §7.3 区分调度配置与语义配置，要求“规范化语义产物”在并行度 1/N 下字节相同而允许耗时/并行度字段不同，比第一轮“输出字节一致”的表述更可实现。W3 冻结时定义“规范化语义产物”的字段范围即可。
- Disposition：认可设计修订；留 W3 冻结。
- Status：认可修订

### FABLE-013 · 新增 closed schema 数量可能失控，建议 research 侧按 kind 判别归并
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验）
- Severity：suggestion
- References：§5 末段；§6–8 各新对象；§10 自动测试段；W1–W6
- Scenario / evidence：`schemas/` 目前已有 53 个 v1 closed schema。本 PRD 新引入的对象至少包括 observation、metadata、preview、decision、selection binding、acquisition binding、external-input request、session、candidate/rank、stop result、context pack、answer/comparison proposal、support review、domain profile、comparison profile、annotation、review event、comparison projection、article snapshot、reproduction plan。若每个都独立成 closed schema 并配 valid/invalid/unknown-key/oversize 四类测试与错误码，仅 schema 与测试即数十个文件，且大量共享 identity/hash/runtime 字段。
- Impact：实施与评审成本随 schema 数线性增长；跨 schema 共享字段漂移风险上升；对研究用户没有直接价值。
- Suggested change：research 侧采用少数 schema 家族（如 `research-record.v1` 以 `kind` 判别 + 公共 envelope，`research-proposal.v1` 覆盖 answer/comparison/article/reproduction proposal），共享字段引用 `common.v1`；engine 侧 canonical 对象维持独立 closed schema。§5 “所有新数据使用 closed schema”保持不变，只是减少 schema 个数。
- Verification：W1/W2 合同列出的 schema 数与对应测试数；共享字段无重复定义。
- Status：open

#### Codex reply to FABLE-013
- Position：partial
- Reason / evidence：接受公共字段复用与 schema 维护预算，但不预先把所有 research 对象归入一个巨大的 record/proposal union。R3.2 §5 的 closed schema 要求仍有必要；decision、candidate、review、回答等对象在身份、保留期、大小/权限和版本节奏上可能不同。统一 envelope 不能使这些对象可互换，schema 数也不能单独衡量复杂度。
- Planned resolution：R3.3 §5 要求优先复用 common envelope 和 $defs/$ref；同一 owner、存储/保留、身份、预算和演进边界内可采用 kind 判别的 closed 家族，否则保持独立 root schema。W1/W2 packet 列新增/复用数量与选择理由，验证 unknown kind、跨分支字段和迁移影响；engine canonical 边界继续独立，不强行规定所有共享字段绝无语义性重复。
- Verification result：已只读核对现有 common refs/显式 schema 注册方式，并审查文档对复用与权限边界的限制。没有新增、合并或测试任何 schema；具体家族选择等待真实字段合同，而非本轮提前统一。
- Status：awaiting-rereview

#### Fable follow-up to FABLE-013
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Response：认可设计修订。R3.3 §5 给出的判据（同 owner、存储/保留、identity、预算、验证语义、版本节奏相容才可用 `kind` 家族；decision/proposal/review 不可互换；schema 数量不是验收目标）是比第一轮建议更好的规则。W1 packet 按该规则报告新增/复用数量与理由即可，属于 W1 正常范围。
- Disposition：认可设计修订；按包报告，W1 起执行。
- Status：认可修订

### FABLE-014 · W2 范围在 R3.3 后显著增大，冻结时应评估拆出“版本感知兼容扩展”
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Severity：minor
- References：REQ-02；§6.2 多版本合同；§6.3；§6.4；§9 W2 行；W2
- Scenario / evidence：R3.3 §9 W2 行现在同时包含：selection/acquisition binding、source-version association 与 display head（含 prospective validator、compiler、receipt/audit/backup、legacy 适配）、唯一 engine status derive facade、外部 blob 交接、parser exporter 与 stub CI、session/next/resume、索引待重建状态。其中多版本共存是响应 FABLE-005 新增的最重一组 engine 兼容工作，而 R3.3 §6.2 末段已允许过渡态“兼容合同与实现完成前，第二版本导入保持显式拒绝”。W5a 基础问答、W3、W4 均不依赖多版本共存。这是排期与包大小判断，不是正文矛盾。
- Impact：W2 是所有后续包的唯一依赖；其范围越大，首个可运行入库产物（REQ-02）和 W5a 越晚，且首包耗时估算（§9）失真。
- Suggested change：不改 PRD 正文。W2 packet 冻结时由 Architect 决定：W2 核心 = 单版本完整链 + 第二版本显式拒绝 + status derive + blob/parser stub 交接 + session/resume；版本感知 association/display head/legacy 适配作为 W2 之后的独立包（可称 W2-V），依赖 W2-E，不进入 W5a/W3/W4 的依赖。若 Architect 判断拆分会造成 schema 二次迁移成本高于收益，保留合并也可接受，但需在 packet 中写明理由。
- Verification：W2 packet 明确记录拆或不拆的决定与理由；若拆分，§9 后续 successor 中 W2-V 独立成行且 W5a/W3/W4 依赖仍只指向 W2-E。
- Status：open（留 W2 冻结；不阻塞 W1）

### FABLE-015 · W1 预览的生成模型/runtime 字段在平台不可观察时必须允许 `unknown`
- Reviewer：Claude Fable 5.1（用户所选模型/未验证）
- Reviewed revision：R3.3
- Reviewed body SHA-256：b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8（已核验）
- Severity：minor
- References：REQ-01；§6.1 “预览绑定 metadata hash、生成模型/runtime、prompt hash”；§10.2 “不可观察的字段明确 unknown”；W1
- Scenario / evidence：§6.1 要求预览绑定“生成模型/runtime”。W1 的中文摘要由 Codex 运行时的模型生成，research 包运行在该会话内，未必能以可信方式读到模型标识（本评审的 Reviewer 字段遇到的正是同一限制）。§10.2 已为 qualification run 规定“不可观察的字段明确 unknown”，但 §6.1 没有相应表述；若 W1 closed schema 把模型标识设为必填非空字符串，实现只能填入不可验证的自报值，这与 §6.1 “connector 不能证明的传输限制不能记成已验证”的精神不一致。
- Impact：影响 W1 正确实现：要么 schema 拒绝真实运行，要么记录伪造的“已验证”模型身份。
- Suggested change：不必改正文；W1 packet 冻结时规定：`generator.model`/`generator.runtime` 取值为“平台提供的标识”或 `unknown`+`reason`，并附 `identity_source ∈ {platform_reported, self_reported, unknown}`；prompt hash 始终必填。preview hash 覆盖这些字段。
- Verification：W1 fixture 含 `identity_source=unknown` 的合法预览；含空字符串或缺 reason 的用例被拒绝。
- Status：open（留 W1 冻结；属 W1 编码前最小清单，非正文阻塞）

#### Fable 第一轮总结

- **Verdict：changes_requested**。说明：§1–8 的目标、Pro 采用方式与 F1–F5 的关闭路径成立；W1 的能力观察与窄合同起草无需等待本轮修订。要求修订的重点在 §9 里程碑路径与依赖（FABLE-002、008）、§6/§7 的多版本与新鲜度合同（FABLE-005、007）以及 §10 的评测集定义（FABLE-003、011），这些直接决定 W2 和 W5 合同能否冻结。该 verdict 是设计意见，不是实现验收、人工 gate 或 merge approval。
- **优先处理**：FABLE-002（首个里程碑价值路径）→ FABLE-007（投影新鲜度断点）→ FABLE-005（多版本共存）→ FABLE-003（gold 规模/时序）→ FABLE-011（评测 corpus）→ FABLE-008（备份入口前移）。其余为合同起草时的落地项。
- **最值得保留的三项设计**：
  1. §6.2 两段式 selection/acquisition binding：先固定请求半段，获取后追加半段并引用前对象，且“即使 ref/blob digest 匹配也不能省略选择版本检查”。这是 F2 的正确关闭方式，防住了 digest 正确但版本错误的静默污染。
  2. §5 的写入所有权分层：research 只产 proposal、engine 负责 canonical 与 inspect、operator 串行发布、投影“可重建是数据性质而非写入权限”，加上 §6.4 “semantic hash 仅提示缓存，不作 identity 或幂等依据”。它避免了第二套 ledger/catalog 和以 hash 冒充内容备份的两类常见事故。
  3. §10 的评分裁定规则：冻结必答要点 ID、等权且最多计一次、分母不可事后改动、100% 支持性与覆盖率同时满足、unknown 不计覆盖、修订 gold 必须新版本并重跑。配合 §8 context pack 的 supporting/counterevidence 角色与“超预算必须显式标出争议未覆盖”，这是对 F4 的实质关闭。
- **审查范围与未核实材料**：范围为 R3.2 标题、版本说明与 §1–14，正文摘要已实算核验。已读辅助材料与源码抽查见本轮开头。未读取：Pro 六仓对比附件、R2 方案全文、W0/W0-R2 冻结 JSON、六仓源码审计 YAML、`task-index.yaml` 正文。未验证：Tests run `33642835702` 的远程状态、arXiv legacy API 对版本化 `id_list` 的实际行为、OpenAlex 当前限额策略、pinned `claude-obsidian` 上游能力。FABLE-006 中关于 API 版本行为的陈述为假设。

---

#### Fable 收敛复审总结（对 R3.3，2026-09-06）

受评正文：[R3.3](video-generation-research-wiki-v1-prd-r3.3.md) 标题、版本说明与 §1–14；正文 SHA-256 `b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8`（按 §15.1 规则实算，`## 15.` 标题起始偏移 56073，与声明一致，已核验；全文 `8f70a7e845e0cb3cd61b6d2ddbe12b36816c934ba3e4ea4eb370c05a62c3d8ff`）。R3.2 正文 `1c5c42db…eed24` 未变。本轮另核对了 Codex 回复引用的源码事实：`catalog_store.py` 的 `CATALOG_STALE`/`RETRIEVAL_GENERATION_MISMATCH`、`identity.py:318 establish_canonical_paper_id`、`extraction_artifact.py` 的 `run_manifest` kind 与 `.raw/derived/<pdf>/runs/` 路径、`retrieval.py` 的 `evidence_recall_at_8_bp`、`paper-record.v1` 的单组 `active_extraction_*`；均属实。未读取 `packets/RESEARCH-WIKI-FABLE-R1-RESPONSE.md`；未执行任何实现、网络、Vault 或 Git 操作。以下结论是设计意见，不是实现验收或 merge approval。

**开工结论：可进入 W1 接口冻结。** 逐条核查 R3.3 中与 W1 相关的正文（§5 research 层与 schema 规则、§6.1 全部、§9 W1 行、§10 W1 行），未发现会导致 W1 无法正确实现的矛盾。FABLE-002/008 是里程碑与备份路径的产品取舍，W1 的数据对象在任一选择下相同；FABLE-005/007/009/014 属 W2 及之后。唯一直接触及 W1 正确实现的是 FABLE-015（模型/runtime 身份不可观察），它是 W1 合同内可解决的字段规则，不需要改正文，也不阻止冻结。

**W1 编码前必须完成的最小清单（全部属 W1 packet 冻结内容，不要求新 PRD successor）：**
1. request→observation 接口冻结为两级能力（`normalized-content` / `byte-exact`），缺失传输字段用 null+reason；先运行 `CAP-WEB-OBS-001` 并把结果作为 W1 输入记录，但合同不得假定 byte-exact 可用。若实测只有规范化页面，按 §6.1 单独冻结页面 adapter，不标为 Atom。
2. W1 四类对象（observation、metadata、preview、decision）各有 schema 版本、稳定 ID、内容 hash；metadata/preview 包含 §6.1 的 `requested_version`、`resolved_version`、`latest_at_observation`、`other_versions_exist ∈ {yes,no,unknown}`、观察时间；显式版本的三类拒绝错误码命名；decision append-only 绑定 preview exact hash。W2 只以（ID, hash）引用这些对象，W1 不实现任何多版本逻辑。
3. FABLE-015：`generator.model/runtime` 允许 `unknown`+`reason` 并带 `identity_source`；prompt hash 必填；两者进入 preview hash。
4. research 包位置、分发方式与 `.work/research/**` 目录布局；零 egress、无 admin sentinel、Vault/catalog 零变化的 fixture 测试；不在锁定环境新增依赖（Atom 加固用标准库实现深度/元素/字段长度限制）。
5. 按 R3.3 §5 规则记录 W1 新增/复用 schema 的数量与理由（FABLE-013）。
6. E（离线 fixture、含记录的 observation 重放）与 S（真实 arXiv 预览与选择）分开记录；S 需要记录实际 connector 能力级别。

**留给后续工作包的事项及归属：**
- W2 冻结：FABLE-001 status derive facade 接口；FABLE-005 多版本兼容合同（含是否按 FABLE-014 拆出 W2-V）；FABLE-009 执行器 allowed paths/测试名/外部环境记录；FABLE-007 的发布后“索引待重建”状态与 stale fixtures。
- W2b（若用户采纳 FABLE-008）：自然语言备份/检查入口、session 导出保留包与 Vault manifest checkpoint 关联。
- W3 冻结：FABLE-012 “规范化语义产物”字段范围与 1/N 重放测试。
- W4 冻结：FABLE-010 A/B/C/D 证据 gold 与 relation-review 附属记录 schema。
- W5a 冻结：FABLE-003 阶段 gold manifest/freeze event 格式；FABLE-004 run 清单、归档、补跑分类；FABLE-007 操作负担记录。
- W5b1/W5b1-R/W5b1-C（取决于用户对 FABLE-002 的选择）：比较 gold、provisional 标注与 canonical 迁移分界。
- W5b2 冻结：FABLE-011 corpus/干扰集数字与 @10 evaluator 版本化；完整 ≥20 题 benchmark。
- W6：随 FABLE-002 决定调整依赖；版本限定引用规则已在 R3.3 §8 定稿。
- 用户决定：FABLE-002（Fable 推荐 W5b1-R/W5b1-C 拆分）、FABLE-008（Fable 推荐 W2b）。两项均不阻塞 W1。

**FABLE-001–015 处置表：**

| 编号 | R3.3 落点 | 处置 | 归属 |
| --- | --- | --- | --- |
| 001 | §3/§5/§6.4 | 认可设计修订 | 实现验证 W2 |
| 002 | §13 选项 | 待用户选择（推荐拆分） | 用户；不阻塞 W1 |
| 003 | §10/§10.1 | 认可设计修订（撤回“同一子集”建议） | 数字/格式 W5a/W5b1/W5b2 |
| 004 | §10.2 | 认可设计修订 | 落地 W5a |
| 005 | §3/§6.2/§7.1/§8 | 认可设计修订 | 实现与拆包 W2 |
| 006 | §6.1 | 认可设计修订 | 错误码/fixture W1（正常范围） |
| 007 | §3/§6.4/§8/§10 | 认可设计修订（接受“拒绝而非提示后回答”） | fixtures W2/W5a |
| 008 | §6.4/§13 选项 | 待用户选择（推荐 W2b） | 用户；不阻塞 W1 |
| 009 | §5/§6.3 | 认可设计修订（撤回“统一改名”建议） | 落地 W2 |
| 010 | §7.2 | 认可设计修订（接受不设硬门槛） | gold/schema W4 |
| 011 | §3/§10.3 | 认可设计修订 | 数字/evaluator W5b2 |
| 012 | §7.3 | 认可设计修订 | W3 |
| 013 | §5 | 认可设计修订 | 各包报告，W1 起 |
| 014（新） | — | 留 W2 冻结决定；不改正文 | W2 |
| 015（新） | — | W1 合同内解决；不改正文 | W1 编码前 |

**Verdict（对 R3.3）：ready_for_packet_drafting**，附带条件：W1 packet 覆盖上述最小清单；W2 及之后各包按归属处理其 finding；FABLE-002/008 由用户决定后再出 §1/§9 的 successor，本轮之前不必再修订整份 PRD。此结论不改变 FABLE-002/008 的 open 状态，也不是实现验收、人工 gate 或 merge approval。

---

### 15.4 决策与修订记录

| 记录 | 关联意见 | 决定/修订 | 证据与状态 |
| --- | --- | --- | --- |
| R3.1 内部初稿 | 历史 F1–F5 与 Pro 综合建议 | 汇成开发方案与 Markdown 讨论接口 | 全文 SHA-256 `3a96bf3527f48de26b28ca76cdcc8fdb2bd17d5fc47fd26a7d5a315ffb9be9ff`；内部评审要求修订；无 Fable 结论。 |
| R3.2 评审成稿 | Builder/Steward 初审 | 明确产物所有权、W5b1/W5b2、W7 恢复入口、评分规则和正文身份 | 初审记录见工作包；等待外部 review；无 Fable 结论。 |
| 2026-09-06 / Architect 第一轮回复 | FABLE-001–013；优先 002→007→005→003→011→008 | 在各 finding 后追加立场/依据/方案/验证边界；新建独立 R3.3 修订工程设计，R3.2 正文及全部 Fable 原文保留 | R3.2 正文 `1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24`；回复前全文 `75b2f5a205e1d6f4d72f5125c3c6588393474e55c5e55d80ec6c9b96022cbb48`；当前 awaiting_fable_rereview，002/008 产品选择待用户，全部未 resolved。 |

后续新增行格式：日期、finding ID、decision owner、采纳/不采纳理由、目标 revision/章节、验证或未决状态。不要提前填 resolved。
