# 飞书双 Bot 协作系统：后续开发交接给 Grok CLI

日期：2026-08-30。用户明确要求将接下来的开发任务交给 Grok CLI，而不只是单个发送问题。

## 职责与项目边界

- Codex：本任务单、架构约束、验收标准、最终审核与部署把关。
- Grok CLI：本目录内后续功能实现、回归测试、集成测试、缺陷修复和交付报告。请实际实施，不要只返回建议。
- 用户：产品选择、真实 PRD 批准与必要的平台授权。

本次项目是 `tools/feishu-dev-collaboration` 飞书双 Bot 协作系统，不是 video-paper-wiki 业务模块或 subtract 示例功能。当前任务中的 subtract PRD 是联调样本，不能自动批准或实现。

先阅读 `GROK_HANDOFF_SEND_FIX.md` 与已存在的 `GROK_SEND_FIX_RESULT.md`（若有）；前者的环境证据和禁止项仍有效。发送修复是下面第一个里程碑，而不是全部工作。

## 开发目标

实现并验证可靠的：用户 @Codex 提需求 → Codex CLI 输出 PRD → 用户查看全文并批准精确 hash → Grok CLI 实现及自测 → Codex CLI 审核 → 必要时退回修改 → ready_for_pr 停止。

群中必须有两个真实独立 Bot，角色严格分离。代码中的 simulated/fake workflow 与真实 CLI、真实飞书验收必须分开报告。

## 里程碑与验收

### M1：生产消息发送契约

修复普通 Enum / string 适配器键兼容问题；严格按目标平台查找，未知平台拒绝，不能 fallback 到任意适配器。保护异步完成回传与 peer handoff 共用发送路径。添加脱敏诊断，禁止记录凭据、消息全文或原始异常文本。使用实际 Hermes Platform 类型或等价普通 Enum 回归，覆盖字符串旧测试。

### M2：异步回传失败的恢复

提供显式、可测试的已完成结果重发机制（例如 owner-only `/dev-resend <task-id>`），读取已有产物并重发，不能再次调用模型，不能自动批准、改变 PRD hash 或重新运行 build/review。角色权限与记录归属校验必须继续生效。发送失败必须保留可观察诊断，不能仅靠手改 state 清错来假装修复。

如果自动交接与用户结果重发共用机制，必须区分“重发用户可见结果”与“重试交接命令”，避免 `/dev-resend` 隐式启动下游工作。自动交接重复或失败必须可被识别；同一阶段不能因网络重试或重复事件启动两次 CLI。只重发结果的命令不增加 handoff 轮数。

### M3：跨应用身份与角色正确性

真实 Ryan 在两个应用下有不同 open_id；TaskStore 共享，不能简单假定两 profile 的 owner_open_id 一样。修复由此造成的授权/取消不一致，但不能放宽到任意群成员。

设计约束：身份别名只能来自明确配置的受信任同一人绑定，不得从消息、任务提示词或显示名自动学习。调用者必须首先匹配本 profile 的 owner_open_id，目标任务的记录 owner 必须在已配置的同一人集合中；空集合/陌生历史 owner 必须 fail closed。若引入 owner_alias_open_ids 等设置，默认不扩权且兼容已有 schema，提供配置示例和迁移说明；不得改现有生产 profile 或历史任务。

Peer Bot 只允许既定 build/review/status/artifact 等机器命令，绝不能以别名获得 human-only approve/cancel/prd 权限。验证在 Grok profile 下同一人可取消自己从 Codex profile 创建的任务，而其他人和 peer 不能借此批准/取消。保留 group allowlist 与 self-message 拒绝。

### M4：自动交接、去重与循环边界

验证当前生产形态的 mentions、sender_type、Route、原始事件归一化、完成消息与 peer ping。成功、needs_changes、拒绝、异常、重复回调、取消与重启恢复均需测试。保留人工精确 hash 批准、产物防篡改、角色限制、单项目并发约束和最多 8 次交接边界。

先前从两个 Bot 发出的 /dev-status 探测已被飞书发送 API 接受，但尚未观察到 peer 入站回复；人工 @bot 两边均成功。这是未解决的验收项，不能归因于单一发送 bug 后宣称关闭。检查本地代码和官方契约，给出区分平台未推送、身份不匹配、mentions 解析或插件路由失败的诊断方法。若需要平台额外权限、产品选择或不同控制通道，明确列为待 Codex/用户决定；不要擅自扩权或迁移平台。

### M5：集成验收与交付

- 完整单测通过，测试不要依赖 str Enum 来掩盖普通 Enum 的差异。
- 用临时 TaskStore 和 fake clients 构建双 profile、不同 human open_id 的完整交接集成测试，包含 human gate、失败恢复和禁止场景。至少一个 host-contract 测试使用已安装 Hermes 的真实平台类型。
- CLI 调用仍使用现有正式 Codex/Grok CLI 与用户订阅；禁止 API key 或付费 API fallback，禁止 bypassPermissions / always-approve。不要在测试中实际调用模型，除非后来得到明确联调授权。
- 更新 SETUP_FEISHU.md：区分已部署事实、离线测试和待真人批准的现场验收；说明 App Secret 错误、真实 @、不同应用 user ID、仅测试群可用、结果重发、排障、回滚和正确启动命令。
- 输出 `GROK_DEVELOPMENT_RESULT.md`：逐项标记 implemented/tested/blocked，变更文件、准确命令及测试结果、剩余风险、需要 Codex 执行的配置迁移/新网关重启步骤。不得将建议或 fake pass 写成真实部署通过。

## 部署与操作限制

只编辑本目录内源码、测试、说明文档。现有数据、凭据、profile、上游 Hermes 和 launchd 文件不能修改；不得重启任何服务，不能发送飞书消息，不能访问 Vault，不做 git commit/push/merge，不启动子 agent。当前生产插件路径为本目录的 symlink，修改后由 Codex 审核并择时仅重启两个新网关。

不得修改或批准 task `d2029758833f4f9b8aaa08a11fea203a`。PRD hash 必须仍为 `6d38fa8b790675325ae9dd95d46e0101050b809cb6aaff854208feb4a1a3d7e1`。测试只能写独立临时数据；不要调用会迁移/恢复生产 TaskStore 的代码。

不能并行启动另外一个同目录修改者。若 M1 已由上一轮完成，接着做 M2–M5，不要推倒重写。遇到必须新增授权的环节，完成其余能独立交付的内容，再明确报告待决事项。
