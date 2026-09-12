# 终端 4：修复 r05 评审的两处问题

本包由 Architect 根据用户“提供终端4的修复/goal命令”制定，供用户在现有 Grok 会话手动执行。它接续已完成的四终端实现，取代 TERMINAL-4.md 的旧等待/复制阶段。无需重新等待终端 1–3，无需新一轮架构审批。仅修复下述两个问题及其回归，不扩展功能。

## 工作目录与输入

唯一实现目录：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`。保留其中未提交候选，不从终端 1–3 旧副本覆盖代码。原来的八小时自动调度已取消，继续按用户手动任务执行；不要启动其他代理或 Grok 进程，不切换当前模型设置，不执行 Git 操作。

先读主仓库 `/Users/huangzhanpeng/python_code/video-paper-wiki` 中的以下文件；历史流程与本次修复范围冲突时，以本包和用户最新指令为准：

- `AGENTS.md`、`docs/ai/task-index.yaml`、`docs/ai/codex-team.md`。
- `docs/ai/packets/lightweight-parallel-v1/COMMON.md`。
- `artifacts/verification/manual-pdf-v1/architect/r05/review.md`。
- 同一 r05 目录中的 `candidate-check.json`、两份 reproduction JSON 和 `reproduce_rebuild.py` / `reproduce_links.py`。

修改前核对 candidate-check.json 的 `reviewed_files`，共 13 文件；评审快照摘要为 `e2823525133042e790cee821a7cddd280fd9bb3554e78f42bba747c944a5f879`。这是未提交源码快照，不能用 HEAD 代替。若发现已有后续改动，记录差异并在现状上核对是否仍需修复，不回滚他人修改或将旧证据标为新结果。

## 允许修改

实现路径仅限 integration 下：

- `src/video_paper_wiki_research/light_index.py`
- `src/video_paper_wiki_research/cli.py`
- 确有渲染需要时，`src/video_paper_wiki_research/light_qa.py`、`light_writing.py`
- `tests/research/test_light_index.py`、`test_light_pipeline.py`、`test_light_cli.py`、`test_light_qa.py`、`test_light_writing.py`、`light_real_demo.py`
- `README.md`

保留 light_pdf 原生提取实现、现有依赖、67 条目录、旧命令行为及无关模块。沿用 COMMON 的公开函数调用方式和 evidence 身份字段；本包明确授权下面的兼容性增量。实现内部算法及小型辅助函数由你决定，不必逐项请示。

## R05-1：准确重建分页定位

目前 `_refresh_document_digest` 用旧偏移切片后只刷新摘要。页锚点前插入 77 个字符，会把原第 1 页 quasar 标成第 2 页，并漏掉原第 2 页 nebula。两页原文仍然存在，不能把“哈希一致”当作页码正确。

对于保留明确页锚点/页标题结构的 Markdown 编辑，重建应重新确定每页正文的 Unicode 码点区间，更新切片摘要和 document 摘要，再生成索引。页头不能进入正文 chunk，chunk 不能跨页。原始 PDF 的身份和摘要不变；用户编辑不能被声称为重新提取过的原 PDF 原文。

若锚点缺失、重复、顺序异常或无法确定页归属，返回明确失败和重新提取提示，不输出假成功，不把错误定位写入 source.json。验证失败前保留原 source.json 和索引内容；不要先改一部分来源记录，再在后续验证中失败。

测试至少覆盖：文档前加导言；第 1 页正文内插入和删除文字；缺失/重复页锚点；旧索引返回 INDEX_STALE；合法重建后原页术语仍在正确页可检索，切片与摘要相符。页锚点正常的两页 quasar/nebula 复现必须从“错页/漏检”变为正确结果。保留既有 EOF 追加、长页分块、中文检索及空结果用例。

## R05-2：输出位置正确的来源链接

CLI 导出上下文时已知道 workspace；渲染后却把相对 workspace 的 `papers/...` 原样写到任意输出目录。修复必须覆盖 README 的默认位置、context 同目录默认输出、workspace/notes 子目录和本轮实际交付目录。

本包授权并固定以下小幅兼容性增量：

1. 新轻量 CLI `qa export` / `writing export` 在成功的 light-context.v1 顶层添加 `workspace_root`，值为实际 workspace 的绝对路径。COMMON 既有字段和 evidence 保持原含义；纯 Python 导出/渲染函数原有调用继续可用。
2. 为轻量 `qa import` / `writing import` 添加可选 `--workspace`。未提供时使用上下文的 workspace_root；两者都有且解析后不一致时明确报错。早期轻量上下文缺少 workspace_root 时，可显式传 --workspace，或者提示重新导出；两者都缺失时不得猜测 cwd/context.parent，更不能写出无法确定来源根的成功文档。
3. 旧 schema 的 import 保持既有调用行为，不因缺少新字段失败。新 --workspace 只供轻量 import 使用；旧模式误传时明确说明不适用。
4. 在最终落盘时按 output.parent 生成正确相对路径，或采用等效的明确可解析链接。context/evidence 的 markdown_path 仍相对 workspace，不得为了渲染而改写引用身份或削弱联合匹配检查。CLI 返回的 markdown 与实际落盘内容一致。支持目录中的空格；来源路径必须实际位于所声明 workspace，目标文件和页锚点应可验证。

QA 与 writing 均增加上述输出位置的测试，检查实际解析的文件和锚点存在，不只断言字符串含 `#page-N`。覆盖早期轻量上下文加显式 --workspace 的兼容用法、缺失根的明确失败及旧模式不受影响。

## 验证与轻量环境

先用新回归用例确认修复，再运行六个 `test_light_*.py` 测试文件。Architect 原 reproduce 脚本是“断言旧 bug 存在”的历史证据，修复后不应以其退出 0 为验收条件；保留原脚本和原 JSON，另写正向修复测试/结果。

使用原始 SANA：`/Users/huangzhanpeng/Downloads/SANA-Video 2.0- Hybrid Linear Attention with Attention Residuals for Efficient Video Generation.pdf`，31 页，SHA-256 `759588574b9b33bff83a6c8c05da1455535498c6cb70992678079242ddaeb23b`。使用新工作区 `integration/.work/light-sana-r05-fix/`，完整执行当前 CLI 的 pdf add → index build → QA/writing export → 当前会话回答/草稿 → import。可核对上一轮模型回答后沿用仍匹配的事实，但必须针对新导出 evidence 生成有效引用，不能复制旧 Markdown 充当新导入结果。

本轮证据统一放主仓库绝对目录：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-parallel-v1/terminal-4/r05-fix/`。问答和草稿输出到该目录的 sana/ 子目录，并验证从最终交付文件点击路径可到达真实来源及页锚点。保留历史 sana 文件，新的交付替代旧文件使用，不覆盖历史证据。

报告提取覆盖、原 PDF 摘要、实际链接检查、文本/元数据/索引大小；SANA 文本与元数据小于 1 MiB，索引小于 5 MiB。新知识工作区不复制 PDF/图片，不下载模型、不安装重依赖，不改真实 Vault、不运行 vpwiki-admin。

共享解释器 `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 只读使用。沿用 COMMON 和主仓库 tools/lightweight-pdf/README.md 的离线缓存与短临时目录配置。修复稳定后构建一次新 wheel，用现有隔离验证方式在源码目录之外运行正常入口，并验证已安装相关模块与本次源码哈希一致，不复用修复前的 wheel 结论。最后通过主仓库 tools/lightweight-pdf/test.py 在新的 r05-fix/full-suite/ 证据目录跑一次完整回归；记录实际数量，以修复前 2239 项为基线，加上新增用例。失败时只修具体问题并按必要范围复测，保留每次原始结果，最终仍需一次完整全绿结果。

## 交付并停止

向主仓库 `artifacts/verification/manual-pdf-v1/terminal-4.md` 追加简报，写清两项修复、命令/结果、实际模型、真实样本、wheel、全量及未跑项。不要声称已经通过 Architect 验收。

在 `terminal-4/r05-fix/ready.json` 原子写入新就绪记录，包含 status=ready、source_root、工作包摘要、r05 评审基线、修复说明、当前全部 13 个既有候选文件的路径/SHA-256（加上任何获准新增路径）、本轮实际改动路径、测试/样本/wheel证据和 known_gaps。原 `terminal-4/ready.json` 与 Architect r05/ 记录保持不变。

两项修复及必要验证完成后停止写入，交 Architect review。不要提交、推送、合并、自批验收或自动启动下一轮任务。
