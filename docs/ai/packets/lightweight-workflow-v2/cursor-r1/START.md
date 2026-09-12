# Cursor 四路并行启动

本轮使用 Cursor 内的 Grok 4.6，沿用 xhigh。四路任务与独立 worktree 已准备好，每路约 3–5 小时，Agent 4 约 4–5 小时。本启动单替代父目录的 Grok CLI 启动单。

## 打开四个已有目录

在系统终端运行下面四行，只打开 Cursor 窗口；它们不会启动 Agent 或设置模型。本机已用 cursor --help 验证 --new-window 可用。

```bash
cursor --new-window "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-1/source"
cursor --new-window "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-2/source"
cursor --new-window "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-3/source"
cursor --new-window "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-4/source"
```

也可以在四个 Cursor 窗口分别打开对应目录，然后新建 Agent 会话并选择本机执行。截图仍在 repair/... 分支；这一轮每个窗口应对应 codex/lightweight-workflow-v2-t1、t2、t3、t4，避免改到旧工作区。

## 模型与任务

每个会话明确选择 Grok 4.6 和 xhigh。截图的 High Fast 显示 High；Fast 是另一个速度选项，沿用你的偏好。Grok 4.6 支持 xhigh，详见[官方模型说明](https://cursor.com/docs/models/grok-4-6)。提示词不能替你切换模型。

关闭每个会话的额外 Multitask 分派，把下面对应文件的完整内容作为普通消息粘贴到 Agent，无需 /goal。四个 Agent 各做不同工作，可以同时开始：

| 会话 | 粘贴的提示词 | 工作内容 |
|---|---|---|
| 1 | [AGENT-1.md](AGENT-1.md) | PDF 恢复、笔记保留与诊断 |
| 2 | [AGENT-2.md](AGENT-2.md) | 引用校验与论文选择 |
| 3 | [AGENT-3.md](AGENT-3.md) | 可恢复工作流与阅读 Skill |
| 4 | [AGENT-4.md](AGENT-4.md) | CLI、文档和集成验收 |

Agent 1/2 可独立推进；Agent 3/4 先完成自有代码和测试，再接收冻结后端。源码所有权、交接和验证都在 [Cursor 执行补充](OVERRIDE.md) 及父任务单中明确。若会话因宿主限额暂停，继续同一个会话并让它读取自己的 progress 从断点接续。单个提示词不会保证应用持续运行固定时长。

完成后回到这里交 Architect 审查。当前准备只生成启动材料，尚未发送 Cursor Agent 提示词，也未修改实际模型/速度设置。
