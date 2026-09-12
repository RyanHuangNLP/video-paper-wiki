# 终端 2：Markdown 轻量检索

先读同目录 COMMON.md，角色为用户手动启动的 Builder。使用 COMMON 指定的 terminal-2 源码副本直接实现，不等待终端 1；根据冻结格式自己建立小型测试输入。

仅允许修改：

- `src/video_paper_wiki_research/light_index.py`
- `tests/research/test_light_index.py`

实现 build_index/search。索引只从 workspace 的 source.json 与 source.md 读取真实文本，验证文档和页切片摘要。使用已有库或标准库的词法检索，支持长页分块和多论文过滤；返回 COMMON 指定的完整 evidence。index 存在该 workspace 内、可重建；不得扫描或复制用户其他目录、不得读模型或下载 embedding。

验证多论文排序、同页不同片段、长于 4000 字符的页仍可检索、空结果、中文文本查询、相同输入稳定输出，以及 Markdown 修改/论文增删后的 INDEX_STALE。不能凭空补正文或绕过 freshness 检查。尽量让缓存大小与文本规模成比例，记录小样本实际字节数。

不要修改公共 CLI、catalog_index.py、旧 core collector、终端 1/3 模块或共享 conftest。完成后按 COMMON 追加主仓库 terminal-2.md，写 terminal-2/ready.json 后停止写入。
