# 四路工作流候选审查

本轮整体状态：`CHANGES_REQUIRED_AND_INTEGRATION_INCOMPLETE`。这是一轮实际工作区及交接审查，不代表执行了新的 Cursor 会话、Git 交付或远程 CI。旧 PR95 的已验收提交仍是历史基线，不给新字节提供验收。

## 当前可验证状态

| Agent | 实际状态 | 后续责任 |
|---|---|---|
| 1 | 有正式 r2，五个冻结文件与当前源码相符；独立检查和 Architect 复放均发现缺口 | 执行 AGENT-1-CONTINUE，发布新 final |
| 2 | 正式目录只有 r1/r2，当前五文件仍与此前被拒的 r2 完全相同 | 执行既有 REPAIR + ADDENDUM，发布新 final |
| 3 | 有工作流/Skill 源码，但正式目录未见 handoff/ready；已导入旧 T2 r2 | 修复本轮合同 C 缺口，更新依赖并发布真正交接 |
| 4 | progress 明确写着尚未完成；缺七个新 T3 文件，没有 final | 接收修复后的 final，再完成真实 CLI、全量、wheel、PDF 试用与文档验收 |

`lane-snapshot.json` 记录实际自有/接收文件 SHA 与正式 handoff 的逐文件比对。证据搜寻范围及独立 Git 只读状态见 steward-status.json。未发现的文件不等于可以补写一份虚假的历史记录。

## Agent 1：正常测试通过，但恢复和诊断仍需返修

独立审查复跑三文件 29 passed，含兼容的六文件 48 passed（48 已包含 29，不是两个不相交集合）。Architect 另通过公开 API 复放确认：非法 UTF-8 使 extract/inspect 抛异常；坏 staged pair 在验证前已发布到 final；transaction symlink 导致外部锁写入；有效空 index 被标 stale。恢复测试还把子进程解释器硬编码为本机用户路径，须改为当前锁定测试运行时以支持 CI。

详情见 terminal-1-review-r1.md、probe-pdf-results.json 和 AGENT-1-CONTINUE.md。以上修复在原五路径内，不委托其他 lane 代改。

## Agent 2：前次返修仍未交付

实际 light_index.py 为 `c05abaa47217ca4007c38ecf1072d60479eb1f0c424ec2eebbcdf4e10ee26ac1`，light_context.py 为 `ef8e41eefb00a66542ec0882e7710c4684e77dd4f6378d10fc8d7b7164b53cc3`。这是上轮审查的同一快照，旧 50 项通过及失败探针继续只描述这份代码。缺口为输出 staging 后缺少最终 live check、畸形 context/index 的异常或错误放行、public search 的 selection 规则未完整落实。见 AGENT-2-CONTINUE.md 引用的两份不可变返修包。本次没有为了重复相同证据再跑完整测试。

## Agent 3：真实后端复现的缺口

被查 light_workflow.py SHA-256：`74f33c8534bd519e2ae7cd4efc663a8f9829b908da027b500cea6887695ef197`。Architect 使用该工作区的真实 T1/T2 后端及小型合成 source，正常 prepare→complete 成功。三个自有 test 文件独立复跑 37 passed；这些测试没有覆盖以下情况。

- **P1，状态路径和临时文件归属。** `.light-workflow`/sessions/locks symlink 被接受并在外部测试目录写入；staging symlink 也被接受。预置同名未知 completion-intent tmp 被覆盖并移走。对应 `_exclusive_lock`、`_publish_session`、`_install_session_file`。合同要求拒绝 symlink state，未知文件保留，不以名称代替归属证明。
- **P2，发布前快照复核。** staged manifest 写完后修改 source.md，prepare 仍发布新 session，随后返回 OK/stale。最终 live check 应在发布之前；失效应返回 INDEX_STALE 且不发布新 session。
- **P2，request 结构及关联字段。** 以合法 B 编码保存非法 kind、list query、非法 selection 和额外字段，并重算 manifest/session ID，status 仍 awaiting_model、complete 仍成功。应同时检查 request 精确字段、类型和其与 context 的对应关系。

完整观察在 probe-workflow-results.json，脚本在 probe_workflow.py。所有输出只来自临时合成工作区，结束后清理；没有修改产品源码或真实 PDF。AGENT-3-CONTINUE.md 给出原九路径内的修复、回归、依赖更新及正式交接要求。

## Agent 4：剩余集成工作

其 progress 的 99 passed / 4 skipped 是 Builder 已保存的局部结果，本次没有冒称独立复跑该数字。当前 source 尚无 light_workflow.py、三个 T3 test 和三个新 Skill 文件；旧 ingest/query 文件仍在，不能据此算接收了 T3 的新版本。未见集成 final、全量新结果、此次源码的新 wheel、当前模型真实 PDF QA/draft 及 Bash/zsh 最终证明。

AGENT-4-CONTINUE.md 接续原包剩余事项。先完成独立 CLI/docs/tests，收到生产者的新冻结副本后精确集成；不得从活动源码直接复制或代修其他作者文件。完整候选通过后再由 Architect 审查并决定 Steward 的串行交付，当前没有 merge 授权。

另有安装验证方法问题需在继续时修正：当前 test 硬编码本机 Python/cache，以 `-I` 配合被忽略的 PYTHONPATH 试图加载 prefix 安装，并容许缺 console 入口时以 module 代替。须验证确实来自新 wheel 的包及两个入口。该结论来自代码审查，本次没有新 wheel 的执行结果。

## 验收结论和下一步

本轮尚无可接受的完整集成快照。Builder 的 `final/ready` 是交接声明，仍需独立检查其真实文件和行为；进度文字不能替代存在的 ready.json。各 Agent 继续各自原工作区及原 Cursor Grok 4.6 会话，不新增并行工作者。所有旧交接、失败证据与原合同保持原字节。修复完成后返回新的实际 handoff/ready 绝对路径。
