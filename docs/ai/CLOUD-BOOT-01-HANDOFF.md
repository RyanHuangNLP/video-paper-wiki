# 云端 BOOT-01 交接说明

日期：2026-09-13。交付分支：`codex/code-proof-v1`。

本次在产品提交 `d440c7aaebb4dcc2c52cab719b0d73347a41493f` 上补充开发文档和
首包历史证据。产品源码、测试、schema、资源、依赖和固定子模块均保持该提交的内容。
`b86bb0250df340e6ae0f01dada1252afdfc2907c` 仅作为选定历史材料的来源，未合并其旧产品树。

## 入口与分工

- [群开发任务书](GROK-BOT-GROUP-DEVELOPMENT-BRIEF.md)：角色、流程、克隆命令和首包 C1。
- [剩余开发计划](remaining-development-plan-2026-09-13.md)：12 个工作包及最终集成验收。
- [材料清单](CLOUD-BOOT-01-MANIFEST.json)：文件大小、SHA-256 和交接前核对的冻结输入。

ChatGPT/Codex 设计、分发和验收；Grok 负责产品代码和测试；agy 负责 Git、PR 和 CI
交付操作；Grok Bot 只转交和交回。实际执行采用用户指定的 Herdr 中已有 Agent。
本次用户直接要求本地持有提交的环境执行 push，以解除云端拿不到基线的阻塞。
用户随后明确要求目录中的项目文件全部 commit 并 push，授权补交历史合同和审查材料。
先前仅发布两份文档的范围限制已被本次指令更新。

完整本地项目档案另发布在 `repair/vpkb000-plan-approval-prepare-follow2` 分支，包含
`b86bb0250df340e6ae0f01dada1252afdfc2907c` 及其后续交接文档。需查找未进入开发分支的
旧证据时，先 `git fetch origin`，再用 `git show origin/repair/vpkb000-plan-approval-prepare-follow2:相对路径`
读取。该分支保存当时的代码和工具；新开发继续从 `codex/code-proof-v1` 开始。

## 历史材料的使用方式

`docs/ai/packets/full-todo-v1/` 按本地保存的版本迁移，包含历史阶段合同、修订、
拒绝和状态；它们用于需求追溯。`running`、旧负责人、旧 CLI 调用形式及时间记录
不证明当前有进程在运行，也不要求重新启动已完成的工作。旧 PR 编号不作为新任务的目标。

C1 的生产冻结文件所直接列出的 24 份合同、审查、诊断工具和环境记录已按原哈希核对并携带，
另带剩余计划所引用的两份独立失败复核及相关诊断输入。更早历史记录引用的仓库档案
可从上述完整档案分支查找；临时目录和被忽略的环境缓存不属于 Git 档案，也不能视为已通过的实现。
需要对旧候选重新做诊断时，先单独补齐候选与适用的运行条件，不能直接安装被拒绝的代码。

迁移检查在四份旧 DISCOVERY 文档中发现末尾空行：`DISCOVERY-EXPANSION-BOUNDS-R4.md`、
`DISCOVERY-EXPANSION-DESIGN-R2.md`、`DISCOVERY-EXPANSION-RECOVERY-R3.md` 和
`DISCOVERY-PROVIDER-TARGET-NOTES-R1.md`。这些历史文件按原字节和哈希保留；本次新写文档
单独通过空白检查。该记录不将历史空白告警描述为整个迁移 diff 检查通过。

历史冻结文件为保持证据完整而不改写。其中：

- `/Users/huangzhanpeng/python_code/video-paper-wiki/docs/...` 和 `artifacts/...`
  映射到当前 clone 根目录下的同名相对路径；文件哈希保持原值。
- 旧 `source_root` 和 `baseline_tracked_files` 指向本机旧工作区，产品内容以 Git 提交
  `d440c7a` 为准。文档交接提交改变整个 Git tree，不应冒用旧 tree 的验收记录。
- `/private/tmp/...` 只标识当时的临时诊断位置，不是云端应创建或读取的必备路径。
- 旧冻结文件中的 `push_authorized: false` 记录当时授权。本次用户已明确授权发布
  开发基线和启动材料；该授权不包含合并、真实 Vault 操作或关闭人工验收项。

ChatGPT 在 Grok 开始 C1 前，按当前完整 HEAD、云端实际路径和新分工准备本次任务交接，
保留 R6/R8/R9 和 R13–R18 的技术约束及失败回归要求；不直接重放历史模型调用指令。

## 云端核对

已有 clone 由 agy 先核对工作区状态，再 fetch；新环境按任务书 clone 指定分支。

```bash
git fetch origin
git rev-parse origin/codex/code-proof-v1
git merge-base --is-ancestor d440c7aaebb4dcc2c52cab719b0d73347a41493f origin/codex/code-proof-v1
git show origin/codex/code-proof-v1:docs/ai/GROK-BOT-GROUP-DEVELOPMENT-BRIEF.md
git show origin/codex/code-proof-v1:docs/ai/remaining-development-plan-2026-09-13.md
```

在该开发分支的干净工作区内初始化固定上游：

```bash
git submodule update --init --checkout vendor/claude-obsidian
git -C vendor/claude-obsidian rev-parse HEAD
```

应输出 `9f8c1199047eac2c3828496279fbb7ba9540b90b`。`.gitmodules` 设置了
`update = none`，因此这里必须显式传入 `--checkout`，不能只运行默认 submodule update。

记录实际远程 HEAD，并在该版本核对清单里的全部文件。完成后由云端 agy 更新其现有
`BOOT-01.md`，交 ChatGPT 审核 C1 开工条件。本次仅补齐远程输入，不冒充云端重跑结果、
新产品测试结果或远程 CI 通过；`integration` 的旧 HEAD 不作为新的开发起点。
