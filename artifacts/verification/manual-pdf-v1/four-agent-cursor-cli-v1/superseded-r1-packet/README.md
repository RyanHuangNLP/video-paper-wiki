# 当前四 Agent 自动开发编排

用户在 2026-09-08 接受四个总 Codex Agent：Astra 主控 + 三个 Luna 控制器，管理原四路 Cursor CLI。此包替换尚未安装的 five-agent-cursor-cli-v1 候选，保留原 lightweight-workflow-v2 合同、25 个产品路径、工作区和人工 gate。

| 角色 | 模型 | 工作 |
|---|---|---|
| Astra | gpt-6-astra / ultra / Fast（priority） | 自动拆包、独立验收、返修与串行交付协调 |
| lw_cursor_1 | gpt-5.6-luna / xhigh | 管理 Cursor CLI 第 1 路 |
| lw_cursor_2 | gpt-5.6-luna / xhigh | 管理 Cursor CLI 第 2 路 |
| lw_cursor_34 | gpt-5.6-luna / xhigh | 分别管理第 3、4 路两个 CLI |

四个 Builder 均使用账户已列出的精确 ID cursor-grok-4.6-xhigh-fast。用户交互终端显示相同默认组合；显式绑定只保证自动调用不漂移，不修改默认模型。已在正常系统环境确认登录；沙箱报告 unauthenticated 不代表用户未登录，不要重复要求登录。

每路保留 .work/parallel/lightweight-workflow-v2/terminal-N/source。T1/T2 独立开发，T3/T4 先做自有工作再接收冻结依赖。控制器 34 可同时管理两个进程，各自加锁、记日志、交接，不合并写权。启动子代理必须显式指定 Luna/xhigh，不新增代理。

先读 CONTROLLER.md、原 COMMON/CONTRACT/freeze、最新 Architect CURRENT 和各路实际最新 handoff。本次用户指令覆盖旧手动转交、两子代理、Grok Build CLI、五 Agent 要求，其余产品约束不变。进度文字不能代替源码和测试摘要。

持续流程由 Astra 管理：冻结任务 → Luna 管 Grok 实现和交接 → 独立核验 → Astra 接受或返修 → 接收依赖 → 完整集成。合同内常规失败自动返修，不让用户搬运提示词。实际完成即停，不用等待凑时长；范围决策或人工审批才交用户。

交付仍为 draft PR → integration，禁止自行 merge/main/关闭人工 gate。全部 Builder 停写并获精确验收后，Astra 可将一位既有 Luna 临时改任串行 Repo Steward，不增加常驻代理。当前运行时具备主控+三个子代理；配置解析或进程退出 0 都不代表产品验收。具体运行状态以本轮 evidence 为准。
