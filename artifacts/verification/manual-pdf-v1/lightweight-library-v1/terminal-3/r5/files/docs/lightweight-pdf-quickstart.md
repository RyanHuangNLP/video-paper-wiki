# 轻量 PDF 快速入门

这份说明面向实际使用者：把一份本地、可选中文字的 PDF 做成可检索的 Markdown 工作区，再用**当前对话模型**写出带 PDF 文件页码引用的问答或草稿。它不是 OCR、不是模型服务、也不是正式 Vault 发布。

普通用户先走自然语言 Skill：打开 `.agents/skills/video-paper-read/SKILL.md`，用当前会话说“读这篇 PDF / 用选定论文回答 / 写一段相关工作”。Skill 负责准备会话和内部 JSON。下面是同一路径的最小 CLI fallback；不要把内部 JSON 当成日常手写格式。知识整理、多篇比较、论文维护和轻量备份见 [轻量文库快速入门](lightweight-library-quickstart.md)；那边说明如何保存 export 对象、8 MiB 文件策略、只收文件的备份，以及恢复后重新 index/prepare。

## 1. 启动方式（不要用旧 console script）

不要依赖 PATH 上的 `vpwiki-research`。那个名字可能指向本机更早安装的入口。`vpwiki-research` 与 `python -m video_paper_wiki_research` 在**同一次安装**里等价。用下面两种之一。

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

下文步骤使用第 2 节的数组 `CLI`，调用写成 `"${CLI[@]}"`。已安装默认带 `-I -B`；源码树改为 `CLI=(python -B -m video_paper_wiki_research)` 并已 `export PYTHONPATH`。这在 Bash 和 zsh 里都可用，不依赖默认拆词，也不需要 `setopt shwordsplit`。不要把整条命令放进未加引号的标量变量后再展开。

## 2. 先定义本次变量

把路径换成自己的文件。工作区必须包含 `.work` 路径分量。先定义数组 `CLI`，后面一律 `"${CLI[@]}" pdf add` 这样调用。

```bash
CLI=(python -I -B -m video_paper_wiki_research)
# 自定义解释器（路径可含空格）时写成：
# CLI=("/absolute/path/to/python" -I -B -m video_paper_wiki_research)
# 源码树：先 export PYTHONPATH，再 CLI=(python -B -m video_paper_wiki_research)
PDF=/absolute/path/to/your-paper.pdf          # 自己的 PDF，可选中文字即可
WS=/absolute/path/to/.work/papers-ws          # 知识工作区；不要把 PDF 拷进去
OUT="/absolute/path/to/my notes"              # 工作区外的输出目录，可以含空格
QUESTION="What method does this paper propose?"   # 与 PDF 正文同一语言；中文问句不会跨语言命中英文 PDF
TOPIC="video diffusion models"
REQUIREMENTS="Two short paragraphs citing original PDF file pages"
PAPER_ID=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

下面会出现的文件都由本次命令生成，不要引用仓库里不存在的示例答案文件：

```bash
CTX="$OUT/qa-context.json"          # workflow prepare / qa export 的 stdout
ANS="$OUT/qa-answer.json"           # 当前会话根据 CTX 写出
QA_MD="$OUT/qa answer.md"           # complete / qa import 的 Markdown
WCTX="$OUT/writing-context.json"
DRAFT="$OUT/writing-draft.json"
WMD="$OUT/writing draft.md"
```

## 3. 连续步骤（推荐：inspect → prepare → 当前会话 → complete）

### 3.1 查看工作区

```bash
mkdir -p "$WS" "$OUT"
"${CLI[@]}" workspace inspect --workspace "$WS"
```

只读。缺目录、空目录、需要重建索引或有损坏项时，看返回的 `state` 和 `next_actions`，不要假设已经可检索。

### 3.2 加入 PDF 并准备会话

同一 PDF 可以再加一次；已有 notes 和用户改过的 `source.md` 会留下。`prepare` 也可顺便 `--pdf`：

```bash
"${CLI[@]}" pdf add --pdf "$PDF" --workspace "$WS" --title "可选标题"
"${CLI[@]}" workflow prepare --workspace "$WS" --kind qa --query "$QUESTION" --pdf "$PDF"
```

成功时 JSON 含 `ok: true`、`session_id`、`state=awaiting_model` 和 `context`。知识目录里只有 Markdown、小型 JSON 和会话文件，没有 PDF/图片副本。把这次 stdout 存成 `$CTX` 供当前会话阅读。整份 PDF 没有可选中文字时会失败，不会生成空成功文档，也不会改走 OCR。

### 3.3 选定论文

问答和写作共用 `--paper-id`，每次只写一个 ID，需要几篇就重复几次：

```bash
"${CLI[@]}" workflow prepare --workspace "$WS" --kind qa --query "$QUESTION" --paper-id "$PAPER_ID"
"${CLI[@]}" workflow prepare --workspace "$WS" --kind writing --query "$TOPIC" --requirements "$REQUIREMENTS" --paper-id "$PAPER_ID"
```

`PAPER_ID` 必须是 `sha256:` 加 64 位小写十六进制。未知、空串或格式错误会被拒绝，不会悄悄改成“全部论文”。合法选择没有任何命中时是 `NO_RESULTS` / `INSUFFICIENT_EVIDENCE`，`session_id` 为空，不要让模型编造答案。

### 3.4 查看状态与重启继续

```bash
"${CLI[@]}" workflow status --workspace "$WS"
"${CLI[@]}" workflow status --workspace "$WS" --session-id "$SESSION_ID"
```

只读，不会修复损坏会话。重启终端后用同一个 `session_id` 再 `complete`。未完成但已有合法 completion intent 时，用**同一份** document 和 output 重试。

### 3.5 当前会话写出答案 JSON

由**当前对话模型**（或你自己）根据 `$CTX` / prepare 返回的 `context` 写 `$ANS`。`chunk_id` 必须来自本次 evidence，不要抄旧样本。最小结构：

```json
{
  "text": "用自己的话概括，并在用到的证据后写 [@chunk_id]。",
  "citations": [
    {"chunk_id": "从本次 context 的 evidence[0].chunk_id 复制"}
  ]
}
```

正文里的 `[@chunk_id]` 集合必须与 `citations` 列表一致。可选的 `paper_id` / `page` / `text_sha256` 一旦填写，必须与同一条 evidence 一致。写作草稿用 `markdown` 字段，并可沿用 `text` 回退。

`--document` 是 UTF-8 JSON **文件路径**，不是命令行里的内联 JSON。

### 3.6 完成并写出可编辑 Markdown

```bash
"${CLI[@]}" workflow complete --workspace "$WS" --session-id "$SESSION_ID" --document "$ANS" --output "$QA_MD"
```

输出可以在工作区外，路径可含空格或括号。来源链接相对 `$QA_MD` 所在目录解析。同一已完成会话再用相同 document 和 output 会复用原文件；换一份 document 或输出是 `LIGHT_SESSION_CONFLICT`，旧 Markdown 保持不动，不要覆盖用户已改过的稿。

写作同样：

```bash
"${CLI[@]}" workflow prepare --workspace "$WS" --kind writing --query "$TOPIC" --requirements "$REQUIREMENTS"
"${CLI[@]}" workflow complete --workspace "$WS" --session-id "$SESSION_ID" --document "$DRAFT" --output "$WMD"
```

## 4. 高级：原始 export / import

需要直接查看检索 context、或沿用旧脚本时：

```bash
"${CLI[@]}" qa export --question "$QUESTION" --workspace "$WS" --paper-id "$PAPER_ID" > "$CTX"
"${CLI[@]}" qa import --context "$CTX" --answer "$ANS" --output "$QA_MD" --workspace "$WS"
"${CLI[@]}" writing export --topic "$TOPIC" --requirements "$REQUIREMENTS" --workspace "$WS" > "$WCTX"
"${CLI[@]}" writing import --context "$WCTX" --draft "$DRAFT" --output "$WMD" --workspace "$WS"
```

export / import / prepare **不会**调用模型。旧的 `--vault-root` / `--upstream-root` / `--config` 路径仍然可用，但不能和 `--workspace` 写在同一条命令里。

## 5. 查看页码引用

Markdown 正文会把 `[@chunk_id]` 换成可读引用（标题与 **PDF 文件页码**）。参考文献列出：

- 论文标题
- `PDF 第 N 页`（N 是 PDF 文件的 1-based 页码，不是印刷页眉）
- `source.md#page-N` 锚点

用输出文件所在目录打开相对链接，确认目标 `source.md` 存在且含 `<a id="page-N"></a>`。核对引用时，切片文本和 hash 必须仍等于当前 `source.md` 与索引的联合结果；改过的 context 或过期索引会被拒绝，并且不会写出新 Markdown。

## 6. 编辑 source 后重新准备

直接改工作区里的 `papers/<sha256>/source.md` 之后，旧 context 和未完成会话会变成 `INDEX_STALE` 或 `stale`。不要手工改 JSON 里的偏移来“对齐”。正常恢复：

```bash
"${CLI[@]}" index build --workspace "$WS"
"${CLI[@]}" workflow prepare --workspace "$WS" --kind qa --query "$QUESTION"
```

重建后同一查询应重新 `OK`，并得到新的 `session_id`；旧的已完成 Markdown 仍保留。旧的、页码已经错位的工作区也可以**就地** `index build`，不必再导入 PDF。

## 7. 边界（不会自动做到）

| 情况 | 行为 |
| --- | --- |
| 查询无命中 | `NO_RESULTS` / `INSUFFICIENT_EVIDENCE`，不要编造论文 |
| 整份 PDF 没有可选中文字 | 提取失败，不会生成空成功文档 |
| 扫描页 / 无文字页 | 保留页码并给出 warning；不能靠本路径做 OCR |
| 图表、公式、多栏 | 页码仍按 PDF 文件；阅读顺序可能乱，需对照原 PDF |
| 中文检索 | 词法匹配工作区内中文；**不是**中英跨语言语义检索 |
| 引用检查通过 | 只说明引用指向本次提供的 evidence，**不是**事实正确性审查 |
| 改用户已有 output | 无匹配 completion intent 时拒绝，不覆盖 |
| 正式入库 / 67 条目录 / Vault | 仍走后文 `vpwiki` / 上游事务；轻量路径不会自动发布或关闭 human gate |

当前模型根据 evidence 写出的答案或短稿只是试用，不是人工事实验收，也不是 canonical Vault 发布。
