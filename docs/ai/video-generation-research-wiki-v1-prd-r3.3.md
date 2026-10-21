# Video Generation Research Wiki v1：开发方案与联合评审 PRD

版本：R3.3 · 日期：2026-09-06 · 状态：Fable 第一轮后的设计修订候选，待复审；FABLE-002/008 产品选择待用户决定。

本地工程基线：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`。本文是 R3.2 的独立 successor，响应 Fable 第一轮意见，不覆盖 R3.2 正文或讨论。Predecessor 正文 SHA-256 为 `1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24`；收到第一轮评论、尚未追加回复时的全文 SHA-256 为 `75b2f5a205e1d6f4d72f5125c3c6588393474e55c5e55d80ec6c9b96022cbb48`，已在本轮工作包先行记录。

本文仍是产品/架构设计，不是实现或合同冻结。Fable 对 R3.2 的 `changes_requested` 继续有效；本文没有获得 Fable follow-up 结论。§13 列出 FABLE-002/008 的具体选项；用户决定前，§1/§9 保留原里程碑与依赖，不把 Architect 的推荐当作已获采纳。统一讨论继续写在 [R3.2 的 §15.3](video-generation-research-wiki-v1-prd-r3.md)，本文件 §15 提供本轮正文身份和复审入口。

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

补充能力边界（FABLE-001/005/007/011）：十状态 ingest 流程是既有文档的推导规则，尚无统一 status 查询实现；W2 将新增 engine 侧唯一只读推导接口。现有 `establish_canonical_paper_id` / prospective validator 对同一 paper ID 的不同 PDF 绑定会拒绝，不能声称多版本共存已有支持。现有 `catalog_status/query_catalog` 已校验 live material 并拒绝 stale，待补的是研究层的新鲜度/覆盖提示与恢复动作。现有 retrieval evaluator 输出 `evidence_recall_at_8`；本文的 evidence-unit Recall@10 是待版本化实现的新指标。

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

新增职责（FABLE-001/005/009/013）：engine 拥有 ingest 状态证据推导、版本感知的 paper/source 关联与展示 head、generation 新鲜度/覆盖状态的唯一权威查询；research 只消费这些结果并计算用户动作。W2 外部 parser executor 拟置于独立可选 operator 包 `operator/parser_executor/`，Builder 负责其代码与 fixture 验证；该包不加入默认 agent 的 import/PATH，具体允许路径和安装合同须在 W2 packet 冻结。

Research 侧优先按权限和生命周期复用公共 envelope 与 `$defs/$ref`；只有 owner、存储/保留策略、identity、大小/预算、验证语义及版本节奏相容的对象，才可用 `kind` 判别的 closed schema 家族。每个分支仍封闭 unknown keys、identity/hash 与跨 kind 字段；不能为减少文件数把 decision、proposal、review/authority 混成可互换对象。Engine canonical 对象维持独立版本和审计边界。W1/W2 合同报告新增 schema、复用字段、跨 kind 拒绝案例及维护取舍，不把 schema 数量越少当成验收目标。

## 6. 输入、版本、解析与恢复合同

### 6.1 预览和网络观察

W1 首先运行 `CAP-WEB-OBS-001`，记录实际 connector 的规范化内容、URL、headers、redirect、raw bytes、DNS/IP 可见性。Observation 支持 `normalized-content` 和 `byte-exact`；缺失传输字段使用 null 与原因，不能编造。前者可用于预览/发现，后续 raw provenance 需要原始 bytes 或等价外部输入证据。

arXiv metadata 保存无版本实体 ID 和 resolved version、标题、作者、日期、分类、摘要、来源与观察时间。预览绑定 metadata hash、生成模型/runtime、prompt hash；明确 abstract-only 和 extracted/inferred/unknown。接受合法新旧 ID/版本及 abs URL，拒绝混淆 host/userinfo/额外 query。默认 24 小时缓存；legacy API 请求按官方规则串行限速，W1 初始下限 3 秒。初始请求预算为单次预览 1 request、20 秒、1 MiB；connector 不能证明的传输限制不能记成已验证。Atom parser 禁 DTD/外部实体并限制深度、元素与字段长度。若只能使用规范化官方页面，单独冻结页面 adapter，不能标为 Atom 响应。

显式版本规则（FABLE-006）：输入带 `vN` 时，metadata/摘要及预览必须证明来自该版本；服务只提供其他版本或不能确认版本时拒绝构成可入库预览，并返回区分“版本不匹配/版本不可服务/能力不足”的稳定错误（具体名称在 W1 冻结）。不得悄悄回退最新版。无版本请求记录 `latest_at_observation`、resolved version、观察时间与其他版本存在性（是/否/未知）；只有 adapter 有明确证据时才宣称“观察时刻最新”。仅能证实一个版本时，显示 `latest_unknown`，需用户显式选择该已知版本后另记 decision。缓存键区分显式版本和最新观察策略，以上字段进入 metadata/preview 摘要。这里规定行为，不声称已验证 arXiv API 或页面对版本请求的实际响应。

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

同一论文的多版本合同（FABLE-005）由 W2 engine 兼容扩展负责，不能只在 research 新增列表来绕过旧身份校验：

- paper 实体 ID 继续去版本；另有不可变 source-version association 绑定实体、明确 arXiv 版本、取得 observation、PDF hash、既有 source-ledger ID、解析产物和 capture/publication receipt。同版本同 bytes 精确复用；同版本不同 bytes 先标冲突，不自动覆盖。不同版本若 bytes 相同，可以共用内容寻址的 raw/source bytes，但各自保留版本观察与 association，不能为“每版本一条”伪造重复 source identity。
- 用户对“当前展示版本”作 append-only decision；operator 经现有 transaction 发布唯一 display head。现有 paper-record 的 source_ids 汇集所绑定来源；display head 与 active_extraction_path/sha256 的兼容镜像在同一事务保持一致，版本感知 validator 检查唯一权威关系，不允许 caller 分别选择。新版本入库不自动切换展示或撤销旧结论。没有新 head 的旧数据继续按 legacy 视图显示，并标版本未知/legacy，不推测 `v1`。
- 新版 Paper Page 列出所有已导入版本及当前展示决定；版本感知 compiler/query 消费 association/head/generation。W2 须同时冻结 v1→版本感知适配、prospective validator、plan/prepare、compiler、receipt/audit/backup 和旧客户端的拒绝/只读兼容策略，不能留下两套“当前版本”权威，也不修改旧 v1 closed schema 的身份语义。
- 新版本 claim 不自动 supersede 或 retire 旧 claim。相同实体与规范化文本仍按现有算法确定 claim ID，不因版本标签强制改 ID；不同文本生成各自身份。同一 claim 的来源关联保留具体版本与 locator；若 canonical evidence fingerprint/head 发生变化，按现有失效/重新 review 规则处理，不继承旧 accepted。展示版本切换只改变视图，不等于 assessment 决定。
- 答案、矩阵、文章行内引用与 bibliography 必须解析到明确版本、PDF/产物 hash 和 locator；跨版本比较先核对条件，未证明一致时为 `not_comparable`。旧版本本身不等于 stale：只有其证据或所声明的 current view 绑定失效时才改变新鲜度状态。

W2-E 增加 v1/v2 共存、同版本异 bytes 冲突、同 bytes 多版本关联、展示切换/回退、旧客户端和 assessment 失效案例。在该兼容合同与实现完成前，第二版本导入保持显式拒绝，不用旧单 PDF 接口冒充支持。

### 6.3 外部 blob 与解析执行器：关闭 F1

外部 input operator 按请求把 PDF 安装到 prepare 可读的 `.work/blobs/<sha256>`；研究层只校验和消费，不恢复 agent 的 ingest put。交接规定 hash、PDF 类型/页数/大小、原子安装、同字节复用、异字节冲突拒绝和路径安全；任何缺失输入都显示 awaiting_external_input。

外部离线 parser executor 使用固定 Docling/core 版本与已准备的模型，绑定 captured PDF hash，生成 `document.json`、`parser-config.json`、`model-manifest.json`、`run-manifest.json` 四件套。run 记录真实版本、配置/模型摘要、输入输出摘要和成功/失败结果；失败不能伪造成功产物。agent 默认锁定环境只调用既有 artifact validator/package/publication。Parser executor 的交付/测试脚本作为 W2 独立边界实现，不由本次方案交付安装运行。

四件套角色映射（FABLE-009）如下。文件 basename 是外部交接命名，不是任意改动既有 enum 的授权：

| 外部交接文件 | prepared.v1 artifact kind | docling-artifact-set/package kind | 发布后的既有角色 |
| --- | --- | --- | --- |
| `document.json` | `document_json` | `document_json` | 解析 document bytes |
| `parser-config.json` | `parser_config` | `parser_config` | parser 配置 bytes |
| `model-manifest.json` | `model_manifest` | `model_manifest` | 模型 manifest bytes |
| `run-manifest.json` | `run_record` | `run_manifest` | `video-paper-wiki.run-manifest.v1`，保存到 `.raw/derived/<pdf>/runs/<run_id>.json` |

上述 prepared 列仅列出 legacy 名称，不表示四件套 exporter 以 prepared.v1 作为输入合同。旧 `prepared.v1` 的 run_record 可选语义保留；实际 `docling-artifact-set.v1`/package 的运行记录 kind 仍为必需的 `run_manifest`，其 bytes 必须通过 run-manifest.v1 校验。新完整解析流程不能以旧 schema 通过三件套就宣布 parsed。只有 W2 明确需要生成 prepared 兼容投影时，adapter 才按冻结规则映射到可选 run_record；不能机械重命名既有 enum 或把缺失 run manifest 当作成功。

默认锁定 CI 通过 stub converter 输出固定 document 来执行真实 exporter/validator/package 代码，覆盖角色映射、失败/缺件、错 hash、离线 sentinel；它证明交接机制，不证明 Docling 解析质量。另有预先准备且版本固定的外部离线环境运行真实 Docling 兼容检查，归档实际 run manifest 与样本输出；可用专门手动 job 或等价本地外部证据，不进入默认 agent 矩阵。该真实检查是声明 parser 集成可用的必要证据，未运行则保持 parser integration pending。具体测试名、job/执行环境和 allowed paths 在 W2 packet 冻结，本轮没有新增或执行这些测试。

W2 映射 section/figure/table/equation 到 existing PDF locator：page、block ref、bbox 或 charspan、artifact/text hash。代码证据使用 repo、full commit、path、line、blob hash；可选 AST 只补充 symbol 信息。只有简要标题预览时不进入 parsed 完成状态。

### 6.4 两阶段编译与可恢复状态

来源提取先输出 claim/entity/method/result/limitation proposal；随后做 alias/version/entity resolution 和 canonical compile。每次重放绑定 exact source、schema、compiler、pipeline、locator/assessment 输入。semantic hash 仅提示缓存/dirty，不作为 identity 或幂等依据。

沿用文档定义的 ingest 推导语义：`absent → planned → prepared → capture_inspected → captured → parsed → drafted → ingest_inspected → applied_provisional → verified`；这不是当前已存在的统一状态 API（FABLE-001）。W2 由 engine 新增唯一只读状态推导 facade，消费经验证的 plan/ref、inspection、artifact、operator result 和 receipt/audit snapshot，输出最后可证明状态、证据引用与不成立的前置条件。具体函数/CLI 名称和 closed 输出在 W2 冻结；research 不重实现 receipt/inspection 状态判定，只消费 engine 结果并结合用户 decision/外部请求计算 session next_action。

create capture 等 operator result；reuse 重新验证 retained sibling；parsed 等真实解析证据；verified 只指 ingest 完整性，不代表 claim 人工 accepted。失败追加观察，状态停在最后可证明步骤；publication preparation/inspection、ref 绑定和 capture disposition 使用正交字段。W2-E 必须覆盖每种状态、缺失/冲突证据、apply 后 audit 失败与 research mock engine 的 next_action，不维护可变 job database。

Session 的 next_action 消费 engine 状态/新鲜度结果，加上 research 自有 decision、模型请求和外部交接状态计算；publication verified 后若 catalog 尚未 current，应显示“已发布，等待 operator 重建索引”，不能写成“已可完整问答”。模型输出、用户 decision、preview、选中输入和模型 proposal 具有不可重建内容，活动 session 不可随意清理；缺少必需 bytes 时返回明确恢复缺口，不能仅凭 hash 自动补造。

保留包必须列出这些确切 bytes、依赖及 manifest，并与同一恢复点的 Vault backup manifest/receipt checkpoint 关联；投影/cache 可以删除重建，用户 notes 的独立所有权不变。最小产品入口是否前移到 W2b 是 FABLE-008 的待决项（§13）；在决定前不宣称已有一键保护能力。W7 保留全部新 namespace 和 session 导出的最终恢复验证职责，各生产者包不能延后其自身完整性要求。

## 7. 领域知识、官方代码与研究

### 7.1 视频领域和实验事实

Method/Model/ArchitectureComponent/TrainingRecipe/Dataset/Benchmark/InferenceRecipe/EvaluationMetric 先作为 typed concept。taxonomy v1 不原地扩写；任务、范式、backbone、component、training、inference、evaluation 的新词先规范化为提案，v2 需独立迁移与真实 review。

claim_kind 为 architecture/training/empirical_result/implementation/ablation/limitation/reproducibility/license/resource_requirement，与 assessment 和 freshness 正交。分类 proposal 绑定 claim text、evidence fingerprint、assessment head、domain profile hash；W2 只建议，W5b1 才通过 versioned annotation/review/head 和现有 transaction 发布。

Domain/comparison profile 是 immutable canonical bytes，由 transaction-published profile-head 选择 active version；agent/query caller 不能切换规则。Annotation、review event 与 current head 同事务更新。Supported 领域事实要求 annotation review 和 claim assessment 均 accepted，所有 source/claim/profile/head 仍 current。旧 claim 无 annotation 仍可查，不能冒充 supported typed comparison。变更保留历史，可回滚 projector，不能改写旧 claim ID/ledger。

Comparison projection 的 generation 包含 annotation/review/head、claim/assessment/evidence、domain/comparison profile 和 profile-head 的完整路径/hash。缺输入、旧/混合 profile 或 changed head 必须成为非 current 结果或拒绝；不得推测缺值。

实验条件至少覆盖来源版本及其 PDF/产物 hash、模型/checkpoint、active/total 参数、resolution、frames/FPS/duration、steps/CFG、benchmark version/split、zero-shot/fine-tuned、teacher/student、训练数据范围、hardware、单位和 metric direction。语义差异先显示待审查；不同上下文默认 not_comparable。

### 7.2 官方性与跨来源一致性：关闭 F3

paper-linked、author-linked、author-org、community-only 是发现信号。只有上下文明示 repo 实现该 paper，且 paper/repo 关系证据通过相应 review，才映射 official。作者身份与其声明的对应关系分别核验；baseline/依赖/一般提及不升级。未核验保持 unverified_candidate，明确第三方实现为 unofficial。

官方性证据按类别保存（FABLE-010）：A=论文在“our code/implementation”语境直接指向仓库；B=论文关联的项目页明确指向实现；C=仓库 README/CITATION 反向精确引用该论文；D=作者身份/控制关系的可验证公开证据。用户名/姓名相似、同一组织仅是 D 的弱线索，不单独证明身份或对应关系。A/B 与 C 的一致组合是优先核对路径；每一侧仍要检查本文实现而非 baseline/依赖。

不把反向引用 C 设为所有 official 仓库的硬门槛：论文明确发布的仓库可能尚无 CITATION 或 README 回链。此时 review 必须记录 A/B 或经核验作者明确声明所提供的关系证据、缺失证据面及接受理由；证据不足仍为 unverified_candidate。仅 C 不能自动判 official，也不能仅因缺 A/B 就断言 unofficial；明确第三方复现声明才支持 unofficial。W4 gold 同时覆盖第三方反向引用、baseline 链接、作者组织无关仓库、可信直接发布但无反向链接。

当前 paper-code-alignment.v1 的 canonical officiality_evidence 使用 PDF locator，不能直接放入 project-page/README URL。新证据先作为 research candidate；W4 必须冻结可审计的 relation-review 附属记录或兼容 successor，并同时规定与现有 alignment/receipt 的关联，之后才能用这些新增证据面发布 official 判定。该扩展还需覆盖有经核验作者/组织控制与明确 repo-side 官方声明、但论文尚未回链的正例；不绕过当前 closed schema。

固定 repo full commit、许可证 observation、入口/配置/代码行；训练、推理、数据处理、评测、checkpoint 能力分别声明 present/partial/absent/unverified。Absence 要有搜索范围；README 声称不等于代码能力。Hugging Face/checkpoint 仅保留 URL/revision/许可 observation，不下载权重。

Mismatch 检查覆盖 paper↔repo、README↔config、主文↔附录、新旧版本，绑定两侧 locator，先核对实验条件和版本，再产生 review candidate。它不能自动改变 assessment。

### 7.3 可恢复的研究会话

发现来源包含 backward/forward citations、相关主题、作者/项目页面，以及代码/checkpoint 候选。排序解释 seed distance、相关性、年份、来源、diversity、代码可用性；ID 去重与版本归并分开。每轮记录 method/benchmark/implementation/counterevidence/reproduction/chronology 路径、覆盖缺口、观察、重复率、新相关来源收益及预算。

来源独立性按原始证据与转述/镜像关系判断；多个 URL 不自动变成独立验证，未知独立性显式记录，不要求所有 claim 强制拥有两份来源。Stop policy 使用固定配置，根据低收益、覆盖、重复率、预算或用户停止产生可重放结果。Live observations 可变化，同一 frozen observations/config 的结果须确定一致。

发现/读取可由产品运行时的有界子任务并行执行，与开发期 Builder/Repo Steward 角色无关（FABLE-012）。并行度/超时属于运行调度配置，写入 run 记录；排名、去重、合并顺序与预算/stop 等语义配置单独固定。同一 frozen observations 和语义配置，以并行度 1/N 重放时规范化语义产物字节相同；调度记录中的耗时/并行度当然可不同，不能拿包含这些字段的整个 run 文件要求字节相同。Live discovery 因响应时序/观察集合不同可不同，但实际 observations 与停止依据必须保留。Decision 归并、compile、publication preparation 和 index build 仍串行。每篇候选由用户选择；单篇失败不阻塞其他候选。

## 8. 检索、问答与研究产物

基础问答先复用 BM25/catalog/exact evidence；完整检索依次加入 section/claim/figure/table/equation、implementation/config、benchmark/comparison row。Intent 包含 quick/standard/compare/implementation/reproduce/survey/research；entity/filter 至少支持 model/task/year/resolution/benchmark/code availability。

完整路径：独立 exact/BM25/typed-graph 排名→确定性 RRF→证据状态/新鲜度/独立性过滤→有预算 context pack。禁止相加异构 raw score。可选 dense 缺失时基础功能仍工作。Graph 从 canonical relation/claim/evidence 重建，predicate registry 校验两端类型；similarity/共现不自动成为事实边，contradiction detector 先产生 candidate。

Context pack 保存 included/omitted、rank/选择原因、claim/evidence/locator、附近原文和 supporting/counterevidence 角色。存在相关反证时应选入；超预算必须显式标出争议未覆盖，不能以多数相似来源宣称已无反证。无法访问原文时明确缺口。相同 snapshot/config 的 pack 字节一致。

新鲜度与已发布覆盖（FABLE-007）：复用 engine 现有的 live catalog status 和查询前后重检；不得把当前 `CATALOG_STALE` / `RETRIEVAL_GENERATION_MISMATCH` 拒绝降为一个可忽略警告。W2/W5a 增补诊断输出，绑定各 catalog/BM25/graph/comparison generation、其输入 manifest、构建时审计 checkpoint、查询时审计 checkpoint，以及声明检索范围内的 current source-version/索引覆盖集合。Receipt head 是否相同只是诊断输入，不能替代依赖完整集合与 live hash 校验；不相关 receipt 变更也须重新核实实际依赖后才可判 current。

current 回答要求所需 generation 与其审计/输入绑定均可验证且一致。Stale、unknown、missing 或查询中变化时，本次不生成“当前知识库”的研究回答，输出可理解的阻塞信息与 operator 重建 next_action。可从审计/current source inventory 与 indexed manifest 可靠求差时列出未覆盖 source-version ID；若无法求完整差集，记录 `coverage_unknown` 和未知原因，不能编造“遗漏 0 篇”或精确数量。合法过滤条件排除的条目另列 excluded_by_scope，不混入索引遗漏。

W2/W5a fixtures 应覆盖发布新论文但未重建、查询期间 head/输入替换、相关与无关 receipt 变化、覆盖差集无法计算、重建后恢复 current。机制测试通过不等于真实用户已完成 operator 重建。Context/review 继续绑定确切 snapshot；当前版本提示不覆盖旧版本的历史引用。

Answer/synthesis proposal 绑定 context、生成 runtime/model、prompt 与输入摘要，区分事实、推断、争议和未知。支持性 review 绑定 exact factual unit、claim、locator 与原始 span；代码核验引用/hash/范围，人工或冻结 gold review 核验语义支持。

文章包含问题、共识、差异、矛盾、未知、比较矩阵和 bibliography；行内引用与 bibliography 同时保留来源版本、PDF/产物摘要和 locator（FABLE-005）。草稿保存在 `.work/research/**`；经选择与 operator 发布后成为 create-only `wiki/synthesis/generated/<artifact-id>.md`。修改生成新 ID 与 supersedes；用户在 Obsidian 复制到自有 notes 后自行编辑。新 namespace 同时纳入 transaction/receipt/audit/backup，不能只生成文件便宣布发布。

复现计划绑定 paper/model、经核验 repo/full commit、entry/config、checkpoint/license observation、软件/硬件/数据需求、验证步骤和预期输出。各项标 verified/inferred/unknown/blocked；verified 必须有出处，明确未下载、未训练、未验证复现成功。

## 9. 工作包、依赖与责任

下面是唯一实施依赖表；E 表示该包工程接口精确验收，S 表示真实产品纵切。后续工程只依赖必要 E，真实发布受相应外部/人工条件约束。W0-R3 正在进行 Fable 第一轮回复与 R3.3 复审交接，W1–W7 产品化实现尚未开始；不重标历史 VPKB 包状态。每个实现包还须在开工前单独冻结其窄合同，这是包的入口条件，不是包对自身的依赖。 FABLE-002/008 的依赖调整尚待用户决定；下面保留现有选择路径，§13 的选项尚不生效。W2 的新增版本/status/parser 合同及 W5 的评测修订必须经过对应包冻结，不能凭本表开始实施。

| 包 | 依赖 | 交付与主要落点 | 退出条件 |
| --- | --- | --- | --- |
| W0-R3（REQ-10） | 当前基线与设计输入 | 本 PRD、review 讨论、外部意见处置 | 文档与接口交付；外部评审和实施冻结分别记录。 |
| W1 预览（REQ-01） | W0-R3 设计输入 | research request/observation/metadata/preview/decision；preview Skill | E：离线 fixture/安全/安装测试；S：真实 arXiv 中文预览与选择。 |
| W2 单篇流程（REQ-02） | W1-E | selection/source-version/display-head 兼容合同、唯一 engine status derive、外部 blob/parser exporter、session/next/resume；复用 prepare/extraction/compiler/publication | E：完整链、多版本/旧客户端兼容、状态/错版拒绝、幂等恢复、parser stub 交接；S：外部真实 parser 证据、PDF 到 Obsidian、receipt/audit 与索引待重建状态。 |
| W5a 基础问答（REQ-05） | W2-E | bounded paper/claim/evidence context、answer、基础 gold | E：阶段 gold、引用/支持/覆盖与 stale 拒绝；S：按三次运行协议的真实论文问答。只验 paper 范围。 |
| W3 研究发现（REQ-03） | W1-E、W2-E | OpenAlex/arXiv observation、candidate/rank/session/stop | E：固定观察确定性重放与恢复；S：3 seeds 候选、反证与 gap。 |
| W4 代码映射（REQ-04） | W2-E；W3 输出可选 | code observation、officiality review、commit/config/locator | E：mapping gold 与 code capture；S：确认 1 repo，再按真实 baseline 扩到 5 repo。 |
| W5b1 领域比较报告（REQ-05/06） | W5a-E、W4-E | canonical profile/annotation/review/head 兼容扩展；比较投影与 lint；research 比较回答、矩阵及 bibliography | E：迁移/拒绝/receipt/audit/backup、字节可重建比较投影、冻结比较 gold 与报告支持/覆盖均通过；S：3-paper/1-repo 的 accepted comparison 报告及恢复。无需 typed graph/RRF。 |
| W5b2 完整检索（REQ-05/06） | W5b1-E | typed graph/generation/query、research RRF/context、完整六类 gold | E：graph/rebuild/过滤/完整 gold 全部指标；S：真实跨论文与代码问答，记录反证和未知。 |
| W6 综合与复现（REQ-07/08） | W5b2-E；研究综述还需 W3-E | 完整 article/reproduction、生成快照发布；消费 W5b1 比较产物 | E：引用/语义支持/namespace；S：文章及复现计划。 |
| W7 产品化与恢复入口（REQ-09） | W1、W2、W3、W4、W5a、W5b1、W5b2、W6 的 E | 自然语言 status/audit/backup/isolated-restore 请求与 operator 交接；全部新 namespace 的兼容、UI/Bases、性能、可选只读 MCP | E：检查/备份/恢复入口与跨 namespace 回归；S：真实外部锚、隔离恢复和视觉验收。完整 v1/readiness 独立完成。 |

W3/W4 可并行；基础问答无需等待完整代码发现。首个 3-paper/1-repo 研究里程碑依赖 W1、W2、W5a、W4、W5b1 的完整 E 和对应真实 S；不消费未命名的“部分 E”。W5a/W5b1 使用分别冻结的阶段 gold，不能称其为尚未建立的完整 gold 子集；完整六类 benchmark 及其可评估性条件仍在 W5b2 单独冻结和验收。完整 v1 仍要求七条产品纵切、最终 corpus/五仓基线和其真实验收，不能用小样本代替。

Architect 负责需求、窄合同、路径所有权与最终验收；Builder 实现主要代码/schema/test；Repo Steward 独立检查范围并串行 Git/CI。代码允许路径在每包具体冻结：research 新包归编排，engine 只做命名清晰的兼容扩展，schema/注册共享文件同一时刻一个写者。Fable 只评审设计，不冒充人工或 Architect 验收。

每包包含 full baseline、contract SHA、允许路径、接口/错误码、测试名称、候选摘要、实际 reviewed head/base/CI checkout；head 变则旧结论保留历史，base 变则重做集成核验。首包实际耗时用于后续估算，不在能力 spike 前承诺整项目工期。每包以一个可演示用户结果收尾。

## 10. 验收与质量指标：关闭 F4/F5

| 验收面 | 标准与证据 |
| --- | --- |
| W1 | 自然语言单请求得到真实题录中文预览；准确版本/abstract-only；选择前后 Vault/catalog 零变化；能力缺口可见。 |
| W2 | 真实来源版本正确，claim 有 locator 或 unsupported；错版/缺产物拒绝；故障恢复无重复来源；receipt 对应 inspected bundle。Fixture-E 与真实-S 分开。 |
| W3 | frozen observations/ranking/stop config 产生一致候选与停止决定；去重、来源多样性、反证、路径缺口可见。 |
| W4 | gold 覆盖本文实现/baseline/依赖/第三方/作者无明确对应；gold 中误判 official 为零，未知关系保持未知；真实代码行与能力声明可查。 |
| W5 | W5a 阶段 ≥10 道 answerable + ≥3 道 unanswerable；W5b1 阶段 ≥6 道比较题，含 ≥2 道期望 not_comparable；W5b2 完整 benchmark ≥20 题，覆盖 model/method/training/dataset/inference/code。各集合独立冻结 source/corpus、题目、truth 与 rubric，按下文时序/独立性规则验收。 |
| Retrieval | 在下述 corpus/干扰集可评估性条件成立时，W5b2 新指标版本要求 paper Recall@5 ≥ 0.85、evidence-unit Recall@10 ≥ 0.75；同时记录 MRR/nDCG/entity/implementation recall。不满足规模/表示层条件时记 not_informative/not_evaluable，不能记通过。 |
| Answer usefulness | 每个 answerable gold 的必答要点覆盖 ≥ 80%，整体 ≥ 90%；空事实集、全部 unknown/inference 不计覆盖。Unanswerable gold 必须明确缺证据并不编造答案；gold 在调试前冻结。 |
| Answer support | factual units 全部 supported、可解析引用覆盖 100%、悬空 0；partially_supported 等不算通过。该规则与要点覆盖同时满足，不能靠降为 unknown 绕过。 |
| Comparison | 缺限定/单位/版本/受管 current annotation/profile/head 时不可进入 current supported result；表中值和结论都有出处。 |
| Article / reproduction | 所有 factual units 引用可解析；全部核心结论和表格单元做语义 review，其余按预先冻结的抽样方案检查并声明抽样范围。样本任一不支持即修订；复现所需项均有来源或明确 unknown/blocked。 |
| Recovery / projection | generation 与当前审计/输入一致，stale/unknown 不生成无提示的当前回答；未覆盖 source-version 或 coverage_unknown 可见，operator 重建后重新核验。投影可重建；不可重建 session bytes 必须保留；profile/版本变化不能复用旧 current 结果。 |

要点覆盖阈值是本 R3 新提出的产品验收标准，需在对应 gold/config 冻结时评审；不声称附件或已有测试提供了这些数值。矛盾识别、不确定性校准、raw-source preference、source independence、benchmark metadata completeness 先作为必报诊断，升级阈值要版本化记录。

评分同时冻结 `rubric`、gold 和 adjudication 规则：每个必答要点有固定 ID、事实范围、所需限定条件与可接受来源，每点等权且最多计一次。单题覆盖率为被充分回答且 supported 的要点数/该题预设要点数；整体为所有 answerable 题的分子之和/分母之和，unanswerable 题单列。不能在看过答案后拆分要点、删除难点、合并问题或改分母；部分回答不计完整覆盖。

Factual unit 按可独立核验的断言切分；数值必须连同对象、单位、版本和实验条件核验，合句中的多个断言分别评分，重复同义句不增加覆盖，省略限定条件不能变成更易通过的单元。答案生成者不能独自制定 gold 或裁定自己的语义支持。独立 reviewer 使用冻结 rubric 给出 unit→point→claim/locator 的标签与理由；fixture/gold 工程规则由 Architect 冻结，真实语义 gold 与争议由用户指定的领域审阅者确认，并遵守现有 claim gate。未裁定争议保留 open，不计通过；修订 rubric/gold 必须新版本、保留旧结果并重跑全部受影响题，不能就地调低标准。

### 10.1 阶段 gold、独立性和冻结时序（FABLE-003）

W5a/W5b1 的最小题数是 R3.3 提出的工程验收下限，不是统计置信保证；真实语义 gold 仍需用户或其指定领域审阅者确认。W5b2 的完整 ≥20 题单独冻结，必须覆盖六类 target 与 answerability/版本/争议场景。阶段 gold 不是事后从完整集挑出的“最好表现子集”。未来完整集可引用保留原题 ID/语义不变的阶段题，但 source/corpus/truth 改变时产生新版本和 lineage，不假称同一 frozen subset。

每个 gold manifest 绑定 source-version/corpus inventory、question IDs、必答要点、truth/evidence、rubric、阶段成员与选择规则、作者和实际 reviewer 记录、freeze event/前驱摘要、时间和文件 SHA-256。Architect 可依据原文起草；答案生成者不得独自确认自己的 gold，两个同家族 agent 也不自动构成人工或领域独立性。真实语义确认须保留实际用户/领域 reviewer 的事件引用，不能自造签名或批准。

开发集与 qualification 集在调试前分开；开发过程中已有的回答永久标为 development-only，不能事后改名为 S 通过。第一次 qualification dispatch 前，gold/rubric、待验模型/prompt/config、source/corpus/context 和完整 question/run 清单均须冻结并绑定同一 attempt；每个 run 引用该冻结事件/hash。通过前驱 hash/记录顺序检查先后，墙钟时间只作辅助，不单凭时间戳宣称防篡改。接触验收失败后改 prompt/ranker 的尝试保留为已暴露回归轨；若要宣称未见题泛化，另需冻结未用于调试的 holdout，不能把回归分数改称泛化分数。

### 10.2 真实模型 qualification 运行协议（FABLE-004）

W5a/W5b1/W5b2 的真实问答及 W6 的文章/复现生成，各在其冻结验收样本上默认执行 3 轮独立的完整生成，不能把同一缓存回答复制为三轮。每轮固定同一 source/context snapshot、模型/runtime、prompt、可观察的 decoding 配置；不可观察的字段明确 unknown。run 清单在 dispatch 前预登记，每次实际 attempt、proposal、context、评分及失败都归档；不要求随机生成字节一致。

问答每轮都满足 100% support 与逐题覆盖 ≥80%、整体 ≥90%，对三轮取最小值判 gate，同时报告 median/range 和失败明细。文章/复现沿用本节原有全量核心单元及预冻结抽样 rubric，每轮分别判定，不能把抽样合格声称为全篇 100% 语义证明。没有合格 run 就不能择优重跑至通过；修改内容/config 后形成新 attempt，重跑整个受影响 frozen slice，旧结果不删除。

基础设施失败/取消及是否允许补跑的分类在协议中预先冻结；每次替代 run 引用原 attempt。该记录验证受管 qualification 清单是否完整，不能证明用户在其他会话从未产生未记录尝试。确定性 engine/projector 的 E 验收仍使用确定性重放，不套用三次模型生成协议。

### 10.3 检索 corpus、干扰集和指标版本（FABLE-011）

每个评测 manifest 固定检索表示层、query filters、candidate universe、eligible paper/source-version 与 evidence-unit inventory、gold/干扰集清单及 hash。paper 排名按去版本实体去重计数，不用同一论文多版本凑 corpus 数；版本限定的证据评测仍按精确 source-version。

W5b2 的 paper Recall@5 gate 至少需要 30 个同一已声明表示层的合格候选，且保留预审的相近方法/任务 hard negatives；≤5 候选时该 cutoff 的排序指标无区分力，5–29 也不满足本方案的完整集下限，均不能报告 full benchmark 通过。小 corpus 阶段可记录 Recall@1、MRR、nDCG 和固定 hard-negative 诊断，并诚实报告候选规模/局限。低规模仍可能暴露“相关论文没召回”的故障，但单次高 Recall@5 不证明排序质量。

冻结 67 项 seed 中的 metadata-only 记录只可用于明确标注的题录/发现排名轨；不能把它们记成已摄取全文、混入全文质量分母或充当 evidence-unit 干扰项。完整正文/claim 检索轨的候选必须真实进入对应、可查询的 source/索引表示；各轨分别报告，不能合并为一个“全文检索通过”。30 是 R3.3 待工作包冻结的可评估性下限，不来自已有测试或统计显著性论证。

新 evidence-unit Recall@10 对每题至少要求 20 个真实可检索的非 gold 单元，分布在 ≥3 篇论文，包含 ≥5 个由 reviewer 预先判定的词汇/语义 hard negatives；若样本内容允许，至少 5 个非 gold 单元来自 gold 论文内部。所有 distractor 必须确属非相关或分级相关，不将未审判的潜在支持证据强标为负例；数量不足时该指标为 not_evaluable，不制造占位单元补数。题目若不适合此候选池，单列专门任务轨，不能继承此 gate。

这些干扰集规模是本修订的初始配置，须在 W5b2 corpus/rubric 冻结时评审。当前 evaluator 的 `evidence_recall_at_8` 基于既有 chunk/mapping 返回协议；新 @10 必须独立版本化 schema/config、候选深度、去重后的证据单元排序/截断及 evaluator，并用新结果验收。不得把 8-chunk 的历史值换名为 10-unit recall，也不得改旧记录来满足新阈值。

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

已确定：完整研究目标、现有唯一内核、Pro 领域设计采用、F1–F5 修订方向、单一依赖表、3-paper/1-repo 首次研究规模、Markdown 外部 review。以下两项产品路径由用户决定，不能由内部或 Fable review 替代：

| 待决项 | 当前保留路径 | Architect 推荐方案与代价 | 生效条件 |
| --- | --- | --- | --- |
| FABLE-002：首个报告/文章交付时点 | §9 原 W5b1 先 canonical accepted comparison；W6 等 W5b2 | 拆出 W5b1-R，依赖 W5a-E+W4-E，输出 `.work/research/**` 的有界报告、矩阵、bibliography；实验条件抽取为 provisional/unreviewed、缺条件即 not_comparable。原 canonical 能力成为 W5b1-C，单独验 accepted typed comparison。W6 草稿消费 W5b1-R+W4，图谱为可选增强；正式受管发布仍遵守 canonical/claim review/namespace 门槛。更早可用，但必须向用户区分待审草稿与受审事实。 | 用户明确选择后再更新 §1/§9；当前推荐尚未采纳，不构成部分 E 或实现授权。 |
| FABLE-008：最小备份入口 | 产品入口目前仍在 W7，各生产者保留完整性要求 | 新 W2b 依赖 W2-E，在持续使用真实数据前完成：自然语言备份/检查请求、Vault backup manifest 请求、session 原字节保留包与两者 checkpoint 关联、operator 交接、隔离恢复/缺件报告。W2 的受控真实 smoke 可用于验证交接；持续使用里程碑须 W2b-S。W7 保留全部后续 namespace 的回归、最终外部锚/恢复/readiness。增加早期范围，但覆盖不可重建的研究状态。 | 用户明确选择后再更新 §6.4/§9；真实外部锚和 readiness 不因入口前移自动关闭。 |

本轮已向用户提出这两个选项。未收到决定时，它们保持 open；Fable 可继续评审技术方案和取舍，但不能替用户选择。

对应包冻结前须落实：connector 实测能力和显式版本规则；selection/source-version/display-head 与状态推导兼容合同；外部 blob/parser executor 的安装/角色映射和 stub/真实执行证据；domain/profile/annotation closed schemas；新鲜度/coverage 输出；阶段及完整 gold、corpus/干扰集、模型运行协议；stop/rank/budget 配置；真实技术轴与来源、人工 gate 证据。它们有明确 owner 和所属包，不要求为整个 v1 提前生成全部 schema。

本修订不表示 W1 已实现，也不把 R3.2 的内部 GO 转授给 R3.3。当前任务交付 Architect 对 FABLE-001–013 的回复和本 successor；产品选择、Fable follow-up 和各包合同冻结仍分别记录，没有意见被预先标为 resolved。

## 14. 设计输入与追溯

- [Pro 六仓对比附件](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md)，SHA-256 `c7fc3871c8061d4bdc6ba01ce3f07dd385ee002985ee77239a4a217bf42fdc33`。
- [R2 方案](video-generation-research-wiki-v1-plan-r2.md)，SHA-256 `a63f1840e86be25872f6a99b6cea853fe22a209de3782723b5bcc17a2caadf5c`。
- [再评审](video-generation-research-wiki-v1-rereview-2026-09-05.md)，SHA-256 `ab55909080ccf3c7f2cce31280a32d87c254800ff513676381fa04abb7b5c655`。
- [附件综合建议](video-generation-research-wiki-v1-combined-review-2026-09-06.md)，SHA-256 `43abdc2b8baa39ea90f074f0192bc84f878100d68698bb6803b877b9fb09f71f`。
- [六仓源码审计](external-reuse-audit-2026-09-04.yaml)、[团队约定](codex-team.md)、[历史任务索引](task-index.yaml)。索引中的旧观察日期/状态保持历史，当前产品化接续按本文 §3、§9。

F1→§6.3/W2；F2→§6.2/W2；F3→§7.2/W4；F4→§8/§10/W5；F5→§9。Pro 的联合证据、领域分类、两阶段、检索、研究 session、可比性分别落入 §7.2、§7.1、§6.4、§8、§7.3、§7.1/§10。

本轮依据：[R3.2 原正文及 Fable 第一轮/Architect 回复](video-generation-research-wiki-v1-prd-r3.md)、[回复工作包](packets/RESEARCH-WIKI-FABLE-R1-RESPONSE.md)。源码只读核对包含 `identity.py`、`contracts.py`、`catalog_store.py`、`catalog_collector.py`、`extraction_artifact.py`、`retrieval.py` 和现有 prepared/paper-record schemas；未执行这些接口，也未查询远程 CI/API。

Finding 追溯：FABLE-001→§3/§5/§6.4；002→§13（用户待决）；003→§10.1；004→§10.2；005→§3/§6.2/§7.1/§8；006→§6.1；007→§3/§6.4/§8/§10；008→§6.4/§13（用户待决）；009→§5/§6.3；010→§7.2；011→§3/§10.3；012→§7.3；013→§5。

## 15. Fable 5.1 ↔ Codex Markdown 评审接口

### 15.1 当前交接状态

- 当前候选：R3.3；状态 `awaiting_fable_rereview`，FABLE-002/008 产品选择仍 pending。
- Reviewed body SHA-256：`b9eeef61bce1532fd039dd82660637abebf02d9bdba2f9819681685a1a5896c8`。范围为文件第一个字节至本节 `## 15.` 标题前的所有原始 UTF-8/LF 字节，包含前空行，不做归一化。
- Predecessor：R3.2 正文 `1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24`；原文及第一轮意见未被本文件覆盖。
- Fable 对 R3.2 的结论仍为 changes_requested，本 successor 尚无 follow-up 结论，没有 resolved finding。

### 15.2 复审方式

请同时阅读本文与 [R3.2 §15.3 的 Architect 逐项回复](video-generation-research-wiki-v1-prd-r3.md)。沿用原 finding ID，在原回复后追加 `Fable follow-up to FABLE-xxx`，写明 Reviewed revision=R3.3、上述 body hash 与核验状态、是否认可修订及剩余问题。FABLE-002/008 可评审推荐方案，但产品选择由用户决定。

R3.2 的 §15.3 继续是唯一讨论区；本文件不另开平行 finding 记录，不复制或改写原 Fable 意见。无本地写权限时返回新增 Markdown 由用户转交。不要把旧 GO 或第一轮摘要重新标成对此正文的批准。

### 15.3 本文件讨论指针

逐项讨论请见上面的 R3.2 链接。本轮文档核验与局限保存在回复工作包，不以工程 CI/测试代替设计复审。

### 15.4 决策与修订记录

| 日期/修订 | 关联 finding | 决定与范围 | 状态 |
| --- | --- | --- | --- |
| 2026-09-06 / R3.3 | FABLE-001/003/004/005/006/007/009/010/011/012/013 | 独立 successor 补充状态/版本/新鲜度/parser/官方性/评测/并行/schema 设计；R3.2 字节保留 | 待 Fable 复审，无实现验证。 |
| 2026-09-06 / 产品路径提案 | FABLE-002/008 | §13 记录明确选项；§1/§9 原路径在用户决定前保持 | open / awaiting-user-decision。 |
