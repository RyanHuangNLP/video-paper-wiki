# 终端 2：独立三反例的修复前后回归

先读同目录 COMMON.md。本轮只在 NEW/terminal-2/ 和自己的工作目录开发独立测试/证据，不改产品、T1 脚本或旧模型试用材料。

实现参数化 `test_mixed_links.py`（或等价独立 runner），通过 `--verifier /abs/verify_links.py` 参数或明确环境变量选择被测脚本。CLI 测试要实际调用该脚本并检查 report，不能通过导入旧模块后调用另一副本混淆身份。工作区与文件由测试自己在短临时目录创建；不依赖已清理的旧临时目录。

至少覆盖下列固定案例，磁盘 oracle 独立于被测解析器：

1. 一条正常引用 + 指向不存在文件的 `source.md?x=1#page-1`。
2. 一条正常引用 + 指向不存在文件的 `[bad](../missing/papers/<64hex>/source.md#page-1 "missing")`。
3. 一条正常引用 + unquoted HTML href 指向存在 source.md 里的不存在 `page-2`。
4. 正常来源引用单独存在应成功；无 query/title、但指向不存在 source.md 的来源引用应拒绝，防止测试或修复一律拒绝。普通非来源链接可以忽略：正常来源引用加一个不存在的非来源链接，仍应成功。

三个坏例的期望是 CLI 非零、report 存在、ok=false、有具体 errors，不能把脚本异常且没报告当成正确拒绝。报告应体现坏来源引用被处理。对带 title/unquoted HTML，支持后发现坏目标或明确 unsupported 都可接受；不能跳过它。正常来源引用和原支持形式必须继续有效。

立即用 baseline.old_verifier 的冻结副本跑同一套断言，预期前三例失败、正常来源引用/无 query 的缺失 source.md/忽略非来源链接控制例通过。保留真实红例退出码、报告和脚本 SHA；不要反转断言把旧 bug 变成“绿测试”。

T1 handoff 到达后，先验证 ready、stopped_writing、文件 SHA，再只读使用其新 verifier 运行**完全同一份**独立测试和坏输入，取得绿色结果。记录旧/新 verifier SHA、测试 SHA、实际命令与磁盘事实。实现变动后必须重跑相同冻结断言，不删失败测试。

完成后冻结测试、使用说明和 red/green 报告，files=[]，记录 tested_verifier_sha256。若新脚本仍失败，冻结 needs_fix handoff，交 T4 在相同范围完成集成修正；你不改 T1 实现，也不无限等待 T1 重发。等待上限遵守 COMMON。
