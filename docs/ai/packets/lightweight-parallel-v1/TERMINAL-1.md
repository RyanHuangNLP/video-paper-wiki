# 终端 1：原生 PDF 提取

先读同目录 COMMON.md，角色为用户手动启动的 Builder。切换到 COMMON 指定的 terminal-1 源码副本，确认已有代码后直接实现，不重新搭环境或扩写计划。

仅允许修改：

- `src/video_paper_wiki_research/light_pdf.py`
- `tests/research/test_light_pdf.py`

实现 COMMON 的 extract_pdf 接口和 source.md/source.json 格式。复用主仓库 `tools/lightweight-pdf/extract.py` 中已经用 SANA 验证的逻辑，完善正常模块接口、标题和明确错误。直接读原 PDF，不走旧 intake 的复制 blob / Docling 路径。不下载任何模型。

验证多页、页码/字符偏移/文本摘要对应、夹杂空页、整份无文本、非法 PDF、同一输入重复执行不增殖副本或破坏其他笔记。用真实 SANA 跑 extract_pdf，检查 31 页、无 PDF/图片副本和输出字节数。这里只做抽取，不自行写检索、QA、CLI 或修改其他人的模块。

完成后按 COMMON 追加主仓库 terminal-1.md，并写 terminal-1/ready.json，列出两项文件摘要、测试和真实样本结果。最后明确停止写入，供终端 4 集成。
