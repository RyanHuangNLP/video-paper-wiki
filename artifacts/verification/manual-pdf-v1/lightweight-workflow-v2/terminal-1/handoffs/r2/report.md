# Terminal 1 development brief

## 做了什么

在指定 worktree 实现合同 A：

- `extract_pdf` 在同文件系统上先写完整两文件 staging，再 `os.rename` 到缺席的 `papers/<digest>`。成功时该目录恰有 `source.md` 与 `source.json` 两个常规文件。
- 每 digest 使用 `fcntl.flock` 非阻塞锁（`.light-transactions/<digest>.lock`）。锁文件存在不代表进程仍在；进程退出后内核释放锁。活跃持有者返回 `ok=false,status=LIGHT_WORKSPACE_BUSY`。
- 完整且身份/锚点有效的已有论文走 reuse，两个输出 byte-identical，包括用户改过的 Markdown。默认 title 不覆盖；显式非空 title 与现有 metadata title 冲突时 `LIGHT_PAPER_CONFLICT`。同 digest 不同路径视为同一论文，保留原 source.path/title。
- 不复制 PDF。T1 自行校验 `source.sha256==digest`，不使用 `_load_paper` 的 digest 回退。
- 只恢复有所有权标记且 allowed set 恰为两个生成文件的 staging。未知标记、symlink、半 pair、额外非规则文件一律保留并拒绝，不递归清理。
- 注入点：`after_lock` / `after_staging_create` / `after_md_write` / `after_json_write` / `before_publish` / `after_publish`。进程级测试用 fifo 同步，不用 sleep 猜时序。
- `inspect_workspace` 只读，包括缺失目录也不创建。状态优先级：损坏/待处理事务 → `needs_attention`；无论文无损坏 → `empty`；有效论文但 index 非 current → `needs_index`；否则 `ready`。缺 index 不是损坏。

## 测试结果

- 模块来源：`.../terminal-1/source/src/video_paper_wiki_research/light_pdf.py` SHA-256 `d51551b81939039114ebb208eb94db5ae48dc84f42b785ed9597542674e96770`
- 模块来源：`.../terminal-1/source/src/video_paper_wiki_research/light_workspace.py` SHA-256 `a166be3a82d2bd62223fbf1196bef7540514f816552e36487eb15f336f8929f2`
- 定向：`tests/research/test_light_pdf.py` + `test_light_pdf_recovery.py` + `test_light_workspace.py` → 29 passed
- 兼容：`test_light_index.py` + `test_light_pipeline.py` + `test_light_cli.py` → 19 passed
- 覆盖：写入中断、同进程异常、子进程 SIGKILL、并发 add busy/reuse、标题冲突、损坏 pair、未知事务保留、缺 pair、symlink、Unicode 标题、失效 metadata 复用、源身份不符、inspect 前后目录摘要不变。
- 并发复用后 `user-note.md` 与 `source.md` 的 SHA-256 与加锁前相同；`papers/<digest>` 无半 pair。
- 恢复：`after_json_write`/`before_publish` 强停后 retry `disposition=recovered`；`after_publish` 后 reuse。

## 预计未完成 / 未跑

- 未跑 Python 3.12 与 Linux 矩阵（本机仅验证 3.13.13 / macOS）。
- 不声称掉电持久性或敌对并发替换文件系统。
- 未跑 OCR/Docling/真实 Vault/真实 inbox PDF（归 T4 试用）。
- 未做 Git 写操作或 Cursor Apply/Merge。

## 需要谁处理什么

- Agent 3 可读 `handoffs/r1`（backend）使用 `extract_pdf`；最终集成必须再核 `handoffs/r2` final 是否改变已接收文件。本轮 r1/r2 五个自有文件字节相同。
- Architect 审查本候选。Repo Steward 在明确指令前不得提交/开 PR。

## 模型观察

- requested_model=`grok-4.6`，requested_effort=`xhigh`，execution_host=`cursor`
- observed_model=`grok-4.6`（当前会话自称）
- observed_effort=`null`（Cursor UI 推理强度不可机读；不能把界面 High 记成 xhigh）
- session_id=`null`

## 审查路径

- 源码：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-1/source`
- 交接：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-1/handoffs/r1` 与 `.../r2`
