# 三个 Codex 角色如何继续开发

本方案替代 Grok Build 主开发的分工，不启用历史 Grok/飞书协作循环。
默认在一个主会话内运行 Architect 主控和 Builder、Repo Steward 两个子 agent；
不要求用户管理三个平行对话，也不新增模型或插件。角色名称是职责约定，不是新的账号或权限隔离。

## 用户指定的模型配置

| 角色 | 模型标识 | 推理强度 |
| --- | --- | --- |
| Architect，唯一主控 | `gpt-5.6-sol` | `ultra` |
| Builder，主力开发子agent | `gpt-5.6-sol` | `medium` |
| Repo Steward，仓库流程子agent | `gpt-5.6-sol` | `medium` |

用户对子agent的“GPT-5.6”使用当前可调用的Sol标识；官方GPT-5.6别名也指向Sol。
2026-09-01配置核对时，主控本地turn context已是`gpt-5.6-sol / ultra`，未修改或伪造运行记录。
两名后续子agent以显式`model=gpt-5.6-sol`、`reasoning_effort=medium`调用。
子agent不使用默认继承，否则会继承主控的Ultra；同一时间仅运行这两个角色，不继续启动旧的继承配置worker。
仓库文件是今后调度的规则，不会热切换主会话模型；新会话应检查UI/实际运行配置。

## 分工和产物

| 角色 | 主要职责 | 必须交付 | 不可代替的职责 |
| --- | --- | --- | --- |
| Architect，主会话 | 拆包、设计、冻结契约、协调依赖、最终代码审查与验收 | 工作包、版本化契约决定、绑定提交的验收结论 | 不把主要编码留给自己；不能替用户关闭人工 gate |
| Builder，子 agent | 按冻结契约完成 schema、代码、测试和修复 | 改动清单、测试证据、未决问题、候选提交或文件摘要 | 不自行改架构，不自行合并，不自批验收 |
| Repo Steward，子 agent | Issue/分支/PR/CI，独立范围检查与验证支持 | head/base/测试提交、CI run/job、交接状态和风险 | 不兼任主要开发；无 Architect 明确指令不能合并 |

Architect 的验收和合并指令是两个不同记录；两者都不能替代用户 gate 或 GitHub 分支保护。
同一个 GitHub 账号下的三个 Codex 角色不能冒充三个独立人工审批账号。
工程契约疑问交给 Architect 处理，不逐项打断用户；只有真实产品选择、权限阻塞或人工 gate 才找用户。

## 每个工作包的运行顺序

1. **Architect 下发任务**：固定目标、完整基线 SHA、依赖、契约版本/摘要、允许改动的路径、非目标及验收条件。
2. **Builder 实现**：写主要代码和测试。发现未定义契约时提交最小问题与选项；停止依赖该决定的代码，不阻塞其他已明确工作。
3. **Repo Steward 准备交付**：核对增量和文件归属，串行处理 Git，创建或更新获准的 draft PR，收集 CI 证据。
4. **Architect 总体验收**：自己审查设计/实现与跨模块关系，重放最终测试；失败项退回 Builder，不能靠改状态转为通过。
5. **Repo Steward 记录结果**：保存绑定当前提交的结论。需要合并时另等 Architect 的精确指令；需要人工 gate 时向用户展示可审阅产物。

这里的准备、实现、审查、返工仅是协作阶段，不修改项目 runtime schema、生命周期或 human gate。

## 并行与工作目录

当前团队的子 agent 默认共享工作目录，并不会自动获得独立 worktree。
先采用单业务写者：Builder 写实现，Architect 写设计/任务单，Steward 读取源码并维护指定交接文件。
例如 `contracts.py` 和 schema 注册只能在一个 agent 手里修改，不能边实现边让另一个 agent改同一文件。

确有独立模块可同时编码时，再为写者建立不同分支/worktree，并给每个 agent 明确 cwd、base 和允许路径。
审查与CI可以在固定候选提交的单独 checkout运行，避免验证时源码继续变化。
Git操作由 Steward串行调度；任何 agent 都不能在其他 agent使用的共享目录切分支、reset或clean。
Worktree不隔离网络、凭据和GitHub权限；需要硬权限隔离时另配环境，不能靠角色提示词宣称已经实现。

## 交接单的最低字段

```yaml
packet_id: VPKB-000-capture-contracts
architect: Architect
implementer: Builder
repository_owner: Repo Steward
packet_base_sha: <完整40位SHA>
contract_path: <冻结规范路径>
contract_sha256: <规范内容摘要>
contract_status: <design-pending或frozen>
allowed_paths: [<允许修改的精确文件或窄glob>]
acceptance: [<可观察的行为和拒绝条件>]
candidate_head_sha: <提交前留空，不伪造>
blocking_questions: []
```

未冻结的接口不得标为可以开始实现。技术范围内的冻结由 Architect负责；更改产品目标或人工决定仍服从用户。

Steward 的验收证据还要包含：`reviewed_head_sha`、`base_sha`、`tested_checkout_sha`、
`tested_ref`、CI run ID/attempt/job ID/结论、Python版本、锁文件摘要、测试命令/数量、未跑项及遗留问题。
若CI测试的是PR合并预览，就不能把其SHA填成head SHA。
Head改变后旧结论只属于旧提交；base改变后要重新检查集成结果和merge preview，不覆盖历史证据。

## 当前接续点与下一包

2026-09-01 当前可验证状态：

- PR [#94](https://github.com/RyanHuangNLP/video-paper-wiki/pull/94) 仍是
  open/draft → `integration`，未合并；base 为
  `08709894adfb20ec07e976783f0ba436d975b74f`。
- VPKB-000 在精确 head
  `acd3821b15e62bce13fa07b82c1665d501f27f67` 完成。Tests run
  `33456016766` 的 Linux/macOS × Python 3.12/3.13 四项各 1658 通过；
  实际 checkout 是合并预览
  `1db75993d8a9843f73a532c9838361462ce05561`。独立 Architect 决定及
  CI/merge-parent 记录保存在 `artifacts/verification/VPKB-000-projection-contracts/`。
- 这份完成结论允许开始 VPKB-001 架构与契约冻结，不自动允许生产代码、PR
  ready/review、merge、auto-merge 或人工 gate。
- 目录与 overlays 继续冻结为 67；保留所有既有未跟踪计划、`inbox/`、`tools/`
  和 `.DS_Store`。

当前 packet 是
[VPKB-001-adapter-contract](packets/VPKB-001-adapter-contract.md)，规范为
[vpkb-001-adapter-contract-v1](contracts/vpkb-001-adapter-contract-v1.md)。
首个有界子版本只冻结固定上游的只读 `transaction inspect`、确定性
`bundle.json + content/<sha256>` 传输、`upstream-authority.v1` 和隔离的 file
`stable_source_id` 调用。两个 Python 子进程都只从临时私有执行树加载 profile 验证过的
21 个源码文件，不直接从含 ignored `.pyc` 的 live checkout 导入；继承环境会被只指向
独立私有 scratch 的 `HOME/TEMP/TMP/TMPDIR` 精确替换。它不包含
apply/recover/admin、真实 Vault、ledger merge、
receipt/audit、mapper/compiler、Docling、BM25/index 或 retrieval。

架构冻结候选先由两个 medium 子agent独立审查，再由 Repo Steward 精确路径提交并收集
新的四项 CI。Architect 只有在核对新 head、base、merge preview、job 日志和提交 blob 后
才可签发 freeze acceptance。Builder 随后依据另行下发的精确 allowed paths 编写主要实现；
冻结 schema/profile/规范、现有 facade/capture 契约、vendor pin 和 generation revision 1
不得由 Builder 顺手修改。

`base-catalog-v1` generation revision 1 在此子版本保持不变，因为 inspect adapter
不生成 catalog rows。第一个实际消费 authority 的 mapper/compiler 必须另升 generation
profile revision 并绑定 adapter、schema/profile 和 authority digest。VPKB-001 仍按
`adapter-contract` → `integrity-runtime` 顺序完成，首个子版本通过不代表整个 slice 或
VPKB-001 完成。

保持同一 PR 中的单业务写者：Architect 写冻结设计，Builder 在放行后写主实现，Steward
串行处理 Git/CI。每次审查以 `packet_base_sha..candidate_head_sha` 为本包增量，同时检查
跨模块不变量；PR94 的全部历史 diff 不是本包新增代码。当前 workflow 只自动覆盖以
`integration`/`main` 为 base 的 PR，不改变 base 或另开不能触发现有矩阵的层叠 PR。

## 工具与持续运行的实际边界

本会话使用现有子agent能力即可，不需要另造一个多agent服务或改全局Codex设置。
角色与上下文保存在仓库文件，后续会话读这些文件恢复；文件本身不会启动后台agent、定时任务或无限开发循环。
在2026-09-01的本次协作配置阶段，未调用Grok，也未创建新的侧栏任务、worktree、Issue、PR或合并操作。

官方能力说明：[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)、
[Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)、
[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。
[GPT-5.6模型标识](https://developers.openai.com/api/docs/guides/latest-model)。
这里的三角色职责、单写者与验收记录是本项目工作约定。
