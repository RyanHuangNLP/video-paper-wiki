# 飞书多 Bot 协作 — 第一阶段实施方案

- 日期：2026-08-30
- 状态：方案（Phase 1）。**未部署、未改线上网关、未做同群双 Bot 真实验收。**
- 依据：`/Users/huangzhanpeng/Downloads/Grok-Build-飞书多Bot协作交接.md`
- 实现方：Grok Build；架构/审核：Codex；用户确认后才进入第二阶段。

本文区分 **已验证事实**、**未完成事项**、**下一步（需确认）**。
不把 mock、单测、旧私聊桥接或「Ryan的智能助手」私聊 `/status` 当作多 Bot 闭环已完成。

---

## 1. 已验证事实（2026-08-30 本机复核）

- Hermes Agent **v0.20.6**，源码 commit `26350357`；CLI：`/Users/huangzhanpeng/.local/bin/hermes`。
- Codex CLI **0.142.0**：`/opt/homebrew/bin/codex`。
- Grok CLI **1.0.5**：交接路径 `/Users/huangzhanpeng/.local/bin/grok` 存在；`which grok` 为 `/Users/huangzhanpeng/.grok/bin/grok`；二者指向同一安装包。
- 官方 Grok 委派 skill **存在**：`~/.hermes/hermes-agent/optional-skills/autonomous-ai-agents/grok/SKILL.md`（以及站点文档副本）。这是 Hermes 通过 terminal 调用真实 `grok` 的指南，**不是** xAI HTTP 模型 provider，也不是独立调度器。
- 官方飞书文档 **存在**：群聊需 @；`FEISHU_ALLOW_BOTS` = `none`（默认）| `mentions` | `all`；peer Bot **不走** 人类 `FEISHU_ALLOWED_USERS`。
- 官方多 profile 网关文档 **存在**：每个 profile 独立 home（config / `.env` / sessions / memory）；默认 **一 profile 一进程**；禁止两个进程写同一个 Hermes home。
- 现网 `ai.hermes.gateway` LaunchAgent **正在运行**（默认 profile）。`plugins.enabled` 为空；编码/终端/文件等 toolset 在默认配置中禁用。
- `~/.hermes/profiles` **不存在**：目前只有默认 profile，没有第二套 Bot 身份。
- 暂存桥接 `/private/tmp/hermes-cli-bridge-dev.W4sQSl` **仍在**。`clients_from_policy()` **无论 policy 是否为空都返回 `DisabledLiveClients`**（见该文件约 72–78 行）。不具备真实 CLI 开发能力。
- 论文 Vault 路径存在且不可被本进程列出；**本次未写入**。

未在本阶段验证、不得宣称完成：指定开发群收发、两个独立飞书应用同群分别回复、Bot-to-Bot 交接、真实 PRD→确认→实现→审核闭环。

---

## 2. Bot identities and isolation

最新要求是 **两个真实、独立的飞书企业自建应用 Bot 进入同一个指定测试群**，各自发言、各自会话、任务可追溯到 Bot 与 CLI。  
**禁止**：一个 Bot 用别名扮演双角色；禁止静默单 Bot 模拟。

| 首批身份 | 飞书应用 | Hermes profile | 网关进程 | 真实 CLI |
| --- | --- | --- | --- | --- |
| Codex 架构／审核 | **新建**应用（建议显示名「Codex 架构」；最终命名由用户定） | `codex-arch`（空白 profile，不 `--clone-all` 默认助手） | `ai.hermes.gateway-codex-arch`（独立 LaunchAgent） | `/opt/homebrew/bin/codex` 非交互（PRD/审核只读） |
| Grok 开发 | **新建**应用（建议显示名「Grok 开发」） | `grok-dev` | `ai.hermes.gateway-grok-dev` | `/Users/huangzhanpeng/.local/bin/grok` 或 `~/.grok/bin/grok`（同一 1.0.5 二进制） |

**现有 Bot「Ryan的智能助手」**：继续占用当前 `ai.hermes.gateway`。本方案 **不改名、不删除、不给它再挂一个消费者**。是否把该 Bot 改派为上表某一角色，**等用户确认**；在确认前，双 Bot 测试用两套新应用，避免打到现网助手上。

隔离规则（官方契约，配置即可大部分落地）：

- 每个 Bot = 一个 Hermes profile = 一份独立 home（凭据、sessions、memory、SOUL、gateway 状态不混写）。
- **不要** 对默认 profile 打开 `gateway.multiplex_profiles`：双 Bot 需要进程级隔离和独立崩溃域。
- **不要** 两个进程指向同一 profile / 同一飞书 App Secret。
- 群内 `group_sessions_per_user: true`（已在默认配置中为 true）：同一群按发送者隔离会话，避免用户与 Bot 上下文串线。
- 群策略：仅指定测试群；人类 allowlist 仅本人；`allow_bots: mentions`（不要 `all`）。
- Peer Bot 不经过人类 allowlist → **必须另做受信 Bot `open_id` 校验**（这是代码任务，不是把 `allow_bots=all` 当设计）。

GitHub 助手为后续阶段，不计入本批两个 Bot，也不把「两个 Bot 验证」写成三角色已交付。

---

## 3. Gateway / CLI relationships

```text
用户（飞书手机）
  └─ 指定测试群，@ 对应 Bot
        ├─ Feishu 开放平台 ──WS──► Hermes gateway 进程 A (codex-arch)
        │                              └─ 插件/状态机 ──subprocess──► codex exec（只读）
        └─ Feishu 开放平台 ──WS──► Hermes gateway 进程 B (grok-dev)
                                       └─ 插件/状态机 ──subprocess──► grok --no-auto-update -p …

任务产物（PRD、实现报告、测试日志、审核意见、SHA-256）
  └─ 持久目录中的 TaskStore；群消息只发摘要 + 产物引用/分页，不截断确认 hash
```

关系说明：

- Hermes 飞书适配器只负责收发、鉴权、@ 门控、session 目录。它 **不是** Codex/Grok 的模型提供方。
- 官方 Grok skill 规定自动化应使用真实 `grok`、`--no-auto-update`、显式 `workdir`/`--cwd`。skill 文中的 `--always-approve` **未经用户授权，本方案不使用**。
- Codex 走官方非交互调用（见 [Codex noninteractive](https://developers.openai.com/codex/noninteractive/)）。本机曾出现 `codex exec resume <id> --sandbox read-only` 参数位置错误；实现时以 **本机 `codex exec --help`** 为准，且 `login status` 可能写 **stderr**。
- 默认 profile 的 `model.provider: auto` 与 OpenRouter `base_url` 属于现网个人助手，**不得**当作 Codex/Grok 编码执行路径。编码 Bot profile 禁止把「Hermes 调付费模型写代码」冒充官方 CLI。
- 现网 `ai.hermes.gateway` 保持不动。Phase 1 **不** 重启该消费者，不给同一飞书 App 再挂进程。

---

## 4. Reuse vs config vs code

| 类别 | 内容 | Phase 1 动作 |
| --- | --- | --- |
| **直接复用** | Hermes 飞书 WS 适配器、profile/gateway 安装模式、群 @ 门控、`allow_bots=mentions`、Grok skill 的 CLI 调用方式、Codex/Grok 本机订阅登录、旧 PRD 中的账户/确认 hash/分页/取消/串行/Vault 禁写契约 | 只读参考；不改现网 |
| **只需配置（用户授权后 Phase 2）** | `hermes profile create` 两个空白 profile；各跑 `setup` 绑定**各自**飞书 App；`gateway install` 生成 `ai.hermes.gateway-<name>.plist`；测试群 `group_rules`；人类 allowlist；显示名 | Phase 1 只列出，不执行 |
| **必须写代码（配置解决不了）** | 见下表 | Phase 2 在确认后实现 |

配置解决不了、必须列为代码任务：

1. 任务状态机：发起、用户确认（版本/完整 SHA-256）、交接、审核退回、status、cancel、重启恢复。
2. 把 `clients_from_policy` 接到真实固定 argv 的 Codex/Grok（仅在 Codex 安全审核通过的本地 policy 之后；Phase 1 **不接线**）。
3. 子进程 runner：进程树取消/超时；取消后核查真实进程，不只回「已取消」。
4. 受信 peer Bot 身份（双方 `open_id`），禁止用 `allow_bots=all` 代替。
5. 忽略自身消息；同一飞书事件去重；进度/「收到」不启动下一轮编码。
6. 每项目串行锁；building 任务重启后不盲目重跑写入。
7. 产物落盘与分页；确认绑定保存后的 PRD hash；群摘要不截断 hash。
8. Codex 预检只对 login 合并 stderr；Grok 退出码 0 但 cancelled/空输出/轮次耗尽视为失败。
9. 不把飞书 App Secret 传给编码子进程；限定项目路径、symlink、项目外写入检查。

明确不做：启用现网 live factory、重启现网 gateway、Pi/Slack/企业微信、付费 API 回退、paper-wiki 业务模块、`vpwiki-admin`、push/PR/merge、`--always-approve` / `bypassPermissions`。

---

## 5. Old staging keep / adjust / abandon and persistent dir

暂存根：`/private/tmp/hermes-cli-bridge-dev.W4sQSl`（可能被系统清理，**不能当部署目录**）。

建议持久目录（用户确认后 Phase 2 再拷贝实现，Phase 1 不搬）：

`/Users/huangzhanpeng/python_code/video-paper-wiki/tools/feishu-dev-collaboration/`

与 `video-paper-wiki` 产品模块隔离；**禁止**写入 `/Users/huangzhanpeng/Documents/video-paper-vault`。

| 处置 | 路径/能力 |
| --- | --- |
| **Keep（挑选复用，不在 /tmp 上继续开发）** | `cli_bridge/engine.py` 状态机骨架、`store.py` 任务记录、`sanitize.py`、`plugin.py`/`route.py` 命令入口、`models.py`/`constants.py`、`tests/` 中与确认 hash/分页/取消/busy 相关的用例思路；`CODEX_REVIEW.md` 未决清单 |
| **Adjust** | 入口从「仅本人私聊」改为「指定群 + 本人 + 明示受信 Bot」；命令可保留 `dev-*` 作诊断，但产品入口是群内 @Bot；身份字段按真实飞书 event 测 open_id；runner 进程树 |
| **Abandon** | 把单 Bot 私聊当作最终产品；把 `DisabledLiveClients` 当完成；`.tools/apply_patch` 工具副本；`allow_bots=all`；把 30 个旧测试或 host fixture 当成多 Bot 通过；在 `/tmp` 上部署；克隆默认 profile 的 OpenRouter/全禁用 toolset 当编码 Bot |

拷贝时排除：`__pycache__`、`.tools/`、会话库、缓存、凭据、无关二进制。

---

## 6. Initiate / confirm / handoff / review-return / status / cancel / restart

沿用旧 PRD 状态名，但执行面改到群：

`draft → approved → building → reviewing → needs_changes → ready_for_pr`  
以及 `needs_user`、`rate_limited`、`cancelled`、`failed`。

| 行为 | 谁 | 群内可见规则 |
| --- | --- | --- |
| **发起** | 用户 @Codex 架构 Bot，给出需求与测试项目（首版固定一个无业务数据的小项目，**不是** Vault/论文模块） | Codex 建任务 ID，进入 `draft`，产出完整可读 PRD（分页+全文 SHA-256） |
| **用户确认** | 仅 allowlist 人类；命令绑定 **task ID + 已保存 PRD 的完整 SHA-256** | 模型文本不能生成有效确认；PRD 一变旧确认失效 |
| **交接** | 确认后 Codex **显式 @Grok 开发 Bot**（mentions），带 task ID、阶段、产物路径 | 不是后台静默代发却在群里假装两个 Bot；两边都要真实发言归属 |
| **实现** | Grok 只改已确认范围；跑测试；写实现报告 | 退出 0 ≠ 自测通过 ≠ 审核通过 |
| **审核** | Grok 完成后交接 Codex 只读复审真实 diff + 测试命令 | 通过 → `ready_for_pr`（仍不 GitHub）；不通过 → `needs_changes` |
| **审核退回** | Codex @Grok，同一 task ID，附审核意见 | Grok 修复后再次 reviewing；至少设计一次退回路径（Phase 3 才真跑） |
| **status** | 任一首批 Bot 的 status 命令 | 返回阶段、阻塞、CLI 版本、产物 hash；不启动新编码 |
| **cancel** | 用户或超时 | 杀受管进程**树**并回读 ps；状态 `cancelled`；不撤销已写文件除非任务说明如此 |
| **重启恢复** | 网关/Mac 重启 | 读持久 TaskStore；`building`/`reviewing` 不自动重跑写入；重复事件不去重编码 |

交接消息最低字段：接收者 Bot、task ID、阶段、有限重试/轮数。忽略自己的消息。普通进度与「收到」不触发下一阶段。

---

## 7. User authorization steps（本阶段只列出，不执行）

用户确认本方案后，预计需要：

1. 在飞书开放平台 **新建两个应用**，开通 Bot；建议权限含 `im:message`、`im:message:send_as_bot`、`im:chat`、`contact:user.id:readonly`、`application:bot.basic_info:read`（peer 显示名）。
2. 为每个应用发布/可用范围允许测试群。
3. 创建（或指定）测试群，把两个 Bot **拉进同一群**；记录群 chat_id。
4. 本机：`hermes profile create codex-arch`、`hermes profile create grok-dev`（空白，不 clone 默认助手）。
5. 在各自 profile 内 `setup` 飞书（扫码或粘贴该应用的 App ID/Secret）。凭据只进该 profile 的 `.env`，**不要**写进 git、计划或聊天。
6. 各 profile `gateway install`（将新增 `~/Library/LaunchAgents/ai.hermes.gateway-codex-arch.plist` 与 `…-grok-dev.plist`）。**先不 start**，等 Phase 2 代码与 Codex 审核。
7. 配置指定群 allowlist、`allow_bots: mentions`、`require_mention: true`；把两个 Bot 的 `open_id` 交给代码侧受信表。
8. 现网 `~/.hermes/config.yaml`、`~/.hermes/.env`、`ai.hermes.gateway.plist`：**Phase 1 不变**。以后若给「Ryan的智能助手」改角色，需单独确认和备份后再改。

预计会变更的配置（仅 Phase 2+，且需备份）：

- 新增 `~/.hermes/profiles/codex-arch/` 与 `grok-dev/` 下的 `config.yaml` / `.env`
- 新增两条 LaunchAgent
- 不修改默认助手的飞书凭据，除非用户明确把旧 Bot 改派

不需要用户现在做：删旧 Bot、给论文 Vault 授权、开通 API 计费、安装 Pi。

---

## 8. 官方依据（本机已有副本者优先）

- Grok skill（本机）：`~/.hermes/hermes-agent/optional-skills/autonomous-ai-agents/grok/SKILL.md`  
  站点：https://hermes-agent.nousresearch.com/docs/user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-grok/
- 飞书群聊与 Bot-to-Bot（本机）：`~/.hermes/hermes-agent/website/docs/user-guide/messaging/feishu.md`  
  站点：https://hermes-agent.nousresearch.com/docs/user-guide/messaging/feishu/
- 多 profile 网关（本机）：`~/.hermes/hermes-agent/website/docs/user-guide/multi-profile-gateways.md`
- Codex 非交互：https://developers.openai.com/codex/noninteractive/
- Codex App-Server runtime（评估副作用，**默认不启用**）：https://hermes-agent.nousresearch.com/docs/user-guide/features/codex-app-server-runtime/

上述文档中的 `--always-approve`、付费 API、push/合并示例 **不构成本次授权**。

---

## 9. 未完成事项与下一步

**已另做（本地 CLI 闭环，不是飞书双 Bot 验收）：** 持久目录 `tools/feishu-dev-collaboration` 已接线真实 Codex/Grok。`run_loop.py` 于 2026-08-30 跑通 draft→hash 确认→Grok 实现 `add.py`→Codex `verdict: pass`，unittest 2 passed。详见 `tools/feishu-dev-collaboration/LOOP_RESULT.md`。未重启现网 gateway，未建飞书应用。

未完成：第三阶段同群双 Bot 真实验收；GitHub 助手；论文知识库模块。飞书应用创建、扫码、拉群仍须用户完成。

机器侧已接（2026-08-30，仍不是飞书真实验收）：

- Hermes 空白 profile `codexarch` / `grokdev`（未 clone、未 start、现网 `ai.hermes.gateway` 未改）
- 插件按 `cli_role` 拆命令；指定群 + 本人 + 受信 peer `open_id`；Grok 完成后阶段为 `built`，等 Codex `/dev-review`
- 安装与用户步骤：`tools/feishu-dev-collaboration/SETUP_FEISHU.md`

下一步（需 Codex/用户确认后才开始 Phase 2）：

1. 用户确认两个新飞书应用 + 测试群，以及现网「Ryan的智能助手」保持不动。
2. 确认持久目录 `video-paper-wiki/tools/feishu-dev-collaboration/`。
3. 确认首个测试项目路径（空/小项目，非 Vault）。
4. Codex 审核本方案后，Grok 按「代码任务」实现，**不**改线上 gateway、**不**把 factory 接到 live CLI，直到该项被单独点名。

Phase 1 **不声称** 真实飞书 PRD→build→review 环路已跑通。
