# Terminal 3 final (r1)

## 做了什么

在 `codex/lightweight-workflow-v2-t3` 实现合同 C：可恢复 `prepare_workflow` / `workflow_status` / `complete_workflow`，以及统一自然语言阅读 Skill。源码已停止写入。

- Session 身份是 request+context 的 canonical SHA-256，不含时钟或随机因素；相同 request+snapshot 复用，源变化产生新 session 并保留历史。
- 持久化 JSON 使用 B(x)=C(x)+一个 LF；每次使用校验目录名、允许条目、整份 manifest bytes、跨文件绑定。
- Status 只读；缺 workspace 不创建；损坏/未知项/symlink/遍历不能回到 `awaiting_model`/`complete`。
- Complete 先 `render_document`，再写 immutable `completion-intent.json`，再调用 T2 `import_document(..., overwrite=False)`，再写 receipt。intent/receipt 临时文件在 `.light-workflow/staging/`，不进入 session 允许条目集。
- 覆盖 intent/output/receipt 中断恢复。用户改稿或无 intent 的已有文件永不覆盖。
- 并发 complete 使用 per-session flock；第二路返回 `LIGHT_WORKSPACE_BUSY`，不写虚假 receipt。
- 新增 `.agents/skills/video-paper-read`；ingest/query 把轻量阅读路由过来，并保留显式 canonical/Vault 指令。
- 先独立协议 stub，再按 hash 导入 T1 `handoffs/r2` 与 T2 `handoffs/r2` final，接通真实 extract/inspect/export/validate/render/import。导入文件保持生产者 SHA。

## 测试结果

- 自有三项 + 导入 T1/T2 定向/兼容：116 passed，exit 0。日志：`E/terminal-3/logs/final-pytest.log`。
- 模块 `__file__` 均落在 terminal-3/source，不是主仓库或已安装包。
- 导入文件 SHA 与生产者 final r2 字节一致。
- 真实后端结构 fixture 链路：prepare(`disposition=created`) → 结构 fixture document → complete(ok) → 重启 status=`complete`。标签为 structural fixture，不是当前会话模型试用。证据：`E/terminal-3/logs/live-chain.json`。

## 预计未完成

无本路实现剩余项。T4 CLI/文档/当前会话模型试用、Architect 审查、Steward 提交均不在本 lane。

## 需要谁处理什么

- Architect 审查本 lane final，再决定是否授权交付。
- T4 按 hash 接收本 handoff 做 CLI/文档/当前模型试用；不得把结构 fixture 标成真实模型试用。
- T1/T2 文件仍由原作者维护；本 lane 未改它们。

## 没有运行的验证

- 未跑全量 2246、未装新 wheel、未测 Python 3.12。
- 未跑 T4 CLI help / 当前会话模型试用。
- 未跑 OCR/Docling/真实 Vault/网络/Git 写操作。

## 运行设置

- execution_host=cursor
- requested_model=grok-4.6
- requested_effort=xhigh
- observed_model=grok-4.6
- observed_effort=null（界面档位不可读，不虚构 xhigh）
- 无 Grok CLI session_id

## 供 Architect 审查的绝对路径

- 源码根：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-3/source`
- 本交接：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-3/handoffs/r1`
- 进度：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-3/progress.md`
