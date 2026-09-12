# 终端 2：独立恢复回归

先读同目录 COMMON.md。在自己的源码副本立即编写回归，无需等待终端 1。

只拥有 `tests/research/test_light_index.py`、必要时 `tests/research/test_light_pipeline.py`，以及 `tests/research/fixtures/r06-legacy-workspace/` 中 source.md、source.json、index.v1.json、provenance.json 四个小夹具文件。从共享 legacy-workspace 核对哈希后复制这四个文件；其 provenance 说明如何还原布局。禁止修改生产代码。

回归必须验证旧 document/text 摘要自洽但位置错误的真实状态；在基线模块上记录新测试失败，作为历史 red 证据。然后断言新版查询识别 INDEX_STALE，不修改原文直接重建后 quasar/nebula 分别回到第 1/2 页；逐页核对起止区间、正文、SHA 与锚点，重建两次稳定。保留既有新编辑、无效锚点、多论文失败不写入等测试；没有覆盖的必要场景补在所拥有文件中。

不要通过重新导入 PDF、再次修改 Markdown、手动修正 source.json 来使恢复测试通过；不要依赖开发机旧 wheel 缓存或绝对主仓库路径。

终端 1 ready 到齐后核对 SHA，只复制其 light_index.py 到自己的副本，记录接收摘要；保持同一组测试断言不变，运行新增回归及六个 test_light_*.py。不要把复制的实现列为自己的交付文件，也不要修它。

测试通过后写 terminal-2/ready.json，列实际变更测试与四个夹具文件，保留 baseline-red 与 candidate-green 两组日志，记录 verified_light_index_sha256。若仍失败，按 COMMON 写 needs_fix 的冻结交接，说明失败输入/期望/实际，交终端 4 处理。交接后停止写入，不跑全量。
