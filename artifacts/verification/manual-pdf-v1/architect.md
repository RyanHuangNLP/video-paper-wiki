# Architect 验证日志

## 2026-09-06 — 终端 4 集成候选独立验证（r02）

状态：**本地工程回归已验证；真实 SANA/Docling 全链路待环境准备**。本次未改实现源码、未 commit/push/merge、未修改真实 Vault。

- 源码：`/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`
- 基线 HEAD：`bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`（未提交候选）
- 终端 4 清单 SHA-256：`1593794b2f8d2bf8e3d4a639e5bb5ca398932bddd6133197091b11a85ec71c51`
- 清单内 54 个文件在测试前后均与交付哈希一致。

### 实际测试

Python 3.13.13 / macOS。R1–R4 修改后的当前版本：

| 执行 | 通过 | 失败/错误 | 说明 |
| --- | --- | --- | --- |
| 首轮全量 | 2170 | 5 failed + 33 setup errors | 本地 AF_UNIX bind 和 uv 缓存访问被工具沙箱拦截 |
| 原样重跑受影响的 38 项 | 38 | 0 | 正常权限审核通过后，仅重跑这些用例；保持离线和相同源码 |

**2208 个不同用例均已取得通过结果。** 这是首轮加定向重试的结果，不是一次全量全绿日志。未重标终端 4 旧的 2207 项结果，也未把此结果称为 CI。

实际 root wheel 在本次离线安装夹具中构建，摘要 `4b55dfb8aeefc5e114ec56ef2f1c21d418c8f13e48c4535f40c3d5120c58378d`。wheel 内 22 个 research 源码/资源与当前清单逐字节对应；源码目录外使用 `python -I` 确认 research、qa、writing 导入来自新安装目录，schema/prompt 存在。运行依赖沿用仓库测试设施的共享锁定环境桥接，未声称完全独立部署环境。

### SANA 实测

输入是用户指定的 Downloads/SANA-Video 2.0 PDF：31 页、34,586,009 字节，SHA-256 `759588574b9b33bff83a6c8c05da1455535498c6cb70992678079242ddaeb23b`。

- 当前集成版本的 `pdf intake` **成功**，生成 staged_input，三项 capture/receipt/published 标志仍为 false。
- 输出仅写入主仓库专用 `.work/research/architect-sana-r02/` 与内容寻址 `.work/blobs/`，没有把原文件移动或改写。
- 独立 pypdf 检查确认 31 页均有可提取文本；已渲染并查看第一页。它不属于 Docling 解析成功证据。
- 实际 `parser profile` 命令返回 **PARSER_RUNTIME_MISSING**。默认环境与 bundled runtime 都没有 Docling/docling-core；检查的默认模型缓存目录不存在。
- 固定依赖为 Docling 2.117.0 / docling-core 2.92.0；本次没有安装它们或下载模型。
- 因此，真实 SANA 的 Docling 解析、发布/索引、模型问答与草稿 **尚未执行**；不能用合成 converter 或 pypdf 抽字代替这条验证。

### 后续条件

终端 4 的合成集成回归已有当前源码的独立通过证据，不要求它重复跑这批测试。下一步优先准备独立 Docling 解析环境及所需模型，然后继续 SANA 完整实测；这一步需要另行确认安装/模型下载范围。Python 3.12、其他平台、远程 CI 和真实人工操作仍未验证。

本次不签发完整产品验收或合并授权。所有测试/渲染进程均已结束。详细命令、首轮失败、重试通过和文件摘要见 [本轮证据](architect/r02/result.json)。


## 2026-09-06 — 改为轻量知识文件，环境修复与 SANA 实测（r04）

用户明确要求控制知识库体积，并同意停止模型下载、改为轻量文本提取。此前 r02 的 Docling 安装计划已被本次方向取代。r03 的依赖安装曾完成，模型下载被终止；本轮新建的 Docling 环境、uv 大型缓存和模型目录现已删除，原 PDF 与共享 `.venv` 保持不变。

### 已完成

- 用已有 pypdf 6.16.2 处理原始 SANA PDF：31/31 页有文本，原始 PDF 摘要保持一致。
- [轻量阅读文件](sana-lightweight/README.md)：分页原文、来源记录、阅读笔记、引用问答和可编辑草稿，总计 117,768 字节（约 115 KiB）。目录仅含 Markdown 和一个小 JSON，不含 PDF、图片或模型。
- 新增可复用的 `tools/lightweight-pdf/extract.py`；它明确使用原生文本与 PDF 文件页码，不伪造 Docling 输出。
- 测试改为项目内可写 uv 缓存、短 `/private/tmp` 路径和 Unix socket 预检。轻量构建缓存约 1.9 MB，隔离构建工具约 1.6 MB；未向共享 `.venv` 安装依赖。
- 在 macOS / Python 3.13.13 上一次完整执行现有集成候选：**2208 passed，186.12 秒，零失败/错误**。这次是真正的一次全量全绿，不是拼接 r02 的重试结果。
- 终端 4 原清单内 54 个文件在本次检查及全量测试后保持原哈希。成功测试产生的本轮临时目录已经清理，文本日志保留。

### 尚未完成的产品实现

当前 `vpwiki-parser` 和原有正式发布流程仍绑定 Docling。此次轻量提取工具和阅读结果没有被冒充成旧产品入口的贯通验收；回答与草稿由当前助手依据实际分页文本整理，未经过原有 QA/import CLI。

已准备 [终端 4 轻量迁移工作包](../../../docs/ai/packets/RESEARCH-WIKI-LIGHTWEIGHT-PDF-MIGRATION.md)，要求将原生文本入口、轻量 Markdown 检索和页码引用接入产品，并用本次 SANA 重放正常入口。Grok 仍由用户手动调度，本次没有自动启动 Grok、子代理或后台定时任务。未修改真实 Vault，未 commit/push/merge，未执行远程 CI。

完整结果与日志：[r04/result.json](architect/r04/result.json)。本轮所有安装、下载和测试进程均已结束。


## 2026-09-06 — 轻量迁移四终端并行任务已准备

根据用户要求提供四个 Grok `/goal` 指令。共同约定与 TERMINAL-1..4 工作包已写入 `docs/ai/packets/lightweight-parallel-v1/`。终端 1 负责原生 PDF 提取，2 负责轻量检索，3 负责引用问答/写作，4 负责公共 CLI、集成和真实贯通。前三个独立源码副本均包含当前未提交候选，已验证每份 842 个文件一致；没有复制模型、虚拟环境、vendor 或 Git 对象。终端 4 留在现有 integration 目录。

接口和文件归属已具体说明，终端 2/3 可以按相同格式独立开发，终端 4 可同时准备 CLI/测试并在 ready 文件齐全后集成。只有终端 4 跑最终全量。各终端继续写统一绝对目录中的 terminal-N.md，交接使用各自 ready.json 和文件摘要。

本次只是准备指令与源码副本，没有调用 Grok、启动代理或执行 Git 操作。基线与工作包摘要见 lightweight-parallel-v1/baseline.json 和 packets.json。


## 2026-09-06 — 四终端轻量实现独立评审（r05）

结论 **REQUEST_CHANGES**，已复现两处问题：P1 重建索引沿用旧偏移，会将原第 1 页内容标成第 2 页并漏检第 2 页；P2 CLI 未按输出目录调整 workspace 相对引用，README 默认用法及已交付 SANA 问答/草稿的来源链接失效。

四个 ready 清单摘要均一致；终端 4 的 13 文件评审快照为 `e2823525133042e790cee821a7cddd280fd9bb3554e78f42bba747c944a5f879`。Architect 独立复跑新增轻量测试 31 项通过，核对终端 4 一次全量 2239 项通过日志；真实 SANA 经当前 CLI 重新提取/检索/导入正常，31 页、文本元数据 113078 字节、索引 281923 字节。既有 wheel 五个新路径相关模块与当前源码字节一致。

此次评审未修改实现，没有调度 Grok 或 Git/远程动作。定向复现使用本轮临时数据，完成后清理；所有源码交付摘要评审后再次一致。详细问题、修复要求、复跑脚本及证据见 [r05/review.md](architect/r05/review.md) 和 [r05/result.json](architect/r05/result.json)。


### 终端 4 r05 修复工作包已准备

根据用户要求已提供手动 `/goal` 工作包 `docs/ai/packets/lightweight-parallel-v1/TERMINAL-4-R05-FIX.md`，SHA-256 `e8a29f9b2039618269a58daaeaa111c0c76d5c74c825766d09c190e672acf646`。它限定修复页偏移重建和输出引用路径，明确 workspace_root/导入兼容行为、六类链接场景和新证据目录。当前 13 文件仍与 r05 评审快照一致。准备工作未启动 Grok、未修改产品代码；下一份候选应交到 `terminal-4/r05-fix/ready.json`，保留上一轮 ready 和 r05 证据。


## 2026-09-06 — r05-fix 复验（Architect r06）

结论 **REQUEST_CHANGES**，仅剩原 R05-1 的已有工作区恢复缺口：旧版实际写入的错误偏移与摘要自洽，新版 `_load_paper` 因而跳过页锚点重定位；显式重建仍错页/漏检。R05-2 的输出链接修复已通过，结论绑定当前 13 文件快照 `c9e486d97c9064826fc7bd43aa250671fea7940fb5c8fca0e9514f89c1f38b39`。

独立 36 项轻量测试通过；4 个新增编辑/多论文失败保留场景通过；核对终端 4 一次全量 2244 项通过。真实 SANA 再次完成提取→索引→导出→导入，16 处来源链接和锚点全部有效，5 个新 wheel 模块与候选字节一致。历史 r05 证据和旧 ready 未改。此次未修改实现、未调度 Grok 或执行 Git/远程操作。详见 [r06/review.md](architect/r06/review.md) 与 [r06/result.json](architect/r06/result.json)。


### R06 剩余修复改为四终端并行

根据用户要求，已准备 `docs/ai/packets/lightweight-r06-parallel-v1/COMMON.md` 和四份终端任务，取代之前单终端 R06 修复安排。终端 1 独占索引实现，2 独占恢复回归/小夹具，3 独立 CLI/SANA/wheel 验证脚本与证据，4 串行集成和一次全量回归。前三个新源码副本各 853 文件/8842203 字节，逐项一致；导入路径已核验，未复制环境、模型、vendor 或 Git 对象。

共享旧工作区夹具由历史 R05 代码实际生成，6631 字节，已验证搬到新临时目录仍能复现错误，无 PDF 副本或旧 wheel 运行依赖。交接证据采用独立 `lightweight-r06-parallel-v1/terminal-N/` 目录，保留旧 r05/r06/r05-fix 等历史。准备过程未调用 Grok、未修改产品代码、未执行 Git；用户可手动同时启动四份任务，终端 4 等待冻结产物后集成。


## 2026-09-06 — 四终端 R06 修复通过本地验收（Architect r07）

决定 `ACCEPTED_R06_REPAIR_AT_EXACT_WORKTREE_SNAPSHOT`，绑定 17 文件快照 `ea67d3b857a23ff721f5a53c8b730c78662e014a8dcac9e78816eda1efaab0dd`。原 R05-1/R06-1 错位恢复与 R05-2 链接问题均关闭；源码与隔离安装 wheel 独立恢复旧工作区通过，38 项轻量测试通过，核对终端 4 一次全量 2246 项通过。真实 SANA 重放 31 页，14 处输出引用路径/页锚点有效。

终端 3 验证脚本的链接检查存在假阳性，已明确排除其结论，改由 Architect 独立按 output.parent 验证；该非阻断脚本问题不在产品运行路径内。此次未改产品源码或执行 Git/Grok/远程操作。详细范围、结论和证据见 [r07/review.md](architect/r07/review.md) 与 [r07/result.json](architect/r07/result.json)。


## 2026-09-06 — 轻量第一版交付收尾四终端任务已准备

用户要求继续四终端手动并行，新的 COMMON 与 TERMINAL-1..4 位于 docs/ai/packets/lightweight-release-parallel-v1/。终端 1 开发完整 href 引用验证器及负例；终端 2 对现有四份 PDF 进行多论文检索、当前会话问答/写作与来源对应性试用；终端 3 独占使用文档草稿和安装入口验证；终端 4 汇总冻结产物、集成两份文档、补缺失验证并准备完整交付清单与 PR/CI 草稿。产品源码和仓库测试保持 R07 候选。

已准备四个独立输出目录，仅复制 12154 字节 README 草稿，无源码/PDF/模型/环境复制。857 个来源文件、413 个产品测试构建输入、四份原 PDF 和旧 R06/R07 证据准备后均未变。源码和已有隔离 wheel 的 python -m video_paper_wiki_research --help 均实际通过；任务包明确不使用不会执行 main 的 cli 子模块。Repo Steward 只读确认 integration 为真实 linked worktree，bcff631 上有 69 个未交付候选路径；R07 的 17 路径不能充当完整交付清单，历史 PR base 未当作当前远程观察。

五份任务包获独立 GO，交接包含失败状态和有界等待。未启动 Grok、未执行 Git 写操作或远程动作。四份手动 /goal 完成后先交 Architect review，Git/PR/CI 继续由 Repo Steward 串行处理。准备记录见 lightweight-release-parallel-v1/preparation.json。


## 2026-09-06 — 轻量第一版收尾评审 r08：需要修正交接

本轮决定 CHANGES_REQUIRED_FOR_LIGHTWEIGHT_RELEASE_HANDOFF，18 文件评审快照 b8b644b0fed9fd0d116a8a427625d468558e3c949fd73258a01d3783a3843569。产品源码/测试保持 R07；发现验证器混合好坏来源链接三类漏检、integration quickstart 未定义 CLI 且 T3 标量修稿在默认 zsh 仍失败，以及 T4 引用的 T3 ready/文档修订过期。保留所有终端材料和历史证据，未修改实现/文档，未启动 Grok 或执行 Git 写/远程动作。

独立 15 项验证器现有测试通过；新 wheel 186 个包文件与源码/安装逐字节一致；四论文 104 页、8 份 export 重放和 15 条 claim 来源身份通过；实际七份输出的 13+5 个唯一来源目标通过。70 路径完整交付清单匹配，但需上述修正后的新冻结交接；3.12/远程 CI 仍未跑。不重复历史 2246 项全量。详见 architect/r08/review.md 与 result.json。


## R08 targeted fix: four manual terminals prepared

Prepared `docs/ai/packets/lightweight-r08-fix-parallel-v1/COMMON.md` and TERMINAL-1..4.md following the user’s next-action request. T1 owns the local citation verifier; T2 independent red/green regressions; T3 actual Bash/zsh quickstart commands; T4 receives frozen inputs and integrates only the quickstart. Independent Luna packet review: GO. Preparation record SHA-256: `cac7527bc61dfa0a58c4c7facc65b92e133cbd7f4ea7d2aa50579632f711b19b`. Verified 858 source paths, all 70 candidate paths, the current 18-file review scope and 188 protected historical files unchanged. Seed copies total 32,185 bytes; no source, PDF or environment copies. Reuse the verified existing program wheel; documentation remains separately hashed. No Grok process, Git mutation, remote CI or release acceptance was performed. The four manual goals are ready for the user; T4 concludes with a new Architect review handoff.


## R09 local acceptance of the four-terminal R08 fixes

Decision `ACCEPTED_R08_FIX_LOCAL_CANDIDATE_PENDING_EXACT_COMMIT_AND_CI`; record SHA-256 `3eb74d7678ab6be87a225f8f7b6173a32426ec1b4f526cbf7e6a8c7f80b7024b`. Exact 70-path mapping `bb64af4cc4152a21c2c5d20ecf33441b9bcb30ce7198ae1ccdb2a466d06f5d03`; quickstart `0c66d84539417e7d902925f1144e558b54fe481b79fd8b77258e562a9c74910e`. Original verifier red/green, 19+7 independent regression checks, literal Bash/zsh final-document replay and 12-output/24-target evidence checks passed. Frozen handoffs, 188 historical files and product bytes are intact. Proceed to serialized Repo Steward delivery under a separate exact-scope instruction; fresh commit/CI and exact-head acceptance remain.


## R09 exact-head delivery accepted after fresh four-matrix CI

Decision `ACCEPTED_MANUAL_PDF_LIGHTWEIGHT_WORKFLOW_AT_EXACT_HEAD` at commit `0fcae592acb977c6b422e7de3b2c3e0cf79df5a0`, tree `d2d592f25d2361d5cbcc3bf58ca441a2824c256b`; acceptance record SHA-256 `f041db80287d51204f5a929b550c0e4d8b93ad4c4986906f2c3c8de90432de03`. Draft PR #95 targets integration base `08709894adfb20ec07e976783f0ba436d975b74f`; fresh Tests run 34046551184 attempt 1 passed 2246 tests in each of four jobs. Actual checkout `6931e1a8f57ec4b0f22d004b92e9842e3bf48908` has exact base/head parents and a tree equal to the candidate. Root independently verified raw logs, remote metadata and committed/final source bytes. PR remains draft and unmerged; no human gate was closed. See r09/completion.md for delivery and next steps.


## Lightweight workflow v2 — four Cursor lanes overall review

Decision: CHANGES_REQUIRED_AND_INTEGRATION_INCOMPLETE. Current review entry is `lightweight-workflow-v2/architect-overall-r1/CURRENT.md`; immutable result SHA-256 is `d793552ec063ac20942aee48f424fdb03c1cec65fc5474a4a36563c26ac13120`.

T1 r2 has confirmed recovery/content/transaction-path findings and portable-test correction. T3 actual workflow passed 37 local directed tests but independent probes reject path/temporary ownership, pre-publication freshness, and request validation; no formal final handoff exists. T4 remains incomplete. T2 published r3 during this review: handoff/ready SHA `802b5d787e4e75db654ec236d6e4b326e1dc8d487fd1eeb2ece9bbd86bfcb7fd`, five-file bytes match, 55 directed tests and prior repair probes pass. Those three prior groups are closed. A separate malformed-source decoding/after-stage cleanup issue remains for a narrow T2 r4. Current T2 instructions are AGENT-2-R4-CONTINUE.md, superseding the earlier same-review r2-only continuation. All other lane input hashes were rechecked unchanged. Detailed ownership qualification is in CURRENT.md.

Four original Cursor Grok 4.6 workstreams may continue within their original 25-path contract using the prepared current instructions. No model session was dispatched, no product source changed, and no Git/remote CI/merge operation occurred in this review. Earlier 2246-test exact-head acceptance stays historical and unchanged.
