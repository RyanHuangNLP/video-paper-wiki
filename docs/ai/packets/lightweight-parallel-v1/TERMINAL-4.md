# 终端 4：公共入口、最终集成与真实贯通

先读同目录 COMMON.md 和其余三份任务。角色为用户手动启动的 Builder/集成执行者，使用现有 integration 目录；不要重置或丢失未提交候选，不执行 Git 操作。

在三个 ready 到齐之前，你仅拥有：

- `src/video_paper_wiki_research/cli.py`
- `README.md`
- `tests/research/test_light_cli.py`
- `tests/research/test_light_pipeline.py`
- `tests/research/light_real_demo.py`
- 必要时 `pyproject.toml` 的打包设置（不得添加重依赖）

先并行准备 CLI、用户说明和贯通测试。接口已在 COMMON 固定，直接按其调用，不等待上游，不创建冒充上游完成的生产实现。

新增正常入口：

```text
vpwiki-research pdf add --pdf PATH --workspace DIR [--title TITLE]
vpwiki-research index build --workspace DIR
vpwiki-research qa export --question TEXT --workspace DIR
vpwiki-research qa import --context PATH --answer PATH [--output PATH]
vpwiki-research writing export --topic TEXT --requirements TEXT --workspace DIR [--paper-id ID ...]
vpwiki-research writing import --context PATH --draft PATH [--output PATH]
```

workspace 位于批准的 `.work/**` 中。pdf add 调用 light_pdf；index build / export 调用 light_index；问答与写作调用终端 3。qa/writing 旧参数模式继续兼容，不能要求新 --workspace 同时再提供旧 Vault/config/Docling 参数。导出 stdout 直接为 COMMON 的上下文 JSON；import 按 context.schema 区分新旧路径，可输出 Markdown 文件并返回明确路径。README 以新轻量正常流程为主，指出扫描件和图表的限制。

完成自己可独立执行的部分后，检查主仓库 `artifacts/verification/manual-pdf-v1/lightweight-parallel-v1/terminal-1..3/ready.json`。依赖未齐时仅作低频文件检查（约每 60 秒），不要反复推理、跑全量、改别人代码或刷屏。若另一个终端明确失败，记录准确阻塞；不要假装它已就绪。

收到 ready 后逐份核验文件摘要，仅将各任务白名单文件复制到 integration 对应路径；不要复制整个目录。复制后这些集成文件的修复归你负责，原终端已停止写入。先跑新增模块和 CLI/贯通相关测试，解决真实接口差异；契约无法兼容时报告具体最小问题，不自行篡改证据状态。

必须用原始 SANA PDF 执行正常 pdf add → index build → qa export。实际阅读导出的原文上下文，由本次 Grok 会话生成有页码依据的答案 JSON，再通过 qa import；同样完成 writing export → 当前会话草稿 → writing import。不能把 Architect 现成 notes.md/qa.md 拷贝一下当作产品贯通，也不能用合成 converter/硬编码检索替代实际路径。

检查输出目录只含轻量文字/元数据/索引，报告 31 页提取覆盖、查询命中、有效引用、Markdown 路径及大小。验证再次导入同一 PDF 不增殖副本、改 Markdown 后旧索引被识别、重建后恢复。旧 receipt/human-gate 不在本次自动关闭。

最后构建 research wheel，在源码之外检查新模块/正常入口可用；只用已有轻量构建缓存，不重新安装环境。跑一次完整回归（基线为 2208 个已有测试，加本轮新增测试），使用主仓库 tools/lightweight-pdf/test.py 和新的证据目录。失败时修复具体问题并按必要范围复测，最终保留准确的一次全量结果。

把集成/真实样本/安装入口/全量结果追加到主仓库 terminal-4.md，详细证据放主仓库 lightweight-parallel-v1/terminal-4/。最后写 ready.json，包含全部本轮实际变更、来源模块摘要、测试、样本输出、未完成项，并停止写入交 Architect 验收。不要 commit/push/merge。
