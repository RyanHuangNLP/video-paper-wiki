# 当前四 Agent 自动开发编排

用户在 2026-09-08 接受四个总 Codex Agent：Astra 主控 + 三个 Luna 控制器，最多同时管理三个 Cursor CLI，调度原四个逻辑工作包。此包替换尚未安装的 five-agent-cursor-cli-v1 候选，保留原 lightweight-workflow-v2 合同、25 个产品路径、工作区和人工 gate。

| 角色 | 模型 | 工作 |
|---|---|---|
| Astra | gpt-6-astra / ultra / Fast（priority） | 自动拆包、独立验收、返修与串行交付协调 |
| lw_cursor_1 | gpt-5.6-luna / xhigh | 管理 Cursor CLI 第 1 路 |
| lw_cursor_2 | gpt-5.6-luna / xhigh | 管理 Cursor CLI 第 2 路 |
| lw_cursor_3 | gpt-5.6-luna / xhigh | 管理第三个 Cursor CLI；完成后接收主控下一项工作 |

所有 Builder 均使用账户已列出的精确 ID cursor-grok-4.6-xhigh-fast。用户交互终端显示相同默认组合；显式绑定只保证自动调用不漂移，不修改默认模型。已在正常系统环境确认登录；沙箱报告 unauthenticated 不代表用户未登录，不要重复要求登录。

每路保留 .work/parallel/lightweight-workflow-v2/terminal-N/source。T1/T2 独立开发，T3/T4 先做自有工作再接收冻结依赖。每个控制器同时只管理一个 CLI。四个逻辑 lane 不要求同时运行；主控在上一个 Builder 停写并完成核验后，给空闲控制器安排下一 lane。切换 lane 使用新的明确 workspace/chat/run，不能恢复另一 lane 的旧 chat。启动子代理必须显式指定 Luna/xhigh，不新增代理。

先读 CONTROLLER.md、原 COMMON/CONTRACT/freeze、最新 Architect CURRENT 和各路实际最新 handoff。本次用户指令覆盖旧手动转交、两子代理、Grok Build CLI、五 Agent 要求，其余产品约束不变。进度文字不能代替源码和测试摘要。

持续流程由 Astra 管理：冻结任务 → Luna 管 Grok 实现和交接 → 独立核验 → Astra 接受或返修 → 接收依赖 → 完整集成。合同内常规失败自动返修，不让用户搬运提示词。实际完成即停，不用等待凑时长；范围决策或人工审批才交用户。

交付仍为 draft PR → integration，禁止自行 merge/main/关闭人工 gate。全部 Builder 停写并获精确验收后，Astra 可将一位既有 Luna 临时改任串行 Repo Steward，不增加常驻代理。当前运行时具备主控+三个子代理；配置解析或进程退出 0 都不代表产品验收。具体运行状态以本轮 evidence 为准。

每个 Luna 约每 30 秒核对所管进程与增量日志。一旦观察到退出、正式 final、错误或 needs_input，立即发给 Astra；Astra 核验候选后安排返修或下一项，不等用户催促，不等其他两路全部结束。控制器发送通知后保持可接续，不自行无限扩大工作范围。

## Cursor App 备用入口

用户已要求保留 Computer Use 操作 Cursor App、粘贴冻结提示词并启动任务的备用流程。
CLI 因启动、崩溃或通信协议等技术故障不可用时，可以按
[GUI 备用协议](GUI-FALLBACK.md)自动切换，沿用已授权的工作包、工作目录、模型和审批设置。
每位控制器同时只有一个 Builder（CLI 或 GUI）；整个 Cursor 界面同时只有一个操作所有者。
权限、安全、自动审批、内容或配额拒绝不能通过切换入口绕过；原因不明时先核实。
本协议是后续调度规则，不会重启已完成的工作包或暂停中的自动接续。

## 已完成范围与本次仓库收录

`lightweight-workflow-v2` 已在产品提交 `809627bfa0deb8c1b1393f731bf3cb9a3c21ee66`
完成验收，自动接续已暂停。上文的四路调度描述是既有工作方式；本说明不是重新启动指令。
后续只有新的已授权且尚未完成工作包才可派发。

本次收录团队入口、控制器/GUI 协议和标准库 CLI helper。helper 固定使用原机器上的
源码、凭据入口和证据路径，不会创建完整运行环境。历史 COMMON/CONTRACT/freeze、
原始交接和模型日志仍保留在原本地工作区，并未由本次提交携带；不得把缺少这些材料的
新 checkout 当作已准备好的开发环境。当前产品使用说明见
[PDF quickstart](../../../lightweight-pdf-quickstart.md)。
