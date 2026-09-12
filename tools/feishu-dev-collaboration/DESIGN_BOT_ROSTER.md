# 多 Bot 花名册与群内交接体验（方案，契约已定）

日期：2026-08-31  
读者：实现与回归  
范围：`tools/feishu-dev-collaboration` 的 `cli-bridge` 插件 + 两个 Hermes profile（`codexarch` / `grokdev`）  
**不是** 论文 Vault、不是 Ryan 助手、不是 GitHub PR。

本文把「已经实测通了的两 Bot 互 @」和「下一步不要做成两个 Bot 特例」写成同一份契约。体验改造（人设、话题归属、摘要 vs 真 @）必须和花名册、mention/inbound 身份拆分一起设计，不能先打两 Bot 补丁。

三列仍须分清：**飞书/Hermes 事实**、**本机实测**、**本方案的设计选择**。

**评审（fable5，2026-08-31）：第 1.4 节四条本地源码断言已抽查属实。第 3 节整包接受，附第 7 节五题裁决与三处契约精度修正（已写入下文）。** 进入第 6 节步骤 1 前不得再改方向。

核心论据（评审确认）：三套 `ou_` 实测不相等，而现在 `format_peer_ping` 要求出站目标 ∈ `trusted_peer_open_ids`（入站白名单）。两 Bot 下靠「把两种 id 都塞进去」侥幸通过，N Bot 下必然错。mention/inbound 拆分是修正已被实测证伪的字段混用，不是风格偏好。契约必须让出站 `mention_open_id` 与入站 `inbound_open_ids` **在类型上无法互填**；只要还保留「出站身份必须在入站集合里」的函数签名，加 `peer_open_id_2` 只会把错误语义复制一份。

---

## 0. 当前状态（事实）

2026-08-30 在测试群 `code_agent开发群`（`oc_a33d1eba5e6a86bd5807ae97b27bf6a8`）跑通 multiply 闭环：

| 步骤 | 谁 | 对端日志 |
| --- | --- | --- |
| `/dev-prd` | 人 @ Codex | `sender=user` |
| `/dev-approve <task> <sha256>` | 人 @ Codex（仅人可批） | `sender=user` |
| `/dev-build <task>` | Codex **自动真 @** Grok | Grok：`sender=bot:` |
| `/dev-review <task>` | Grok **自动真 @** Codex | Codex：`sender=bot:` |
| 结束 | Codex 审核 `verdict=pass` | `stage=ready_for_pr`，不再 @ 对端 |

任务 `79e850c87efc495c9dfeb74de7a6e1fc`。工作区 `loop-sandbox` 已有 `multiply.py` / `test_multiply.py`，本机 `unittest` 9 项通过。未 git commit/push，未写 Vault。

`allow_bots` 仍是 `mentions`，**没有**改成 `all`。Ryan 助手网关未动。

这只证明：**两个真实飞书应用、两条 Hermes 网关、群内真 @ 可以互下命令**。不证明配置模型可扩展到第三个 Bot，也不证明群体验可接受。

---

## 1. 材料来源（请按出处打分）

### 1.1 飞书开放平台文档

- 接收消息 `im.message.receive_v1` 按权限决定推什么：  
  https://open.feishu.cn/document/server-docs/im-v1/message/events/receive  
  - `im:message.group_at_msg:readonly`：仅 **用户** @ 当前机器人  
  - `im:message.group_at_msg.include_bot:readonly`：用户 **和其他机器人** @ 当前机器人
- `open_id` 按应用隔离：  
  https://open.feishu.cn/document/home/user-identity-introduction/introduction
- 文本真 @：`<at user_id="ou_…">姓名</at>`；无效 ID 只显示名字、不产生 @。  
  https://open.feishu.cn/document/server-docs/im-v1/message-content-description/create_json
- `GET /im/v1/chats/:chat_id/members` **不返回群内机器人**。

### 1.2 Hermes 源码与文档

本机仓库：`~/.hermes/hermes-agent`（`origin` = https://github.com/NousResearch/hermes-agent ，当时 commit `2635035`）。

| 位置 | 内容 |
| --- | --- |
| `plugins/platforms/feishu/adapter.py` 文件头 | `open_id` app-scoped；bot 的 `/bot/v3/info` open_id 用于 `mentions[].id.open_id`；**currently supports single-bot mode**（一个进程一个 App） |
| 同文件 `_admit` / `_mentions_self` | `FEISHU_ALLOW_BOTS=none\|mentions\|all`；bot 入站 fail-closed（身份未水合 → `self_ids_unknown`）；ID 优先于显示名；`@_all` 视为提到自己 |
| 同文件 `_handle_message_event_data` | `_admit` 拒绝只打 `logger.debug`，INFO 看不到「丢掉了」 |
| `website/docs/user-guide/messaging/feishu.md` | 权限表 **没有** `include_bot`；只跟 Hermes 文档配，人 @ 通、Bot @ 不通 |

Hermes 不提供「群内 Bot 花名册」，也不替插件选择下一个执行者。它只做：事件到了放不放行、按 `mentions` 判断是否 @ 了自己。

### 1.3 本机 API / 日志（不是文档里的现成表）

`GET /application/v6/scopes`：两个新应用均已 `im:message.group_at_msg.include_bot:readonly` 且 `grant_status=1`。

跨 App 的 bot `open_id` **三套不是同一串**（2026-08-30 发送 API + 入站日志）：

| 视角 | Codex 架构 | grok 开发 |
| --- | --- | --- |
| 自己的 `/bot/v3/info`（可作 `<at user_id>`） | `ou_ef9ee8e8317bfaf8a088b7bf7106e521` | `ou_4ae43ad446ea716566fe7b655b0633b3` |
| 对端收到时的 `sender=bot:` | `ou_6ebc8da986387529b5c99fa43d458671` | `ou_e2d0d7ca2f6febd3b32c612aa4a5c3e3` |

用对端 **self** id 发 `<at>`，飞书能解析成真 @（发送响应里 `mentions[].id` 是 **发送方 App 视角** 的另一串）。接收方 `_mentions_self` 比的是自己的 `/bot/v3/info`。插件鉴权比的是入站 `sender.open_id`。  
因此：**出站 @ 目标和入站白名单不能共用一个字段。**

### 1.4 本插件源码（特例，不是平台能力）

fable5 抽查：以下与 `plugin.py` / `engine.py` / `handoff.py` / `_reject_if_busy` 一致。

- `cli_bridge/handoff.py`：`peer_open_id` **标量**；`format_peer_ping` 要求它 ∈ `trusted_peer_open_ids`（出站身份必须在入站集合里——这就是要拆掉的错误语义）
- `cli_bridge/plugin.py` `_send_with_status`：摘要和真 @ **都** `reply_to=route.message_id` → 群里显示「回复 Ryan / 回复 Codex」
- `cli_bridge/engine.py` `completion_message`（约 496 / 500 行）：在给人看的摘要里写 `Next: /dev-build <task>`（**纯文本**，不是 `<at>`）
- `cli_role` 只有 `codex` / `grok` / `both`
- 任务记录没有 `assignees`；`_reject_if_busy` + `active_for_project` 整项目单飞锁
- 配置上目前把 self id 和 inbound id **都塞进** `trusted_peer_open_ids`，两 Bot 能通，N 个不可维护

### 1.5 群里的人设句（尚未在 Hermes 里钉死拼接点）

命令回复前出现过「我是负责调用codex cli的bot / 我是调用grok cli的bot」。  
profile 的 `SOUL.md` 是英文身份（「You are the Feishu Codex architecture bot…」），**不是**那句中文。中文从哪一层拼上去，撰写时 **没有再对 Hermes 命令包装源码逐行定位**。落地步骤 3 必须 grep 给出出处；定位结果不是 `SOUL.md` 时 **不得顺手改 Hermes 源码**，只改本插件或 profile 层。

---

## 2. 问题：现在是两个 Bot 的特例

若只「把体验修漂亮」而不改模型，会把下面绑死：

1. 永远只 @ 一个 `peer_open_id`。第三个 Bot 无处可挂。
2. 入站允许的 `ou_` 和出站 `<at>` 的 `ou_` 混在同一列表。N 个 Bot 是有向的 N×(N−1) 条边。
3. 摘要和命令同一条回复链：人看见「回复 Ryan」里夹着 @Grok；`Next:` 看起来像命令，实际对端不会因此开工。
4. 一对多（一条消息 @ 多个 Bot 带同一个 `/dev-build`）会让共享 TaskStore + 项目锁打架，或 `message_id` 去重让第二人直接 duplicate。
5. Hermes 对 `@_all` 视为提到自己；N 个 Bot 都 `allow_bots=mentions` 时 @所有人会全员叫醒。

这些不是「再加一个 peer_open_id_2」能收场的。体验（人设、话题、摘要/真 @）和扩展（花名册、1:1 / 1:N）是同一条发送/身份链。

---

## 3. 设计选择（整包已接受）

### 3.1 花名册，不写死 Codex/Grok 一对

每个 Hermes profile 一份花名册。**逻辑名**是主键，不是 `ou_`。

人类 **不进** 机器花名册。`/dev-prd` `/dev-approve` 等人类权限继续走 `owner_open_id` + `owner_alias_open_ids`。花名册条目 **没有** `prd` 角色。

每个条目字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定逻辑名，如 `architect` / `builder-a` |
| `roles` | 列表，枚举 **仅** `build` \| `review` \| `observe`（可多项，如观察者兼 review 用两项显式写出） |
| `display_name` | 仅用于 `<at>` 显示名 |
| `self_open_id` | 仅本进程自己的 `/bot/v3/info`（本行是「我」时填写） |
| `mention_open_id` | **本 App 出站** @ 对方时用的 `ou_`。类型上只用于构造 `<at>`，**禁止**写入任何入站集合 |
| `inbound_open_ids` | **本 App 入站** `sender=bot:` 允许的 `ou_`（可多值）。类型上只用于鉴权，**禁止**当作 `<at user_id>` |

出站 ping 的函数签名不得再接收「一个 open_id + 一个 trusted 集合然后做成员校验」。出站参数是花名册条目（或 `mention_open_id`），入站参数是 `inbound_open_ids`；二者不能传入同一形参。

配置解析 fail closed：

- 同一 `inbound_open_id` 出现在多个条目 → 启动报错
- 某条目的 `mention_open_id` 出现在 **任意** 条目的 `inbound_open_ids` 里 → 不自动当错误（两 App 视角下偶发可能撞号），但 **测试与实现不得把 mention 填进 inbound 来“省事”**
- `roles` 为空、含未知值、或含 `prd` → 启动报错

两个现网 Bot 迁进去只是两行，不是特殊模式。Ryan 助手不进花名册、不进交接。

本进程扮演的角色来自 `roster_self` 那一行的 `roles`，不再用 `cli_role: codex|grok` 作为长期键。迁移期见第 4 节旧键规则。

### 3.2 任务上写指派

`TaskRecord` 增加（默认空 = 按角色选花名册里该 role 的默认一人；同一 role 多行时必须显式指派，否则 fail closed）：

- `assignees.build`：花名册 `id`
- `assignees.review`：花名册 `id`
- `watchers`：花名册 `id` 列表，只收 `multicast-notify`，禁止对其发 `unicast-command`

不要「唯一对端」。一对一交接 = @ `assignees.*` 那一个。

### 3.3 对话模式（和体验绑在一起）

| 模式 | 规则 |
| --- | --- |
| `unicast-command` | 恰好一个 `<at mention_open_id>` + 一条可执行命令（`/dev-* <task_id>`）。默认 build/review 交接走这条。**新消息**，不要 `reply_to` 人的批准消息。发送后必须检查发送 API 响应的 `mentions[]` **非空**；为空视为送达失败，不得把 `last_handoff_status` 记为 `ok`，并在随后的 `human-summary` 里报告送达失败。错误的 `mention_open_id` 在飞书侧只显示名字、不产生 @（见 1.1），不能静默当成功。 |
| `human-summary` | 给人看的 `stage=` 摘要。可 `reply_to` 人的原消息。禁止 `<at>`。禁止可执行完整命令串：`/dev-*` 后接 task_id 的形式，或以 `/` 开头的整行。禁止人设句。禁止 `Next: /dev-build …`。命令名 **不带** task_id 出现在叙述句中合法，例如「已向 architect 发出 /dev-review」。这是 **人类可读性规则**，不是安全规则：对端 `allow_bots=mentions` 下没有真 @ 收不到消息；测试断言按可读性写，不要写成「正文不得出现 `/dev-` 子串」。 |
| `multicast-notify` | 可 @ 人 + `watchers`。正文遵守与 `human-summary` 相同的可读性规则（无 `<at>` 以外的可执行命令串；notify 里的 `<at>` 只点观察者，不下 `/dev-* <task_id>`）。 |
| `multicast-command` | **默认禁止。** 开启前置四条必须同时满足：（1）目标角色相同；（2）任务可分割；（3）已不再使用整项目单飞锁（见 3.6）；（4）**每个目标独立 `task_id` 或显式子任务标识**——共享 TaskStore 下同一 `om_…` 会推给多个 Bot，靠 `message_id` 去重决定谁干活不可控。 |
| 禁止 | `@all`；一条消息 @ 多个不同角色还带同一个 `/dev-review <task_id>` |

`/dev-resend` 继续区分：`/dev-resend <id>` 只重发 **human-summary**；`/dev-resend <id> handoff` 只重发 **unicast-command**。不增加 handoff 轮数、不重跑 CLI。Peer 不得持有 `/dev-approve` `/dev-prd` `/dev-cancel` `/dev-resend`。

### 3.4 鉴权

- 飞书侧：每个参与交接的应用保持 `FEISHU_ALLOW_BOTS=mentions`，且必须开通并 **发布** `im:message.group_at_msg.include_bot:readonly`。不要 `allow_bots=all`，不要申请全群 `group_msg`。
- 插件侧：入站 `sender.open_id` ∈ 某花名册条目的 `inbound_open_ids` 才是 peer。人类仍走 `owner_open_id` + `owner_alias_open_ids`。Peer **不能** 获得 `/dev-approve` `/dev-prd` `/dev-cancel` `/dev-resend`。
- 出站 `@` 只用该条目的 `mention_open_id`。禁止用「对端 self open_id」去填入站白名单并指望它们相等（两 Bot 实测不相等）。

入站 ID 的来源：对端第一次 `sender=bot:` 日志，或发送 API 返回的 `mentions[].id`（那是 **发送方** 视角，给发送方当 `mention_open_id` 用）。不要从显示名学习，不要调「群成员列表」当 Bot 发现（接口不含机器人）。

### 3.5 人设

从 **命令成功/失败回复** 中去掉身份朗诵。需要说明角色时：飞书 Bot 显示名 + `/dev-help` 正文。  
步骤 3 验收：grep 定位中文「我是负责调用codex cli的bot」出处并写入实现记录。若不是 profile `SOUL.md`，只改本插件或 profile，**不改 Hermes 源码**。

**步骤 3 定位记录（2026-09-01）：**

- 精确中文「我是负责调用codex cli的bot / 我是调用grok cli的bot」**不在** `cli_bridge/`、**不在** 两 profile 的 `SOUL.md`（英文身份）、**不在** Hermes 源码树。
- 命令回复 Hermes 日志字数与插件返回值一致（例如 `accepted (reviewing)` 为 58 字符），说明网关 `adapter.send` 的 payload **没有**这句前缀。
- 最接近的 profile 来源是英文 `SOUL.md`「You are the Feishu … bot」，若有回合落到 LLM 可能被译成中文自我介绍。
- **未改 Hermes 源码。** 已在两 profile `SOUL.md` 加「Never introduce yourself…」；插件对出站摘要/真 @/命令返回值做 `strip_identity_preamble`。

**步骤 3 源码 + API（2026-09-02，Hermes v0.21.0 `fab3643`；不再用「简介」猜测）：**

1. **出站包装源码（逐段）：** `cli_bridge.plugin.cmd_review` 返回 `task {id} accepted (reviewing)`（32 位 task_id → 正好 58 字符）。`gateway/run.py` 插件命令分支 `return str(result)`。`gateway/platforms/base.py` `_process_message_background` 把该字符串原样交给 `adapter.send(content=text_content, reply_to=event.message_id)`。Feishu `adapter.format_message` 只 `strip()`；`_build_outbound_payload` 对纯文本走 `{"text": content}`，markdown 走 `post.zh_cn.content` 的 `md` 行，**都不拼接身份句**。`/bot/v3/info` 水合只填 `_bot_open_id` / `_bot_name`，不写入发送正文。
2. **飞书 API GET 历史交接正文：** `GET /im/v1/messages/:message_id`（`im:message` 即可；拉群历史要 `im:message.group_msg`，本方案不做）。`om_x100b6670f62fc4a4b32a5fd64102d43`（Codex 真 @ Grok `/dev-build`）body=`{"text":"@_user_1 /dev-build 79e850c87efc495c9dfeb74de7a6e1fc"}`；`om_x100b6670f2c070a4b39aace78bf73e8`（Grok 真 @ Codex `/dev-review`）body=`{"text":"@_user_1 /dev-review 79e850c87efc495c9dfeb74de7a6e1fc"}`。`mentions[].name` 是「Codex 架构」，**正文没有**「我是…bot」。
3. **飞书 API 探测：** 用 Codex App `POST /im/v1/messages` 发唯一 marker，立刻 `GET` 同一 `message_id`，再 `DELETE`。发送响应与 GET 正文都是 marker 原样，**飞书存储层不插入身份句**。
4. **仍未知（现有权限证伪不了）：** 客户端是否在气泡外另画「机器人描述」。`GET /application/v6/applications/:app_id` 返回 99991672（缺 `admin:app.info:readonly` / `application:application:self_manage`），本轮不申请。`/bot/v3/info` 只有 `app_name`，没有 description 字段。
5. **未改 Hermes 源码。**

### 3.6 锁与去重

- **本轮不动项目锁。** 现在：整个 `project_root` 同时只能有一个 in-flight（drafting/building/reviewing）。两 Bot 语义够用。锁粒度改动与花名册迁移叠加会放大回归面。
- 互斥键改为 `(project, assignees.build)` 或 `(task_id,)` **钉为硬前置**：开启 `multicast-command` **或** 花名册出现第二个 `build` 角色条目之前必须先改锁。在此之前不得声称支持多 builder。
- `message_id` 去重保留防重放；**不要**用它实现「一对多只有一个人干活」（飞书给每个被 @ 的 Bot 同一条 `om_…`）。这既是禁忌，也是 `multicast-command` 开启前置第 4 条的原因。

---

## 4. 配置示意（两个现网 Bot 迁入，不是特例语法）

不要再引入 `peer_open_id` 标量。字段名可在实现时微调，语义不行。

```yaml
# grokdev plugins.entries.cli-bridge.settings（示意）
roster_self: builder-a
roster:
  - id: architect
    roles: [review]
    display_name: Codex 架构
    mention_open_id: ou_ef9ee8e8317bfaf8a088b7bf7106e521   # 本 App 去 @ 对方
    inbound_open_ids:
      - ou_6ebc8da986387529b5c99fa43d458671                 # 本 App 看见对方发言
  - id: builder-a
    roles: [build]
    display_name: grok 开发
    self_open_id: ou_4ae43ad446ea716566fe7b655b0633b3
```

Codex profile 对称填写：Grok 的 mention/inbound 用 **Codex App 视角** 的那两串（`ou_4ae43a…` 与 `ou_e2d0d7…`）。

人类 owner 仍用现有 `owner_open_id` + `owner_alias_open_ids`，不进机器花名册。

**旧键兼容（收紧版）：**

- **仅** 存在旧键 `peer_open_id` + `trusted_peer_open_ids`、没有任何 `roster`：合成一行花名册并打 warning，限期一个版本删除旧键。
- `roster`（或 `roster_self`）与 `peer_open_id` / `trusted_peer_open_ids` **同时存在** → **启动报错**。不允许两套配置并存时「哪套生效」成为测试双可过的漏洞。
- 纯新配置：不得再读旧键。

---

## 5. 明确不做

- 不重启、不改名、不复用 Ryan 助手 / `ai.hermes.gateway`
- 不把 `allow_bots` 改成 `all`
- 不自动批准 PRD；Bot 不能互相 `/dev-approve`
- 不写论文 Vault；测试项目仍是 `loop-sandbox`
- 不 git commit/push/merge、不建 GitHub PR（除非另开任务）
- 不在一个 Hermes 进程里挂两个飞书 App（与 Hermes single-bot 注释相反）
- 不把「群里所有 Bot」自动扫进花名册（无可靠 API；身份必须显式配置）
- 本轮不改项目锁粒度（见 3.6）
- 定位人设句后不顺手改 Hermes 源码

---

## 6. 落地顺序

1. **契约与测试（不接飞书）** — 进入实现的第一刀，须覆盖：  
   - 花名册解析：`roles` 仅 `build|review|observe`；含 `prd` 或空/未知值报错  
   - mention id ≠ inbound id：出站 ping 用 `mention_open_id`、入站鉴权用 `inbound_open_ids`；出站函数不得做「mention ∈ inbound 集合」校验  
   - 同一 `inbound_open_id` 出现在多个条目 → 解析失败  
   - `human-summary`：禁止 `<at>`、禁止 `/dev-build <task_id>` 或以 `/` 开头的行；叙述句「已向 architect 发出 /dev-review」必须 **通过**  
   - `unicast-command`：不含对 **人消息** 的 `reply_to`；发送结果 `mentions[]` 为空 → 送达失败，不得记 `ok`  
   - 第三个 `observe` Bot 可出现在 `watchers` 的 notify 中，但不执行 `/dev-build` / `/dev-review`  
   - 纯旧配置 → 合成花名册 + warning；新旧键并存 → 报错  
2. **迁现网两行花名册**  
   删除对 `peer_open_id` 的硬编码依赖；行为与现在两 Bot 闭环等价。只重启 `codexarch` / `grokdev`。
3. **体验**  
   grep 定位命令回复人设句出处并记录；去掉命令成功/失败回复中的朗诵；拆摘要 / 真 @。出处不是 `SOUL.md` 则只动插件或 profile。
4. **群测**  
   新的小 PRD（不要复用已 `ready_for_pr` 的任务）。验收：  
   - 人批准后，Grok 入站必须 `sender=bot:` 且命令来自真 @ 那条，而不是摘要里的叙述  
   - 摘要话题挂在人；命令消息不挂在「回复 Ryan」  
   - 故意配错 `mention_open_id` 时，human-summary 报告送达失败，对端无 `sender=bot:`  
   - 终态 `ready_for_pr` 不再发 unicast-command（`handoff skipped`）
5. **第三个 Bot / 第二 builder / multicast-command（可选后续）**  
   加花名册一行前：该应用 `include_bot` 已发布。出现第二个 `build` 或要开 `multicast-command` 前：先改 3.6 的锁。不改状态机主路径。

实现前不要声称「已经支持 N 个 Bot」；两 Bot 互 @ 已在第 0 节，那是前提不是本方案的完成定义。

---

## 7. 评审裁决（fable5，2026-08-31）

1. **体验 + 花名册 + 身份拆分同一份契约：同意。** 禁止两字段补丁。出站/入站必须类型隔离。
2. **`multicast-command` 默认禁止：同意。** 开启前置三条保留，并加上第四条独立 `task_id` / 子任务标识。
3. **人设句：从命令回复去掉**，仅 Bot 显示名 + `/dev-help`。步骤 3 必须 grep 出处；非 `SOUL.md` 不改 Hermes 源码。
4. **旧配置：警告兼容一个版本 + 新旧并存即启动报错。** 只允许纯旧配置合成一行花名册。
5. **项目锁本轮不动。** 改锁钉为开启 `multicast-command` 或第二个 builder 的硬前置（3.6）。

精度修正 (a) `roles` 列表、去掉花名册 `prd`；(b) human-summary 可读性规则而非「禁止 `/dev-` 子串」；(c) `mentions[]` 送达验证 + inbound id 全局唯一 — 均已写入第 3 / 4 / 6 节。

相关操作说明仍见 `SETUP_FEISHU.md`（权限、`include_bot`、现网 ID 映射）。
