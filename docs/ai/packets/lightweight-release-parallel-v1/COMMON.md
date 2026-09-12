# 轻量第一版收尾：四终端共同约定

用户在 R07 本地验收之后要求四个终端并发。此包是新的手动 Grok `/goal` 分工；此前 R05/R06 修复包和已取消的八小时自动调度不再是活动任务。四个会话沿用用户指定的 Grok 4.6 / xhigh，不自动调用其他 Grok、不启动其他代理、不改模型设置。

先读主仓库 `/Users/huangzhanpeng/python_code/video-paper-wiki` 的 AGENTS.md、docs/ai/task-index.yaml、docs/ai/codex-team.md、本 COMMON、自己的 TERMINAL-N.md，以及 `artifacts/verification/manual-pdf-v1/architect/r07/review.md`。任务索引中的旧交付记录不是本候选的新 CI。

## 本轮结果与范围

完成可重用的引用检查器、真实多论文试用、可照做的使用说明，以及供 Architect / Repo Steward 使用的精确交付材料。核心产品源码和仓库测试冻结；不新增检索、解析或模型服务功能。发现产品问题时保留最小复现并报告，不能在未经划定的新范围里抢修。

已验收源码根为 `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`。R07 的 17 文件快照是 `ea67d3b857a23ff721f5a53c8b730c78662e014a8dcac9e78816eda1efaab0dd`，light_index.py 为 `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8`。这 17 个文件不是相对真实仓库 HEAD 的全部待提交变更，也不代表远程分支。

主仓库下本轮证据根：`artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/`。其中 baseline.json 已记录 857 个来源文件、413 个产品/测试/构建输入的当前摘要、四份 PDF、旧证据和工作目录。开始与结束都核对负责的输入；若产品摘要变化，停止依赖该输入的验证并报告，不能继续沿用 R07 验收。

| 终端 | 可写范围 | 共享源码权限 |
|---|---|---|
| 1 | 本轮证据根 terminal-1/；主仓库 `.work/parallel/lightweight-release-parallel-v1/terminal-1/` | 只读 |
| 2 | 本轮证据根 terminal-2/；对应 terminal-2 工作目录 | 只读 |
| 3 | 本轮证据根 terminal-3/；对应 terminal-3 工作目录及其中 draft/README.md、draft/docs/lightweight-pdf-quickstart.md | 只读；不直接改 integration 文档 |
| 4 | 本轮证据根 terminal-4/；对应 terminal-4 工作目录；接收终端 3 冻结交接后才能写 integration 的 README.md 和 docs/lightweight-pdf-quickstart.md | 其余只读 |

四个工作目录均位于主仓库 `.work/parallel/lightweight-release-parallel-v1/`，已准备。它们是输出工作目录，不是假 Git worktree，也不是源码副本。终端 3 只复制了约 12 KB 的 README 作为草稿。运行共享源码时必须明确 PYTHONPATH；不能从主仓库旧 src 误导入。

## 运行与空间

共享解释器只读使用 `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`。源码运行设置：

```sh
export PYTHONPATH=/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src
export PYTHONDONTWRITEBYTECODE=1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export UV_OFFLINE=1
export UV_PYTHON_DOWNLOADS=never
export UV_CACHE_DIR=/Users/huangzhanpeng/python_code/video-paper-wiki/.work/cache/uv-tests
```

通过 `python -m video_paper_wiki_research` 执行源码入口；先记录模块 `__file__` 和摘要。不要使用 `-m video_paper_wiki_research.cli`，该模块仅定义 main 而不直接运行它，可能空输出却返回 0。各自的 `.work/.../terminal-N/workspace` 为新知识工作区，输出可放该工作区之外的本终端目录。不要让任何终端写另一个终端的 workspace。测试临时目录使用 `/private/tmp` 下的短路径并指定独立 pytest cache。

现有已验证安装位于 integration 的 `.work/r06-wheel-prefix/venv/`，只读使用。安装验证必须清除 PYTHONPATH，使用该解释器的 `-I -B`，cwd 在源码之外，记录实际安装模块及 SHA。新 wheel/隔离安装仅由终端 4 在本轮独占目录创建一次；不要重装共享 `.venv` 或旧 wheel 环境。只可复用已有离线依赖/构建缓存，缺环境时交付具体缺项，禁止下载模型或为补检查安装重依赖。

不要重复运行已经通过的 38 项/2246 项 Python 3.13 检查。T1 运行新验证器的独立测试；T2 运行新多论文案例；T3 验证文档命令；T4 运行合并后的必要 smoke 和尚缺的 Python 3.12 轻量检查（仅已有环境可用时）。发现新故障时可以重跑受影响项，保留失败日志和修复原因。

只保存文本、必要的小型 JSON、索引和报告；不复制原 PDF、图片或模型。不要整目录复制 `.work`、虚拟环境或历史证据。原 PDF 与 inbox、tools、既有计划、67 条目录、真实 Vault、旧 R05/R06/R07 证据保持原字节。旧验证器有已知误判，只供参考，不能就地修正。

## 交接与完成条件

四个终端立即开展独立任务，无需等其他会话启动。各自在本轮证据根 terminal-N/ 原子写 `handoff.json`，成功时另写 `ready.json`。共同字段：

```json
{
  "status": "ready",
  "stopped_writing": true,
  "source_root": "/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration",
  "baseline_sha256": "本轮 baseline.json 的摘要",
  "packet_sha256": "自己的 TERMINAL-N.md 摘要",
  "verified_source_files": {"相对产品路径": "实际 SHA-256"},
  "files": [],
  "artifacts": [{"path": "/绝对/证据文件", "sha256": "..."}],
  "commands": [],
  "known_gaps": [],
  "blocking_findings": []
}
```

`files` 仅为待集成的产品/文档文件：终端 1/2 为空，终端 3 只能有上述两份文档且记录 draft_root 与相对 path，终端 4 记录最终文档和完整交付清单的引用。报告至少包含实际命令/cwd/exit_code、关键输入输出摘要、结论及未跑项；不能把方案标成已执行。

失败或缺输入时仍冻结已有产物并写 handoff.json：status=`needs_fix`、`needs_input` 或 `blocked`，附最小复现/具体缺项及 stopped_writing=true。这样终端 4 能汇总未完成项，不会等待永远不会出现的 ready。终端 4 等待其他交接时约 60 秒检查一次，最多等待 30 分钟；到时保存缺项交接并结束，后续可由用户再次启动。不得把超时当成功。

这里的 ready 只表示任务材料就绪，不是 Architect 验收或发布批准。Grok 不执行 Git 写操作、fetch、push、创建/修改 PR、触发远程 CI 或 merge；也不触碰真实 Vault 或运行 vpwiki-admin。终端 4 完成可审查的清单与 PR 草稿后交 Architect，由 Repo Steward 在后续明确指令下串行执行 Git/CI。Git/远程 CI 的未执行状态应清楚留在交付记录中。
