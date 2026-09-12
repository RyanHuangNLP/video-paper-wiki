# 终端 3：可照做的使用说明与安装入口验证

先读同目录 COMMON.md。只在主仓库 `.work/parallel/lightweight-release-parallel-v1/terminal-3/draft/` 编辑 `README.md` 和新 `docs/lightweight-pdf-quickstart.md`。README 已从已验收 integration 按摘要复制；它是文档草稿，不是源码根。共享 integration 的 README 和所有生产/测试文件都不由你直接改。

当前 README 已有轻量入口，不重复堆叠第二套过时命令。保留旧正式入库/领域命令与 67 条目录说明，在开头提供简洁指引，并链接新的 quickstart。新说明面向实际使用者，应包含：

- 已有锁定环境/安装包的准确启动方式，以及如何确认 CLI 实际指向本次版本；不能只依赖本机主仓库旧的 console script。
- 使用用户自己的可选中文字 PDF，从 `.work` workspace、pdf add、index build 到 qa/writing export、当前会话生成 JSON、import 的连续步骤；关键变量和文件要先定义，不引用不存在的占位答案文件。
- 模型 JSON 的最小真实结构；chunk_id 来自本次上下文，不硬编码旧样本引用。明确哪一步需要当前会话模型生成，不把 export/import 宣传成自动调用模型。
- 查看 Markdown 与 PDF 文件页码引用；输出在 workspace 外时的路径；编辑 source.md 后的 INDEX_STALE 和正常重建；旧错误工作区可直接恢复。
- 空结果、扫描页无文本、图表/公式/多栏阅读顺序、中文词法与跨语言语义边界，以及轻量路径与正式 Vault 发布的关系。

不得在产品说明中堆积内部 reviewer 状态、哈希清单或终端协调细节；这些只进证据。不要许诺 OCR、模型服务、事实审稿或自动正式入库。

在自己的新工作区按说明逐条执行核心命令，使用一份 baseline.json 已列的原 PDF。用只读的既有 R06 installed wheel，在源码目录外运行 `python -I -B -m video_paper_wiki_research`；记录清空 PYTHONPATH、实际 `__file__`、五个轻量相关模块 SHA。若文档涉及源码方式，也单独核对实际源码导入路径。不要改装现有 wheel/共享环境，不为此再下载依赖。缺少既有安装时可完成文档与源码验证并记录安装缺项，让 T4 统一构建一次。

命令演示中的答案/草稿必须从本次 evidence 由当前会话形成；如果仅验证协议，可以明确标记为协议示例，不能作为 T2 的内容质量证据。输出在自己的 workspace 外且包含空格，独立核对完整 href；生成供 T4 使用的 outputs.json。执行失败先纠正文档或调用方法；确认产品缺陷则报告，不修产品。

交付两份完整文档及 SHA，files 中的 path 相对 draft_root；另有 `command-checks.json`、`outputs.json` 和简短使用验收报告。这些是 T4 唯一获准复制到 integration 的文档路径。新文档中链接必须按最终 docs/ 路径解析。写 frozen handoff/ready 后停止修改，文档所有权才转给 T4。不跑 2246 项全量。
