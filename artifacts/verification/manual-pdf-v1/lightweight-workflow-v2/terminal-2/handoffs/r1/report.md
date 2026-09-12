# Terminal 2 backend milestone (r1)

## 做了什么

在 `codex/lightweight-workflow-v2-t2` 工作树实现合同 B 的公开 API，并关闭基线 CLI 已复现的三项导入漏洞（本路用 API 证明，不声称旧 CLI 已修复）。

- `light_index.search` / `_index_is_current`：用当前 Markdown+metadata 派生完整 chunk 集，与存储 index 的论文元数据、chunk 集合、文本、偏移、页码、标题、hash、df/token_count 对照。伪造 index 不再是权威。损坏 index 稳定返回 `INDEX_STALE`，不抛 KeyError。
- 新增 `light_context.export_context` / `validate_live_context` / `render_document` / `import_document`。
- QA/写作共用论文选择：`None`/`[]` 全选；合法重复 ID 去重；未知/错误格式/空串 → `LIGHT_SELECTION_INVALID` 且 evidence 为空；筛选发生在 top-k 之前。
- 导入前与提交前两次实时校验；同目录原子安装；`overwrite=False` 只创建；拒绝时不建新 Markdown、不改已有输出。
- 链接按 `output.parent` 重写，空格/括号使用 `<>`。

## 测试结果

- 定向+兼容：`tests/research/test_light_{index,context,selection,qa,writing,pipeline}.py` → **48 passed**。
- API smoke（正确源码导入）：valid_control=OK 且写出 Markdown；篡改 evidence 文本并重算 hash → `LIGHT_CONTEXT_INVALID` 无输出；改 source 未重建 → `INDEX_STALE` 无输出；重建后旧 context → `INDEX_STALE` 无输出。
- 模块 `__file__` 落在本工作树 `terminal-2/source/src/...`。

## 未完成 / 谁处理

- Backend milestone 只冻结本快照，供 T3 只读接收 `export_context` / `validate_live_context` / `render_document` / `import_document`。
- T4 负责把 CLI 接到这些 API；不得把基线 CLI 仍成功导入伪造成新 API 失败。
- 本路继续对抗补强后发 final revision。

## 没有运行的验证

- 未跑全量 2246、未装新 wheel、未测 Python 3.12、未跑真实 Vault/OCR/Docling/网络、未做 Git 写操作。

## 运行设置

- execution_host=cursor
- requested_model=grok-4.6
- requested_effort=xhigh
- observed_model=grok-4.6（会话声明；非 CLI session）
- observed_effort=null（界面档位不可读，不虚构 xhigh）
- 无 Grok CLI session_id

## 供 Architect 审查的绝对路径

- 源码根：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-2/source`
- 本交接：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-2/handoffs/r1`
