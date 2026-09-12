# 终端 3：独立 CLI、SANA 与 wheel 验证

先读同目录 COMMON.md。自己的源码副本仅供运行与安装来源验证，不修改生产代码、仓库测试或 README。

立即在主仓库共同证据根的 terminal-3/ 中准备一个可复跑验证脚本和用法说明。脚本通过参数接受待验证源码根或已安装 Python、独立 workspace、输出目录和 PDF；不能把 integration、旧 wheel 或 terminal-3 的路径写死为被验证实现。记录实际导入模块文件和 SHA，避免运行到共享解释器的另一个源码副本。

先在当前副本确认既有 CLI 正常流程和输出链接可用，明确标记为 baseline 观察。终端 1 ready 到齐后，只核对并复制其 light_index.py 到自己的副本；之后的正式验证必须绑定这个新 SHA。

使用原始 SANA PDF 在自己的新 `.work` 工作区执行实际 pdf add、index build、qa/writing export/import。阅读当前 export 的 evidence，生成当前会话答案/草稿 JSON；如沿用旧模型 JSON，先验证 evidence 完全相同。检查 31 页、原 PDF 摘要未变、文本元数据小于 1 MiB、索引小于 5 MiB、无 PDF/图片副本。输出到 workspace 之外及含空格目录，实际解析每处来源路径和页锚点，确认返回 Markdown 与落盘一致。

以本副本和现有轻量构建缓存生成新 wheel，在源码目录外用隔离安装解释器运行正常入口，确认 light_index SHA 等于终端 1 ready；也验证旧工作区恢复，不只检查 import 成功。不要安装模型或新环境依赖，不跑全量。

脚本、模型 JSON、wheel 验证命令和报告放 terminal-3/，供终端 4 按参数重放。ready.json 中 files=[]，artifacts 列冻结脚本/说明/输入和关键证据摘要，记录 verified_light_index_sha256 与准确命令。失败时按 COMMON 写 needs_fix 冻结交接。结束后停止写入；不要把旧证据贴成新结果。
