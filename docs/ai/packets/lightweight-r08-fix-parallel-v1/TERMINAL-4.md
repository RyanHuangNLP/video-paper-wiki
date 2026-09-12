# 终端 4：接收新冻结版本并完成 R08 集成交付材料

先读同目录 COMMON.md 和 TERMINAL-1..3.md。本轮独占 NEW/terminal-4/ 和自己的工作目录。integration 中唯一可写文件是 docs/lightweight-pdf-quickstart.md，且必须先满足交接和旧摘要保护；README、产品源码和仓库 tests 不改。

## 立即开展

核对 baseline 的 858 文件与当前 70 路径候选。以 GIT_OPTIONAL_LOCKS=0 只读复核 worktree、HEAD、branch、index、tracked/untracked 路径。旧 delivery-inventory 的 69 路径是复制文档前观察，保持原字节；旧 R07 17/413/857 映射也保持历史标签。

在本轮目录准备新的完整 delivery-manifest、CI 输入和 PR 草稿模板。最终清单必须来自当时完整 `HEAD..working-tree` 加 untracked 集合，不只列 quickstart 或旧 17 路径。逐文件列来源绝对路径、拟提交相对路径、SHA、HEAD 状态、来源归属；保留未说明主仓库差异、inbox/tools/既有计划/旧证据的排除项。历史 PR base 未联网确认，current head/base/CI run/merge-preview 留 pending，不能伪造新观察。

校验 baseline.wheel 的现有字节与安装位置。它不包含 README/quickstart，这轮不重建、不改装、不复制虚拟环境。3.12 未跑与远程四矩阵保持待验证；不为此重复产品全量。

## 交接后集成

接收 T1/T2/T3 **本轮** handoff/ready，核对每个实际文件、所有列出的 artifact SHA 和 stopped_writing。T2 tested_verifier_sha256 必须等于将使用的 T1 脚本 SHA。不能再引用 OLD 的 ready，不能只比较报告文字。交接文件自身 SHA 保存到本轮 receipt；结束前再核对一次未变。

先复跑 T2 的冻结回归，确认当前 verifier 上三个坏例全部拒绝且正常例通过。再运行 T1 实现侧测试；同一失败需保留日志，不能削弱独立断言或改 T2 文件。可重新使用 OLD/T2、OLD/T3 的已验收输出做链接校验，但标为已有输出的检查，不冒充新的内容试用。

复制 T3 quickstart 前确认 integration 仍是 baseline 的 `6c02145f…`，README 仍为 `f8395276…`，T3 draft SHA 与其最新冻结交接完全相同。只复制这一个文件，不覆盖整目录。复制后记录新 doc SHA、前后差异以及接收的 ready SHA；确认没有新的 src/tests/依赖改变。

对**最终集成文档**复跑 T3 保存的 Bash/zsh shell 片段，确认脚本对应该文档的最终字节，不用 Python argv 列表代替 shell。参数必须指向 T4 自己的工作区/输出，不能写 T3 的冻结目录；复用现有安装，用同一份 PDF 做文档流程即可，无需重新生成四论文内容。用最终 verifier 核对本轮 T3 outputs、T4 文档输出和旧 T2/T3 来源目标，保存实际命令/报告。

若仍有同一 R08 范围的小修，在 T4 自己的新副本改验证器或文档，保留原始来源摘要、差异及失败证据。修改后的 verifier 必须通过同一 T2 冻结测试，文档必须重跑两种 shell。不要改其他终端冻结目录，不扩展产品代码范围。按 COMMON 接收失败 handoff；等待上限到了就保存未完成交接，不伪造 ready。

## 最终材料与完成标准

在 NEW/terminal-4/ 生成 final-inputs.json、delivery-manifest.json、integration-review.md、pr-description.md、ci-plan.md 和 handoff/ready：

- 三项 R08 问题的具体关闭证据；独立回归/文档命令/链接检查与最终脚本和文档 SHA 一致。
- 完整当前候选清单和准确数量；70 是起点，实际增减需解释。当前映射按文档集成后的字节重新计算，新文件计入；不要把旧 R07 映射标为当前 match。
- 真实接收的 T1/T2/T3 ready SHA，与现存文件再次核对一致。历史 ready/报告不改标签、不覆盖；未完成项明确列出。
- wheel 作为复用且已校验的程序包单列；文档按独立 SHA 验收，不声称文档在 wheel 中。
- `git_mutations_executed=false`、`remote_ci_executed=false`、`architect_accepted=false`、`stopped_writing=true`。已知 Python 3.12/远程 CI 缺项如实保留。

最后检查 baseline.protected_history 188 个旧文件和原 PDF 未变。停止全部写入，交 Architect review。Review 通过后，Repo Steward 再按明确指令串行提交 draft PR → integration 并核验远程四矩阵；本终端到材料就绪为止。
