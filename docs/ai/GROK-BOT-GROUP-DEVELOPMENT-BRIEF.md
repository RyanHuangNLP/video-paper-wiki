# Video Paper Wiki：Grok Bot 群开发任务书

版本：2026-09-13。用途：直接交给群里的各个 bot，作为后续开发的共同指令。
本文规定任务分工和交付方式，不是 Herdr 安装或配置教程。

## 1. 总目标

完成 Video Paper Wiki 第一版完整可用的研究知识库：论文整理、带引用问答、论文与代码关联、
严谨比较、完整技术文章、复现计划、Obsidian 阅读以及备份恢复。

剩余范围以 [剩余开发计划](remaining-development-plan-2026-09-13.md) 为准：
CODE、DOMAIN、SYNTHESIS、QUALITY、PRODUCT 五块，12 个工作包和最终集成验收。
已有的基础阅读、问答、论文维护、长文分批整理、提纲/章节修订、来源目录和论文发现继续复用。

## 2. 固定分工

群里的 bot 是交接入口；实际仓库操作交给 Herdr 中已有的对应 Agent。
本项目采用以下明确分工，优先于通用的“按特长任意选人”建议和旧的 Luna/Cursor 编排方式。

| 群内角色 | 对应执行负责人 | 职责与交付物 |
| --- | --- | --- |
| ChatGPT：设计与验收 | Herdr 中的 Codex Agent | 分析需求、设计方案、拆分任务、明确接口/修改范围/验收标准；决定派发、返修和完成；审核真实 diff、测试及质量 |
| Grok：开发 | Herdr 中的 Grok Agent | 全部生产代码、测试代码、脚本、schema、CI 配置代码和修复；运行自测，提交开发简报，交付后停止写入 |
| agy：仓库交付 | Herdr 中的 agy Agent | clone/fetch、分支/worktree、候选 commit、push、Issue/PR、CI 观察和交付记录；按审核结论组织返修和交付 |
| Grok Bot：转交 | 使用上述已分配 Agent | 转发任务书、等待结果、按状态交回下一负责人；群内只给简短状态和结果入口 |

ChatGPT 可以运行已有测试和检查命令来验收，可以编写设计与任务文档。
需要新增测试代码、修生产代码、改 CI YAML 或解决涉及代码语义的冲突时，交给 Grok。
agy 可以执行已确认的 Git 集成操作，不自行决定代码冲突的业务含义，也不代替 ChatGPT 签发质量结论。

Grok Bot 的“分派”是转发 ChatGPT 已明确的任务，不自行再做一遍设计、编码或代码审查。
所有角色只使用现有 Agent，不为本任务安装、增加或静默替换执行工具。

## 3. 单一负责人、等待与额度规则

1. 同一完整任务只给一个负责人；不同时把同一道题发给多个 Agent 各做一遍。
2. Grok 开发与 ChatGPT 验收是先后发生的不同职责，不是两份重复实现。
3. 负责人对某个事实或技术判断不确定时，只把这个具体判断交给另一 Agent，附已有证据和待核实问题。
4. 能按职责和文件范围拆开的不同子任务才并行。存在接口依赖时先等待上游结果；共享文件同一时刻只有一个写者。
5. Agent 正在工作时，不因为暂时没有回复就重新派一份。先等完成、明确阻塞或失败，再决定下一步。
6. 卡住时说明原因、已完成内容、剩余内容和断点。接手前确认原负责人停止写入，并交接同一任务的确切版本。
7. 额度用于决定是否继续当前会话、换同角色可用会话或等待恢复，不自动改变三方职责。跨角色代写代码需要用户调整分工。
8. 额度不可读时记录未知，不根据印象编造剩余额度。只在派发或额度错误时检查，避免频繁轮询。
9. 默认复用同一任务的已有会话。只有新任务或明确需要隔离时才创建新会话。
10. 原有权限和审核要求保留；权限、登录或配额拒绝不能通过换入口绕过。

## 4. 每个任务的交接顺序

```text
ChatGPT 制定任务和验收条件
  → agy 准备指定代码基线与任务分支
  → Grok 实现、自测、报告并停止写入
  → agy 将候选保存为准确 commit，核对范围
  → ChatGPT 审核该 commit 与测试结果
      ├─ 需要修改：同一任务交回 Grok，再产生新候选
      └─ 本地通过：交 agy 做获准的 push、draft PR 和 CI
  → ChatGPT 核对最终 head、PR base 与 CI，确认交付状态
```

Herdr 或 bot 显示 done、进程退出成功、测试通过、PR 已创建，各自只说明对应步骤的结果。
任务完成由 ChatGPT 根据约定的功能和验收证据判断。审核期间候选源码保持不变。
任何新的源码 commit 都需要核对新版本，不复用旧 head 的通过结论。

默认交付为 draft PR → `integration`。不自动合并、不写 `main`、不关闭真实用户或操作员验收项。

## 5. 仓库和开发基线

- 仓库：<https://github.com/RyanHuangNLP/video-paper-wiki>
- 最新已知产品开发基线：`codex/code-proof-v1`
- 对应 commit：`d440c7aaebb4dcc2c52cab719b0d73347a41493f`
- 本地材料快照：`b86bb0250df340e6ae0f01dada1252afdfc2907c`
- 该快照位于 `repair/vpkb000-plan-approval-prepare-follow2`，包含大量历史文档，但产品源码较旧。

**新开发使用包含 d440c7a 和本次启动文档的 `origin/codex/code-proof-v1` HEAD。不得拿 b86bb02 的旧产品文件覆盖最新实现，也不得因为新分支找不到而退回 main 开发。**

本次交付将任务书、剩余计划、合同及首包所需历史证据放进同一个开发分支；
无需另取聊天附件。agy 按下面的命令核对远程 HEAD，记录其完整 SHA。
材料范围与历史路径的映射见 [云端交接说明](CLOUD-BOOT-01-HANDOFF.md)。

## 6. 第一个交付准备任务：BOOT-01，负责人 agy

目标：让其他 Agent 能取得同一份最新源码、剩余计划和当前任务书。

1. 在有最新提交的仓库中确认 `d440c7a` 完整存在，记录源仓库和 commit。
2. 把需要的计划、当前任务书和本包合同放入基于最新源码的开发交付分支；只转移明确选定的文档，不整包合并旧源码快照。
3. 由 ChatGPT 核对源码基线和文档范围，明确本项目采用本文的新角色规则；旧记录作为历史保留。
4. 按现有用户授权发布开发基线与必要文档。若公开推送范围尚未授权，提交确切的待发布范围，等待该项授权；先完成其余本地准备。
5. 核对远程 ref、源码 commit 和文档确实可读取，返回可克隆分支及 HEAD。保留原始 d440c7a 作为可核对的产品基线。
6. 如果当前环境只有远程仓库而没有 d440c7a，报告“等待持有本地开发提交的环境交付”，不要重新实现已完成的代码。

BOOT-01 只处理交付准备，不重做产品实现。远程已有更晚的合法开发提交时，由 ChatGPT 核对后指定实际基线。

## 7. 如何克隆并开始任务

以下 Git 操作由 agy 在工作环境执行。已有项目目录先核对，不在脏工作区直接切分支。

```bash
git clone --branch codex/code-proof-v1 https://github.com/RyanHuangNLP/video-paper-wiki.git
cd video-paper-wiki
git fetch origin
git branch -r
```

BOOT-01 确认最新开发基线已发布后，验证对象存在并创建首包分支：

```bash
git cat-file -e 'd440c7aaebb4dcc2c52cab719b0d73347a41493f^{commit}'
git merge-base --is-ancestor d440c7aaebb4dcc2c52cab719b0d73347a41493f origin/codex/code-proof-v1
git switch -c codex/c1-code-proof-io origin/codex/code-proof-v1
git submodule update --init --checkout vendor/claude-obsidian
git rev-parse HEAD
git -C vendor/claude-obsidian rev-parse HEAD
```

本次启动文档位于 d440c7a 之后的提交，因此不要切回仅含产品基线的 d440c7a 而丢失文档。
记录创建任务分支时的完整 HEAD；分支已经存在时核对并复用，不执行强制重置。
固定上游应为 `9f8c1199047eac2c3828496279fbb7ba9540b90b`；缺失提交或核对不一致时停止该步骤并报告。

Grok 在任务分支中准备默认锁定环境：

```bash
uv sync --locked
uv run --offline --no-sync vpwiki doctor
```

使用默认依赖，不加入 Docling extras、OCR、embedding 或模型权重下载。
首次核对环境与基线后，按当前任务跑相关测试；需要交付时完成对应的回归和安装包检查。
标准测试临时目录写法：

```bash
VPKB_TASK_TMP="$(mktemp -d /tmp/vp.XXXXXX)"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --offline --no-sync python -m pytest -q \
  --basetemp "$VPKB_TASK_TMP/p" -o cache_dir="$VPKB_TASK_TMP/cache"
```

上面的 pytest 命令是完整测试写法；开发中可追加 ChatGPT 指定的测试路径做相关检查。
ChatGPT 验收按风险复核必要测试，不让多个 Agent 无理由重复相同全量运行。

## 8. 首个开发任务：C1，负责人 Grok

### 目标

完成代码证据流程的 retained I/O 层，使后续公开操作能够安全读取输入、保存产物和恢复失败。

### 开始前由 ChatGPT 完成

- 阅读剩余计划、当前源码、最新 C1 合同和已知失败记录。
- 明确本次允许文件、接口、错误行为、测试要求与停止条件。
- 区分已接受的资源基础/Git 内核/配置内核，以及尚未落库的 I/O 返回产物。
- 下发一个 C1 任务，不同时启动依赖 C1 的 C2 实现。

### 输入材料

以下路径相对项目根目录，需由 BOOT-01 确保可读取：

- `docs/ai/remaining-development-plan-2026-09-13.md`
- `docs/ai/packets/full-todo-v1/CODE-PROOF-PUBLIC-IMPLEMENTATION-SEQUENCE-R1.md`
- `docs/ai/packets/full-todo-v1/CODE-PROOF-IO-production-freeze-r2.json`
- `docs/ai/packets/full-todo-v1/GROK-CODE-PROOF-IO-PRODUCTION-R2.md`
- 上述文件引用的 retained-I/O 定义及 R13–R18 补充约束。
- `artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/io-r1/independent-returned-production-review-r1.json`
- 同目录 `independent-returned-production-review-supplement-r2.json`。

缺少输入时列出缺件，由 agy 补交；不凭旧聊天或猜测补造合同。

### 实现范围

由 ChatGPT 在现有合同之上明确本次修改清单，主要目标包括：

- `src/video_paper_wiki/code_proof_io.py`
- `tests/unit/test_code_proof_io.py`
- 该包实际需要且明确授权的相关测试。

处理保留文件/目录身份、锁、资源校验、固定输出槽、原子安装、重复复用、预算、最终校验和清理。
保留已接受内核；本包不提前实现 `code_proof_public.py` 或扩展公开命令。

### 已知问题必须覆盖

- 安装失败后不能误报为正常 idle。
- 一个最终校验组失败时不能跳过其他必要校验和清理。
- 正确释放保留的资源与描述符引用。
- 读取旧状态异常和已保存资源缺失不能逃过最终检查或被忽略。
- 新安装及安装峰值预算检查需通过。

### 交付标准

正常输入可确定性处理；重复执行符合复用规则；替换、冲突、中断、写入失败均准确报错或保持可恢复状态。
提供相关测试、回归和安装边界结果，列出未解决问题。Grok 交付后停止写入，agy 保存候选 commit，ChatGPT 审核。
该包通过只表示 C1 完成，不能宣称整个 CODE 或第一版知识库完成。

## 9. 后续任务队列

| 顺序 | 开发任务 | 设计/验收 | 实现 | GitHub/CI |
| --- | --- | --- | --- | --- |
| 1 | C1 I/O → C2 公开操作和 CLI | ChatGPT | Grok | agy |
| 2 | D1 领域与代码关系 → D2 实验比较 | ChatGPT | Grok | agy |
| 3 | D3 图谱及联合检索 | ChatGPT | Grok | agy |
| 4 | S1 完整文章、S2 复现计划 | ChatGPT | Grok | agy |
| 穿插 | Q1 评测工具、Q2 真实试用和回归 | ChatGPT | Grok | agy |
| 后段 | P1 连续入口、P2 阅读视图、P3 完整恢复 | ChatGPT | Grok | agy |
| 最后 | I1 全流程集成验收 | ChatGPT | Grok 修复发现的问题 | agy 交付 |

ChatGPT 可提前设计领域数据和评测接口。只有接口与文件职责真正独立的不同任务才并行实现。
真实材料验收、独立语义审阅、Obsidian 视觉和隔离恢复结果单独记录，不能用 fixture 代替。

## 10. ChatGPT 每次下发的任务格式

```text
Task-ID / revision：
目标：用户最终能完成什么
负责人：Grok 或 agy
基线：repo、branch、exact HEAD
输入：设计文档、合同、上游结果
允许修改：明确文件或目录
实现要求：具体行为和错误处理
验收：功能场景、必要测试、交付材料
依赖与停止条件：
下一交接人：
```

任务范围变化时产生新 revision，保留前一版。不要让执行者自己扩大范围或降低验收标准。

## 11. 执行者交回的结果格式

```text
Task-ID / revision：
状态：完成待审核 / 阻塞 / 失败
基线与当前候选：branch、HEAD 或交给 agy 提交前的文件摘要
改动：文件与实现内容
验证：实际命令、退出码、结果、完整报告位置
未解决问题：没有则明确写无
写入状态：已停止写入 / 尚有受控进程及原因
下一动作与下一负责人：
```

agy 的交付报告另加 PR URL、base/head、CI checkout、run/attempt、失败 job 和剩余交付项。
ChatGPT 的审核报告明确：通过、需修改或阻塞；绑定被审核的确切版本及具体原因。

## 12. 给群内 Grok Bot 的简短总指令

```text
本群负责开发 RyanHuangNLP/video-paper-wiki 第一版知识库。
使用 Herdr 里已有 Agent：ChatGPT/Codex 负责设计、派发和最终审核；
Grok Agent 负责全部代码、测试代码与修复；agy 负责 Git、Issue、PR、CI 与交付记录。
你只转交任务和结果，不自行再做设计、编码或审查，以减少 Grok Bot 用量。

同一任务只给一个负责人。只有具体事实判断不确定时才请另一 Agent 核实该判断。
不同且独立的子任务可以并行；有依赖先等结果。正在工作时不重复派发。
阻塞后先读结果、保存断点，确认停写，再按 ChatGPT 决定交接。
额度不足时等待或报告，不静默跨角色接管代码。

先把 BOOT-01 交 agy，取得最新产品基线 d440c7a 及必要文档。
随后由 ChatGPT 明确 C1 的范围与验收，再交 Grok 实现。
Grok 交付后 agy 保存候选 commit，ChatGPT 审核；返修仍交同一 Grok 任务。
本地审核通过后，agy 做获准的 push、draft PR → integration 与 CI；
ChatGPT 根据确切版本和验收证据确认完成。禁止自动合并或写 main。

群内每次只发 Task-ID、状态、负责人、结果/报告入口、阻塞和下一动作。
长日志、源码和合同保存在工作区文件中，按任务读取，不反复贴进群聊。
```

## 13. 单独发给 ChatGPT bot 的首条任务

```text
你是 Video Paper Wiki 的设计与验收负责人，实际仓库检查交 Herdr 中的 Codex Agent。
仓库：https://github.com/RyanHuangNLP/video-paper-wiki
最新已知产品基线：codex/code-proof-v1@d440c7aaebb4dcc2c52cab719b0d73347a41493f。

先接收 agy 的 BOOT-01 结果，核对最新源码和必要文档可用。
阅读剩余开发计划、群任务书和 C1 最新合同/失败记录，给 C1 制定一个明确任务包：
目标、基线、允许文件、接口、已知问题、必要测试、验收条件和下一交接人。
只把该实现任务交给 Grok；设计尚未明确的部分先在当前任务中解决。

Grok 返回后，审核 agy 保存的准确候选 commit、实际改动及测试结果，必要时重放检查。
代码或测试代码需要修改时交回 Grok；通过后交 agy 做获准的 PR/CI。
最后核对代码版本、PR base 与 CI，明确任务是否完成、质量是否达到要求。
你可以编写设计/任务/审核文档，但不接管本项目的代码实现。
不要启动其他旧任务、重复派发、自动合并或将本地测试称为真实产品验收。
```

## 14. 单独发给 Grok 开发 bot 的首条任务

```text
你是 Video Paper Wiki 的唯一代码实现负责人，使用 Herdr 中的 Grok Agent。
仓库：https://github.com/RyanHuangNLP/video-paper-wiki
你的首包是 C1：代码证据 retained I/O，基线和分支以 ChatGPT 下发的任务书为准。

先等 agy 准备好分支、ChatGPT 下发明确任务，再开始改代码。
实现 code_proof_io.py 和获准测试，复用已接受的资源基础及 Git/配置内核。
优先覆盖已知安装状态、最终校验、资源释放、缺失资源和预算失败案例。
本包不提前实现公开 CODE 层，不改无关文件，不删除或改写历史证据。

全部生产代码、测试代码、脚本/schema/CI 代码及返修由你完成。
先自测，交回文件清单、实现说明、实际测试结果、问题和报告位置，然后停止写入。
Git 提交/推送/PR 交给 agy，任务验收交给 ChatGPT；不要自己批准完成。
事实判断不确定时仅提出具体问题及证据；不把整个任务重复交其他 Agent。
```

## 15. 单独发给 agy bot 的首条任务

```text
你是 Video Paper Wiki 的 GitHub 与交付负责人，使用 Herdr 中的 agy Agent。
仓库：https://github.com/RyanHuangNLP/video-paper-wiki
首先执行 BOOT-01，让所有执行者取得同一份最新源码与任务材料。

确认产品基线 d440c7aaebb4dcc2c52cab719b0d73347a41493f 是否可取得，
准备基于它的开发分支，并带上经 ChatGPT 核对的计划、当前群任务书和 C1 必需合同。
b86bb02 是旧产品源码加历史材料的快照，不能整包覆盖新开发代码。
如果远程没有最新提交且本环境没有本地对象，报告缺件，等待持有者交付。
按已有授权处理发布；不擅自上传未审阅的私有材料。

返回实际 repo/branch/HEAD、文档位置、固定上游状态及可开始开发的结论。
之后负责候选 commit、范围检查、获准的 push、draft PR → integration、CI 和交付记录。
源码候选变化通知 ChatGPT 重新核对；代码失败或有语义的合并冲突交回 Grok。
不要自行写实现或修改测试让 CI 变绿，也不要自动合并、写 main 或冒充人工 reviewer。
```
