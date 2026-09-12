# RESEARCH-WIKI-R3-PRD-REVIEW

日期：2026-09-06。范围：开发方案与 Markdown 评审接口；不实现研究产品。

- 用户目标：最终形成开发方案，并提供 Fable 5.1 可以 review、与 Codex 讨论的入口。
- 用户已明确接口形式为 Markdown PRD 文档，不需要模型 API、CLI bridge 或网络服务。
- 基线：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`。
- 输入：R2 方案、Pro 六仓对比附件、2026-09-05 再评审和 2026-09-06 综合建议。
- Architect 单独拥有 `docs/ai/video-generation-research-wiki-v1-prd-r3.md` 和本工作包。
- Builder：只读检查 PRD 的完整目标、模块职责、F1–F5 修订和可执行性，反馈给 Architect；不写 PRD。
- Repo Steward：只读检查依赖、验收与事实状态；在 Architect 交接后，单独编写 `docs/ai/fable-5.1-review-entry.md`，不写 PRD。
- 两个子 agent 使用显式配置的 `gpt-5.6-sol / medium`，不增加 worker。主控实际设置按当前运行记录，不由文档热切换。
- 不改生产代码、schema、依赖、CI、seed/overlays、旧计划或旧证据；不运行 Docling/admin，不修改真实 Vault，不执行 Git/PR mutation。

## 交付合同

1. 一份自包含中文 PRD：目标/非目标、用户流程、当前状态、可借鉴架构、模块与数据所有权、版本和恢复语义、工作包依赖、验收、风险与首次研究里程碑。
2. PRD 含稳定需求与章节编号、专属 Markdown 讨论区、Fable finding/Codex reply/决策格式、冲突与修订规则；外部 review 状态如实保留为尚未收到。
3. 一个可复制给 Fable 5.1 的 Markdown 入口，支持本地文件访问和附件/人工转交两种方式，点名 PRD、评审问题、输出位置和格式。
4. 明确本次只交付方案与接口。PRD 成文、内部文档核验、Fable 实际 review、后续实现验收是不同结果；本任务不伪造 Fable 回复。

## 本地验收

- 两个子 agent 独立检查同一 PRD revision；Architect 处理必要修订。
- 检查需求到工作包/验收的覆盖、依赖无环、Markdown 本地链接与行号、review 模板可填写且无需特定 API。
- 核对旧输入摘要不变、Git tracked/staged 无修改；新产物只在上述三条路径。
- 只做文档验证，不以工程全量测试证明文档质量，不将历史 2152-test CI 重标为本次验收。

## 内部初审与修订输入

两位 reviewer 均读取 R3.1 初稿，全文 SHA-256 为 `3a96bf3527f48de26b28ca76cdcc8fdb2bd17d5fc47fd26a7d5a315ffb9be9ff`。Builder 为 `CHANGES_REQUIRED`，Repo Steward 为 `CHANGES_RECOMMENDED`；没有给该初稿签发最终 GO。

Architect 接受以下修订：明确 W0-R3/W1 的依赖与入口条件；拆出有完整 E 的首次比较报告工作包；补齐 canonical/projection/context 的产物和代码归属；点名 REQ-09 的 W7 入口及验收；固定质量评分的单元、分母、review 与争议规则；为评审正文定义不受评论追加影响的摘要。另修正 W0-R3 已在进行而 W1–W7 实现未开始的状态措辞。R3.2 完成后由两位 reviewer 对新的 exact bytes 重审，初审结论保留在此，不转授给 successor。

## R3.2 文档交付验收

- PRD 全文 SHA-256：`dddf743620c6920aca294ed732992e4ddc85e28ae739005071ee71b051a429e4`。
- PRD 正文前缀 SHA-256：`1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24`；范围由 §15.1 定义，后续讨论不改变正文身份。
- Fable 入口 SHA-256：`00c504e74a028b203c40227c2c6d3bcdeee0a0eeb4b4b23d20a8acf36a1fe5e7`。
- Builder 与 Repo Steward 对上述精确 PRD 各返回 `GO_FOR_FABLE_5_1_EXTERNAL_REVIEW`；两者都独立重算正文摘要。Steward 单独完成入口，Architect 读取全文验证了本地与附件/人工转交两条路径。
- Architect 文档核验：10 个需求均有工作包归属；10 节点依赖图无环；正文 15 个顶级章节、讨论模板和本地链接有效；入口明确在 §15.3、§15.4 之前插入评论，示例编号不计为真实 finding。
- 七个 R2 frozen input 及 R2 freeze、再评审、综合建议共十项历史摘要不变；本地 HEAD 仍为上述基线，tracked/staged 无修改。本文不声称检查过本次无关未跟踪文件的全部字节。
- 文档验收决定：`ACCEPTED_PRD_AND_MARKDOWN_REVIEW_INTERFACE_LOCAL_R3_2`。仅证明本次方案与交接接口交付，不是实现、远程 CI、Fable review、真实 gate 或合并验收；实际 Fable 状态为 `awaiting_fable_review`。本次没有为文档运行工程全量测试或进行 Git/PR mutation。
