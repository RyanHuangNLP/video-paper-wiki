# Terminal 4 r1 — independent CLI/docs checkpoint (needs_input)

## 做了什么

在 `codex/lightweight-workflow-v2-t4` 继续合同 D 的独立 CLI/docs/测试，不改 T1/T2 已接受字节，不复制 T3 活动源码。

- 核验 T1 `handoffs/r3` SHA-256 `ac1aadc2e57b28db5359b655a2ac6ac1d4b5db1ca5dd114a414a0f143daaca89` 与 T2 `handoffs/r4` SHA-256 `e04bab0e3f2f441443b3034ab34f3a536feac236d5519a2bd8cadaecfb9f9ca6`：ready==handoff，本地 imported 十文件与生产者 files/ 字节相同。
- 旧 progress 的 117 passed / 4 skipped 与旧 wheel 只属于当时字节，本 revision 不复用。
- 安装测试已改为 `sys.executable` / `LW2_PYTHON` 与 `LW2_UV_CACHE`/`UV_CACHE_DIR`；缺路径失败而不是 skip。本轮未跑官方新 wheel（T3 未入，候选字节未冻结）。
- README 轻量 fallback 去掉会被 Bash 当成重定向的 `--session-id <64-hex>`，改为 `"$SESSION_ID"`。
- 真实执行 Bash 与 zsh 的 `CLI=(python -I/-B -m …)` / `"${CLI[@]}"` 路径：help、inspect、pdf add、index、qa/writing export 成功；`workflow prepare` 因无 T3 返回 `LIGHT_MODULE_UNAVAILABLE` / exit 2。
- 直接读取 `inbox/arxiv-2204.03458.pdf`（未复制）：15 页，`disposition=created`，index/export 成功，写出 QA/writing context 与模板。
- 用合成 PDF 的 T2 import 跑 `verify_citations.py`：href/page-anchor/slice/hash 联合通过；坏引用 `INVALID_CITATION` 且不写输出。

## 测试结果

- 定向：`tests/research/test_light_{cli,workflow_cli,pdf,pdf_recovery,workspace,index,context,selection}.py`
- 结果：**102 passed / 4 skipped**，exit 0，锁定 Python 3.13.13。
- 四个 skip 全部是 `importorskip(video_paper_wiki_research.light_workflow)`，对应 live workflow CLI。
- 模块 `__file__` 均落在 terminal-4/source。

## 预计未完成

只剩官方 T3 final。T3 `handoffs/r2/` 仅有 `report.md`，无 `handoff.json`/`ready.json`。

## 需要谁处理什么

- T3 控制器发布正式 ready（files/ + byte-identical handoff/ready）。
- 本会话在同 chat 恢复后按 COMMON 复制全部上游 final，再跑无 skip live CLI、一次 3.13 全量、一次新离线 wheel、真实 PDF 当前会话 QA/短稿、文档命令与联合核验。
- Architect / Luna 核验本 needs_input；不要把本 revision 当最终集成。

## 没有运行的验证

一次锁定 Python 3.13 全量、官方新 wheel、真实 PDF 当前会话模型试用、workflow 无 skip 回归、Python 3.12、远程 CI、Git/PR。

## 运行设置

- cwd: `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-4/source`
- HEAD: `0fcae592acb977c6b422e7de3b2c3e0cf79df5a0`
- tree: `d2d592f25d2361d5cbcc3bf58ca441a2824c256b`
- requested_model: cursor-grok-4.6-xhigh-fast
- observed_model: cursor-grok-4.6-xhigh-fast
- observed_effort: unknown
- execution_host: cursor
