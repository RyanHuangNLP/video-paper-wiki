# 轻量研究快速入门

这份说明面向实际使用者：在已有轻量工作区里用中文问英文论文、把长文按批次整理成带引用的知识记录、做选择性刷新，以及用提纲/章节修订稿。它不是 OCR、不是模型服务、也不是正式 Vault 发布。原 PDF 始终留在工作区外。

普通用户先走自然语言 Skill：打开 `.agents/skills/video-paper-read/SKILL.md`，用当前会话说“用中文问这篇英文论文 / 把这篇长文整份整理成知识笔记 / 只接受方法节的刷新 / 先写提纲再改两节”。Skill 负责准备内部 JSON。下面是同一路径的最小 CLI fallback；**不要把内部 JSON 当成日常手写格式**。当前问答/写作会话仍只用 `workflow --kind qa|writing`，不要发明新的 session kind。

`vpwiki-research` 与 `python -m video_paper_wiki_research` 等价。启动方式见 [轻量 PDF 快速入门](lightweight-pdf-quickstart.md)。下文使用数组 `CLI`。整理单篇一键笔记、比较、文库维护和备份见 [轻量文库快速入门](lightweight-library-quickstart.md)。

## 1. 先定义本次变量

工作区、生成 JSON 和稿件路径都必须带 `.work` 路径分量。重复出现的旗标每次只带一个值。

```bash
CLI=(python -I -B -m video_paper_wiki_research)
WS=/absolute/path/to/.work/papers-ws
QUESTION="这篇论文的方法是什么"
TOPIC="请按证据写提纲"
REQUIREMENTS="用中文写提纲并修订章节。"
PAPER_A=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
REWRITE_QA=$WS/qa.rewrite.json
REWRITE_WRITING=$WS/writing.rewrite.json
```

`--rewrite` / `--context` / `--document` / `--diff` 都是 Skill 或当前会话写出的 JSON **文件路径**，不是命令行里的内联 JSON。把成功命令的 stdout JSON 对象原样保存后再传回去。生成的 JSON 放在 `.work/**` 下。显式只读 JSON 必须是常规文件：无符号链接/硬链接、8 MiB、严格 UTF-8，顶层必须是对象，拒绝重复键和 NaN/Infinity。

## 2. 中文问题检索英文证据

当前会话先写 rewrite JSON：`schema=video-paper-wiki.light-query-rewrite.v1`，`original_query` 必须与 `--question` / `--topic` 完全一致，`rewritten_query` 是含拉丁字母的英文词法，`language` 恰好为 `en`。

```bash
"${CLI[@]}" qa export --workspace "$WS" --question "$QUESTION" --rewrite "$REWRITE_QA" --paper-id "$PAPER_A"
"${CLI[@]}" writing export --workspace "$WS" --topic "$TOPIC" --requirements "$REQUIREMENTS" --rewrite "$REWRITE_WRITING"
```

QUESTION 和 TOPIC 不同时必须用两份 rewrite 文件：每份的 `original_query` 必须与当时的 `--question` / `--topic` 完全一致。`--rewrite` 只能和 `--workspace` 一起用；旧的 Vault/catalog 路径加上它是 `USAGE`。显式 `--paper-id` 出现重复值会拒绝，不会悄悄改成去重集合。检索命中仍只来自 `evidence`；`query_plan` 只是诊断痕迹。

## 3. 长文分批整理知识

```bash
"${CLI[@]}" knowledge batch-plan --workspace "$WS" --paper-id "$PAPER_A"
"${CLI[@]}" knowledge batch-export --workspace "$WS" --plan-id "$PLAN_ID" --batch-index 0
"${CLI[@]}" knowledge batch-import --workspace "$WS" --context "$BCTX" --document "$BDOC"
"${CLI[@]}" knowledge merge-export --workspace "$WS" --plan-id "$PLAN_ID"
"${CLI[@]}" knowledge merge-import --workspace "$WS" --context "$MCTX" --document "$MDOC"
"${CLI[@]}" knowledge batch-status --workspace "$WS" --plan-id "$PLAN_ID"
"${CLI[@]}" knowledge finalize --workspace "$WS" --plan-id "$PLAN_ID"
```

`--batch-index` 从 0 开始。每批只把该批 evidence 交给当前模型。处理覆盖率不是“每个事实都写进了摘要”。未完成的 batch 作业会阻止备份；完成后的作业按原字节作为历史保留。

## 4. 选择性刷新

```bash
"${CLI[@]}" knowledge refresh-plan --workspace "$WS" --paper-id "$PAPER_A"
# 源已变化时计划会返回 batches；必须先做完返回的 batch/merge，再 finalize 候选。
"${CLI[@]}" knowledge batch-export --workspace "$WS" --plan-id "$REFRESH_PLAN" --batch-index 0
"${CLI[@]}" knowledge batch-import --workspace "$WS" --context "$RBCTX" --document "$RBDOC"
"${CLI[@]}" knowledge merge-export --workspace "$WS" --plan-id "$REFRESH_PLAN"
"${CLI[@]}" knowledge merge-import --workspace "$WS" --context "$RMCTX" --document "$RMDOC"
"${CLI[@]}" knowledge batch-status --workspace "$WS" --plan-id "$REFRESH_PLAN"
"${CLI[@]}" knowledge finalize --workspace "$WS" --plan-id "$REFRESH_PLAN"
"${CLI[@]}" knowledge diff --workspace "$WS" --base-record-id "$BASE" --candidate-record-id "$CAND"
"${CLI[@]}" knowledge apply --workspace "$WS" --diff "$DIFF" --accept-section summary --keep-concepts
"${CLI[@]}" knowledge apply --workspace "$WS" --diff "$DIFF" --keep-sections --accept-concepts
```

源未变的 metadata-only refresh 可以是 0 个 batch，此时没有返回的 batch/merge 可做，直接 `finalize`。源已变化时必须先完成计划返回的全部 batch 与 merge，再 `finalize`。`finalize` 在 refresh 计划上只生成候选，不推进 HEAD。`apply` 必须同时给出互斥的章节选择和概念选择：`--accept-section KEY`（可重复）或 `--keep-sections`（空列表），以及 `--accept-concepts` 或 `--keep-concepts`。缺一组或两组都给是 `USAGE`。没有隐式全接受。

## 5. 提纲与章节修订

```bash
"${CLI[@]}" writing outline-export --workspace "$WS" --context "$WCTX"
"${CLI[@]}" writing outline-import --workspace "$WS" --context "$OCTX" --document "$ODOT"
"${CLI[@]}" writing section-export --workspace "$WS" --project-id "$PROJECT_ID" --section-id s1
"${CLI[@]}" writing section-import --workspace "$WS" --context "$SCTX" --document "$SDOT"
"${CLI[@]}" writing history --workspace "$WS" --project-id "$PROJECT_ID"
"${CLI[@]}" writing project-export --workspace "$WS" --project-id "$PROJECT_ID" --output "$WS/reports/article.md"
```

章节模型文档必须包含 `schema`、`project_id`、`section_id`、`status`、`markdown`、`citations`。未写章节显示“尚未撰写”。整篇未写或全未知不能当成完成稿导出。未写完的提纲/部分草稿是有效历史，**可以备份**；阻止备份的是未完成发布、损坏或冲突状态，不是 `progress.complete=false`。

## 6. 边界

| 情况 | 行为 |
| --- | --- |
| Vault 路径加 `--rewrite` | `USAGE` |
| 重复 `--paper-id`（rewrite 路由） | `USAGE`，不改选择集合 |
| 缺 apply 选择组 | `USAGE`，不会变成全接受 |
| 坏的交接 JSON | `LIGHT_HANDOFF_INVALID` |
| 源或索引已变 | `INDEX_STALE` / `SOURCE_INVALID` |
| 未完成发布 / 冲突 HEAD | 备份拒绝，原文件不动 |
| 未写完但完整保存的写作项目 | 可作为历史备份 |

当前模型写出的改写词、摘要、提纲和章节只是工程试用，不是人工事实验收，也不是 canonical 发布。
