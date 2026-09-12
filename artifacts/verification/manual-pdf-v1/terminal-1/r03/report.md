# 终端 1 r03 — lightweight-r06-parallel-v1 索引实现

记录时间：2026-09-06  
角色：Builder / 终端 1（Grok Build grok-4.6）  
任务：`docs/ai/packets/lightweight-r06-parallel-v1/TERMINAL-1.md`  
停止写入实现：是

## 源码绝对路径

`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/terminal-1`

## 基线

- 13 文件快照：`c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39`
- 853 文件清单 SHA-256：`daf56597d6800153f8c1099013c95cb22c18ea7ba1d92b32b68041923b954ac8`
- 工作包 TERMINAL-1.md SHA-256：`8f6bad8dd157387d9404643eace69a06938c4e35ed5b01420a26b7ff94da89b5`
- COMMON.md SHA-256：`00a4137df7daf1212c73793c9ba60bc9fd582cfe238d97172ada656e3ce6369b`
- 未修复 light_index.py SHA-256：`3d105819c4af6ec4f1a84ab66ec747dcdb29234f5fd17c491ebc4750f8608b80`

## 文件清单

仅修改：

| 路径 | SHA-256 |
| --- | --- |
| `src/video_paper_wiki_research/light_index.py` | `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8` |

未改测试、夹具、CLI、README 或其他实现。共享 `legacy-workspace/` 未原地修改。

## 完成内容

`_load_paper` 不再在 document/切片摘要自洽时跳过 `_locate_pages`。读取与重建始终按当前 Markdown 页锚点、页标题、完整页集合和正文区间重算，并与已存记录比较；不一致则 `search` 返回 `INDEX_STALE`，页结构合法时 `build_index` 写回定位并重建索引。页结构不合法时 `SOURCE_INVALID`，且在写入任一 `source.json` 或旧索引之前失败。`index_id` 现包含每页偏移。

## 实际测试结果

未修复基线（物化到 `/private/tmp/vp.r06.t1.base/workspace`，未改共享夹具）：

- quasar：`OK` 第 2 页
- nebula：`NO_RESULTS`
- 再次 `build_index` 后仍错页；`metadata_stale=false`；已存偏移 (261,302)/(338,380)，活锚点 (338,379)/(415,457)

修复后同一未再编辑的旧工作区：

- 查询 quasar/nebula 均为 `INDEX_STALE`，且不改写 source/index
- `build_index` 后 quasar 第 1 页、nebula 第 2 页；偏移与活锚点一致
- 第二次重建 `index_id` 稳定 `c2cc45d3a7c5b4faaea2c0ff9e976d93222f9ee3840b6dac71d24cac46e7162a`
- 页内增删保持页码；缺失/重复/乱序锚点拒绝且不改写；后一篇非法锚点不改写前一篇

六个现有 `test_light_*.py`（未改断言）：

```text
36 passed in 0.26s
```

解释器：`/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`

证据：`artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/terminal-1/evidence/`

## 未完成事项

- 终端 2 回归测试与可移植夹具
- 终端 3 CLI/SANA/wheel
- 终端 4 集成与全量
- Python 3.12 / CI / Git

## 是否停止写入

是。本终端已停止修改 `light_index.py`。终端 2/3 按上述 SHA 复制验证。
