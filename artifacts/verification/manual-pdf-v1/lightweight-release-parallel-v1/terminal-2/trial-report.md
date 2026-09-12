# 终端 2 试用报告 — lightweight-release-parallel-v1

角色：Builder（Grok Build，终端 2）  
日期：2026-09-06  
源码根（只读）：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`  
工作区：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-release-parallel-v1/terminal-2/workspace`  
输出目录（含空格、在 workspace 外）：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-release-parallel-v1/terminal-2/import out`  
证据根：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/terminal-2`

本文件区分流程通过、检索表现、内容对应性、未覆盖项。不是 Architect 验收。

## 1. 流程通过

解释器：`/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`  
`PYTHONPATH=/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src`  
入口：`python -m video_paper_wiki_research`（不是 `-m video_paper_wiki_research.cli`）  
cwd：`/private/tmp`

加载模块：

- `video_paper_wiki_research.cli` → `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/cli.py` SHA-256 `27225bbc2f3f762e9513f17a24e5e6a264acba36a8fb3d3ed682834d3d6ce388`
- `light_index.py` SHA-256 `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8`（R07 冻结）
- `__main__.py` SHA-256 `89e1f0772a62cee99b721d0da3a55efeb25281e81fa66f16e9779fc8a7a04720`

四份 `pdf_inputs` 哈希与 baseline 一致后，逐份 `pdf add`，再 `index build`。重复 add 第一份 PDF 未新增 paper 目录。工作区无复制的 `.pdf`。全部页切片 `text == markdown[start:end]` 且 UTF-8 SHA 匹配，页码为 PDF 1-based。

| PDF | paper_id | 页数 | warnings | source.md+source.json 字节 | exit |
| --- | --- | ---: | --- | ---: | ---: |
| arxiv-2311.15127.pdf | sha256:654ef597…a92e | 30 | [] | 106121+6651 | 0 |
| arxiv-2204.03458.pdf | sha256:564428dc…a96f | 15 | [] | 50289+3667 | 0 |
| arxiv-2311.17982.pdf | sha256:6108d596…8235 | 28 | [] | 133113+6257 | 0 |
| SANA-Video 2.0 …pdf | sha256:75958857…b23b | 31 | [] | 106264+6976 | 0 |

`index build` exit 0：`paper_count=4`，`chunk_count=197`，`size_bytes=978882`，`index_id=5407dd85aaa08cbba89b38dacd575ab6f4190c83b28a26d1851c84c865125fd8`。不是仅 SANA。

`cases.json` 写于任何答案/草稿 JSON 之前。随后 `qa export` / `writing export`，本会话根据 evidence 写新 JSON，再 `qa import` / `writing import`。未调用新模型服务，未使用 `_model_from_evidence`。

命令日志：`ingest.log`、`qa-writing.log`。

## 2. 检索表现

- 三道单篇问题均 `status=OK`、`schema=video-paper-wiki.light-context.v1`。SVD 与 VBench 的 top-k 混入了其他论文 chunk；作答只引用目标论文。SANA 单篇检索未混入其他论文。
- 比较问题第一次检索只返回 SANA（不足）。**保留首次 JSON**。一次标注改写后同时返回 SANA 与 SVD。比较作答使用改写后的 evidence。
- 无关词法查询 `xyzzyplugh quxzymorphic tungstenbeetle 91827364`：`NO_RESULTS`，evidence 空，exit 2。不是脚本伪装的模型拒答。
- 中文 writing topic 第一次 `NO_RESULTS`（中文查询对英文正文无词法命中）。**保留首次 JSON**。标注改写为英文 topic、同一对 `--paper-id` 后 `OK`，evidence 仅为 SVD+SANA，过滤掉 VBench 与 Video Diffusion Models。

## 3. 内容对应性

本会话生成的答案/草稿 JSON 经真实 import 写入含空格目录。CJK 字数 338（要求 300–600）。引用至少两篇论文。

从 `output.parent` 解析来源链接：5 个 Markdown 全部解析到 `workspace/papers/<sha>/source.md#page-N`，目标文件与页锚点存在，见 `link-self-check.json`。

`claim-review.json`：15 条数字/方法归属/比较结论全部 `supported`，0 unsupported，0 uncertain。未声称独立人工审稿。检索漏检记在 counts.misses，不把漏检改写成全支持。

## 4. 未覆盖项

- 未跑 38 项轻量或 2246 项全量，也未跑 Python 3.12 / 远程 CI。
- 未改产品源码或仓库测试。
- Video Diffusion Models（Ho et al.）未作为单篇问答目标；工作区有该论文，仅出现在多论文集合中。
- 第一次比较/中文写作检索不足，靠标注改写才得到两篇证据。
- Git/PR/CI 未执行。
- 原生文本抽取对这四份都成功；没有合成 PDF。

## 5. 关键命令（cwd=/private/tmp，除非注明）

```
python -m video_paper_wiki_research pdf add --pdf <abs.pdf> --workspace <workspace>
python -m video_paper_wiki_research index build --workspace <workspace>
python -m video_paper_wiki_research qa export --question <q> --workspace <workspace>
python -m video_paper_wiki_research writing export --topic <t> --requirements <r> --workspace <workspace> --paper-id <id> --paper-id <id>
python -m video_paper_wiki_research qa import --context <ctx.json> --answer <ans.json> --output '<import out/file.md>' --workspace <workspace>
python -m video_paper_wiki_research writing import --context <ctx.json> --draft <draft.json> --output '<import out/file.md>' --workspace <workspace>
```

exit_code：四次 add 与 index build 为 0；无关查询与中文 writing 首次 export 为 2（NO_RESULTS）；其余成功 export/import 为 0。完整 stdout 见日志。

## 6. 停止写入

`stopped_writing: true`。`files` 为空。产品问题未发现需改源码的阻断项。
