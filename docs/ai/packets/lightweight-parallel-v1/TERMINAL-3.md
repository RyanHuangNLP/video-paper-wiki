# 终端 3：引用问答与 Markdown 草稿

先读同目录 COMMON.md，角色为用户手动启动的 Builder。使用 COMMON 指定的 terminal-3 源码副本直接实现。使用符合冻结格式的小型 retrieval 输入并行开发，不等待终端 2。

仅允许修改：

- `src/video_paper_wiki_research/light_qa.py`
- `src/video_paper_wiki_research/light_writing.py`
- `tests/research/test_light_qa.py`
- `tests/research/test_light_writing.py`

实现 COMMON 冻结的四个接口。上下文包含原文、页码和来源摘要；提示当前模型依据给定内容回答和写作。导入模型文档时联合校验引用身份，渲染可读的页码来源和参考文献。保持错误/无结果/证据不足的区别，不把“引用存在”等同于“事实正确”。不启动外部模型服务、浏览器或其他代理。

验证合法多引用、缺失/虚构引用、正文标记和列表不一致、把甲论文标识与乙论文 chunk/page 混配、空证据、写作 paper_ids 过滤。模型文档可能含非 ASCII 标点、中文和多段 Markdown，输出应可直接编辑。读写路径由 CLI 处理，模块本身以 dict 输入输出为主，不改公共 CLI 或旧 qa.py/writing.py。

完成后按 COMMON 追加主仓库 terminal-3.md，写 terminal-3/ready.json，停止写入。
