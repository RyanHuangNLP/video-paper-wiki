# 终端 3 r03 — lightweight-release-parallel-v1 使用说明与安装入口

date: 2026-09-06  
task: lightweight-release-parallel-v1 / TERMINAL-3.md  
status: LOCAL_READY_STOPPED_WRITING  
role: 终端 3 / Builder（Grok Build `grok-4.6`）  
acceptance: not requested；ready 只表示任务材料就绪  
git: 未 commit / 未 push / 未 merge  
ci: not_run  
stopped_writing: true（文档草稿与本轮证据已冻结）

## 源码绝对路径与基线

- 已验收源码根：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`
- 主仓库工作树：`/Users/huangzhanpeng/python_code/video-paper-wiki`
- 分支：`repair/vpkb000-plan-approval-prepare-follow2`
- HEAD（未提交本轮实现）：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`
- R07 17 文件快照：`ea67d3b857a23ff721f5a53c8b730c78662e014a8dcac9e78816eda1efaab0dd`
- 本轮 `baseline.json` SHA-256：`06b0c1ac60885e7dd59485a863542fbf8bce0e6f9a2ad41eaab02021798f8357`
- 包 `TERMINAL-3.md` SHA-256：`f429905c09a18f57a2178ec33155f3861fef64b40eb140851c763ca45caf633c`
- 草稿根：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-release-parallel-v1/terminal-3/draft`
- 证据根：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/terminal-3/`
- 本修订：`.../terminal-3/r03/`（r01/r02 保留不覆盖）
- 平铺报告：`.../terminal-3.md`（追加）

未改 integration `README.md`、未改生产/测试源码。文档只写在 `draft/`。

## 文件清单

| 绝对路径 | SHA-256 |
| --- | --- |
| `.../draft/README.md` | `f8395276775c930cf87d0e5a427663083e7a25ae55b1eb577b6383091da6458b` |
| `.../draft/docs/lightweight-pdf-quickstart.md` | `82d44948d71f821317047b91fc17e9c3c74281acd695d97697ec541661ca1b74` |
| integration `src/video_paper_wiki_research/cli.py` | `27225bbc2f3f762e9513f17a24e5e6a264acba36a8fb3d3ed682834d3d6ce388` |
| integration `.../light_index.py` | `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8` |
| integration `.../light_pdf.py` | `ddc265cfa5e65d43c4a347fcfdb7f6db93b76d93e13ad0131ef98ae15fd1eb25` |
| integration `.../light_qa.py` | `d0ccf305d0dfd24128c45b22cb1f5ccbde8baf89b8d40ee95fdec798bc17d23b` |
| integration `.../light_writing.py` | `b5ee32cbae4242afd641b8f2e491a9ff38480411d9b76c872d53dc0b274115c9` |
| integration `README.md`（未改） | `ec42b6864a9291317276986bd4607790b9c44d35a8006298a910b83175206eec` |
| `.../terminal-3/ready.json` | `99aca9687a8ad9e8bd9a1e7b044deb4a643cb6ac423f43a7f4e5ec911ffd3810` |

完整哈希见 `files.sha256` 与 packet 证据目录。

## 完成内容

1. 写出可照做的 README 轻量入口 + `docs/lightweight-pdf-quickstart.md`。新文档链接按最终 `docs/lightweight-pdf-quickstart.md` 解析。
2. 只读使用既有 R06 wheel：`python -I -B -m video_paper_wiki_research`，cwd `/private/tmp/vp.t3rel`，空 `PYTHONPATH`。五个轻量模块 `__file__` 落在 site-packages，SHA 与基线一致。
3. 单独源码导入：`PYTHONPATH=.../integration/src`，`__file__` 落在 integration/src，SHA 相同。
4. 按说明对 baseline 已列原 PDF `inbox/arxiv-2204.03458.pdf`（SHA `564428dc…a96f`，15 页）跑通 pdf add → index build → qa/writing export → 当前会话 JSON → import。输出目录 `import outputs/` 在 workspace 外且含空格。
5. 独立从 `output.parent` 解析完整 href（含 `../` 前缀），确认目标 `source.md` 与 `id="page-N"` 存在；JSON markdown 与落盘一致。未使用 r06 `verify_r06.py` 的 papers/ 拼接检查器。
6. 编辑 `source.md` 后 `qa export` 返回 `INDEX_STALE`，就地 `index build` 后恢复 `OK`。
7. 复制 r06 legacy 夹具到本终端新 `.work/legacy-restore`（不改共享夹具）：先 `INDEX_STALE`，重建后 quasar 第 1 页、nebula 第 2 页。
8. 原子写入 `handoff.json` / `ready.json`，`files` 仅两份草稿文档。

当前会话答案/草稿 JSON 的 `chunk_id` 来自本次 export，是协议走查，不是终端 2 的内容质量证据。中文问句对这篇英文 PDF 返回 `NO_RESULTS`，与文档中的词法/跨语言边界一致。

## 实际测试结果

未跑 2246 项全量（包禁止）。实际命令见 `command-checks.json` / `outputs.json`。

- 已安装 `--help`：exit 0
- `pdf add`：ok，15 页
- `index build`：ok，19 chunks，122961 字节
- `qa export`（英文）：OK，8 evidence
- `qa export`（中文）：NO_RESULTS
- `qa import` / `writing import`：OK
- href：qa 2 个唯一链接、writing 3 个唯一链接，全部从 output.parent 打开
- markdown == disk：true / true
- 工作区：文本/元数据 54002 字节，索引 123069 字节（stale 重建后），无 PDF/图片副本
- 五个已安装模块 SHA 与源码基线逐字节一致

## 未完成事项

- 2246 全量、Python 3.12、远程 CI、Git/PR
- Architect 验收 / 人工 gate
- 终端 4 将草稿复制进 integration 文档（需等本 ready）
- 会话 JSON 不是 T2 质量评测

## 停止写入

是。草稿文档与 packet `ready.json` 已冻结。本 r03 与 `terminal-3.md` 仅为报告归档，不改草稿。

## 审查纠正（同一 r03，旧 ready `3d53b6ec…` 作废）

1. 第 2 节变量块补上 `CLI="python -I -B -m video_paper_wiki_research"`。未赋值时 `$CLI pdf add` 会变成 `pdf: command not found`（exit 127）；赋值后 `$CLI --help` 与 `$CLI index build` 均为 exit 0。
2. `usage-acceptance.md` 表格改为真实进程退出码：中文 `NO_RESULTS`、编辑后 `INDEX_STALE`、legacy 过期导出均为 **exit 2**（JSON status 仍是那些字符串）。

新 `ready.json` SHA-256：`99aca9687a8ad9e8bd9a1e7b044deb4a643cb6ac423f43a7f4e5ec911ffd3810`。quickstart SHA-256：`82d44948d71f821317047b91fc17e9c3c74281acd695d97697ec541661ca1b74`。未改生产模块。
