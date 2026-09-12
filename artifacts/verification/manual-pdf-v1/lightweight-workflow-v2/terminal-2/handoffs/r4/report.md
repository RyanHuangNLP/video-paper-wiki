# Terminal 2 r4 final repair

Architect 已核验 r3 的三组修复。本 revision 只补剩余 P2：非法 UTF-8 源解码异常与分阶后自有临时文件清理。r1/r2/r3 交接与审查目录保持只读。

## 修复

1. `_load_paper` 将 source.md 读取/UTF-8 解码失败转为既有 `SOURCE_INVALID`，不把坏源当空证据，也不自动重提取。`validate_live_context` 同步关闭解码/读取异常为结构化拒绝。
2. `import_document` 一旦写出 `.light-out.tmp`，之后的预期校验失败和未预期异常退出都只清理本调用可证明归属的临时文件；旧输出保留，新输出不存在。不吞任意程序错误，也不把清理伪装成 OK。

## 测试

- 原 6 文件定向+兼容 + 新增 UTF-8/分阶/异常清理回归：**59 passed**。
- 审查 additional probe 副本回放：缺/畸形 evidence 与缺 query 仍为 `LIGHT_CONTEXT_INVALID`；非法 UTF-8 validate/分阶后 overwrite 与 create-only 均为 `SOURCE_INVALID`，旧输出保留或新目标不存在，owned stage 为空。
- 测试日志绑定的五文件 hash 与运行前后一致。`test_light_selection.py` 相对 r3 未改字节。

## Agent 3/4 必须重新接收

相对 r3 变化的文件：
- `src/video_paper_wiki_research/light_index.py`
- `src/video_paper_wiki_research/light_context.py`
- `tests/research/test_light_index.py`
- `tests/research/test_light_context.py`

`tests/research/test_light_selection.py` 相对 r3 未变。若 Agent 3/4 仍持有 r2 字节，必须从本 r4 `files/` 按 hash 重收全部五个路径。基于 r2 的工作只是历史输入。

## 未跑 / 未声称

全量、Python 3.12、wheel、CLI、真实 Vault。本文件不是 Architect 验收。

## 路径

- 源码：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-2/source`
- r4：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-2/handoffs/r4`
- 保留的 r3：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-2/handoffs/r3`
