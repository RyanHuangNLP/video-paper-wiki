# Pi / Hermes 飞书订阅 CLI 接入核查

日期：2026-08-30。状态：只读选型审查；未安装 Pi，未切换飞书 Bot，未批准生产开发。

## 目标保持不变

飞书手机入口 → Codex 生成 PRD/验收标准 → 用户确认 → Grok Build 主力编码与自测 → Codex 审核 → 需要修改则退回 Grok。复用两端现有官方 CLI 登录，不增加 API Key，不提取令牌作为替代调用路径。正常项目开发权限不等于开放其他用户控制电脑。

本文件是选型补充，不替换现有 `hermes-subscription-collaboration-prd.md`，不改变视频论文知识库契约。

## 核查范围与证据级别

- 阅读公开仓库源码和官方文档，运行本机 Codex 的参数解析检查。
- 没有运行第三方 Pi 扩展，没有读取真实认证文件，没有发起媒体 API 请求。
- 源码来自审查时默认分支，不宣称 npm 发布包与分支内容完全一致。审查时查询到的分支 head：
  - surenkid/pi-feishu `48826aabeb5c8ed3946bb2e2909894ae4349ab3c`
  - hwei/pi-external-advisor `72b1332906e211dd5ecabbc64e40a670045ac22f`
  - ramarivera/pi-grok-build `f8a948f56679b2cd2399930e5e47e833e537a010`
- 以下为局部审查发现，不是完整安全审计或兼容性认证。

## 主要发现

### 1. pi-feishu 不能原样承担本人专用远程开发入口

`src/feishu-client.ts` 的 `handleInboundMessage` 排除 bot/app、做时间和去重检查后，直接把消息交给上层。未核验发送者 open_id 白名单；回调参数也不携带发送者身份。

`src/index.ts` 使用单个 `ctxRef` 和 `pi.sendUserMessage`。按 chat_id 分开的队列不是独立模型上下文；`/stop` 会中断共享上下文，`/new` 调用 compact 而不是创建新会话。不能据“支持多用户”就认定用户或任务之间隔离。

另外，入口按 4000 字符切片，但客户端卡片按 3500 字符截断，会丢失长 PRD/审核报告的一部分。消息过期常量为 `30 * 60 * 60 * 1000`（30 小时），与注释及 README 的 30 分钟不符。

部署前至少需要：本人身份和私聊限制、明确任务/会话路由、长文无损传递、取消和重置的正确语义。不能仅配置 App ID/Secret 就接入开发目录。

来源：[入口](https://github.com/surenkid/pi-feishu/blob/master/src/index.ts)、[客户端](https://github.com/surenkid/pi-feishu/blob/master/src/feishu-client.ts)。

### 2. pi-external-advisor 是真实 Codex CLI，但不是完整工作流

`index.ts` 构造真实 `codex exec` 调用，并为新任务设置 read-only。其角色是返回建议，没有固化 PRD 内容确认、实现版本绑定和强制终审。

同一参数构造器在恢复时生成：

```text
codex exec resume <session-id> --json --sandbox read-only --skip-git-repo-check -
```

本机使用不存在的全零 session ID、空 stdin 做纯参数解析检查，退出码 2：`unexpected argument '--sandbox' found`。没有启动模型任务或恢复任何真实会话。扩展有恢复失败后新建会话的回退，因此这不证明所有调用失败，但恢复功能在当前本机 CLI 下不能按 README 预期工作。

进程启动还使用 `shell: true`，没有显式清理继承环境；macOS 取消路径为 `child.kill()`。这些都需要独立验证，不能据启动成功宣称订阅专用或后代进程已经终止。

来源：[实现](https://github.com/hwei/pi-external-advisor/blob/master/index.ts)、[OpenAI 非交互调用文档](https://developers.openai.com/codex/noninteractive/)。

### 3. ramarivera/pi-grok-build 的 ACP 路径有价值，但默认行为不符合现有约束

`src/acp-mode.ts` 确实启动官方 `grok agent ... stdio`，通过 ACP 协商 cached_token 认证；这与扩展自行读取 token 不同。当前每次 provider 调用新建进程与会话，客户端只映射文本/思考通知；不能据此证明完整工具进度、权限交互或持久化会话已接通。

默认启动参数包含 `--always-approve`，环境完整继承；在特定条件下允许选择 xai.api_key。JSONL 路径则默认 `maxTurns: 1`、禁用子 agent 和 plan。不能把这两种模式泛称为已经验证的完整 Grok Build 委派。

更重要的是 `src/xai-api.ts` 的 `getXaiApiKey` 在没有 API Key 时，默认调用 `getCachedGrokXaiToken` 读取 `~/.grok/auth.json`，可供图片/视频 REST 请求使用；`extension.ts` 据此注册媒体工具。这与 README 的“不复用私有缓存令牌”声明冲突。存在关闭缓存读取的环境开关，但部署应明确移除/禁用无关媒体能力并验证，而非依赖 README 保证。

来源：[ACP](https://github.com/ramarivera/pi-grok-build/blob/main/src/acp-mode.ts)、[provider](https://github.com/ramarivera/pi-grok-build/blob/main/src/provider.ts)、[媒体认证](https://github.com/ramarivera/pi-grok-build/blob/main/src/xai-api.ts)、[扩展注册](https://github.com/ramarivera/pi-grok-build/blob/main/src/extension.ts)。

### 4. grok-pi 与原生 Grok Build agent 不能混为一谈

根据当前包文档，grok-pi 1.4.0 每轮调用真实 Grok CLI，但通过 `--tools ""` 禁用其工具，再由 Pi 执行工具。这可作为订阅 CLI transport 候选，不等价于保留原生 Grok Build agent 的完整执行环境。本次没有完成该包源码/发布包审计。

来源：[grok-pi](https://pi.dev/packages/grok-pi)。

### 5. Hermes 本身也有原生 Codex runtime

Hermes 官方文档提供 opt-in `codex app-server` runtime，工具循环在 Codex 中执行。不能以“Hermes 完全不支持订阅 CLI”为迁移依据。该能力尚未在本机启用；其配置迁移和 Grok 协作仍需明确设计。

来源：[Hermes Codex App-Server Runtime](https://hermes-agent.nousresearch.com/docs/user-guide/features/codex-app-server-runtime/)。

## 决策与下一步

当前证据支持“Pi 有可复用组件，值得做隔离 PoC”，不支持“安装三个插件即可获得可靠的双 agent 开发 Bot”。目前不能证明迁移 Pi 比完成现有 Hermes 路线更省工作。

在用户确认试用 Pi 前，不安装或切换线上 Bot，也不继续扩大 Hermes 自制桥接。建议的 PoC 保留完整官方 CLI agent 委派这个原始要求；若改为 Pi 工具循环 + Grok 模型，应单独获得用户确认。

PoC 验收必须覆盖：本人授权入口、实际 CLI 登录路径、指定项目读写、Codex PRD → Grok 修改与测试 → Codex 审核、完整长文交付、限额/失败可见、取消后进程退出；不以普通对话成功代替这些项目。
