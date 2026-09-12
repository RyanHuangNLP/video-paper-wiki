# 下一轮四终端：恢复、可信引用与自然语言工作流

用户在 2026-09-07 明确要求继续下一轮，并安排可连续开发 3–4 小时以上的工作量、多个 terminal 并行。本轮是四个**用户手动启动的 Grok 终端**，每个使用 Grok 4.6 / xhigh；不自动启动会话。目标是交付有实际功能增量的候选，预计每路约 3–5 小时；提前完成不凑时长，时间到仍未完成就保存真实断点，不把耗时当作验收。

## 开始前

主仓库 ROOT=`/Users/huangzhanpeng/python_code/video-paper-wiki`。先读 ROOT 的 AGENTS.md、docs/ai/task-index.yaml、docs/ai/codex-team.md，再读本 COMMON、CONTRACT.md、自己的 TERMINAL-N.md 和 `freeze.json`。旧八小时自动循环已结束；当前用户四终端指令与本包取代该旧包的调度方式。只继承其中适用的角色和边界，不恢复定时任务，不开子代理，不调用另一个模型，不启动 Git/PR 操作。

交付基线为已通过四矩阵、每项 2246 测试的 `0fcae592acb977c6b422e7de3b2c3e0cf79df5a0`。这是 PR95 的已接受历史，不能冒称为本轮新实现的测试。新源码工作区已实际创建为独立 linked worktree：

| 终端 | cwd（相对 ROOT） | 分支 | 主要职责 |
|---|---|---|---|
| 1 | `.work/parallel/lightweight-workflow-v2/terminal-1/source` | `codex/lightweight-workflow-v2-t1` | PDF 原子写入、重试恢复、工作区诊断 |
| 2 | `.work/parallel/lightweight-workflow-v2/terminal-2/source` | `codex/lightweight-workflow-v2-t2` | 引用实时验证、论文选择、原子输出 |
| 3 | `.work/parallel/lightweight-workflow-v2/terminal-3/source` | `codex/lightweight-workflow-v2-t3` | 可恢复工作流与统一阅读 Skill |
| 4 | `.work/parallel/lightweight-workflow-v2/terminal-4/source` | `codex/lightweight-workflow-v2-t4` | CLI、文档、集成与完整验证 |

证据根 E=`ROOT/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2`；自己的可写证据是 `E/terminal-N/`。自己的 scratch 是 `ROOT/.work/parallel/lightweight-workflow-v2/terminal-N/` 下除 source 外的目录。源码中只准修改本终端列出的精确路径；其他终端工作树、主仓库及既有 integration 工作树都只读。不要把本轮测试输出混进 tracked source。运行开始先核对 baseline.json、freeze.json 的 SHA、自己的 HEAD/tree/vendor 和实际模块来源；工作区不是空壳，禁止重建/覆盖或整树复制。

## 环境、成本与真实输入

共享运行时只读：`ROOT/.venv/bin/python`（已验证 Python 3.13.13）。每次设置 `PYTHONPATH` 为**自己的 source/src**，记录导入模块的 `__file__` 和 SHA，避免误测主仓库旧源码或安装包。设置 `PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`UV_OFFLINE=1`、`UV_PYTHON_DOWNLOADS=never`、`GIT_OPTIONAL_LOCKS=0`；不要安装/复制四套环境，不改锁文件，不下载模型。vendor 已从本地对象初始化到 `9f8c1199047eac2c3828496279fbb7ba9540b90b`，不要 fetch/update。

下面是 Bash/zsh 均可用的定向测试结构；将路径中的 N 换成本终端数字，最后测试路径用自己包内清单。不使用嵌入多个词的命令字符串。

```bash
cd /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-N/source
export PYTHONPATH="$PWD/src"
export PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never GIT_OPTIONAL_LOCKS=0
LW_TEST_TMP="$(mktemp -d /private/tmp/lw2.XXXXXX)"
/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python -B -m pytest -q \
  --basetemp "$LW_TEST_TMP/base" -o "cache_dir=$LW_TEST_TMP/cache" tests/research/test_light_pdf.py
```

遵循 README 的短真实临时目录规则。保留日志后仅清理自己创建的短目录，不能清理别人的 `.work`/`/tmp`。T1–T3 跑定向/相关兼容测试；T4 最终集成后跑一次全量和一次新 wheel 的隔离验证。测试失败修复后重跑受影响项；无新改动不重复全量。缺 Python 3.12 如实留给后续 CI，不安装一套环境来凑矩阵。

真实 PDF 只在 T4 最后试用时直接读 ROOT/inbox/arxiv-2204.03458.pdf（baseline 绑定），不复制原 PDF、不截图、不新抓论文。单元测试用已有合成生成器或自己短目录内小样本。不要复制历史几十 MB 的报告或旧环境。生成 workspace 放自己的 scratch 下 `.work/` 子目录；已确认的真实 Vault 不在本轮写入范围。不得运行 vpwiki-admin、apply、外部模型/API、网络脚本、OCR/Docling。手动 Grok 当前会话产生答案允许； Python 产品仍保持零网络。

## 依赖与持续工作顺序

四路同时开始。T1/T2 不依赖其他实现。T3 先写工作流状态机、内部存储/恢复、Skill 与协议测试；T4 先写 CLI 解析/dispatch/错误测试和文档，无需等后端全部完成。T1/T2 完成可运行公开 API 后尽早发布 backend milestone；T3 可只读接收这些快照完成真实集成。T4 最后接收各路 final。不要从另一个终端的活动源码直接 import/copy，不用 mock 结果声称真实链路成功。

跨目录接收仅允许从指定生产者 immutable `handoffs/<revision>/files/<relative_path>` 复制到**接收者自己的** source 对应路径；先核对 hash、allowed set、baseline、contract/freeze，再复制。禁止 Git merge/cherry-pick 或读写另一个终端源文件。T3 可接收 T1/T2 生产文件和测试；T4 可接收 T1/T2/T3 生产文件、测试及 Skill。接收文件仍由原作者维护；接收者不能擅自改它。需要修复时写 findings 给原作者，新 revision 交接；不覆盖旧 revision。共享接口缺口写 `questions.md` 并完成其他独立工作，不能自行改 CONTRACT。

依赖等待前先完成尚未完成的自有代码/测试/文档。确实只剩等待时约每 60 秒检查一次 handoff；连续等待最多 45 分钟，或到自己的预算结束，写 `needs_input` 断点。不要无限空转或使用 sleep 凑 3–4 小时。后续 `/goal` 可从报告继续。

## 交接格式与冻结

每路在 `E/terminal-N/` 写进度 `progress.md`，完成阶段时创建新的 `handoffs/r1/`（后续 r2/r3，永不覆盖）。目录内 `files/` 保存精确自有候选文件、`report.md` 保存开发简报、`checks.json` 保存实际命令/cwd/exit/结果。最后原子写 `handoff.json`；通过该阶段自检才另写**相同内容**的 `ready.json`。不通过也交接真实失败材料，不创建 ready。消费的是冻结副本；本地源码继续下一阶段时必须新 revision、重新绑定摘要。

handoff 至少含：`schema=lightweight-workflow-v2-handoff.v1`，terminal，revision，phase=`backend|final`，status=`ready|needs_fix|needs_input`，snapshot_stopped_writing=true，baseline_head，baseline_sha256，contract_sha256，freeze_sha256，source_root，`files`（每项 relative_path、sha256、size_bytes），`inputs`（消费的 handoff/ready 路径及 SHA），`artifacts`（报告/测试日志路径及 SHA），commands，known_gaps，blocking_findings。files 只含本 lane 自有路径；T3/T4 的接收路径另列 `imported_files` 与源 handoff/hash；T4 再输出完整合并文件清单 `integrated_files`。

成功 final 必须固定全部自有文件和所有最终输入，ready/handoff byte-identical，停止自有源码写入。backend milestone 只保证该快照冻结，不等于整路已完成；消费者最终必须检查生产者 final 是否改变已接收文件。若改变，用 final 重做受影响集成。单个测试日志须绑定运行前后相同源码 hash；不能给新字节贴旧测试标签。

简报包含：做了什么、具体测试结果、预计未完成量、需要谁处理什么、没有运行的验证、Grok 当前模型/设置、实际会话信息（能读到才填），以及可供 Architect 审查的绝对路径。final ready 只代表 Builder 候选；Architect 独立审查后才由 Repo Steward 串行提交、draft PR → integration、fresh CI。四个 Grok 终端都不 commit/stage/fetch/push/改 PR/merge，PR95 当前状态保留。
