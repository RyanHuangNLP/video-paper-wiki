# 四终端轻量 PDF 迁移评审 — r05

结论：**REQUEST_CHANGES**。正常入口已经贯通，但当前集成候选有两处已复现的问题，修复后再验收。此次只评审与生成证据，没有修改产品代码或启动 Grok。

## 评审对象

- 集成目录：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`。
- 基线是 `lightweight-parallel-v1/baseline.json` 记录的 842 文件未提交候选，不能把 `bcff631` 单独当成本次实现。
- 终端 4 的 13 文件清单全部与 ready.json 一致；本次按路径排序后对路径→SHA-256 映射计算的快照摘要为 `e2823525133042e790cee821a7cddd280fd9bb3554e78f42bba747c944a5f879`。详情见 [candidate-check.json](candidate-check.json)。评审结束时再次核对，源码摘要未变。
- 四终端各自的 ready 文件摘要均验证通过；基线文件改动及新增 src/tests 文件均在各自交付清单内，见 [scope-check.json](scope-check.json)。原有 catalog/taxonomy 基线文件未改动。

## 1. P1 — 重建索引会认可失效的页内偏移，产生错误页码

位置：[light_index.py:285](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/light_index.py:285)，关联 `_load_paper` 第 125–155 行、`build_index` 第 307–310 行。

`_load_paper` 仍用旧 `text_start/text_end` 切片；`_refresh_document_digest` 只给这些旧区间更新摘要，没有重新确定原文页边界。这样，插入导言或修改前页文本长度后，重建会把错位文本签入新的“有效”索引和 source.json。

独立复现使用真实两页 PDF 经当前 pypdf 提取：第 1 页有 `quasar`，第 2 页有 `nebula`。在 source.md 的全部页锚点前插入 77 字符导言，保留所有原始页文本。随后 search 正确返回 INDEX_STALE，但 build_index 返回 OK；再次查询时，第 1 页的 `quasar` 被标为 **PDF 第 2 页**，`nebula` 返回 **NO_RESULTS**。错误页码会继续进入问答和写作引用。

这是终端 4 集成时新增的摘要刷新逻辑引入的问题；终端 2 的原交付会拒绝摘要不一致的源。现有 pipeline 测试仅在文件末尾追加文字，没有移动原有区间，因此没有发现问题。

修复要求：只在能确定分页边界时，重算各页偏移、切片和摘要后再建索引；无法确认页归属时明确拒绝并提示重新提取。不能仅通过刷新哈希接受旧偏移。补充“文件前加导言”“前页中插入/删除文字”“页锚点缺失”用例，检查原页内容仍可检索且归属正确；失败时不得把旧定位改写成有效来源记录。

证据：[rebuild-reproduction.json](rebuild-reproduction.json)；可复跑脚本：[reproduce_rebuild.py](reproduce_rebuild.py)。

## 2. P2 — 默认导出的问答和草稿引用链接失效

位置：[cli.py:377](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/cli.py:377)，写作同类位置第 425–427 行；相对链接在 [light_qa.py:331](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/light_qa.py:331) 生成。

检索给出的 `markdown_path` 相对 workspace。CLI 把渲染结果原样写到任意输出目录，却没有按输出位置调整路径。README 默认把 qa.md/draft.md 写在当前目录，而原文在 `.work/papers-ws/papers/...`；生成的 `papers/.../source.md#page-N` 因此无法打开。输出到 workspace 的子目录同样失败。

独立调用当前 CLI，QA 和 writing 各验证“显式输出到当前目录”“默认输出到 context 同目录”“输出到 workspace/notes”，共 **6 种情况均返回 OK，但链接全部失效**。源文件和页锚点真实存在。终端 4 已交付的 `sana-qa.md`、`sana-writing.md` 各有 3 个不同的来源链接，全部指向不存在的文件。

修复要求：让导出上下文/导入 CLI 获得原 workspace 根，并在最终落盘时相对 output.parent 生成可解析链接，或使用等效且明确的路径方案。context 所在目录不一定是 workspace，不能直接把它当作根。覆盖上述输出位置以及 README 原样命令，并实际验证目标文件与页锚点存在。同步重生成已交付的 SANA Markdown。

证据：[link-reproduction.json](link-reproduction.json)；可复跑脚本：[reproduce_links.py](reproduce_links.py)。

## 已通过的核对与适用范围

- Architect 独立运行六个新轻量测试文件：**31 passed in 0.13s**，见 [focused-pytest.log](focused-pytest.log)。另一位只读评审者独立检查了 QA/writing/CLI，复现链接问题；其相关 21 项测试也通过。这些数字是重叠用例，不能相加。
- 核对终端 4 一次全量日志：**2239 passed in 178.21s**、exit_code=0。这是终端 4 提供的 macOS/Python 3.13 本地证据，本轮没有再重复全量，也没有新的 Python 3.12 或远程 CI 结果。
- Architect 使用原始 SANA PDF 重新执行当前 CLI 的提取、建索引、QA/writing export/import：**31 页**，原 PDF SHA-256 未变；分页偏移/摘要与全部导出 evidence 的正文切片一致。文本和元数据 **113,078 字节**，索引 **281,923 字节**，无 PDF/图片副本。见 [sana-replay.json](sana-replay.json)。本次导入用短引文构造有效模型返回来验证协议，不作为新的模型回答质量评测。
- 检查终端 4 已安装 wheel：cli、light_pdf、light_index、light_qa、light_writing 五个模块与评审源码逐字节一致，见 [wheel-hash-check.json](wheel-hash-check.json)。安装来源/入口运行证据仍引用终端 4 既有记录，没有重新安装依赖。

建议由终端 4 在当前集成候选集中修复这两点，保留现有证据。更新文件摘要后先复跑定向用例和真实 SANA，最后再按原工作包完成必要回归；不要从旧副本整树覆盖当前集成代码。
