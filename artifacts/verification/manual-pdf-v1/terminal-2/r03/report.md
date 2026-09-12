# 终端 2 r03 — lightweight-r06-parallel-v1 独立恢复回归

角色：Builder（Grok Build，终端 2）  
日期：2026-09-06  
包：`docs/ai/packets/lightweight-r06-parallel-v1/TERMINAL-2.md`  
工作包 SHA-256：`9ea6ef6590b877418e2521ead4251e728e0822542459e2c6d99c075657fded81`  
COMMON SHA-256：`00a4137df7daf1212c73793c9ba60bc9fd582cfe238d97172ada656e3ce6369b`

## 源码绝对路径与基线

| 项 | 值 |
| --- | --- |
| 本终端源码副本 | `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/terminal-2` |
| 主仓库（仅证据与 terminal-2.md） | `/Users/huangzhanpeng/python_code/video-paper-wiki` |
| 13 文件基线快照 | `c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39` |
| 853 文件清单 SHA-256 | `daf56597d6800153f8c1099013c95cb22c18ea7ba1d92b32b68041923b954ac8` |
| 副本基线 light_index.py | `3d105819c4af6ec4f1a84ab66ec747dcdb29234f5fd17c491ebc4750f8608b80` |
| 终端 1 ready 实现 SHA-256 | `4d5a8a87f0a6f76e31e1db077e239f98e9b65f9a5b7a685a67f8d781da026be8` |
| Git | 未在副本或主仓库执行 commit/push/merge |

未改公共 `__init__.py` / `contracts.py` / `cli.py` / 配置。`test_light_pipeline.py` 未改。复制的 `light_index.py` 不是本终端交付文件。

## 本终端文件清单

相对源码副本：

| 相对路径 | SHA-256 |
| --- | --- |
| `tests/research/test_light_index.py` | `b80b680e907931c70fd2112627daca11bf8545acd6934adef5a1db9ff3d45b0c` |
| `tests/research/fixtures/r06-legacy-workspace/source.md` | `f985d353c7b2f643e2b2addd76182b3c99641b64814e3001ff43ee34c2266804` |
| `tests/research/fixtures/r06-legacy-workspace/source.json` | `4aab5a9a49b3d8aae1ba252d80c2963d4afa1e7f22960767b409f8452f69a5db` |
| `tests/research/fixtures/r06-legacy-workspace/index.v1.json` | `5d8a185db8177b6dc59ad201ef94f62dab1a0d902b54269377cdd84002f7347f` |
| `tests/research/fixtures/r06-legacy-workspace/provenance.json` | `36c32e09bea20a1a9258d3753c2f0352129f2a228d6d52f1a5c63262c5770a2b` |

四个夹具是共享 `legacy-workspace/` 的哈希核对副本；测试按 `provenance.materialize` 还原到临时工作区，未读取 `source.md`/`source.json` 中的历史 PDF 路径，未再导入 PDF，未手改 Markdown/source.json 使恢复通过。

## 完成内容

1. 将共享旧工作区四文件核对哈希后写入副本夹具目录。
2. 在 `test_light_index.py` 增加恢复回归：物化夹具后调用已发布 `search`/`build_index`，断言 required_fixed_observation（重建前 INDEX_STALE；重建后 quasar 第 1 页、nebula 第 2 页；切片/SHA/锚点对照当前 Markdown；第二次重建字节稳定）。另补多论文后一篇锚点非法时不改写前一篇 source.json 与旧索引。
3. 同一组断言先在**未修改基线** `light_index.py` 上失败，作为历史 red。
4. 终端 1 `ready.json` status=ready 后按 SHA 只复制其 `light_index.py`，不修补。
5. 用同一断言跑恢复回归与六个 `test_light_*.py`。

## 实际测试结果

解释器：`/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`（3.13.13，pytest 9.1.1）  
环境：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` `PYTHONDONTWRITEBYTECODE=1` `UV_OFFLINE=1` `UV_PYTHON_DOWNLOADS=never`  
`PYTHONPATH=<copy>/src`，`UV_CACHE_DIR` 主仓库 `.work/cache/uv-tests`。

**基线 red**（`--basetemp=/private/tmp/vpwiki-t2-r06-red`）：

- 命令：`pytest tests/research/test_light_index.py::test_r06_legacy_misplaced_offsets_recover_from_current_markdown -vv -s`
- 打印：`R06_BEFORE_REBUILD OK [2] NO_RESULTS []`
- 断言失败：`assert 'OK' == 'INDEX_STALE'`
- 结果：1 failed in 0.22s，exit 1
- 与 `provenance.expected_baseline_observation` 一致（quasar 第 2 页，nebula NO_RESULTS）
- 日志：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/terminal-2/evidence/baseline-red.log`

基线其余 `test_light_index.py`（不含恢复回归）：8 passed / 1 deselected in 0.18s。

**候选 green**（复制终端 1 模块后，`--basetemp=/private/tmp/vpwiki-t2-r06-green`）：

- 命令：六个 `tests/research/test_light_*.py`（含新增回归）
- 打印：`R06_BEFORE_REBUILD INDEX_STALE [] INDEX_STALE []`；`R06_AFTER_REBUILD OK [1] OK [2]`
- 结果：**38 passed in 0.27s**，exit 0
- 日志：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/terminal-2/evidence/candidate-green.log`

未跑全量。未使用旧 wheel 缓存或主仓库绝对 import 路径。

## 未完成事项

- 全量回归、SANA、wheel、公共 CLI 集成属终端 3/4。
- 未跑 Python 3.12 / 远程 CI。
- 未 commit/push/merge。
- 共享夹具是两页历史工作区，不是 SANA 或真实用户授权。
- 词法中文检索不是跨语言语义匹配。

## 是否停止写入

是。`stopped_writing: true`。本终端不再改测试、夹具或复制的实现。
