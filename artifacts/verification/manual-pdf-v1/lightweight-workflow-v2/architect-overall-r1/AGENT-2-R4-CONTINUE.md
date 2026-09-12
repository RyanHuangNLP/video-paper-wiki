# Agent 2：R3 已关闭旧缺口，R4 只补异常路径

本文件取代本目录较早的 AGENT-2-CONTINUE.md 作为当前续跑入口；保留旧文件。审查期间你已发布正式 r3，Architect 不要求重复 r3 已完成的工作。

继续当前 Cursor Grok 4.6 会话及 `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-2/source`。遵守原 COMMON、CONTRACT、TERMINAL-2、freeze 与 cursor-r1/OVERRIDE，只修改原五个自有路径。正式 r3 handoff/ready SHA-256 均为 `802b5d787e4e75db654ec236d6e4b326e1dc8d487fd1eeb2ece9bbd86bfcb7fd`。当前 light_index.py 为 `e03b05fe50a7e4793e9b4ab8ab9f0ec4b7fe046ce9865ca2dafdc7040dea07c9`，light_context.py 为 `7c3b46b9323eb04297ea07eb44de319b40430f60cd12316e70f7ef06f66fecac`。

## 已通过，不重做

Architect 独立复跑六文件 55 passed；旧九项 probe 及七项缺失/畸形 context shape 观察均符合修复要求。staging 之后的 live check、原 context/index 类型拒绝和 public search selection 三组问题已关闭。全部旧交接、旧审查与这些通过证据保留原字节。

## 剩余一项 P2：源文件解码失败及临时文件清理

读取同目录 `t2-r3/probe_additional.py` 与 `t2-r3/additional-results.json`。这是实际 r3 模块的小型合成源探针，不是真实 PDF 试用。探针会写相邻 JSON，复制到自己的 scratch 后才可执行。

- source.md 为非法 UTF-8 时，validate_live_context 的 `_load_live_papers` → `_load_paper` 泄露 UnicodeDecodeError，没有 SOURCE_INVALID 关闭结果。
- 在 `.light-out.tmp` 写完、最终 revalidate 前将 source.md 变为非法 UTF-8，overwrite=True 和 create-only 均抛相同异常，并遗留自有 temp。旧输出已正确保留/新输出不存在，这一部分保持。

在原 light_index/light_context 自有范围内将预期的源解码/读取失败转换为既有结构化拒绝；本次非法 Markdown 解码用 SOURCE_INVALID，不把坏源当空证据或自动覆盖重提取。确保输出 staging 一旦创建，之后预期校验失败及异常退出都会只清理本调用可证明归属的临时文件；旧输出保留、新输出不存在。不以吞掉任意程序错误或返回 OK 代替清理，也不承诺锁住外部编辑器。

新增直接 validate/import 的坏 UTF-8 回归，以及在实际 staging 边界注入后的 overwrite/create-only 回归。断言结构化 status、无未处理解码异常、旧输出保存或新输出缺失、无本次 owned stage 遗留。重跑受影响的原六文件和新增测试，并确认 r3 已关闭的案例仍通过。不得通过 CLI 总捕获或关闭测试掩盖 backend 缺口。

## 新交接

在 `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-2/handoffs/` 创建尚不存在的新 final revision，通常 r4。保存所有五个精确文件、真实运行前后 hash、命令/日志/结果、原 freeze/dispatch、r3 输入 SHA 和本指令 SHA；handoff.json/ready.json 字节相同。明确列出 changed-from-r3，供 Agent 3/4 替换其旧 r2 输入。返回两个存在的绝对路径后停止写入。

不要运行 Git、跨 lane 写入、改依赖/合同、全量/wheel、额外模型或真实 Vault。你只负责此处剩余异常路径；不替 Agent 1/3 修其归属文件，也不将自检称为 Architect 验收。
