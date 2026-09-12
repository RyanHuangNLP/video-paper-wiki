# 轻量 PDF 快速入门

这份说明面向实际使用者：把一份本地、可选中文字的 PDF 做成可检索的 Markdown 工作区，再用**当前对话模型**写出带 PDF 文件页码引用的问答或草稿。它不是 OCR、不是模型服务、也不是正式 Vault 发布。

## 1. 启动方式（不要用旧 console script）

不要依赖 PATH 上的 `vpwiki-research`。那个名字可能指向本机更早安装的入口。用下面两种之一。

### 已安装包

在**源码树之外**的目录，清空 `PYTHONPATH`，用安装环境的 Python：

```bash
unset PYTHONPATH
python -I -B -m video_paper_wiki_research --help
```

确认版本：下面打印的路径必须落在**本次安装的 site-packages** 里，而不是某个旧源码树的 `src/`。

```bash
unset PYTHONPATH
python -I -B -c "import video_paper_wiki_research.light_index as m; print(m.__file__)"
```

不要使用 `python -m video_paper_wiki_research.cli`：该模块只定义 `main`，可能空输出却返回 0。

### 源码树（开发机）

必须显式指定已验收源码的 `src`，避免误导入主仓库旧代码：

```bash
export PYTHONPATH=/absolute/path/to/integration/src
export PYTHONDONTWRITEBYTECODE=1
python -B -c "import video_paper_wiki_research.light_index as m; print(m.__file__)"
python -B -m video_paper_wiki_research --help
```

打印路径应是 `.../integration/src/video_paper_wiki_research/light_index.py`。

下文用 `CLI` 表示 `python -I -B -m video_paper_wiki_research`（已安装）或已设置 `PYTHONPATH` 后的 `python -B -m video_paper_wiki_research`（源码）。

## 2. 先定义本次变量

把路径换成自己的文件。工作区必须包含 `.work` 路径分量。

```bash
PDF=/absolute/path/to/your-paper.pdf          # 自己的 PDF，可选中文字即可
WS=/absolute/path/to/.work/papers-ws          # 知识工作区；不要把 PDF 拷进去
OUT="/absolute/path/to/my notes"              # 工作区外的输出目录，可以含空格
QUESTION="What method does this paper propose?"   # 与 PDF 正文同一语言；中文问句不会跨语言命中英文 PDF
TOPIC="video diffusion models"
REQUIREMENTS="Two short paragraphs citing original PDF file pages"
```

下面会出现的文件都由本次命令生成，不要引用仓库里不存在的示例答案文件：

```bash
CTX="$OUT/qa-context.json"          # qa export 的 stdout
ANS="$OUT/qa-answer.json"           # 当前会话根据 CTX 写出
QA_MD="$OUT/qa answer.md"           # qa import 的 Markdown
WCTX="$OUT/writing-context.json"
DRAFT="$OUT/writing-draft.json"
WMD="$OUT/writing draft.md"
```

## 3. 连续步骤

### 3.1 提取

```bash
mkdir -p "$WS" "$OUT"
$CLI pdf add --pdf "$PDF" --workspace "$WS" --title "可选标题"
```

成功时 JSON 含 `ok: true`、`page_count`、绝对 `markdown_path`。知识目录里只有 Markdown 和小型 JSON，没有 PDF/图片副本。

### 3.2 建索引

```bash
$CLI index build --workspace "$WS"
```

成功时 `ok: true`。之后检索使用这份索引。

### 3.3 导出问答上下文（本地，不调用模型）

```bash
$CLI qa export --question "$QUESTION" --workspace "$WS" > "$CTX"
```

这是本地检索 + 拼上下文。**不会**调用任何模型。打开 `$CTX`，记下 `evidence[].chunk_id`、`page`、`text`。

### 3.4 当前会话写出答案 JSON

由**当前对话模型**（或你自己）根据 `$CTX` 写 `$ANS`。`chunk_id` 必须来自本次 `$CTX` 的 evidence，不要抄旧样本。最小结构：

```json
{
  "text": "用自己的话概括，并在用到的证据后写 [@chunk_id]。",
  "citations": [
    {"chunk_id": "从本次 qa-context.json 的 evidence[0].chunk_id 复制"}
  ]
}
```

正文里的 `[@chunk_id]` 集合必须与 `citations` 列表一致。可选的 `paper_id` / `page` / `text_sha256` 一旦填写，必须与同一条 evidence 一致。

### 3.5 导入为可编辑 Markdown（本地，不调用模型）

```bash
$CLI qa import --context "$CTX" --answer "$ANS" --output "$QA_MD" --workspace "$WS"
```

输出可以在工作区外。来源链接相对 `$QA_MD` 所在目录解析。

### 3.6 写作同样走 export → 当前会话草稿 → import

```bash
$CLI writing export --topic "$TOPIC" --requirements "$REQUIREMENTS" --workspace "$WS" > "$WCTX"
```

当前会话根据 `$WCTX` 写 `$DRAFT`：

```json
{
  "markdown": "第一段……[@chunk_id]\n\n第二段……",
  "citations": [{"chunk_id": "从本次 writing-context.json 复制"}]
}
```

```bash
$CLI writing import --context "$WCTX" --draft "$DRAFT" --output "$WMD" --workspace "$WS"
```

## 4. 查看页码引用

Markdown 正文会把 `[@chunk_id]` 换成可读引用（标题与 **PDF 文件页码**）。参考文献列出：

- 论文标题
- `PDF 第 N 页`（N 是 PDF 文件的 1-based 页码，不是印刷页眉）
- `source.md#page-N` 锚点

用输出文件所在目录打开相对链接，确认目标 `source.md` 存在且含 `<a id="page-N"></a>`。

## 5. 编辑后重建

直接改工作区里的 `papers/<sha256>/source.md` 之后，检索会返回 `INDEX_STALE`（索引相对当前 Markdown 过期）。不要手工改 JSON 里的偏移来“对齐”。正常恢复：

```bash
$CLI index build --workspace "$WS"
```

重建后同一查询应重新 `OK`。旧的、页码已经错位的工作区也可以**就地** `index build`，不必再导入 PDF。

## 6. 边界（不会自动做到）

| 情况 | 行为 |
| --- | --- |
| 查询无命中 | `NO_RESULTS`，不要编造论文 |
| 整份 PDF 没有可选中文字 | 提取失败，不会生成空成功文档 |
| 扫描页 / 无文字页 | 保留页码并给出 warning；不能靠本路径做 OCR |
| 图表、公式、多栏 | 页码仍按 PDF 文件页；阅读顺序可能乱，需对照原 PDF |
| 中文检索 | 词法匹配工作区内中文；**不是**中英跨语言语义检索 |
| 引用检查通过 | 只说明引用指向本次提供的 evidence，**不是**事实正确性审查 |
| 正式入库 / 67 条目录 / Vault | 仍走后文 `vpwiki` / 上游事务；轻量路径不会自动发布或关闭 human gate |

export / import **不会**自动调用模型。需要模型的只有：根据 export JSON 写出 answer/draft JSON 的那一步。
