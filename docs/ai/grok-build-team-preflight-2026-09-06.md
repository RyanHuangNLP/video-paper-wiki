# Grok Build 开发团队预检

2026-09-06 · 状态：调用验证完成，等待用户确认启动。尚未创建 8 小时目标、自动化或启动项目编码。

## 拟采用的职责

用户最新指令优先于旧 AGENTS.md 中的禁止 Grok 和 Sol 子 agent 配置；旧协议本次尚未改写。用户已明确确认 `lua` 指 `gpt-5.6-luna / high`。

| 角色 | 模型与档位 | 职责 |
| --- | --- | --- |
| 主控 / Architect | `gpt-6-astra / ultra` | 拆分和冻结工作包，审查实际代码及测试，决定返工、验收和下一步 |
| Grok 进度监听 | `gpt-5.6-luna / high` | 按主控指令调用 Grok，定期检查进度，收取开发简报并回报主控 |
| Repo Steward | `gpt-5.6-luna / high` | 独立检查候选范围，串行执行获准的 Git、draft PR 和 CI 操作 |
| 实现者 | Grok Build `grok-4.6 / xhigh` | 在工作包允许路径内编码、测试、修复，完成后交简报并停止写入 |

执行链：主控下发工作包 → 监听 agent 启动并观察 Grok → Grok 交开发简报 → 监听 agent 回报主控 → 主控审查代码。未通过则返工；通过后由 Git agent 处理获准交付，主控再下发下一步。监听 agent 和 Git agent 不代替主控验收。

监听默认每 30 秒有界检查一次，保留 session/request ID、进程状态和日志偏移；只有实质进展、完成、失败、需决策时通知主控。非零退出、空结果、明确达到 max-turns 上限都不能当作完成。简报包含改动文件/摘要、测试命令与结果、未决问题和候选文件 hashes；状态及日志使用 Markdown/JSON 文件交接。

Grok 是实现路径的唯一写者。冻结候选后暂停写入，由主控和 Steward 审查同一份文件；头提交或源码改变须重新绑定验收。Steward 仅暂存明确清单，继续现有 draft PR94 → integration。保留既有未跟踪计划、PRD、inbox/tools 和 67 条目录。目标启动本身不授权合并或关闭人工 gate。

## 已完成的实际调用

- 本机 CLI：`/Users/huangzhanpeng/.local/bin/grok`，版本 `1.0.5 (5115b46bc909)`。
- `grok models` 联网刷新成功：`You are logged in with grok.com.`；默认且可用模型为 `grok-4.6`。
- 选中模型的服务地址：`https://cli-chat-proxy.grok.com/v1`；没有自定义模型配置，也未设置代理地址覆盖。
- 测试在空临时目录运行，禁用 memory、子 agent 和 web search，`permission-mode=dontAsk`；提示明确禁止文件读取、工具、写入及委派。
- 显式参数：`--model grok-4.6 --reasoning-effort xhigh --max-turns 1 --output-format json`。
- Session：`e24b7562-c13a-469a-9481-22858877d02c`。
- Request：`08f303d7-995c-4657-948e-4c3c440a3f6d`。
- 退出码 0，`stopReason=end_turn`，`num_turns=1`，Grok 实际返回 `GROK_BUILD_SMOKE_OK`。
- 运行结果 `modelUsage` 的实际键为 `grok-4.6-build`，modelCalls 为 1；保留这个返回名称，不擅自改成命令行别名。
- 本次会话 `summary.json` 的 `reasoning_effort` 为 `xhigh`，事件 model_id 为 `grok-4.6`。独立打开的 TUI 也显示 `Grok 4.6 (xhigh)`。
- 用量字段：input_tokens 12157，cache_read_input_tokens 1408，output_tokens 55，reasoning_tokens 42，total_tokens 13620；按 CLI 原字段记录，不自行重算包含关系。
- CLI 的 `total_cost_usd=0.00430916` 是运行用量统计，不是逐笔账单证明。

因此，本次调用已确认走当前 grok.com 登录的 Grok Build 服务通道；不是凭模型自述推断身份或额度。另用官方 TUI `/usage` 只读查询，页面原文显示 `Weekly limit: 19%`、`Next reset: September 6, 23:42`。这里保留 UI 原文，不把这一次事后观察当作本次调用的额度前后差值，也不据此保证剩余额度足够连续运行 8 小时。查询完成后 TUI 已退出。

最初沙箱内的模型刷新遇到 DNS 限制，经过正常权限审核后重试成功。CLI 对旧 `privacy` 配置项有非致命警告；本次没有改全局配置。没有读取或复制认证秘密。

## Codex 侧核对与未启动事项

主控本次运行设置已经核对为 `gpt-6-astra / ultra`。两名预检子 agent 均显式指定 `gpt-5.6-luna / high`：`grok_monitor_probe` 和 `git_steward_probe`。两者完成只读职责预检，没有编码或 Git 修改；此前两个 Sol agent 保持暂停。

当前 Git HEAD 仍为 `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`，分支为 `repair/vpkb000-plan-approval-prepare-follow2`。手工 PDF 首包工作包仍需在用户确认新管理方式后完成最终核对与冻结。8 小时应从确认后的实际启动时间计算，保存明确截止时间；到时收束、保留检查点并汇报。额度、认证、权限或人工 gate 阻塞须如实记录。

本报告和临时预检记录不是产品实现、完整编码工具测试、真实 Docling 烟测或 CI 验收。

## 证据

调用参数、返回值和脱敏会话元数据位于 `/private/tmp/grok-model-check-_6d7r1sw/`：`invocation.json`、`stdout.json`、`stderr.log`、`session-metadata-safe.json`、`usage-view.txt`。

- [Grok Build 官方说明](https://docs.x.ai/build/overview)
- [推理档位官方说明](https://docs.x.ai/developers/model-capabilities/text/reasoning)：Grok 4.6 支持 xhigh。
- [官方命令说明](https://docs.x.ai/build/modes-and-commands)：`/usage` 查看用量。
- 本机随 CLI 提供的认证说明：`/Users/huangzhanpeng/.grok/docs/user-guide/02-authentication.md`，说明浏览器登录与 API key 的优先级。
