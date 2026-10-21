# 当前会话自动接续

用户已授权四个总 Agent 的持续自动开发，无需重新登录、改模型或重开主控。Astra 显式接续三个 Luna/xhigh，每人只管理一个活动 Builder（默认 CLI，技术故障时按 [GUI-FALLBACK.md](GUI-FALLBACK.md)使用 GUI），按主控指令调度四个逻辑 lane，Builder 留在原 source。核对最新交接及停写后，控制器运行已冻结任务；主控自动审查、返修、汇合集成，完成当前工作包要求的验收及授权内 draft PR/CI。

中断后读取 README.md、CONTROLLER.md 和 artifacts/verification/manual-pdf-v1/four-agent-cursor-cli-v1 最新状态，核对 PID/lease，恢复精确 chat ID，不重复启动。

如果最新状态已经完成，或自动接续已经暂停，不凭本启动说明重新运行历史任务。
明确的审批拒绝不能通过 GUI 备用入口绕过。

历史工作包及 CURRENT/PID/lease 记录仅在原本地工作区保留。缺少时先核实或准备新的冻结任务，不能推断旧任务仍应运行。
