# 终端 4：串行集成、缺失验证与精确交付准备

先读同目录 COMMON.md 和 TERMINAL-1..3.md。主工作目录为 `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`；自己的临时输出与证据使用 COMMON 指定目录。产品源码、仓库测试、依赖和 CI workflow 冻结。本轮只有 README.md 与 docs/lightweight-pdf-quickstart.md 在收到 T3 冻结交接后允许改变。

## 现在即可开展

1. 核对 baseline.json 的产品/测试/构建摘要及 R07 验收、R06 2246 项日志的输入。保留其历史测试归属，不能改标签当作本轮重跑。
2. 只读复核本 integration 目录与主仓库的来源关系；可读取 `.git` 以及 `git status/diff/ls-files/rev-parse`，设置 GIT_OPTIONAL_LOCKS=0，但不创建/修改 Git index、commit、branch 或 remote，不 fetch。准备时 Repo Steward 已确认它是真实 linked worktree，分支 `integrate/manual-pdf-pipeline`，与主仓库同 HEAD `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`，两个 index 为空；当时 integration 有 10 个 tracked 修改和 59 个 untracked 候选路径。该观察只供起点，需防后续变化；`integration` 目录名不代表远程 integration 分支。历史 PR base `08709894adfb20ec07e976783f0ba436d975b74f` 本轮未联网验证，不能称当前远程 base。
3. 准备完整候选交付的对照清单：区分主仓库已跟踪文件、主仓库既有未提交修改、integration 中新增/修改文件、受保护输入/证据。对候选源文件记录绝对源路径、拟提交相对路径、SHA、在真实 HEAD 的状态和来源。不要将 R07 17 路径当成所有未交付工作；不执行 blanket add/copy/reset/clean。不要把主仓库中未说明归属的差异自动归入本任务。
4. 读取 `.github/workflows/tests.yml`，形成 `ci-plan.md`：后续真实提交和 draft PR → integration 的四项 Linux/macOS × Python 3.12/3.13 检查、当前源码/依赖摘要、待确认 head/base/merge-preview/run/attempt/jobs 字段。尚未查询或未执行的值保持 null/pending。可写本地 `pr-description.md` 草稿；不创建/更新远程 PR，不触发 CI。
5. 本候选缺少的 Python 3.12 检查只使用已经存在的可用环境；记录版本与依赖输入，并对当前源码运行六个轻量测试及必要入口检查一次。环境缺失则写明确未跑项，由后续远程矩阵补齐，不重复 Python 3.13 全量，不联网准备新环境。

## 接收后执行

按 COMMON 接收 T1/T2/T3 的 ready 或失败 handoff，核对全部摘要与 stopped_writing。T1/T2 产物留在其本轮证据/工作目录，不搬运整树。T3 只按 files 白名单将 README.md 和新 quickstart 复制到 integration，前提是 README 原摘要仍与 baseline 相同且新路径不存在；未知后续编辑不得覆盖。

T1 验证器的正确性不能只靠 self-report：复跑其负例，另建一个错误相对层级但 workspace 正确文件存在的例子，确认非零退出；检查正例真实解析位置。随后按 T2/T3 outputs.json 对全部最终 Markdown 运行冻结的 T1 工具，保存准确命令/exit_code/链接数量/报告。不修改 T1 的冻结脚本；必要的验证器或文档小修只在自己的证据副本中进行，保留差异、旧失败与新增回归，再交 Architect 复核。产品源码问题不在本包内抢修。

最终文档稳定后，用现有离线构建缓存在本轮独占目录生成一次新 wheel；隔离安装到自己的新前缀，不能覆盖旧 R06 环境。源码外、无 PYTHONPATH、`-I -B` 检查实际安装模块 SHA 与冻结产品相同，并按文档跑最小 pdf add → index → QA/writing export/import。可使用本轮已有精确匹配 evidence 的模型 JSON重放；不匹配时使用当前会话新输出，不能手改 chunk 身份迁就旧结果。安装包/协议 smoke 不算新的模型质量试用。不要重复提取四篇到多个长期工作区。

新增材料若只有验证工具和文档，不再跑 2246 项全量；运行相关工具测试、文档命令、隔离安装检查即够。新 wheel 带的 README/包元数据可能变化，应记录 wheel 新 SHA；不能把新的文档快照直接标成已有的 R07 17 文件验收。

## 最终交付

生成：

- `integration-review.md`：各终端结果、实际试用结论、修正与未完成项。
- `delivery-manifest.json`：完整待交付候选的逐文件来源/目标/SHA；不确定或受保护路径单列 excluded/unresolved，不默认纳入。原始 PDF、临时 `.work`、模型、虚拟环境、个人绝对路径或全文试用原件不得混入待上传内容；本地证据和可提交摘要分开列明。
- `pr-description.md`、`ci-plan.md`：可审查草稿及准确未执行状态。
- `ready.json` 或失败 handoff：最终源文件、两份文档、轮次交接与证据摘要；明确 `git_mutations_executed=false`（只读观察另记）、`remote_ci_executed=false`、`architect_accepted=false`、`stopped_writing=true`。

由 Architect review 后，Repo Steward 才接收真实 Git/PR/CI 操作。不得为等该步骤常驻轮询，也不得把本轮终端材料就绪说成项目已发布。其他终端缺交接时按 COMMON 的 30 分钟上限保留已完成项并写未完成 handoff。
