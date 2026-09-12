# Codex 复审：NEEDS_CHANGES，暂不重启部署

日期：2026-08-30。审核对象为当前磁盘代码及 GROK_DEVELOPMENT_RESULT.md。

先前由 Codex 启动的 Grok 开发进程 47494 尚未退出，且提示源码读取期间发生变化；已发送 SIGINT 并确认退出 130，防止继续与用户交回的代码并发修改。以下结论基于停止该调用后的文件，不把该次中断当作成功交付。

## 已核实

- 完整测试复跑：74 tests，OK，2.116s；真实 Hermes Platform 测试未跳过。
- 普通 Enum 适配器键查找修复覆盖了已知发送失败根因。
- `/dev-resend` 为 human-only；正常路径没有直接调用 CLI、批准 PRD或增加 handoff_round。
- 生产任务 d2029758833f4f9b8aaa08a11fea203a 仍为 draft、approved_hash=null。
- state.json SHA-256：161ea3ec930e4502122feaa0ae7f9adec0972aa6ff9a45e05e8dd7e9584888da。
- PRD SHA-256：6d38fa8b790675325ae9dd95d46e0101050b809cb6aaff854208feb4a1a3d7e1。
- 当前两网关报告 active_agents=0，所有 TaskStore 记录无 drafting/building/reviewing。但因下列阻断，不执行重启。

## R1 [P1] 发送状态/重发的读改写可能撤销另一网关的取消或阶段变化

位置：cli_bridge/engine.py 的 note_delivery（144–158）与 request_resend（161–177）；cli_bridge/store.py 的 load/save。

`load` 与 `save` 不在同一个锁事务中。save 只保护整条旧记录写入，不能防止期间另一进程已经更新同一任务。note_delivery 在每次异步回传和交接后都会执行，因此能把另一个 profile 的新状态覆盖掉。

已在完全独立的临时 TaskStore 中做确定性交错复现：

1. 创建并批准临时任务，stage=approved。
2. 网关 A 的 note_delivery 读取 approved 快照。
3. 在 A 保存前，另一个 TaskEngine B 正常执行 owner cancel，持久状态为 cancelled。
4. A 保存其包含 `last_delivery_status=ok` 的旧快照。
5. 实际最终 stage=approved；预期应保持 cancelled。

复现输出：

```text
other profile cancellation: cancelled
after delivery metadata save: approved
BUG: expected cancelled to remain terminal
```

这不只是日志不准确：终态取消可能被恢复为可构建阶段；request_resend 的去重写入同样有旧快照覆盖风险。现有串行 fake 集成测试不足以覆盖两个独立网关。

修复要求：引入锁内重新读取并更新或版本 CAS 的状态更新契约；发送元数据更新不能覆盖阶段、批准、取消或其他进程的去重结果。审计所有参与同一任务读改写的路径，不能只给 note_delivery 单独加锁而让其他旧快照写入继续覆盖它。不要在锁内等待网络/模型。增加确定性并发回归，最好使用两个独立进程和屏障，至少覆盖 delivery-vs-cancel、resend-vs-stage transition 和重复交接的单次执行保证。

## R2 [P1，部署前置条件] 身份别名不是报告所说的“可选取消功能”

位置：cli_bridge/engine.py::_can_act（76–86）；GROK_DEVELOPMENT_RESULT.md 第55行及部署说明。

新实现先要求记录 owner 属于本 profile 的 same-person 集合，然后才检查是否为 trusted peer。这是合理的 fail-closed 约束，但当前 grokdev 配置没有 owner_alias_open_ids；Codex 创建的记录 owner 又是 Codex app-scoped Ryan ID。因此新版本中即使是合法 Codex Bot 的 build handoff 也会被拒绝，不仅仅是 Grok 侧人工 cancel 失败。

用当前配置和生产任务记录进行只读授权判定，临时引擎输出：

```text
grokdev alias configuration present: False
trusted Codex peer authorized for this task: False
local Grok-profile human authorized for this task: False
```

修复要求：保留严格授权，不删除该归属检查来绕过问题。把已核验同一人的 app-scoped ID 绑定作为跨应用自动开发的必需部署步骤，并增加启动/预检诊断及回归：缺少绑定时明确指出配置问题；配置正确后 trusted peer 可处理该用户任务，外人和 peer 仍不能 approve/cancel。生产 profile 更新只能由 Codex 在审核后执行。

## 非阻断说明与仍待现场验证

- GROK_DEVELOPMENT_RESULT.md 声称此前 Secret 出现在聊天中，但本次交付未给出证据。不要把该断言作为已确认事实，也不要擅自轮换凭据。
- Bot-to-Bot 入站无回复仍为独立未解决项；发送修复/离线通过不代表飞书现场验收通过。
- 并发问题修复并复审通过后，才可仅重启 codexarch/grokdev，随后由用户发送 `/dev-resend d2029758833f4f9b8aaa08a11fea203a`。
- 不批准、不重跑现有 PRD，不实现 subtract，不修改生产 TaskStore，不触碰 Ryan 默认网关或 Vault。
