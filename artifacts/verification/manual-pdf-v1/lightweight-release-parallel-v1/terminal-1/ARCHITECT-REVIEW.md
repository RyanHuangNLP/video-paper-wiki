# Terminal 1 → Architect review

请按 `docs/ai/packets/lightweight-release-parallel-v1/TERMINAL-1.md` 与 `COMMON.md` 审查本终端冻结交接。本文件只索引已冻结产物；`verify_links.py` 在 `ready.json` 写出后未再修改。

## 冻结交接

| 文件 | SHA-256 |
| --- | --- |
| `ready.json` | `a5148386e518c7fa1be369306e1f756abffd2f1a33d3d98966cd219753cdb906` |
| `handoff.json` | `a5148386e518c7fa1be369306e1f756abffd2f1a33d3d98966cd219753cdb906`（与 ready 字节相同） |
| `verify_links.py` | `51d67390e22dc3c21f2f4f85b12a9ab78d8c583eb3242f4c8e7c81248661f743` |
| `test_verify_links.py` | `eb278ba4553ebdf643778f6f83404cd37c75592b45d5eca13de0765ad541b0c8` |
| `USAGE.md` | `1dfcca1f803f93ba7688c14c1216b9729a6b97106a43afc3affe70ff563e1751` |
| `files.sha256` | 同目录清单，含 evidence/samples |

`status=ready`，`files=[]`，`stopped_writing=true`。没有待集成产品文件。

绝对目录：

`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/terminal-1/`

## 对照输入（未改）

| 项 | SHA-256 |
| --- | --- |
| TERMINAL-1.md | `e86810adefa2a6062a877f928112e622e0a48672b3291f03e030395d3500f216` |
| COMMON.md | `1fae9eea106e46f6c087f4fa5b437f8ee71351d36c9ea692aa0133893d054201` |
| baseline.json | `06b0c1ac60885e7dd59485a863542fbf8bce0e6f9a2ad41eaab02021798f8357` |
| integration `cli.py` | `27225bbc2f3f762e9513f17a24e5e6a264acba36a8fb3d3ed682834d3d6ce388` |
| integration `light_index.py` | `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8` |
| 旧 `verify_r06.py` | `78134bded9f658905190ab5ba838706af6d8baf458309a1e820196e2353b17a6` |

## 请核对的行为

1. CLI 必填绝对路径 `--workspace --output --report`；缺参非零。报告字段 `ok` / `source_link_count` / `checked{href,resolved_path,anchor,exists}` / `errors`。
2. 完整 href 相对 `output.parent` 解析，不截 `papers/...` 拼 workspace。
3. `test_verify_links.py` 驱动 shipped `verify_links.py`：`15 passed in 0.12s`（`evidence/test_verify_links.log`，复跑日志相同）。
4. CLI 好样本两次一致 `ok=true`；坏样本两次一致 `ok=false` 且 errors 非空。
5. 保留 r07 样本：旧验证器 `errors=[]`，新工具 `ok=false`。
6. R06 终端 4 SANA Markdown 只读历史检查通过，不是新验收。

## 未完成（非本终端阻断）

终端 2/3 新 Markdown；全量 pytest / Python 3.12 / Git / CI；不原地修补旧 `verify_r06.py`。
