# 完整本地项目档案与云端交接

日期：2026-09-13。用户已明确授权把目录中的项目文件 commit 并 push。

本分支 `repair/vpkb000-plan-approval-prepare-follow2` 保存原工作区的完整 Git 档案，
包括 `b86bb0250df340e6ae0f01dada1252afdfc2907c` 中的源码、工具、合同、设计和原始验证记录。
这些记录保留当时的状态和哈希，不能视为当前代码全部通过或重新运行旧任务的授权。

当前开发分支是 `codex/code-proof-v1`，C1 缺件补交提交为
`21eddfcec6d479948709b81419b92738ec6004af`，产品基线为 `d440c7a`。
开发分支已携带 C1 的 retained-I/O 合同、R13–R18、生产冻结文件、生产任务书、实施顺序
及两份独立返回产物复核。使用以下入口：

- [开发分支交接说明](https://github.com/RyanHuangNLP/video-paper-wiki/blob/21eddfcec6d479948709b81419b92738ec6004af/docs/ai/CLOUD-BOOT-01-HANDOFF.md)
- [开发分支材料哈希清单](https://github.com/RyanHuangNLP/video-paper-wiki/blob/21eddfcec6d479948709b81419b92738ec6004af/docs/ai/CLOUD-BOOT-01-MANIFEST.json)

从本档案读取旧材料可用 `git show origin/repair/vpkb000-plan-approval-prepare-follow2:相对路径`。
新开发从 `origin/codex/code-proof-v1` 创建任务分支，不用旧产品文件覆盖新实现。

在开发分支初始化上游须显式执行：

```bash
git submodule update --init --checkout vendor/claude-obsidian
git -C vendor/claude-obsidian rev-parse HEAD
```

固定上游应为 `9f8c1199047eac2c3828496279fbb7ba9540b90b`。

按仓库现有规则，虚拟环境、缓存、临时工作区、嵌套验证 checkout、Python 字节码和 PDF
原件不强制加入 Git；它们不是本次报告的 C1 合同缺件。未执行主分支合并或真实 Vault 操作。
