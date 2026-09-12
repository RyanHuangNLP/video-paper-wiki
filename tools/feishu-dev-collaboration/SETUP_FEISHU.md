# 飞书双 Bot 接入（Codex CLI + Grok CLI）

日期：2026-08-30

多 Bot 花名册 / 摘要与真 @ 拆分 / mention vs inbound 身份：见 **`DESIGN_BOT_ROSTER.md`**（2026-08-31，fable5 整包通过，契约已定）。操作仍按本文；不要把两 Bot 特例再加成第三个 peer 字段。

这不是「一个 Bot 分饰两角」。目标是 **两个真实飞书应用**，各自一个 Hermes profile、各自一条网关进程：

| 飞书 Bot（建议显示名） | Hermes profile | 控制的 CLI | 群内命令 |
| --- | --- | --- | --- |
| Codex 架构 | `codexarch` | `/opt/homebrew/bin/codex`（PRD / 只读审核） | `/dev-prd` `/dev-approve` `/dev-review` `/dev-status` `/dev-cancel` `/dev-artifact` |
| Grok 开发 | `grokdev` | `grok` 1.0.5（实现，`--sandbox workspace`，`--permission-mode dontAsk`） | `/dev-build` `/dev-status` `/dev-cancel` `/dev-artifact` |

**已确认（2026-08-30）：不把 Ryan 助手改派成 Codex 或 Grok。**  
现网 Bot **「Ryan的智能助手」** 与 `ai.hermes.gateway` **保持不动**：不改名、不删除、不给同一 App 再挂消费者。  
请在开放平台 **另外新建两个企业自建应用**，不要复用 Ryan 助手的 App ID/Secret。

本机已做（机器侧）：

- 空白 profile `codexarch` / `grokdev`（`--no-skills`，未 clone 默认助手）
- 各自 `plugins/cli-bridge` 指向本目录的插件
- 共享 TaskStore：`tools/feishu-dev-collaboration/task-data`
- 首个测试项目：`tools/feishu-dev-collaboration/loop-sandbox`（不是论文 Vault）
- **未** `gateway start`，**未** 写入任何飞书 App Secret

本机未做、必须由你完成：创建两个飞书应用、扫码/粘贴凭据、建测试群、把两个 Bot 拉进同一群。在此之前不能声称飞书同群闭环已跑通。

## 1. 开放平台：新建两个应用

对每个应用重复：

1. [飞书开放平台](https://open.feishu.cn/) → 创建企业自建应用。
2. 开通 **机器人** 能力，显示名建议「Codex 架构」「Grok 开发」。
3. 权限。人 @ Bot 与 Bot @ Bot **不是同一个权限**（飞书官方 [接收消息](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive)）：
   - 人 @ 当前机器人：`im:message.group_at_msg:readonly`（两个应用目前已有，所以人 @ 能通）
   - **其他机器人 @ 当前机器人**：`im:message.group_at_msg.include_bot:readonly`（两个应用目前都没有；缺这个时飞书根本不会把事件推到 Hermes WS）
   - 其余至少：`im:message`、`im:message:send_as_bot`、`im:message.p2p_msg:readonly`、`im:chat`、`contact:user.id:readonly`；peer 显示名需要 `application:bot.basic_info:read`
   - 不要用 `im:message.group_msg` / `include_bot:read` 收全群消息（过宽）。不要把 `allow_bots` 改成 `all`。
   - 开通后必须 **创建并发布新版本**，权限才生效。
4. 事件订阅：使用 **长连接（WebSocket）**，不要 webhook；订阅 `im.message.receive_v1`。Hermes 文档的权限表 **没有** 列出 `include_bot`，只跟 Hermes 文档会漏掉 Bot-to-Bot。
5. 可用范围包含将要使用的测试群；发布版本。
6. 记下 **App ID**。App Secret 只粘贴到对应 profile 的 `.env`，不要发到聊天、不要提交 git。

不要复用「Ryan的智能助手」的 App ID/Secret。

## 2. 本机写入凭据（每个 profile 各做一次）

```bash
# Codex Bot
codexarch setup
# 或：hermes -p codexarch setup
# 选择 Feishu，粘贴该应用的 App ID / Secret（可扫码）

# Grok Bot
grokdev setup
```

凭据只应出现在：

- `~/.hermes/profiles/codexarch/.env`
- `~/.hermes/profiles/grokdev/.env`

不要复制 `~/.hermes/.env`。不要把 Secret 写进本仓库。

## 3. 测试群

1. 新建一个测试群（不要用生产/论文群）。
2. 把两个 Bot 都拉进该群。
3. 在群里各 @ 一次，确认进群成功。
4. 记录：
   - 群 `chat_id`（`oc_...`）
   - 你本人的 `open_id`（`ou_...`）
   - 两个 Bot 自己的 `open_id`（网关首次连上后日志里会有；也可在开放平台/通讯录侧确认）

然后编辑两个 profile 的 `config.yaml` 中 `plugins.entries.cli-bridge.settings`。现网已迁到花名册（2026-09-01），**不要**再写 `peer_open_id` / `trusted_peer_open_ids`（与 `roster` 并存会启动失败）。形状见 `DESIGN_BOT_ROSTER.md` 第 4 节。

`mention_open_id` 是本 App 去 @ 对端的 id；`inbound_open_ids` 是本 App 入站 `sender=bot:` 看到的 id，通常不是同一串。交接用飞书真实 `<at>`，纯文本 `@名字` 对端收不到。

`owner_chat_id` 可留空或填你与该 Bot 的私聊 chat_id（仅诊断用）。空的 `owner_open_id` 时插件对所有人返回 Unauthorized。

Hermes 侧群策略：

- `feishu.allow_bots: mentions`（已写入 profile；**不要** `all`）
- 人类 allowlist 只放你本人：`FEISHU_ALLOWED_USERS=ou_你本人`（写在对应 `.env`）
- 群消息需要 @；peer Bot 不走人类 allowlist，所以必须填 `trusted_peer_open_ids`

## 4. 启动两条新网关（现网助手不要动）

```bash
codexarch gateway install
grokdev gateway install
codexarch gateway start
grokdev gateway start
```

会新增：

- `~/Library/LaunchAgents/ai.hermes.gateway-codexarch.plist`
- `~/Library/LaunchAgents/ai.hermes.gateway-grokdev.plist`

确认 `launchctl list | grep hermes` 里 **原来的** `ai.hermes.gateway` 仍在，且 pid 未无故更换。

不要 `hermes gateway start`（那是默认 profile / Ryan 助手）。不要 `gateway.multiplex_profiles`。

## 5. 群内最小流程

测试项目已固定为 `loop-sandbox`。不要指向 Vault。

1. 你 @Codex 架构：`/dev-prd 在本项目实现 add(a,b)`（若已实现，可换一个小需求）
2. Codex 回复 PRD 摘要 + 完整 SHA-256；用 `/dev-artifact <task> prd` 读全文
3. 你 @Codex：`/dev-approve <task-id> <64位sha256>`（只有你能批准；Bot 不能互相批准）
4. Codex **自动 @Grok** `/dev-build <task-id>`（群内第二条消息，带真实 @）
5. Grok 实现并自测后 **自动 @Codex** `/dev-review <task-id>`
6. Codex 只读审核；`needs_changes` 再自动 @Grok `/dev-build`；`ready_for_pr` 停止互聊，仍不创建 GitHub PR

互聊上限 8 轮交接，避免修-审循环。普通进度消息不会触发下一轮；忽略自己的消息。

取消：你对任一 Bot `/dev-cancel <task-id>`。状态：`/dev-status`。

异步结果没进群、但任务已是 `draft`/`built` 时，**不要改 state.json、不要重跑 CLI、不要批准**。由本人对对应 Bot：

```text
/dev-resend <task-id>
/dev-resend <task-id> handoff
```

前者只重发用户可见摘要（含完整 PRD hash），后者只重试 peer `@` 交接命令。都不调用模型、不增加交接轮数、不自动批准。

同一人在两个飞书应用下的 `open_id` 不同。共享 TaskStore 后，若要在 Grok Bot 上取消自己在 Codex Bot 创建的任务，须**显式**配置（默认不扩权，空列表 fail closed）。示例，不要从显示名学习：

```yaml
# grokdev plugins.entries.cli-bridge.settings
owner_open_id: ou_本应用的Ryan
owner_alias_open_ids:
  - ou_Codex应用里的Ryan
```

Codex profile 对称填写 Grok 应用里的 Ryan `open_id`。Peer Bot 不能借别名获得 `/dev-approve` / `/dev-cancel` / `/dev-prd`。

## 6. 已部署 / 离线测试 / 待现场验收

| 层级 | 状态 | 不能当成 |
| --- | --- | --- |
| 本机代码 + unittest | 离线可重复 | 飞书同群闭环 |
| 本地 `run_loop.py` | 曾用真实 CLI、假飞书 | 群内 Bot 交接 |
| 两个新网关 WS、人 @Bot `/dev-status` | 现场曾成功 | PRD 异步回传、Bot-to-Bot |
| 任务 `d2029758833f4f9b8aaa08a11fea203a` | `draft`，发送失败；hash 固定 | 已批准或已实现 |

测试群仅 `code_agent开发群`。不要把 Ryan 助手私聊 `/status` 或单测当作双 Bot 验收。

## 6.1 App Secret invalid（10014）

飞书换 token 同时要 **App ID + 此刻控制台里的 Secret**。截图 OCR 常把 `l`/`I`/`1`/`0`/`O` 认错。应用须已发布。Secret 只进对应 profile 的 `.env`，不要复制 Ryan 助手凭据，两个应用不能对调。

## 6.2 异步回传失败

`last_error` 形如 `delivery failed: missing_adapter|send_exception|send_unsuccessful`，不含消息全文或原始异常。根因曾是 Hermes `Platform` 为普通 Enum，用字符串 `'feishu'` 取 `gateway.adapters` 会 KeyError。修复后须由 Codex 审核并**只重启两个新网关**才进生产。积压 PRD 用 `/dev-resend`，不要手改 state、不要重跑 draft。

## 6.3 Bot-to-Bot 入站无回复（已用 Hermes 源码 + 飞书权限 API 核对）

人 @ 两个 Bot 成功、发送 API 也成功、但对端 `gateway.log` **从未出现** `sender=bot:`，这不是「再试一次」能修好的。对照：

上游仓库：https://github.com/NousResearch/hermes-agent （本机 `~/.hermes/hermes-agent` @ `2635035`）
飞书文档：`im.message.receive_v1` 按权限决定推什么。

| 层 | 源码/API 事实 | 本机现状 |
| --- | --- | --- |
| 飞书平台推送 | `group_at_msg:readonly` 只推 **用户** @；Bot @ 当前机器人要 `group_at_msg.include_bot:readonly` | 两个应用均已开通且 `grant_status=1`（2026-08-30） |
| Hermes 入站 | `adapter.py` `_admit`：`allow_bots=mentions` 且被 @ 才放行；拒绝原因是 `logger.debug`，INFO 看不到 | 开通后已出现 `sender=bot:`。入站 `open_id` 是 **本 App 视角**，不是对端 `/bot/v3/info` |
| 身份水合 | `_hydrate_bot_identity()` 调 `/bot/v3/info`；空 `self_ids` 对 bot sender 直接 `self_ids_unknown` | `/bot/v3/info`：Codex `ou_ef9ee8e8317bfaf8a088b7bf7106e521`，Grok `ou_4ae43ad446ea716566fe7b655b0633b3`（与 plugin `self_open_id` 一致）。人 @ 能匹配，说明水合大体可用 |
| @ 是否真实 | 文本必须是 `<at user_id="ou_...">`，且 `user_id` 在 **发送方应用** 里是有效成员 ID，否则只显示名字、不产生 @ | 插件 `handoff.py` 发的是 `<at>`；`peer_open_id` 填的是对端 **自己的** `/bot/v3/info` open_id。跨 App 的 bot open_id 可能不同（Hermes 注释写明 open_id **app-scoped**，且「currently supports single-bot mode」） |
| 插件二次门 | 对端入站后还要 `sender.open_id ∈ trusted_peer_open_ids` | 只配对端 self id 会回 `Unauthorized.`。必须同时放入本 App 日志里的 `sender=bot:ou_...` |

现场映射（不要把两边的 self id 当成入站 id）：

| 视角 | Codex 架构 | grok 开发 |
| --- | --- | --- |
| 自己的 `/bot/v3/info`（可作 `<at user_id>`） | `ou_ef9ee8e8317bfaf8a088b7bf7106e521` | `ou_4ae43ad446ea716566fe7b655b0633b3` |
| 对端收到时的 `sender=bot:` | `ou_6ebc8da986387529b5c99fa43d458671` | `ou_e2d0d7ca2f6febd3b32c612aa4a5c3e3` |

`<at user_id>` 用对端 self open_id 可以解析成真 @。`trusted_peer_open_ids` 要包含 self **和** 入站 id。不要 `allow_bots=all`，不要动 Ryan 助手。

当前任务 `d2029758833f4f9b8aaa08a11fea203a` 已是 `ready_for_pr`，`/dev-resend handoff` 会 skip。完整交接用一条新的小 PRD。

## 7. 回滚

```bash
codexarch gateway stop
grokdev gateway stop
# 如需卸服务：
# launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ai.hermes.gateway-codexarch.plist
# launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ai.hermes.gateway-grokdev.plist
```

不要删除「Ryan的智能助手」，不要改默认 `~/.hermes/.env`。

禁止项仍有效：付费 API 回退、`--always-approve` / `bypassPermissions`、写论文 Vault、`vpwiki-admin`、GitHub PR/merge、同一飞书 App 双消费者。
