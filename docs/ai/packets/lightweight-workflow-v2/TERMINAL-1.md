# Terminal 1 — PDF 写入恢复与工作区诊断

先读同目录 COMMON、CONTRACT、freeze.json。cwd 为 ROOT/.work/parallel/lightweight-workflow-v2/terminal-1/source；模型 Grok 4.6 / xhigh。目标是在约 3–5 小时连续开发中完成合同 A，从“重跑可能覆盖笔记、异常留下半份论文”推进到可靠重试与可读诊断。

## 精确自有源码范围

- `src/video_paper_wiki_research/light_pdf.py`
- `src/video_paper_wiki_research/light_workspace.py`（新增）
- `tests/research/test_light_pdf.py`
- `tests/research/test_light_pdf_recovery.py`（新增）
- `tests/research/test_light_workspace.py`（新增）

另可写自己的 scratch/证据；不改 light_index、CLI、Skill、共享 fixture、依赖或 README。需要复用测试 helper 时在自己测试文件内定义小型 helper，不改公共 conftest。T1 不消费其他 lane 的实现；保留 baseline index 私有接口兼容性。

## 连续里程碑

1. 先用真实实现建立红例：同 PDF 重加会覆盖人工追加的 Markdown；在原两次文件写入间中断会出现不完整 pair。记录基线行为，不为了“红”而改断言。实现同文件系统目录原子发布、源身份验证、每 digest advisory lock、已完成论文 reuse。定向兼容测试通过后发布 `phase=backend`，让 T3 能用 extract_pdf。
2. 实现已拥有事务的中断识别与重试；注入 staging 创建后、MD 写后、JSON 写后、发布前、发布后的异常/进程终止。锁须随进程结束释放；同进程异常和子进程强停都要覆盖。只恢复有可证明 ownership 的生成物。验证两个同时 add 的进程不产生半文件、不覆盖 notes，第二路可以 bounded busy/reuse。
3. 实现只读 inspect_workspace：空目录、缺 index、当前/stale/损坏 index、有效论文、坏 anchors、缺 pair、意外路径、事务残留均有明确 diagnostics/next_actions。状态归并按合同，不给损坏目录贴 ready。
4. 回归标题/路径复用、人工 notes 保留、多页/空页/Unicode metadata、重复导入、已失效 metadata、source.json 身份不符、symlink/额外文件/非规则文件、未知事务保留。统一异常结果、清理仅自有临时文件，审查代码易读性后冻结 final。

## 必须证明的行为

新建成功时 `papers/<digest>` 恰有两个完整 regular 输出；失败/中断前后没有可见半 pair。重试恢复或 reuse 后输出可被 baseline build_index/search 正常消费。用户已修改 Markdown 的 repeat add byte-identical；显式冲突 title 拒绝、默认 title 不覆盖。识别同 digest 的不同源路径；不复制 PDF。损坏/未知目标从不删除。inspect 调用前后目录文件摘要和存在性不变，连缺失 workspace 都不创建。

至少包含进程级并发/强停覆盖，不能只 mock 每个私有函数。注入点以完成状态/pipe 同步，避免仅靠 sleep 猜时序。针对文件大小/mtime/内容，优先核对真实 bytes；不要使用 unlink/recreate 一定产生不同 inode 的非便携假设。

## 验证与交接

按 COMMON 短目录配方跑自己的三个 test 文件，再跑 `tests/research/test_light_index.py`、`test_light_pipeline.py`、`test_light_cli.py` 的相关旧兼容项。新增公开 API 先记录真实模块路径/SHA。CLI 旧测试因为未集成新功能无需测试新 inspect 子命令；该部分归 T4。全部自有范围完成才发布 final；仍有失败就 needs_fix，不自行扩大范围。简报列出故障窗口、恢复结果、notes 前后 SHA、并发结果与尚未跑的跨平台项。
