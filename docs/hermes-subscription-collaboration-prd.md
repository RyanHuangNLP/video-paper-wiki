# Hermes × Codex × Grok Build 订阅协作桥接 PRD

- 版本：0.1.3
- 日期：2026-08-30
- 状态：暂存开发中；用户已授权放宽开发权限，尚未交付可部署桥接代码。
- 负责人：Codex 负责契约和审核；Grok Build 负责主要实现与自测。
- 本文不修改视频论文知识库的产品契约，不授权提前开发其中的模块。

## 1. 用户要求

手机通过飞书下达开发需求；在这台 Mac 上调用真实的 Codex CLI 和 Grok Build CLI，复用各自已有账户登录与可用额度，不以另配 OpenAI/xAI/OpenRouter API Key 代替。

协作流程：

1. Codex 编写 PRD、接口/schema、任务单与验收标准。
2. 用户确认具体 PRD 版本和允许修改的项目范围。
3. Grok Build 完成主要实现、自测及实现报告。
4. Codex 对照已确认 PRD 和实际代码/测试进行审核。
5. 有问题交回 Grok；通过后标记可进入 PR 流程。
6. GitHub 助手后续处理 PR、CI、合并；本期不接入、不自动发布。

Codex 不承担主要功能编码。用户保留产品选择、人工 gate 和 `vpwiki-admin` 操作。

## 2. 已验证事实与未交付内容

本机已安装 Hermes v0.20.6，源码 commit 为 `26350357d76e4508c8df9304a3374bdc5a6f6220`；飞书 Bot「Ryan的智能助手」通过出站 WebSocket 连接，后台服务运行，已验证本人私聊 `/status` 的收发。

本机 Codex CLI v0.142.0 的 `login status` 显示 ChatGPT 登录；Grok Build v1.0.5 的 `models` 显示 grok.com 登录。清除测试进程的常见 API Key 环境变量、关闭工具或启用只读沙箱后，两端分别返回 `CODEX_SUBSCRIPTION_OK` 与 `GROK_SUBSCRIPTION_OK`，进程均正常退出。

上述测试证明客户端可调用，不代表已经验证飞书发起 PRD → 编码 → 审核流程，也不能从输出推算账户后台的具体扣额明细。

当前 Hermes 未选择可工作的主模型，编码工具仍关闭。本期新增确定性路由，不依赖第三个调度模型，也不启用 Hermes 的 Codex App Server 自动迁移。

## 3. 架构与入口

飞书本人私聊 → Hermes 鉴权 → 本地任务桥接层 → 指定客户端子进程 → 本地任务记录/产物 → 飞书结果摘要。

桥接层采用 Hermes 原生插件扩展点，保持独立于 Hermes 核心源码。它只做鉴权、状态机、进程管理和结果交接，不直接调用模型 HTTP API，不从客户端凭据文件提取或复制令牌。

拟定命令（属于待实现接口，不是当前可用功能）：

| 命令 | 行为 |
| --- | --- |
| `/dev-help` | 显示帮助和当前能力，不调用模型 |
| `/dev-prd <需求>` | 启动 Codex 生成 PRD 草案与验收标准 |
| `/dev-approve <任务ID> <PRD摘要>` | 用户确认指定 PRD 内容；不自动启动编码 |
| `/dev-build <任务ID>` | 仅对已确认 PRD 启动 Grok，完成后自动交 Codex 审核 |
| `/dev-review <任务ID>` | Codex 只读复审指定任务 |
| `/dev-status [任务ID]` | 查询状态、结果和阻塞原因 |
| `/dev-artifact <任务ID> <prd\|build\|review> [页码]` | 分页查看完整 PRD、实现或审核报告；只允许记录中的固定产物，不接受文件路径 |
| `/dev-cancel <任务ID>` | 终止任务及受管子进程，不撤销已产生的文件修改 |

普通消息只返回使用帮助，不进入未配置的 Hermes 模型循环。命令统一使用 `dev-` 前缀，避免与 Hermes 已有的 `/review`、`/status` 冲突。首版不做一句话全自动开发、群聊协作或无限自动修复。审核需修改时，用户再次发 `/dev-build <任务ID>`，Grok 读取审核报告继续修复；不得扩大原确认范围。

## 4. 账户与费用契约

1. Codex 通过官方 CLI 的 ChatGPT 登录执行；Grok 通过官方 CLI 的 grok.com 登录执行。保持现有客户端登录，不要求用户把订阅转换成 API Key。
2. 启动前核对登录模式；未登录、模式无法确定或发现 API-backed 自定义 provider 时停止并提示，不猜测可用计费路径。
3. 不在插件中实现令牌提取、共享 refresh token、登录劫持或第三方反向代理。
4. 不自动切换模型/provider，不自动充值或购买额外额度，不在限额后自动改走 API Key。
5. 限额、需要登录或权限不足时进入可见的暂停/失败状态。额度归属、共享额度和用户已开通的额外用量按平台账户规则执行；“走订阅登录”不等于无限或保证任何情况下零额外费用。
6. 后台标题生成、压缩、记忆、judge 等不得悄悄触发其他模型调用；本期桥接层不使用这些能力。
7. CLI 新任务并不自动继承当前 Codex 桌面聊天。上下文通过明确选定的 PRD、任务单、审核报告和项目文件传递，不复制无关聊天。

## 5. 权限与安全边界

- 用户在 2026-08-30 明确要求扩大访问权限以方便开发；执行范围调整为正常项目开发：Grok 使用 `workspace` 或基于它的受限自定义 profile，可读写指定项目、访问开发工具与运行必要构建/测试，不继续采用仅当前目录可读的 `strict` 模式。此授权不等于关闭沙箱或整台 Mac 任意写入。
- 首版仅允许当前已验证的飞书本人私聊；其他用户、群聊和 Bot 消息不启动进程。
- 命令分发必须位于 Hermes 鉴权之后。若使用前置 hook，只允许采集当前事件上下文或重写为帮助命令，禁止在鉴权前启动 CLI、读取项目或发送任务结果。
- Hermes 的 `register_command` handler 只有 `raw_args` 参数，支持 async；实现不得假定它直接提供 event。飞书 open_id、user_id、union_id 不可混用，需对真实事件字段进行身份契约测试。
- 命令 handler 必须捕获并返回失败，防止异常后落入 Hermes 默认模型分发。
- 仅靠前置 hook 不能保证异常时阻断模型调用；本期使用无独立模型凭据的专用 gateway，必须覆盖 hook 异常、未知命令和内部消息的无模型调用测试。
- 专用 gateway 明确设置 `model.provider: auto`、`providers.auto.enabled: false`，并清空 `fallback_providers`/`fallback_model`。固定版本的 resolver 已通过独立配置测试：即使注入合成 API Key，也在任何网络连接前拒绝解析。完整 gateway 分发测试仍是部署前验收项；不得将 resolver 单测当作端到端验证。
- 桥接插件拥有独立执行能力，不受当前 `agent.disabled_toolsets` 全禁用自动约束；部署前必须单独审查。
- 首个项目固定为 `/Users/huangzhanpeng/python_code/video-paper-wiki`。聊天不得指定任意 cwd、可执行文件、CLI 参数、环境变量或 shell 命令；一律以固定 argv 启动，不使用 shell 拼接。
- `/Users/huangzhanpeng/Documents/video-paper-vault` 不得成为可写目录；禁止执行 `vpwiki-admin`、人工 gate 或擅自修改 review 决策。
- Codex PRD/审核阶段使用只读模式；PRD 文本由桥接层保存到受管任务产物目录，不开放主模型任意文件写入。
- Grok 在指定项目范围内编码；普通项目编辑、构建/测试不要求逐条交互确认，但保留操作系统沙箱。不使用 `always-approve`、`bypassPermissions` 或关闭沙箱；超出项目开发范围的额外权限必须报告，不能自动升级。
- cwd 不是沙箱。实际可写路径、符号链接逃逸、配置覆盖、凭据读取限制必须单独验证。Mac 原生沙箱也不等同于 Docker/虚拟机；Grok 内建 profile 的子进程网络限制在 macOS 上有限制，不得宣称完全网络隔离。
- 不给编码子进程继承飞书 App Secret、Bot 凭据或无关 API Key；日志/飞书摘要脱敏，不回传客户端认证文件或环境变量。
- 原生 CLI 信任边界：Grok 1.0.5 实测在 OS 级拒绝读取自身 `~/.grok/auth.json` 时无法订阅登录。按用户放宽开发权限的选择，保留官方客户端自身必要的认证访问，禁止把凭据内容作为提示词/输出传递，并继续隔离飞书、SSH、其他客户端等无关凭据。不得宣称能在同一个 Grok 进程内通过 OS 沙箱完全分离“认证代码”与“模型工具”；如要求这种强隔离，需要另行设计执行环境，不能以配置文字假装满足。
- 禁止自动提交、push、开 PR、合并、删除用户文件或执行其他超出已确认开发范围的动作。

## 6. 任务、状态与产物

每个任务有唯一 ID、项目、用户需求、PRD 内容摘要、用户确认记录、阶段、开始/结束时间、调用客户端版本、退出状态、报告路径。

PRD 改动使原确认失效。模型文本不得自行生成有效人工确认。确认必须来自已鉴权本人命令，并绑定任务 ID 与完整 PRD 内容 hash；命令中允许展示经碰撞检查的短摘要。

首版命令使用完整 SHA-256，不启用短摘要。模型产物先做控制字符清理与敏感字段脱敏，再保存并计算 hash；确认绑定实际保存的 PRD，而非脱敏前文本。`dev-artifact` 按每页 6000 字符展示，并附页数和完整内容 hash；用户可以在手机阅读全部 PRD 后确认，不以需求预览代替 PRD。

状态至少包括：`draft`、`approved`、`building`、`reviewing`、`needs_changes`、`ready_for_pr`、`needs_user`、`rate_limited`、`cancelled`、`failed`。

- 每项目同一时间只运行一个任务；不并行改同一工作目录。
- 长任务立即返回任务 ID；可查状态和取消。模型调用、测试均有有界超时。
- 使用插件托管后台任务接口；回传绑定任务创建时的不可变本人私聊目标，通过对应平台 adapter 发送并检查结果，不通过会触发模型回合的消息注入接口。限制进度频率与输出大小。
- 取消需终止受管进程树；服务重启不得盲目重跑写入任务或把旧 PID 当作当前任务杀掉。
- CLI 非零退出、空结果、超时或达到轮次上限不能标记成功。区分 CLI 成功退出、实现自测通过和 Codex 审核通过。
- 保留 PRD、Grok 实现报告/测试结果、Codex 审核报告；审核依据包括真实变更与可复现测试，而非只相信 Grok 的成功描述。
- 不在代码工作区保存认证信息；具体任务产物位置由实现方案确定并在部署说明中记录。

## 7. 交付拆分

1. Codex 冻结此 PRD 的执行权限与入口契约，补充实现任务单。
2. Grok 在独立暂存开发目录实现插件、状态机、CLI adapter、测试和安装/卸载说明；不改 Hermes 核心或全局 Codex 配置，不自行启用服务。
3. Codex 审核代码与测试，较大问题退回 Grok；审核通过后才部署插件。
4. 先用临时空项目验证 PRD → 人工确认 → Grok 实现一个无外部依赖的小函数/测试 → Codex 审核；确认权限限制及取消有效。
5. 再在飞书本人私聊完成端到端测试。最后才开放真实项目入口；不自动启动知识库模块开发。

## 8. 最小验收集

1. 证明执行的是固定路径的真实 `codex` / `grok`，而非直接模型 API；无 API Key 仍可通过已登录客户端完成调用。
2. 无登录、限额、退出失败、空输出、轮次耗尽时不走其他 provider，不购买额度。
3. 未授权用户、群聊、Bot、伪造身份字段、跨任务确认均不能启动任务。
4. 普通消息及插件异常不触发 Hermes 默认模型；未确认或已变更 PRD 不能进入 build。
5. 输入包含引号、换行、`$()`、分号、路径穿越、CLI flag 时仅作为需求数据，不改变固定 argv/cwd。
6. Vault 写入、Bot 凭据、SSH/其他客户端认证文件及项目外写入有明确拒绝测试；默认只读/strict、禁 shell 或空项目调用成功均不算隔离通过，必须验证实际生效权限与订阅登录同时可用。当前客户端自身必要认证访问按第 5 节披露的原生信任边界处理，不列为已通过的强隔离项。若其他承诺无法保证，停止部署并报告，不用提示词代替强制隔离。受保护的状态/批准产物不得放在已发现有额外放行规则的系统临时目录中。
7. 长任务可查询、取消并回收进程树；超时/重启不重复编码，错误信息脱敏。
8. Grok 完成后正确交接 PRD 与实现报告给 Codex；只读审核不自动改代码、批准人工 gate 或执行合并。
9. 飞书端收到阶段、最终结果或明确阻塞状态；所有运行只归属当前本人私聊。

## 9. 官方依据

- [OpenAI：Codex 登录方式](https://learn.chatgpt.com/docs/auth)
- [OpenAI：非交互调用](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Grok Build：概览](https://docs.x.ai/build/overview)
- [Grok Build：Headless 与脚本调用](https://docs.x.ai/build/cli/headless-scripting)
- [Grok Build：沙箱边界](https://docs.x.ai/build/features/sandbox)
- Hermes 插件契约以本机固定 commit 的 `hermes_cli/plugins.py`、`gateway/run.py` 和 `website/docs/developer-guide/plugins/index.md` 为开发时校验依据。
