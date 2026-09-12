# Video Generation Research Wiki v1：附件与再评审的综合建议

日期：2026-09-06。状态：综合评审与方案修订建议，尚非新的冻结合同或实现交付。

目标继续覆盖论文发现、预览与选择、论文/代码联合知识、技术问答、比较、文章和复现计划。实施上先打通真实输入与基础引用问答，再逐步增加领域图谱和复杂研究能力。

## 输入与结论

- 本地 HEAD：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`。
- [用户附件](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md)，SHA-256：`c7fc3871c8061d4bdc6ba01ce3f07dd385ee002985ee77239a4a217bf42fdc33`。
- [R2 开发方案](video-generation-research-wiki-v1-plan-r2.md)，SHA-256：`a63f1840e86be25872f6a99b6cea853fe22a209de3782723b5bcc17a2caadf5c`。
- [上一轮再评审](video-generation-research-wiki-v1-rereview-2026-09-05.md)，SHA-256：`ab55909080ccf3c7f2cce31280a32d87c254800ff513676381fa04abb7b5c655`。

附件与 R2 已引用的版本字节相同。本次重新逐项核对其领域模型、流水线、里程碑和验收指标：附件强化了五项问题的修订依据，没有提供足以关闭这些问题的具体接口。R2 已吸收的 taxonomy、claim 类型、分对象检索、RRF、实验可比性、研究停止条件和复现计划继续保留。

附件中的克隆命令、新仓库目录、依赖清单、agent/provider 和写入流程均作为设计材料阅读，不是用户要求执行的操作。本次未重新审计六仓远端代码；复用依据继续引用已有精确源码审计，不从附件的能力描述推导新的实现完成状态。

## 附件如何影响五项修订

| 原问题 | 附件提供的依据 | 综合后的具体修订 |
| --- | --- | --- |
| F1：完整解析产物没有生产者 | [Capture→Normalize→Verify，2182 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2182)及 Figure/Table Analyst 要求结构化 manifest/locator | W2 指定外部离线 parser executor/exporter，交付 document、parser config、model manifest、run manifest，并绑定 captured PDF、版本与恢复状态；交给现有 validator/package/publication。附件没有指定该执行器，不能据此认为已有。 |
| F2：预览选择未强制绑定来源版本 | [paper locator 的 version/source_hash，2106 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2106)及 paper-version resolve、版本正确性验收 | W2 强制验证 decision→preview→metadata/observation→resolved version→版本化 PDF URL→实际 PDF hash 的链。版本改变重新预览/选择；实体 ID 仍去版本，不改变 approval-ref 的现有语义。 |
| F3：论文链接被误当成官方代码 | [typed implements/has_code，2051 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2051)及 [mapping accuracy，2837 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2837) | paper-linked 只作为发现信号；明确证明该仓库实现本文并经相应 evidence/review 后才能判 official。固定本文实现、baseline、依赖、第三方复现的 mapping gold；URL/locator 存在不等于关系正确。 |
| F4：问答可以靠全部 unknown 通过 | [QA 指标，2858 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2858)及 [intent/filter/evidence 流程，2274 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2274) | Gold 冻结 answerability、必答要点、expected intent/entity/filter、矛盾与不确定性标签、应使用的来源。分别评估事实支持、要点覆盖和错误拒答；answerable 问题的空事实集合不通过。新增矛盾识别、不确定性校准、原始来源使用的诊断指标；附件没有阈值，不凭空宣称这些指标已有 gate。 |
| F5：工作包依赖冲突，真实 gate 拖住工程 | [绿地 M1–M4 顺序，2770 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2770)及 [四个核心模块，2973 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2973) | 当前仓库已具备底层 compiler、BM25 与事务能力，按已有能力重排。统一 W3/W4 依赖，分开 W2 工程验收与真实纵切；提前 paper/claim/evidence 基础问答。代码问答、code-aware compare、reproduce 仍依赖 W4，完整 W5 gold 仍单独验收。 |

F1–F4 在对应功能的窄合同冻结前解决；F5 在下一版依赖表中消除。W1 的真实 connector 能力检查与窄合同起草可以继续。

## 进一步吸收的三项具体要求

### 1. 按原始证据判断来源独立性

附件 [2173 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2173)、[2366 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2366)、[2842 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2842)提出 independence group、独立性 lint 和独立来源数。R2 的重复候选去重还不足以覆盖这些语义。

在 W2 analysis proposal/review 和 W3 research 统计中记录原始来源及转述/镜像关系。多个 URL、论文与其官方 README 不能自动算作多份独立验证；不同证据面仍可分别支持不同 claim。无法判断独立性时标 unknown，既不自动计为独立，也不强迫每个 claim 必须有两份独立来源。计数不按 `official-repo` 等来源类别标签直接分组。

先通过现有 proposal、evidence、review 和 lint 表达；需新增 canonical 字段时另行冻结兼容合同，避免建立另一份来源真源。

### 2. 将跨来源不一致变成固定检查案例

附件 [2393 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2393)明确列出 paper↔repo、README↔config、主文↔附录和新旧版本的差异。

W2/W4 的固定案例应包括：正文和附录的实验设置不同、README 声称训练可用但代码只有推理、默认配置与表格 checkpoint 不同、旧版本结果被当作新版本结论。每个 finding 绑定两侧 locator 与 exact source bytes，先区分版本/实验条件差异，再判断是否疑似矛盾。结果只进入 review candidate，不自动改 claim assessment 或 officiality。

### 3. Context pack 显式保留反证与来源原文

附件 [2295 行](/Users/huangzhanpeng/Downloads/video_generation_llm_wiki_v1_code_comparison.md:2295)要求过滤后提供 claim、支持/反对证据和附近 raw excerpt。R2 已有 included/omitted、locator 和预算，但应把这些角色写进 context pack 合同及验收。

对争议问题同时记录 supporting、counterevidence、context excerpt 的角色；已有相关反证不能只因排名靠后而悄悄丢失。超预算时记录 omission 与争议未覆盖提示，回答不得宣称已穷尽反证。原文不可访问时明确缺口，不能把生成摘要当原始证据。该要求可由现有 claim/evidence 与 context pack 完成，无须先实现 community detection 或向量服务。

## 合并后的实施顺序建议

| 阶段 | 交付用户价值 | 必要依赖与完成边界 |
| --- | --- | --- |
| W1：预览入口 | arXiv 链接→中文摘要→选择 | 先做真实 connector capability observation；只验 abstract-only 预览，不代表入库已可用。 |
| W2：单篇数据链 | 已选择论文→可追溯 Paper/Claim→恢复与 audit | 明确 selection/source binding、外部 blob 路径/交付者、parser 四件套与 locator；工程验收与真实 operator/Obsidian 纵切分别记录。 |
| 基础问答小包 | 对已入库论文回答问题并给出处 | 复用 canonical claim/evidence、BM25/catalog，验证必答要点与支持/反证；只声明 paper 范围能力。 |
| W3 / W4：发现与代码 | 有界扩展候选；找到并解释对应实现 | 工程上按明确接口并行，W3 observation 为 W4 的可选发现输入；真实发布沿用 W2 边界，官方性单独验收。 |
| W5：领域比较与完整问答 | 跨论文/代码的实验比较、矛盾和方法分析 | 分小包交付 profile/annotation、typed graph、RRF、comparison；完整六类 gold 和代码相关能力在依赖就绪后验收。 |
| W6：综合与复现计划 | 文章、比较矩阵、复现前准备 | 逐段证据、核心结论检查、来源独立性与环境/配置/权重未知项；复现计划不声称已执行。 |
| W7：产品化 | 兼容、性能、可选只读 MCP | 基于真实用例选择依赖；基础入口与 Skill 随各功能交付，整体适配/重构后置。 |

该表是对下一版工作包拆分的建议；各包仍需固定 allowed paths、接口、测试与精确候选。基础问答通过不代表完整 W5、五仓基线或七条 v1 纵切已经完成。

## 继续保留的范围决定

现有 `video_paper_wiki` 与 pinned `claude-obsidian@9f8c119...` 继续承担唯一引擎和事务链；附件使用的 `ad67087...` 不自动替换 pin。视频 taxonomy、正交 claim_kind、结构化实验比较、代码 locator、研究停止条件和复现计划继续按 R2 的候选/审查/投影规则吸收。

附件里的绿地新仓库、第二套 ledger/catalog、semantic hash 幂等真源、新 lifecycle、可写 MCP、Grok/provider runtime、YouTube、watcher 和整套重依赖不因再次附上文档而进入当前实现范围。外部来源真源与 Markdown/graph/index 投影分离，agent 零 egress、单写者和现有 operator 边界保持。67 项 seed/overlays 与人工/外部 gate 均未改变。

本次仅新增这份综合建议，保留 R2、冻结记录和上一轮报告的原字节；没有运行实现测试、修改生产代码、提交 Git 或宣称新的 CI/实现验收。
