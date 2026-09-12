# 终端 1：修复可复用的引用验证工具

先读同目录 COMMON.md。在主仓库本轮证据根 terminal-1/ 独占实现 `verify_links.py`、`test_verify_links.py`、`USAGE.md`。产品源码、仓库 tests 与旧 terminal-3/verify_r06.py 都只读。本任务是验证工具开发，不能把旧验证脚本的自动拼接引文称作模型生成。

读取 Architect r07 的 verifier-limit.json 与 review.md，保留能复现旧误判的最小样本。新的工具应使用标准库，接受 `--workspace /abs/... --output /abs/answer.md --report /abs/result.json`，只读被检验文件；支持 Python 函数调用但 CLI 参数不得缺失。报告至少返回 ok、source_link_count、checked（完整 href、resolved_path、anchor、exists）、errors；缺文件、坏链接、缺锚点、无法解析预期来源引用或没有任何来源引用均令 ok=false，CLI 非零退出。

只检查产品生成的本地来源引用，普通非来源链接可以明确排除。读取实际 Markdown 中完整 href，不得先截成 `papers/...` 再拼 workspace。以 output.parent 解析实际相对路径，兼容产品输出的 Markdown 尖括号链接、空格/括号、百分号编码和实际 HTML href 形式（先检查当前 cli.py 输出语法）。解析 URL 后正确解码路径/fragment；相对路径中的 `..` 是外部输出的正常情况。确认解析目标正是声明 workspace 的 `papers/<sha>/source.md`，存在对应 `<a id="page-N"></a>`。对于不支持或不合法的来源链接语法，明确报错，不能静默漏检后判全绿。不得访问网络。

独立测试至少覆盖：输出在 workspace 根、workspace 子目录、workspace 之外、含空格/括号的父目录，以及产品支持的编码形式；反例包括错误前缀但 workspace 内存在同名来源、错误相对层级、缺 source.md、缺 page 锚点、错误论文目录、零来源引用。反例需先确认实际路径确实坏，不能用实现同一解析逻辑作为唯一 oracle。检查脚本不改写 Markdown、来源或索引。

立即用最小手写测试文件开发与验证，无需等待 T2。再只读核验 R06 终端 4 的既有 SANA 输出，记录为历史输出的工具检查；它不是新的模型/产品验收。T2/T3 的新输出由 T4 在交接后检查，你不等待它们。`USAGE.md` 写准确入口、返回值、支持语法及失败语义。

交付脚本/测试/用法及真实测试结果的摘要，files=[]；写 stopped_writing=true 的 handoff.json/ready.json 后停止。不得编辑其他终端文件、追加新依赖或跑项目全量。
