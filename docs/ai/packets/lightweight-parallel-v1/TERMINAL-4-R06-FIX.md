# 终端 4：补齐旧工作区的分页恢复

这是 r06 复验后唯一剩余修复包。用户在现有 Grok 会话手动执行；不启动新代理、Grok 进程或自动循环，不执行 Git，不改变模型或环境。

## 当前候选与范围

唯一实现目录：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`。继续当前未提交候选，不覆盖旧副本、不重新等待终端 1–3。

先读主仓库 `/Users/huangzhanpeng/python_code/video-paper-wiki` 下的 AGENTS.md、docs/ai/task-index.yaml、docs/ai/codex-team.md、本目录 COMMON.md，以及 `artifacts/verification/manual-pdf-v1/architect/r06/review.md`、`candidate-check.json`、`existing-workspace-reproduction.json`、`check_existing_workspace.py`。历史八小时调度和旧终端等待阶段已结束，本包继续用户手动开发安排。

基线为 r06 评审的 13 文件路径/摘要映射，快照 `c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39`。开始前核对 candidate-check.json 的 reviewed_files；它包含未提交源码，不能以 HEAD 代替。若已存在后续改动，记录差异并保留它们，不回滚他人工作。

只允许修改：

- `src/video_paper_wiki_research/light_index.py`
- `tests/research/test_light_index.py`
- 必要时 `tests/research/test_light_pipeline.py`

CLI、QA/writing、PDF 提取、README、依赖与其他文件保持当前候选。当前 R05-2 引用路径修复已通过，不要重写。保留 COMMON 的公开接口、evidence 字段和状态语义。此包直接授权下述修复，无需新增架构评审。

## 修复要求

旧 R05 实现实际会把错误偏移与新 document/text 摘要一起写入 source.json。当前 `_load_paper` 在 194–198 行看到摘要自洽便直接信任 `_stored_pages`，跳过锚点定位。因此旧工作区升级后，显式 index build 仍可能把 quasar 标为第 2 页、漏检 nebula。

不要仅凭 document 或切片摘要判断分页范围正确。读取与重建应对照当前 Markdown 页锚点和页标题核验页号、正文起止区间与完整页集合；对摘要自洽、位置却与页结构不一致的旧记录，search 应返回 INDEX_STALE。页结构有效时，显式 build_index 必须重算并修复定位、摘要和索引，使查询恢复正确页码。不能依赖用户再次修改 Markdown 或重新导入 PDF 来触发修复。

保留原 PDF 身份及摘要，不将用户编辑声称为重新提取过的 PDF 原文。页结构不合法时明确拒绝并提示重新提取，验证失败不得改写任何来源记录或旧索引。已经正确的工作区应保持稳定，不因检查而每次改变 index_id 或无意义改写文件。

## 回归与验证

新增“升级既有错误工作区”的正向回归。夹具必须包含旧 R05 产生的自洽但错位的 source.json 和索引，而不只是先修改 Markdown、保留旧 document 摘要。可参考 Architect 脚本使用真实旧 wheel 生成该状态；持久测试应携带小型、来源清楚的夹具或构造步骤，不依赖开发机 `.work/wheel-prefix` 长期存在，也不要复制整份旧生产模块进入产品。

回归必须断言：

1. 旧记录的 document 摘要和各旧切片摘要确实匹配当前 Markdown，能覆盖原来的错误快速路径。
2. 新版直接读取该旧工作区时识别 INDEX_STALE，不返回错误引用。
3. 不再修改原文，直接重建后 quasar 为第 1 页、nebula 为第 2 页；偏移、摘要、页锚点和正文一致，页头不进入正文，chunk 不跨页。
4. 再次重建稳定；缺失/重复/乱序页锚点继续拒绝，多论文工作区遇到无效来源时仍不提前改写其他记录。

Architect r06/check_existing_workspace.py 断言的是旧缺陷，保留它和历史 JSON，不以其退出 0 为新版本通过标准。新回归应在修复前捕获问题、修复后通过。

先跑上述定向回归与六个 test_light_*.py。然后重放真实 SANA 的索引、查询和 QA/writing 正常入口，确认已通过的引用链接仍有效；原始 PDF、页数和轻量体积约束沿用 COMMON。复用此前有效的提取工作区是允许的，不必重复生成整套模型回答；模型 JSON 只有在新导出 evidence 与原输入完全一致时才可直接重放，否则重新生成匹配的引用。用于验证编辑和旧错误记录的操作只在自有临时夹具进行，不损坏已交付 SANA 工作区。

修复稳定后，使用既有轻量缓存构建新 wheel，在源码目录外验证所安装 light_index 与候选字节一致并运行新版重建/检索。最后通过主仓库 tools/lightweight-pdf/test.py 跑一次完整回归，以 2244 项加新增回归为预期基线，记录实际数量。使用共享只读 `.venv`、离线配置和 `/private/tmp` 短目录；不要安装重依赖或下载模型。失败时保留日志，针对问题修复与复测，最终保留一次完整全绿结果。

## 新证据与交接

本轮证据目录为主仓库绝对路径：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-parallel-v1/terminal-4/r06-fix/`。

向主仓库 `artifacts/verification/manual-pdf-v1/terminal-4.md` 追加简报。最终原子写入 `terminal-4/r06-fix/ready.json`，包含 status=ready、source_root、工作包路径及 SHA-256、r06 基线快照、13 个候选文件的当前路径/摘要、实际改动路径、旧工作区恢复证据、定向/轻量/SANA/wheel/全量结果及未跑项。测试期间源码冻结，结束前再次核对摘要。

保留 terminal-4 原 ready、r05-fix 全目录、Architect r05/r06 证据和已有 SANA 文件。完成后停止实现写入，交 Architect 复验；不要自批验收、提交、推送、合并或启动下一轮任务。
