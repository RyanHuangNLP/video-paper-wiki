# Agent 4：接续尚未完成的集成与验收候选

继续当前 Cursor Grok 4.6 会话及 `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-4/source`。先读同目录 review.md，再读原 COMMON、CONTRACT、TERMINAL-4、freeze 和 cursor-r1/OVERRIDE。本指令保持原六个自有路径范围及原输入复制权限；不改其他 lane 的生产代码。

当前 progress 明确为等待状态：99 passed / 4 skipped 使用旧 T1/T2，尚无 T3 workflow 模块，不是完整候选。现有 Agent 2 r2 被拒；Agent 3 也有本轮复现缺口。不要只补一个 T3 文件便报告全部完成。

1. 在等待依赖时继续自有 CLI/docs/tests，补充真实后端回归以检出 Agent 2/3 审查中的拒绝及旧文件保存行为。接口 stub 测试标为协议测试，不能算作真实集成通过。
2. 接收 Agent 1/2/3 最新已停止写入的 final。逐个检查正式 ready/handoff 存在、字节相同、完整文件集合、baseline/contract/freeze/dispatch/input SHA。只从 handoffs/<revision>/files 精确复制到自己的 source；记录已替换旧 r2 输入。任何缺项或新失败回到原作者，不静默修入自己的副本。
3. 实际集成通过后冻结全部源码，完成原 TERMINAL-4 剩余事项：真实 workflow CLI（无依赖缺失 skip）、一次锁定 Python 3.13 全量、一次离线新 wheel 的 source 外模块/SHA/两个入口验证、指定现有真实 PDF 的当前 Cursor 会话 QA 和短 draft、带空格/括号的外部输出、全部 href/page/slice/hash 联合核验、实际 Bash/zsh 文档命令。保留失败和修复前结果，源码变化后只重跑受影响验证并在最终快照上完成验收；不得给新字节贴旧日志。
4. 新建最终 handoff，六个自有 files、全部 imported_files 和完整 integrated_files 分列。包含真实测试/模型试用、wheel SHA、输入交接 SHA、未跑项目和本地 PR 草案。证据根必须是 `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-4/handoffs/`；ready/handoff 字节相同。返回两个实际存在的绝对路径并停止写入。

依赖等待前完成独立工作；确实只剩等待时按原包上限保存 needs_input checkpoint，不空转也不标完成。不触发 Git/PR/CI/merge，不使用旧 wheel 冒充新实现，不改真实 Vault、依赖或模型运行设置。候选交 Architect 后才考虑 Steward 串行交付。

## 现有 installed test 在实际运行前需要修正

`test_light_workflow_installed.py` 仍硬编码当前用户的 Python/cache，并在找不到该 Python 时 skip。这不能验证其他机器上的安装。采用实际锁定运行时和明确可配置的本地离线缓存；本地环境选择属于运行参数，不应硬编码进通用测试或以缺少某个用户目录为由跳过必要验证。

当前代码先 `pip --prefix` 安装，然后以原 Python 的 `-I` 加 `PYTHONPATH=prefix-site` 导入。`-I` 会忽略 PYTHONPATH，因此这段代码没有把导入定位到新 prefix，可能仍导入旧环境包/可编辑源码。应从确实能隔离并加载新 wheel 的安装环境运行，记录并断言实际 `__file__`/所有新模块 SHA、schema 字节和完整入口行为。必须真实验证 module 与 console 两个入口，不能在 console 缺失时放行 module 作为替代。此处是源码审查发现的验证方法问题，Architect 本次未构建或运行该新 wheel。
