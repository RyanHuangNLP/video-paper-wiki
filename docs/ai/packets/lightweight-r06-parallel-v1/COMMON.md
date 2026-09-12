# R06 剩余修复：四终端共同约定

用户明确要求四终端并行。本包取代 `lightweight-parallel-v1/TERMINAL-4-R06-FIX.md` 的单终端分工，保留其修复语义；不启动已取消的自动调度。用户手动启动四个 Grok 会话，不再派其他代理，不执行 Git，不改变模型或环境。

## 目录、基线与所有权

Architect 已从当前 integration 准备三个独立源码副本，各 853 个文件、8,842,203 字节，逐文件验证一致；未复制模型、环境、vendor 或 Git 对象。

| 终端 | 工作目录 | 独占交付 |
|---|---|---|
| 1 | `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/terminal-1` | light_index.py 实现 |
| 2 | `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/terminal-2` | 索引/贯通回归和小型旧工作区夹具 |
| 3 | `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/terminal-3` | 独立 CLI/SANA/wheel 验证脚本与证据，无产品修改 |
| 4 | `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration` | 串行集成、最终检查和一次全量回归 |

前三个为源码副本；`.git/grok-worktree-source` 仅供已有测试定位只读共享资源，不是真实 Git worktree。不要在旧 lightweight-v1 副本或主仓库实现目录中开发。

基线 13 文件快照：`c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39`。完整 853 文件清单在主仓库 `artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/baseline.json`。核对后再修改；不覆盖任何未知后续变化。

先读主仓库 `/Users/huangzhanpeng/python_code/video-paper-wiki` 下 AGENTS.md、docs/ai/task-index.yaml、docs/ai/codex-team.md、`artifacts/verification/manual-pdf-v1/architect/r06/review.md` 和本终端工作包。COMMON 的公开数据格式仍见 `docs/ai/packets/lightweight-parallel-v1/COMMON.md`。历史职责与本轮冲突时按本轮文件归属执行。

## 唯一修复目标

旧 R05 会同时写入错位偏移和自洽的新摘要。当前代码只核验摘要就跳过页锚点验证；升级后 index build 仍保留错页/漏检。

读取与重建需对照当前 Markdown 的页锚点、页标题、完整页集合和正文区间，不能只信任旧摘要。遇到自洽但错位的旧记录，search 返回 INDEX_STALE；页结构有效时，直接 build_index 修复，使 quasar 在第 1 页、nebula 在第 2 页，无需再次编辑或导入 PDF。再次重建稳定。页结构不合法时明确拒绝，验证失败不得改写任一 source.json 或旧索引。

保留原 PDF 身份/摘要、Unicode 码点偏移、正文切片摘要、chunk 不跨页、状态语义和既有接口。用户编辑不代表重新提取 PDF。已通过的 CLI/问答/写作/链接修复保持不变，不加新功能或重依赖，不改 67 条目录、真实 Vault 或历史证据。

## 共享旧工作区夹具

主仓库 `artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/legacy-workspace/` 有 source.md、source.json、index.v1.json、provenance.json，共约 6.6 KB。它由已核验 SHA 的旧 R05 wheel 真正执行提取、编辑和重建产生，没有手写伪造索引，也没有复制 PDF。provenance 记录源代码摘要、文件摘要和还原布局。

根据 provenance.materialize 将三个数据文件复制到自己的临时 `.work` 工作区即可复现，不能原地修改共享夹具。source.md 中的原 PDF 路径是已清理的临时测试来源，测试不应尝试读取该路径；它不是 SANA/真实用户数据授权。终端 2 将小夹具带入回归测试后，测试不得依赖主机绝对路径、旧 wheel 缓存或旧生产模块。

## 交接和依赖

证据统一根目录为主仓库绝对路径：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r06-parallel-v1/`。各自仅写 terminal-N/ 子目录，并追加主仓库 `artifacts/verification/manual-pdf-v1/terminal-N.md`。

四个终端可以同时开始。终端 1 先实现，不等待终端 2 的测试；终端 2 先写能捕获当前缺陷的回归；终端 3 先准备参数化验证脚本；终端 4 先核验范围、准备集成与测试命令。终端 1 写出 ready 后停止修改 light_index.py；终端 2/3 核对它的 SHA，仅复制该模块到自己副本并运行验证，不修改复制的实现。

成功交接时原子写 terminal-N/ready.json：status=ready、source_root、工作包 SHA、基线快照、files（待集成的相对路径与 SHA）、artifacts（脚本/证据绝对路径与 SHA）、tests、known_gaps、stopped_writing=true。终端 2/3 还记录所验证的终端 1 模块 SHA；终端 3 files 可以为空，验证脚本放 artifacts。

若候选仍有问题，保留失败证据，写 terminal-N/handoff.json，status=needs_fix、stopped_writing=true，并列出冻结的测试/脚本摘要和具体失败；不能谎报 ready。终端 4 可接收这些已停止写入的产物，在 integration 内修复同一契约范围内的问题并重验，不必等待一份永远不会出现的成功记录。任何新实现 SHA 都需重跑受影响验证。

终端 4 只按交接白名单复制实现、测试和小夹具；不复制整树。终端 1–3 停止写入后，集成文件所有权交给终端 4。终端 4 完成最终验证后也停止写入，交 Architect review。依赖尚未齐时约每 60 秒检查一次交接文件，不反复跑测试或刷屏。

## 环境和最终交付

共享解释器只读使用 `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`。测试从各自源码根启动，确保导入来自该副本 src；`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`UV_OFFLINE=1`、`UV_PYTHON_DOWNLOADS=never`，uv 缓存沿用主仓库 `.work/cache/uv-tests`。使用 `/private/tmp` 短临时目录和临时 pytest cache，不修改共享环境。

只有终端 4 跑最终一次全量，使用主仓库 tools/lightweight-pdf/test.py 和新的 terminal-4/full-suite/ 证据目录；当前基线为 2244 项，加新增回归，记录实际数量。终端 1–3 仅跑定向/轻量验证。

SANA 原 PDF、31 页及体积约束沿用原 COMMON；真实验证不复制 PDF/图片到知识目录，不下载模型。旧回答 JSON 仅在新 evidence 完全一致时可重放，否则生成新的匹配引用；不能复制旧 Markdown 冒充 import。源码测试、wheel、模型内容和 CI 证据如实区分，不自批验收、不 commit/push/merge。
