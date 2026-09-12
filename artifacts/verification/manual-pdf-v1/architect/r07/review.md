# 四终端 R06 修复复验 — Architect r07

结论：**本轮产品修复通过本地验收**，绑定 17 文件快照 `ea67d3b857a23ff721f5a53c8b730c78662e014a8dcac9e78816eda1efaab0dd`。原 R05/R06 的错页、漏检和输出引用路径问题均已关闭。未发现本轮产品代码的新增阻断问题。

## 修复结果

索引现在始终按当前 Markdown 的页锚点和页标题定位，再比较 source.json 的完整页集合、偏移和摘要；索引快照也包含偏移，检索会核对索引中的页记录。旧错误记录即使摘要自洽，也不能再绕过定位验证。

我独立将便携旧工作区还原到新的临时目录，在**源码与隔离安装 wheel**中分别验证：

- 未再次编辑或导入 PDF，查询首先返回 INDEX_STALE，且不改写来源或索引。
- 直接重建后，quasar 位于 PDF 第 1 页，nebula 位于第 2 页；正文、Unicode 区间及摘要都正确。
- Markdown 和原 PDF 身份不变；再次重建的来源/索引字节与 index_id 稳定。

源码和 wheel 的 light_index.py 均为 `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8`。wheel 验证使用其 Python 的 `-I` 模式，工作目录在源码之外，导入实际来自安装目录。详见 [source-recovery.json](source-recovery.json)、[wheel-recovery.json](wheel-recovery.json) 和可复跑的 [verify_recovery.py](verify_recovery.py)。

## 范围与测试证据

- 四份 ready 的文件及所列证据摘要全部一致；终端 4 接收的 ready 摘要匹配，当前实现与终端 1 完全一致，测试和四个小夹具与终端 2 完全一致。
- 相对 853 文件基线，既有源码仅 light_index.py 与 test_light_index.py 改变，另加四个获准夹具；CLI/QA/writing/PDF/README 保持原候选。R05/R06 已记录历史证据和旧 ready 未变。见 [candidate-check.json](candidate-check.json)。
- Architect 独立运行六个轻量测试文件：**38 passed in 0.21s**，exit_code=0。见 [focused-pytest.log](focused-pytest.log)。第一次记录脚本在测试结束后的结果序列化阶段出现变量遮蔽错误；原日志保留，已修正评审脚本并完成这次可核验的定向重跑，不属于产品失败。
- 核对终端 4 一次完整回归：**2246 passed in 212.32s**，exit_code=0，实际启动目录为 integration。此数包含新增两项回归；终端之间重叠测试不相加。本轮未重复全量，没有新的 Python 3.12 或远程 CI 结果。
- 五个已安装模块 cli、light_index、light_pdf、light_qa、light_writing 均与当前源码逐字节一致。见 [delivery-evidence-check.json](delivery-evidence-check.json)。

## 真实 SANA 与引用

我从原始 PDF 重新执行当前 CLI 的提取、建索引、QA/writing export。新导出 evidence 与终端 4 提供的模型输入逐项一致后，重放它的答案/草稿 JSON，并 import 到独立、含空格的外部输出目录。

31 页切片和摘要正确，原 PDF SHA-256 未变。文本/元数据为 **113078 字节**，索引 **281923 字节**。交付文件与独立重放文件各有 **14 处正文/参考文献来源路径**，均按实际 output.parent 解析并确认目标文件和页锚点存在；返回 Markdown 与落盘内容相同。见 [sana-replay.json](sana-replay.json)。这是流程和引用协议复验，不是新模型内容质量评测。

## 非阻断的验证脚本问题

终端 3 的 [verify_r06.py](/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/terminal-3/verify_r06.py) 中 `_verify_links` 仅提取 `papers/...` 后拼接 workspace，丢弃最终链接的前缀，没有从输出文件所在目录解析。我给它一个实际无法打开的相对链接，它仍返回空 errors；因此它的 links_ok **不作为本次验收依据**。应在后续复用该脚本前，改为解析完整 href 并以 output.parent 检查，增加坏相对路径的负例。复现见 [verifier-limit.json](verifier-limit.json)。

该脚本的 `_model_from_evidence` 是自动拼接引文的协议夹具，不应描述为真实模型生成验证。本次流程结论使用终端 4 的独立答案/草稿及 Architect 重放；没有把终端 3 的自动引文当作模型质量证据。

上述问题只在交付验证脚本中，产品源码没有使用它。Architect 的独立输出路径检查已补齐所需证据，因此无需为此重开索引修复。

本次只写评审证据，没有修改产品代码、启动 Grok 或执行 Git/远程操作；所有本轮临时工作区已清理。验收绑定本地工作树快照，源码改变后需重新核验相应范围。
