# R08 小范围修复：四终端共同约定

用户要求将 R08 的三项收尾问题交给四个手动 Grok 终端。此包取代上一轮 release 任务的活动写入范围；既有 R05–R08 证据、上一轮 release 目录和已取消的八小时调度均不再写入。沿用用户指定的 Grok 4.6 / xhigh；不自动调用其他会话或代理。

先读取主仓库 `/Users/huangzhanpeng/python_code/video-paper-wiki` 的 AGENTS.md、docs/ai/task-index.yaml、docs/ai/codex-team.md、本 COMMON、自己的 TERMINAL-N.md，以及 `artifacts/verification/manual-pdf-v1/architect/r08/review.md`。本包只关闭 R08-1（混合坏引用漏检）、R08-2（Bash/zsh 文档命令）、R08-3（过期交接），保持 R07 产品功能和测试冻结。

## 目录与所有权

共享源码根：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`。它是真实 linked worktree，目录名不是远程 integration 分支证明。新证据根为主仓库的 `artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1/`；以下称 NEW。旧 release 证据根为同级 `lightweight-release-parallel-v1/`；以下称 OLD。所有路径按绝对主仓库根展开。

NEW/baseline.json 已锁定当前 858 个来源文件、完整 70 路径候选、R08 18 文件快照 `b8b644b0fed9fd0d116a8a427625d468558e3c949fd73258a01d3783a3843569`、188 个保护历史文件、旧 ready、wheel、PDF 和本轮目录。开始/交接时核对这些输入；遇到未说明的新改动，保留证据并暂停受影响操作，不覆盖它。

| 终端 | 独占输出 | 允许修改 |
|---|---|---|
| 1 | NEW/terminal-1/；主仓库 `.work/parallel/lightweight-r08-fix-parallel-v1/terminal-1/` | 本轮 verify_links.py、实现侧测试与 USAGE.md |
| 2 | NEW/terminal-2/；对应 terminal-2 工作目录 | 独立参数化回归及其证据 |
| 3 | NEW/terminal-3/；对应 terminal-3 工作目录 | draft/docs/lightweight-pdf-quickstart.md 与命令验证脚本/证据 |
| 4 | NEW/terminal-4/；对应 terminal-4 工作目录 | 接收后仅 integration/docs/lightweight-pdf-quickstart.md，以及本终端集成证据 |

四个工作目录已经准备好。T1 的新脚本、15 项测试、用法及小样本已从旧版本复制；其初始 verify_links SHA 为 `51d67390e22dc3c21f2f4f85b12a9ab78d8c583eb3242f4c8e7c81248661f743`。T3 从已有修稿 `82d44948d71f821317047b91fc17e9c3c74281acd695d97697ec541661ca1b74` 开始，位于本轮 terminal-3/draft/。该修稿仍须解决 zsh 标量拆词错误，不能原样交付。

integration 当前 quickstart 为 `6c02145f0627020cf717048162f363a470d64d62fc41f2f71f0ce4b8d8569178`。README 固定为 `f8395276775c930cf87d0e5a427663083e7a25ae55b1eb577b6383091da6458b`，本轮不改。所有产品 src、仓库 tests、依赖/锁文件、CI workflow、旧目录/ready 和其他文档只读。

## 环境和验证范围

共享 Python 只读使用 `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`；设置 PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、UV_OFFLINE=1、UV_PYTHON_DOWNLOADS=never。已有缓存为主仓库 `.work/cache/uv-tests`。定向测试使用各自 `/private/tmp` 短目录和独立 pytest cache。

实际产品入口是 `python -m video_paper_wiki_research`，不是 `-m video_paper_wiki_research.cli`。源码运行须明确 PYTHONPATH 指向共享 integration/src，先记录实际模块 `__file__` 与 SHA。安装验证复用 baseline.json 的 wheel_python（上轮 terminal-4/wheel/venv/bin/python），清空 PYTHONPATH，源码外运行 `-I -B`；不重装旧环境或共享 `.venv`。

只跑新验证器/独立回归、文档真实 shell 命令及必要的集成核验。不重复四论文内容试用、38/2246 项产品测试，不为缺失 Python 3.12 安装环境。3.12 和远程四矩阵保持待交付验证。旧 wheel SHA `9e1861d92a3b5fc63159a0d0e6e1aca63eb50e283fb6e008f579ef70fce13b21` 不含 README/quickstart；本轮产品和包资源不变，复用并校验该 wheel，不为文档修正重建它。

只写本轮生成工作区和报告，不复制 PDF/图片/模型。baseline.pdf_input 是主仓库 inbox/arxiv-2204.03458.pdf，可供文档命令测试直接读取；不改原件。67 条目录、真实 Vault、vpwiki-admin、人工门均不在本轮动作中。

## 冻结交接

四个终端可以立即开始独立工作。T1 不等 T2；T2 先跑旧版本红例，再等 T1 冻结版本；T3 独立改文档；T4 先准备完整候选/CI 输入核对，最后接收三个交接。

各终端在 NEW/terminal-N/ 原子写 handoff.json；成功另写相同内容的 ready.json。至少包含 status、stopped_writing=true、source_root、本轮 baseline_sha256、packet_sha256、files、artifacts（绝对 path + SHA）、commands（cwd/exit/result）、known_gaps、blocking_findings。T1/T2 的 files=[]；T3 files 只能列 quickstart，并注明 draft_root；T2 另记 tested_verifier_sha256 和冻结回归脚本 SHA。T4 记录最终文件清单及所有接收摘要。

**写出交接后该版本不再修改**，包括 ready、报告和脚本。需要第二次修订时放新 revision 子目录，并重新交接；不能原地更新已经被另一个终端接收的 ready。当前 OLD 的 T3/T4 不一致保留为历史失败输入，不补写旧记录。

失败/缺输入时写 status=needs_fix/needs_input/blocked 的冻结 handoff，说明最小复现或具体缺项。其他终端可以接收失败材料并完成未受影响任务；不能用缺失输入虚构成功。等交接约每 60 秒检查一次，最多 30 分钟；到时保存缺项后结束，不无限等待或把超时标成 ready。

T4 接收全部 stopped_writing 产物后独占最终集成。若仅剩同一 R08 范围的脚本/文档小修，可在 T4 自己的新副本修复并记录来源/差异，用 T2 未被削弱的冻结回归及两种 shell 重新验证；不改 T1/T2/T3 的冻结文件，不扩展到产品源码。

本轮不执行 Git 写操作、fetch/push、PR 修改、远程 CI 或 merge。T4 只读 Git 使用 GIT_OPTIONAL_LOCKS=0。材料交 Architect 后，由 Repo Steward 在明确指令下串行交付 draft PR → integration 和远程四矩阵。所有 ready 都不是 Architect 验收、CI 成功或发布证明。
