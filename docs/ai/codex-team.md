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
- VPKB-000 已在精确 head
  `acd3821b15e62bce13fa07b82c1665d501f27f67` 完成。VPKB-001 首个
  `pinned-read-only-transaction-inspect-adapter-v1` 已在精确 head
  `17c13f6317416f47d2610240aaf905598131e5bc` 完成。Tests run
  `33465872376` 的 Linux/macOS × Python 3.12/3.13 四项各 1747 通过，实际
  checkout 是合并预览 `dd6954f1c2368d83cd6d5f1d5057ed4d20acb327`，随后
  Architect 签发 `ACCEPTED_VPKB_001_PINNED_READ_ONLY_ADAPTER_V1_AT_EXACT_HEAD`。
- 第二个有界子版本的架构已在精确 head
  `3ab19eda4f417b96d89a0a50b2ce2c05233a8478` 接受。Tests run
  `33469912314` 的四项各 1750 通过，合并预览为
  `ea86e96fbbbcaf6fbda360679c6e6d209a6151b7`。三份架构 post-CI 记录
  保持原字节，交由当前实现提交持久化；该 run 只证明架构 head。
- Builder 的 R1 因四类身份替换与覆盖不足被拒绝；R2 修正语义后获独立 GO，
  但最终暂存审计因 helper 末尾空白行而拒绝，22 路径尝试、回滚和旧证据均已保留。
  唯一一字节修正后的 R3 七文件快照
  `c275904d2865cb1560408e1d3ba3894ed172e3a9ecf51c44d5c392e2d5b3a50d`
  已获 Repo Steward 独立 R3 GO，并在 Python 3.12/3.13 各通过 342 项 focused
  和 1835 项全量测试及离线 wheel 验收。它已提交为精确 head
  `57c2519425dbccd6bb48a0f82e77699e17afcfb6`、tree
  `c77a7c6ccc8bae3292611c2b24c33255f248710c`。Tests run `33477484577`
  的四项各 1835 通过，实际 checkout 合并预览
  `058ae19131cc418edc42dd8d311354503a0e515b`，随后 Architect 签发
  `ACCEPTED_VPKB_001_MANUAL_PDF_CAPTURE_DRY_RUN_IMPLEMENTATION_AT_EXACT_HEAD`。
- 目录与 overlays 继续冻结为 67；保留所有既有未跟踪计划、`inbox/`、`tools/`
  和 `.DS_Store`。

当前 packet 仍是
[VPKB-001-adapter-contract](packets/VPKB-001-adapter-contract.md)。第二个有界
子版本已经完成，三份 post-CI 记录由当前架构交付原字节携带。第三个有界子版本规范为
[vpkb-001-transaction-inspect-staging-v1](contracts/vpkb-001-transaction-inspect-staging-v1.md)。
它把已经验证的 transaction proposal 与调用者提供的三组精确 bytes map，确定地写入
当前 checkout 的 `.work/<batch>/transaction-inspect/{content/**,bundle.json}`，供既有
只读 pinned inspect adapter 消费。第一轮独立评审发现，多次单文件 `stage_bytes` 调用之间
替换 batch/transport 目录会把同一 transport 分裂到不同目录 lineage；R1 因而拒绝并保留。
修订 2 改为一次多文件 session：从首个 content 到最终完整集合复核持续持有 checkout、
`.work`、batch、transport 和 content 描述符，并在每次安装前后通过命名重开核对
device/inode。内容先写、bundle 最后写，相同字节精确幂等，不同字节拒绝；既有公开
`stage_bytes` 行为不变。

Builder 和 Repo Steward 已对第三个子版本的精确修订 2 候选分别返回 GO。主控本地在
Python 3.12/3.13 各完成 1838 项全量测试，隔离安装的 wheel 含 24 个 schema，新增 schema
字节与 checkout 相同。精确 21 路径架构已经提交为 head
`62f3063fb612024179125bc7d842abdd3de0a4ee`、tree
`37dfbba09e9f73656af4bb5510f7586bb5d4223e`；新的四项 merge-ref Tests run
`33481415882` 各通过 1838 项，测试 merge preview 为
`910e272879b728aef8d1da1db2ba88d70feba5b0`，随后取得单独的精确 head
Architect 验收。实现 R1 在两个本地 Python 版本各通过 1888 项，但 Repo Steward 发现
complete-set 会忽略 FIFO、symlink、目录、非 digest content extra 和 transport root extra，
因此返回 `CHANGES_REQUIRED`。R1 工作包、候选和 review 原字节保留。当前 revision-2
工作包 SHA-256
`c79ade9aa3b9c70c77250ef3f5a3aa7743c60652b3c4725d5d4e0995a5a67633`
只授权 Builder 在同十个生产/测试路径关闭这一项并重新冻结。Builder 已冻结修正版快照
`75179e9d0a66b3d528a14d6cc48be7139d350380be9b945b61eeb18eb6cb4ab2`；Repo Steward
独立通过 435 项 focused、24 项 lineage/complete-set 和八个自建探针后给出 `GO`。主控又
独立通过 Python 3.12/3.13 各 1895 项全量、435 项 focused、24 项对抗、四个真实 pinned
操作向量和 checkout 外 wheel 验收。主控本地决定
`PASSED_LOCAL_R2_IMPLEMENTATION_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI` 绑定证据
SHA-256 `98ec4d0c3a7571fc46e271bed260191f0bbae6b89230bbd69734a5c132126d9b`。
随后精确临时 index 审计发现一项非语义阻塞：`tests/contract/test_transaction_staging.py`
以两个 LF 结束，cached diff-check 报 `new blank line at EOF`，因此 R2 不得提交。R2 工作包、
候选/review、本地验收、manifest 和交付拒绝全部保留。活动 R3 工作包 SHA-256
`1ba273bd9ae25f00583a4dac4c881b5eeb0d3796faf8b7cc10fffa34e918ac67`
只授权删除最后一个 LF 并生成 R3 证据；目标十路径快照预先锁定为
`e5f9f9b8e8686023183c5871ebb55b4d5ac8c6a9494646f91bb614fab1cedc76`。
Builder 已冻结该精确快照，Repo Steward 独立 R3 审查为 `GO`。主控重新通过 435 项
focused、24 项对抗、四个 pinned 操作向量、Python 3.12/3.13 各 1895 项全量及字节不变的
wheel 验收；本地 R3 决定
`PASSED_LOCAL_R3_IMPLEMENTATION_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI` 绑定 SHA-256
`a4ce61b1035960131d7e6484e637464ee0c302ce8242212dc449287ebc86c8a8`。
该精确 R3 实现已提交为
`fb2cbcb565195a232f22d02c0474ac1b1b34f7d3`、tree
`4a28ee53f71a0f2971f23b87e1f4c06d3bdf5b79`。新的四项 merge-ref Tests run
`33491834331` 各通过 1895 项，merge preview 为
`12bc7925140352fad516405b7eafaa8923d106e7`，随后取得
`ACCEPTED_VPKB_001_TRANSACTION_INSPECT_STAGING_IMPLEMENTATION_AT_EXACT_HEAD`。
三份 post-CI 记录由下一架构交付原字节携带。

第四个有界子版本为 `staged-pdf-capture-inspect-v1`，baseline 为 `fb2cbcb`。
Architect 已冻结 canonical prepared request、完整 parsed desensitized
approval-ref、一次 retained prepare/inspect batch lineage、完整 Vault sibling
snapshot、create/reuse closed authority 以及三处共用的 compact bundle encoder。
Builder 与 Repo Steward 已分别对 contract SHA-256
`8f9624c98ebbc9ae7eba51e61645291f11bc482f2fde1353e2ec4187f6c9d21f`
和工作包 SHA-256
`298ae880c5013c79a3db94dbc05c0d6d1c77eb0af3e507a55d5a2a2752c02421`
返回 GO。Python 3.12/3.13 已各通过 1901 项全量，checkout 外 wheel 已验证 26 个
schema 与新增资源精确字节。当前只允许完成精确交付、fresh CI 与单独 exact-head
验收；通过前不授权 Builder 写主实现。此阶段仍不执行
upstream apply/recover/admin，不处理 staged code、operation result、ledger/integrity、
vendor/dependency/workflow 或真实 Vault。

`base-catalog-v1` generation revision 1 继续保持不变，因为两个 adapter 子版本都不生成
catalog rows。第一个实际消费 authority 的 mapper/compiler 必须另升 generation profile
revision 并绑定 adapter、schema/profile 和 authority digest。VPKB-001 仍按
`adapter-contract` → `integrity-runtime` 顺序完成；首个子版本通过不代表整个 slice 或
VPKB-001 完成。

保持同一 PR 中的单写者：架构阶段由 Architect 写冻结文件，实施阶段再显式把生产/测试
路径交给 Builder；Steward 始终只独立核验并串行处理 Git/CI。每次审查以
`packet_base_sha..candidate_head_sha` 为本包增量，
同时检查跨模块不变量；PR94 的全部历史 diff 不是本包新增代码。当前 workflow 只自动
覆盖以 `integration`/`main` 为 base 的 PR，不改变 base 或另开不能触发现有矩阵的层叠 PR。

## 工具与持续运行的实际边界

本会话使用现有子agent能力即可，不需要另造一个多agent服务或改全局Codex设置。
角色与上下文保存在仓库文件，后续会话读这些文件恢复；文件本身不会启动后台agent、定时任务或无限开发循环。
在2026-09-01的本次协作配置阶段，未调用Grok，也未创建新的侧栏任务、worktree、Issue、PR或合并操作。

官方能力说明：[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)、
[Git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)、
[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。
[GPT-5.6模型标识](https://developers.openai.com/api/docs/guides/latest-model)。
这里的三角色职责、单写者与验收记录是本项目工作约定。
