# 四终端启动单

四个真实 linked worktree 已从已验收 `0fcae592` 建好，固定 vendor 已本地初始化。无需再开 worktree，也不要复用上一轮 cwd。每路约 3–5 小时实质工作，T4 约 4–5 小时。下面是用户手动启动方法，准备文件本身不会启动模型或后台任务。

每个系统终端先运行对应 shell 命令，进入 Grok 后再粘贴对应 `/goal`。CLI 已本地核对支持这些 flags；登录已存在，缓存模型含 grok-4.6，本次受限环境未实时刷新远程模型列表。若终端提示登录/模型不可用，按真实状态处理，不能自动换模型。

## 终端 1

```bash
grok --cwd /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-1/source --model grok-4.6 --reasoning-effort xhigh --no-subagents --disable-web-search
```

```text
/goal 完成 /Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/lightweight-workflow-v2/TERMINAL-1.md。先读同目录 COMMON.md、CONTRACT.md、freeze.json 并核验基线。在指定独立 worktree 连续推进约 3–5 小时的 PDF 原子写入、中断恢复、重复导入保留笔记、只读工作区诊断与定向回归。可用后端尽早发布冻结 milestone，全部完成后发布 final ready。只改允许路径，不做 Git 写操作。提前完成不凑时长；缺输入或未完成留下可接续简报，不无限等待。
```

## 终端 2

```bash
grok --cwd /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-2/source --model grok-4.6 --reasoning-effort xhigh --no-subagents --disable-web-search
```

```text
/goal 完成 /Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/lightweight-workflow-v2/TERMINAL-2.md。先读同目录 COMMON.md、CONTRACT.md、freeze.json 并核验基线。在指定独立 worktree 连续推进约 3–5 小时的实时证据与索引校验、QA/写作论文选择、原子 Markdown 输出及对抗回归，关闭已复现的三项导入漏洞。公开 API 可用即发布冻结 milestone，完成后发布 final ready。只改允许路径，不做 Git 写操作。提前完成不凑时长；缺输入或未完成留下可接续简报，不无限等待。
```

## 终端 3

```bash
grok --cwd /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-3/source --model grok-4.6 --reasoning-effort xhigh --no-subagents --disable-web-search
```

```text
/goal 完成 /Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/lightweight-workflow-v2/TERMINAL-3.md。先读同目录 COMMON.md、CONTRACT.md、freeze.json 并核验基线。在指定独立 worktree 连续推进约 3–5 小时的 prepare/status/complete 可恢复工作流、统一自然语言阅读 Skill 和恢复测试。先做独立代码与协议测试，再按规则接收终端1/2冻结快照接通真实后端，无需等依赖才开始；完成发布 final ready。只改允许路径，不做 Git 写操作。提前完成不凑时长；缺输入或未完成留下可接续简报，不无限等待。
```

## 终端 4

```bash
grok --cwd /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-4/source --model grok-4.6 --reasoning-effort xhigh --no-subagents --disable-web-search
```

```text
/goal 完成 /Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/lightweight-workflow-v2/TERMINAL-4.md。先读同目录 COMMON.md、CONTRACT.md、freeze.json 并核验基线。在指定独立 worktree 连续推进约 4–5 小时的 CLI、自然语言入口文档、集成验收。先独立实现命令与验收用例，再接收终端1/2/3冻结快照；完成真实 CLI 回归、一次全量测试、新 wheel 离线验证、已有真实 PDF 当前模型问答/短稿和 Bash/zsh 文档试用，冻结完整候选交 Architect。只改允许路径，不做 Git 写操作。提前完成不凑时长；缺输入或未完成留下可接续简报，不无限等待。
```

各路 progress/handoff 位于主仓库 `artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-N/`。接口问题保存在自己的 questions/findings 中；其他终端可以读取并在自有范围修复，但不能改变冻结合同。四路完成后统一交 Architect 审查，再交 Repo Steward 处理 draft PR → integration 和新的 CI；本启动单不授权合并。
