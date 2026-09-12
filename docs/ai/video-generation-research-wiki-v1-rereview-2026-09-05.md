# Video Generation Research Wiki v1 R2 再评审

日期：2026-09-05。评审对象是 R2 开发方案，不是本轮实现交付。

结论：**保留整体架构；在后续工作包冻结前修正五项设计问题。W1 能力验证与窄契约起草可以继续，不应把 R2 直接作为 W2–W6 的实现合同。**

继续采用现有 engine、单一事务发布链、可追溯 claim/evidence、可重建检索投影，以及先预览再选择的用户流程。主要问题集中在真实输入交接、官方代码判定、产品验收和实施依赖；不需要重启项目或继续扩大底层审计框架。

## 评审基线与范围

- 本地 HEAD：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`。
- [R2 方案](video-generation-research-wiki-v1-plan-r2.md) SHA-256：`a63f1840e86be25872f6a99b6cea853fe22a209de3782723b5bcc17a2caadf5c`。
- [W0-R2 冻结记录](video-generation-research-wiki-v1-w0-r2-freeze.json) SHA-256：`0eed0bfeb24c3025f45fc7805b8aeacd0d2942ebb570375a3361308062591a57`。
- 已读取关联任务 `Clone video-paper-wiki`（`01a05893-14e8-7dc2-8c8c-a9b24a853a15`）。其最后结论为 W0-R2 完成、W1 未开始；本次不把历史结论当作免审依据。
- 冻结记录引用的七份输入全部存在且 SHA-256 匹配；旧方案、冻结和附件保持原字节。
- Architect 实际运行上下文为 `gpt-6-astra / ultra`，并非仓库偏好的 `gpt-5.6-sol / ultra`；未修改运行配置。Builder 与 Repo Steward 均按仓库要求显式使用 `gpt-5.6-sol / medium`，只读并行审查。
- 本次检查方案、相关生产代码/schema、默认环境依赖状态和有限公开网页；未跑全量测试、未执行真实 Vault/operator 操作、未获取新的远程 CI 状态。已有 2152-test/run 记录仍只属于其历史基线。

## 必须修订的问题

### F1 · P1 · W2 缺少完整解析产物的生产者

**位置：** [R2:519](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:519)、[R2:522](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:522)、[R2:721](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:721)。

方案把“复用现有 Docling”与 figure/table/equation block locator 放进单篇自动流程，但已有 [docling_local.py:132](/Users/huangzhanpeng/python_code/video-paper-wiki/src/video_paper_wiki/parse/docling_local.py:132) 只返回标题、`preview_only` 和空 `claims`；[extraction_artifact.py:1](/Users/huangzhanpeng/python_code/video-paper-wiki/src/video_paper_wiki/extraction_artifact.py:1) 与 [README:75](/Users/huangzhanpeng/python_code/video-paper-wiki/README.md:75) 明确只打包外部已经产生的 Docling 文件。默认环境检查也确认没有安装 Docling。

**后果：** 即使 PDF capture 成功，方案仍没有指定谁产出 `document.json`、parser config、model manifest、run manifest，以及绑定这些字节的 block locator。把已有函数串起来无法完成这一步。

**最小修订：** W2 明确外部离线 parser executor/exporter 的所有者与交接合同：固定 parser/model/config，绑定 captured PDF hash，交付四份解析产物，定义错误/中断恢复和 locator 映射。继续复用现有 validator/package/publication；不要求在默认 agent 环境安装模型。W2 的能力表应写“已有解析产物验证与打包；完整导出/映射待实现”。

**验收：** 用一份真实、合法提供的 PDF 和真实解析输出走完整流程；缺少解析器或任一产物时明确停在待外部输入，不得把标题预览标为已完成块级解析。

### F2 · P1 · 预览选择到入库之间缺少强制版本绑定规则

**位置：** [R2:273](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:273)、[R2:290](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:290)、[R2:524](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:524)。

W1 metadata 保存 resolved version，decision 绑定 preview；W2 只笼统要求把 decision 绑定到 plan。已有 [ingest-plan schema:7](/Users/huangzhanpeng/python_code/video-paper-wiki/schemas/video-paper-wiki.ingest-plan.v1.schema.json:7) 是 closed schema，没有 preview/decision/metadata 的绑定字段；[contracts.py:427](/Users/huangzhanpeng/python_code/video-paper-wiki/src/video_paper_wiki/contracts.py:427) 要求 ingest plan 的 `input.arxiv_id` 使用去版本标识。去版本的实体 ID 本身合理，但它不证明此次选择的来源版本。

**触发：** 用户根据 v1 摘要选择入库，获取文件前已有 v2；如果 external request 使用 latest URL，operator 可以提供 digest 完全正确的 v2 文件。仅通过现有 plan/ref 的 hash 校验，不能证明内容仍是用户选择的 v1。

**最小修订：** W2 显式定义并强制消费 selection/source binding，绑定 decision、preview、metadata/observation hash、resolved version、版本化 PDF URL，以及外部获取后确认的 PDF hash。生成请求、prepare、resume 和最终发布均检查同一绑定。版本变化需重新预览/选择；保留去版本 canonical paper ID。具体采用 sidecar 还是版本化 schema 扩展应在 W2 窄契约决定，不必预先重写既有 approval-ref。

**验收：** v1 选择搭配 v2 observation/PDF 的错配用例被拒绝；同一版本重复输入幂等；恢复时不能用最新 metadata 覆盖旧 decision 的精确输入。

### F3 · P1 · `paper-linked` 不足以判定官方实现

**位置：** [R2:323](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:323)、[R2:554](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:554)。

规则把论文原文中的 repo 链接直接映射为 `official`。论文同样会链接 baseline、依赖和 related work 的仓库；已有 [paper-code-alignment schema:13](/Users/huangzhanpeng/python_code/video-paper-wiki/schemas/video-paper-wiki.paper-code-alignment.v1.schema.json:13) 仅要求 official 至少有一个 PDF locator，无法代替语义判断。

**后果：** 他人的仓库会进入官方实现记录，并继续影响代码图谱和复现计划。

**最小修订：** `paper-linked` 仅作为发现信号。只有链接上下文明示“该仓库实现本文”，且证据绑定这篇 paper 与该 repo、完成相应 review，才可升级为 official。作者身份核验也应同时核验其声明的 paper→repo 关系；其余维持 `unverified_candidate`。

**验收：** 分别覆盖本文实现、baseline、依赖、第三方复现、作者主页无明确论文对应关系等案例；不能只测试链接是否出现。

### F4 · P1 · Q&A 验收可以通过回避回答而过关

**位置：** [R2:580](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:580)。

现有标准要求所有 factual units 都 supported，并允许将失败项降为 inference/unknown；却没有约束“本来可回答的问题必须回答到什么程度”。检索 Recall 达标也不能弥补回答层缺失。

**触发与后果：** 检索器找到了正确证据，回答器仍对所有问题输出 unknown，或者只重复一个无争议背景事实。此时 unsupported 数量可以为零，引用覆盖也不一定失败，但用户研究问题没有得到回答。若 factual unit 为空，当前方案也未规定如何判定。

**最小修订：** Gold 中先冻结 answerable/unanswerable、必答要点和必要比较维度；分别评估证据支持、要点覆盖、错误拒答和应当拒答的识别率。空 factual-unit 集合对 answerable 问题不得算通过；inference/unknown 不计作已回答必答要点。阈值须在调试回答器前冻结，保留现有事实支持要求。

**相关 P2：** [R2:595](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:595) 只人工检查按 ID 排序的前十个 factual 段，不能证明长文章后半部分的结论。至少覆盖全部核心结论与比较表，再对其余内容做冻结、可复现的抽样；报告明确区分全量引用完整性与抽样语义支持。

### F5 · P2 · 工作包依赖和工程/真实使用验收混在一起

**位置：** [R2:619](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:619)、[R2:634](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:634)、[R2:636](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:636)、[R2:704](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:704)、[R2:712](/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-plan-r2.md:712)。

依赖图和近期顺序要求 W3 discovery 与 W4 code discovery 并行，入口表却要求 W4 先完成 W3。另一方面，W2 工程退出包含真实 operator receipt/纵切，后续包又宣称候选发现不受人工 gate 阻塞。

**后果：** 按不同章节排期会得到不同结果；等待真实发布/人工验收可能拖住本可独立完成的候选发现。

**最小修订：** 统一以一张依赖表为准。W4 若直接消费已知 paper，可依赖 W2 工程接口，W3 observation 为可选输入；W2 分开记录 engineering acceptance 与 gated real-product smoke，后续工程包只依赖所需接口的前者。真实纵切和 v1 完成仍必须满足原有人工/外部条件。

**额外产品排序建议：** 将基础 paper Q&A 提前成小包，依赖已有 canonical claim/evidence 与 BM25/catalog；代码问答再依赖 W4，typed comparison/完整图谱另做后续包。当前 W5 同时承担 profile 迁移、annotation review、graph、community、RRF、多对象索引、comparison 和回答器，范围过大。提前交付基础问答是调整里程碑，不是降低最终七条纵切标准。

## 应补入对应工作包的交接项

以下是明确责任与恢复边界的补充，不单独据此阻止 W1 起草：

- **PDF blob 的安装者与路径。** [prepare.py:244](/Users/huangzhanpeng/python_code/video-paper-wiki/src/video_paper_wiki/commands/prepare.py:244) 从 blob store 读取；默认路径是 `.work/blobs/<sha>`，而 research 自有输出只允许 `.work/research/**`。外部 operator 可以提供该 blob，因此不能断言架构上绝对无法完成；但 W2 必须写清其交付路径、校验与幂等/冲突行为，不能只写“给一个 PDF”。不必为此恢复 agent 的 `ingest put`。
- **decision 的保留策略。** R2:187 将 session/preview 称为可丢弃、可重建，但真实用户选择和原始 LLM 输出不能保证精确重建。明确选中输入的保留期、清理约束及丢失时的恢复错误；哈希不是原始内容的备份。
- **规划材料的持久交接。** R2/审计/冻结仍是 local untracked；task-index 仍记录旧接续点。未来交付应同步接续索引并持久化评审证据。关联任务和冻结中已经记录历史 GO，不能因仓库缺少独立报告就断言历史 GO 不存在；现有形式的跨 checkout 可审计性仍需改善。本次保留历史，不重写旧冻结。

## 外部能力抽查及其限度

本次 Web 工具打开方案中的 legacy API 示例 URL 返回 `Internal Error`；同一论文的[官方摘要页](https://arxiv.org/abs/2311.15127)可返回题录和摘要。一次错误不证明 API 长期不可用，网页成功也不证明 Atom/raw headers/redirect/DNS 能力已经具备。R2 的 `CAP-WEB-OBS-001` 因此仍是有效前置检查，不是可以略过的文档项。API 返回 Atom 的合同以 [arXiv 官方手册](https://info.arxiv.org/help/api/user-manual.html)为准；若改用网页规范化输入，需显式修订 metadata adapter，不能把网页包装成原始 Atom。

OpenAlex 在 2026-08-19 更新的[认证文档](https://help.openalex.org/api/authentication/)允许 basic keyless 使用，并说明 key 提高额度、预算/速率超限会返回 429。不能依据二月旧公告简单断言所有请求均须 key。W3 仍应冻结实际 executor、预算、退避和降级路径；本次未调用用户凭证或完整验证 OpenAlex discovery。

## 建议的开发顺序

1. 完成实际 connector 能力观察，冻结并实现 W1：链接→abstract-only 摘要→选择。先形成可运行的入口，不再扩写架构范围。
2. 冻结 W2 的 selection/source binding、外部 blob 交付和 parser 四件套交接；完成单篇入库与中断恢复。工程结果与真实 operator/Obsidian 验收分别记录。
3. 尽早交付基于已入库论文的基础引用问答，并用必答要点验证有用性。
4. Discovery 与 code discovery 按统一依赖并行；先修正官方性规则，再做代码问答和复现计划。
5. 按真实查询需求增加 domain annotation、typed graph、严格实验比较和文章生成；MCP、community/性能优化仍后置。

该顺序是本次 review 的建议，不是对原 R2 的自动改写、重新冻结或实现授权。正式变更应形成 successor；本次只新增本报告，未修改生产代码、旧证据或任何 gate。

## 独立审查处理

Builder 与 Repo Steward 分别完成只读审查；两者都独立确认 Docling 产物缺口。Builder 另确认版本绑定和官方性误判；Steward 确认依赖图/入口表冲突及持久交接缺口。Architect 将“没有 agent blob 写接口”收敛为外部输入责任待明确，将“缺少独立仓库报告”收敛为证据持久化问题，未把它们扩大为所有开发必须停止的结论。
