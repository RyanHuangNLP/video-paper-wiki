# r05-fix 候选复验 — Architect r06

结论：**REQUEST_CHANGES，剩余 1 个 P1 问题**。R05-2 输出引用路径修复已通过本次复验；R05-1 已修好新编辑场景，但没有修复旧版本已经写入的错误分页记录。

## 唯一剩余问题：已有工作区重建仍保留错页和漏检

位置：[light_index.py:194](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src/video_paper_wiki_research/light_index.py:194)，范围 194–198 行。

当 document 摘要与 Markdown 相同、旧切片摘要也自洽时，`_load_paper` 直接接受 `_stored_pages`，跳过 `_locate_pages`。上一版 R05 的错误恰好会把错位偏移和新摘要一起写入 source.json。因此，已遭遇过 R05 问题的工作区升级后，即使再次执行 `index build`，仍返回 OK 并保留错误页码。

本次复现没有手工伪造 metadata：先核验历史 wheel 中 light_index.py 的 SHA-256 为 `9a7c978213d90da59d2e97391f8a10d94f5a6a2be67d6c4df2f4fcfb3f122eee`，确实是 R05 评审过的旧实现；再用它实际执行两页 PDF 提取后的建索引、加导言、重建，产生旧问题留下的来源记录。随后切换到当前候选并显式重建。

结果：当前 build_index 返回 **OK**；第 1 页的 `quasar` 仍被标为 **PDF 第 2 页**；第 2 页的 `nebula` 仍为 **NO_RESULTS**。两页原文和正确页锚点都仍存在。新版在重建前的查询也没有把该记录识别为失效。

证据：[existing-workspace-reproduction.json](existing-workspace-reproduction.json)；脚本：[check_existing_workspace.py](check_existing_workspace.py)。该脚本断言本次观察到的缺陷，只是历史失败证据，不能作为下一版通过条件。

最小修复要求：重建不能只凭旧 document/text 摘要信任页偏移；必须对照当前 Markdown 页锚点验证/重算分页范围。对旧版已经写入、摘要仍自洽的错位记录，明确识别失效并在合法页结构下恢复正确定位；不能依赖用户再次编辑 Markdown 或重新导入 PDF来触发修复。新增实际旧格式工作区的回归，确认 quasar 恢复到第 1 页、nebula 恢复到第 2 页，所有切片/摘要与页边界一致。继续保留无法确认页结构时的拒绝和不改写记录行为。

这是原 R05-1 的持久化恢复缺口，不要求扩展新的产品模块。下一次主要改动应限于 light_index 与对应回归；已通过的 CLI 修复保留。

## 已通过的部分

- **R05-2 已关闭于本次源码快照。** CLI 在上下文中携带 workspace_root，支持早期轻量上下文显式传入 --workspace，校验冲突/缺失根，按最终输出目录调整链接；原 schema 路径保持兼容。独立只读评审也对这一范围返回 GO。
- 新导言、第一页插入/删除文字的重建行为通过。我额外使用中文文本编辑，确认 Unicode 偏移、页码、正文切片与摘要正确。另验证了两个论文文件中后一个页结构失效时，前一个 source.json 和原索引均未被提前改写。见 [forward-rebuild.json](forward-rebuild.json)。
- Architect 独立重跑六个轻量测试文件：**36 passed in 0.20s**，见 [focused-pytest.log](focused-pytest.log)。其他评审者的 36 项与此重叠，不相加。
- 核对终端 4 完整日志：**2244 passed in 184.41s**、exit_code=0、启动目录为本次 integration。本轮没有重复全量，也没有新增 Python 3.12 或远程 CI 结果。
- 已安装新 wheel 的 cli、light_index、light_pdf、light_qa、light_writing 五个文件均与候选字节一致。终端 4 已交付的 SANA 问答/草稿共 **16 处正文/参考文献来源路径**全部能解析到真实源文件和对应页锚点。见 [delivery-evidence-check.json](delivery-evidence-check.json)。
- Architect 又从原始 SANA PDF 执行当前 CLI 的提取、建索引、QA/writing export。核对新导出 evidence 与已交付模型输入完全相同后，重新 import 到独立、含空格的输出目录；**16 处来源路径和页锚点全部通过**，JSON 的 markdown 与落盘文件相同。31 页切片正确、原 PDF SHA-256 未变，文本/元数据 113078 字节、索引 281923 字节。见 [sana-replay.json](sana-replay.json)。这是产品流程重放，不是新模型内容质量评估。

## 精确范围与记录

新 ready.json SHA-256：`3fa991d913c2833f331fb4a5eb7a44efafd220b5e9fafef836d9ca6067d2eac8`。13 文件的路径→SHA-256 映射快照：`c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39`。

相对 R05 确实只有声明的六个文件改变：light_index.py、cli.py、test_light_index.py、test_light_pipeline.py、test_light_cli.py、README.md。其余既有基线文件未改变。旧 ready 摘要仍为 `35854b47745f4a51795619246f64a32f8c614ce032e50c5044a799e94a6ba0f2`，R05 已记录证据摘要全部一致。详情见 [candidate-check.json](candidate-check.json)。

本次未修改产品代码、未调用 Grok、未执行 Git/远程动作。复验临时工作区已清理。没有签发整体产品验收；R05-2 的通过结论只绑定上述候选快照。
