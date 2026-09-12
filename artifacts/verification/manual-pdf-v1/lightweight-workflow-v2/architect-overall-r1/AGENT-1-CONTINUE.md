# Agent 1：R2 候选的原合同 A 返修

Architect 决定 `CHANGES_REQUIRED_AGENT_1_R2`。继续当前 Cursor Grok 4.6 会话及 `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-1/source`，保持原 COMMON、CONTRACT、TERMINAL-1、freeze 和 cursor-r1/OVERRIDE。只恢复原五个自有路径和自己的新证据写权；不改 T2 私有 helper、其他工作区、Git、依赖或原合同。

当前冻结 light_pdf.py SHA 为 `d51551b81939039114ebb208eb94db5ae48dc84f42b785ed9597542674e96770`，light_workspace.py 为 `a166be3a82d2bd62223fbf1196bef7540514f816552e36487eb15f336f8929f2`。独立审查的三文件 29 项、含相关兼容的六文件 48 项均通过，但独立探针和 Architect 复放确认以下缺口。读取同目录 terminal-1-review-r1.md、probe_pdf.py、probe-pdf-results.json。探针写相邻结果文件，只能复制到自己的 scratch 后运行，保留全部旧结果。

1. **畸形 UTF-8 必须正常拒绝/诊断。** 有效 paper 的 source.md 变成非法 UTF-8 后，extract_pdf 和 inspect_workspace 均抛 UnicodeDecodeError。复用/恢复路径应拒绝为 SOURCE_INVALID 且保留原文件；inspect 应完成只读检查，将该 paper 写入诊断、state=needs_attention，不中断整个检查。不通过自动重提取覆盖来掩盖损坏。
2. **恢复完整 staging 必须先验证内容再发布。** 原 `_recover_owned` 根据两文件名称及 marker 就 rename 到 papers，之后才发现 JSON schema 错误。Architect 通过公开 extract_pdf 复现 SOURCE_INVALID 返回但坏 final pair 已存在。对经确认归属的 staged pair，发布前验证身份、JSON/UTF-8/anchors/完整集合；异常不发布新 final、不损坏旧 paper，只按原合同处理确定归属的 staging。增加坏 metadata、坏 Markdown/anchors、身份不匹配的前置拒绝测试，保留普通进程中断后的成功恢复。
3. **拒绝事务路径 symlink。** `.light-transactions` 指向外部测试目录时，当前 extract 成功并在外部建立锁。对 transaction/staging/lock 的既有路径逐级验证，不跟随 symlink、非普通 lock 或未知项执行写入；拒绝时外部目录和现有文件保持原字节。inspect 同样只读报告异常。按原合同保持 macOS/Linux advisory lock 与有界 busy 行为，无需额外安全产品范围。
4. **空 workspace 与 index 状态分别判断。** 合法零论文 index 应为 index_state=current，同时 workspace state=empty。移除依赖 valid_papers 非空才可能 current 的错误条件，不让缺失/损坏 index 被误标 current。
5. **新恢复测试必须使用本次测试运行时。** `tests/research/test_light_pdf_recovery.py:24` 把子进程 Python 固定成当前用户机器的 `/Users/huangzhanpeng/.../.venv/bin/python`。这是只适用于当前机器的路径，不会指向 Linux/macOS CI 的锁定解释器。使用实际运行测试的解释器/可移植路径，保持子进程导入当前候选；不能靠 skip 隐藏这些恢复测试。共享本地环境仍只读，不安装新环境。

完成修复与受影响回归后新建尚不存在的 final revision（通常 r3），不得覆盖 r1/r2。正式根为 `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-1/handoffs/`。冻结五个自有文件，记录实际六文件定向/兼容结果、运行前后 source hashes、freeze/dispatch、本指令 SHA 及逐项 finding 对应回归；ready.json 与 handoff.json byte-identical。返回两个实际存在的绝对路径，停止写入，供 Agent 3/4 重新导入及 Architect 审查。没有 full suite/wheel/远程 CI 或合并动作。
