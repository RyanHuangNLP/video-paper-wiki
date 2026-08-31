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

2026-09-01核对结果：

- PR：[#94](https://github.com/RyanHuangNLP/video-paper-wiki/pull/94)，open/draft → `integration`，未合并。
- 本地和PR head：`9d87dc67b949fc0cef5ac64b91a2d15aea8ec0fe`。
- PR base：`08709894adfb20ec07e976783f0ba436d975b74f`。
- [CI run 33420150322](https://github.com/RyanHuangNLP/video-paper-wiki/actions/runs/33420150322) 四项成功，各899项通过。
  实际checkout为合并预览`3c0adb319fe768ba583d6efcdf836949161d7d8b`，
  不是裸head；精确环境与job记录在capture-contracts的`ci-observation.json`。
- 保留已有未跟踪文件；目录/overlays仍冻结67。阶段仍是VPKB-000。

capture/code-evidence子包已在上述head完成本地与CI验收。
当前工作包是 [VPKB-000-transaction-facade](packets/VPKB-000-transaction-facade.md)：
固定上游submodule已初始化到精确pin且保持干净；Builder运行公开CLI隔离fixture，
Architect制定统一纯数据契约，Steward独立审查。准确阶段、规范摘要和验收状态以
`task-index.yaml`为准；没有完成001生产适配，也不沿用上一包的通过结论。

该包最新本地候选已通过 Python 3.12/3.13 各1239项及独立安装包验收，
274个输入摘要为`437fb3bb0cc0c8baa26e93cb374b1814519771c3e0cd3df161e6ab24a466fa8e`。
首次安全扫描误报的两次失败保留在独立证据中，没有改写成通过。
此处的本地候选尚不代表新提交的CI验收；交付后必须核对PR当前head/base与实际测试checkout，
不能把上面capture-contracts的旧CI套用到新代码。合并和人工gate仍未授权。

短期保持同一PR中的单写者推进，并以`packet_base_sha..candidate_head_sha`单独审查每包增量，
同时检查与其余代码的兼容性。PR94的完整历史diff不是下一包新增代码。
若随后改成每包独立PR，由Architect先明确分支/base策略：当前workflow只自动覆盖以
`integration`或`main`为base的PR，直接把新PR的base设成repair分支不会触发这套CI。

随后按依赖推进：capture/code-evidence契约 → 纯transaction facade → projection/SQLite契约，
固定上游源码/fixture证据可在文件和依赖独立时并行补齐；000完整通过后才开始001运行时。
不能靠继续扩目录或增加PR数量代替引擎验收。

## 工具与持续运行的实际边界

本会话使用现有子agent能力即可，不需要另造一个多agent服务或改全局Codex设置。
角色与上下文保存在仓库文件，后续会话读这些文件恢复；文件本身不会启动后台agent、定时任务或无限开发循环。
在2026-09-01的本次协作配置阶段，未调用Grok，也未创建新的侧栏任务、worktree、Issue、PR或合并操作。

官方能力说明：[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)、
[Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)、
[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。
[GPT-5.6模型标识](https://developers.openai.com/api/docs/guides/latest-model)。
这里的三角色职责、单写者与验收记录是本项目工作约定。
