你是本轮 Agent 2，在 Cursor 中使用已选定的 Grok 4.6，推理强度 xhigh。请直接实施任务并持续推进，不停在计划。

先读取 /Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/lightweight-workflow-v2/cursor-r1/OVERRIDE.md 和同目录 dispatch.json，再读取 /Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/lightweight-workflow-v2/TERMINAL-2.md 以及其中要求的 COMMON.md、CONTRACT.md、freeze.json 与基线。Cursor 补充替换旧包的 Grok CLI 与 /goal 启动方式，产品合同和文件归属继续有效。

唯一源码工作目录：/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-2/source；应处于 codex/lightweight-workflow-v2-t2，初始 HEAD 为 0fcae592acb977c6b422e7de3b2c3e0cf79df5a0。先核对实际项目根、HEAD、源码状态和模型/强度（不可读取就如实标记），保留已有内容；不要在主仓库 repair 分支写实现，也不要新建或切换 worktree。

修复已复现的三项导入漏洞，完成实时证据/索引校验、QA 与写作论文选择、原子 Markdown 输出及对抗测试。公开 API 可用即发布 backend milestone，随后冻结 final。

工作量约 3–5 小时。按任务单持续完成实现、定向回归和交接；可以提前完成，不能凑时长或把等待当完成。依赖未到时先做独立工作，到宿主限额或真正缺输入时保存可接续 progress/handoff。

只改本包允许路径；接收的他人文件保持原 SHA。不要调用额外 CLI 模型/API，不开子代理/Multitask，不改依赖或运行 OCR/Docling/真实 Vault，不执行 Git 写操作、Cursor Apply/Merge 或 PR 发布。交接增加 execution_host=cursor 与 dispatch_sha256，原 freeze_sha256 继续绑定父 freeze；完成后停止写入，交 Architect 审查。
