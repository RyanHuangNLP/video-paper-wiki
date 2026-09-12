# Fable 5.1 评审入口

待评审文档：[Video Generation Research Wiki v1 PRD R3.2](video-generation-research-wiki-v1-prd-r3.md)

本地绝对路径：`/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-prd-r3.md`

- 评审版本：R3.2
- 全文 SHA-256：`dddf743620c6920aca294ed732992e4ddc85e28ae739005071ee71b051a429e4`
- Reviewed body SHA-256：`1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24`
- 本地核验：已按 PRD §15.1 的原始 UTF-8/LF 前缀范围实算正文摘要，与文档声明值一致。

如果评审平台能读取本地文件，请提供绝对路径和下方提示词。如果不能，请上传 PRD Markdown 附件并提供同一提示词。若平台不能写回本地文件，请让评审者返回完整新增 Markdown 块，再由用户转交给 Codex 插入 PRD 的 §15.3、`### 15.4` 标题之前。

## 可复制提示词

```text
请评审随附的《Video Generation Research Wiki v1：开发方案与联合评审 PRD》R3.2。若当前平台能读取本地文件，路径是：
/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/video-generation-research-wiki-v1-prd-r3.md

被评审正文是文件标题、版本说明和 §1–14。Reviewed body SHA-256 为：
1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24

正文摘要范围遵循 PRD §15.1：从原始 UTF-8/LF 文件第一个字节开始，到“## 15. Fable 5.1 ↔ Codex Markdown 评审接口”标题前的全部字节，并包含该标题前的空行，不做空白归一化。若你实际按此规则计算且结果相同，请标注“已核验”；若无法计算，只能标注“文档声明值/未核验”，不得声称完成了字节核验。

你可能只会看到这份 PRD 附件；§1–14 是自包含的核心开发方案，§15 是评审接口。请以实际可见内容完成评审。§14 引用的旧方案、审计和附件只是可选证据；只有在确实读取某项材料后才能引用，不要声称读过不可访问的文件，也不要因缺少可选材料而停止评审。

请重点检查：
1. 完整目标和 REQ-01–10 是否保留，Pro 设计是否被合理采用；
2. 当前能力与“尚未实现”的状态是否准确区分，规划项是否被误写成已完成；
3. F1–F5 是否有闭合路径，输入、版本、解析、恢复、发布、产物和实现所有权是否一致；
4. §9 是否是唯一、无环且明确的实施依赖表，W5b1/W5b2、首次里程碑和 E/S 退出条件是否可执行；
5. §10 的 retrieval、answer usefulness/support、comparison、article/reproduction 标准及评分裁定规则能否稳定衡量研究价值；
6. 3-paper/1-repo 首次里程碑能否产出有用结果，领域比较或研究流程是否被过度后置；
7. W7 的 REQ-09 检查、备份、隔离恢复入口，以及整体工作量、复杂度和风险排序是否合理。

不要执行工程实现、下载、真实 Vault 或 Git 操作。不要把尚未实现的下一包任务本身列为缺陷，也不要伪造外部证据或 GO。

Reviewer 字段必须反映当前平台实际选择的评审模型。若平台不能验证模型身份，写“用户所选模型/未验证”；不要通过角色扮演声称自己是某个模型。

每条真实意见须选择 §15.3 中尚未使用的下一个 FABLE 编号，并保持后续引用稳定。§15.3 代码围栏里的 FABLE-001 只是模板，不是已提交意见；第一次外部评审可从 FABLE-001 开始，已有真实意见时则顺延。每条采用下面格式，不要代填 Codex 的立场或结论：

### FABLE-001 · 简短标题
- Reviewer：当前平台实际选择的模型；无法验证时写“用户所选模型/未验证”
- Reviewed revision：R3.2
- Reviewed body SHA-256：1c5c42db4d55bc66357a3ff7fc3ca549f7a272e8ebc193a533271ae3806eed24（已核验 / 文档声明值、未核验）
- Severity：blocker / major / minor / suggestion
- References：REQ-xx；§x.x；Wx
- Scenario / evidence：具体触发条件及 PRD 内依据；假设和未验证外部材料须注明
- Impact：对研究用户或工程交付的影响
- Suggested change：最小可行修改与取舍
- Verification：怎样证明问题已解决
- Status：open

#### Codex reply to FABLE-001
- Position：
- Reason / evidence：
- Planned resolution：
- Verification result：未验证
- Status：open

最后追加：
- Verdict：ready_for_packet_drafting / changes_requested / needs_information
- 最值得保留的三项设计：列出三项并说明理由

若没有发现问题，不要虚构 finding；直接给出 verdict、审查范围、未核实材料和三项应保留设计。Verdict 只是设计意见，不是实现验收、人工 gate 或 merge approval。

如果有本地写权限，将完整新增块插入 PRD §15.3 的讨论区末尾、`### 15.4 决策与修订记录` 标题之前，保持 §1–14 和现有讨论不变；否则仅返回完整新增块，供用户转交给 Codex。不要把内容简单追加到文件末尾，也不要改写或删除既有讨论历史。
```
