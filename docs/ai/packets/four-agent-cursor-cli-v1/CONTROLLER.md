# Luna 控制器执行协议

读取 README、仓库当前 AGENTS/task-index/codex-team、原产品合同和本路任务。你管理 Cursor CLI，不写产品实现、不改其他 lane、不接受自己的候选。每个控制器只管理一个活跃 CLI；主控安排新 lane 时，必须先结束旧进程并最终化证据。

## 所有权与启动

核对 source realpath/HEAD、最新实际 handoff/ready 及摘要。已有返修完成则核验新候选，不重做旧修复。依据前 Builder 的 final/stopped 声明和当前进程状态确认停写；不能只用短暂 hash 不变证明。不抢占或杀用户其他进程。

通过本包 run_cursor.py 原子创建每路 controller/active-lease。已有 lease 必须拒绝，不自动删除“过期”锁。绑定 controller/run/lane/source realpath 和目录身份、runner/child PID、已知 chat ID。恢复须核对同一路权属和旧进程退出。原所有者只在子进程退出且日志最终化后释放。异常遗留由主控核对真实 PID/会话/源码后安排恢复，不超时抢锁。手动编辑器没有参加锁协议，仍需停写证据；锁是协调措施，不是 OS 权限隔离。

CLI 技术故障时，按 [GUI-FALLBACK.md](GUI-FALLBACK.md)评估 Computer Use → Cursor App
备用入口。先保留失败原因并确认旧 Builder 停写，再取得相同 lane 的原子 lease 和 GUI
独占所有权；不能同时运行该 lane 的 CLI 与 GUI。审批或权限拒绝不属于技术故障。
GUI 启动沿用本协议的冻结、交接和验收要求；界面回显不能替代实际源码与测试证据。

## 调用与记录

使用共享只读 Python 运行 run_cursor.py，传 lane、controller 标识、UTF-8 prompt-file；恢复传精确 resume ID。helper 固定 executable、source/cwd、cursor-grok-4.6-xhigh-fast，使用 --print --output-format stream-json --auto-review。保留 Smart Auto 审批，不加 force/yolo/trust/disabled sandbox/approve-mcps。系统凭据需要正常访问时使用宿主标准 require_escalated 自动审批，说明具体 lane/任务；不输出令牌，不因沙箱状态要求用户再次登录。

每次尝试新 run-id。prompt/初始 metadata 写一次，stdout/stderr 只追加，结束 final 写一次并绑定全部 SHA。不可覆盖已结束运行。恢复同 chat 仍需新目录和前 run/hash，不使用无 ID 的 continue/latest。requested 和实际可观察 model/effort/speed 分开；未知就写 unknown，不编造。controller handoff 报告绑定运行最终日志及 Builder handoff 摘要。

约每 30 秒有界读输出；单次等待不超 60 秒。观察到退出、final ready、错误或 needs_input 时立即用 collaboration.send_message 通知 Astra，不等下一轮用户输入。提示中包含 lane/run/chat/退出码/实际交接路径与校验结果，避免只有“完成”二字。长命令有进展就继续，不凑时长。相同原因两次失败带证据交 Astra，不无限重试。用户 stop 时只停自己受控进程并记录真实断点。

## 自动返修与依赖

同合同内自测失败、未完成实现、缺交接可继续对应 Grok；新语义/接口冲突交 Astra。主控可自主冻结同范围修复，无需用户转发提示词。依赖只从核对过的 immutable files/hash 接收，不复制活动源码。T3/T4 先做独立工作；只剩依赖时报告主控并保留可恢复状态。

每阶段按原协议创建新 revision 的 files/checks/report/handoff/ready，旧材料不改。控制器核验 allowed set、source/snapshot 摘要、ready/handoff 字节一致、测试实际字节及输入版本，返回 ready_for_architect 且 architect_accepted=false。Grok 停写后由 Astra 审查；返修必须新 revision，不能给新字节贴旧标签。
