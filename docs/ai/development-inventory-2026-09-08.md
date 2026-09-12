# 开发余量盘点 · 2026-09-08

本次按实际代码、后续用户范围调整及最新 CI 盘点。结论是：**最近交付的轻量 PDF 主链路已经完成；完整研究知识库仍有后续开发。建议近期拆成 5 个小包，若全部选择，粗估 12–22 人日；原始完整 PRD 则是另一组更大的工作。** 这些估算供排序，不是已批准的新工作包或工期承诺。

盘点基准为集成工作区 `3368c6435db166a285b4b0e2df00f5d6a7491956`，产品代码与已验收的 `809627bfa0deb8c1b1393f731bf3cb9a3c21ee66` 相同，最新提交只变更协调文件。没有使用主工作目录里旧分支的产品代码推断当前完成度。旧 TODO/PRD 的未勾选框和“尚未实现”段落存在过时信息，不能直接计数。

[最新 Tests 运行 34176699951](https://github.com/RyanHuangNLP/video-paper-wiki/actions/runs/34176699951) 已完成，Linux/macOS × Python 3.12/3.13 四项均成功，head 为 `3368c643`、attempt 1。这是本次只读状态观察，不代替新的精确提交验收或真人审核。观察记录见 [CI 记录](../../artifacts/verification/manual-pdf-v1/four-agent-cursor-cli-v1/development-inventory-ci-2026-09-08.json)。

## 已实现的用户能力

| 能力 | 当前状态与实际边界 |
| --- | --- |
| 手动导入 PDF | 原生文本提取、逐页来源、PDF 摘要、轻量 Markdown/小型记录；不复制 PDF、图片或模型。重复导入保留用户笔记。 |
| 检索和带引用问答 | BM25、显式论文选择、实际原文/页码、来源变化检测和引用校验已接入公开 CLI/Skill。 |
| 多论文简单写作 | 可以选择多篇论文，交当前会话模型生成带引用的可编辑 Markdown 初稿。 |
| 中断后继续 | prepare/status/complete、持久会话、重复执行、冲突和过期状态处理已实现。 |
| 工作区诊断 | inspect 可检查工作区、来源、索引及事务问题；会话由 workflow status 查看。 |
| 正式知识库底座 | 代码证据、知识编译/发布、catalog/query、审计及正式 Vault 备份恢复已有实现；轻量阅读工作区与这些正式流程仍有边界。 |

轻量入口的主要证据见 [使用说明](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/docs/lightweight-pdf-quickstart.md)、[公开 CLI](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/cli.py:61)、[会话编排](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/light_workflow.py:1401) 和 [来源引用检查](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/light_context.py:123)。

## 建议近期考虑的 5 个工作包

| 工作包 | 还需完成什么 | 粗估 |
| --- | --- | --- |
| 1. 结构化知识整理与入口衔接 | 将轻量原文接到摘要、方法/实验/局限等知识建议、主题/概念及基础论文关联。复用已有知识接口；先明确原文与建议的来源关系。 | 3–7 人日 |
| 2. 论文库维护 | 公开的删除、更新/替换、元数据编辑入口；保护已有笔记，并正确标记或重建索引与旧会话。当前主要覆盖新增和重复导入。 | 2–3 人日 |
| 3. 轻量成果备份与恢复 | 保存 Markdown、用户笔记、小型来源记录和会话；定义外部导出草稿的范围，提供清单校验及隔离恢复。 | 2–4 人日 |
| 4. 基础多论文比较 | 在现有选文和写作上补明确的比较模板/表格、逐项引用、条件差异及“证据不足”。不包含完整比较图谱与严格 benchmark。 | 2–3 人日 |
| 5. 真实论文使用验收与质量修复 | 建议先用 5–10 篇真实论文跑一组中文提问、跨论文问答、草稿和重启场景；记录漏检与来源错误，再做有界修复。 | 3–5 人日 |

合计 **12–22 人日**。一个人日指有经验工程师的一天工作量，包含实现与必要测试。AI 并行执行时间不能简单用这个数字除以代理数量；模型耗时、排队和人工阅读另算。

第 1 项对应更完整的知识库使用需求，但这里的 3–7 人日只估有界知识建议和接口衔接。**正式 canonical 发布尚需解决轻量原文的来源授权及存储合同**：旧发布路径绑定 captured PDF/receipt，不能直接套到“不复制 PDF”的轻量工作区，也不能伪造 Docling 产物。若选完整受管发布、多版本、图表公式定位，须按下节大包重新估算，不能沿用 3–7 人日。

第 2、3、4 项是建议的后续能力，不是已冻结轻量入口交付包遗漏的验收项。特别是，第 3 项的独立轻量备份流程没有被当前轻量迁移合同明确冻结，FABLE-008 的产品选择仍保留。正式 Vault 备份底座已经存在，但其清单要求 receipt-backed Vault，不覆盖任意轻量工作区；参见 [backup_manifest.py](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki/backup_manifest.py:122)。

第 5 项包含验收工程及有限修复，不预先保证真实论文语义质量。5–10 篇是本次建议的首轮样本，不是既有 PRD 的正式验收标准。真实许可、claim 判定及人工视觉评审不包含在人日中。

中文问题目前有同语言词法限制：引擎没有跨语言语义检索，但 Skill 已提示无结果时尝试英文关键词。后续可以先把这个当前模型的检索词改写流程和真实案例做好，不需要直接引入 embedding 服务。参见 [词法索引](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/light_index.py:83) 和 [已有 Skill 回退提示](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/.agents/skills/video-paper-read/references/workflow.md:47)。

我的排序建议是：**先做第 1、5 项，共约 6–12 人日，把真实论文上的知识整理和使用效果做实；再做第 2、3 项；比较模板按实际使用需要增加。** 这只是本次盘点建议，没有启动开发或代替后续合同冻结。

## 如果目标仍是原始完整研究 Wiki

下表对应原始 R3.3/plan-r2 的更完整目标，不能全部列为当前轻量版本的必修尾项。各包包含已有底座的集成、剩余功能和验证，不是从零重写；也与上节小包有重叠。

| 完整目标中的剩余大包 | 主要差距 | 粗估 |
| --- | --- | --- |
| 完整单篇知识入库及版本生命周期 | 正式来源衔接、版本管理、知识提案/审核/发布、复杂定位和连续状态 | 12–20 人日 |
| 官方代码及配置关联 | 官方性证据、论文—仓库—commit—文件/配置关系及真实仓库验证 | 8–15 人日 |
| 知识图谱、矛盾与严谨比较 | 类型化关系、条件约束、支持/反对证据、不可比较结果及图/检索衔接 | 20–35 人日 |
| 高级综述及复现方案 | 比较矩阵、段落支持检查、正式文章产物和绑定代码/配置的复现计划 | 10–18 人日 |
| 完整真实语料及语义评测 | 独立 gold、难负例、检索和回答支持度、多轮模型评测及回归 | 12–20 人日 |
| 完整产品使用与维护 | 跨目录成果保留/恢复、Obsidian 视图、故障入口、迁移与必要适配器 | 10–18 人日 |

这 6 包简单相加为 **72–126 人日**。尚未按实际选定范围去重，因此只能说约 **70–125 人日量级**，不能当作已排定工期，也不能与上节 12–22 再相加。

在线论文发现、arXiv/OpenAlex 预览与版本发现另约 **12–20 人日**，已明确延后。若把它也选入原始完整愿景，7 包毛合计为 **84–146 人日**。OCR、额外模型/权重下载、视频摄入、多用户及第二套桌面客户端不计入当前范围。正式文章、多版本图谱和在线发现均不能由这次盘点自动获得实施授权。

## 仍然开放的验收与交付事项

- 当前 67 条 catalog/overlay 是目录种子，不能按 67 篇已完成全文知识整理计算。
- 单篇真实 PDF 演示、工程 fixture 和 CI 通过，不能替代真实语料上的回答正确性与知识覆盖率验收。
- 原计划中的真实论文/仓库、许可来源、claim 审核、检索 gold、Obsidian 视觉以及备份锚点等要求仍需按实际选择的产品范围完成；这些主要是数据和人工验收，并非都要新写代码。
- 当前开发任务的 draft PR → integration 交付边界保留；本次没有修改代码、启动开发、提交、推送、合并或恢复自动调度。

范围依据：[手动 PDF 范围](packets/RESEARCH-WIKI-MANUAL-PDF-SCOPE.md)、[人工 PDF 首版补充](video-paper-wiki-manual-pdf-v1-addendum.md)、[后续轻量迁移](packets/RESEARCH-WIKI-LIGHTWEIGHT-PDF-MIGRATION.md)、[原始 PRD R3.3](video-generation-research-wiki-v1-prd-r3.3.md)。

独立核查最初记录见 [原始 backlog 审计](../../artifacts/verification/manual-pdf-v1/four-agent-cursor-cli-v1/product-backlog-audit-r1.json)。该原始记录保留历史，其“approved”分类和净估算随后经复核纠正；本报告采用后续用户范围优先的分类，不沿用那些过宽的完成要求或不一致的净估算。
