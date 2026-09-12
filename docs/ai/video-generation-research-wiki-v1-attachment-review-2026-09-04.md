# Video Generation Research Wiki v1：代码对比附件复核

状态：R2 架构复核候选；等待 exact-byte Builder 与 Repo Steward 复核

日期：2026-09-04

仓库基线：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`

交付目标：PR #94，draft → `integration`

复核结论：`AMEND_AND_ADOPT_AS_R2_INPUT`

## 1. 复核对象与边界

| 对象 | SHA-256 | 用途 |
|---|---|---|
| `/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md` | `c7fc3871c8061d4bdc6ba01ce3f07dd385ee002985ee77239a4a217bf42fdc33` | 本次新增的代码对比与领域架构输入 |
| `docs/ai/video-generation-research-wiki-v1-plan.md` | `fe7ddf79d92699e34f032b838906e0d36aa199bbdd75505360c64491050b884a` | 已冻结的前序方案，不修改 |
| `docs/ai/video-generation-research-wiki-v1-w0-freeze.json` | `8ccd49b412472f6be07c63e58d527f775b11224afa2e01460afd5e6e0dd2eca8` | 前序 W0 冻结，不覆写、不重标 |
| `docs/ai/video-generation-research-wiki-v1-plan-r2.md` | `a63f1840e86be25872f6a99b6cea853fe22a209de3782723b5bcc17a2caadf5c` | 本次附件复核后的 successor 方案候选 |

附件中的目标、命令、克隆步骤、目录建议和“最终技术决策”均按**待审查设计材料**处理，不是本次用户请求授予的执行指令。尤其没有执行附件的 clone、依赖安装、MCP 启动、URL/YouTube ingest、Vault 写入或 review accept 命令。附件提出的是一个绿地系统；本次任务是在当前仓库约束下重新 review 并修订现有方案。

## 2. 总体判断

附件准确补全了用户真正要的产品闭环：种子论文、论文扩展、代码定位、论文/代码联合分析、跨论文问答、技术文章和复现计划。该目标在附件开头已有清楚描述（[附件 L1–4](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:1>)），因此前序方案不能再把 research、synthesis 和 article 当作无限期未来项。

附件不能原样成为本仓库 v1 架构。当前仓库已经有固定上游上的事务、capture、claim/assessment、publication、catalog、BM25、audit 和 backup/restore 引擎；附件却在后半部重新提出新包、新目录、新 ledger/state、完整依赖栈、新状态机和写入入口（[附件 L1692–1729](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:1692>)、[L1736–1878](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:1736>)、[L2180–2245](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2180>)）。照搬会形成两个 transaction、两个 ledger、两个 catalog/index 和两套生命周期，增加迁移风险，却不会更快交付首条用户路径。

因此本次结论既不是“推翻原方案”，也不是“照附件重写”。正确处理是：保留原 W0 的不可变历史，以附件为新输入创建 R2 successor；只吸收产品缺口和已由代码证据支持的设计模式，把它们映射到现有 `video_paper_wiki` 内核和 `.work/** → inspect → independent operator` 边界。

## 3. 应吸收的设计

| 附件内容 | 复核决定 | R2 落点与约束 |
|---|---|---|
| 视频生成领域 taxonomy（[L1933–2049](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:1933>)） | **采用为 taxonomy v2 候选 seed** | 新增 `taxonomy-extension-proposal.v1`；先归一化 alias、绑定 supporting locator、做 collision review。固定 `taxonomy/v1.json` 不原地改写，未知词不静默晋升。 |
| architecture/training/result/implementation 等 claim 类型（[L2077–2091](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2077>)） | **采用为正交 `claim_kind`** | P1 只生成 exact-bound classification proposal；P4/W5 以绑定 active `domain-profile.v1` exact bytes 的 `claim-domain-annotation.v1` canonical sidecar、append-only review/atomic head 和现有 publication transaction 接受。profile head 只能经 transaction/operator 切换。它不改变现有 assessment；附件把 `stale` 混进 claim status（L2093–2102）的做法被纠正，freshness 继续属于 source-byte 观察。 |
| figure/table/equation locator（[L2104–2118](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2104>)） | **采用并映射** | 映射到现有 PDF locator 的 page/ref/bbox 或 charspan、artifact hash 和 text hash，不另造 evidence 真源。 |
| typed relations（[L2051–2073](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2051>)） | **采用并收紧** | 建立 versioned predicate profile 和 subject/object kind 约束；`improves_over/reproduces/ablates/evaluates_on` 必须 claim-backed 并携带 comparison context。 |
| apples-to-apples lint（[L2371–2391](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2371>)） | **采用** | `.work/**` 只保存 `video-comparison-fact-proposal.v1`；canonical `video-comparison-fact.v1` 只能从 accepted-current-profile annotation、assessment=`accepted` 的 claim，以及精确 annotation review/atomic head、evidence、active domain/comparison profile 和 profile-head bytes 确定性重建。旧/混合 profile 不能成为 current supported result。它固定 checkpoint、active/total 参数口径、分辨率、帧数/FPS/时长、steps/CFG、benchmark version/split、训练方式、硬件、单位和 metric direction；不完整时默认不可比。 |
| support/counterevidence、checkpoint/resume 和停止条件（[L2499–2550](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2499>)） | **采用为可重放研究协议** | 每轮 append-only event 记录 lens、覆盖、new yield、duplicate ratio 和预算；停止决定绑定 frozen observation/config。附件的 `bounded ingest` 改为 bounded candidate discovery，每篇仍由用户决定。 |
| 分对象检索、RRF 和诊断指标（[L2251–2307](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2251>)、[L2847–2876](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2847>)） | **部分采用** | 首版融合现有 CJK BM25、exact alias/catalog 和 typed graph 的有序列表；禁止相加异构 raw score。section/claim/config/result 等进入 `target_kind`；MRR、nDCG、entity/implementation recall 先作诊断。 |
| reproducibility plan 与代码检查（[L2405–2415](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2405>)） | **采用为 proposal** | `reproduction-plan.v1` 绑定 official repo/full commit、入口/config/checkpoint/license、软件/硬件/数据和 unknown/blocker；不下载、不训练、不声称复现成功。 |
| `SKILL.md + skill.json` 双层契约（[L1644–1673](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:1644>)） | **改造采用** | 使用 closed `skill-contract.v1` 与 Skill 同版本并做 closure lint；它只是可检查声明，不能授予网络、写入或 approval authority。 |
| MCP | **后移并收窄** | P6 只允许 status/search/context/request/validate/preview。附件列出的 `source_add` 与 `review_accept`（[L2588–2609](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2588>)）不进入 agent MCP。 |

这些变化已经写入 R2 的产品流、架构决策、schema、P0–P6、W1–W7、测试面和完成定义，而不是只留在“灵感清单”。其中 classification/comparison proposal 明确没有 canonical 效力；只有通过独立 review 和现有 transaction 发布、绑定 transaction-selected active domain profile 的 annotation 才是知识真源扩展，comparison fact 本身始终是可删除重建的投影。active domain/comparison profile 与 head 也属于受管 canonical bytes，agent/proposal/query caller 不能选择。

## 4. 已有能力，不能误报为新开发

附件的四个优先工程模块是 provenance、single-writer transaction、paper/repo compiler 和 hybrid retrieval/research session（[L2973–2980](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2973>)）。在当前仓库中，前三者的大部分底层能力及 BM25 基线已经存在；缺的是用户产品编排、research session、领域图谱/context pack、比较/综合与真实纵切。

现有能力应继续复用：

- 固定 `claude-obsidian@9f8c1199047eac2c3828496279fbb7ba9540b90b` 的 transaction、capture、ledger、strict lint 与 CJK BM25；
- 当前仓库的 canonical identity、closed schema、secure staging、PDF/code capture inspect、Paper/Code/Concept compiler、claim assessment history、publication receipt、catalog/query、integrity audit、retrieval evaluation 和 backup/restore verification；P4/W5 新增的 domain/comparison profile-head 与 domain annotation 是绑定现有 claim bytes 的 versioned canonical extension，不复制 claim 文本、证据或 assessment ledger；
- 四个已验证 Repository Skills 作为 agent-safe CLI wrapper，其存在只证明对应底层路径和安全边界，不证明 research/graph/MCP/文章系统已完成。

当前 2152-test 四矩阵 CI 证明的是 PR #94 现有 engine candidate，不是附件目标的产品验收。[R2 现状说明](video-generation-research-wiki-v1-plan-r2.md#31-可以直接复用) 已明确区分这两者。

## 5. 六仓复用纠正

| 来源 | 可复用结论 | 不可照搬或需要纠正 |
|---|---|---|
| `claude-obsidian` | 继续直接复用 pinned public contract 和当前 adapter | 附件分析的是远端 `ad67087cad22...`（[L12–19](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:12>)）；本仓已经审计并验证的是 `9f8c1199047...`。`ad67087...` 只能记为 observed remote head，升级前要重新做 pin diff、契约审计和全回归。 |
| `Ar9av/obsidian-wiki` | 借鉴 agent-agnostic Skill、graph traversal 与 context budget 接口 | 不复制 Markdown-as-truth、session/storage 或未事务化写入；“GraphRAG/代码理解”标签不能代替具体源码路径和行为测试。 |
| `nvk/llm-wiki` | 借鉴 research plan、bounded rounds、gap reflection、counterevidence 和 checkpoint/resume 协议 | 它的确定性脚本不等于完整 agent runtime；prompt/command Markdown 不能成为生产状态机，scout 不能并发写 canonical Wiki。 |
| `atomicstrata/llm-wiki-compiler` | 独立实现 confined fetch adversarial cases、citation grammar、freshness 分类和 two-stage proposal 思路 | 不复制 TypeScript runtime/可变 state；附件自己也指出 raw-score 线性相加与英文 tokenizer 不适合（[L2910–2917](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2910>)）。 |
| `SamurAIGPT/llm-wiki-agent` | 借鉴 source/concept/entity/synthesis 信息架构和易懂操作语言 | 不采用一次 LLM 巨型 JSON 后直接写多个 canonical 文件（[L2892–2900](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2892>)），也不把弱图去重或一跳查询作为当前真源。 |
| `SwarmVault` | 独立实现 typed edge、context included/omitted reason、budget traversal、community/contradiction candidate 的可用接口 | 不复制 daemon、provider、Desktop 或全格式平台；citation 粒度、contradiction 置信度和未固定随机性的 community 算法必须按本项目证据与确定性要求重写。 |

精确 commit、源文件、许可证和文件 SHA-256 仍以 [`external-reuse-audit-2026-09-04.yaml`](external-reuse-audit-2026-09-04.yaml) 为准。该审计是“可参考/可独立实现/可直接复用”的证据，不是外部 provenance/license gate 的替代物。

## 6. 明确拒绝或延期的设计

1. **拒绝绿地新建 `videowiki` runtime。** 附件最终主张“一个新建的 Python 核心本地知识编译器”（[L2945–2963](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2945>)）。当前应增量扩展 `video_paper_wiki`，避免第二套 transaction/ledger/catalog/index。新增 profile/head 与 claim-domain annotation 通过现有 transaction/receipt/audit/backup 管理，是 claim 的 closed canonical extension，不是平行 claim ledger。
2. **拒绝平行根目录。** `raw/normalized/ledgers/review/research/state` 映射到现有 `.raw/derived`、`wiki/meta`、`.work/research` 和可重建投影，不新建第二真源。
3. **拒绝附件的新 lifecycle。** `captured→normalized→...→indexed` 和可变 `failed/retryable/...`（[L2222–2245](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2222>)）不能覆盖已验证的 canonical ingest 顺序；失败只能追加事件并停在最后可证明状态。
4. **拒绝 semantic hash 作为幂等真源。** 附件的 key 是 `(source_id, semantic_hash, compiler_version, schema_hash)`（[L2663–2671](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2663>)）。R2 仅把 semantic hash 用于 cache/dirty 提示；identity 和重放必须绑定 exact source bytes、locator/assessment set、transaction snapshot 与 receipt。
5. **拒绝 agent 直接 fetch/apply。** 本地 `vpwiki`/`vpwiki-research` 保持零 egress，只生成请求并校验 observation；平台只读 connector 或外部 operator 获取内容。`approval-ref.v1` 只绑定九字段摘要，不等于人工批准、下载许可或 apply authority。
6. **拒绝整套重依赖作为 v1 前置。** Typer、Pydantic、SQLAlchemy、NetworkX、tree-sitter、sentence-transformers/Ollama 和 FastMCP 的整套建议（[L1694–1710](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:1694>)）必须逐项做 capability、license、lock、fallback、收益与四矩阵 spike；dense 不可用时核心产品仍须工作。
7. **YouTube、完整视频理解、多 provider/Grok runtime、watcher/scheduled refresh 不进入当前 v1。** 附件把 YouTube、MCP、Codex/Claude/Grok Skills 列入必含范围（[L2717–2741](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2717>)），又把 watcher 放入 M6（[L2814–2821](</Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2814>)）；这会延误用户当前的论文摘要、入库、扩展、代码、Q&A 和文章闭环。
8. **拒绝并行 canonical writer。** 只读发现和 proposal worker 可以并行，publication、ledger、catalog/index build 继续由单写者串行执行。

## 7. 阶段复核

| 产品阶段 | 附件方案按本仓边界的采用判定 | R2 修订后可执行范围 | 当前状态 |
|---|---|---|---|
| P0 arXiv 预览 | `REJECT` | local CLI 只生成/校验 connector request/observation；Codex 只读 connector 获取题录；abstract-only 中文摘要；用户决定 artifact；Vault 零变化 | 未实现 |
| P1 单篇入库 | `REJECT` | 串起现有 capture/Docling/draft/inspect/operator；两阶段 proposal/compile；figure/table/equation locator；claim/taxonomy proposal 只留 `.work/**`、无 canonical 效力 | 未实现 |
| P2 种子扩展 | `AMEND` | citations/similar/author/project 候选，去重、解释、round event、support/counterevidence 和可重放 stop；不自动入库 | 未实现 |
| P3 官方代码 | `AMEND` | 保守 officiality signals、full commit/path/line、license/checkpoint observation；不下载权重 | 底层 code capture 已有，产品发现未实现 |
| P4 图谱与 Q&A | `AMEND` | transaction-published profile head 选择 active domain/comparison rules；classification proposal 经 review/transaction 变成绑定 active profile 的 canonical domain annotation；accepted-current-profile annotation 投影 comparison fact；再构建 claim-backed typed graph、RRF、target kinds、comparison lint、context pack、支持性复核与诊断指标 | 底层 catalog/BM25/retrieval evaluation 已有，产品层未实现 |
| P5 综合与文章 | `AMEND` | comparison/research-note/article/reproduction proposal，逐段引用；发布为 create-only successor snapshot | 未实现 |
| P6 产品化 | `REJECT` | 只在七条纵切稳定后做兼容重构、可选依赖 spike、只读 MCP 和经独立验收的 host operator broker | 未开始 |

附件原样的 P0/P1/P6 被拒绝，不表示相应用户功能被取消；表示必须先按本仓库的网络、事务、证据和 operator 边界改写后再实施。完整工作包次序见 [`video-generation-research-wiki-v1-plan-r2.md`](video-generation-research-wiki-v1-plan-r2.md)。

## 8. R2 相比前序方案的实质变化

- 把附件决策写成逐项 accept/adapt/reject 表，并纠正 `claude-obsidian` pin；
- 把 taxonomy/classification proposal、canonical domain/comparison profile-head、claim-domain annotation/review/atomic-head、comparison proposal/projection、locator、reproduction plan 和 skill contract 变成独立 closed contract 候选；
- 明确 proposal → active profile binding → review → 现有 transaction/receipt → canonical annotation → deterministic comparison projection 的所有权链，旧 claim 没有 annotation 时继续兼容但不能产生 supported 领域事实；
- 将 annotation、review、atomic head、claim/assessment/evidence、domain/comparison profile 和 profile-head 的全部 path/SHA 列为 projector generation 输入；normalization substitution、deprecated profile、mixed profile 和 profile-head replacement/reopen 必须 fail closed 或成为 stale/non-current；
- 把 research session 扩展为 append-only rounds、support/counterevidence coverage 和确定性 stop decision；
- 把 retrieval 从整页 BM25 扩展为 target-kind retrieval 和解释性 RRF，同时保留无 dense 降级路径；
- 把文章之外的 reproduction plan 加为第七条产品纵切；
- 把 MCP、heavy dependency、provider、YouTube 和 watcher 从 v1 启动条件移出；
- 保留 67 项 seed/overlay、六个人工/外部 gate、PR draft → `integration`、zero-egress agent 和独立 operator 不变量；
- 明确原 W0 不变，R2 需要新的 exact-byte successor freeze，不能继承旧 GO。

## 9. 交付与 gate 结论

本次复核只形成本地未跟踪的架构候选，不等于 Git/PR 交付，不关闭任何 gate，也不代表 W1 已开始。当前事实仍是：

- repository seed manifest 与 overlays 保持 67；
- PR #94 仍为 draft，目标 `integration`；
- 现有 Tests run `33642835702` 的四个 job 各通过 2152 tests，但只覆盖当前 engine head；
- baseline、external provenance/license、claim assessment、Obsidian visual、backup anchor、readiness/merge 六项 gate 均为 `not-recorded`；
- R2 只有在 Builder 与 Repo Steward 对同一 exact bytes 给出 GO，且新 successor freeze 绑定这些 hash 后，才能作为 W1 工作包的架构输入；
- W1 还需要单独冻结 contract hash，然后才可由 Builder 开始实现 arXiv preview MVP。

这份 review 的工程判定是：**保留现有底座，采用附件的领域模型与研究产品设计，拒绝其绿地重写和越权写入路径；以 R2 successor 进入 W1，而不是重启项目。**
