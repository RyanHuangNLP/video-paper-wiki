# 轻量文库快速入门

这份说明面向实际使用者：在已有轻量工作区里整理带引用的笔记、比较选定论文、编辑/归档/恢复/替换论文，以及备份与恢复整个轻量工作区。它不是 OCR、不是模型服务、也不是正式 Vault 备份或发布。原 PDF 始终留在工作区外，不会被拷进知识目录或 ZIP。

普通用户先走自然语言 Skill：打开 `.agents/skills/video-paper-read/SKILL.md`，用当前会话说“整理这篇论文的知识笔记 / 比较这几篇 / 改标题或标签 / 先归档以后再恢复 / 备份这个工作区”。Skill 负责准备内部 JSON。下面是同一路径的最小 CLI fallback；不要把内部 JSON 当成日常手写格式。当前问答/写作仍只用 `workflow --kind qa|writing`，不要发明新的 session kind。

`vpwiki-research` 与 `python -m video_paper_wiki_research` 等价。启动方式见 [轻量 PDF 快速入门](lightweight-pdf-quickstart.md)。中文检索、长文分批、选择性刷新和提纲/章节见 [轻量研究快速入门](lightweight-research-quickstart.md)。下文使用数组 `CLI`。

## 1. 先定义本次变量

工作区、备份输出、恢复目标和比较稿都必须带 `.work` 路径分量。重复出现的旗标每次只带一个值。

```bash
CLI=(python -I -B -m video_paper_wiki_research)
WS=/absolute/path/to/.work/papers-ws
BACKUP=/absolute/path/to/.work/library-backups/papers-ws.zip
RESTORE=/absolute/path/to/.work/papers-ws-restored
COMPARE_MD="$WS/reports/compare.md"
PAPER_A=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
PAPER_B=sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210
```

`knowledge` / `compare` 的 `--context` 与 `--document` 是 Skill 或当前会话写出的 JSON **文件路径**，不是命令行里的内联 JSON。把 `knowledge export` / `compare export` 的 stdout JSON 对象原样保存为 `--context`；不要让普通用户手写这份对象。生成的 JSON 放在 `.work/**` 下。显式只读 JSON 或 `--include-output` `.md` 可以在 `.work` 外，但必须是常规文件：无符号链接/硬链接、8 MiB、严格 UTF-8，顶层必须是对象，拒绝重复键和 NaN/Infinity。不要根据旧 receipt 去扫外部目录。

## 2. 列出、编辑、归档与恢复

```bash
"${CLI[@]}" library list --workspace "$WS"
"${CLI[@]}" library edit --workspace "$WS" --paper-id "$PAPER_A" --title "显示标题" --tag video --tag diffusion
"${CLI[@]}" library edit --workspace "$WS" --paper-id "$PAPER_A" --clear-tags
"${CLI[@]}" library remove --workspace "$WS" --paper-id "$PAPER_A"
"${CLI[@]}" library restore --workspace "$WS" --archive-id "$ARCHIVE_ID"
"${CLI[@]}" library replace --workspace "$WS" --paper-id "$PAPER_A" --pdf /absolute/path/new.pdf --title "替换后的标题"
"${CLI[@]}" library recover --workspace "$WS"
"${CLI[@]}" library recover --workspace "$WS" --operation-id "$OPERATION_ID"
```

- `--tag` 省略表示保留原标签；`--clear-tags` 与 `--tag` 不能同用，表示写成空列表。
- `library remove` 是可逆归档，不是永久删除。成功 JSON 会给出 `archive_id`，再用 `library restore`。常规嵌套 Markdown/代码笔记和空目录会随论文一起归档/恢复，中文/希腊文用户文件名也按原名原字节保留；原 PDF 不会被删。
- 替换会把旧论文连同嵌套笔记放进归档，新论文用自己的 PDF 哈希。旧笔记只作为“先前论文笔记”保留，不能当成新 PDF 的陈述。刚恢复的同一篇论文再替换，是这次恢复的归档后继，`library recover` 可以证明。若在进入 staging 之前中止，旧论文仍在原位：这是**未替换**，不是一次成功发布。
- 中断后先 `library recover`，不要手改 journal。备份若拒绝非空的 `.light-library` staging，也先恢复库操作。进入 staging 之前的放弃同样不是替换成功。

有效变更之后，旧 context / 检索会变成 `INDEX_STALE`。先 `index build` 再重新 export / prepare。

## 3. 整理知识笔记

```bash
"${CLI[@]}" knowledge export --workspace "$WS" --paper-id "$PAPER_A"
"${CLI[@]}" knowledge import --workspace "$WS" --context "$KCTX" --document "$KDOC"
"${CLI[@]}" knowledge build --workspace "$WS"
"${CLI[@]}" knowledge list --workspace "$WS"
```

当前模型必须按导出 evidence 写文档：`sections` 只能是 `summary`、`method`、`architecture`、`training_data`、`experiments`、`limitations`、`code_resources`、`open_questions`。每节 `status` 为 `provisional` 或 `unknown`。未知节正文固定为“证据不足”且没有引用。至少一节必须是 provisional；全是 unknown 会以 `INSUFFICIENT_EVIDENCE` 关闭，不会发布记录。改标题/标签后先 `index build`，否则 export 是 `INDEX_STALE`。视图在 `knowledge/views/`，可读入口是返回的 `index_path`。过期或缺源的条目要标出来，不要把旧记录说成当前结论。深度嵌套或超长整数的 JSON 会以 `LIGHT_HANDOFF_INVALID` 关闭，不进后端。

## 4. 比较选定论文

```bash
"${CLI[@]}" compare export --workspace "$WS" --query "training data and evaluation protocol" \
  --paper-id "$PAPER_A" --paper-id "$PAPER_B" --dimension method --dimension experiments
"${CLI[@]}" compare import --workspace "$WS" --context "$CCTX" --document "$CDOC" --output "$COMPARE_MD"
```

必须显式给出 2–8 个不同的 `--paper-id`，不会悄悄改成“全部论文”。没有命中的论文仍留在表里，显示证据不足。中文问句可用当前会话改写成英文词法再 export。`--output` 必须是 `.md`，并且路径含 `.work`。已有文件是 `LIGHT_OUTPUT_CONFLICT`，旧字节不动。这是模型提议的对照表，不是跨数据集的科学裁定。

## 5. 备份与恢复

默认把稿子写在工作区 `reports/`，备份会收进去。只有工作区外的 `.md` 才需要 `--include-output`。

```bash
"${CLI[@]}" backup create --workspace "$WS" --output "$BACKUP"
"${CLI[@]}" backup create --workspace "$WS" --output "$BACKUP" --include-output /absolute/path/to/.work/outside/draft.md
"${CLI[@]}" backup verify --archive "$BACKUP"
"${CLI[@]}" backup restore --archive "$BACKUP" --destination "$RESTORE"
```

- 备份输出必须在被备份工作区**外面**的 `.work` 路径上，且是 create-only。ZIP 只收文件，不写空目录成员。中文/希腊文笔记名和中文 `--include-output` 报告按原名原字节进出 ZIP；对完全相同的已有 ZIP 再 create 是 reuse。
- `verify` 只读，不创建工作区或恢复目录。
- 恢复目标的父目录必须已存在且在 `.work` 下；目标本身必须不存在，即使是空目录也算冲突。
- 可重建的索引和短暂锁/空 staging 会被排除。未完成的 library / knowledge / workflow / writing 发布 staging 会拒绝，先 `library recover` 或重试对应 import/build。完整保存但尚未写完的提纲/章节是有效历史，可以备份；`progress.complete` 不是发布完整性。
- 恢复后的旧 workflow session 进入 history，不会在新根下自动继续。需要重新 `index build` 和 `workflow prepare`。
- ZIP 不包含原 PDF。也不要跟随旧 receipt 里的外部输出路径。

## 6. 边界

| 情况 | 行为 |
| --- | --- |
| 全未知知识文档 | `INSUFFICIENT_EVIDENCE`，不发布 |
| 改过 source / 元数据 | 旧 knowledge/compare/QA context 过期，先重建索引 |
| 归档后再建一篇同 id 活论文 | 冲突，保留双方字节 |
| 替换中断 | `library recover`；旧归档不能丢 |
| 备份遇到二进制/PDF/符号链接/超限 | 拒绝，不默默省略用户文件 |
| 正式 Vault / 67 条目录 | 仍走 `vpwiki` / 上游事务；这条轻量备份没有 receipt 权威 |

当前模型写出的笔记和对照表只是工程试用，不是人工事实验收，也不是 canonical 发布。
