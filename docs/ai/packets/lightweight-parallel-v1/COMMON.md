# 轻量 PDF 并行实现：共同约定

2026-09-06，Architect 为用户手动启动的四个 Grok `/goal` 任务制定。本包取代上一版将全部迁移交给终端 4 的分工，也取代已取消的八小时自动调度。不要启动其他代理、自动调用 Grok 或改变模型设置。

## 基线与文件归属

基线是终端 4 当前集成候选，包含未提交修改；不是仅有 `bcff631` 提交的旧代码。Architect 已准备三个独立源码副本并验证每份 842 个文件一致，没有复制模型、虚拟环境、vendor 或 Git 对象。

- 终端 1：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-v1/terminal-1`
- 终端 2：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-v1/terminal-2`
- 终端 3：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-v1/terminal-3`
- 终端 4：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`

前三个是源码副本，`.git/grok-worktree-source` 只是已有测试支持的来源标记，不是真实 Git worktree。不要执行 Git 命令，不要重新创建工作树，不要改原来的 goal2 或主仓库实现。终端 4 独占公共 CLI、README 和最终集成；其他终端仅修改各自任务列出的模块和测试。基线清单：主仓库 `artifacts/verification/manual-pdf-v1/lightweight-parallel-v1/baseline.json`。

所有终端仍读取主仓库 AGENTS.md、task-index.yaml、codex-team.md；历史说明与本轮用户轻量化及四终端手动并行要求冲突时，以本包和最新用户指令为准。

## 当前目标

手动 PDF → 分页 Markdown → 轻量文本检索 → 当前模型问答/写作 → 带真实页码引用的 Markdown。使用现有 pypdf 与标准库；不下载模型，不安装 Docling/PyTorch/OCR/embedding 服务，不复制 PDF/图片/视频进入知识目录。只持久化 Markdown、必要的小型来源记录和可重建文本索引。用户原始 PDF 不变。

新能力使用独立模块，不伪装成 Docling 的 profile/run/bbox，不自动继承旧 receipt/published/human-gate 状态。保留旧命令兼容和原有 67 条目录。代理生成的工作区仍放在所负责目录的 `.work/**` 中；不改真实 Vault、不运行 vpwiki-admin、不提交/推送/合并。

## 冻结的最小互通格式

无需再做大型架构评审。以下接口足以让三个模块独立实现。确有问题只报告具体字段和最小调整建议，不停止无关工作，不自行改名。

### 1. 论文文件，终端 1 写、终端 2 读

`workspace/papers/<PDF_SHA256>/source.md` 是唯一的全文正文。每页有 `<a id="page-N"></a>` 和可读页标题，N 为 PDF 文件的 1-based 页码。页面原文按 pypdf 输出作 NFC、换行和空行归一化，不臆造表格/图像内容。

同目录 `source.json`：

```json
{
  "schema": "video-paper-wiki.light-paper.v1",
  "paper_id": "sha256:<64hex>",
  "title": "paper title",
  "source": {"path": "/absolute/original.pdf", "sha256": "<64hex>", "size_bytes": 123},
  "parser": {"engine": "pypdf-native-text", "version": "actual installed version"},
  "page_count": 1,
  "document": {"path": "papers/<64hex>/source.md", "sha256": "<64hex>"},
  "pages": [{"page": 1, "anchor": "page-1", "text_start": 123, "text_end": 456, "text_sha256": "<64hex>"}],
  "warnings": []
}
```

`text_start/end` 是整个 UTF-8 Markdown 解码为 Python 字符串后的 Unicode 码点偏移，半开区间，不是字节偏移；切片只包含该页原文，不含页标题/锚点。切片 UTF-8 SHA-256 必须等于 `text_sha256`。空文本页保留页码，start=end，明确 warning；整份无文本则返回明确不支持，不能生成空成功结果。JSON 不重复保存全文。

### 2. 检索结果，终端 2 写、终端 3 读

`search` 返回 `{ok, status, query, index_id, evidence, message}`。成功 status=OK；无匹配 NO_RESULTS；文件摘要与索引不符 INDEX_STALE。`index_id` 标识所用 Markdown 内容快照，生成方法由终端 2 决定并记录。

每个 evidence 项固定：`chunk_id, paper_id, title, source_sha256, page, markdown_path, markdown_sha256, text_start, text_end, text_sha256, text, score`。路径相对 workspace，偏移针对完整 source.md；text 必须等于对应切片。一个 chunk 只跨同一页，可将长页切块。chunk_id 由内容和定位信息确定，相同输入稳定。score 是有限数字。按分数与稳定次序排序，不能依赖随机或字典遍历顺序。

索引实现可用标准库 SQLite 或轻量 JSON/BM25；不引入新服务或模型。中文查询至少支持中文文本的检索，不声称词法检索自动具备中英跨语言语义匹配。测试真实长页分块、空结果和改源后的 stale。

### 3. 模型上下文与返回文档，终端 3 负责

成功上下文为 `{ok: true, status: "OK", schema: "video-paper-wiki.light-context.v1", kind: "qa"|"writing", query, requirements, paper_ids, index_id, evidence, prompt}`。evidence 沿用上节全部字段，不丢失原文和定位。prompt 要求模型引用给定 chunk，不编造来源。上下文生成是本地操作；生成答案由当前 Grok/当前对话模型完成，不创建另一个模型服务。writing 的 paper_ids 为空表示使用此次 retrieval 中命中的论文；非空则严格过滤。

模型回答：`{text, citations: [{chunk_id}]}`；模型草稿：`{markdown, citations: [{chunk_id}]}`。正文引用标记为 `[@chunk_id]`。可选引用身份字段（paper_id、page、text_sha256 等）一旦提供，必须与同一 evidence 项共同匹配。拒绝不存在的 chunk、正文与 citations 列表不一致、交叉拼接引用；没有证据则明确 INSUFFICIENT_EVIDENCE。不要把引用结构校验宣传为事实正确性判定。

渲染返回 `{ok, status, markdown, citations, message}`；将标记转换为可读引用，并生成包含论文标题、PDF 页码和原文 Markdown 锚点的参考来源。最终路径写入由终端 4 的 CLI 负责。

## 冻结的 Python 接口

路径参数为 pathlib.Path，返回普通 dict；输入错误沿用 ResearchError 或明确的上述状态，不吞异常假成功。

```python
# light_pdf.py — 终端 1
extract_pdf(pdf_path: Path, workspace_root: Path, *, title: str | None = None) -> dict
# 成功返回 ok/status、paper_id、metadata_path、markdown_path、page_count、warnings；输出路径用绝对路径。

# light_index.py — 终端 2
build_index(workspace_root: Path) -> dict
search(workspace_root: Path, query: str, *, top_k: int = 8, paper_ids: list[str] | None = None) -> dict

# light_qa.py — 终端 3，retrieval 就是 search 的返回值
export_qa_context(question: str, retrieval: dict) -> dict
render_answer(context: dict, answer: dict) -> dict

# light_writing.py — 终端 3
export_writing_context(topic: str, requirements: str, paper_ids: list[str], retrieval: dict) -> dict
render_draft(context: dict, draft: dict) -> dict
```

终端 2/3 用符合本约定的小型测试输入独立开发，无须等待上游。真正跨模块和真实 SANA 测试由终端 4 完成，不用测试替身代替最终贯通。

## 环境与交付

共享解释器只读使用 `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`。PATH 含 `/Users/huangzhanpeng/.hermes/bin`，UV_CACHE_DIR 固定为主仓库 `.work/cache/uv-tests`，UV_OFFLINE=1、UV_PYTHON_DOWNLOADS=never、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、PYTHONDONTWRITEBYTECODE=1；测试临时目录用 `/private/tmp` 下的短路径。只有终端 4 最后跑一次全量，终端 1–3 跑相关测试。环境用法见主仓库 `tools/lightweight-pdf/README.md`。不要重复准备环境或下载依赖。

每个终端只追加主仓库绝对目录 `artifacts/verification/manual-pdf-v1/terminal-N.md` 中属于自己的日志，写任务、改动、命令/结果、未完成项及停止写入状态。交付就绪文件统一写入主仓库 `artifacts/verification/manual-pdf-v1/lightweight-parallel-v1/terminal-N/ready.json`，包含 `status: "ready"`、`source_root`、`files: [{path, sha256}]`、`tests`、`known_gaps`。path 为自己源码副本内的相对路径，限定本任务允许的文件。只在实现完成且相关测试通过后写 ready；先写临时 JSON 再替换为 ready.json，避免终端 4 读到半份文件。写出后停止改代码。

真实 PDF：`/Users/huangzhanpeng/Downloads/SANA-Video 2.0- Hybrid Linear Attention with Attention Residuals for Efficient Video Generation.pdf`，31 页，SHA-256 `759588574b9b33bff83a6c8c05da1455535498c6cb70992678079242ddaeb23b`。现成阅读参考在主仓库 `artifacts/verification/manual-pdf-v1/sana-lightweight/`。本轮 SANA 的持久阅读文本/元数据应小于 1 MiB，索引单列统计并保持小于 5 MiB；这是该样本验收约束，不要求对所有论文武断裁剪正文。
