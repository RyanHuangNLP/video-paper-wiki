# Agent 3：完成原合同 C 的返修和正式交接

这是 Architect 对现有范围的返修指令。继续使用 Cursor 当前 Grok 4.6 会话，遵守 cursor-r1/OVERRIDE.md；不调用 CLI 模型或新增代理。源码工作区仍为 `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-3/source`。只恢复 TERMINAL-3.md 所列九个自有路径的写权。T1/T2 输入只能从新冻结交接按 hash 导入，不能代改。

本次观察的 light_workflow.py SHA-256 为 `74f33c8534bd519e2ae7cd4efc663a8f9829b908da027b500cea6887695ef197`。37 项自有定向测试独立通过；以下真实后端探针仍失败。阅读同目录 probe_workflow.py 和 probe-workflow-results.json。探针会写相邻结果文件，只能复制到自己的 scratch 后重放；不得覆盖 Architect 历史记录。

## 必须修复的现有合同缺口

1. **拒绝符号链接状态路径，并保护未确认归属的文件。** `_exclusive_lock`、`_publish_session` 和 `_install_session_file` 没有检查完整的状态目录路径。把 `.light-workflow`、`sessions`、`staging` 或 `locks` 预先设为 symlink，prepare 仍成功；其中 `.light-workflow`、`sessions`、`locks` 三个探针在外部测试目录留下 lock/session 文件；`staging` 探针也被接受，临时文件随后被清理。固定的 `.<session>.completion-intent.json.tmp` 若已存在普通未知文件，也会被覆盖后移走。合同 C 明确要求拒绝 symlink state、保留未知项、仅恢复经版本化 ownership marker 证明归属的临时文件。对 prepare/status/complete 一致检查已有状态路径及锁/临时目标；在读写前拒绝危险路径。使用有明确归属的唯一 staging，不得把路径名称相同当作所有权。补充普通未知文件和 symlink 的保存断言。无须承诺防御任意外部编辑器在最后检查之后的竞态。

2. **发布前再次核验 live context。** 当前 `_export_and_validate` 检查后，代码写三份 staged JSON 并 rename，下一次核验已经在发布之后。探针在 staged manifest 写完时修改 source.md，prepare 返回 `ok=true/state=stale`，并留下一个新 session。合同要求导出后及实际发布前核验。完成 staging 后、安装前再验证；失效时返回 `ok=false/INDEX_STALE`、session_id=null，不安装新 session，保留已有历史，仅清理可证明归属的临时文件。普通成功和相同请求复用保持兼容。

3. **验证 request 的完整结构及其与 context 的对应关系。** `_validate_loaded_session` 只检查 request 的 schema/root 和摘要。探针将 query 改为 list、kind 改为非法值、selection 改为非法 ID、增加字段，再按公开公式重算文件摘要、manifest 和目录名；status 仍 awaiting_model，complete 仍成功。request 必须恰好符合合同 C 的字段集合、类型、非空 query、合法 kind、normalized selection，并核对 request 与 context 的 kind/query/requirements/selection 一致性。摘要自洽不能代替结构校验。分别覆盖错误类型、额外/缺字段，以及字段类型合法但与 context 不一致的情况。status 对损坏 session 报 needs_attention；complete 返回 LIGHT_SESSION_INVALID 且不创建 intent/output/receipt。

同时检查上述 staging 修复的真实中断恢复：在 prepared 文件移动、intent/receipt 临时写入各阶段中断，重试只恢复准确绑定的自有产物，未知项保持原字节。不要只在 intent/output 已成功安装后的 hook 测恢复。

## 输入与依赖

现有导入的 Agent 2 r2 已被 Architect 拒绝，不能作为最终输入。先完成独立的工作流修复/测试，然后读取 `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/architect-agent2-r1/REPAIR.md` 和 REPAIR-ADDENDUM.md 了解接口缺口。等待 Agent 2 新 final，核对并导入其精确五文件，重跑受影响的真实后端测试。Agent 1 如有新 final，同样核对并导入。等待时遵守原包的有界 checkpoint 规则，不把缺依赖写成完成。

## 必须完成正式交接

正式证据根的绝对路径是 `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-3`。`E` 是文档中的别名，不是要创建的目录名。不要仅在 progress.md 声称某个目录存在。保留全部旧材料；使用尚不存在的下一个 revision（通常 r2），写 files/、report.md、checks.json、handoff.json 和 byte-identical ready.json。九个自有路径与 imported_files 分列，绑定全部实际输入 handoff SHA、原 freeze/dispatch、本修复指令 SHA；逐项核实声明的文件存在且摘要相符。

在正式目录缺少旧 r1 时，说明该事实及找到的实际旧位置；不得伪造历史交接，也不迁移/删除未知旧材料。最终报告给出两个实际存在的绝对路径：handoff.json 和 ready.json。完成后停止写入，交 Architect 审查。不要运行 Git、改 PR95、改原合同、写真实 Vault、执行全量或 wheel；全量和真实模型 CLI 试用仍归 Agent 4。
