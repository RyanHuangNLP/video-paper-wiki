# 五 Agent 启动入口

先完成 Cursor CLI 登录（已有登录则只核验，不重复登录）：

```bash
/Users/huangzhanpeng/.local/bin/agent login
```

重新打开主控会话，使项目 `.codex/config.toml` 及四个自定义 agent 文件加载。主控选择 `GPT-6 Astra / ultra / Fast`。配置请求四个子代理，不保证能越过宿主并发限制；开始时必须检查当前工具实际支持主控+四个子代理。

可直接给主控的提示词：

```text
按 /Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/five-agent-cursor-cli-v1/README.md 和 CONTROLLER.md 启动五 Agent 编排。主控保持 gpt-6-astra / ultra / Fast；四个子代理必须分别显式使用 gpt-5.6-luna / xhigh，对应 lw_cursor_1、lw_cursor_2、lw_cursor_3、lw_cursor_4，各控制一个 Cursor CLI，Builder 统一 Grok 4.6 / xhigh / Fast。

先验证当前可同时容纳主控和四个子代理、Cursor CLI 已登录且所需模型组合可用、四个旧手动 Cursor Agent 已停止写各自工作区。任何条件不满足就报告具体条件，不伪造启动成功、不降级模型或改成其他拓扑。

读取最新 Architect 审查和各 lane 最新正式 handoff，从实际断点接续现有四路任务。四个控制器各自在原 source 工作区管理进程、日志、精确 chat ID 的恢复及交接核验；Grok 实现，Luna 检查，Astra 最终审查。遵守原 25 路径单写者和冻结合同。不要重复已经通过的返修，不启动额外代理，不自行 Git/PR/merge。
```

若当前客户端的 spawn 接口不接受自定义 agent 名称，主控可读取对应 `.codex/agents/lw_cursor_N.toml`，把其职责传入原生子代理提示词，并仍显式传 `model=gpt-5.6-luna` 与 `reasoning_effort=xhigh`。这只改变角色指令的加载方式，不改变 Agent 数量、模型或写权。

需要从终端打开应用兼容的主控时，可使用以下已安装版本；此命令由用户运行，不是本包创建时已经启动的会话：

```bash
/Applications/ChatGPT.app/Contents/Resources/codex \
  -C /Users/huangzhanpeng/python_code/video-paper-wiki \
  -m gpt-6-astra \
  -c 'model_reasoning_effort="ultra"' \
  -c 'service_tier="priority"'
```

在该会话发送上面的主控提示词。保留现有权限配置，不使用绕过审批或 sandbox 的参数。CLI 不等于自动创建一个新 Codex 桌面侧栏任务。
