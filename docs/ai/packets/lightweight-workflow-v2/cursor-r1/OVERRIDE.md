# Cursor 执行补充：Grok 4.6

用户最新明确要求：这轮在 Cursor 中开发，仍用 Grok 4.6。本补充只替换执行入口/运行者称呼；继承父目录 freeze.json 绑定的产品合同、25 个源码路径归属、依赖、测试、候选交接和四个既有 worktree。父目录所有冻结文件和历史验收保持原字节。

## 当前执行规则

- Builder 是 Cursor 中选定 Grok 4.6 的四个独立 Agent 会话。父包“终端 N”对应这里“Agent N”。这是四个已经授权的并行工作包，不由一个 Agent 再拆出子代理。
- 先在 Cursor 每个会话的模型选择处选 Grok 4.6，推理强度保持 xhigh；Fast 为独立速度设置，沿用用户选择。截图中的 High 不能记成 xhigh。若当前界面/套餐不提供指定模型或强度，记录实际可用设置并报告，不自动切模型、不购买或升级。
- 启动使用普通自然语言提示词；旧 START.md 的 grok shell 命令、/goal 前缀、Grok CLI 会话/轮数约定不再是要求。不要调用 Grok Build CLI、Cursor agent CLI、额外 API 或外部模型来代替当前 Agent。
- 当前四份任务仅需要一个会话各负责一份。在这些会话中关闭 Multitask/额外自动分派，不再创建子代理、best-of-n 或新的 worktree。本轮并行来自四个独立会话。
- 每个会话直接打开指定已存在的 source 目录，以本机执行。编辑器实际项目根、命令 cwd、Python 模块来源必须对应该目录。不要在主仓库的 repair/... 工作区直接实施，也不把 Cursor 新建的别处 worktree 当成本包目录。
- 父合同与 T4 试用中“当前 Grok 会话”现在指 Cursor 中当前 Grok 4.6 Agent。它读取导出的 context 并生成模型文档；Python 运行时仍不调用模型服务、OCR/Docling 或网络。T3 文档用宿主中立的“当前会话模型”，不要把最终产品限定为 Grok CLI。
- 开始核对来源/运行设置，随后持续完成本包各里程碑，不停在分析或计划。约 3–5 小时是工作量估计，不承诺宿主无中断运行；达到宿主限额、需要权限或缺依赖时保存 progress/checkpoint，用户继续同会话后从已验证断点接续。没有进展不要空转凑时长。
- 仍只修改自有源码和证据路径；保留实际权限提示，不改全局设置绕开限制。Git 暂存/提交/切分支/推送、Cursor Apply/Merge/自动发布仍不在 Builder 范围。完成后提交冻结候选给 Architect。

## 输入与交接绑定

先读此补充和同目录 dispatch.json，再按父 COMMON.md 读取主仓库 AGENTS.md、task-index、team、父 CONTRACT、自己的 TERMINAL-N、父 freeze 和 baseline。本补充覆盖其中与“必须通过 Grok CLI、必须 /goal、CLI session”直接冲突的执行要求；其余产品规则全部保留。

交接仍写父 COMMON 指定的 E/terminal-N/handoffs/<revision>。handoff 的 freeze_sha256 继续绑定父 freeze；新增 dispatch_sha256 绑定本目录 dispatch.json，execution_host=cursor，requested_model=grok-4.6，requested_effort=xhigh。observed_model/observed_effort 只记录可观察设置，无法读取就标 null 并说明，不虚构 CLI session_id。若原位置已有旧启动方式的材料，使用新的 revision，不覆写。

来源索引：父 contract SHA `559e2b339c192837fa5d6c47f15ea7688f484155b95b2492f28eeee6d940e5dc`；父 freeze SHA `2128528583787cb10aad69eb1954b424bba10873327885792dce7c7e3ae3099e`。新的 dispatch 绑定本补充和四条普通提示词。本文件不修改实际 Cursor 模型设置，也不声称已经启动四个 Agent。

运行说明参考：[Cursor Agent](https://cursor.com/docs/agent/overview)、[Grok 4.6 的 effort 与速度](https://cursor.com/docs/models/grok-4-6)、[worktree 隔离](https://cursor.com/docs/configuration/worktrees)。这些页面用于核对宿主能力，不把页面中的安装、Git 或自动 worktree 示例加入本项目授权。
